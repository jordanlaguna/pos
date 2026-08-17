import type { Handle, HandleServerError } from '@sveltejs/kit';
import { clearSessionCookie, pendingSession, resolveUser } from '$lib/server/auth';
import { SESSION_COOKIE } from '$lib/server/config';

/**
 * Resuelve la sesión una sola vez por petición y la deja en `locals`, para que
 * los `load` y las acciones no tengan que repetir el trabajo.
 *
 * Desde F2 hay tres estados y no dos: sin sesión, **con compañía elegida**, y el
 * intermedio —autenticado pero sin compañía— que crea el login de dos pasos.
 */
export const handle: Handle = async ({ event, resolve }) => {
	const token = event.cookies.get(SESSION_COOKIE) ?? null;
	const pending = pendingSession(token);
	const user = pending ? null : await resolveUser(token);

	// Token presente pero inservible (vencido o revocado): se limpia la cookie.
	// Un token de tránsito vigente no entra acá: sirve, aunque no para el POS.
	if (token && !user && !pending) clearSessionCookie(event.cookies);

	// El token viaja en `locals` aunque sea de tránsito: `/compania` lo necesita
	// para pedir la lista y para elegir.
	event.locals.token = user || pending ? token : null;
	event.locals.user = user;
	event.locals.pending = pending;

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
