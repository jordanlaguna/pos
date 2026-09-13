/**
 * De código a frase.
 *
 * El dominio y la capa de aplicación devuelven **código y datos**
 * (`{ code: 'cart_out_of_stock', product: 'Arroz' }`) porque no saben en qué
 * idioma está la pantalla. Acá, que es la interfaz, se arma la oración con el
 * catálogo. Es RN-30 aplicada dentro del POS: el mismo trato que se le da al
 * backend.
 *
 * Los `switch` son exhaustivos a propósito y el `never` del final es lo que hace
 * que agregar un código nuevo al dominio **rompa `npm run check`** hasta que
 * tenga su mensaje. Sin eso, un caso sin traducir aparecería en la pantalla del
 * cajero como una cadena vacía.
 */

import type { CheckoutRejection } from '$lib/application/checkout';
import type { Errors, ValidationError } from '$lib/application/validation';
import type { CartRejection } from '$lib/domain/cart';
import type { ImportFailure, ImportNote, ModuleName, Subscription } from '$lib/domain/types';
import { m } from '$lib/paraglide/messages.js';
import { formatDate } from './format';

/** Nunca debería alcanzarse: existe para que el compilador vigile los `switch`. */
function faltaMensaje(caso: never): string {
	throw new Error(`Falta el mensaje del código ${JSON.stringify(caso)}`);
}

export function cartMessage(r: CartRejection): string {
	switch (r.code) {
		case 'cart_quantity_not_positive':
			return m.cart_quantity_not_positive();
		case 'cart_out_of_stock':
			return m.cart_out_of_stock({ product: r.product });
		case 'cart_reserved_elsewhere':
			return m.cart_reserved_elsewhere({
				free: r.free,
				product: r.product,
				reserved: r.reserved
			});
		case 'cart_only_units':
			return m.cart_only_units({ stock: r.stock, product: r.product });
		case 'cart_only_units_with_current':
			return m.cart_only_units_with_current({
				stock: r.stock,
				product: r.product,
				current: r.current
			});
		case 'cart_only_free_units':
			return m.cart_only_free_units({ free: r.free, product: r.product });
		case 'cart_max_tickets':
			return m.cart_max_tickets({ max: r.max });
		case 'cart_line_not_found':
			return m.cart_line_not_found();
		default:
			return faltaMensaje(r);
	}
}

export function checkoutMessage(r: CheckoutRejection): string {
	switch (r.code) {
		case 'checkout_no_lines':
			return m.checkout_no_lines();
		case 'checkout_bad_sale_number':
			return m.checkout_bad_sale_number();
		case 'checkout_product_gone':
			return m.checkout_product_gone();
		case 'checkout_bad_quantity':
			return m.checkout_bad_quantity({ product: r.product });
		case 'checkout_insufficient_stock':
			return m.checkout_insufficient_stock({
				product: r.product,
				available: r.available
			});
		case 'checkout_cash_short':
			return m.checkout_cash_short();
		default:
			return faltaMensaje(r);
	}
}

export function validationMessage(e: ValidationError): string {
	switch (e.code) {
		case 'validation_required':
			return m.validation_required({ field: e.label.text, concord: e.label.concord });
		case 'validation_not_allowed':
			return m.validation_not_allowed({ field: e.label.text, concord: e.label.concord });
		case 'validation_too_short':
			return m.validation_too_short({ field: e.label.text, min: e.min, concord: e.label.concord });
		case 'validation_too_long':
			return m.validation_too_long({ field: e.label.text, max: e.max, concord: e.label.concord });
		case 'validation_not_a_number':
			return m.validation_not_a_number({ field: e.label.text, concord: e.label.concord });
		case 'validation_not_an_integer':
			return m.validation_not_an_integer({ field: e.label.text, concord: e.label.concord });
		case 'validation_below_min':
			return m.validation_below_min({ field: e.label.text, min: e.min, concord: e.label.concord });
		case 'validation_above_max':
			return m.validation_above_max({ field: e.label.text, max: e.max, concord: e.label.concord });
		case 'validation_bad_email':
			return m.validation_bad_email({ field: e.label.text, concord: e.label.concord });
		case 'validation_digits_only':
			return m.validation_digits_only({ field: e.label.text, concord: e.label.concord });
		case 'validation_digit_length':
			return m.validation_digit_length({ field: e.label.text, min: e.min, max: e.max, concord: e.label.concord });
		case 'validation_bad_date':
			return m.validation_bad_date({ field: e.label.text, concord: e.label.concord });
		case 'validation_future_date':
			return m.validation_future_date({ field: e.label.text, concord: e.label.concord });
		case 'validation_text':
			// Ya viene resuelto por quien lo puso: un error del backend, o una regla
			// propia de la pantalla.
			return e.text;
		default:
			return faltaMensaje(e);
	}
}

/**
 * Los errores del validador, ya en frases, tal como los espera la pantalla.
 *
 * Se llama justo antes del `fail()`. Así el contrato con los componentes sigue
 * siendo `Record<string, string>` y las ocho pantallas que muestran
 * `form.errors` no se tocaron al hacer T-815.
 */
export function validationErrors(errors: Errors): Record<string, string> {
	return Object.fromEntries(
		Object.entries(errors).map(([campo, error]) => [campo, validationMessage(error)])
	);
}

/** El primer error, que es el que explica la causa. Para el aviso general. */
export function firstError(errors: Errors): string {
	const primero = Object.values(errors)[0];
	return primero ? validationMessage(primero) : '';
}

// ----------------------------------------------------- los lectores de archivos

/**
 * Lo que dice un lector de planilla o de XML, en frase.
 *
 * Sirve para las dos cosas que devuelven: el aviso de una línea (`issue`) y los
 * avisos del archivo entero (`warnings`). Los dos son `ImportNote`.
 */
export function importMessage(n: ImportNote): string {
	switch (n.code) {
		case 'import_lines_need_review':
			return m.import_lines_need_review({ count: n.count });
		case 'import_no_cost_column':
			return m.import_no_cost_column();
		case 'import_bad_quantity':
			return m.import_bad_quantity();
		case 'import_bad_quantity_in_row':
			return m.import_bad_quantity_in_row({ row: n.row });
		case 'import_fractional_quantity':
			return m.import_fractional_quantity({ quantity: n.quantity });
		case 'import_fractional_quantity_in_row':
			return m.import_fractional_quantity_in_row({ quantity: n.quantity, row: n.row });
		default:
			return faltaMensaje(n);
	}
}

/** Lo que impidió leer el archivo del todo. */
export function importFailureMessage(f: ImportFailure): string {
	switch (f.code) {
		case 'import_csv_unreadable':
			return m.import_csv_unreadable();
		case 'import_xlsx_unreadable':
			return m.import_xlsx_unreadable();
		case 'import_sheet_empty':
			return m.import_sheet_empty();
		case 'import_no_quantity_column':
			return m.import_no_quantity_column();
		case 'import_no_identifier_column':
			return m.import_no_identifier_column();
		case 'import_no_data_rows':
			return m.import_no_data_rows();
		case 'import_not_an_invoice':
			return m.import_not_an_invoice();
		case 'import_xml_unreadable':
			return m.import_xml_unreadable();
		case 'import_invoice_without_lines':
			return m.import_invoice_without_lines();
		default:
			return faltaMensaje(f);
	}
}

// ------------------------------------------------------------------ el backend

/**
 * Los códigos que puede traer un fallo del API.
 *
 * Es el contrato con `backend/app/utils/api_errors.py` y tiene que decir lo
 * mismo. Lo comprueban dos cosas: `messages.test.ts` compara esta lista con la
 * del backend —leyendo el archivo— y el `never` del final de `frase()` impide
 * compilar mientras un código no tenga su caso.
 *
 * Los cuatro primeros son del POS y no del backend: los produce el cliente HTTP
 * cuando el backend no contesta, o contesta algo que no entendemos.
 *
 * Es un arreglo y no una unión escrita a mano porque hace falta en ejecución: un
 * backend más nuevo que este POS puede mandar un código que acá todavía no
 * existe, y hay que reconocerlo para responder con el aviso genérico en vez de
 * caer en un `switch` que no lo tiene.
 */
export const API_CODES = [
	// del cliente HTTP del POS
	'unreachable',
	'timeout',
	'unexpected',
	'invalid_request',
	// sesión
	'unauthorized',
	'no_company_in_token',
	'membership_inactive',
	'admin_only',
	'invalid_credentials',
	'company_blocked',
	'membership_not_found',
	'invalid_invitation_action',
	'invitation_already_accepted',
	// soporte y suscripción (F3)
	'support_only',
	'subscription_read_only',
	'impersonation_read_only',
	'plan_limit_reached',
	'company_not_found',
	'plan_not_found',
	'company_already_exists',
	'invalid_company_state',
	'support_cannot_be_member',
	// módulos por plan (F10)
	'module_not_in_plan',
	// caja
	'cash_read_not_yours',
	'cash_open_not_yours',
	'cash_movement_not_yours',
	'cash_close_not_yours',
	'cash_session_not_found',
	'cash_session_not_yours',
	'cash_already_open',
	'cash_opening_negative',
	'cash_no_open_session',
	'cash_insufficient',
	'cash_invalid_movement_type',
	'cash_amount_not_positive',
	'cash_missing_reason',
	'cash_counted_negative',
	// ventas
	'duplicate_sale_number',
	'empty_sale',
	'invalid_sale_line',
	'invalid_sale_payment_method',
	'product_not_found',
	'product_without_price',
	'insufficient_stock',
	'totals_mismatch',
	'insufficient_payment',
	'sale_not_found',
	'sale_details_not_found',
	'sale_failed',
	// devoluciones
	'empty_return',
	'missing_return_reason',
	'not_sold_in_this_sale',
	'invalid_return_quantity',
	'excessive_return',
	'return_not_found',
	'return_failed',
	// entradas de mercadería
	'empty_entry',
	'invalid_entry_source',
	'duplicate_document',
	'invalid_entry_line',
	'entry_product_not_found',
	'entry_missing_barcode',
	'barcode_taken',
	'entry_line_without_product',
	'entry_not_found',
	'entry_already_cancelled',
	'entry_cannot_cancel',
	'entry_failed',
	'entry_cancel_failed',
	// catálogo
	'product_has_sales',
	'category_name_taken',
	// categorías de dos niveles (F4)
	'category_not_found',
	'category_too_deep',
	'category_has_children',
	'category_self_parent',
	'category_in_use',
	'category_needs_subcategory',
	'category_inactive',
	'category_reorder_incomplete',
	// CABYS
	'cabys_invalid_code',
	'cabys_not_found',
	// personas
	'person_identification_taken',
	'email_taken',
	'person_not_found',
	'person_not_yours',
	'client_identification_taken',
	'client_not_found',
	// compras (F10)
	'supplier_not_found',
	'supplier_inactive',
	'supplier_identification_taken',
	'invalid_identification_type',
	'identification_required',
	// abonos a proveedor (T-1010)
	'payment_exceeds_balance',
	'payment_not_positive',
	'invalid_payment_method',
	'purchase_cancelled',
	'payment_failed',
	'purchase_has_payments',
	'void_reason_required',
	'client_update_failed',
	'invalid_role',
	'account_not_found',
	'user_not_found',
	'user_not_yours',
	'last_admin',
	// configuración
	'unsupported_locale',
	'settings_too_large',
	'tax_rate_not_a_number',
	'tax_rate_out_of_range',
	'settings_save_failed',
	// contabilidad (F11)
	'accounting_already_active',
	'invalid_opening_balance',
	'accounting_failed'
] as const;

export type ApiCode = (typeof API_CODES)[number];

/** Los cuatro que produce el POS. El backend no los manda nunca. */
export const POS_CODES = ['unreachable', 'timeout', 'unexpected', 'invalid_request'] as const;

const CONOCIDOS: ReadonlySet<string> = new Set<string>(API_CODES);

/**
 * Un fallo del API visto desde acá.
 *
 * Se declara por estructura y no importando `ApiError`: `$lib/server` no puede
 * entrar en código de cliente, y este módulo lo usan los componentes.
 */
interface Failure {
	readonly code: string;
	readonly data: Readonly<Record<string, unknown>>;
}

function comoFallo(error: unknown): Failure {
	if (error && typeof error === 'object') {
		const posible = error as Partial<Failure>;
		if (typeof posible.code === 'string' && posible.code) {
			return { code: posible.code, data: posible.data ?? {} };
		}
	}
	return { code: 'unexpected', data: {} };
}

const texto = (valor: unknown): string => (typeof valor === 'string' ? valor : '');

const numero = (valor: unknown): number => {
	const n = typeof valor === 'number' ? valor : Number(valor);
	return Number.isFinite(n) ? n : 0;
};

/**
 * Cómo se nombra el producto del que habla el error.
 *
 * El backend manda el nombre cuando puede leerlo y solo el id cuando la fila ya
 * no está. Un hueco en blanco en medio de la frase es peor que un «#47».
 */
function producto(d: Failure['data']): string {
	const nombre = texto(d.product);
	if (nombre) return nombre;
	if (d.product_id !== null && d.product_id !== undefined) {
		return m.api_product_by_id({ product_id: String(d.product_id) });
	}
	return m.api_product_unknown();
}

/** El campo del cotejo de totales, dicho como palabra. */
function campo(valor: unknown): string {
	switch (texto(valor)) {
		case 'subtotal':
			return m.api_field_subtotal();
		case 'tax':
			return m.api_field_tax();
		default:
			return m.api_field_total();
	}
}

/**
 * De un fallo del backend a la frase que ve una persona (RN-30).
 *
 * Acepta cualquier cosa atrapada en un `catch` porque es lo que hay en un
 * `+page.server.ts`: puede ser un `ApiError`, puede ser un `TypeError` de una
 * línea nuestra. Lo que no tenga código sale como el aviso genérico.
 *
 * Las cifras van sin formatear a propósito. `formatMoney` necesita la moneda
 * configurada, que la fija el layout al renderizar, y una acción corre antes de
 * eso: pondría el símbolo equivocado. Se resuelve con T-806.
 */
export function apiMessage(error: unknown): string {
	const fallo = comoFallo(error);
	if (!esConocido(fallo.code)) {
		// Un backend más nuevo que este POS. Se registra el código —hace falta
		// para saber qué agregar— y la pantalla dice lo genérico.
		console.error('[ventasys] el backend devolvió un código sin frase:', fallo.code);
		return m.error_unexpected_backend();
	}
	return frase(fallo.code, fallo.data);
}

function esConocido(code: string): code is ApiCode {
	return CONOCIDOS.has(code);
}

/** El `switch` de verdad. Recibe el código ya reconocido, nunca una cadena suelta. */
function frase(code: ApiCode, d: Failure['data']): string {
	switch (code) {
		// ------------------------------------------------------ el cliente HTTP
		case 'unreachable':
			return m.api_unreachable();
		case 'timeout':
			return m.api_timeout();
		case 'unexpected':
			return m.api_unexpected();
		case 'invalid_request':
			return m.api_invalid_request();

		// ------------------------------------------------------------- sesión
		case 'unauthorized':
			return m.api_unauthorized();
		case 'no_company_in_token':
			return m.api_no_company_in_token();
		case 'membership_inactive':
			return m.api_membership_inactive();
		case 'admin_only':
			return m.api_admin_only();
		case 'invalid_credentials':
			return m.api_invalid_credentials();
		case 'company_blocked':
			// `state` es el estado de la suscripción tal como está en la base: un
			// valor, no un código. Son las mismas frases de la pantalla de
			// selección de compañía, y por eso se reusan sus claves.
			switch (texto(d.state)) {
				case 'suspendida':
					return m.company_reason_suspended();
				case 'cancelada':
					return m.company_reason_cancelled();
				default:
					return m.company_reason_unavailable();
			}
		case 'membership_not_found':
			return m.api_membership_not_found();
		case 'invalid_invitation_action':
			return m.api_invalid_invitation_action();
		case 'invitation_already_accepted':
			return m.api_invitation_already_accepted();

		// ------------------------------------------- soporte y suscripción (F3)
		case 'support_only':
			return m.api_support_only();
		case 'subscription_read_only':
			// `state` es el estado **efectivo** de la suscripción, y la frase cambia
			// con él: al que venció hay que decirle que pague y al suspendido, que
			// llame. Un solo texto para los tres no le sirve a ninguno.
			return m.api_subscription_read_only({ state: texto(d.state) });
		case 'impersonation_read_only':
			return m.api_impersonation_read_only();
		case 'plan_limit_reached':
			return m.api_plan_limit_reached({
				resource: texto(d.resource),
				current: numero(d.current),
				max: numero(d.max)
			});
		case 'company_not_found':
			return m.api_company_not_found();
		case 'plan_not_found':
			return m.api_plan_not_found();
		case 'company_already_exists':
			return m.api_company_already_exists({
				afiliado: numero(d.afiliado),
				compania: numero(d.compania)
			});
		case 'invalid_company_state':
			return m.api_invalid_company_state({ state: texto(d.state) });
		case 'support_cannot_be_member':
			return m.api_support_cannot_be_member({ email: texto(d.email) });
		case 'module_not_in_plan':
			// El nombre del módulo viaja en inglés —es el de la columna— y la
			// frase lo nombra en el idioma de quien mira, con una variante por
			// módulo. Interpolarlo daría «Su plan no incluye accounting».
			return m.api_module_not_in_plan({ module: texto(d.module) });

		// --------------------------------------------------------------- caja
		case 'cash_read_not_yours':
			return m.api_cash_read_not_yours();
		case 'cash_open_not_yours':
			return m.api_cash_open_not_yours();
		case 'cash_movement_not_yours':
			return m.api_cash_movement_not_yours();
		case 'cash_close_not_yours':
			return m.api_cash_close_not_yours();
		case 'cash_session_not_found':
			return m.api_cash_session_not_found();
		case 'cash_session_not_yours':
			return m.api_cash_session_not_yours();
		case 'cash_already_open':
			return m.api_cash_already_open();
		case 'cash_opening_negative':
			return m.api_cash_opening_negative();
		case 'cash_no_open_session':
			return m.api_cash_no_open_session();
		case 'cash_insufficient':
			return m.api_cash_insufficient({ available: numero(d.available) });
		case 'cash_invalid_movement_type':
			return m.api_cash_invalid_movement_type();
		case 'cash_amount_not_positive':
			return m.api_cash_amount_not_positive();
		case 'cash_missing_reason':
			return m.api_cash_missing_reason();
		case 'cash_counted_negative':
			return m.api_cash_counted_negative();

		// ------------------------------------------------------------ ventas
		case 'duplicate_sale_number':
			return m.api_duplicate_sale_number({ sale_number: texto(d.sale_number) });
		case 'empty_sale':
			return m.api_empty_sale();
		case 'invalid_sale_line':
			return m.api_invalid_sale_line({ product: producto(d) });
		case 'invalid_sale_payment_method':
			return m.api_invalid_sale_payment_method({ method: texto(d.method) });
		case 'product_not_found':
			return m.api_product_not_found({ product: producto(d) });
		case 'product_without_price':
			return m.api_product_without_price({ product: producto(d) });
		case 'insufficient_stock':
			return m.api_insufficient_stock({
				product: producto(d),
				available: numero(d.available),
				requested: numero(d.requested)
			});
		case 'totals_mismatch':
			return m.api_totals_mismatch({
				field: campo(d.field),
				declared: numero(d.declared),
				computed: numero(d.computed)
			});
		case 'insufficient_payment':
			return m.api_insufficient_payment({
				received: numero(d.received),
				total: numero(d.total)
			});
		case 'sale_not_found':
			return m.api_sale_not_found();
		case 'sale_details_not_found':
			return m.api_sale_details_not_found();
		case 'sale_failed':
			return m.api_sale_failed();

		// ------------------------------------------------------ devoluciones
		case 'empty_return':
			return m.api_empty_return();
		case 'missing_return_reason':
			return m.api_missing_return_reason();
		case 'not_sold_in_this_sale':
			return m.api_not_sold_in_this_sale({ product: producto(d) });
		case 'invalid_return_quantity':
			return m.api_invalid_return_quantity({ product: producto(d) });
		case 'excessive_return':
			return m.api_excessive_return({
				product: producto(d),
				remaining: numero(d.remaining)
			});
		case 'return_not_found':
			return m.api_return_not_found();
		case 'return_failed':
			return m.api_return_failed();

		// ---------------------------------------------------------- entradas
		case 'empty_entry':
			return m.api_empty_entry();
		case 'invalid_entry_source':
			return m.api_invalid_entry_source();
		case 'duplicate_document':
			return m.api_duplicate_document({
				document_number: texto(d.document_number),
				loaded_at: formatDate(texto(d.loaded_at))
			});
		case 'invalid_entry_line':
			return m.api_invalid_entry_line({ line: numero(d.line) });
		case 'entry_product_not_found':
			return m.api_entry_product_not_found({ product: producto(d) });
		case 'entry_missing_barcode':
			return m.api_entry_missing_barcode({ line: numero(d.line) });
		case 'barcode_taken':
			return m.api_barcode_taken({ barcode: texto(d.barcode) });
		case 'entry_line_without_product':
			return m.api_entry_line_without_product({ line: numero(d.line) });
		case 'entry_not_found':
			return m.api_entry_not_found();
		case 'entry_already_cancelled':
			return m.api_entry_already_cancelled();
		case 'entry_cannot_cancel':
			return m.api_entry_cannot_cancel({
				product: producto(d),
				available: numero(d.available),
				added: numero(d.added)
			});
		case 'entry_failed':
			return m.api_entry_failed();
		case 'entry_cancel_failed':
			return m.api_entry_cancel_failed();

		// ---------------------------------------------------------- catálogo
		case 'product_has_sales':
			return m.api_product_has_sales();
		case 'category_name_taken':
			return m.api_category_name_taken({ name: texto(d.name) });

		// ------------------------------------------ categorías de dos niveles
		case 'category_not_found':
			return m.api_category_not_found();
		case 'category_too_deep':
			return m.api_category_too_deep();
		case 'category_has_children':
			return m.api_category_has_children({ children: numero(d.children) });
		case 'category_self_parent':
			return m.api_category_self_parent();
		// El backend manda las dos cuentas y la frase nombra una: la de los
		// productos manda cuando hay, porque moverlos es lo que hay que hacer
		// primero. Con las dos en la misma oración harían falta cuatro
		// variantes de plural por idioma para decir lo mismo.
		case 'category_in_use':
			return numero(d.products) > 0
				? m.api_category_in_use_products({ products: numero(d.products) })
				: m.api_category_in_use_children({ children: numero(d.children) });
		case 'category_needs_subcategory':
			return m.api_category_needs_subcategory({
				category: texto(d.name),
				children: numero(d.children)
			});
		case 'category_inactive':
			return m.api_category_inactive({ category: texto(d.name) });
		case 'category_reorder_incomplete':
			return m.api_category_reorder_incomplete();

		// ------------------------------------------------------------ CABYS
		case 'cabys_invalid_code':
			return m.api_cabys_invalid_code({ value: texto(d.value) });
		case 'cabys_not_found':
			return m.api_cabys_not_found({ code: texto(d.code) });

		// ---------------------------------------------------------- personas
		case 'person_identification_taken':
			return m.api_person_identification_taken();
		case 'email_taken':
			return m.api_email_taken();
		case 'person_not_found':
			return m.api_person_not_found();
		case 'person_not_yours':
			return m.api_person_not_yours();
		case 'client_identification_taken':
			return m.api_client_identification_taken();
		case 'client_not_found':
			return m.api_client_not_found();

		// ------------------------------------------------------------ compras
		case 'supplier_not_found':
			return m.api_supplier_not_found();
		case 'supplier_inactive':
			return m.api_supplier_inactive({ name: texto(d.name) });
		case 'supplier_identification_taken':
			// Trae de quién es ya: sin el nombre, la frase manda a buscar en una
			// lista de proveedores el que tiene esa cédula.
			return m.api_supplier_identification_taken({
				identification: texto(d.identification),
				name: texto(d.name)
			});
		case 'invalid_identification_type':
			return m.api_invalid_identification_type({
				identification_type: texto(d.identification_type)
			});
		case 'identification_required':
			return m.api_identification_required();
		case 'payment_exceeds_balance':
			// Los dos montos, para que la frase diga cuánto se debe de verdad:
			// sin el saldo, quien corrige el dedo de más no sabe a qué corregirlo.
			return m.api_payment_exceeds_balance({
				balance: numero(d.balance),
				requested: numero(d.requested)
			});
		case 'payment_not_positive':
			return m.api_payment_not_positive();
		case 'invalid_payment_method':
			return m.api_invalid_payment_method();
		case 'purchase_cancelled':
			return m.api_purchase_cancelled();
		case 'payment_failed':
			return m.api_payment_failed();
		case 'purchase_has_payments':
			// Cuántos: deshacer uno o siete abonos no es la misma tarea.
			return m.api_purchase_has_payments({ payments: numero(d.payments) });
		case 'void_reason_required':
			return m.api_void_reason_required();

		case 'client_update_failed':
			return m.api_client_update_failed();
		case 'invalid_role':
			return m.api_invalid_role();
		case 'account_not_found':
			return m.api_account_not_found();
		case 'user_not_found':
			return m.api_user_not_found();
		case 'user_not_yours':
			return m.api_user_not_yours();
		case 'last_admin':
			return m.api_last_admin();

		// ----------------------------------------------------- configuración
		case 'unsupported_locale':
			return m.api_unsupported_locale({ locale: texto(d.locale) });
		case 'settings_too_large':
			return m.api_settings_too_large();
		case 'tax_rate_not_a_number':
			return m.api_tax_rate_not_a_number();
		case 'tax_rate_out_of_range':
			return m.api_tax_rate_out_of_range();
		case 'settings_save_failed':
			return m.api_settings_save_failed();

		// --------------------------------------------------- contabilidad
		case 'accounting_already_active':
			return m.api_accounting_already_active();
		case 'invalid_opening_balance':
			return m.api_invalid_opening_balance({
				debits: texto(d.debits),
				credits: texto(d.credits)
			});
		case 'accounting_failed':
			return m.api_accounting_failed();
		default:
			// Acá `code` ya es `never`: si falta un caso, esto no compila. Es lo
			// único que impide que un código nuevo salga en blanco en la pantalla.
			return faltaMensaje(code);
	}
}

/**
 * Rótulo de un rol.
 *
 * Igual que el método de pago: `'admin'` y `'cajero'` son los valores que viven
 * en `user_companies.role` y con los que se compara el permiso. No se traducen;
 * se traduce cómo se muestran.
 */
export function roleLabel(role: string): string {
	switch (role) {
		case 'admin':
			return m.role_admin();
		case 'cajero':
			return m.role_cashier();
		default:
			return role;
	}
}

/** El mismo rótulo cuando va dentro de una frase: «entrar como cajero». */
export function roleLabelLower(role: string): string {
	switch (role) {
		case 'admin':
			return m.role_admin_lower();
		case 'cajero':
			return m.role_cashier_lower();
		default:
			return role;
	}
}

/**
 * Rótulo de un método de pago.
 *
 * El **valor** (`'Efectivo'`) no se traduce nunca: es lo que se guarda en
 * `sales.payment_method` y contra lo que se compara en las plantillas de
 * documento y en los reportes. Traducirlo sería corromper datos. Lo que se
 * traduce es cómo se muestra.
 */
export function paymentLabel(method: string): string {
	switch (method) {
		case 'Efectivo':
			return m.payment_cash();
		case 'Tarjeta de crédito':
			return m.payment_credit_card();
		case 'Transferencia bancaria':
			return m.payment_bank_transfer();
		case 'Pago móvil':
			return m.payment_mobile();
		default:
			// Un método que llegue de la base sin rótulo se muestra tal cual, que es
			// mejor que dejar el hueco en blanco en la pantalla de cobro.
			return method;
	}
}

// ---------------------------------------------- soporte y suscripción (F3)

/**
 * Cómo se llama un estado de suscripción en pantalla.
 *
 * El **valor** (`'activa'`) no se traduce: es lo que guarda `companies.estado` y
 * lo que se manda al cambiarlo. Lo que se traduce es cómo se muestra, igual que
 * con los métodos de pago. Las cinco palabras son las de la pantalla de
 * selección de compañía, y se reusan sus claves: tenerlas dos veces es tenerlas
 * distintas.
 */
export function companyStateLabel(state: string): string {
	switch (state) {
		case 'prueba':
			return m.company_status_trial();
		case 'activa':
			return m.company_status_current();
		case 'vencida':
			return m.company_status_overdue();
		case 'suspendida':
			return m.company_status_suspended();
		case 'cancelada':
			return m.company_status_cancelled();
		default:
			// Un estado que llegue de la base sin rótulo se muestra tal cual. En el
			// panel de soporte eso es información: significa que alguien escribió
			// algo raro en esa fila, y el sistema lo trata como bloqueado.
			return state;
	}
}

/**
 * El nombre de un módulo, para el panel y la navegación (RF-39, RF-40).
 *
 * El backend lo manda en inglés —es el nombre de la columna— y acá se vuelve el
 * de la pantalla. `never` en el `default` es lo que hace que agregar un módulo
 * a `MODULES` sin su rótulo **no compile**, en vez de sacar «payroll» en medio
 * de una frase en español.
 */
export function moduleLabel(module: ModuleName): string {
	switch (module) {
		case 'purchases':
			return m.module_purchases();
		case 'accounting':
			return m.module_accounting();
		case 'payroll':
			return m.module_payroll();
		default: {
			const nunca: never = module;
			return nunca;
		}
	}
}

/**
 * El aviso de suscripción que ve el cliente (RF-11, T-308).
 *
 * Recibe el estado ya evaluado por el backend —los días, la gracia y el código
 * del aviso— y devuelve la frase. Nulo cuando no hay nada que decir: una
 * suscripción al día y con el vencimiento lejos no necesita un aviso, y un aviso
 * permanente que no dice nada es un aviso que nadie lee.
 */
export function subscriptionNotice(s: Subscription | null | undefined): string | null {
	if (!s?.aviso) return null;

	switch (s.aviso) {
		case 'en_prueba':
			return s.vence_el
				? m.subscription_trial_until({ fecha: formatDate(s.vence_el) })
				: m.subscription_trial();
		case 'vence_pronto':
			// `dias` viene del backend y es 0 el día del vencimiento. «Vence en 0
			// días» es una frase que nadie escribiría a mano.
			if (s.dias === null || s.dias <= 0) return m.subscription_due_today();
			return m.subscription_due_in({ dias: s.dias });
		case 'en_gracia':
			return m.subscription_grace({ dias: s.gracia });
		case 'solo_lectura':
			return m.subscription_read_only();
		case 'suspendida':
			return m.subscription_suspended();
		case 'cancelada':
			return m.subscription_cancelled();
		default:
			return faltaMensaje(s.aviso);
	}
}

/**
 * Qué dice una línea de la bitácora (RF-9).
 *
 * La acción llega como el código que escribió el backend (`alta_compania`). Una
 * que todavía no tenga rótulo se muestra cruda: en una bitácora, un código que
 * no se entiende sigue siendo información, y un hueco en blanco no.
 */
export function auditActionLabel(accion: string): string {
	switch (accion) {
		case 'login':
			return m.admin_action_login();
		case 'login_soporte':
			return m.admin_action_login_soporte();
		case 'elegir_compania':
			return m.admin_action_elegir_compania();
		case 'invitacion_aceptar':
			return m.admin_action_invitacion_aceptar();
		case 'invitacion_rechazar':
			return m.admin_action_invitacion_rechazar();
		case 'idioma_usuario':
			return m.admin_action_idioma_usuario();
		case 'idioma_compania':
			return m.admin_action_idioma_compania();
		case 'alta_compania':
			return m.admin_action_alta_compania();
		case 'suscripcion':
			return m.admin_action_suscripcion();
		case 'plan_modulos':
			return m.admin_action_plan_modulos();
		case 'entrar_como':
			return m.admin_action_entrar_como();
		default:
			return accion;
	}
}
