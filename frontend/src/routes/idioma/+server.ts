import { error, redirect } from '@sveltejs/kit';
import { api } from '$lib/server/api';
import { requireUser, setSessionCookie } from '$lib/server/auth';
import { apiMessage } from '$lib/ui/messages';
import type { RequestHandler } from './$types';

/**
 * Cambiar el idioma de **esta persona** (T-810, RN-28).
 *
 * Es POST por lo mismo que `/logout`: un GET lo dispararía cualquier precarga
 * del navegador, y acá eso significaría cambiarle el idioma a alguien por pasar
 * el mouse por encima de un enlace.
 *
 * Lo interesante es que **el backend devuelve un token nuevo**: el idioma vive en
 * el token (plan §8.4), así que cambiarlo es emitir sesión otra vez, igual que
 * cambiar de compañía (RF-28). Sin renovar la cookie, la pantalla seguiría en el
 * idioma anterior hasta el siguiente login.
 *
 * `locale=auto` borra la preferencia y vuelve a heredar la de la compañía. No es
 * lo mismo que elegir español: si el dueño cambia el idioma del negocio, quien
 * hereda lo sigue y quien eligió español se queda en español.
 */
export const POST: RequestHandler = async ({ request, cookies, locals, url }) => {
	requireUser(locals, url.pathname);

	const form = await request.formData();
	const elegido = String(form.get('locale') ?? 'auto');
	const volverA = String(form.get('redirectTo') ?? '/ventas');

	try {
		const respuesta = await api<{ access_token: string }>('/auth/locale', {
			method: 'POST',
			body: { locale: elegido === 'auto' ? null : elegido },
			token: locals.token
		});
		setSessionCookie(cookies, respuesta.access_token);
	} catch (err) {
		// La frase se arma acá porque un `+server.ts` es interfaz. Que falle es
		// raro —el selector solo ofrece idiomas válidos— así que se dice y no se
		// esconde: un cambio que no pasó y no avisa deja a la persona dándole
		// clics al mismo botón.
		error(400, { message: apiMessage(err) });
	}

	// A la misma pantalla, para que el cambio se vea donde se pidió.
	redirect(303, volverA.startsWith('/') ? volverA : '/ventas');
};
