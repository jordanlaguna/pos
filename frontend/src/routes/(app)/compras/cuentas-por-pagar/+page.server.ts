import { fail } from '@sveltejs/kit';
import { api, apiSafe } from '$lib/server/api';
import { requireAdmin } from '$lib/server/auth';
import { formError, Validator } from '$lib/application/validation';
import type { Payables } from '$lib/domain/types';
import { F } from '$lib/ui/fields';
import { m } from '$lib/paraglide/messages.js';
import { apiMessage, validationErrors } from '$lib/ui/messages';
import type { Actions, PageServerLoad } from './$types';

/** Lo que se debe cuando no hay nada: los cuatro tramos igual (RF-44). */
const VACIO: Payables = {
	as_of: new Date().toISOString().slice(0, 10),
	total: 0,
	by_bucket: [0, 30, 60, 90].map((bucket) => ({ bucket, balance: 0 })),
	suppliers: []
};

export const load: PageServerLoad = async ({ locals, url }) => {
	requireAdmin(locals, url.pathname);
	const payables = await apiSafe<Payables>('/payables', VACIO, { token: locals.token });
	return { payables };
};

export const actions: Actions = {
	abonar: async ({ request, locals, url }) => {
		requireAdmin(locals, url.pathname);
		const form = await request.formData();
		const v = new Validator(form);

		const entryId = v.integer('entry_id', F.entry(), { min: 1 });
		const amount = v.decimal('amount', F.amount(), { min: 0.01 });
		if (!v.ok) return fail(400, { errors: validationErrors(v.errors) });

		try {
			await api(`/purchases/${entryId}/payments`, {
				method: 'POST',
				token: locals.token,
				body: {
					amount,
					method: String(form.get('method') ?? 'transfer'),
					reference: String(form.get('reference') ?? '').trim() || null,
					// El motivo del movimiento de caja lo arma la pantalla (RN-30):
					// el backend no sabe en qué idioma está. Solo se usa si el
					// método es efectivo, que es el único que escribe en la gaveta.
					reason: String(form.get('reason') ?? '').trim()
				}
			});
		} catch (error) {
			return fail(400, { errors: formError(apiMessage(error)) });
		}

		return { success: m.payment_saved() };
	}
};
