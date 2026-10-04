import { describe, expect, it } from 'vitest';
import { relativeLuminance } from './color';
import {
	CORRECTS_AMOUNT,
	EINVOICE_RESOLUTION,
	SALE_CONDITION_CASH,
	amountNoteDocument,
	brandTones,
	claveGroups,
	creditNoteDocument,
	documentKind,
	documentLines,
	documentNumber,
	documentSummary,
	exchangeRate,
	fiscalBlock,
	isNote,
	issuerActivity,
	issuerLines,
	returnedTotal,
	taxBreakdown
} from './documents';
import { mergeSettings } from './settings';
import type { AmountNote, EmittedDocument, SaleReturn } from './types';

const base = mergeSettings({});

/** Configuración con el negocio que pida la prueba. */
function con(business: Record<string, unknown> = {}) {
	return mergeSettings({ business });
}

/** Lo que T-705 va a mandar. Hoy no viaja; las pruebas lo fabrican. */
function emitido(environment: EmittedDocument['environment']): EmittedDocument {
	return {
		clave: '50615092600310123456700100001040000000123100000001',
		consecutive: '00100001040000000123',
		environment,
		economic_activity: '523101'
	};
}

describe('brandTones', () => {
	it('conserva el color elegido como base', () => {
		expect(brandTones('#0e7490').base).toBe('#0e7490');
	});

	it('ordena los tonos de oscuro a claro', () => {
		const t = brandTones('#0e7490');
		const lum = (hex: string) => relativeLuminance(hex);
		expect(lum(t.deep)).toBeLessThan(lum(t.base));
		expect(lum(t.base)).toBeLessThan(lum(t.line));
		expect(lum(t.line)).toBeLessThan(lum(t.tint));
	});

	it('la tinta se lee encima de la base', () => {
		// Un tono oscuro pide texto blanco; uno claro, texto oscuro.
		expect(brandTones('#0e7490').ink).toBe('#ffffff');
		expect(brandTones('#fde68a').ink).toBe('#0f172a');
	});
});

describe('documentKind — lo dice la venta, no la configuración (RN-85)', () => {
	it('una venta sin tipo es el documento de siempre', () => {
		// Todas las anteriores a la migración 014, y las de una compañía que no
		// factura electrónicamente.
		expect(documentKind({})).toBe('invoice');
		expect(documentKind({ document_type: null })).toBe('invoice');
	});

	it('la factura y el tiquete son lo que se guardó', () => {
		expect(documentKind({ document_type: '01' })).toBe('einvoice');
		expect(documentKind({ document_type: '04' })).toBe('eticket');
	});

	it('la de exportación también, y lleva su bloque fiscal (T-727)', () => {
		expect(documentKind({ document_type: '09' })).toBe('eexport');
		expect(isNote('eexport')).toBe(false);
		expect(fiscalBlock({ document_type: '09' })?.kind).toBe('eexport');
	});

	it('las notas son lo que son, y no cobran', () => {
		expect(documentKind({ document_type: '03' })).toBe('ecredit');
		expect(documentKind({ document_type: '02' })).toBe('edebit');
		expect(isNote('ecredit')).toBe(true);
		expect(isNote('edebit')).toBe(true);
		expect(isNote('eticket')).toBe(false);
	});

	it('un tipo que no se imprime no se hace pasar por factura electrónica', () => {
		expect(documentKind({ document_type: '99' })).toBe('invoice');
	});
});

describe('creditNoteDocument — la nota con la forma de las plantillas (RN-89)', () => {
	const devolucion: SaleReturn = {
		id: 12,
		sale_id: 7,
		sale_number: '20260926103036',
		user_id: 2,
		user_name: 'Caja Uno',
		created_at: '2026-09-26T11:00:00',
		reason: 'no le quedó',
		subtotal: 1000,
		tax: 130,
		total: 1130,
		is_full: false,
		items: [
			{ id_product: 1, name: 'Arroz', quantity: 1, price: 1000, subtotal: 1000, tax_rate: 0.13, tax_amount: 130 }
		],
		document_type: '03',
		reference_code: '06',
		sale_document_type: '04',
		sale_created_at: '2026-09-26T10:30:36',
		sale_client_id: 5,
		sale_payment_method: 'Efectivo'
	};

	it('lleva lo devuelto, la referencia al original y nada de efectivo', () => {
		const nota = creditNoteDocument(devolucion)!;
		expect(documentKind(nota)).toBe('ecredit');
		expect(nota.reference).toEqual({
			document_type: '04',
			number: '20260926103036',
			date: '2026-09-26T10:30:36',
			code: '06'
		});
		expect([nota.subtotal, nota.tax, nota.total]).toEqual([1000, 130, 1130]);
		expect([nota.cash_received, nota.change_given]).toEqual([0, 0]);
		expect(nota.client_id).toBe(5);
		expect(nota.payment_method).toBe('Efectivo');
		expect(taxBreakdown(nota)).toEqual([{ rate: 0.13, base: 1000, tax: 130 }]);
		expect(fiscalBlock(nota)?.reference?.code).toBe('06');
	});

	it('una devolución vieja sin desglose deduce el impuesto del total', () => {
		const nota = creditNoteDocument({
			...devolucion,
			subtotal: null,
			tax: null,
			items: [{ id_product: 1, name: 'Arroz', quantity: 1, price: 1000, subtotal: 1000 }]
		})!;
		expect([nota.subtotal, nota.tax]).toEqual([1130, 0]);
		expect(nota.items[0].tax_rate).toBeNull();
	});

	it('lo que falte del original no rompe la nota', () => {
		const nota = creditNoteDocument({
			...devolucion,
			sale_created_at: null,
			reference_code: null,
			sale_client_id: undefined,
			sale_payment_method: null,
			user_name: undefined
		})!;
		expect(nota.reference?.date).toBe('');
		expect(nota.reference?.code).toBe('');
		expect(nota.client_id).toBeNull();
		expect(nota.payment_method).toBe('');
		expect(nota.user_name).toBeNull();
	});

	it('una devolución sin nota no tiene nada que imprimir', () => {
		expect(creditNoteDocument({ ...devolucion, document_type: null })).toBeNull();
		expect(creditNoteDocument({ ...devolucion, sale_document_type: undefined })).toBeNull();
	});
});

describe('fiscalBlock — lo que Hacienda pide imprimir (RN-86)', () => {
	it('sin tipo no hay bloque', () => {
		// Su leyenda es la del dueño (T-304); repetirla sería decirlo dos veces.
		expect(fiscalBlock({})).toBeNull();
		expect(fiscalBlock({ document_type: null, einvoice: emitido('production') })).toBeNull();
	});

	it('con tipo y sin clave, pendiente de emisión', () => {
		// Es todo lo que hay hasta T-705, y es la verdad (RN-17).
		expect(fiscalBlock({ document_type: '04' })).toEqual({
			kind: 'eticket',
			state: 'pending',
			emitted: null,
			reference: null
		});
		expect(fiscalBlock({ document_type: '01', einvoice: null })?.state).toBe('pending');
	});

	it('lo emitido en pruebas lo dice', () => {
		const bloque = fiscalBlock({ document_type: '01', einvoice: emitido('sandbox') });
		expect(bloque?.kind).toBe('einvoice');
		expect(bloque?.state).toBe('sandbox');
		expect(bloque?.emitted?.clave).toHaveLength(50);
	});

	it('y lo de producción va autorizado, con su clave y su consecutivo juntos', () => {
		const bloque = fiscalBlock({ document_type: '04', einvoice: emitido('production') });
		expect(bloque?.state).toBe('authorized');
		expect(bloque?.emitted?.consecutive).toHaveLength(20);
	});

	it('la resolución es un dato, no una frase', () => {
		expect(EINVOICE_RESOLUTION).toBe('MH-DGT-RES-0027-2024');
	});
});

describe('issuerLines', () => {
	it('sin datos del negocio no imprime líneas vacías', () => {
		expect(issuerLines(base)).toEqual([]);
	});

	/*
	 * El dominio devuelve QUÉ es cada línea, no cómo se dice: el rótulo
	 * («Cédula», «Tel.») lo pone la plantilla, que es la que sabe el idioma del
	 * documento (RN-30, y RN-29 para el idioma).
	 */
	it('dice qué es cada línea y en qué orden van', () => {
		const s = con({
			nombre: 'La Esquina',
			legalName: 'Inversiones La Esquina S.A.',
			taxId: '3-101-123456',
			address: 'San José, Costa Rica',
			phone: '2222-3333',
			email: 'ventas@laesquina.cr',
			website: 'laesquina.cr'
		});
		expect(issuerLines(s)).toEqual([
			{ kind: 'legalName', value: 'Inversiones La Esquina S.A.' },
			{ kind: 'taxId', value: '3-101-123456' },
			{ kind: 'address', value: 'San José, Costa Rica' },
			{ kind: 'phone', value: '2222-3333' },
			{ kind: 'email', value: 'ventas@laesquina.cr' },
			{ kind: 'website', value: 'laesquina.cr' }
		]);
	});

	it('no repite la razón social cuando es igual al nombre comercial', () => {
		const s = con({ nombre: 'La Esquina', legalName: 'La Esquina' });
		expect(issuerLines(s)).toEqual([]);
	});

	it('omite las líneas de los campos que están vacíos', () => {
		const s = con({ phone: '', taxId: '', address: 'Cartago' });
		expect(issuerLines(s)).toEqual([{ kind: 'address', value: 'Cartago' }]);
	});
});

describe('returnedTotal', () => {
	const dev = (total: number | string) => ({ total }) as unknown as SaleReturn;

	it('sin devoluciones da cero', () => {
		expect(returnedTotal([])).toBe(0);
	});

	it('suma las que haya', () => {
		expect(returnedTotal([dev(1638.5), dev(1000)])).toBe(2638.5);
	});

	it('acepta el total como texto, que es como lo manda el backend', () => {
		expect(returnedTotal([dev('1638.50')])).toBe(1638.5);
	});
});


describe('taxBreakdown — el desglose por tarifa del documento (RF-21)', () => {
	const linea = (id: number, subtotal: number, rate: number | null, tax: number) => ({
		id_product: id,
		name: `P${id}`,
		quantity: 1,
		price: subtotal,
		subtotal,
		tax_rate: rate,
		tax_amount: tax
	});

	it('una sola tarifa da una sola fila, como antes de F5', () => {
		const desglose = taxBreakdown({
			subtotal: 4350,
			tax: 565.5,
			items: [linea(1, 4350, 0.13, 565.5)]
		});
		expect(desglose).toEqual([{ rate: 0.13, base: 4350, tax: 565.5 }]);
	});

	it('separa las tarifas y de menor a mayor', () => {
		const desglose = taxBreakdown({
			subtotal: 2000,
			tax: 150,
			items: [linea(1, 1000, 0.13, 130), linea(2, 1000, 0.02, 20)]
		});
		expect(desglose).toEqual([
			{ rate: 0.02, base: 1000, tax: 20 },
			{ rate: 0.13, base: 1000, tax: 130 }
		]);
	});

	it('junta las líneas de la misma tarifa en una fila', () => {
		const desglose = taxBreakdown({
			subtotal: 3000,
			tax: 390,
			items: [linea(1, 1000, 0.13, 130), linea(2, 2000, 0.13, 260)]
		});
		expect(desglose).toEqual([{ rate: 0.13, base: 3000, tax: 390 }]);
	});

	it('el desglose suma el subtotal y el impuesto del encabezado', () => {
		const venta = {
			subtotal: 2000,
			tax: 150,
			items: [linea(1, 1000, 0.13, 130), linea(2, 1000, 0.02, 20)]
		};
		const desglose = taxBreakdown(venta);
		expect(desglose.reduce((a, f) => a + f.base, 0)).toBe(venta.subtotal);
		expect(desglose.reduce((a, f) => a + f.tax, 0)).toBe(venta.tax);
	});

	it('lee lo COBRADO, no lo recalcula', () => {
		// Una línea cuyo impuesto guardado no es el producto de su base por su
		// tarifa: pasa con las exoneraciones y con lo cobrado antes de un cambio
		// de redondeo. El documento tiene que decir lo que se cobró (RN-12).
		const desglose = taxBreakdown({
			subtotal: 1000,
			tax: 99,
			items: [linea(1, 1000, 0.13, 99)]
		});
		expect(desglose[0].tax).toBe(99);
	});

	describe('ventas anteriores a la migración 006', () => {
		it('sin tarifa en las líneas, deduce la del encabezado', () => {
			const desglose = taxBreakdown({
				subtotal: 4350,
				tax: 565.5,
				items: [{ id_product: 1, name: 'P1', quantity: 3, price: 1450, subtotal: 4350 }]
			});
			expect(desglose).toEqual([{ rate: 0.13, base: 4350, tax: 565.5 }]);
		});

		it('sin líneas tampoco se cae', () => {
			expect(taxBreakdown({ subtotal: 1000, tax: 130 })).toEqual([
				{ rate: 0.13, base: 1000, tax: 130 }
			]);
		});

		it('con subtotal en cero no divide entre cero', () => {
			expect(taxBreakdown({ subtotal: 0, tax: 0 })).toEqual([
				{ rate: 0, base: 0, tax: 0 }
			]);
		});

		it('con tarifa pero sin monto, la fila cuenta con cero', () => {
			// La 006 agregó las dos columnas a la vez, así que la mezcla no debería
			// darse; pero el desglose es lo que imprime la factura y no puede
			// devolver `NaN` si se diera. Cero es lo honesto: no se cobró nada que
			// conste.
			const desglose = taxBreakdown({
				subtotal: 1000,
				tax: 0,
				items: [{ id_product: 1, name: 'P1', quantity: 1, price: 1000, subtotal: 1000, tax_rate: 0 }]
			});
			expect(desglose).toEqual([{ rate: 0, base: 1000, tax: 0 }]);
		});
	});
});

describe('lo que el comprobante imprime además (RN-86, T-731)', () => {
	const conFacturacion = mergeSettings({
		business: { name: 'SWS', taxId: '3101702934', taxIdType: '02' },
		eInvoicing: { enabled: true, economicActivity: '4741.0' }
	});

	it('en un comprobante la cédula lleva su tipo y se agrega la actividad', () => {
		expect(issuerLines(conFacturacion, { activity: '4741.0' })).toEqual([
			{ kind: 'taxId', value: '3101702934', idType: '02' },
			{ kind: 'activity', value: '4741.0' }
		]);
	});

	it('en el documento de siempre no, porque sirve en cualquier país', () => {
		expect(issuerLines(conFacturacion)).toEqual([{ kind: 'taxId', value: '3101702934' }]);
		expect(issuerLines(conFacturacion, { activity: null })).toEqual([
			{ kind: 'taxId', value: '3101702934', idType: '02' }
		]);
	});

	it('la actividad es la del emitido, si no la configurada, y nada sin comprobante', () => {
		expect(issuerActivity({ document_type: '01', einvoice: emitido('production') }, conFacturacion)).toBe(
			'523101'
		);
		expect(issuerActivity({ document_type: '04' }, conFacturacion)).toBe('4741.0');
		expect(issuerActivity({ document_type: '04' }, base)).toBeNull();
		expect(issuerActivity({ document_type: null }, conFacturacion)).toBeNull();
	});

	it('la cabecera lleva un solo número: el consecutivo cuando lo hay', () => {
		expect(documentNumber({ sale_number: '2026', einvoice: emitido('sandbox') })).toBe(
			'00100001040000000123'
		);
		expect(documentNumber({ sale_number: '2026' })).toBe('2026');
	});

	it('se vende de contado y en colones el tipo de cambio es uno', () => {
		expect(SALE_CONDITION_CASH).toBe('01');
		expect(exchangeRate('CRC')).toBe(1);
		// El del BCCR del día no existe en el sistema: mejor nada que uno inventado.
		expect(exchangeRate('USD')).toBeNull();
	});

	describe('documentLines', () => {
		it('numera, congela el CABYS y la unidad, y suma el impuesto a la línea', () => {
			const lineas = documentLines({
				subtotal: 5640,
				tax: 223.2,
				items: [
					{ id_product: 9, name: 'Jugo', quantity: 1, price: 1390, subtotal: 1390, tax_rate: 0.13, tax_amount: 180.7, cabys_code: '2449002000100', unit_of_measure: 'Unid' },
					{ id_product: 4, name: 'Café', quantity: 1, price: 4250, subtotal: 4250, tax_rate: 0.01, tax_amount: 42.5 }
				]
			});
			expect(lineas).toEqual([
				{ number: 1, id_product: 9, cabys: '2449002000100', name: 'Jugo', quantity: 1, unit: 'Unid', unitPrice: 1390, rate: 0.13, subtotal: 1390, tax: 180.7, total: 1570.7 },
				{ number: 2, id_product: 4, cabys: null, name: 'Café', quantity: 1, unit: null, unitPrice: 4250, rate: 0.01, subtotal: 4250, tax: 42.5, total: 4292.5 }
			]);
		});

		it('una venta anterior a la 006 saca el impuesto de la tarifa del encabezado', () => {
			const [linea] = documentLines({
				subtotal: 1000,
				tax: 130,
				items: [{ id_product: 1, name: 'Arroz', quantity: 2, price: 500, subtotal: 1000 }]
			});
			expect([linea.rate, linea.tax, linea.total]).toEqual([0.13, 130, 1130]);
		});

		it('sin líneas no hay nada, y una venta en cero no divide entre cero', () => {
			expect(documentLines({ subtotal: 0, tax: 0 })).toEqual([]);
			const [linea] = documentLines({
				subtotal: 0,
				tax: 0,
				items: [{ id_product: 1, name: 'Regalo', quantity: 1, price: 0, subtotal: 0 }]
			});
			expect(linea.tax).toBe(0);
		});
	});

	it('el resumen lleva los renglones de Hacienda, con los descuentos en cero', () => {
		const resumen = documentSummary({
			subtotal: 5640,
			tax: 223.2,
			total: 5863.2,
			items: [
				{ id_product: 9, name: 'Jugo', quantity: 1, price: 1390, subtotal: 1390, tax_rate: 0.13, tax_amount: 180.7 },
				{ id_product: 4, name: 'Café', quantity: 1, price: 4250, subtotal: 4250, tax_rate: 0.01, tax_amount: 42.5 }
			]
		});
		expect(resumen).toEqual({
			gross: 5640,
			discounts: 0,
			net: 5640,
			taxes: [
				{ rate: 0.01, base: 4250, tax: 42.5 },
				{ rate: 0.13, base: 1390, tax: 180.7 }
			],
			tax: 223.2,
			total: 5863.2
		});
	});

	it('la nota de crédito repite el CABYS y la unidad de la venta', () => {
		const nota = creditNoteDocument({
			id: 3,
			sale_id: 1,
			sale_number: '1',
			user_id: 1,
			created_at: '2026-09-26T11:00:00',
			reason: 'x',
			total: 1130,
			is_full: true,
			items: [{ id_product: 1, name: 'Arroz', quantity: 1, price: 1000, subtotal: 1000, cabys_code: '2316100000100', unit_of_measure: 'kg' }],
			document_type: '03',
			sale_document_type: '01'
		})!;
		expect(nota.items[0].cabys_code).toBe('2316100000100');
		expect(nota.items[0].unit_of_measure).toBe('kg');
	});
});

describe('amountNoteDocument — la nota por monto con la forma de las plantillas (T-726)', () => {
	const nd: AmountNote = {
		id: 3,
		sale_id: 7,
		sale_number: '20260926103036',
		user_id: 1,
		user_name: 'Dueña',
		created_at: '2026-09-26T15:00:00',
		document_type: '02',
		reference_code: CORRECTS_AMOUNT,
		reason: 'se cobró mal el precio',
		payment_method: 'Tarjeta de crédito',
		subtotal: 1000,
		tax: 130,
		total: 1130,
		items: [
			{ id_product: 1, name: 'Arroz', subtotal: 1000, tax_rate: 0.13, tax_amount: 130, cabys_code: '2316100000100', unit_of_measure: 'kg' }
		],
		sale_document_type: '01',
		sale_created_at: '2026-09-26T10:30:36',
		sale_client_id: 5
	};

	it('es una nota de débito con la referencia al original y nada de efectivo', () => {
		const doc = amountNoteDocument(nd);
		expect(documentKind(doc)).toBe('edebit');
		expect(doc.reference).toEqual({
			document_type: '01',
			number: '20260926103036',
			date: '2026-09-26T10:30:36',
			code: '02'
		});
		expect([doc.sale_number, doc.payment_method, doc.cash_received]).toEqual(['3', 'Tarjeta de crédito', 0]);
		expect(doc.client_id).toBe(5);
	});

	it('cada línea es una corrección: cantidad uno y el monto como precio', () => {
		const [linea] = documentLines(amountNoteDocument(nd));
		expect([linea.quantity, linea.unitPrice, linea.tax, linea.total]).toEqual([1, 1000, 130, 1130]);
		expect([linea.cabys, linea.unit]).toEqual(['2316100000100', 'kg']);
	});

	it('la NC sale de la gaveta: su medio es el efectivo', () => {
		const doc = amountNoteDocument({ ...nd, document_type: '03', payment_method: null });
		expect(documentKind(doc)).toBe('ecredit');
		expect(doc.payment_method).toBe('Efectivo');
	});

	it('lo que falte del original no rompe la nota', () => {
		const doc = amountNoteDocument({
			...nd,
			sale_document_type: undefined,
			sale_created_at: null,
			sale_client_id: undefined,
			user_name: undefined,
			items: [{ id_product: 1, name: 'Arroz', subtotal: 100, tax_rate: 0, tax_amount: 0 }]
		});
		expect(doc.reference).toMatchObject({ document_type: '', date: '' });
		expect([doc.client_id, doc.user_name]).toEqual([null, null]);
		expect(doc.items[0].cabys_code).toBeNull();
	});
});


describe('claveGroups — la clave en tramos, como la factura de referencia (T-705)', () => {
	it('parte los 50 dígitos donde la nota 3 los arma', () => {
		expect(claveGroups('50624092600310170293400100001010001819201163700346')).toEqual([
			'506',
			'240926',
			'003101702934',
			'001',
			'00001',
			'01',
			'0001819201',
			'163700346'
		]);
	});

	it('una que no son 50 dígitos vuelve entera: no se inventan cortes', () => {
		expect(claveGroups('506240926')).toEqual(['506240926']);
		expect(claveGroups('5062409260031017029340010000101000181920116370034X')).toHaveLength(1);
	});
});

describe('la dirección del emisor en un comprobante (T-722)', () => {
	const conUbicacion = con({
		address: 'San José, 200 m sur del parque',
		location: {
			province: '1',
			canton: '01',
			district: '05',
			neighborhood: 'Barrio La Cruz',
			otherSigns: '600 m oeste de Plaza Cristal'
		}
	});

	it('lleva provincia, cantón y distrito con su nombre, y las otras señas', () => {
		const lineas = issuerLines(conUbicacion, { activity: null });
		expect(lineas).toEqual([
			{
				kind: 'location',
				value: 'San José / San José / Zapote',
				place: { province: 'San José', canton: 'San José', district: 'Zapote' }
			},
			{ kind: 'address', value: 'Barrio La Cruz, 600 m oeste de Plaza Cristal' }
		]);
	});

	it('el tiquete de siempre sigue con la dirección de texto libre', () => {
		expect(issuerLines(conUbicacion)).toEqual([
			{ kind: 'address', value: 'San José, 200 m sur del parque' }
		]);
	});

	it('sin ubicación completa, el comprobante imprime la de texto libre', () => {
		const aMedias = con({ address: 'Cartago', location: { province: '3' } });
		expect(issuerLines(aMedias, { activity: null })).toEqual([{ kind: 'address', value: 'Cartago' }]);
	});
});

describe('las notas numeradas referencian la clave del original (T-705)', () => {
	const emitida = emitido('sandbox');

	it('la NC de una devolución', () => {
		const nota = creditNoteDocument({
			id: 12,
			sale_id: 7,
			sale_number: '2026',
			user_id: 2,
			created_at: '2026-09-27T11:00:00',
			reason: 'no le quedó',
			total: 1130,
			is_full: false,
			items: [],
			document_type: '03',
			reference_code: '06',
			sale_document_type: '04',
			einvoice: emitida,
			sale_clave: '50627092600310123456700100001040000000001100000009'
		})!;
		expect(nota.einvoice).toEqual(emitida);
		expect(nota.reference?.number).toBe('50627092600310123456700100001040000000001100000009');
		expect(documentNumber(nota)).toBe(emitida.consecutive);
	});

	it('la nota por monto', () => {
		const doc = amountNoteDocument({
			id: 3,
			sale_id: 7,
			sale_number: '2026',
			user_id: 1,
			created_at: '2026-09-27T15:00:00',
			document_type: '02',
			reference_code: CORRECTS_AMOUNT,
			reason: 'precio',
			payment_method: 'Efectivo',
			subtotal: 0,
			tax: 0,
			total: 0,
			items: [],
			einvoice: emitida,
			sale_clave: '50627092600310123456700100001010000000001100000009'
		});
		expect(doc.einvoice).toEqual(emitida);
		expect(doc.reference?.number).toBe('50627092600310123456700100001010000000001100000009');
	});
});
