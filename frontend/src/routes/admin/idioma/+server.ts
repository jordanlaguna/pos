import { error, redirect } from '@sveltejs/kit';
import { api } from '$lib/server/api';
import { requireSoporte, setSessionCookie } from '$lib/server/auth';
import { apiMessage } from '$lib/ui/messages';
import type { RequestHandler } from './$types';

/**
 * El idioma del panel de soporte (QA-02).
 *
 * Es el `/idioma` del POS para la otra aplicación: POST por la misma razón
 * —un GET lo dispararía una precarga— y el backend devuelve un token nuevo
 * porque el idioma vive en el token. Va por `/support/locale` y no por
 * `/auth/locale`, que arma un token con compañía, y soporte no tiene ninguna
 * (RN-4).
 */
export const POST: RequestHandler = async ({ request, cookies, locals, url }) => {
	requireSoporte(locals, url.pathname);

	const form = await request.formData();
	const elegido = String(form.get('locale') ?? 'es');
	const volverA = String(form.get('redirectTo') ?? '/admin');

	try {
		const respuesta = await api<{ access_token: string }>('/support/locale', {
			method: 'POST',
			body: { locale: elegido },
			token: locals.token
		});
		setSessionCookie(cookies, respuesta.access_token);
	} catch (err) {
		error(400, { message: apiMessage(err) });
	}

	redirect(303, volverA.startsWith('/admin') ? volverA : '/admin');
};
