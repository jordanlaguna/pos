import { browser } from '$app/environment';
import { computeTotals, lineTotal, round2, taxRate, type Totals } from '$lib/money';
import type { CartLine, Product } from '$lib/types';

/**
 * Ventas en curso.
 *
 * Un mostrador real no atiende de a un cliente por vez: alguien deja su compra
 * a medias porque volvió por otro producto, y detrás hay tres personas
 * esperando. Por eso hay varias ventas abiertas al mismo tiempo y el cajero
 * salta entre ellas; solo una está activa.
 *
 * Todo vive en sessionStorage: si el navegador se recarga —o la pestaña se
 * cierra sin querer— las ventas en espera siguen ahí. El WinForms perdía la
 * venta entera al cerrar el formulario, y ni siquiera podía tener dos.
 */

const STORAGE_KEY = 'ventasys-ventas';

/** Tope de ventas simultáneas. Más que esto no se maneja: se pierde el hilo. */
export const MAX_TICKETS = 8;

export interface Ticket {
	id: number;
	lines: CartLine[];
	/** Cliente asociado, como string porque viene de un <select>. */
	clientId: string;
	createdAt: number;
}

export interface AddResult {
	ok: boolean;
	/** Motivo del rechazo, listo para mostrar. */
	message?: string;
}

interface Persisted {
	tickets: Ticket[];
	activeId: number;
	sequence: number;
}

function blankTicket(id: number): Ticket {
	return { id, lines: [], clientId: '', createdAt: Date.now() };
}

class Cart {
	tickets = $state<Ticket[]>([blankTicket(1)]);
	activeId = $state(1);
	private sequence = 1;

	constructor() {
		if (browser) this.restore();
	}

	// ------------------------------------------------------------ persistencia

	private restore() {
		try {
			const raw = sessionStorage.getItem(STORAGE_KEY);
			if (!raw) return;
			const parsed = JSON.parse(raw) as Persisted;
			if (!Array.isArray(parsed?.tickets) || parsed.tickets.length === 0) return;

			this.tickets = parsed.tickets;
			this.sequence = parsed.sequence ?? Math.max(...parsed.tickets.map((t) => t.id));
			// Si el id guardado ya no existe, se cae a la primera venta.
			this.activeId = parsed.tickets.some((t) => t.id === parsed.activeId)
				? parsed.activeId
				: parsed.tickets[0].id;
		} catch {
			// Contenido inservible: se empieza limpio.
		}
	}

	private save() {
		if (!browser) return;
		try {
			const data: Persisted = {
				tickets: this.tickets,
				activeId: this.activeId,
				sequence: this.sequence
			};
			sessionStorage.setItem(STORAGE_KEY, JSON.stringify(data));
		} catch {
			// Sin almacenamiento sigue funcionando, solo que en memoria.
		}
	}

	// -------------------------------------------------------- venta en espera

	get active(): Ticket {
		return this.tickets.find((t) => t.id === this.activeId) ?? this.tickets[0];
	}

	/** Índice humano de una venta: la pestaña muestra «Venta 2», no el id. */
	positionOf(id: number): number {
		return this.tickets.findIndex((t) => t.id === id) + 1;
	}

	get canOpenMore(): boolean {
		return this.tickets.length < MAX_TICKETS;
	}

	/** Abre otra venta y la deja activa. La anterior queda en espera. */
	open(): AddResult {
		if (!this.canOpenMore) {
			return {
				ok: false,
				message: `No se pueden tener más de ${MAX_TICKETS} ventas en espera.`
			};
		}
		this.sequence += 1;
		const ticket = blankTicket(this.sequence);
		this.tickets.push(ticket);
		this.activeId = ticket.id;
		this.save();
		return { ok: true };
	}

	switchTo(id: number) {
		if (this.tickets.some((t) => t.id === id)) {
			this.activeId = id;
			this.save();
		}
	}

	/** Pasa a la siguiente venta en espera, en círculo. Para el atajo de teclado. */
	next() {
		if (this.tickets.length < 2) return;
		const index = this.tickets.findIndex((t) => t.id === this.activeId);
		this.activeId = this.tickets[(index + 1) % this.tickets.length].id;
		this.save();
	}

	/**
	 * Descarta una venta. Nunca quedan cero: si era la única, se vacía en vez de
	 * desaparecer, para que la pantalla siempre tenga dónde escanear.
	 */
	close(id: number) {
		if (this.tickets.length === 1) {
			this.tickets[0].lines = [];
			this.tickets[0].clientId = '';
			this.save();
			return;
		}

		const index = this.tickets.findIndex((t) => t.id === id);
		if (index === -1) return;

		this.tickets.splice(index, 1);
		if (this.activeId === id) {
			// Se pasa a la de la izquierda, o a la primera si se cerró la primera.
			this.activeId = this.tickets[Math.max(0, index - 1)].id;
		}
		this.save();
	}

	/** Ventas distintas de la activa que tienen algo dentro. */
	get waitingCount(): number {
		return this.tickets.filter((t) => t.id !== this.activeId && t.lines.length > 0).length;
	}

	// ------------------------------------------------------------ venta activa

	get lines(): CartLine[] {
		return this.active.lines;
	}

	get clientId(): string {
		return this.active.clientId;
	}

	setClient(value: string) {
		this.active.clientId = value;
		this.save();
	}

	get count(): number {
		return this.lines.reduce((acc, l) => acc + l.quantity, 0);
	}

	countOf(ticket: Ticket): number {
		return ticket.lines.reduce((acc, l) => acc + l.quantity, 0);
	}

	get isEmpty(): boolean {
		return this.lines.length === 0;
	}

	/*
	 * Los totales del carrito son un anticipo de lo que va a cobrar el servidor,
	 * así que usan la tasa configurada y no una constante: si el negocio factura
	 * al 4 %, mostrar 13 % en la pantalla de cobro y cobrar otra cosa es peor que
	 * no mostrar nada. El importe que vale sigue siendo el que calcula el servidor
	 * releyendo los precios.
	 */
	get totals(): Totals {
		return computeTotals(this.lines, taxRate());
	}

	totalsOf(ticket: Ticket): Totals {
		return computeTotals(ticket.lines, taxRate());
	}

	lineTotal(line: CartLine): number {
		return lineTotal(line.price, line.quantity);
	}

	/**
	 * Suma unidades a la venta activa. Si el producto ya está, acumula —igual que
	 * `AddProductToSaleTable` del original—, pero validando el stock contra el
	 * total resultante y no solo contra la cantidad nueva.
	 */
	add(product: Product, quantity = 1): AddResult {
		if (quantity <= 0) return { ok: false, message: 'La cantidad debe ser mayor que cero.' };
		if (product.stock <= 0)
			return { ok: false, message: `${product.name} no tiene existencias.` };

		const lines = this.active.lines;
		const existing = lines.find((l) => l.id_product === product.id_product);
		const resulting = (existing?.quantity ?? 0) + quantity;

		/*
		 * El stock se mide contra lo apartado en TODAS las ventas abiertas, no
		 * solo en esta. Si quedan 3 unidades y la venta en espera ya tiene 2, acá
		 * solo puede entrar 1: si no, al cobrar la segunda el backend la rechaza y
		 * el cajero se entera con el cliente enfrente.
		 */
		const enOtras = this.tickets
			.filter((t) => t.id !== this.activeId)
			.reduce(
				(acc, t) =>
					acc + (t.lines.find((l) => l.id_product === product.id_product)?.quantity ?? 0),
				0
			);

		if (resulting + enOtras > product.stock) {
			const libre = Math.max(0, product.stock - enOtras);
			return {
				ok: false,
				message: enOtras
					? `Solo quedan ${libre} de ${product.name}: hay ${enOtras} apartadas en otra venta.`
					: `Solo hay ${product.stock} unidades de ${product.name}${
							existing ? ` y ya llevás ${existing.quantity}` : ''
						}.`
			};
		}

		if (existing) {
			existing.quantity = resulting;
			// Precio y stock se refrescan: pudieron cambiar desde otra caja.
			existing.price = product.price;
			existing.stock = product.stock;
		} else {
			lines.push({
				id_product: product.id_product,
				barcode: product.barcode,
				name: product.name,
				price: product.price,
				quantity,
				stock: product.stock
			});
		}
		this.save();
		return { ok: true };
	}

	/** Fija la cantidad exacta de una línea. Cero o menos la elimina. */
	setQuantity(idProduct: number, quantity: number): AddResult {
		const line = this.lines.find((l) => l.id_product === idProduct);
		if (!line) return { ok: false, message: 'El producto no está en la venta.' };

		if (quantity <= 0) {
			this.remove(idProduct);
			return { ok: true };
		}

		const enOtras = this.tickets
			.filter((t) => t.id !== this.activeId)
			.reduce(
				(acc, t) => acc + (t.lines.find((l) => l.id_product === idProduct)?.quantity ?? 0),
				0
			);

		if (quantity + enOtras > line.stock) {
			const libre = Math.max(0, line.stock - enOtras);
			return { ok: false, message: `Solo quedan ${libre} unidades de ${line.name}.` };
		}

		line.quantity = Math.trunc(quantity);
		this.save();
		return { ok: true };
	}

	increment(idProduct: number): AddResult {
		const line = this.lines.find((l) => l.id_product === idProduct);
		if (!line) return { ok: false };
		return this.setQuantity(idProduct, line.quantity + 1);
	}

	decrement(idProduct: number): AddResult {
		const line = this.lines.find((l) => l.id_product === idProduct);
		if (!line) return { ok: false };
		return this.setQuantity(idProduct, line.quantity - 1);
	}

	remove(idProduct: number) {
		this.active.lines = this.lines.filter((l) => l.id_product !== idProduct);
		this.save();
	}

	/** Vacía la venta activa sin cerrarla. */
	clear() {
		this.active.lines = [];
		this.active.clientId = '';
		this.save();
	}

	/**
	 * Cierra la venta que se acaba de cobrar y deja activa la siguiente en
	 * espera, para que el cajero siga sin tocar nada.
	 */
	completed(id: number = this.activeId) {
		this.close(id);
	}

	/** Formato que espera `POST /sales/add_sale`: `stock` es la cantidad vendida. */
	toPayload() {
		return this.lines.map((l) => ({
			id_product: l.id_product,
			stock: l.quantity,
			price: l.price,
			name: l.name
		}));
	}
}

export const cart = new Cart();

/** Número de factura `yyyyMMddHHmmss`, igual que generaba `Bills.cs`. */
export function saleNumber(date = new Date()): string {
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

/** Montos sugeridos para el pago en efectivo: el exacto y los redondeos al alza. */
export function quickCash(total: number): number[] {
	if (total <= 0) return [];
	const suggestions = new Set<number>([round2(total)]);
	for (const step of [500, 1000, 5000, 10000, 20000]) {
		const rounded = Math.ceil(total / step) * step;
		if (rounded > total) suggestions.add(rounded);
	}
	return [...suggestions].sort((a, b) => a - b).slice(0, 5);
}
