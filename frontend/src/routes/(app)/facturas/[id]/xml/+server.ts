import { requireUser } from '$lib/server/auth';
import { archivoDelComprobante } from '$lib/server/fe';
import type { RequestHandler } from './$types';

/** El XML firmado tal como se envió a Hacienda (RF-34, RN-44). */
export const GET: RequestHandler = async ({ locals, params, url }) => {
	requireUser(locals, url.pathname);
	return archivoDelComprobante(locals.token, Number(params.id), 'xml');
};
