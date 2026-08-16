import { error } from '@sveltejs/kit';
import { API_BASE_URL, USE_MOCK } from '$lib/server/config';
import type { RequestHandler } from './$types';

/**
 * Puente hacia `GET /sales/pdf/{id}` del backend.
 *
 * Se proxea en vez de enlazar directo para que el navegador nunca tenga que
 * alcanzar la VM: la IP del backend no sale de este servidor y el JWT viaja
 * en la cabecera, no en la URL.
 */
export const GET: RequestHandler = async ({ params, locals, fetch }) => {
	if (!locals.user) error(401, { message: 'Sesión requerida.' });
	if (USE_MOCK) {
		error(404, {
			message: 'El modo demostración no genera PDF. Usá "Imprimir" para guardarlo desde el navegador.'
		});
	}

	const upstream = await fetch(`${API_BASE_URL}/sales/pdf/${params.id}`, {
		headers: locals.token ? { Authorization: `Bearer ${locals.token}` } : {}
	});

	if (!upstream.ok) {
		error(upstream.status === 404 ? 404 : 502, {
			message: 'El backend no pudo generar el PDF de esta factura.'
		});
	}

	return new Response(upstream.body, {
		headers: {
			'content-type': upstream.headers.get('content-type') ?? 'application/pdf',
			'content-disposition': `inline; filename="factura_${params.id}.pdf"`
		}
	});
};
