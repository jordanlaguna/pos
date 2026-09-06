import { describe, expect, it } from 'vitest';
import { relativeLuminance } from './color';
import {
	brandTones,
	documentKind,
	issuerLines,
	returnedTotal,
	taxBreakdown
} from './documents';
import { mergeSettings } from './settings';
import type { SaleReturn } from './types';

const base = mergeSettings({});

/** Configuración con el negocio y la sección electrónica que pida la prueba. */
function con(business: Record<string, unknown> = {}, eInvoicing: Record<string, unknown> = {}) {
	return mergeSettings({ business, eInvoicing });
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

describe('documentKind', () => {
	it('dice «Factura» mientras no se emita electrónica', () => {
		expect(documentKind(base)).toBe('invoice');
	});

	it('y «Factura electrónica» cuando está activa', () => {
		expect(documentKind(con({}, { enabled: true }))).toBe('einvoice');
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
