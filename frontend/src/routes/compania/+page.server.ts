import { fail, redirect } from '@sveltejs/kit';
import { api } from '$lib/server/api';
import { setSessionCookie } from '$lib/server/auth';
import { m } from '$lib/paraglide/messages.js';
import type { ChooseCompanyResponse, CompanyOption } from '$lib/domain/types';
import type { Actions, PageServerLoad } from './$types';
import { apiMessage } from '$lib/ui/messages';

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
	// «Cambiar de caja» desde el menú (RN-102): la misma pantalla, aunque la
	// compañía sea una sola, porque lo que hay que elegir es la caja.
	const cajas = disponibles.find((c) => c.id === locals.user?.company_id)?.terminals ?? [];
	const cambiandoDeCaja = url.searchParams.get('caja') === '1' && cajas.length > 1;

	// Una sola y ya se está adentro de esa: no hay nada que decidir.
	if (locals.user && disponibles.length <= 1 && !cambiandoDeCaja) {
		redirect(303, url.searchParams.get('redirectTo') ?? '/ventas');
	}

	return {
		companies,
		/** La actual, para marcarla cuando se llega desde el menú. */
		actual: locals.user?.company_id ?? null,
		/** Y la caja actual, por lo mismo. */
		actualTerminal: locals.user?.terminal_id ?? null,
		redirectTo: url.searchParams.get('redirectTo') ?? '/ventas'
	};
};

function companyIdDe(form: FormData): number | null {
	const valor = Number(form.get('company_id'));
	return Number.isInteger(valor) && valor > 0 ? valor : null;
}

/** La caja elegida, si la pantalla ofreció varias; en blanco es «la de siempre». */
function terminalIdDe(form: FormData): number | null {
	const crudo = String(form.get('terminal_id') ?? '').trim();
	if (!crudo) return null;
	const valor = Number(crudo);
	return Number.isInteger(valor) && valor > 0 ? valor : null;
}

export const actions: Actions = {
	elegir: async ({ request, cookies, locals, url }) => {
		if (!locals.token) redirect(303, '/login');

		const form = await request.formData();
		const companyId = companyIdDe(form);
		if (companyId === null) {
			return fail(400, { message: m.company_choose_one() });
		}
		const terminalId = terminalIdDe(form);

		try {
			const elegida = await api<ChooseCompanyResponse>('/auth/company', {
				method: 'POST',
				// La caja va solo si se eligió: el servidor comprueba que sea de esa
				// compañía y esté activa (RN-102), y sin ella abre en la de siempre.
				body: terminalId === null ? { company_id: companyId } : { company_id: companyId, terminal_id: terminalId },
				token: locals.token
			});
			// El token nuevo reemplaza al anterior, sea de tránsito o de otra
			// compañía. No conviven: una sesión, una compañía (RN-27).
			setSessionCookie(cookies, elegida.access_token);
		} catch (error) {
			return fail(403, { message: apiMessage(error) });
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
			return fail(400, { message: m.company_bad_invite_answer() });
		}

		try {
			await api<CompanyOption[]>('/auth/invitation', {
				method: 'POST',
				body: { company_id: companyId, accion },
				token: locals.token
			});
		} catch (error) {
			return fail(400, { message: apiMessage(error) });
		}

		return {
			hecho:
				accion === 'aceptar'
					? m.company_invite_accepted()
					: m.company_invite_rejected()
		};
	}
};
