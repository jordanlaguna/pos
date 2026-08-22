import { describe, expect, it } from 'vitest';
import { DEFAULT_SETTINGS, type Settings } from '$lib/domain/settings';
import { issuerLines } from '$lib/domain/documents';
import { documentTitle, issuerLine, issuerText } from './documents';

/**
 * Los rótulos del documento impreso.
 *
 * El dominio dice QUÉ es cada línea y acá se convierte en texto. Es la mitad que
 * no se puede comprobar contra el sistema corriendo: la compañía de prueba no
 * tiene cédula ni teléfono configurados, así que en pantalla esas líneas ni
 * aparecen. Sin estas pruebas, un rótulo roto no lo caza nadie.
 */

function con(business: Partial<Settings['business']>): Settings {
	return {
		...DEFAULT_SETTINGS,
		business: { ...DEFAULT_SETTINGS.business, ...business }
	};
}

describe('documentTitle', () => {
	it('es «Factura» mientras no se emita electrónicamente', () => {
		expect(documentTitle(DEFAULT_SETTINGS)).toBe('Factura');
	});

	it('y «Factura electrónica» cuando se activa', () => {
		const s: Settings = {
			...DEFAULT_SETTINGS,
			eInvoicing: { ...DEFAULT_SETTINGS.eInvoicing, enabled: true }
		};
		expect(documentTitle(s)).toBe('Factura electrónica');
	});
});

describe('issuerLine', () => {
	it('la cédula y el teléfono van rotulados', () => {
		// Un número suelto en la cabecera de una factura no dice qué número es.
		expect(issuerLine({ kind: 'taxId', value: '3-101-123456' })).toBe('Cédula 3-101-123456');
		expect(issuerLine({ kind: 'phone', value: '2222-3333' })).toBe('Tel. 2222-3333');
	});

	it('la dirección, el correo y el sitio se reconocen solos', () => {
		expect(issuerLine({ kind: 'address', value: 'Cartago' })).toBe('Cartago');
		expect(issuerLine({ kind: 'email', value: 'a@b.cr' })).toBe('a@b.cr');
		expect(issuerLine({ kind: 'website', value: 'b.cr' })).toBe('b.cr');
		expect(issuerLine({ kind: 'legalName', value: 'Inversiones S.A.' })).toBe('Inversiones S.A.');
	});
});

describe('issuerText', () => {
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
		expect(issuerText(issuerLines(s))).toEqual([
			'Inversiones La Esquina S.A.',
			'Cédula 3-101-123456',
			'San José',
			'Tel. 2222-3333',
			'ventas@laesquina.cr',
			'laesquina.cr'
		]);
	});

	it('sin datos del negocio no imprime ninguna línea', () => {
		expect(issuerText(issuerLines(DEFAULT_SETTINGS))).toEqual([]);
	});
});
