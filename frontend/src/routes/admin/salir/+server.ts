import { redirect } from '@sveltejs/kit';
import { clearSupportCookie, setSessionCookie } from '$lib/server/auth';
import { SUPPORT_COOKIE } from '$lib/server/config';
import type { RequestHandler } from './$types';

/**
 * Salir de un *entrar como* y volver al panel (RF-8, T-306).
 *
 * La cookie de sesión lleva el token de la visita y el de soporte está guardado
 * al lado; acá se cambian de lugar y se borra el respaldo. Es lo que hace que la
 * franja de la pantalla pueda ofrecer «volver al panel» en vez de «cerrar sesión
 * y entrar otra vez».
 *
 * Es POST por lo mismo que `/logout` y `/idioma`: un GET lo dispararía cualquier
 * precarga del navegador, y acá eso significaría sacar a alguien de la compañía
 * que estaba mirando por pasar el mouse por encima de un enlace.
 *
 * Sin token guardado no hay a dónde volver —la visita venció y `hooks` ya
 * restauró la sesión, o alguien llegó acá de casualidad— así que se manda al
 * panel igual: si la sesión de soporte ya no existe, `/admin` lo llevará al
 * login, que es la respuesta correcta y no hace falta duplicarla.
 */
export const POST: RequestHandler = async ({ cookies }) => {
	const guardado = cookies.get(SUPPORT_COOKIE);
	if (guardado) {
		setSessionCookie(cookies, guardado);
		clearSupportCookie(cookies);
	}
	redirect(303, '/admin');
};
