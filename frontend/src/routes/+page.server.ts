import { redirect } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';

/** La raíz no muestra nada propia: manda a vender o a iniciar sesión. */
export const load: PageServerLoad = async ({ locals }) => {
	redirect(303, locals.user ? '/ventas' : '/login');
};
