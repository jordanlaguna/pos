import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { DEFAULT_SETTINGS, type Settings } from '$lib/domain/settings';
import { issuerLines } from '$lib/domain/documents';
import { documentLabels, issuerText } from './documents';

const PLANTILLAS = join(dirname(fileURLToPath(import.meta.url)), 'components', 'documents');

/**
 * Los rótulos del documento impreso.
 *
 * El dominio dice QUÉ es cada línea y acá se convierte en texto. Es la mitad que
 * no se puede comprobar contra el sistema corriendo: la compañía de prueba no
 * tiene cédula ni teléfono configurados, así que en pantalla esas líneas ni
 * aparecen. Sin estas pruebas, un rótulo roto no lo caza nadie.
 *
 * Desde T-811 se prueba además **en dos idiomas**, porque el documento se emite
 * en el de la compañía y no en el de la pantalla (RN-29): que el diccionario
 * reciba el idioma es lo único que separa una factura correcta de una factura en
 * el idioma del cajero.
 */

const es = documentLabels('es');
const en = documentLabels('en');

function con(business: Partial<Settings['business']>): Settings {
	return {
		...DEFAULT_SETTINGS,
		business: { ...DEFAULT_SETTINGS.business, ...business }
	};
}

describe('el título del documento', () => {
	it('es «Factura» cuando la venta no es un comprobante electrónico', () => {
		expect(es.title('invoice')).toBe('Factura');
		expect(en.title('invoice')).toBe('Invoice');
	});

	it('y el nombre del comprobante cuando lo es (RN-85)', () => {
		expect(es.title('einvoice')).toBe('Factura electrónica');
		expect(en.title('einvoice')).toBe('Electronic invoice');
		expect(es.title('eticket')).toBe('Tiquete electrónico');
		expect(en.title('eticket')).toBe('Electronic receipt');
	});
});

describe('el bloque fiscal (RN-86)', () => {
	it('rotula la clave y el consecutivo', () => {
		expect(es.fiscalKey).toBe('Clave');
		expect(es.fiscalConsecutive).toBe('Consecutivo');
		expect(es.fiscalActivity('523101')).toBe('Actividad económica 523101');
	});

	it('las notas y su referencia al original (RN-89)', () => {
		expect(es.title('ecredit')).toBe('Nota de crédito electrónica');
		expect(es.title('edebit')).toBe('Nota de débito electrónica');
		expect(es.fiscalReference).toBe('Referencia');
		expect(es.referenceTo('eticket', '2026', '26/09/2026')).toBe(
			'Tiquete electrónico 2026 del 26/09/2026'
		);
		expect(es.referenceReason('01')).toMatch(/anula/i);
		expect(es.referenceReason('06')).toMatch(/devolución de mercancía/i);
		expect(es.referenceReason('02')).toMatch(/corrige monto/i);
		expect(es.referenceReason('99')).toMatch(/99/);
	});

	it('las tres leyendas dicen en qué punto está', () => {
		expect(es.fiscalPending).toMatch(/pendiente de emisión/i);
		expect(es.fiscalSandbox).toMatch(/pruebas/i);
		expect(es.fiscalSandbox).toMatch(/efecto fiscal/i);
		expect(es.fiscalResolution('MH-DGT-RES-0027-2024')).toMatch(/MH-DGT-RES-0027-2024/);
	});
});

describe('todas las plantillas imprimen el bloque fiscal (RN-86)', () => {
	/*
	 * La lista no está escrita acá: sale de `DocumentSheet.svelte`, que es el único
	 * lugar donde se decide qué plantilla se imprime. Una cuarta plantilla que se
	 * agregue ahí entra sola en esta prueba, y si no trae el bloque, falla — antes
	 * de que un cliente reciba una factura sin clave porque el dueño eligió la
	 * plantilla que se veía mejor.
	 */
	const hoja = readFileSync(join(PLANTILLAS, 'DocumentSheet.svelte'), 'utf-8');
	const ofrecidas = [...hoja.matchAll(/import\s+\w+\s+from\s+'\.\/(\w+\.svelte)'/g)].map(
		(m) => m[1]
	);

	it('DocumentSheet ofrece las tres de siempre', () => {
		expect([...ofrecidas].sort()).toEqual([
			'FacturaClasica.svelte',
			'FacturaModerna.svelte',
			'Tiquete.svelte'
		]);
	});

	it.each(ofrecidas)('%s usa FiscalBlock', (nombre) => {
		const fuente = readFileSync(join(PLANTILLAS, nombre), 'utf-8');
		expect(fuente, `${nombre} no importa el bloque fiscal`).toMatch(
			/import\s+FiscalBlock\s+from\s+'\.\/FiscalBlock\.svelte'/
		);
		expect(fuente, `${nombre} importa el bloque fiscal y no lo pinta`).toMatch(/<FiscalBlock\b/);
		// Y al pie: la resolución y dónde se verifica van abajo, como en la factura
		// de referencia (T-731). Una plantilla que solo lo pinta arriba entrega un
		// comprobante autorizado sin decir por qué lo está.
		expect(fuente, `${nombre} no pinta el pie del bloque fiscal`).toMatch(
			/<FiscalBlock\b[^>]*part="foot"/
		);
	});

	it('las tres imprimen lo mismo de Hacienda (T-731)', () => {
		/*
		 * Lo que la factura de referencia lleva y el POS sabe: la condición de
		 * venta, la moneda, el CABYS y la unidad por línea, el resumen de Hacienda y
		 * el monto en letras. Se busca el marcador de cada pieza en las tres, porque
		 * la primera que se olvide es la que el dueño eligió por cómo se ve.
		 */
		for (const nombre of ofrecidas) {
			const fuente = readFileSync(join(PLANTILLAS, nombre), 'utf-8');
			for (const pieza of [
				'data-condicion',
				'data-moneda',
				'data-cabys',
				'data-resumen',
				'data-en-letras',
				't.totalDocument'
			]) {
				expect(fuente, `${nombre} no imprime ${pieza}`).toContain(pieza);
			}
			// La identificación del receptor con su tipo, como frase o como rótulo.
			expect(fuente, `${nombre} no nombra el tipo de identificación`).toMatch(
				/t\.id(Typed|Label)\(/
			);
		}
	});
});

describe('las líneas del emisor', () => {
	it('la cédula y el teléfono van rotulados', () => {
		// Un número suelto en la cabecera de una factura no dice qué número es.
		expect(es.issuerLine({ kind: 'taxId', value: '3-101-123456' })).toBe('Cédula 3-101-123456');
		expect(es.issuerLine({ kind: 'phone', value: '2222-3333' })).toBe('Tel. 2222-3333');
		expect(en.issuerLine({ kind: 'taxId', value: '3-101-123456' })).toBe('ID 3-101-123456');
	});

	it('la dirección, el correo y el sitio se reconocen solos', () => {
		// No llevan rótulo, así que el idioma no los toca.
		for (const labels of [es, en]) {
			expect(labels.issuerLine({ kind: 'address', value: 'Cartago' })).toBe('Cartago');
			expect(labels.issuerLine({ kind: 'email', value: 'a@b.cr' })).toBe('a@b.cr');
			expect(labels.issuerLine({ kind: 'website', value: 'b.cr' })).toBe('b.cr');
			expect(labels.issuerLine({ kind: 'legalName', value: 'Inversiones S.A.' })).toBe(
				'Inversiones S.A.'
			);
		}
	});

	it('arma la cabecera completa en el orden del dominio', () => {
		const s = con({
			name: 'La Esquina',
			legalName: 'Inversiones La Esquina S.A.',
			taxId: '3-101-123456',
			address: 'San José',
			phone: '2222-3333',
			email: 'ventas@laesquina.cr',
			website: 'laesquina.cr'
		});
		expect(issuerText(issuerLines(s), es)).toEqual([
			'Inversiones La Esquina S.A.',
			'Cédula 3-101-123456',
			'San José',
			'Tel. 2222-3333',
			'ventas@laesquina.cr',
			'laesquina.cr'
		]);
	});

	it('sin datos del negocio no imprime ninguna línea', () => {
		expect(issuerText(issuerLines(DEFAULT_SETTINGS), es)).toEqual([]);
	});

	it('en un comprobante la cédula lleva su tipo y la actividad su rótulo (RN-86)', () => {
		const s = con({ taxId: '3101702934', taxIdType: '02' });
		expect(issuerText(issuerLines(s, { activity: '4741.0' }), es)).toEqual([
			'Cédula jurídica 3101702934',
			'Actividad económica 4741.0'
		]);
		// Un tipo que no es de Hacienda no inventa un rótulo.
		expect(es.issuerLine({ kind: 'taxId', value: '1', idType: '99' })).toBe('Cédula 1');
	});
});

describe('lo que el comprobante imprime además (T-731)', () => {
	it('la identificación del receptor con su tipo, o la genérica', () => {
		expect(es.idTyped('01', '108840287')).toBe('Cédula física 108840287');
		expect(en.idTyped('02', '3101702934')).toBe('Cédula jurídica 3101702934');
		expect(es.idTyped(null, '108840287')).toBe('Cédula 108840287');
		expect(es.idLabel('03')).toBe('DIMEX');
		expect(es.idLabel(undefined)).toBe('Cédula');
	});

	it('la condición de venta y la moneda', () => {
		expect(es.saleCondition).toBe('Condición de venta');
		expect(es.saleConditionName('01')).toBe('Contado');
		expect(en.saleConditionName('01')).toBe('Cash');
		expect(es.saleConditionName('02')).toBe('02');
		expect(es.currencyWithRate('CRC', 1)).toBe('CRC (TC 1.00)');
		expect(es.currencyWithRate('USD', null)).toBe('USD');
	});

	it('las columnas y los renglones del resumen', () => {
		expect([es.colCabys, es.colUnit, es.colSubtotal, es.colTax]).toEqual([
			'CABYS',
			'Unid.',
			'Subtotal',
			'Impuesto'
		]);
		expect([es.totalSale, es.totalDiscounts, es.totalNet, es.totalTax, es.totalDocument]).toEqual(
			['Total venta', 'Total descuentos', 'Total venta neta', 'Total impuesto', 'Total comprobante']
		);
		expect(es.lineCabys('2449002000100')).toBe('CABYS 2449002000100');
		expect(es.lineQuantity(2, 'Unid', '₡1.390,00')).toBe('2 Unid × ₡1.390,00');
		// Sin unidad —una venta anterior a la 016— no queda un espacio doble.
		expect(es.lineQuantity(2, '', '₡1.390,00')).toBe('2 × ₡1.390,00');
	});

	it('el monto en letras sale en el idioma del documento', () => {
		expect(es.amountInWordsLabel).toBe('Monto en letras');
		expect(es.amountInWords(1130, 'CRC', 2)).toBe('MIL CIENTO TREINTA CON 00/100 COLONES');
		expect(en.amountInWords(1130, 'CRC', 2)).toBe(
			'ONE THOUSAND ONE HUNDRED THIRTY AND 00/100 COLONES'
		);
	});

	it('dónde se verifica un comprobante autorizado', () => {
		expect(es.fiscalVerify('https://x')).toMatch(/portal de comprobantes de Hacienda \(https:\/\/x\)/);
		expect(es.issueDate).toBe('Fecha de emisión');
		expect(es.email).toBe('Correo');
	});
});

describe('el método de pago del documento', () => {
	it('se traduce como se muestra, sin tocar el valor guardado', () => {
		expect(es.paymentName('Efectivo')).toBe('Efectivo');
		expect(en.paymentName('Efectivo')).toBe('Cash');
		expect(en.paymentName('Tarjeta de crédito')).toBe('Credit card');
	});

	it('un método sin rótulo se muestra tal cual', () => {
		// Mejor el valor de la base que un hueco en blanco en la factura.
		expect(en.paymentName('Criptomoneda')).toBe('Criptomoneda');
	});
});

describe('el idioma del documento es independiente del de la pantalla', () => {
	it('el mismo rótulo sale distinto según el idioma que se pida', () => {
		expect(es.total).toBe('Total');
		expect(es.cashReceived).toBe('Efectivo recibido');
		expect(en.cashReceived).toBe('Cash received');
		expect(es.colQuantity).toBe('Cant.');
		expect(en.colQuantity).toBe('Qty');
	});

	it('los que llevan datos también', () => {
		expect(es.numbered('invoice', '000123')).toBe('Factura 000123');
		expect(en.numbered('invoice', '000123')).toBe('Invoice 000123');
		expect(es.numbered('eticket', '000123')).toBe('Tiquete electrónico 000123');
	});
});
