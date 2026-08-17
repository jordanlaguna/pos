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

/** Nombre del documento según se emita o no factura electrónica. */
export function documentTitle(settings: Settings): string {
	return settings.eInvoicing.enabled ? 'Factura electrónica' : 'Factura';
}

/** Datos del emisor listos para imprimir, sin las líneas vacías. */
export function issuerLines(settings: Settings): string[] {
	const { business } = settings;
	return [
		business.legalName && business.legalName !== business.name ? business.legalName : '',
		business.taxId ? `Cédula ${business.taxId}` : '',
		business.address,
		business.phone ? `Tel. ${business.phone}` : '',
		business.email,
		business.website
	].filter(Boolean);
}

/** Total devuelto de una venta. Cero si no tiene devoluciones. */
export function returnedTotal(returns: SaleReturn[]): number {
	return returns.reduce((acc, r) => acc + Number(r.total), 0);
}

export type { Client, SaleDetail, SaleReturn };
