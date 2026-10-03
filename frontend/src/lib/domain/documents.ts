import { readableInk, withLightness } from './color';
import { CREDIT_NOTE, DEBIT_NOTE, INVOICE, TICKET } from './documentType';
import { locationNames } from './location';
import { round2 } from './money';
import type { Settings } from './settings';
import type {
	AmountNote,
	Client,
	DocumentReference,
	EmittedDocument,
	SaleDetail,
	SaleItem,
	SaleReturn
} from './types';

/**
 * Documento de venta: lo que el cliente se lleva.
 *
 * Hay tres plantillas y todas reciben exactamente estos datos, de modo que
 * cambiar de una a otra en Configuración no cambia lo que se imprime, solo cómo
 * se ve. La que decide es `settings.document.template`.
 */
export interface DocumentProps {
	sale: SaleDetail;
	client: Client | null;
	/** Devoluciones aplicadas a esta venta; se advierten en el documento. */
	returns: SaleReturn[];
	settings: Settings;
	/** URL del logo, o null si el negocio no cargó ninguno. */
	logoUrl: string | null;
	/** Código de barras por producto, para cuando la plantilla los muestra. */
	barcodes?: Record<number, string>;
	/**
	 * Idioma en el que se emite el documento (RN-29, T-811).
	 *
	 * **No es el de la pantalla.** La factura es para el cliente y para Hacienda:
	 * una compañía costarricense la emite en español aunque su cajero tenga el POS
	 * en portugués. Sale de `companies.document_locale` y llega hasta acá porque
	 * es la plantilla la que lo necesita.
	 */
	docLocale: string;
}

/** Una fila del desglose por tarifa del documento (RF-21). */
export interface TaxLine {
	/** Entre 0 y 1: el 13 % es `0.13`. */
	rate: number;
	/** Lo que se vendió a esa tarifa. */
	base: number;
	/** Lo que se cobró de impuesto a esa tarifa. */
	tax: number;
}

/**
 * El desglose por tarifa de una venta **ya cobrada**.
 *
 * Lee lo que se guardó en cada línea, no lo recalcula: un documento reimpreso
 * dentro de cinco años tiene que decir lo que se cobró, aunque para entonces la
 * tarifa del producto sea otra o haya cambiado cómo se redondea (RN-12).
 *
 * Para las ventas **anteriores a la migración 006** las líneas no traen tarifa.
 * Ahí se devuelve un solo grupo con la del encabezado —`tax / subtotal`—, que en
 * ellas es exacta porque llevan una sola. Es el mismo respaldo que usa el
 * servidor al devolver.
 *
 * De menor a mayor tarifa, para que el documento salga siempre igual.
 */
export function taxBreakdown(sale: {
	subtotal: number;
	tax: number;
	items?: SaleItem[];
}): TaxLine[] {
	const conTarifa = (sale.items ?? []).filter((i) => i.tax_rate != null);

	if (conTarifa.length === 0) {
		const rate = sale.subtotal > 0 ? sale.tax / sale.subtotal : 0;
		return [{ rate, base: sale.subtotal, tax: sale.tax }];
	}

	const grupos = new Map<number, TaxLine>();
	for (const item of conTarifa) {
		const rate = item.tax_rate as number;
		const previo = grupos.get(rate) ?? { rate, base: 0, tax: 0 };
		grupos.set(rate, {
			rate,
			base: round2(previo.base + item.subtotal),
			tax: round2(previo.tax + (item.tax_amount ?? 0))
		});
	}
	return [...grupos.values()].sort((a, b) => a.rate - b.rate);
}

/**
 * Tonos derivados del color de marca del documento.
 *
 * Se calculan en JavaScript y no con `color-mix()` en CSS por una razón
 * práctica: esto termina en una impresora. Los valores quedan resueltos en el
 * HTML, sin depender de qué sepa interpretar el motor de impresión.
 */
export interface BrandTones {
	base: string;
	/** Texto legible encima de `base`. */
	ink: string;
	/** Versión oscura, para la segunda figura del encabezado. */
	deep: string;
	/** Fondo muy claro, para filas alternas y bloques de totales. */
	tint: string;
	/** Borde suave del mismo tono. */
	line: string;
}

export function brandTones(hex: string): BrandTones {
	return {
		base: hex,
		ink: readableInk(hex),
		deep: withLightness(hex, 0.32),
		tint: withLightness(hex, 0.96),
		line: withLightness(hex, 0.85)
	};
}

/** Qué documento es, en código. El nombre lo pone la plantilla. */
export type DocumentKind = 'invoice' | 'einvoice' | 'eticket' | 'ecredit' | 'edebit';

/** Las notas no cobran: no llevan efectivo recibido ni vuelto (RN-89). */
export function isNote(kind: DocumentKind): boolean {
	return kind === 'ecredit' || kind === 'edebit';
}

/**
 * Qué documento es, **según la venta** (RN-85).
 *
 * Antes lo decía la configuración de hoy, y eso tenía dos consecuencias: con la
 * facturación activa, la venta del cliente de contado salía «Factura
 * electrónica» —que sin receptor no puede ser—, y activarla convertía en
 * factura electrónica hasta las ventas de antes de activarla. El tipo quedó
 * guardado en la venta al cobrar, y el documento dice ese.
 */
export function documentKind(sale: { document_type?: string | null }): DocumentKind {
	switch (sale.document_type) {
		case INVOICE:
			return 'einvoice';
		case TICKET:
			return 'eticket';
		case CREDIT_NOTE:
			return 'ecredit';
		case DEBIT_NOTE:
			return 'edebit';
		default:
			return 'invoice';
	}
}

/**
 * La resolución que autoriza los comprobantes 4.4 (README de Hacienda §1 y §10).
 *
 * Es un dato y no una frase: la frase la pone el catálogo, en el idioma del
 * documento. **El texto exacto de la leyenda está por confirmar** contra la
 * resolución (T-724): el README la cita «del [fecha]» sin la fecha, y se imprime
 * sin ella.
 */
export const EINVOICE_RESOLUTION = 'MH-DGT-RES-0027-2024';

/**
 * Dónde se verifica un comprobante autorizado: el portal de TRIBU-CR. Es el que
 * imprime la factura de referencia del usuario
 * (`docs/invoice/50624092600310170293400100001010001819201163700346.pdf`), que
 * es un comprobante real aceptado.
 */
export const EINVOICE_VERIFY_URL =
	'https://ovitribucr.hacienda.go.cr/tico/comprobante/comprobante-electronico/';

/**
 * En qué punto está el comprobante, para lo que tiene que decir impreso.
 *
 * - `pending`: tiene tipo pero todavía no clave. Es lo que hay hasta T-705.
 * - `sandbox`: emitido en pruebas. No tiene efecto fiscal, y lo dice (RN-17).
 * - `authorized`: emitido en producción.
 */
export type FiscalState = 'pending' | 'sandbox' | 'authorized';

export interface FiscalBlock {
	kind: Exclude<DocumentKind, 'invoice'>;
	state: FiscalState;
	/** La clave y el consecutivo. Nulo mientras no los haya. */
	emitted: EmittedDocument | null;
	/** El comprobante que modifica, si es una nota. Va impreso siempre (RN-89). */
	reference: DocumentReference | null;
}

/**
 * Lo fiscal del documento, o nada si la venta no es un comprobante electrónico
 * (RN-86).
 *
 * Una sola función para las tres plantillas, y un solo componente que lo
 * imprime: el dueño elige la plantilla por cómo se ve, así que lo que Hacienda
 * pide no puede depender de cuál eligió.
 *
 * Sin tipo no hay bloque. Es el documento de siempre y su leyenda es la que puso
 * el dueño (T-304): repetirla desde acá sería decir lo mismo dos veces.
 */
export function fiscalBlock(sale: {
	document_type?: string | null;
	einvoice?: EmittedDocument | null;
	reference?: DocumentReference | null;
}): FiscalBlock | null {
	const kind = documentKind(sale);
	if (kind === 'invoice') return null;

	const emitted = sale.einvoice ?? null;
	const state: FiscalState =
		emitted === null ? 'pending' : emitted.environment === 'production' ? 'authorized' : 'sandbox';
	return { kind, state, emitted, reference: sale.reference ?? null };
}

/**
 * La nota de crédito de una devolución, con la forma que imprimen las plantillas
 * (RN-89, T-725).
 *
 * Las tres plantillas saben imprimir una venta, y una nota de crédito es eso
 * mismo con otro título, sin efectivo recibido y con la referencia al original.
 * Se arma acá, pura, y no en cada pantalla: la nota impresa dice lo mismo desde
 * donde se la pida.
 *
 * El número es su consecutivo desde T-704 (`documentNumber`), y el de la
 * devolución si es anterior. El medio de pago es el de la venta, que es por
 * donde se reembolsa.
 *
 * Nulo si la devolución no tiene nota: una venta que no fue comprobante no deja
 * nada que imprimir.
 */
export function creditNoteDocument(devolucion: SaleReturn): SaleDetail | null {
	if (!devolucion.document_type || !devolucion.sale_document_type) return null;
	const subtotal = devolucion.subtotal ?? devolucion.total;
	return {
		id: devolucion.id,
		sale_number: String(devolucion.id),
		created_at: devolucion.created_at,
		payment_method: devolucion.sale_payment_method ?? '',
		subtotal,
		tax: devolucion.tax ?? round2(devolucion.total - subtotal),
		total: devolucion.total,
		cash_received: 0,
		change_given: 0,
		client_id: devolucion.sale_client_id ?? null,
		user_id: devolucion.user_id,
		user_name: devolucion.user_name ?? null,
		items: devolucion.items.map((item) => ({
			id_product: item.id_product,
			name: item.name,
			quantity: item.quantity,
			price: item.price,
			subtotal: item.subtotal,
			tax_rate: item.tax_rate ?? null,
			tax_amount: item.tax_amount ?? null,
			// Los de la línea de la venta: la nota repite con qué se vendió.
			cabys_code: item.cabys_code ?? null,
			unit_of_measure: item.unit_of_measure ?? null
		})),
		document_type: devolucion.document_type,
		einvoice: devolucion.einvoice ?? null,
		reference: {
			document_type: devolucion.sale_document_type,
			// La clave del original, que es como la nota lo referencia (T-705).
			number: devolucion.sale_clave ?? devolucion.sale_number,
			date: devolucion.sale_created_at ?? '',
			code: devolucion.reference_code ?? ''
		}
	};
}

/**
 * La clave partida en sus tramos (nota 3 del anexo), para imprimirla como la
 * factura de referencia: «506 240926 003101702934 001 00001 01 0001819201
 * 163700346». País, fecha, emisor, sucursal, caja, tipo, secuencia, y la
 * situación junto con el código de seguridad.
 *
 * Se lee mejor, y en un rollo de 58 mm se parte en los espacios y no a mitad de
 * un tramo. Una clave que no son 50 dígitos vuelve entera: no se inventan cortes.
 */
export function claveGroups(clave: string): string[] {
	if (!/^\d{50}$/.test(clave)) return [clave];
	return [
		clave.slice(0, 3),
		clave.slice(3, 9),
		clave.slice(9, 21),
		clave.slice(21, 24),
		clave.slice(24, 29),
		clave.slice(29, 31),
		clave.slice(31, 41),
		clave.slice(41)
	];
}

/** El motivo de Hacienda de una nota por monto: `'02'`, corrige monto (T-726). */
export const CORRECTS_AMOUNT = '02';

/**
 * Una nota por monto, con la forma que imprimen las plantillas (RN-89, T-726).
 *
 * Como `creditNoteDocument`: las tres plantillas saben imprimir una venta, y una
 * ND o una NC por monto es eso mismo con otro título, sin efectivo recibido y con
 * la referencia al original. Cada línea es una corrección: cantidad uno y el
 * monto como precio.
 *
 * La ND lleva el medio con que se cobró. La NC sale de la gaveta, así que su
 * medio es el efectivo, sea cual sea el de la venta —igual que una devolución—.
 * El número es su consecutivo desde T-704, y el id de la nota si es anterior.
 */
export function amountNoteDocument(nota: AmountNote): SaleDetail {
	return {
		id: nota.id,
		sale_number: String(nota.id),
		created_at: nota.created_at,
		payment_method: nota.payment_method ?? 'Efectivo',
		subtotal: nota.subtotal,
		tax: nota.tax,
		total: nota.total,
		cash_received: 0,
		change_given: 0,
		client_id: nota.sale_client_id ?? null,
		user_id: nota.user_id,
		user_name: nota.user_name ?? null,
		items: nota.items.map((item) => ({
			id_product: item.id_product,
			name: item.name,
			quantity: 1,
			price: item.subtotal,
			subtotal: item.subtotal,
			tax_rate: item.tax_rate,
			tax_amount: item.tax_amount,
			cabys_code: item.cabys_code ?? null,
			unit_of_measure: item.unit_of_measure ?? null
		})),
		document_type: nota.document_type,
		einvoice: nota.einvoice ?? null,
		reference: {
			document_type: nota.sale_document_type ?? '',
			number: nota.sale_clave ?? nota.sale_number,
			date: nota.sale_created_at ?? '',
			code: nota.reference_code
		}
	};
}

/**
 * Una línea de los datos del emisor: qué es y qué dice.
 *
 * `kind` distingue las que llevan rótulo —«Cédula 3-101…», «Tel. 2222-3333»,
 * «Actividad económica 4741.0»— de las que se imprimen tal cual. El rótulo lo
 * pone la plantilla: acá no se escribe texto para una persona (RN-30).
 */
export interface IssuerLine {
	kind:
		| 'legalName'
		| 'taxId'
		| 'activity'
		| 'location'
		| 'address'
		| 'phone'
		| 'email'
		| 'website';
	value: string;
	/**
	 * Provincia, cantón y distrito con su nombre, solo en `location`: la
	 * plantilla los rotula como la factura de referencia —«Provincia: San José /
	 * Cantón: San José / Distrito: Zapote»— (T-722).
	 */
	place?: { province: string; canton: string; district: string };
	/**
	 * El tipo de la identificación, solo en un comprobante: ahí se imprime con
	 * su nombre legal —«Cédula jurídica 3101702934»—, como en el XML (RN-86). En
	 * el documento de siempre queda la «Cédula» a secas, que sirve en cualquier
	 * país.
	 */
	idType?: string;
}

/**
 * Datos del emisor listos para imprimir, sin las líneas vacías.
 *
 * Con `fiscal`, el documento es un comprobante (RN-86): la identificación va con
 * su tipo y se agrega la actividad económica, que Hacienda pide impresa. Y la
 * dirección es la del XML (T-722): provincia, cantón y distrito con su nombre, y
 * debajo el barrio y las otras señas. Sin ubicación completa queda la dirección
 * de texto libre, que es la que había.
 */
export function issuerLines(
	settings: Settings,
	fiscal: { activity: string | null } | null = null
): IssuerLine[] {
	const { business } = settings;
	const lugar = fiscal ? locationNames(business.location) : null;
	const senas = lugar
		? [business.location.neighborhood, business.location.otherSigns].filter(Boolean).join(', ')
		: business.address;
	const posibles: IssuerLine[] = [
		{
			kind: 'legalName',
			// La razón social solo se imprime si aporta algo: repetir el nombre
			// comercial dos veces seguidas se lee como un error de la factura.
			value: business.legalName && business.legalName !== business.name ? business.legalName : ''
		},
		fiscal
			? { kind: 'taxId', value: business.taxId, idType: business.taxIdType }
			: { kind: 'taxId', value: business.taxId },
		{ kind: 'activity', value: fiscal?.activity ?? '' },
		lugar
			? {
					kind: 'location',
					value: `${lugar.province} / ${lugar.canton} / ${lugar.district}`,
					place: lugar
				}
			: { kind: 'location', value: '' },
		{ kind: 'address', value: senas },
		{ kind: 'phone', value: business.phone },
		{ kind: 'email', value: business.email },
		{ kind: 'website', value: business.website }
	];
	return posibles.filter((linea) => Boolean(linea.value));
}

/**
 * La actividad económica que declara el comprobante.
 *
 * La del comprobante emitido cuando lo hay —es la que se mandó, aunque hoy la
 * configurada sea otra—; mientras tanto, la configurada, que es la que va a
 * declarar. Nula si la venta no es un comprobante.
 */
export function issuerActivity(
	sale: { document_type?: string | null; einvoice?: EmittedDocument | null },
	settings: Settings
): string | null {
	if (documentKind(sale) === 'invoice') return null;
	return sale.einvoice?.economic_activity || settings.eInvoicing.economicActivity || null;
}

/**
 * El número que se imprime en la cabecera.
 *
 * El consecutivo de Hacienda cuando el comprobante ya lo tiene; mientras tanto,
 * el de la venta. Uno solo y no los dos: dos números en la misma cabecera obligan
 * al cliente a adivinar cuál es el de su factura.
 */
export function documentNumber(sale: {
	sale_number: string;
	einvoice?: EmittedDocument | null;
}): string {
	return sale.einvoice?.consecutive ?? sale.sale_number;
}

/**
 * La condición de venta del comprobante: `'01'`, contado (nota 5 del anexo).
 *
 * Es una constante porque el POS cobra el total en el mostrador —`check_payment`
 * lo exige— y vender a crédito no está en el spec (T-729). El día que lo esté,
 * la condición pasa a ser de la venta.
 */
export const SALE_CONDITION_CASH = '01';

/**
 * El tipo de cambio que se imprime junto a la moneda, o `null` si no se sabe.
 *
 * En colones es 1 por definición. En otra moneda es el del BCCR del día, y ese
 * dato todavía no existe en el sistema: imprimir uno inventado sería peor que no
 * imprimirlo.
 */
export function exchangeRate(currencyCode: string): number | null {
	return currencyCode === 'CRC' ? 1 : null;
}

/** Una línea del comprobante, con lo que el anexo pide por línea (RN-86). */
export interface DocumentLine {
	/** Desde 1, en el orden de la venta. */
	number: number;
	id_product: number;
	cabys: string | null;
	name: string;
	quantity: number;
	unit: string | null;
	unitPrice: number;
	/** La tarifa con que se cobró, entre 0 y 1. */
	rate: number;
	/** Cantidad por precio. El POS no descuenta, así que es también la base. */
	subtotal: number;
	tax: number;
	/** Lo que paga el cliente por la línea: subtotal más impuesto. */
	total: number;
}

/**
 * Las líneas del documento, listas para imprimir.
 *
 * El impuesto es el que se **guardó** en la línea (RN-12). Las ventas anteriores
 * a la migración 006 no lo guardaron y llevan una sola tarifa: ahí sale de la del
 * encabezado, que para ellas es exacta, igual que en `taxBreakdown`.
 */
export function documentLines(sale: {
	subtotal: number;
	tax: number;
	items?: SaleItem[];
}): DocumentLine[] {
	const tasaDelEncabezado = sale.subtotal > 0 ? sale.tax / sale.subtotal : 0;
	return (sale.items ?? []).map((item, indice) => {
		const rate = item.tax_rate ?? tasaDelEncabezado;
		const tax = item.tax_amount ?? round2(item.subtotal * rate);
		return {
			number: indice + 1,
			id_product: item.id_product,
			cabys: item.cabys_code ?? null,
			name: item.name,
			quantity: item.quantity,
			unit: item.unit_of_measure ?? null,
			unitPrice: item.price,
			rate,
			subtotal: item.subtotal,
			tax,
			total: round2(item.subtotal + tax)
		};
	});
}

/**
 * El resumen del comprobante, con los renglones del `ResumenFactura` de Hacienda
 * (RN-86).
 *
 * Los descuentos son cero porque el POS no descuenta: no hay descuento en la
 * venta ni en sus líneas. Se imprimen igual porque es el renglón que el cliente
 * busca, y el día que haya descuentos salen de las líneas y el resumen ya los
 * tiene donde van.
 */
export interface DocumentSummary {
	gross: number;
	discounts: number;
	net: number;
	/** El desglose por tarifa (RF-21). */
	taxes: TaxLine[];
	tax: number;
	total: number;
}

export function documentSummary(sale: {
	subtotal: number;
	tax: number;
	total: number;
	items?: SaleItem[];
}): DocumentSummary {
	const discounts = 0;
	return {
		gross: sale.subtotal,
		discounts,
		net: round2(sale.subtotal - discounts),
		taxes: taxBreakdown(sale),
		tax: sale.tax,
		total: sale.total
	};
}

/** Total devuelto de una venta. Cero si no tiene devoluciones. */
export function returnedTotal(returns: SaleReturn[]): number {
	return returns.reduce((acc, r) => acc + Number(r.total), 0);
}

export type { Client, SaleDetail, SaleReturn };
