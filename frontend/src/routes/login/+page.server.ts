import { fail, redirect } from '@sveltejs/kit';
import { api, toMessage } from '$lib/server/api';
import { setSessionCookie } from '$lib/server/auth';
import { USE_MOCK } from '$lib/server/config';
import { formError, Validator } from '$lib/validation';
import type { LoginResponse } from '$lib/types';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ locals, url }) => {
	if (locals.user) redirect(303, url.searchParams.get('redirectTo') ?? '/ventas');
	// En modo demo se muestran las credenciales en pantalla: nadie puede adivinarlas.
	return { demo: USE_MOCK };
};

export const actions: Actions = {
	default: async ({ request, cookies, url }) => {
		const form = await request.formData();
		const v = new Validator(form);
		const email = v.email('email');
		const password = v.password('password', 'La contraseña', { min: 1 });

		if (!v.ok) return fail(400, { errors: v.errors, email });

		try {
			const result = await api<LoginResponse>('/users/login', {
				method: 'POST',
				body: { email, password }
			});
			if (!result?.access_token) {
				return fail(502, {
					errors: formError('El backend no devolvió un token de acceso.'),
					email
				});
			}
			setSessionCookie(cookies, result.access_token);
		} catch (error) {
			return fail(401, { errors: formError(toMessage(error)), email });
		}

		// El redirect va fuera del try: lanza una excepción que no es un error.
		redirect(303, url.searchParams.get('redirectTo') ?? '/ventas');
	}
};
