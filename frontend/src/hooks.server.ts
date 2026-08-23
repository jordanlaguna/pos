import type { Handle, HandleServerError } from '@sveltejs/kit';
import {
	clearSessionCookie,
	clearSupportCookie,
	pendingSession,
	resolveSupport,
	resolveUser,
	sessionLocale,
	setSessionCookie,
	tokenFromCookieHeader
} from '$lib/server/auth';
import { SESSION_COOKIE, SUPPORT_COOKIE } from '$lib/server/config';
import { m } from '$lib/paraglide/messages.js';
import { cookieName, defineCustomServerStrategy } from '$lib/paraglide/runtime.js';
import { paraglideMiddleware } from '$lib/paraglide/server.js';

/**
 * De dónde sale el idioma de cada petición (T-809, plan §8.4).
 *
 * Del **token**, que es donde el backend dejó el idioma ya resuelto. Se registra
 * como estrategia de servidor y no se lee en un `load` porque el idioma tiene que
 * estar puesto antes de que se renderice cualquier cosa: los mensajes se piden
 * durante el render, no después.
 *
 * `getLocale` recibe el `Request` y nada más, así que el token se saca de la
 * cabecera `Cookie` a mano. **No hay estado de módulo**: si el idioma se guardara
 * en una variable de este archivo, la primera petición del proceso le prestaría
 * su idioma a todas las demás —el defecto 17, y es exactamente por eso que
 * `strategy` no incluye `globalVariable`—. Paraglide lo guarda por petición en
 * AsyncLocalStorage, y ese es el trabajo de `paraglideMiddleware`.
 */
defineCustomServerStrategy('custom-session', {
	getLocale: (request) => sessionLocale(tokenFromCookieHeader(request?.headers.get('cookie') ?? null)) ?? undefined
});

/**
 * Resuelve la sesión una sola vez por petición y la deja en `locals`, para que
 * los `load` y las acciones no tengan que repetir el trabajo.
 *
 * Desde F2 hay tres estados y no dos: sin sesión, **con compañía elegida**, y el
 * intermedio —autenticado pero sin compañía— que crea el login de dos pasos.
 * Desde F3 hay un cuarto: **soporte**, que tampoco tiene compañía, pero no
 * porque le falte elegirla sino porque no le corresponde ninguna (RN-4).
 *
 * Los cuatro se resuelven una sola vez y son excluyentes, así que se pregunta en
 * orden y se paga una petición al backend, no tres.
 */
export const handle: Handle = async ({ event, resolve }) => {
	let token = event.cookies.get(SESSION_COOKIE) ?? null;
	const pending = pendingSession(token);
	let support = pending ? null : await resolveSupport(token);
	const user = pending || support ? null : await resolveUser(token);

	/*
	 * La visita venció: se vuelve al panel, no al login (RF-8).
	 *
	 * Un *entrar como* dura media hora. Cuando se acaba, el token de la
	 * suplantación deja de servir y sin esto soporte terminaría en la pantalla de
	 * login escribiendo su contraseña otra vez —teniendo una sesión de soporte
	 * perfectamente válida guardada al lado—. Se restaura y se sigue.
	 */
	const guardado = event.cookies.get(SUPPORT_COOKIE) ?? null;
	if (!user && !pending && !support && guardado) {
		support = await resolveSupport(guardado);
		if (support) {
			token = guardado;
			setSessionCookie(event.cookies, guardado);
			clearSupportCookie(event.cookies);
		}
	}

	// Token presente pero inservible (vencido o revocado): se limpia la cookie.
	// Un token de tránsito vigente no entra acá: sirve, aunque no para el POS. El
	// de soporte tampoco, salvo que ya no valga —y entonces sí hay que limpiarlo,
	// porque si no la pantalla de login lo vería y creería que hay sesión—.
	if (token && !user && !pending && !support) {
		clearSessionCookie(event.cookies);
		clearSupportCookie(event.cookies);
	}

	// El token viaja en `locals` aunque sea de tránsito: `/compania` lo necesita
	// para pedir la lista y para elegir. Y el de soporte, para el panel.
	event.locals.token = user || pending || support ? token : null;
	event.locals.user = user;
	event.locals.pending = pending;
	event.locals.support = support;

	return paraglideMiddleware(event.request, ({ locale }) => {
		event.locals.locale = locale;

		/*
		 * La cookie es el **espejo** del idioma del token, para el navegador.
		 *
		 * Después de hidratar, el POS navega del lado del cliente y ahí no hay
		 * token que leer —la cookie de sesión es httpOnly a propósito—, así que
		 * Paraglide resuelve el idioma con su estrategia `cookie`. Es un espejo y
		 * nunca una fuente: en el servidor manda `custom-session`, y quien edite
		 * esta cookie a mano solo se cambia el idioma a sí mismo hasta el
		 * siguiente render. No es httpOnly porque el punto es que el navegador la
		 * lea.
		 */
		if (event.cookies.get(cookieName) !== locale) {
			event.cookies.set(cookieName, locale, {
				path: '/',
				httpOnly: false,
				sameSite: 'strict',
				maxAge: 60 * 60 * 24 * 365
			});
		}

		// `<html lang>` tiene que decir la verdad: de ahí salen la pronunciación de
		// un lector de pantalla y el guionado del navegador.
		return resolve(event, {
			transformPageChunk: ({ html }) => html.replace('%paraglide.lang%', locale)
		});
	});
};

export const handleError: HandleServerError = ({ error, status }) => {
	if (status !== 404) console.error('[ventasys]', error);
	return {
		message: status === 404 ? m.error_page_missing() : m.error_unexpected_backend()
	};
};
