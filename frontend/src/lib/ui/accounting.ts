/**
 * De código a frase, para contabilidad (F11).
 *
 * El backend no escribe texto para personas (RN-30): un asiento automático lleva
 * el **código** del evento en su descripción —`sale`, `cash_close`— y el número
 * de la fila que lo originó. La oración se arma acá, que es donde se sabe en qué
 * idioma está la pantalla.
 *
 * Los `switch` terminan en un valor por omisión y no en un `never` a propósito:
 * los códigos vienen de la base y una fila vieja puede traer uno que ya no
 * existe. Mostrar el código crudo es feo pero legible; una cadena vacía sería
 * una línea del libro sin nombre.
 */

import { m } from '$lib/paraglide/messages.js';
import type { AccountKind, EntryKind, JournalEntry } from '$lib/domain/types';

/** El nombre del tipo de cuenta: activo, pasivo, patrimonio… */
export function kindLabel(kind: AccountKind | string): string {
	switch (kind) {
		case 'asset':
			return m.accounting_kind_asset();
		case 'liability':
			return m.accounting_kind_liability();
		case 'equity':
			return m.accounting_kind_equity();
		case 'income':
			return m.accounting_kind_income();
		case 'cost':
			return m.accounting_kind_cost();
		case 'expense':
			return m.accounting_kind_expense();
		default:
			return kind;
	}
}

/** Cómo nació el asiento: automático, manual, de ajuste o de apertura. */
export function entryKindLabel(kind: EntryKind | string): string {
	switch (kind) {
		case 'auto':
			return m.accounting_entry_kind_auto();
		case 'manual':
			return m.accounting_entry_kind_manual();
		case 'adjustment':
			return m.accounting_entry_kind_adjustment();
		case 'opening':
			return m.accounting_entry_kind_opening();
		default:
			return kind;
	}
}

/** El movimiento del negocio que un mapeo traduce a cuentas. */
export function eventLabel(event: string): string {
	switch (event) {
		case 'sale':
			return m.accounting_event_sale();
		case 'return':
			return m.accounting_event_return();
		case 'cash_close':
			return m.accounting_event_cash_close();
		case 'cash_movement':
			return m.accounting_event_cash_movement();
		case 'purchase':
			return m.accounting_event_purchase();
		case 'supplier_payment':
			return m.accounting_event_supplier_payment();
		case 'payroll':
			return m.accounting_event_payroll();
		default:
			return event;
	}
}

/**
 * Qué dice un asiento en una línea.
 *
 * En los automáticos la descripción es un código y lo que informa de verdad es
 * **de dónde salió**: «Venta n.º 412». En los manuales y los de ajuste la
 * descripción la escribió una persona, así que se muestra tal cual.
 */
export function entryTitle(entry: Pick<JournalEntry, 'kind' | 'description' | 'source_type' | 'source_id'>): string {
	if (entry.kind !== 'auto') {
		// La apertura y la reclasificación pueden venir sin frase: ahí también
		// hay código, y tiene su nombre.
		switch (entry.description) {
			case 'opening':
				return m.accounting_auto_opening();
			case 'reclassify':
				return m.accounting_auto_reclassify();
			default:
				return entry.description;
		}
	}

	const id = entry.source_id ?? 0;
	switch (entry.source_type) {
		case 'sale':
			return m.accounting_auto_sale({ id });
		case 'return':
			return m.accounting_auto_return({ id });
		case 'cash_session':
			return m.accounting_auto_cash_close({ id });
		case 'cash_movement':
			return m.accounting_auto_cash_movement({ id });
		case 'stock_entry':
			return m.accounting_auto_purchase({ id });
		case 'supplier_payment':
			return m.accounting_auto_supplier_payment({ id });
		default:
			return entry.description;
	}
}

/** El periodo, como se nombra en pantalla: `9/2026`. */
export function periodLabel(year: number, month: number): string {
	return `${month}/${year}`;
}
