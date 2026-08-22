import { describe, expect, it } from 'vitest';
import { relativeLuminance } from './color';
import { brandTones, documentKind, issuerLines, returnedTotal } from './documents';
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
