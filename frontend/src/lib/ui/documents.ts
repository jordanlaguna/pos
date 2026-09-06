/**
 * Los rótulos del documento impreso, en el idioma del documento (RN-29, T-811).
 *
 * El documento no habla el idioma de la pantalla: la factura es para el cliente
 * y para Hacienda, así que una compañía costarricense la emite en español aunque
 * su cajero tenga el POS en portugués. Son dos ajustes distintos y el del
 * documento vive en Configuración.
 *
 * **Por eso las plantillas no importan el catálogo.** Reciben este diccionario ya
 * resuelto y no tienen forma de pedir un mensaje «a secas»: si lo hicieran,
 * saldría en el idioma de la sesión y nadie lo notaría hasta que un cajero
 * portugués imprimiera una factura costarricense. Lo cuida una prueba en
 * `loose-text.test.ts` —ninguna plantilla importa `$lib/paraglide`—, porque la
 * regla es fácil de romper sin darse cuenta: basta escribir `m.doc_total()`.
 */

import type { IssuerLine } from '$lib/domain/documents';
import type { Settings } from '$lib/domain/settings';
import { documentKind } from '$lib/domain/documents';
import { m } from '$lib/paraglide/messages.js';
import { baseLocale, isLocale, type Locale } from '$lib/paraglide/runtime.js';

/**
 * Idioma en el que se emite el documento.
 *
 * Se recibe como texto —viene de una columna de la base— y se estrecha acá con
 * `isLocale`. **Sin lanzar**: un `document_locale` con basura dejaría la pantalla
 * de la factura en blanco, y una factura en el idioma base es infinitamente
 * mejor que una factura que no se puede imprimir. Que el valor sea imposible ya
 * lo cuidan el backend —que rechaza lo que no tiene catálogo— y la columna.
 */
function comoLocale(valor: string): Locale {
	return isLocale(valor) ? valor : baseLocale;
}

/**
 * Todo el texto del documento, resuelto de una vez.
 *
 * Los que llevan datos quedan como funciones; los demás, como cadenas. Es un
 * objeto y no un montón de argumentos porque las tres plantillas usan casi las
 * mismas claves y una firma con treinta parámetros no la mantiene nadie.
 */
export function documentLabels(locale: string) {
	const o = { locale: comoLocale(locale) } as const;
	return {
		invoice: m.doc_invoice({}, o),
		einvoice: m.doc_einvoice({}, o),
		invoiceNumber: (number: string | number) => m.doc_invoice_number({ number }, o),

		issuer: m.doc_issuer({}, o),
		issuerIncomplete: m.doc_issuer_incomplete({}, o),
		issuerAddContact: m.doc_issuer_add_contact({}, o),

		client: m.doc_client({}, o),
		billTo: m.doc_bill_to({}, o),
		walkIn: m.doc_walk_in({}, o),
		walkInHint: m.doc_walk_in_hint({}, o),
		clientId: m.doc_client_id({}, o),

		/**
		 * Cédula y teléfono rotulados, sueltos.
		 *
		 * Los mismos rótulos que usa `issuerLine`, pero las facturas de página
		 * completa también los imprimen para el **cliente**, y ahí no hay línea de
		 * emisor que envolverlos.
		 */
		taxId: (id: string | number) => m.doc_tax_id({ id }, o),
		phone: (phone: string | number) => m.doc_phone({ phone }, o),

		date: m.doc_date({}, o),
		paymentMethod: m.doc_payment_method({}, o),
		payment: m.doc_payment({}, o),
		servedBy: m.doc_served_by({}, o),

		colProduct: m.doc_col_product({}, o),
		colDescription: m.doc_col_description({}, o),
		colQuantity: m.doc_col_quantity({}, o),
		colUnitPrice: m.doc_col_unit_price({}, o),
		colUnitPriceLong: m.doc_col_unit_price_long({}, o),
		colTotal: m.doc_col_total({}, o),

		noDetail: m.doc_no_detail({}, o),
		noDetailHint: (endpoint: string) => m.doc_no_detail_hint({ endpoint }, o),

		subtotal: m.doc_subtotal({}, o),

		/**
		 * El rótulo del impuesto con su tarifa: «IVA (13 %)».
		 *
		 * Recibe el nombre y ya no lo lee de `taxLabel()`, que sale del estado de
		 * módulo de `money.ts` —o sea de la configuración de la sesión que esté
		 * pintando—. Ese era un defecto que ya estaba: reimprimir una factura vieja
		 * después de cambiar el IVA mostraba el porcentaje de hoy junto al monto de
		 * entonces, y el nombre no seguía al idioma del documento (RN-29).
		 *
		 * El nombre no se traduce, se configura: puede ser IVA, ISV o lo que el
		 * país llame. Lo que aporta la clave es la forma.
		 */
		taxAtRate: (name: string, rate: string) => m.doc_tax_at_rate({ name, rate }, o),

		total: m.doc_total({}, o),
		cashReceived: m.doc_cash_received({}, o),
		change: m.doc_change({}, o),
		returned: m.doc_returned({}, o),
		returnsApplied: m.doc_returns_applied({}, o),

		notes: m.doc_notes({}, o),
		notesAndTerms: m.doc_notes_and_terms({}, o),

		/** «Factura» o «Factura electrónica», según lo configurado. */
		title: (settings: Settings) =>
			documentKind(settings) === 'einvoice' ? m.doc_einvoice({}, o) : m.doc_invoice({}, o),

		/**
		 * Una línea del emisor, con su rótulo si lo lleva.
		 *
		 * La cédula y el teléfono se imprimen rotulados —«Cédula 3-101-123456»—
		 * porque un número suelto en la cabecera de una factura no dice qué número
		 * es. La dirección, el correo y el sitio se reconocen solos.
		 */
		issuerLine: (linea: IssuerLine) => {
			switch (linea.kind) {
				case 'taxId':
					return m.doc_tax_id({ id: linea.value }, o);
				case 'phone':
					return m.doc_phone({ phone: linea.value }, o);
				default:
					return linea.value;
			}
		},

		/**
		 * El método de pago como se muestra.
		 *
		 * El valor que se guarda en `sales.payment_method` no se traduce nunca —se
		 * compara en los reportes y en las plantillas— y por eso el `switch` es
		 * sobre el texto en español, que es el dato.
		 */
		paymentName: (method: string) => {
			switch (method) {
				case 'Efectivo':
					return m.payment_cash({}, o);
				case 'Tarjeta de crédito':
					return m.payment_credit_card({}, o);
				case 'Transferencia bancaria':
					return m.payment_bank_transfer({}, o);
				case 'Pago móvil':
					return m.payment_mobile({}, o);
				default:
					return method;
			}
		}
	};
}

export type DocumentLabels = ReturnType<typeof documentLabels>;

/** Las líneas del emisor, ya en texto, en el idioma del documento. */
export function issuerText(lineas: IssuerLine[], labels: DocumentLabels): string[] {
	return lineas.map(labels.issuerLine);
}

/**
 * Los textos con los que nace el documento de una compañía nueva (T-304, RF-6).
 *
 * Nacen vacíos en el dominio a propósito —`$lib/domain/settings.ts` explica por
 * qué— y se siembran acá, que es la interfaz y sí tiene catálogo, en el momento
 * en que se conoce el idioma **del documento**: no el de la pantalla de quien da
 * de alta, ni el de la compañía, el de la factura (RN-29).
 *
 * Después son del dueño. Si los borra en Configuración, se quedan borrados: esto
 * corre una sola vez, al dar de alta, y no como respaldo del vacío.
 */
export function initialDocumentTexts(locale: string): {
	thanksMessage: string;
	legalNotice: string;
} {
	const o = { locale: comoLocale(locale) } as const;
	return {
		thanksMessage: m.doc_default_thanks({}, o),
		legalNotice: m.doc_default_legal({}, o)
	};
}
