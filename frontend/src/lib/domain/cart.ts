/**
 * Reglas de la venta en curso.
 *
 * Puro: sin Svelte, sin `$state`, sin `fetch`. Lo que decide si un producto
 * entra al carrito y en qué cantidad vive acá; el almacén reactivo
 * (`$lib/ui/stores/cart.svelte.ts`) solo guarda el estado y llama a estas
 * funciones.
 *
 * La regla que importa es la de existencias, y no es obvia: **el stock se mide
 * contra lo apartado en TODAS las ventas abiertas**, no solo en la activa. Un
 * mostrador real tiene tres ventas a medias al mismo tiempo; si quedan 3
 * unidades y la venta en espera ya tiene 2, en la activa solo puede entrar 1. Sin
 * esto, al cobrar la segunda el backend la rechaza y el cajero se entera con el
 * cliente enfrente.
 */

import { round2 } from './money';
import type { CartLine, Product } from './types';

/** Tope de ventas simultáneas. Más que esto no se maneja: se pierde el hilo. */
export const MAX_TICKETS = 8;

export interface TicketLines {
	id: number;
	lines: CartLine[];
}

/**
 * Motivo del rechazo, como **código y datos**: nunca como frase.
 *
 * Es la misma regla que RN-30 le impone al backend, aplicada acá adentro. El
 * dominio no puede armar la frase porque no sabe —ni tiene por qué saber— en qué
 * idioma está la pantalla; quien la arma es la interfaz, con su catálogo
 * (`$lib/ui/messages.ts`). De paso las pruebas dejan de comparar cadenas:
 * afirman qué código sale de qué situación, que es lo que de verdad importa.
 */
export type CartRejection =
	| { code: 'cart_quantity_not_positive' }
	| { code: 'cart_out_of_stock'; product: string }
	| { code: 'cart_reserved_elsewhere'; free: number; product: string; reserved: number }
	| { code: 'cart_only_units'; stock: number; product: string }
	| { code: 'cart_only_units_with_current'; stock: number; product: string; current: number }
	| { code: 'cart_only_free_units'; free: number; product: string }
	| { code: 'cart_max_tickets'; max: number }
	| { code: 'cart_line_not_found' };

export type Decision =
	/** `quantity` es lo que queda en la línea cuando la respuesta es que sí. */
	| { ok: true; quantity?: number }
	| { ok: false; reason: CartRejection };

/**
 * Unidades de un producto apartadas en las **otras** ventas abiertas.
 */
export function reservedElsewhere(
	tickets: TicketLines[],
	activeId: number,
	productId: number
): number {
	return tickets
		.filter((t) => t.id !== activeId)
		.reduce(
			(acc, t) => acc + (t.lines.find((l) => l.id_product === productId)?.quantity ?? 0),
			0
		);
}

/** Unidades totales de una lista de líneas. */
export function unitCount(lines: CartLine[]): number {
	return lines.reduce((acc, l) => acc + l.quantity, 0);
}

/**
 * ¿Se pueden agregar `quantity` unidades del producto a la venta activa?
 *
 * Devuelve la cantidad resultante de la línea cuando la respuesta es que sí, de
 * modo que quien llama no tenga que volver a sumar.
 */
export function canAdd(
	product: Product,
	quantity: number,
	current: CartLine | undefined,
	reserved: number
): Decision {
	if (quantity <= 0) return { ok: false, reason: { code: 'cart_quantity_not_positive' } };
	if (product.stock <= 0)
		return { ok: false, reason: { code: 'cart_out_of_stock', product: product.name } };

	const resulting = (current?.quantity ?? 0) + quantity;

	if (resulting + reserved > product.stock) {
		if (reserved) {
			return {
				ok: false,
				reason: {
					code: 'cart_reserved_elsewhere',
					free: Math.max(0, product.stock - reserved),
					product: product.name,
					reserved
				}
			};
		}
		return {
			ok: false,
			reason: current
				? {
						code: 'cart_only_units_with_current',
						stock: product.stock,
						product: product.name,
						current: current.quantity
					}
				: { code: 'cart_only_units', stock: product.stock, product: product.name }
		};
	}

	return { ok: true, quantity: resulting };
}

/**
 * ¿Se puede fijar la línea en `quantity` unidades?
 *
 * Cero o menos significa quitarla, y eso siempre se puede: `ok` con
 * `quantity: 0` es la señal de que hay que eliminar la línea.
 */
export function canSetQuantity(line: CartLine, quantity: number, reserved: number): Decision {
	if (quantity <= 0) return { ok: true, quantity: 0 };

	if (quantity + reserved > line.stock) {
		return {
			ok: false,
			reason: {
				code: 'cart_only_free_units',
				free: Math.max(0, line.stock - reserved),
				product: line.name
			}
		};
	}

	// Se trunca: media unidad de arroz no existe en el mostrador.
	return { ok: true, quantity: Math.trunc(quantity) };
}

/** Línea nueva a partir de un producto del catálogo. */
export function newLine(product: Product, quantity: number): CartLine {
	return {
		id_product: product.id_product,
		barcode: product.barcode,
		name: product.name,
		price: product.price,
		quantity,
		stock: product.stock
	};
}

/**
 * Cuál queda activa al cerrar una venta: la de la izquierda, o la primera si se
 * cerró la primera. Devuelve `null` si no queda ninguna.
 */
export function nextActiveId(tickets: TicketLines[], closedIndex: number): number | null {
	const quedan = tickets.filter((_, i) => i !== closedIndex);
	if (quedan.length === 0) return null;
	return quedan[Math.max(0, closedIndex - 1)].id;
}

// ------------------------------------------------------------------- cobro

/**
 * Número de factura `yyyyMMddHHmmss`, igual que generaba `Bills.cs`.
 *
 * Recibe la fecha en vez de leer el reloj para poder probarse: el mismo motivo
 * por el que el backend tiene un puerto `Clock`.
 */
export function saleNumber(date: Date): string {
	const pad = (n: number) => String(n).padStart(2, '0');
	return [
		date.getFullYear(),
		pad(date.getMonth() + 1),
		pad(date.getDate()),
		pad(date.getHours()),
		pad(date.getMinutes()),
		pad(date.getSeconds())
	].join('');
}

/**
 * Montos sugeridos para el pago en efectivo: el exacto y los redondeos al alza.
 *
 * Es lo que evita que el cajero teclee «10000» con el cliente esperando. Los
 * pasos son los billetes que circulan en Costa Rica.
 */
export function quickCash(total: number): number[] {
	if (total <= 0) return [];
	const suggestions = new Set<number>([round2(total)]);
	for (const step of [500, 1000, 5000, 10000, 20000]) {
		const rounded = Math.ceil(total / step) * step;
		if (rounded > total) suggestions.add(rounded);
	}
	return [...suggestions].sort((a, b) => a - b).slice(0, 5);
}
