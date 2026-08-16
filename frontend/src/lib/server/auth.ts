import type { Cookies } from '@sveltejs/kit';
import { error, redirect } from '@sveltejs/kit';
import { api, ApiError } from './api';
import { SESSION_COOKIE } from './config';
import type { Role, SessionUser } from '$lib/types';

/**
 * Sesión del POS.
 *
 * El JWT que emite FastAPI se guarda en una cookie httpOnly + sameSite=strict:
 * ningún script del navegador puede leerlo, a diferencia del `AuthSession` estático
 * que usaba el WinForms. Cada petición se resuelve contra el backend para que un
 * token revocado o vencido deje de servir de inmediato.
 */

const EIGHT_HOURS = 60 * 60 * 8;

export function setSessionCookie(cookies: Cookies, token: string): void {
	cookies.set(SESSION_COOKIE, token, {
		path: '/',
		httpOnly: true,
		sameSite: 'strict',
		// El backend corre en HTTP dentro de la LAN; en producción con TLS poner true.
		secure: process.env.NODE_ENV === 'production' && process.env.POS_INSECURE_COOKIE !== '1',
		maxAge: EIGHT_HOURS
	});
}

export function clearSessionCookie(cookies: Cookies): void {
	cookies.delete(SESSION_COOKIE, { path: '/' });
}

/** Lee el payload de un JWT sin verificar la firma. Verificar es tarea del backend. */
function decodeJwt(token: string): Record<string, unknown> | null {
	const parts = token.split('.');
	if (parts.length !== 3) return null;
	try {
		return JSON.parse(Buffer.from(parts[1], 'base64url').toString('utf-8'));
	} catch {
		return null;
	}
}

function isExpired(payload: Record<string, unknown> | null): boolean {
	const exp = payload?.exp;
	return typeof exp === 'number' && exp * 1000 <= Date.now();
}

/**
 * Resuelve el usuario del token.
 *
 * Camino normal: `GET /users/me`, que devuelve también el rol. Si ese endpoint no
 * existe todavía (backend sin el patch de este proyecto) se reconstruye el usuario
 * desde el propio JWT y se asume rol admin — así el POS sigue siendo utilizable
 * contra el backend original, solo que sin separación de permisos.
 */
export async function resolveUser(token: string | null): Promise<SessionUser | null> {
	if (!token) return null;

	const payload = decodeJwt(token);
	if (isExpired(payload)) return null;

	try {
		const me = await api<{
			id_user: number;
			email: string;
			id_person: number | null;
			role?: Role;
			name?: string;
		}>('/users/me', { token });
		return {
			id_user: me.id_user,
			email: me.email,
			id_person: me.id_person ?? null,
			role: me.role === 'cajero' ? 'cajero' : 'admin',
			name: me.name?.trim() || me.email
		};
	} catch (err) {
		// 401/403: el token ya no vale. Cualquier otra cosa: intentamos el respaldo.
		if (err instanceof ApiError && (err.status === 401 || err.status === 403)) return null;

		const idUser = typeof payload?.id_user === 'number' ? payload.id_user : null;
		const email = typeof payload?.email === 'string' ? payload.email : null;
		if (idUser == null || !email) return null;

		let name = email;
		try {
			const persons = await api<{ id_user: number; name: string; lastName: string }[]>(
				'/persons/persons_list',
				{ token }
			);
			const person = persons.find((p) => p.id_user === idUser);
			if (person) name = `${person.name} ${person.lastName}`.trim() || email;
		} catch {
			// El nombre es cosmético: si falla, se muestra el correo.
		}

		return { id_user: idUser, email, id_person: null, role: 'admin', name };
	}
}

/** Exige sesión iniciada. Redirige al login conservando el destino. */
export function requireUser(locals: App.Locals, pathname = '/'): SessionUser {
	if (!locals.user) {
		const target = pathname && pathname !== '/' ? `?redirectTo=${encodeURIComponent(pathname)}` : '';
		redirect(303, `/login${target}`);
	}
	return locals.user;
}

/** Exige rol admin. Un cajero que llegue aquí recibe 403, no un redirect. */
export function requireAdmin(locals: App.Locals, pathname = '/'): SessionUser {
	const user = requireUser(locals, pathname);
	if (user.role !== 'admin') {
		error(403, { message: 'Esta sección es solo para administradores.', code: 'FORBIDDEN' });
	}
	return user;
}
