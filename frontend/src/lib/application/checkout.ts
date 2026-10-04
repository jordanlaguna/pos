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
import { EXPORT_INVOICE, documentTypeFor } from '$lib/domain/documentType';
import { exportLineProblem, hasForeignAddress } from '$lib/domain/export';
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
	/** Opcional desde T-706. Si viene, 14 dígitos. */
	saleNumber?: string;
	userId: number;
	/**
	 * El comprobante que eligió el cajero (RN-85), tal como vino del formulario.
	 * Nulo es «el que sugiera la regla».
	 */
	documentType: string | null;
	/**
	 * Lo que dice la configuración que el servidor acaba de leer —si la compañía
	 * factura electrónicamente y qué comprobantes emite (RN-88)—, no la que tenía
	 * la pantalla al abrirse: el dueño pudo cambiarla con la caja abierta.
	 */
	einvoicing: boolean;
	enabledTypes: readonly string[];
	/**
	 * Quién es el cliente ante Hacienda (RN-87, T-727): si es del extranjero se
	 * le exporta, y la exportación necesita su dirección. Lo lee el servidor de
	 * la ficha del cliente, no el formulario.
	 */
	foreignReceiver: boolean;
	foreignAddress?: string | null;
}

export interface SalePayload {
	/** Opcional desde T-706: el número lo pone el servidor con su reloj. */
	sale_number?: string;
	client_id: number | null;
	document_type: string | null;
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

/**
 * Motivo del rechazo, como código y datos. Igual que en el dominio y por lo
 * mismo: esta capa no sabe en qué idioma está la pantalla (RN-30 aplicada
 * adentro). La frase la arma `$lib/ui/messages.ts`.
 */
export type CheckoutRejection =
	| { code: 'checkout_no_lines' }
	| { code: 'checkout_bad_sale_number' }
	| { code: 'checkout_product_gone' }
	| { code: 'checkout_bad_quantity'; product: string }
	| { code: 'checkout_insufficient_stock'; product: string; available: number }
	| { code: 'checkout_cash_short' }
	| { code: 'checkout_invoice_needs_client' }
	| { code: 'checkout_document_type_not_enabled' }
	| { code: 'checkout_bad_document_type' }
	| { code: 'checkout_invoice_needs_resident' }
	| { code: 'checkout_export_needs_client' }
	| { code: 'checkout_export_needs_foreign_client' }
	| { code: 'checkout_export_needs_foreign_address' }
	| { code: 'checkout_export_line_needs_tariff_heading'; product: string }
	| { code: 'checkout_export_tariff_not_allowed'; product: string; taxCode: string };

export type CheckoutResult =
	| { ok: false; reason: CheckoutRejection; field?: string }
	| { ok: true; payload: SalePayload; totals: Totals };

function no(reason: CheckoutRejection, field?: string): CheckoutResult {
	return { ok: false, reason, field };
}

export function prepareSale(
	request: CheckoutRequest,
	catalog: Product[],
	taxRate: number,
	now: Date
): CheckoutResult {
	if (!Array.isArray(request.lines) || request.lines.length === 0) {
		return no({ code: 'checkout_no_lines' });
	}
	// Desde T-706 el número lo pone el servidor con su reloj, así que lo normal
	// es que no venga. Si viene —una pantalla vieja—, tiene que ser el de
	// siempre: 14 dígitos, `yyyyMMddHHmmss`; otra cosa es algo manipulado.
	if (request.saleNumber && !/^\d{14}$/.test(request.saleNumber)) {
		return no({ code: 'checkout_bad_sale_number' });
	}
	// El comprobante, con la misma regla que el servidor (RN-85, RN-88). La
	// pantalla no ofrece lo imposible, así que llegar acá es una pantalla vieja o
	// un cliente que se quitó a mitad del cobro: se dice antes de ir al servidor,
	// que diría lo mismo con un código.
	const comprobante = documentTypeFor(request.documentType, {
		einvoicing: request.einvoicing,
		enabled: request.enabledTypes,
		hasReceiver: request.clientId !== null,
		foreign: request.foreignReceiver
	});
	if (!comprobante.ok) {
		switch (comprobante.code) {
			case 'invoice_needs_receiver':
				return no({ code: 'checkout_invoice_needs_client' });
			case 'invoice_needs_resident':
				return no({ code: 'checkout_invoice_needs_resident' });
			case 'export_needs_receiver':
				return no({ code: 'checkout_export_needs_client' });
			case 'export_needs_foreign_receiver':
				return no({ code: 'checkout_export_needs_foreign_client' });
			case 'document_type_not_enabled':
				return no({ code: 'checkout_document_type_not_enabled' });
			default:
				return no({ code: 'checkout_bad_document_type' });
		}
	}
	// La exportación lleva las señas del receptor en vez de su ubicación (RF-78):
	// se arregla en la ficha del cliente, y se dice antes de ir al servidor.
	if (comprobante.type === EXPORT_INVOICE && !hasForeignAddress(request.foreignAddress)) {
		return no({ code: 'checkout_export_needs_foreign_address' });
	}

	// `taxRate` en nulo es «la configurada del negocio» (RN-9); `computeTotals`
	// la resuelve con la tasa que recibe de respaldo.
	const priced: {
		id_product: number;
		price: number;
		quantity: number;
		taxRate: number | null;
	}[] = [];
	/** Los productos de la venta, en su orden, para lo que la exportación exige de cada uno. */
	const vendidos: Product[] = [];
	for (const line of request.lines) {
		const product = catalog.find((p) => p.id_product === Number(line.id_product));
		if (!product) return no({ code: 'checkout_product_gone' });

		const quantity = Math.trunc(Number(line.quantity));
		if (!(quantity > 0)) return no({ code: 'checkout_bad_quantity', product: product.name });
		if (quantity > product.stock) {
			return no({
				code: 'checkout_insufficient_stock',
				product: product.name,
				available: product.stock
			});
		}

		// El precio sale del catálogo. Lo que mandó el navegador ni se mira. Y
		// desde F5, la tarifa también: cada producto lleva la suya, y `null` es
		// «la configurada del negocio» (RN-9), que es la que va de respaldo.
		priced.push({
			id_product: product.id_product,
			price: Number(product.price),
			quantity,
			taxRate: product.tax_rate ?? null
		});
		vendidos.push(product);
	}

	// Lo que una exportación exige de cada línea (RF-78, T-720): la partida de
	// cada mercancía y una tarifa que la FEE admita. Con el producto, como el
	// servidor: «falta la partida» sin decir de cuál obliga a revisar la venta.
	if (comprobante.type === EXPORT_INVOICE) {
		for (const product of vendidos) {
			const problema = exportLineProblem(product);
			if (problema?.code === 'export_tariff_not_allowed') {
				return no({
					code: 'checkout_export_tariff_not_allowed',
					product: product.name,
					taxCode: problema.taxCode
				});
			}
			if (problema) {
				return no({ code: 'checkout_export_line_needs_tariff_heading', product: product.name });
			}
		}
	}

	const totals = computeTotals(priced, taxRate);

	// En efectivo el monto entregado tiene que alcanzar; en los demás métodos se
	// cobra el importe exacto, así que no hay vuelto que calcular.
	const isCash = request.paymentMethod === CASH_METHOD;
	const received = isCash ? round2(request.cashReceived) : totals.total;
	if (isCash && received < totals.total) {
		return no({ code: 'checkout_cash_short' }, 'cash_received');
	}

	return {
		ok: true,
		totals,
		payload: {
			...(request.saleNumber ? { sale_number: request.saleNumber } : {}),
			client_id: request.clientId,
			// El que decidió la regla, no el que vino del formulario: sin elección,
			// viaja la sugerencia, que es lo mismo que el servidor aplicaría.
			document_type: comprobante.type,
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
