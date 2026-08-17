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

export interface Decision {
	ok: boolean;
	/** Motivo del rechazo, listo para mostrar. */
	message?: string;
	/** Cantidad que queda en la línea si la decisión fue que sí. */
	quantity?: number;
}

const SI: Decision = { ok: true };

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
	if (quantity <= 0) return { ok: false, message: 'La cantidad debe ser mayor que cero.' };
	if (product.stock <= 0) return { ok: false, message: `${product.name} no tiene existencias.` };

	const resulting = (current?.quantity ?? 0) + quantity;

	if (resulting + reserved > product.stock) {
		const libre = Math.max(0, product.stock - reserved);
		return {
			ok: false,
			message: reserved
				? `Solo quedan ${libre} de ${product.name}: hay ${reserved} apartadas en otra venta.`
				: `Solo hay ${product.stock} unidades de ${product.name}${
						current ? ` y ya llevás ${current.quantity}` : ''
					}.`
		};
	}

	return { ...SI, quantity: resulting };
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
		const libre = Math.max(0, line.stock - reserved);
		return { ok: false, message: `Solo quedan ${libre} unidades de ${line.name}.` };
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
