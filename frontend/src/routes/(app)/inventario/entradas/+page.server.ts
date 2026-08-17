import { fail } from '@sveltejs/kit';
import { api, apiSafe, toMessage } from '$lib/server/api';
import { requireAdmin } from '$lib/server/auth';
import { formError, Validator } from '$lib/application/validation';
import type { StockEntry } from '$lib/domain/types';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ locals, url }) => {
	requireAdmin(locals, url.pathname);
	const entries = await apiSafe<StockEntry[]>('/inventory/entries', [], {
		token: locals.token
	});
	return {
		entries,
		/** Sin el endpoint, el backend no tiene el módulo de entradas aplicado. */
		available: Array.isArray(entries)
	};
};

export const actions: Actions = {
	anular: async ({ request, locals, url }) => {
		requireAdmin(locals, url.pathname);
		const v = new Validator(await request.formData());
		const id = v.integer('id_entry', 'La entrada', { min: 1 });
		if (!v.ok) return fail(400, { errors: v.errors });

		try {
			await api(`/inventory/entry/${id}/cancel`, { method: 'POST', token: locals.token });
		} catch (error) {
			return fail(400, { errors: formError(toMessage(error)) });
		}
		return { success: 'Entrada anulada; el stock volvió atrás.' };
	}
};
