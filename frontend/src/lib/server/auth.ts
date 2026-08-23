import type { Cookies } from '@sveltejs/kit';
import { error, redirect } from '@sveltejs/kit';
import { api, ApiError } from './api';
import { SESSION_COOKIE, SUPPORT_COOKIE } from './config';
import type { PendingSession, Role, SessionUser, Subscription, SupportUser } from '$lib/domain/types';

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

/**
 * Guarda el token de soporte antes de entrar a una compañía (RF-8).
 *
 * La cookie de sesión pasa a llevar el de suplantación, y este queda a un lado
 * para poder volver al panel sin escribir la contraseña otra vez. Dura lo mismo
 * que la visita más un margen: si la visita vence, `hooks.server.ts` lo usa para
 * devolver a soporte al panel en vez de al login.
 */
export function setSupportCookie(cookies: Cookies, token: string): void {
	cookies.set(SUPPORT_COOKIE, token, {
		path: '/',
		httpOnly: true,
		sameSite: 'strict',
		secure: process.env.NODE_ENV === 'production' && process.env.POS_INSECURE_COOKIE !== '1',
		maxAge: EIGHT_HOURS
	});
}

export function clearSupportCookie(cookies: Cookies): void {
	cookies.delete(SUPPORT_COOKIE, { path: '/' });
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
 * El idioma que resolvió el servidor al emitir el token (T-809, plan §8.4).
 *
 * Viaja en el JWT como `loc` junto con la compañía y el rol, por la misma razón
 * que ellos: lo decide el backend —lo de la persona, si no lo de la compañía, si
 * no español— y el cliente no puede elegirlo mandando un parámetro. Un token de
 * tránsito no lo trae: sin compañía elegida no hay idioma que resolver.
 *
 * Devuelve `null` cuando no hay token, cuando venció o cuando el reclamo no
 * viene, y quien llama cae al idioma base. No se valida contra la lista de
 * idiomas compilados: eso lo hace Paraglide, que es quien la tiene.
 */
export function sessionLocale(token: string | null): string | null {
	if (!token) return null;
	const payload = decodeJwt(token);
	if (isExpired(payload)) return null;
	return typeof payload?.loc === 'string' && payload.loc ? payload.loc : null;
}

/**
 * El token de sesión dentro de una cabecera `Cookie` cruda.
 *
 * Hace falta porque la estrategia de idioma de Paraglide recibe el `Request` y
 * no el `event` de SvelteKit, así que no tiene `event.cookies`. Se lee del texto
 * y no se guarda en ninguna variable de módulo: el idioma es de la petición, y
 * un módulo lo compartiría entre todas (defecto 17).
 */
export function tokenFromCookieHeader(header: string | null): string | null {
	if (!header) return null;
	for (const parte of header.split(';')) {
		const [nombre, ...resto] = parte.trim().split('=');
		if (nombre === SESSION_COOKIE) return decodeURIComponent(resto.join('=')) || null;
	}
	return null;
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
 * ¿Este token es del panel de soporte?
 *
 * Se decide leyendo el propio JWT, igual que con el de tránsito y por la misma
 * razón: un token de soporte hace 401 en toda ruta del POS, así que preguntarle
 * al backend sería gastar una petición para que nos digan que no. Lo que **sí**
 * se consulta contra el backend es `/support/me`, que es quien vuelve a
 * comprobar la marca de soporte en la base (T-301).
 */
export function isSupportToken(token: string | null): boolean {
	if (!token) return false;
	const payload = decodeJwt(token);
	if (isExpired(payload)) return false;
	return payload?.tipo === 'soporte';
}

/**
 * Resuelve la sesión de soporte contra `GET /support/me`.
 *
 * Se consulta en cada petición por lo mismo que `/users/me`: quitarle el
 * permiso a alguien tiene que surtir efecto en su siguiente clic. Devuelve
 * `null` si el token ya no vale o si esa cuenta dejó de ser soporte, y entonces
 * el panel manda al login.
 */
export async function resolveSupport(token: string | null): Promise<SupportUser | null> {
	if (!isSupportToken(token)) return null;

	try {
		const me = await api<{
			id_user: number;
			email: string;
			name?: string;
			is_support?: boolean;
			locale?: string;
		}>('/support/me', { token });
		if (me.is_support === false) return null;
		return {
			id_user: me.id_user,
			email: me.email,
			name: me.name?.trim() || me.email,
			locale: me.locale ?? 'es'
		};
	} catch (err) {
		if (!(err instanceof ApiError)) console.error('[ventasys] /support/me', err);
		return null;
	}
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
 * es `/compania`, no el POS. Uno de soporte tampoco es un usuario del POS: no
 * tiene compañía, y su pantalla es `/admin`.
 */
export async function resolveUser(token: string | null): Promise<SessionUser | null> {
	if (!token) return null;

	const payload = decodeJwt(token);
	if (isExpired(payload)) return null;
	if (payload?.tipo === 'transito' || payload?.tipo === 'soporte') return null;

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
			locale?: string;
			user_locale?: string | null;
			company_locale?: string;
			document_locale?: string;
			subscription?: Subscription | null;
			impersonated_by?: string | null;
			impersonation_reason?: string | null;
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
			companies_available: me.companies_available ?? 1,
			locale: me.locale ?? 'es',
			user_locale: me.user_locale ?? null,
			company_locale: me.company_locale ?? 'es',
			document_locale: me.document_locale ?? 'es',
			subscription: me.subscription ?? null,
			impersonated_by: me.impersonated_by ?? null,
			impersonation_reason: me.impersonation_reason ?? null
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
 *
 * A soporte le responde **403 y no un redirect** (T-302): tiene una sesión
 * válida, lo que no tiene es compañía. Mandarlo al login lo dejaría en un
 * círculo —entra, vuelve al panel, prueba el POS otra vez— y no le diría nunca
 * qué pasó.
 */
export function requireUser(locals: App.Locals, pathname = '/'): SessionUser {
	if (locals.support) error(403, { code: 'no_company_in_token' });
	if (!locals.user) {
		const target = pathname && pathname !== '/' ? `?redirectTo=${encodeURIComponent(pathname)}` : '';
		if (locals.pending) redirect(303, `/compania${target}`);
		redirect(303, `/login${target}`);
	}
	return locals.user;
}

/**
 * Exige rol admin. Un cajero que llegue aquí recibe 403, no un redirect.
 *
 * Lanza un **código y no una frase** (RN-30): esta función vive en `$lib/server`,
 * que no es la interfaz y no sabe en qué idioma está la pantalla. La frase la
 * arma `+error.svelte`.
 */
export function requireAdmin(locals: App.Locals, pathname = '/'): SessionUser {
	const user = requireUser(locals, pathname);
	if (user.role !== 'admin') error(403, { code: 'admin_only' });
	return user;
}

/**
 * Exige sesión de soporte (T-301, T-302).
 *
 * Un usuario de compañía recibe 403 y no un redirect, por lo mismo que arriba:
 * volver a entrar no lo va a convertir en soporte. Quien no tiene ninguna
 * sesión sí va al login, que es donde puede hacer algo.
 */
export function requireSoporte(locals: App.Locals, pathname = '/'): SupportUser {
	if (locals.support) return locals.support;
	if (locals.user || locals.pending) error(403, { code: 'support_only' });

	const target = pathname && pathname !== '/' ? `?redirectTo=${encodeURIComponent(pathname)}` : '';
	redirect(303, `/login${target}`);
}

/**
 * Exige que la sesión pueda **escribir** (T-308, RF-10).
 *
 * Es el mismo control que aplica el backend en cada petición, adelantado a la
 * carga de la pantalla. No es una duplicación inútil: el backend impide que la
 * escritura ocurra y esto impide que se ofrezca. RN-2 pide justamente eso —el
 * bloqueo se evalúa al abrir la pantalla de ventas y no al cobrar—, porque
 * enterarse de que la suscripción venció con el cliente enfrente y el carrito
 * lleno es la peor manera posible de enterarse.
 *
 * Lanza un código con el estado como dato; la frase la arma `+error.svelte`.
 */
export function requireWrite(user: SessionUser): SessionUser {
	if (user.impersonated_by) error(403, { code: 'impersonation_read_only' });

	const suscripcion = user.subscription;
	if (suscripcion && !suscripcion.puede_vender) {
		error(403, { code: 'subscription_read_only', state: suscripcion.estado });
	}
	return user;
}
