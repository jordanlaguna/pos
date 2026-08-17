import { fail, redirect } from '@sveltejs/kit';
import { api, toMessage } from '$lib/server/api';
import { setSessionCookie } from '$lib/server/auth';
import { USE_MOCK } from '$lib/server/config';
import { formError, Validator } from '$lib/application/validation';
import type { LoginResponse } from '$lib/domain/types';
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

		let hayQueElegir = false;
		try {
			const result = await api<LoginResponse>('/auth/login', {
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
			// Con una sola compañía disponible el backend ya devuelve la sesión
			// completa y no hay pantalla intermedia (RN-25): el cajero de un
			// negocio de una sola caja no se entera de que esto existe.
			hayQueElegir = result.tipo === 'transito';
		} catch (error) {
			return fail(401, { errors: formError(toMessage(error)), email });
		}

		// El redirect va fuera del try: lanza una excepción que no es un error.
		const destino = url.searchParams.get('redirectTo');
		if (hayQueElegir) {
			redirect(303, destino ? `/compania?redirectTo=${encodeURIComponent(destino)}` : '/compania');
		}
		redirect(303, destino ?? '/ventas');
	}
};
