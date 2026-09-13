import { fail } from '@sveltejs/kit';
import { api, apiSafe } from '$lib/server/api';
import { requireAdmin, requireModule } from '$lib/server/auth';
import { formError, Validator } from '$lib/application/validation';
import { F } from '$lib/ui/fields';
import { m } from '$lib/paraglide/messages.js';
import { apiMessage, validationErrors } from '$lib/ui/messages';
import type { AccountingPeriod } from '$lib/domain/types';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ locals, url }) => {
	requireAdmin(locals, url.pathname);
	const periodos = await apiSafe<AccountingPeriod[]>('/accounting/periods', [], {
		token: locals.token
	});
	return { periodos };
};

export const actions: Actions = {
	cerrar: async ({ request, locals, url }) => {
		requireAdmin(locals, url.pathname);
		requireModule(locals, 'accounting', url.pathname);
		const form = await request.formData();
		const v = new Validator(form);

		// El año y el mes van por la ruta, así que se validan como enteros: un
		// mes 13 no tiene que llegar al servidor para que lo rechace.
		const year = v.integer('year', F.entryDate(), { min: 2000, max: 2100 });
		const month = v.integer('month', F.entryDate(), { min: 1, max: 12 });
		if (!v.ok) return fail(400, { errors: validationErrors(v.errors) });

		try {
			await api(`/accounting/periods/${year}/${month}/close`, {
				method: 'POST',
				token: locals.token,
				body: {}
			});
		} catch (error) {
			return fail(400, { errors: formError(apiMessage(error)) });
		}

		return { success: m.accounting_period_closed_ok() };
	}
};
