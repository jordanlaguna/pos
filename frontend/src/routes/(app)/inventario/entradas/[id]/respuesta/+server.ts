import { requireAdmin } from '$lib/server/auth';
import { archivoDeEntrada } from '$lib/server/fe';
import type { RequestHandler } from './$types';

/** La respuesta firmada de Hacienda a la factura de compra (RF-34, T-728). */
export const GET: RequestHandler = async ({ locals, params, url }) => {
	requireAdmin(locals, url.pathname);
	return archivoDeEntrada(locals.token, Number(params.id), 'response');
};
