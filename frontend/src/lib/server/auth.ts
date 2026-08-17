import type { Cookies } from '@sveltejs/kit';
import { error, redirect } from '@sveltejs/kit';
import { api, ApiError } from './api';
import { SESSION_COOKIE } from './config';
import type { PendingSession, Role, SessionUser } from '$lib/domain/types';

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
 * Un token de tránsito no es una sesión.
 *
 * Se distingue mirando el propio JWT y no preguntándole al backend: el token de
 * tránsito hace 401 en toda ruta de negocio, así que preguntar significaría
 * gastar una petición para que nos digan que no. La firma la valida el backend
 * cuando el token se usa de verdad; acá solo se lee para saber a qué pantalla
 * mandar a la persona.
 */
export function pendingSession(token: string | null): PendingSession | null {
	if (!token) return null;

	const payload = decodeJwt(token);
	if (isExpired(payload)) return null;
	if (payload?.tipo !== 'transito') return null;

	const idUser = typeof payload.id_user === 'number' ? payload.id_user : null;
	const email = typeof payload.email === 'string' ? payload.email : null;
	if (idUser == null || !email) return null;

	return { user_id: idUser, email };
}

/**
 * Resuelve el usuario del token.
 *
 * `GET /users/me` devuelve el rol **y la compañía**, y se consulta en cada
 * petición: así, quitarle a alguien la membresía o degradarlo surte efecto en su
 * siguiente clic y no cuando venza el JWT.
 *
 * Un token de tránsito devuelve `null` acá a propósito. No es un fallo: es
 * alguien autenticado que todavía no dijo en qué compañía trabaja, y su pantalla
 * es `/compania`, no el POS.
 */
export async function resolveUser(token: string | null): Promise<SessionUser | null> {
	if (!token) return null;

	const payload = decodeJwt(token);
	if (isExpired(payload)) return null;
	if (payload?.tipo === 'transito') return null;

	try {
		const me = await api<{
			id_user: number;
			email: string;
			id_person: number | null;
			role?: Role;
			name?: string;
			company_id: number;
			company_name?: string | null;
			branch_code?: string | null;
			terminal_code?: string | null;
			companies_available?: number;
		}>('/users/me', { token });
		return {
			id_user: me.id_user,
			email: me.email,
			id_person: me.id_person ?? null,
			role: me.role === 'cajero' ? 'cajero' : 'admin',
			name: me.name?.trim() || me.email,
			company_id: me.company_id,
			company_name: me.company_name ?? null,
			branch_code: me.branch_code ?? null,
			terminal_code: me.terminal_code ?? null,
			companies_available: me.companies_available ?? 1
		};
	} catch (err) {
		/*
		 * Antes había acá un camino de respaldo que reconstruía el usuario desde
		 * el JWT y le asumía rol admin, para poder hablar con un backend viejo
		 * sin `/users/me`. Se quitó en F2: ese respaldo no puede saber en qué
		 * compañía está la sesión, y adivinarla es exactamente lo que no se
		 * puede hacer. Sin `/users/me` no hay sesión.
		 */
		if (!(err instanceof ApiError)) console.error('[ventasys] /users/me', err);
		return null;
	}
}

/**
 * Exige sesión iniciada. Redirige al login conservando el destino.
 *
 * Con un token de tránsito manda a `/compania` y no al login: la persona ya
 * escribió su contraseña y hacérsela escribir otra vez sería castigarla por no
 * haber elegido todavía.
 */
export function requireUser(locals: App.Locals, pathname = '/'): SessionUser {
	if (!locals.user) {
		const target = pathname && pathname !== '/' ? `?redirectTo=${encodeURIComponent(pathname)}` : '';
		if (locals.pending) redirect(303, `/compania${target}`);
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
