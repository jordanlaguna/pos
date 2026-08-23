import { error, fail, redirect } from '@sveltejs/kit';
import { api } from '$lib/server/api';
import { requireSoporte, setSessionCookie, setSupportCookie } from '$lib/server/auth';
import { formError, Validator } from '$lib/application/validation';
import { COMPANY_STATES, type AuditLine, type Plan, type SupportCompany } from '$lib/domain/types';
import { F } from '$lib/ui/fields';
import { apiMessage, validationErrors } from '$lib/ui/messages';
import { m } from '$lib/paraglide/messages.js';
import type { Actions, PageServerLoad } from './$types';

/** Lo que hay que escribir para entrar como una compañía. El backend exige 5. */
const MOTIVO_MINIMO = 5;

function idDe(params: { id: string }): number {
	const id = Number(params.id);
	if (!Number.isInteger(id) || id <= 0) error(404, { code: 'company_not_found' });
	return id;
}

export const load: PageServerLoad = async ({ locals, params, url }) => {
	requireSoporte(locals, url.pathname);
	const id = idDe(params);

	/*
	 * Las tres cosas en paralelo. La ficha no sirve sin la bitácora de esa
	 * compañía —la pregunta que trae a alguien acá es «qué pasó»— y pedirlas en
	 * fila triplicaría la espera por nada: no dependen entre sí.
	 */
	const [company, plans, auditoria] = await Promise.all([
		api<SupportCompany>(`/support/companies/${id}`, { token: locals.token }),
		api<Plan[]>('/support/plans', { token: locals.token }),
		api<{ lineas: AuditLine[] }>(`/support/audit?company_id=${id}&limite=10`, {
			token: locals.token
		})
	]);

	return {
		company,
		plans,
		lineas: auditoria.lineas,
		estados: COMPANY_STATES,
		// Se muestra en pantalla antes de entrar: quien entra tiene que saber
		// cuánto le dura la visita.
		minutosDeVisita: 30,
		recienCreada: url.searchParams.get('creada') === '1'
	};
};

export const actions: Actions = {
	/** Estado, fecha y plan (RF-7, T-305). */
	suscripcion: async ({ request, locals, params, url }) => {
		requireSoporte(locals, url.pathname);
		const id = idDe(params);

		const form = await request.formData();
		const v = new Validator(form);
		const estado = v.oneOf('estado', F.companyState(), COMPANY_STATES);
		const vence = v.date('vence_el', F.expiresOn(), { required: false });
		const planId = v.integer('plan_id', F.plan(), { min: 1 });
		if (!v.ok) return fail(400, { errors: validationErrors(v.errors) });

		try {
			await api(`/support/companies/${id}/subscription`, {
				method: 'PUT',
				token: locals.token,
				body: { estado, vence_el: vence || null, plan_id: planId }
			});
		} catch (err) {
			return fail(400, { errors: formError(apiMessage(err)) });
		}

		return { success: m.admin_subscription_saved() };
	},

	/**
	 * *Entrar como* la compañía (RF-8, RN-4, T-306).
	 *
	 * El token que devuelve el backend reemplaza a la cookie de sesión, y el de
	 * soporte se guarda al lado para poder volver. Es la parte que hace que esto
	 * sea usable: sin guardarlo, salir de la visita significaría escribir la
	 * contraseña otra vez.
	 */
	entrar: async ({ request, locals, params, url, cookies }) => {
		requireSoporte(locals, url.pathname);
		const id = idDe(params);
		const tokenDeSoporte = locals.token;

		const form = await request.formData();
		const v = new Validator(form);
		const motivo = v.text('motivo', F.reason(), { min: MOTIVO_MINIMO, max: 500 });
		if (!v.ok) return fail(400, { errors: validationErrors(v.errors) });

		try {
			const visita = await api<{ access_token: string }>(`/support/companies/${id}/enter`, {
				method: 'POST',
				token: locals.token,
				body: { motivo }
			});
			if (tokenDeSoporte) setSupportCookie(cookies, tokenDeSoporte);
			setSessionCookie(cookies, visita.access_token);
		} catch (err) {
			return fail(400, { errors: formError(apiMessage(err)) });
		}

		// Al tablero y no a ventas: soporte va a mirar, y ventas es la pantalla
		// donde no puede hacer nada (la visita es de solo lectura).
		redirect(303, '/dashboard');
	}
};
