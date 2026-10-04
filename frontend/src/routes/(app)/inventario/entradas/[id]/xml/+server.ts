import { requireAdmin } from '$lib/server/auth';
import { archivoDeEntrada } from '$lib/server/fe';
import type { RequestHandler } from './$types';

/** El XML firmado de la factura de compra, tal como se envió (RF-34, T-728). */
export const GET: RequestHandler = async ({ locals, params, url }) => {
	requireAdmin(locals, url.pathname);
	return archivoDeEntrada(locals.token, Number(params.id), 'xml');
};
