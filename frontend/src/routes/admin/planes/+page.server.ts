import { fail } from '@sveltejs/kit';
import { api } from '$lib/server/api';
import { requireSoporte } from '$lib/server/auth';
import { formError, Validator } from '$lib/application/validation';
import { MODULES, type Plan } from '$lib/domain/types';
import { F } from '$lib/ui/fields';
import { apiMessage, validationErrors } from '$lib/ui/messages';
import { m } from '$lib/paraglide/messages.js';
import type { Actions, PageServerLoad } from './$types';

/**
 * Los planes y qué módulos incluye cada uno (RF-39, T-1003).
 *
 * Solo los módulos se editan desde acá. El precio y los límites son una decisión
 * comercial que se escribe en la base; los módulos son lo que se vende y se deja
 * de vender, y eso tiene que poder hacerse sin abrir Adminer.
 */
export const load: PageServerLoad = async ({ locals, url }) => {
	requireSoporte(locals, url.pathname);

	const plans = await api<Plan[]>('/support/plans', { token: locals.token });
	return { plans };
};

export const actions: Actions = {
	/**
	 * Guarda los tres módulos de un plan.
	 *
	 * Se mandan los tres siempre y no solo los marcados: una casilla sin marcar
	 * no viaja en el formulario, así que un parche con lo que llegó no podría
	 * distinguir «la desmarcó» de «no la tocó».
	 */
	modulos: async ({ request, locals, url }) => {
		requireSoporte(locals, url.pathname);

		const form = await request.formData();
		const v = new Validator(form);
		const planId = v.integer('plan_id', F.plan(), { min: 1 });
		if (!v.ok) return fail(400, { errors: validationErrors(v.errors) });

		const body = Object.fromEntries(MODULES.map((nombre) => [nombre, form.has(nombre)]));

		try {
			await api(`/support/plans/${planId}/modules`, {
				method: 'PUT',
				token: locals.token,
				body
			});
		} catch (err) {
			return fail(400, { errors: formError(apiMessage(err)) });
		}

		return { success: m.admin_plan_modules_saved() };
	}
};
