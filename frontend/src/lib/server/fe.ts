/**
 * Lo que las pantallas de facturas, devoluciones y notas comparten del
 * recorrido ante Hacienda (F7): reintentar un detenido y bajar sus archivos.
 *
 * Vive acá y no en cada `+page.server.ts` por lo mismo que `payroll.ts`: una
 * acción que existe en tres pantallas tiene que decir lo mismo en las tres.
 */

import { error, fail } from '@sveltejs/kit';
import { m } from '$lib/paraglide/messages.js';
import { api, apiFile, ApiError } from '$lib/server/api';
import { formError } from '$lib/application/validation';
import { apiMessage } from '$lib/ui/messages';
import type { DocumentFile, EmittedDocument, SaleDetail, StockEntry } from '$lib/domain/types';

/** RF-36: vuelve a la cola el comprobante detenido que diga el formulario. */
export async function reintentarComprobante(token: string | null | undefined, form: FormData) {
	const id = Number(form.get('document_id'));
	if (!Number.isInteger(id) || id <= 0) return fail(400, { errors: formError(m.invoice_retry_failed()) });
	try {
		await api<DocumentFile>(`/fe/documents/${id}/retry`, { method: 'POST', token });
	} catch (e) {
		return fail(400, { errors: formError(apiMessage(e)) });
	}
	return { success: m.invoice_retry_done() };
}

/**
 * RF-34: el XML firmado o la respuesta de Hacienda de la venta, **byte por
 * byte** como los guardó el backend. Acá no se toca el contenido; solo se
 * pasa con su nombre.
 */
export async function archivoDelComprobante(
	token: string | null | undefined,
	saleId: number,
	cual: 'xml' | 'response'
): Promise<Response> {
	return descargar(token, cual, saleId, async () => {
		const venta = await api<SaleDetail>(`/sales/sale/${saleId}`, { token });
		return venta.einvoice;
	});
}

/** Lo mismo para la factura electrónica de compra de una entrada (T-728). */
export async function archivoDeEntrada(
	token: string | null | undefined,
	entryId: number,
	cual: 'xml' | 'response'
): Promise<Response> {
	return descargar(token, cual, entryId, async () => {
		const entrada = await api<StockEntry>(`/inventory/entry/${entryId}`, { token });
		return entrada.einvoice;
	});
}

async function descargar(
	token: string | null | undefined,
	cual: 'xml' | 'response',
	origen: number,
	comprobante: () => Promise<EmittedDocument | null | undefined>
): Promise<Response> {
	try {
		const emitido = await comprobante();
		const documento = emitido?.id;
		if (!documento) error(404, { code: 'document_not_found' });
		const archivo = await apiFile(`/fe/documents/${documento}/${cual}`, { token });
		return new Response(archivo.bytes as BodyInit, {
			headers: {
				'content-type': archivo.contentType || 'application/xml',
				'content-disposition': `attachment; filename="${archivo.filename ?? `${emitido?.clave ?? origen}.xml`}"`
			}
		});
	} catch (e) {
		if (e instanceof ApiError) error(e.status >= 400 && e.status < 500 ? e.status : 502, { code: e.code });
		throw e;
	}
}
