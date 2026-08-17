/**
 * Cobrar: preparar la venta que se le manda al backend.
 *
 * Es una función pura. Recibe lo que pidió la caja, el catálogo tal como lo
 * acaba de leer el servidor y la tasa configurada, y devuelve o el cuerpo listo
 * para `POST /sales/add_sale`, o el motivo por el que no se puede cobrar. No
 * hace `fetch`, no lee cookies y no sabe que existe SvelteKit: la acción de
 * `+page.server.ts` queda como transporte (T-112).
 *
 * Que sea pura es lo que permite comprobar sin levantar nada las dos cosas que
 * importan de este paso:
 *
 * - **Los precios los pone el catálogo**, no el navegador. Lo que el POS mandó
 *   como precio ni se mira.
 * - **El efectivo tiene que alcanzar** antes de que la venta salga de acá.
 *
 * El servidor vuelve a comprobar ambas cosas (T-108b); esto es la primera
 * barrera, la que le da al cajero un mensaje entendible en vez de un 400.
 */

import { toLocalIso } from '$lib/domain/datetime';
import { changeDue, computeTotals, round2, type Totals } from '$lib/domain/money';
import type { Product } from '$lib/domain/types';

/** El método que pasa por la gaveta. Los demás se cobran por el importe exacto. */
export const CASH_METHOD = 'Efectivo';

export interface RequestedLine {
	id_product: number;
	quantity: number;
}

export interface CheckoutRequest {
	lines: RequestedLine[];
	paymentMethod: string;
	cashReceived: number;
	clientId: number | null;
	saleNumber: string;
	userId: number;
}

export interface SalePayload {
	sale_number: string;
	client_id: number | null;
	user_id: number;
	subtotal: number;
	tax: number;
	total: number;
	payment_method: string;
	cash_received: number;
	change_given: number;
	created_at: string;
	products: { id_product: number; stock: number }[];
}

export type CheckoutResult =
	| { ok: false; message: string; field?: string }
	| { ok: true; payload: SalePayload; totals: Totals };

function no(message: string, field?: string): CheckoutResult {
	return { ok: false, message, field };
}

export function prepareSale(
	request: CheckoutRequest,
	catalog: Product[],
	taxRate: number,
	now: Date
): CheckoutResult {
	if (!Array.isArray(request.lines) || request.lines.length === 0) {
		return no('Agregá al menos un producto antes de cobrar.');
	}
	// 14 dígitos, `yyyyMMddHHmmss`. Lo genera el POS; si llega otra cosa, algo
	// se manipuló por el camino.
	if (!/^\d{14}$/.test(request.saleNumber)) {
		return no('El número de factura no es válido.');
	}

	const priced: { id_product: number; price: number; quantity: number }[] = [];
	for (const line of request.lines) {
		const product = catalog.find((p) => p.id_product === Number(line.id_product));
		if (!product) return no('Un producto de la venta ya no existe.');

		const quantity = Math.trunc(Number(line.quantity));
		if (!(quantity > 0)) return no(`Cantidad inválida para ${product.name}.`);
		if (quantity > product.stock) {
			return no(`Stock insuficiente para ${product.name}: quedan ${product.stock}.`);
		}

		// El precio sale del catálogo. Lo que mandó el navegador ni se mira.
		priced.push({ id_product: product.id_product, price: Number(product.price), quantity });
	}

	const totals = computeTotals(priced, taxRate);

	// En efectivo el monto entregado tiene que alcanzar; en los demás métodos se
	// cobra el importe exacto, así que no hay vuelto que calcular.
	const isCash = request.paymentMethod === CASH_METHOD;
	const received = isCash ? round2(request.cashReceived) : totals.total;
	if (isCash && received < totals.total) {
		return no('El monto recibido no cubre el total de la venta.', 'cash_received');
	}

	return {
		ok: true,
		totals,
		payload: {
			sale_number: request.saleNumber,
			client_id: request.clientId,
			user_id: request.userId,
			subtotal: totals.subtotal,
			tax: totals.tax,
			total: totals.total,
			payment_method: request.paymentMethod,
			cash_received: received,
			change_given: changeDue(received, totals.total),
			created_at: toLocalIso(now),
			products: priced.map((p) => ({ id_product: p.id_product, stock: p.quantity }))
		}
	};
}
