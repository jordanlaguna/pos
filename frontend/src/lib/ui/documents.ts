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

import type { DocumentKind, IssuerLine } from '$lib/domain/documents';
import { identificationTypeName } from '$lib/domain/identification';
import { m } from '$lib/paraglide/messages.js';
import { baseLocale, isLocale, type Locale } from '$lib/paraglide/runtime.js';
import { amountInWords } from './amountInWords';

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

	/**
	 * «Factura», «Factura electrónica» o «Tiquete electrónico», según **la
	 * venta** (RN-85). Antes lo decía la configuración de hoy, y una venta de
	 * antes de activar la facturación se reimprimía como electrónica.
	 */
	const title = (kind: DocumentKind) => {
		switch (kind) {
			case 'einvoice':
				return m.doc_einvoice({}, o);
			case 'eticket':
				return m.doc_eticket({}, o);
			case 'ecredit':
				return m.doc_ecredit({}, o);
			case 'edebit':
				return m.doc_edebit({}, o);
			default:
				return m.doc_invoice({}, o);
		}
	};

	return {
		invoice: m.doc_invoice({}, o),
		einvoice: m.doc_einvoice({}, o),
		eticket: m.doc_eticket({}, o),
		title,
		/** «Tiquete electrónico 20260815143200»: el tipo y el número, juntos. */
		numbered: (kind: DocumentKind, number: string | number) =>
			m.doc_numbered({ document: title(kind), number }, o),

		/*
		 * El bloque fiscal (RN-86). La clave, el consecutivo y la actividad son
		 * datos; lo que se traduce es cómo se rotulan y las tres leyendas.
		 */
		fiscalKey: m.doc_fiscal_key({}, o),
		fiscalConsecutive: m.doc_fiscal_consecutive({}, o),
		fiscalActivity: (code: string) => m.doc_fiscal_activity({ code }, o),
		fiscalPending: m.doc_fiscal_pending({}, o),
		fiscalSandbox: m.doc_fiscal_sandbox({}, o),
		fiscalResolution: (resolution: string) => m.doc_fiscal_resolution({ resolution }, o),
		fiscalVerify: (url: string) => m.doc_fiscal_verify({ url }, o),
		/** Lo que un lector de pantalla dice del QR de la clave (T-705). */
		fiscalQr: m.doc_fiscal_qr({}, o),

		/*
		 * La referencia de una nota al comprobante que modifica (RN-89): qué es,
		 * cuál es y por qué. La fecha llega ya formateada en el idioma del
		 * documento; el motivo es el código de Hacienda y se nombra acá.
		 */
		fiscalReference: m.doc_fiscal_reference({}, o),
		referenceTo: (kind: DocumentKind, number: string, date: string) =>
			m.doc_fiscal_reference_to({ document: title(kind), number, date }, o),
		referenceReason: (code: string) => {
			switch (code) {
				case '01':
					return m.doc_reason_annul({}, o);
				case '02':
					return m.doc_reason_corrects_amount({}, o);
				case '06':
					return m.doc_reason_goods_return({}, o);
				default:
					return m.doc_reason_other({ code }, o);
			}
		},

		issuer: m.doc_issuer({}, o),
		issuerIncomplete: m.doc_issuer_incomplete({}, o),
		issuerAddContact: m.doc_issuer_add_contact({}, o),

		client: m.doc_client({}, o),
		billTo: m.doc_bill_to({}, o),
		walkIn: m.doc_walk_in({}, o),
		walkInHint: m.doc_walk_in_hint({}, o),
		clientId: m.doc_client_id({}, o),
		email: m.doc_email({}, o),

		/**
		 * Cédula y teléfono rotulados, sueltos.
		 *
		 * Los mismos rótulos que usa `issuerLine`, pero las facturas de página
		 * completa también los imprimen para el **cliente**, y ahí no hay línea de
		 * emisor que envolverlos.
		 */
		taxId: (id: string | number) => m.doc_tax_id({ id }, o),
		phone: (phone: string | number) => m.doc_phone({ phone }, o),
		/**
		 * La identificación con su tipo —«Cédula física 108840287»—, como la pide
		 * el comprobante (RN-86). Sin un tipo de Hacienda queda la «Cédula» a
		 * secas: mejor un rótulo genérico que uno equivocado.
		 */
		idTyped: (type: string | null | undefined, id: string | number) => {
			const nombre = identificationTypeName(type);
			return nombre ? m.doc_id_typed({ type: nombre, id }, o) : m.doc_tax_id({ id }, o);
		},
		/** Lo mismo como rótulo de una columna, para el tiquete: el tipo, o «Cédula». */
		idLabel: (type: string | null | undefined) =>
			identificationTypeName(type) ?? m.doc_client_id({}, o),

		date: m.doc_date({}, o),
		issueDate: m.doc_issue_date({}, o),
		/*
		 * La condición de venta, la moneda y el tipo de cambio (RN-86). La
		 * condición es un código de la nota 5 del anexo; hoy solo existe el
		 * contado, porque el POS no vende a crédito.
		 */
		saleCondition: m.doc_sale_condition({}, o),
		saleConditionName: (code: string) =>
			code === '01' ? m.doc_sale_condition_cash({}, o) : code,
		currency: m.doc_currency({}, o),
		currencyWithRate: (code: string, rate: number | null) =>
			rate === null
				? code
				: m.doc_currency_with_rate({ code, rate: rate.toFixed(2) }, o),
		paymentMethod: m.doc_payment_method({}, o),
		payment: m.doc_payment({}, o),
		servedBy: m.doc_served_by({}, o),

		colProduct: m.doc_col_product({}, o),
		colDescription: m.doc_col_description({}, o),
		colQuantity: m.doc_col_quantity({}, o),
		colUnitPrice: m.doc_col_unit_price({}, o),
		colUnitPriceLong: m.doc_col_unit_price_long({}, o),
		colTotal: m.doc_col_total({}, o),
		colCabys: m.doc_col_cabys({}, o),
		colUnit: m.doc_col_unit({}, o),
		colSubtotal: m.doc_col_subtotal({}, o),
		colTax: m.doc_col_tax({}, o),
		/** Las dos líneas chicas de cada producto en el tiquete, que no tiene columnas. */
		lineCabys: (code: string) => m.doc_line_cabys({ code }, o),
		lineQuantity: (quantity: number, unit: string, price: string) =>
			unit
				? m.doc_line_quantity({ quantity, unit, price }, o)
				: m.doc_line_quantity_no_unit({ quantity, price }, o),

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
		/** Los renglones del resumen de Hacienda (`ResumenFactura`). */
		totalSale: m.doc_total_sale({}, o),
		totalDiscounts: m.doc_total_discounts({}, o),
		totalNet: m.doc_total_net({}, o),
		totalTax: m.doc_total_tax({}, o),
		totalDocument: m.doc_total_document({}, o),
		amountInWordsLabel: m.doc_amount_in_words_label({}, o),
		/** El total en letras, en el idioma del documento. Nulo si no cabe. */
		amountInWords: (amount: number, currency: string, decimals: number) =>
			amountInWords(amount, { locale: o.locale, currency, decimals }),
		cashReceived: m.doc_cash_received({}, o),
		change: m.doc_change({}, o),
		returned: m.doc_returned({}, o),
		returnsApplied: m.doc_returns_applied({}, o),

		notes: m.doc_notes({}, o),
		notesAndTerms: m.doc_notes_and_terms({}, o),

		/**
		 * Una línea del emisor, con su rótulo si lo lleva.
		 *
		 * La cédula y el teléfono se imprimen rotulados —«Cédula 3-101-123456»—
		 * porque un número suelto en la cabecera de una factura no dice qué número
		 * es. La dirección, el correo y el sitio se reconocen solos.
		 */
		issuerLine: (linea: IssuerLine) => {
			switch (linea.kind) {
				case 'taxId': {
					// En un comprobante, con su tipo (RN-86); si no, la «Cédula» de siempre.
					const nombre = linea.idType ? identificationTypeName(linea.idType) : null;
					return nombre
						? m.doc_id_typed({ type: nombre, id: linea.value }, o)
						: m.doc_tax_id({ id: linea.value }, o);
				}
				case 'activity':
					return m.doc_fiscal_activity({ code: linea.value }, o);
				case 'location':
					// Los nombres son los de Hacienda y no se traducen; los rótulos sí.
					return linea.place
						? m.doc_issuer_location(
								{
									province: linea.place.province,
									canton: linea.place.canton,
									district: linea.place.district
								},
								o
							)
						: linea.value;
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
