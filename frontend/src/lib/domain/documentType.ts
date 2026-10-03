/**
 * Los siete comprobantes, cuáles emite cada compañía y cuál sale de una venta
 * (RN-85, RN-87, RN-88).
 *
 * Es la misma regla que `backend/app/domain/fe_document_type.py`, y está dos
 * veces por lo mismo que la plata: la pantalla tiene que proponer lo que el
 * servidor va a aplicar. Si el selector ofreciera una factura sin cliente, el
 * cajero se enteraría del «no» con el cliente enfrente.
 *
 * **De una venta** salen dos hoy, y los distingue el receptor. La factura exige
 * uno con nombre e identificación; el tiquete no, y por eso es lo que se le
 * entrega al cliente de contado. Con cliente la venta sale como factura, salvo
 * que el cajero la deje en tiquete.
 *
 * **Los otros cinco** no se eligen al cobrar porque nacen de su propio flujo
 * (RN-87): la nota de crédito de una devolución, la de débito de la factura
 * abierta, la factura de compra de una compra, el recibo de pago de cobrar una
 * venta a crédito. La de exportación sí es una venta y se suma acá con T-727.
 */

export const INVOICE = '01';
export const DEBIT_NOTE = '02';
export const CREDIT_NOTE = '03';
export const TICKET = '04';
export const PURCHASE_INVOICE = '08';
export const EXPORT_INVOICE = '09';
export const PAYMENT_RECEIPT = '10';

export type CounterDocumentType = typeof INVOICE | typeof TICKET;

/** Los siete, en el orden de Configuración: lo que se vende, lo que corrige, lo que nace de otro lado. */
export const ALL_TYPES: readonly string[] = [
	TICKET,
	INVOICE,
	EXPORT_INVOICE,
	CREDIT_NOTE,
	DEBIT_NOTE,
	PURCHASE_INVOICE,
	PAYMENT_RECEIPT
];

/**
 * Los que ya tienen un flujo que los emita. **Es una lista y no una casilla**:
 * cuando llegue la ND (T-726) se agrega acá y en el servidor, y su casilla en
 * Configuración empieza a moverse sola (RN-88).
 */
export const AVAILABLE: readonly string[] = [TICKET, INVOICE, CREDIT_NOTE];

/** Los que no se apagan: toda devolución de un comprobante emitido pasa por una NC. */
export const ALWAYS_ON: readonly string[] = [CREDIT_NOTE];

/** Con los que nace una compañía: los que Hacienda pide para certificarse y operar. */
export const DEFAULT_ENABLED: readonly string[] = [TICKET, INVOICE, CREDIT_NOTE, DEBIT_NOTE];

/** Los que se emiten al cobrar. */
export const COUNTER_TYPES: readonly CounterDocumentType[] = [INVOICE, TICKET];

export function isCounterDocumentType(value: unknown): value is CounterDocumentType {
	return value === INVOICE || value === TICKET;
}

/** En el orden de `ALL_TYPES`, para que la configuración se guarde siempre igual. */
function ordenados(codigos: Iterable<string>): string[] {
	const juego = new Set(codigos);
	return ALL_TYPES.filter((codigo) => juego.has(codigo));
}

/**
 * Lo que la compañía emite, a partir de lo guardado, venga como venga (RN-88).
 *
 * Mismo saneo que el servidor: ausente es la de fábrica, se tiran los códigos
 * que no son de Hacienda, se agrega lo que no se apaga, y si no quedó ni
 * tiquete ni factura se vuelve a la de fábrica. **Nunca lanza**, como el resto
 * de `mergeSettings`.
 */
export function enabledTypes(raw: unknown): string[] {
	if (!Array.isArray(raw)) return [...DEFAULT_ENABLED];
	const elegidos = new Set(raw.filter((codigo): codigo is string => ALL_TYPES.includes(codigo)));
	if (!COUNTER_TYPES.some((codigo) => elegidos.has(codigo))) return ordenados(DEFAULT_ENABLED);
	for (const codigo of ALWAYS_ON) elegidos.add(codigo);
	return ordenados(elegidos);
}

/**
 * Si la casilla de un tipo se puede mover en Configuración.
 *
 * No se mueve lo que no tiene flujo todavía, lo que no se apaga, ni el último
 * tipo de venta encendido: con los dos apagados no se podría cobrar.
 */
export function canToggle(codigo: string, enabled: readonly string[]): boolean {
	if (!AVAILABLE.includes(codigo) || ALWAYS_ON.includes(codigo)) return false;
	const esElUltimoDeVenta =
		COUNTER_TYPES.includes(codigo as CounterDocumentType) &&
		enabled.includes(codigo) &&
		COUNTER_TYPES.filter((c) => enabled.includes(c)).length === 1;
	return !esElUltimoDeVenta;
}

/** El que se emite si nadie elige otro, con lo que la compañía tiene encendido. */
export function suggestedDocumentType(
	hasReceiver: boolean,
	enabled: readonly string[] = DEFAULT_ENABLED
): CounterDocumentType {
	if (hasReceiver && enabled.includes(INVOICE)) return INVOICE;
	return enabled.includes(TICKET) ? TICKET : INVOICE;
}

/**
 * El que se va a emitir, con lo que eligió el cajero. Nulo es «así no se puede
 * cobrar»: una compañía que solo factura, sin cliente elegido.
 *
 * Lo elegido se respeta solo mientras sea posible: sin receptor no hay factura,
 * y un tipo apagado no se emite. Lo que no se devuelve nunca es una elección
 * imposible, porque la pantalla la mostraría y el servidor la rechazaría.
 */
export function effectiveDocumentType(
	chosen: CounterDocumentType | null | undefined,
	hasReceiver: boolean,
	enabled: readonly string[] = DEFAULT_ENABLED
): CounterDocumentType | null {
	const posibles = COUNTER_TYPES.filter(
		(tipo) => enabled.includes(tipo) && (tipo !== INVOICE || hasReceiver)
	);
	if (chosen && posibles.includes(chosen)) return chosen;
	const sugerido = suggestedDocumentType(hasReceiver, enabled);
	return posibles.includes(sugerido) ? sugerido : null;
}

/** Por qué no sale el comprobante pedido. Código y no frase: esto es dominio. */
export type DocumentTypeRejection =
	| 'invalid_sale_document_type'
	| 'document_type_not_enabled'
	| 'invoice_needs_receiver';

/**
 * El tipo con el que va a quedar la venta, con la misma regla y el mismo orden
 * que `document_type_for` del servidor. Nulo es «sin facturación electrónica».
 */
export function documentTypeFor(
	requested: string | null,
	opciones: { einvoicing: boolean; enabled: readonly string[]; hasReceiver: boolean }
): { ok: true; type: CounterDocumentType | null } | { ok: false; code: DocumentTypeRejection } {
	if (requested !== null && !isCounterDocumentType(requested)) {
		return { ok: false, code: 'invalid_sale_document_type' };
	}
	if (!opciones.einvoicing) return { ok: true, type: null };
	let tipo: CounterDocumentType;
	if (requested === null) {
		tipo = suggestedDocumentType(opciones.hasReceiver, opciones.enabled);
	} else if (!opciones.enabled.includes(requested)) {
		return { ok: false, code: 'document_type_not_enabled' };
	} else {
		tipo = requested;
	}
	if (tipo === INVOICE && !opciones.hasReceiver) return { ok: false, code: 'invoice_needs_receiver' };
	return { ok: true, type: tipo };
}
