import { fail, redirect } from '@sveltejs/kit';
import { api, toMessage } from '$lib/server/api';
import { setSessionCookie } from '$lib/server/auth';
import type { ChooseCompanyResponse, CompanyOption } from '$lib/domain/types';
import type { Actions, PageServerLoad } from './$types';

/**
 * Elegir compañía (RF-27, plan §3.5).
 *
 * Se llega acá de dos maneras: recién autenticado con un token de tránsito, o
 * desde el menú para cambiar de compañía sin volver a escribir la contraseña
 * (RF-28). Las dos usan los mismos endpoints.
 *
 * Nadie sin token llega: sin tránsito ni sesión se va al login. Y con una sola
 * compañía disponible no hay nada que elegir, así que se entra directo en vez
 * de mostrar una lista de un elemento (RN-25).
 */

export const load: PageServerLoad = async ({ locals, url }) => {
	if (!locals.token) redirect(303, '/login');

	const companies = await api<CompanyOption[]>('/auth/companies', { token: locals.token });
	const disponibles = companies.filter((c) => c.puede_entrar);

	// Una sola y ya se está adentro de esa: no hay nada que decidir.
	if (locals.user && disponibles.length <= 1) {
		redirect(303, url.searchParams.get('redirectTo') ?? '/ventas');
	}

	return {
		companies,
		/** La actual, para marcarla cuando se llega desde el menú. */
		actual: locals.user?.company_id ?? null,
		redirectTo: url.searchParams.get('redirectTo') ?? '/ventas'
	};
};

function companyIdDe(form: FormData): number | null {
	const valor = Number(form.get('company_id'));
	return Number.isInteger(valor) && valor > 0 ? valor : null;
}

export const actions: Actions = {
	elegir: async ({ request, cookies, locals, url }) => {
		if (!locals.token) redirect(303, '/login');

		const companyId = companyIdDe(await request.formData());
		if (companyId === null) {
			return fail(400, { message: 'Elija una compañía para continuar.' });
		}

		try {
			const elegida = await api<ChooseCompanyResponse>('/auth/company', {
				method: 'POST',
				body: { company_id: companyId },
				token: locals.token
			});
			// El token nuevo reemplaza al anterior, sea de tránsito o de otra
			// compañía. No conviven: una sesión, una compañía (RN-27).
			setSessionCookie(cookies, elegida.access_token);
		} catch (error) {
			return fail(403, { message: toMessage(error) });
		}

		redirect(303, url.searchParams.get('redirectTo') ?? '/ventas');
	},

	/**
	 * Aceptar o rechazar una invitación (T-229).
	 *
	 * No redirige: se queda en la pantalla con la lista ya actualizada, porque
	 * aceptar una invitación no es lo mismo que elegir dónde trabajar. Quien
	 * acepta puede querer aceptar la otra, o entrar a la que ya tenía.
	 */
	invitacion: async ({ request, locals }) => {
		if (!locals.token) redirect(303, '/login');

		const form = await request.formData();
		const companyId = companyIdDe(form);
		const accion = String(form.get('accion') ?? '');
		if (companyId === null || !['aceptar', 'rechazar'].includes(accion)) {
			return fail(400, { message: 'No se entendió la respuesta a la invitación.' });
		}

		try {
			await api<CompanyOption[]>('/auth/invitation', {
				method: 'POST',
				body: { company_id: companyId, accion },
				token: locals.token
			});
		} catch (error) {
			return fail(400, { message: toMessage(error) });
		}

		return {
			hecho:
				accion === 'aceptar'
					? 'Invitación aceptada. Ya puede entrar a esa compañía.'
					: 'Invitación rechazada.'
		};
	}
};
