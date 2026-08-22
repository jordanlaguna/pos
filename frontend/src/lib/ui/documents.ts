/**
 * Los rótulos del documento impreso.
 *
 * El documento no habla el idioma de la pantalla: la factura es para el cliente
 * y para Hacienda, así que una compañía costarricense la emite en español
 * aunque su cajero tenga el POS en portugués (RN-29). Hoy estas funciones leen
 * el catálogo de la sesión, que es lo mismo mientras haya un solo idioma;
 * **T-811** las hará leer el de `document_locale`. Lo que cambia entonces es de
 * dónde sale el idioma, no quién arma la frase: eso sigue siendo esto.
 */

import type { IssuerLine } from '$lib/domain/documents';
import type { Settings } from '$lib/domain/settings';
import { documentKind } from '$lib/domain/documents';
import { m } from '$lib/paraglide/messages.js';

/** «Factura» o «Factura electrónica», según lo configurado. */
export function documentTitle(settings: Settings): string {
	return documentKind(settings) === 'einvoice' ? m.doc_einvoice() : m.doc_invoice();
}

/**
 * Una línea del emisor, con su rótulo si lo lleva.
 *
 * La cédula y el teléfono se imprimen rotulados —«Cédula 3-101-123456»— porque
 * un número suelto en la cabecera de una factura no dice qué número es. La
 * dirección, el correo y el sitio se reconocen solos.
 */
export function issuerLine(linea: IssuerLine): string {
	switch (linea.kind) {
		case 'taxId':
			return m.doc_tax_id({ id: linea.value });
		case 'phone':
			return m.doc_phone({ phone: linea.value });
		default:
			return linea.value;
	}
}

/** Las líneas del emisor, ya en texto. */
export function issuerText(lineas: IssuerLine[]): string[] {
	return lineas.map(issuerLine);
}
