import { describe, expect, it } from 'vitest';
import {
	ALL_TYPES,
	ALWAYS_ON,
	AVAILABLE,
	COUNTER_TYPES,
	CREDIT_NOTE,
	DEBIT_NOTE,
	DEFAULT_ENABLED,
	EXPORT_INVOICE,
	INVOICE,
	PAYMENT_RECEIPT,
	PURCHASE_INVOICE,
	TICKET,
	canToggle,
	documentTypeFor,
	effectiveDocumentType,
	enabledTypes,
	isCounterDocumentType,
	suggestedDocumentType
} from './documentType';

/**
 * Los comprobantes en el POS (RN-85, RN-88).
 *
 * Tienen que decir lo mismo que `tests/domain/test_fe_document_type.py` del
 * backend: la pantalla propone y el servidor aplica, y si no coinciden el cajero
 * ve una cosa y cobra otra.
 */

const SOLO_FACTURA = [INVOICE, CREDIT_NOTE];
const SOLO_TIQUETE = [TICKET, CREDIT_NOTE];

describe('los siete', () => {
	it('son los del anexo, en el orden de Configuración', () => {
		expect(ALL_TYPES).toEqual(['04', '01', '09', '03', '02', '08', '10']);
		expect([EXPORT_INVOICE, DEBIT_NOTE, PURCHASE_INVOICE, PAYMENT_RECEIPT]).toEqual([
			'09',
			'02',
			'08',
			'10'
		]);
	});

	it('de una venta salen la factura y el tiquete', () => {
		expect(COUNTER_TYPES).toEqual([INVOICE, TICKET]);
		expect(isCounterDocumentType('01')).toBe(true);
		expect(isCounterDocumentType('04')).toBe(true);
		for (const malo of ['03', '1', '', null, undefined, 1]) {
			expect(isCounterDocumentType(malo)).toBe(false);
		}
	});

	it('hoy tienen flujo los de venta y la nota de crédito, que no se apaga', () => {
		expect(AVAILABLE).toEqual([TICKET, INVOICE, CREDIT_NOTE]);
		expect(ALWAYS_ON).toEqual([CREDIT_NOTE]);
		expect(DEFAULT_ENABLED).toEqual([TICKET, INVOICE, CREDIT_NOTE, DEBIT_NOTE]);
	});
});

describe('lo que emite la compañía (RN-88)', () => {
	it('sin lista es la de fábrica', () => {
		for (const guardado of [undefined, null, '01,04', { '01': true }, 7]) {
			expect(enabledTypes(guardado)).toEqual(DEFAULT_ENABLED);
		}
	});

	it('respeta lo elegido, en orden, y agrega la NC si falta', () => {
		expect(enabledTypes(['03', '01'])).toEqual([INVOICE, CREDIT_NOTE]);
		expect(enabledTypes(['04'])).toEqual([TICKET, CREDIT_NOTE]);
	});

	it('tira lo que no es de Hacienda', () => {
		expect(enabledTypes(['04', 'FE', '99', 4])).toEqual([TICKET, CREDIT_NOTE]);
	});

	it('sin tiquete ni factura vuelve a la de fábrica', () => {
		for (const guardado of [[], ['03'], ['02', '09'], ['FE']]) {
			expect(enabledTypes(guardado)).toEqual(DEFAULT_ENABLED);
		}
	});

	it('guarda lo que todavía no tiene flujo', () => {
		expect(enabledTypes(['04', '02'])).toContain(DEBIT_NOTE);
	});
});

describe('qué casilla se mueve', () => {
	it('los de venta y lo que tiene flujo, sí', () => {
		expect(canToggle(TICKET, DEFAULT_ENABLED)).toBe(true);
		expect(canToggle(INVOICE, DEFAULT_ENABLED)).toBe(true);
	});

	it('la NC no, porque no se apaga', () => {
		expect(canToggle(CREDIT_NOTE, DEFAULT_ENABLED)).toBe(false);
	});

	it('lo que todavía no tiene flujo tampoco', () => {
		for (const codigo of [DEBIT_NOTE, EXPORT_INVOICE, PURCHASE_INVOICE, PAYMENT_RECEIPT]) {
			expect(canToggle(codigo, DEFAULT_ENABLED)).toBe(false);
		}
	});

	it('el último de venta encendido no se apaga', () => {
		expect(canToggle(INVOICE, SOLO_FACTURA)).toBe(false);
		expect(canToggle(TICKET, SOLO_TIQUETE)).toBe(false);
		// Pero el otro sí se puede volver a encender.
		expect(canToggle(TICKET, SOLO_FACTURA)).toBe(true);
	});
});

describe('la sugerencia', () => {
	it('sin cliente tiquete, con cliente factura', () => {
		expect(suggestedDocumentType(false)).toBe(TICKET);
		expect(suggestedDocumentType(true)).toBe(INVOICE);
	});

	it('con la factura apagada, tiquete aunque haya cliente', () => {
		expect(suggestedDocumentType(true, SOLO_TIQUETE)).toBe(TICKET);
	});

	it('con el tiquete apagado, factura aunque no haya cliente', () => {
		expect(suggestedDocumentType(false, SOLO_FACTURA)).toBe(INVOICE);
	});
});

describe('lo que se va a emitir', () => {
	it('sin elección, la sugerencia', () => {
		expect(effectiveDocumentType(null, false)).toBe(TICKET);
		expect(effectiveDocumentType(undefined, true)).toBe(INVOICE);
	});

	it('el cajero puede dejar en tiquete a un cliente', () => {
		expect(effectiveDocumentType(TICKET, true)).toBe(TICKET);
	});

	it('sin cliente sale tiquete aunque se haya elegido factura', () => {
		// Quien elige factura y después quita el cliente.
		expect(effectiveDocumentType(INVOICE, false)).toBe(TICKET);
	});

	it('un tipo apagado no se emite aunque se haya elegido', () => {
		expect(effectiveDocumentType(TICKET, true, SOLO_FACTURA)).toBe(INVOICE);
	});

	it('solo factura y sin cliente: así no se puede cobrar', () => {
		expect(effectiveDocumentType(null, false, SOLO_FACTURA)).toBeNull();
	});
});

describe('la regla de la venta, como la aplica el servidor', () => {
	const activa = { einvoicing: true, enabled: DEFAULT_ENABLED, hasReceiver: false };

	it('un tipo que el mostrador no emite se rechaza siempre', () => {
		for (const einvoicing of [true, false]) {
			expect(documentTypeFor('03', { ...activa, einvoicing })).toEqual({
				ok: false,
				code: 'invalid_sale_document_type'
			});
		}
	});

	it('con la facturación apagada no lleva tipo', () => {
		expect(documentTypeFor('01', { ...activa, einvoicing: false })).toEqual({ ok: true, type: null });
	});

	it('sin pedir nada sale la sugerencia', () => {
		expect(documentTypeFor(null, activa)).toEqual({ ok: true, type: TICKET });
		expect(documentTypeFor(null, { ...activa, hasReceiver: true })).toEqual({
			ok: true,
			type: INVOICE
		});
	});

	it('lo pedido, si está encendido', () => {
		expect(documentTypeFor(TICKET, { ...activa, hasReceiver: true })).toEqual({
			ok: true,
			type: TICKET
		});
	});

	it('un tipo apagado no', () => {
		expect(documentTypeFor(TICKET, { ...activa, enabled: SOLO_FACTURA })).toEqual({
			ok: false,
			code: 'document_type_not_enabled'
		});
	});

	it('factura sin cliente no, pedida o sugerida', () => {
		expect(documentTypeFor(INVOICE, activa)).toEqual({ ok: false, code: 'invoice_needs_receiver' });
		expect(documentTypeFor(null, { ...activa, enabled: SOLO_FACTURA })).toEqual({
			ok: false,
			code: 'invoice_needs_receiver'
		});
	});
});
