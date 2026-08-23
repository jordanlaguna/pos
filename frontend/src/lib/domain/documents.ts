import { readableInk, withLightness } from './color';
import type { Settings } from './settings';
import type { Client, SaleDetail, SaleReturn } from './types';

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
export function documentKind(settings: Settings): 'einvoice' | 'invoice' {
	return settings.eInvoicing.enabled ? 'einvoice' : 'invoice';
}

/**
 * Una línea de los datos del emisor: qué es y qué dice.
 *
 * `kind` distingue las dos que llevan rótulo —«Cédula 3-101…», «Tel. 2222-3333»—
 * de las que se imprimen tal cual. El rótulo lo pone la plantilla: acá no se
 * escribe texto para una persona (RN-30).
 */
export interface IssuerLine {
	kind: 'legalName' | 'taxId' | 'address' | 'phone' | 'email' | 'website';
	value: string;
}

/** Datos del emisor listos para imprimir, sin las líneas vacías. */
export function issuerLines(settings: Settings): IssuerLine[] {
	const { business } = settings;
	const posibles: IssuerLine[] = [
		{
			kind: 'legalName',
			// La razón social solo se imprime si aporta algo: repetir el nombre
			// comercial dos veces seguidas se lee como un error de la factura.
			value: business.legalName && business.legalName !== business.name ? business.legalName : ''
		},
		{ kind: 'taxId', value: business.taxId },
		{ kind: 'address', value: business.address },
		{ kind: 'phone', value: business.phone },
		{ kind: 'email', value: business.email },
		{ kind: 'website', value: business.website }
	];
	return posibles.filter((linea) => Boolean(linea.value));
}

/** Total devuelto de una venta. Cero si no tiene devoluciones. */
export function returnedTotal(returns: SaleReturn[]): number {
	return returns.reduce((acc, r) => acc + Number(r.total), 0);
}

export type { Client, SaleDetail, SaleReturn };
