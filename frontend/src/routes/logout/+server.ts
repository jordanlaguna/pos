import { redirect } from '@sveltejs/kit';
import { clearSessionCookie } from '$lib/server/auth';
import type { RequestHandler } from './$types';

/** Cerrar sesión es POST a propósito: un GET lo dispararía cualquier precarga. */
export const POST: RequestHandler = async ({ cookies }) => {
	clearSessionCookie(cookies);
	redirect(303, '/login');
};
