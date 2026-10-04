import { error } from '@sveltejs/kit';
import { apiFile, ApiError } from '$lib/server/api';
import { requireAdmin } from '$lib/server/auth';
import type { RequestHandler } from './$types';

/**
 * El archivo de la planilla para RT-Virtual (RF-85), tal cual lo arma el
 * backend: ancho fijo, ISO-8859-1. Acá no se toca ni un byte; solo se pasa con
 * su nombre.
 */
export const GET: RequestHandler = async ({ locals, url }) => {
	requireAdmin(locals, url.pathname);
	try {
		const archivo = await apiFile('/payroll/exports/ins', {
			token: locals.token,
			query: {
				year: url.searchParams.get('year'),
				month: url.searchParams.get('month'),
				policy: url.searchParams.get('policy')
			}
		});
		return new Response(archivo.bytes as BodyInit, {
			headers: {
				'content-type': archivo.contentType,
				'content-disposition': `attachment; filename="${archivo.filename ?? 'planilla-ins.txt'}"`
			}
		});
	} catch (e) {
		if (e instanceof ApiError) error(e.status >= 400 && e.status < 500 ? e.status : 502, { code: e.code });
		throw e;
	}
};
