/**
 * Los siete comprobantes, cuáles emite cada compañía y cuál sale de una venta
 * (RN-85, RN-87, RN-88).
 *
 * Es la misma regla que `backend/app/domain/fe_document_type.py`, y está dos
 * veces por lo mismo que la plata: la pantalla tiene que proponer lo que el
 * servidor va a aplicar. Si el selector ofreciera una factura sin cliente, el
 * cajero se enteraría del «no» con el cliente enfrente.
 *
 * **De una venta** salen tres, y los distingue el receptor. La factura exige
 * uno con nombre y cédula del país; el tiquete no, y por eso es lo que se le
 * entrega al cliente de contado; la de exportación es para el cliente del
 * extranjero —identificación `05`—, que no tiene cédula costarricense y por eso
 * no puede recibir una factura (RN-87, T-727). Con cliente la venta sale como
 * factura —o como exportación—, salvo que el cajero la deje en tiquete.
 *
 * **Los otros cuatro** no se eligen al cobrar porque nacen de su propio flujo
 * (RN-87): la nota de crédito de una devolución, la de débito de la factura
 * abierta, la factura de compra de una compra, el recibo de pago de cobrar una
 * venta a crédito.
 */

export const INVOICE = '01';
export const DEBIT_NOTE = '02';
export const CREDIT_NOTE = '03';
export const TICKET = '04';
export const PURCHASE_INVOICE = '08';
export const EXPORT_INVOICE = '09';
export const PAYMENT_RECEIPT = '10';

export type CounterDocumentType = typeof INVOICE | typeof TICKET | typeof EXPORT_INVOICE;

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
 * cuando llega un flujo se agrega acá y en el servidor, y su casilla en
 * Configuración empieza a moverse sola (RN-88). La ND entró con T-726, la FEE
 * con T-727 y la FEC con T-728; queda el REP, que espera la venta a crédito.
 */
export const AVAILABLE: readonly string[] = [
	TICKET,
	INVOICE,
	CREDIT_NOTE,
	DEBIT_NOTE,
	EXPORT_INVOICE,
	PURCHASE_INVOICE
];

/** Los que no se apagan: toda devolución de un comprobante emitido pasa por una NC. */
export const ALWAYS_ON: readonly string[] = [CREDIT_NOTE];

/** Con los que nace una compañía: los que Hacienda pide para certificarse y operar. */
export const DEFAULT_ENABLED: readonly string[] = [TICKET, INVOICE, CREDIT_NOTE, DEBIT_NOTE];

/** Los que se emiten al cobrar. La FEE es una venta como las otras dos (T-727). */
export const COUNTER_TYPES: readonly CounterDocumentType[] = [INVOICE, TICKET, EXPORT_INVOICE];

/**
 * Los que se le emiten a un cliente del país: con los que un negocio puede
 * cobrar en su mostrador. Una lista que solo deja la exportación encendida no
 * le sirve para venderle a nadie de acá.
 */
export const DOMESTIC_COUNTER_TYPES: readonly CounterDocumentType[] = [INVOICE, TICKET];

export function isCounterDocumentType(value: unknown): value is CounterDocumentType {
	return value === INVOICE || value === TICKET || value === EXPORT_INVOICE;
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
	if (!DOMESTIC_COUNTER_TYPES.some((codigo) => elegidos.has(codigo)))
		return ordenados(DEFAULT_ENABLED);
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
		DOMESTIC_COUNTER_TYPES.includes(codigo as CounterDocumentType) &&
		enabled.includes(codigo) &&
		DOMESTIC_COUNTER_TYPES.filter((c) => enabled.includes(c)).length === 1;
	return !esElUltimoDeVenta;
}

/**
 * El que se emite si nadie elige otro, con lo que la compañía tiene encendido.
 *
 * Con cliente del país, factura si está encendida; con cliente del extranjero
 * (`foreign`), exportación si está encendida; si no, tiquete.
 */
export function suggestedDocumentType(
	hasReceiver: boolean,
	enabled: readonly string[] = DEFAULT_ENABLED,
	foreign = false
): CounterDocumentType {
	if (hasReceiver && foreign && enabled.includes(EXPORT_INVOICE)) return EXPORT_INVOICE;
	if (hasReceiver && !foreign && enabled.includes(INVOICE)) return INVOICE;
	return enabled.includes(TICKET) ? TICKET : INVOICE;
}

/** Si un tipo de venta se le puede emitir a este receptor (RN-85, RN-87). */
function cabeConElReceptor(tipo: CounterDocumentType, hasReceiver: boolean, foreign: boolean) {
	if (tipo === INVOICE) return hasReceiver && !foreign;
	if (tipo === EXPORT_INVOICE) return hasReceiver && foreign;
	return true;
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
	enabled: readonly string[] = DEFAULT_ENABLED,
	foreign = false
): CounterDocumentType | null {
	const posibles = COUNTER_TYPES.filter(
		(tipo) => enabled.includes(tipo) && cabeConElReceptor(tipo, hasReceiver, foreign)
	);
	if (chosen && posibles.includes(chosen)) return chosen;
	const sugerido = suggestedDocumentType(hasReceiver, enabled, foreign);
	return posibles.includes(sugerido) ? sugerido : null;
}

/**
 * El comprobante de una compra, o nulo si no lleva (RF-79, RN-87, T-728).
 *
 * La factura electrónica de compra nace de comprarle a quien no es
 * contribuyente —identificación `06`—: la emite el negocio como comprador,
 * porque el vendedor no puede. A un proveedor inscrito no se le emite nada, y
 * con la facturación o el tipo apagados la compra entra igual, sin comprobante.
 * Misma regla que `purchase_document_type` en el servidor; acá la usa el
 * simulado.
 */
/**
 * El no contribuyente (`identification.NON_TAXPAYER`). Se repite el literal y no
 * se importa: `identification` importa `settings`, y `settings` importa este
 * módulo para la configuración de fábrica. Importarlo de vuelta sería un ciclo
 * que deja `DEFAULT_ENABLED` sin definir en medio de la carga.
 */
const NON_TAXPAYER = '06';

export function purchaseDocumentType(
	einvoicing: boolean,
	enabled: readonly string[],
	supplierIdentificationType: string | null | undefined
): string | null {
	if (!einvoicing || supplierIdentificationType !== NON_TAXPAYER) return null;
	return enabled.includes(PURCHASE_INVOICE) ? PURCHASE_INVOICE : null;
}

/** Por qué no sale el comprobante pedido. Código y no frase: esto es dominio. */
export type DocumentTypeRejection =
	| 'invalid_sale_document_type'
	| 'document_type_not_enabled'
	| 'invoice_needs_receiver'
	| 'invoice_needs_resident'
	| 'export_needs_receiver'
	| 'export_needs_foreign_receiver';

/**
 * El tipo con el que va a quedar la venta, con la misma regla y el mismo orden
 * que `document_type_for` del servidor. Nulo es «sin facturación electrónica».
 * `foreign` es si el cliente es del extranjero; sin cliente no significa nada.
 */
export function documentTypeFor(
	requested: string | null,
	opciones: {
		einvoicing: boolean;
		enabled: readonly string[];
		hasReceiver: boolean;
		foreign?: boolean;
	}
): { ok: true; type: CounterDocumentType | null } | { ok: false; code: DocumentTypeRejection } {
	if (requested !== null && !isCounterDocumentType(requested)) {
		return { ok: false, code: 'invalid_sale_document_type' };
	}
	if (!opciones.einvoicing) return { ok: true, type: null };
	const foreign = opciones.foreign ?? false;
	let tipo: CounterDocumentType;
	if (requested === null) {
		tipo = suggestedDocumentType(opciones.hasReceiver, opciones.enabled, foreign);
	} else if (!opciones.enabled.includes(requested)) {
		return { ok: false, code: 'document_type_not_enabled' };
	} else {
		tipo = requested;
	}
	if (tipo === INVOICE) {
		if (!opciones.hasReceiver) return { ok: false, code: 'invoice_needs_receiver' };
		if (foreign) return { ok: false, code: 'invoice_needs_resident' };
	}
	if (tipo === EXPORT_INVOICE) {
		if (!opciones.hasReceiver) return { ok: false, code: 'export_needs_receiver' };
		if (!foreign) return { ok: false, code: 'export_needs_foreign_receiver' };
	}
	return { ok: true, type: tipo };
}
