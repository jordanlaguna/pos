import { describe, expect, it } from 'vitest';
import { DEFAULT_SETTINGS, type Settings } from '$lib/domain/settings';
import { issuerLines } from '$lib/domain/documents';
import { documentLabels, issuerText } from './documents';

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
	it('es «Factura» mientras no se emita electrónicamente', () => {
		expect(es.title(DEFAULT_SETTINGS)).toBe('Factura');
		expect(en.title(DEFAULT_SETTINGS)).toBe('Invoice');
	});

	it('y «Factura electrónica» cuando se activa', () => {
		const s: Settings = {
			...DEFAULT_SETTINGS,
			eInvoicing: { ...DEFAULT_SETTINGS.eInvoicing, enabled: true }
		};
		expect(es.title(s)).toBe('Factura electrónica');
		expect(en.title(s)).toBe('Electronic invoice');
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
		expect(es.invoiceNumber('000123')).toBe('Factura 000123');
		expect(en.invoiceNumber('000123')).toBe('Invoice 000123');
	});
});
