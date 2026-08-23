import { redirect } from '@sveltejs/kit';
import { clearSessionCookie, clearSupportCookie } from '$lib/server/auth';
import type { RequestHandler } from './$types';

/** Cerrar sesión es POST a propósito: un GET lo dispararía cualquier precarga. */
export const POST: RequestHandler = async ({ cookies }) => {
	clearSessionCookie(cookies);
	/*
	 * Y también la de soporte, si había una visita en curso (RF-8).
	 *
	 * Sin esto, cerrar sesión desde dentro de un *entrar como* borraba el token de
	 * la visita y dejaba el de soporte guardado, así que `hooks.server.ts` lo
	 * restauraba en la petición siguiente y la persona volvía al panel en vez de
	 * al login. «Cerrar sesión» tiene que cerrar **las dos**: es lo que hace
	 * cualquiera al levantarse de una máquina prestada.
	 */
	clearSupportCookie(cookies);
	redirect(303, '/login');
};
