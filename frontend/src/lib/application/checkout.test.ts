import { describe, expect, it } from 'vitest';
import { CASH_METHOD, prepareSale, type CheckoutRequest } from './checkout';
import type { Product } from '$lib/domain/types';

/**
 * Cobrar, sin servidor de por medio.
 *
 * Antes esto vivía dentro de la acción de `/ventas` y solo se podía probar
 * levantando SvelteKit y el backend. Ahora es una función: mismas entradas,
 * misma salida.
 */

const AHORA = new Date(2026, 7, 16, 21, 43, 5);
const IVA = 0.13;

function producto(id: number, name: string, price: number, stock: number): Product {
	return {
		id_product: id,
		name,
		description: '',
		price,
		stock,
		barcode: `B${id}`,
		created_at: '2026-01-01T00:00:00',
		category_id: 1
	};
}

const CATALOGO = [
	producto(1, 'Arroz 1 kg', 1450, 20),
	producto(2, 'Café molido', 4250, 10),
	producto(3, 'Escaso', 1000, 2)
];

function peticion(cambios: Partial<CheckoutRequest> = {}): CheckoutRequest {
	return {
		lines: [{ id_product: 1, quantity: 3 }],
		paymentMethod: CASH_METHOD,
		cashReceived: 5000,
		clientId: null,
		saleNumber: '20260816214305',
		userId: 7,
		...cambios
	};
}

describe('venta que se puede cobrar', () => {
	it('arma el cuerpo con los totales del invariante', () => {
		const r = prepareSale(peticion(), CATALOGO, IVA, AHORA);

		expect(r.ok).toBe(true);
		if (!r.ok) return;
		expect(r.totals).toEqual({ subtotal: 4350, tax: 565.5, total: 4915.5 });
		expect(r.payload.subtotal).toBe(4350);
		expect(r.payload.tax).toBe(565.5);
		expect(r.payload.total).toBe(4915.5);
		expect(r.payload.change_given).toBe(84.5);
	});

	it('el precio lo pone el catálogo, no el navegador', () => {
		// Aunque la caja mandara otro precio, acá ni se mira: solo viajan
		// identificador y cantidad.
		const r = prepareSale(peticion(), CATALOGO, IVA, AHORA);
		if (!r.ok) throw new Error('debía poderse cobrar');
		expect(r.payload.products).toEqual([{ id_product: 1, stock: 3 }]);
		expect(r.totals.subtotal).toBe(3 * 1450);
	});

	it('varias líneas', () => {
		const r = prepareSale(
			peticion({ lines: [{ id_product: 1, quantity: 1 }, { id_product: 2, quantity: 1 }], cashReceived: 10000 }),
			CATALOGO,
			IVA,
			AHORA
		);
		if (!r.ok) throw new Error('debía poderse cobrar');
		expect(r.totals.total).toBe(6441);
		expect(r.payload.change_given).toBe(3559);
	});

	it('sella la hora local, no UTC', () => {
		const r = prepareSale(peticion(), CATALOGO, IVA, AHORA);
		if (!r.ok) throw new Error('debía poderse cobrar');
		expect(r.payload.created_at).toBe('2026-08-16T21:43:05');
	});

	it('trunca las cantidades: media unidad no existe', () => {
		const r = prepareSale(
			peticion({ lines: [{ id_product: 1, quantity: 2.9 }] }),
			CATALOGO,
			IVA,
			AHORA
		);
		if (!r.ok) throw new Error('debía poderse cobrar');
		expect(r.payload.products[0].stock).toBe(2);
	});

	it('lleva el cliente cuando hay', () => {
		const r = prepareSale(peticion({ clientId: 4 }), CATALOGO, IVA, AHORA);
		if (!r.ok) throw new Error('debía poderse cobrar');
		expect(r.payload.client_id).toBe(4);
	});

	it('usa la tasa que se le pasa y no una constante', () => {
		const r = prepareSale(peticion(), CATALOGO, 0.04, AHORA);
		if (!r.ok) throw new Error('debía poderse cobrar');
		expect(r.totals.tax).toBe(174);
		expect(r.totals.total).toBe(4524);
	});
});

describe('métodos que no son efectivo', () => {
	it('se cobran por el importe exacto y sin vuelto', () => {
		const r = prepareSale(
			peticion({ paymentMethod: 'Tarjeta de crédito', cashReceived: 0 }),
			CATALOGO,
			IVA,
			AHORA
		);
		if (!r.ok) throw new Error('debía poderse cobrar');
		expect(r.payload.cash_received).toBe(4915.5);
		expect(r.payload.change_given).toBe(0);
	});

	it('no exigen que el monto recibido alcance', () => {
		// No hay gaveta de por medio: pedirlo sería pedir un dato que no existe.
		const r = prepareSale(
			peticion({ paymentMethod: 'Transferencia bancaria', cashReceived: 0 }),
			CATALOGO,
			IVA,
			AHORA
		);
		expect(r.ok).toBe(true);
	});
});

describe('venta que no se puede cobrar', () => {
	it('sin líneas', () => {
		const r = prepareSale(peticion({ lines: [] }), CATALOGO, IVA, AHORA);
		expect(r).toEqual({ ok: false, message: 'Agregá al menos un producto antes de cobrar.', field: undefined });
	});

	it('con algo que no es una lista', () => {
		const r = prepareSale(
			peticion({ lines: null as unknown as CheckoutRequest['lines'] }),
			CATALOGO,
			IVA,
			AHORA
		);
		expect(r.ok).toBe(false);
	});

	it('con un número de factura que no tiene la forma esperada', () => {
		for (const malo of ['', '123', 'abcdefghijklmn', '202608162143050']) {
			const r = prepareSale(peticion({ saleNumber: malo }), CATALOGO, IVA, AHORA);
			expect(r.ok, malo).toBe(false);
			if (!r.ok) expect(r.message).toBe('El número de factura no es válido.');
		}
	});

	it('con un producto que ya no existe', () => {
		const r = prepareSale(
			peticion({ lines: [{ id_product: 99, quantity: 1 }] }),
			CATALOGO,
			IVA,
			AHORA
		);
		expect(r.ok).toBe(false);
		if (!r.ok) expect(r.message).toBe('Un producto de la venta ya no existe.');
	});

	it('con una cantidad que no tiene sentido', () => {
		for (const q of [0, -2, 0.4]) {
			const r = prepareSale(
				peticion({ lines: [{ id_product: 1, quantity: q }] }),
				CATALOGO,
				IVA,
				AHORA
			);
			expect(r.ok, String(q)).toBe(false);
			if (!r.ok) expect(r.message).toBe('Cantidad inválida para Arroz 1 kg.');
		}
	});

	it('sin existencias suficientes', () => {
		const r = prepareSale(
			peticion({ lines: [{ id_product: 3, quantity: 5 }] }),
			CATALOGO,
			IVA,
			AHORA
		);
		expect(r.ok).toBe(false);
		if (!r.ok) expect(r.message).toBe('Stock insuficiente para Escaso: quedan 2.');
	});

	it('con efectivo que no alcanza, señalando el campo', () => {
		const r = prepareSale(peticion({ cashReceived: 1000 }), CATALOGO, IVA, AHORA);
		expect(r.ok).toBe(false);
		if (!r.ok) {
			expect(r.message).toBe('El monto recibido no cubre el total de la venta.');
			expect(r.field).toBe('cash_received');
		}
	});

	it('pagar justo alcanza', () => {
		expect(prepareSale(peticion({ cashReceived: 4915.5 }), CATALOGO, IVA, AHORA).ok).toBe(true);
	});

	it('si falla una línea, no se arma nada', () => {
		const r = prepareSale(
			peticion({ lines: [{ id_product: 1, quantity: 1 }, { id_product: 3, quantity: 99 }] }),
			CATALOGO,
			IVA,
			AHORA
		);
		expect(r.ok).toBe(false);
	});
});
