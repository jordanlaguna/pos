import { fail, redirect } from '@sveltejs/kit';
import { api } from '$lib/server/api';
import { setSessionCookie } from '$lib/server/auth';
import { USE_MOCK } from '$lib/server/config';
import { formError, Validator } from '$lib/application/validation';
import type { LoginResponse } from '$lib/domain/types';
import { F } from '$lib/ui/fields';
import { m } from '$lib/paraglide/messages.js';
import { apiMessage, validationErrors } from '$lib/ui/messages';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ locals, url }) => {
	if (locals.user) redirect(303, url.searchParams.get('redirectTo') ?? '/ventas');
	// Soporte ya tiene sesión, la suya: al panel, no al POS (RN-4).
	if (locals.support) redirect(303, '/admin');
	// En modo demo se muestran las credenciales en pantalla: nadie puede adivinarlas.
	return { demo: USE_MOCK };
};

export const actions: Actions = {
	default: async ({ request, cookies, url }) => {
		const form = await request.formData();
		const v = new Validator(form);
		const email = v.email('email', F.email());
		const password = v.password('password', F.password(), { min: 1 });

		if (!v.ok) return fail(400, { errors: validationErrors(v.errors), email });

		let hayQueElegir = false;
		let esSoporte = false;
		try {
			const result = await api<LoginResponse>('/auth/login', {
				method: 'POST',
				body: { email, password }
			});
			if (!result?.access_token) {
				return fail(502, {
					errors: formError(m.auth_no_token()),
					email
				});
			}
			setSessionCookie(cookies, result.access_token);
			// Con una sola compañía disponible el backend ya devuelve la sesión
			// completa y no hay pantalla intermedia (RN-25): el cajero de un
			// negocio de una sola caja no se entera de que esto existe.
			hayQueElegir = result.tipo === 'transito';
			// Soporte no elige compañía porque no tiene ninguna (RN-4): su pantalla
			// es el panel, y `redirectTo` no aplica —lo que pidió, si pidió algo, era
			// una pantalla del POS a la que no puede entrar—.
			esSoporte = result.tipo === 'soporte';
		} catch (error) {
			return fail(401, { errors: formError(apiMessage(error)), email });
		}

		// El redirect va fuera del try: lanza una excepción que no es un error.
		const destino = url.searchParams.get('redirectTo');
		if (esSoporte) {
			redirect(303, '/admin');
		}
		if (hayQueElegir) {
			redirect(303, destino ? `/compania?redirectTo=${encodeURIComponent(destino)}` : '/compania');
		}
		redirect(303, destino ?? '/ventas');
	}
};
