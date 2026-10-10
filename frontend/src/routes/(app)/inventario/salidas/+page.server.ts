import { fail } from '@sveltejs/kit';
import { api, apiSafe } from '$lib/server/api';
import { requireAdmin, requireModule } from '$lib/server/auth';
import { formError, Validator } from '$lib/application/validation';
import type { StockExit } from '$lib/domain/types';
import { F } from '$lib/ui/fields';
import { m } from '$lib/paraglide/messages.js';
import { apiMessage, validationErrors } from '$lib/ui/messages';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ locals, url }) => {
	requireAdmin(locals, url.pathname);
	const exits = await apiSafe<StockExit[]>('/inventory/exits', [], { token: locals.token });
	return {
		exits,
		/** Sin el endpoint, el backend es anterior a F15. */
		available: Array.isArray(exits)
	};
};

export const actions: Actions = {
	anular: async ({ request, locals, url }) => {
		requireAdmin(locals, url.pathname);
		requireModule(locals, 'inventory', url.pathname);
		const form = await request.formData();
		const v = new Validator(form);
		const id = v.integer('id_exit', F.exit(), { min: 1 });
		// El motivo es obligatorio **siempre** (RN-99): toda salida nació con
		// motivo y se va con motivo. A diferencia de la entrada, que solo se lo
		// pide a una compra.
		const reason = v.text('reason', F.reason(), { max: 255 });
		if (!v.ok) return fail(400, { errors: validationErrors(v.errors) });

		try {
			await api(`/inventory/exits/${id}/cancel`, {
				method: 'POST',
				token: locals.token,
				body: { reason }
			});
		} catch (error) {
			return fail(400, { errors: formError(apiMessage(error)) });
		}
		return { success: m.exits_cancelled_ok() };
	}
};
