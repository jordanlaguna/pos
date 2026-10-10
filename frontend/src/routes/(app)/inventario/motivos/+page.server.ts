import { fail } from '@sveltejs/kit';
import { api, apiSafe } from '$lib/server/api';
import { requireAdmin, requireModule } from '$lib/server/auth';
import { formError, Validator } from '$lib/application/validation';
import type { StockReason } from '$lib/domain/types';
import { F } from '$lib/ui/fields';
import { m } from '$lib/paraglide/messages.js';
import { apiMessage, validationErrors } from '$lib/ui/messages';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ locals, url }) => {
	requireAdmin(locals, url.pathname);
	const reasons = await apiSafe<StockReason[]>('/inventory/reasons', [], { token: locals.token });
	return { reasons };
};

export const actions: Actions = {
	crear: async ({ request, locals, url }) => {
		requireAdmin(locals, url.pathname);
		requireModule(locals, 'inventory', url.pathname);
		const v = new Validator(await request.formData());
		const code = v.text('code', F.reasonCode(), { max: 20 });
		const name = v.text('name', F.name(), { max: 80 });
		if (!v.ok) return fail(400, { errors: validationErrors(v.errors), action: 'crear' });

		try {
			await api('/inventory/reasons', { method: 'POST', token: locals.token, body: { code, name } });
		} catch (error) {
			return fail(400, { errors: formError(apiMessage(error)), action: 'crear' });
		}
		return { success: m.reasons_created() };
	},

	renombrar: async ({ request, locals, url }) => {
		requireAdmin(locals, url.pathname);
		requireModule(locals, 'inventory', url.pathname);
		const v = new Validator(await request.formData());
		const id = v.integer('id', F.stockReason(), { min: 1 });
		const name = v.text('name', F.name(), { max: 80 });
		if (!v.ok) return fail(400, { errors: validationErrors(v.errors), action: 'renombrar' });

		try {
			await api(`/inventory/reasons/${id}`, { method: 'PUT', token: locals.token, body: { name } });
		} catch (error) {
			return fail(400, { errors: formError(apiMessage(error)), action: 'renombrar' });
		}
		return { success: m.reasons_updated() };
	},

	/** Apaga o enciende. No se borra: las salidas viejas lo nombran (RF-88). */
	activar: async ({ request, locals, url }) => {
		requireAdmin(locals, url.pathname);
		requireModule(locals, 'inventory', url.pathname);
		const form = await request.formData();
		const v = new Validator(form);
		const id = v.integer('id', F.stockReason(), { min: 1 });
		if (!v.ok) return fail(400, { errors: validationErrors(v.errors), action: 'activar' });
		const isActive = form.get('is_active') === 'true';

		try {
			await api(`/inventory/reasons/${id}`, {
				method: 'PUT',
				token: locals.token,
				body: { is_active: isActive }
			});
		} catch (error) {
			return fail(400, { errors: formError(apiMessage(error)), action: 'activar' });
		}
		return { success: m.reasons_updated() };
	}
};
