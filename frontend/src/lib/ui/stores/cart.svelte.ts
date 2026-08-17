import { browser } from '$app/environment';
import {
	MAX_TICKETS,
	canAdd,
	canSetQuantity,
	newLine,
	nextActiveId,
	reservedElsewhere,
	unitCount
} from '$lib/domain/cart';
import { computeTotals, lineTotal, taxRate, type Totals } from '$lib/domain/money';
import type { CartLine, Product } from '$lib/domain/types';

export { MAX_TICKETS };

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

		const siguiente = nextActiveId(this.tickets, index);
		this.tickets.splice(index, 1);
		if (this.activeId === id && siguiente !== null) this.activeId = siguiente;
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
		return unitCount(this.lines);
	}

	countOf(ticket: Ticket): number {
		return unitCount(ticket.lines);
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
		const lines = this.active.lines;
		const existing = lines.find((l) => l.id_product === product.id_product);
		const apartadas = reservedElsewhere(this.tickets, this.activeId, product.id_product);

		const decision = canAdd(product, quantity, existing, apartadas);
		if (!decision.ok) return decision;

		if (existing) {
			existing.quantity = decision.quantity!;
			// Precio y stock se refrescan: pudieron cambiar desde otra caja.
			existing.price = product.price;
			existing.stock = product.stock;
		} else {
			lines.push(newLine(product, quantity));
		}
		this.save();
		return { ok: true };
	}

	/** Fija la cantidad exacta de una línea. Cero o menos la elimina. */
	setQuantity(idProduct: number, quantity: number): AddResult {
		const line = this.lines.find((l) => l.id_product === idProduct);
		if (!line) return { ok: false, message: 'El producto no está en la venta.' };

		const apartadas = reservedElsewhere(this.tickets, this.activeId, idProduct);
		const decision = canSetQuantity(line, quantity, apartadas);
		if (!decision.ok) return decision;

		if (decision.quantity === 0) {
			this.remove(idProduct);
			return { ok: true };
		}

		line.quantity = decision.quantity!;
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

	/**
	 * Tira todo: las ventas en espera y lo guardado en el navegador.
	 *
	 * Lo usa el cambio de compañía (RN-27). Una venta a medias son productos de
	 * la compañía anterior —con sus precios y sus identificadores—, y arrastrarla
	 * a otra compañía no es un inconveniente estético: es cobrarle a un negocio
	 * artículos que no son suyos.
	 */
	reset() {
		this.tickets = [blankTicket(1)];
		this.activeId = 1;
		if (browser) sessionStorage.removeItem(STORAGE_KEY);
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
