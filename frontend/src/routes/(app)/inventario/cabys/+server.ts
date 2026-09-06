import { error, json } from '@sveltejs/kit';
import { api, ApiError } from '$lib/server/api';
import { requireAdmin } from '$lib/server/auth';
import { m } from '$lib/paraglide/messages.js';
import type { CabysAnswer } from '$lib/domain/cabys';
import type { RequestHandler } from './$types';

/**
 * Puente hacia el catálogo CABYS (T-504).
 *
 * Es el único sitio del POS donde el navegador pide algo por su cuenta, y por
 * eso existe: buscar un código es teclear y ver resultados, y eso no cabe en un
 * envío de formulario. Todo lo demás sigue igual —el token nunca sale de este
 * servidor, la IP del backend tampoco—.
 *
 * `q` busca por texto y `codigo` trae uno exacto. Son dos usos distintos: el
 * primero es el buscador, y el segundo es el que sirve para saber cuál es la
 * tarifa oficial de un producto que ya estaba clasificado, que es lo que hace
 * falta para poder avisar de una diferencia (RN-11).
 */
export const GET: RequestHandler = async ({ url, locals }) => {
	requireAdmin(locals, url.pathname);

	const texto = url.searchParams.get('q');
	const codigo = url.searchParams.get('codigo');

	try {
		if (codigo) {
			return json(await api<CabysAnswer>(`/cabys/${encodeURIComponent(codigo)}`, { token: locals.token }));
		}
		return json(
			await api<CabysAnswer>('/cabys/buscar', {
				token: locals.token,
				query: { q: texto ?? '', top: 20 }
			})
		);
	} catch (e) {
		/*
		 * Que Hacienda no conteste NO llega hasta acá: el backend responde 200
		 * desde su caché y lo dice en `source` (RNF-4). Un 404 es «ese código no
		 * existe» y un 400 es «no es un código», y las dos son respuestas: el
		 * buscador las muestra como «sin resultados» y quien consulta la tarifa
		 * oficial las lee como «no se sabe».
		 *
		 * Lo que sí es una falla de verdad es no alcanzar el backend, y eso sale
		 * como 502 para que la pantalla lo distinga de una búsqueda sin premio.
		 */
		if (e instanceof ApiError && e.isClientError) {
			return json({ items: [], source: 'hacienda', cached_at: null } satisfies CabysAnswer);
		}
		error(502, { message: m.inventory_cabys_unreachable() });
	}
};
