import { requireUser } from '$lib/server/auth';
import { archivoDelComprobante } from '$lib/server/fe';
import type { RequestHandler } from './$types';

/** La respuesta firmada de Hacienda, tal como llegó (RF-34). */
export const GET: RequestHandler = async ({ locals, params, url }) => {
	requireUser(locals, url.pathname);
	return archivoDelComprobante(locals.token, Number(params.id), 'response');
};
