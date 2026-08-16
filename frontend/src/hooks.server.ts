import type { Handle, HandleServerError } from '@sveltejs/kit';
import { clearSessionCookie, resolveUser } from '$lib/server/auth';
import { SESSION_COOKIE } from '$lib/server/config';

/**
 * Resuelve la sesión una sola vez por petición y la deja en `locals`, para que
 * los `load` y las acciones no tengan que repetir el trabajo.
 */
export const handle: Handle = async ({ event, resolve }) => {
	const token = event.cookies.get(SESSION_COOKIE) ?? null;
	const user = await resolveUser(token);

	// Token presente pero inservible (vencido o revocado): se limpia la cookie.
	if (token && !user) clearSessionCookie(event.cookies);

	event.locals.token = user ? token : null;
	event.locals.user = user;

	return resolve(event);
};

export const handleError: HandleServerError = ({ error, status }) => {
	if (status !== 404) console.error('[ventasys]', error);
	return {
		message:
			status === 404
				? 'La página que buscás no existe.'
				: 'Ocurrió un error inesperado. Revisá la conexión con el backend.'
	};
};
