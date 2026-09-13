import { fail } from '@sveltejs/kit';
import { api, apiSafe } from '$lib/server/api';
import { requireAdmin, requireModule } from '$lib/server/auth';
import { formError, Validator } from '$lib/application/validation';
import { F } from '$lib/ui/fields';
import { m } from '$lib/paraglide/messages.js';
import { apiMessage, validationErrors } from '$lib/ui/messages';
import { ACCOUNT_KINDS, type Account } from '$lib/domain/types';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ locals, url }) => {
	requireAdmin(locals, url.pathname);
	const cuentas = await apiSafe<Account[]>('/accounting/accounts', [], {
		token: locals.token
	});
	return { cuentas };
};

export const actions: Actions = {
	crear: async ({ request, locals, url }) => {
		requireAdmin(locals, url.pathname);
		requireModule(locals, 'accounting', url.pathname);
		const form = await request.formData();
		const v = new Validator(form);

		const code = v.text('code', F.accountCode(), { max: 20 });
		const name = v.text('name', F.name(), { max: 120 });
		const kind = v.oneOf('kind', F.accountKind(), ACCOUNT_KINDS);
		if (!v.ok) return fail(400, { errors: validationErrors(v.errors) });

		try {
			await api('/accounting/accounts', {
				method: 'POST',
				token: locals.token,
				body: { code, name, kind }
			});
		} catch (error) {
			return fail(400, { errors: formError(apiMessage(error)) });
		}

		return { success: m.accounting_account_saved() };
	},

	guardar: async ({ request, locals, url }) => {
		requireAdmin(locals, url.pathname);
		requireModule(locals, 'accounting', url.pathname);
		const form = await request.formData();
		const v = new Validator(form);

		const id = v.integer('id', F.account(), { min: 1 });
		const name = v.text('name', F.name(), { max: 120 });
		if (!v.ok) return fail(400, { errors: validationErrors(v.errors) });

		// `is_active` solo viaja cuando el botón lo manda: guardar el nombre no
		// puede activar ni desactivar de rebote.
		const activa = form.get('is_active');
		try {
			await api(`/accounting/accounts/${id}`, {
				method: 'PUT',
				token: locals.token,
				body: { name, is_active: activa === null ? null : activa === 'true' }
			});
		} catch (error) {
			return fail(400, { errors: formError(apiMessage(error)) });
		}

		return { success: m.accounting_account_saved() };
	},

	borrar: async ({ request, locals, url }) => {
		requireAdmin(locals, url.pathname);
		requireModule(locals, 'accounting', url.pathname);
		const form = await request.formData();
		const v = new Validator(form);

		const id = v.integer('id', F.account(), { min: 1 });
		if (!v.ok) return fail(400, { errors: validationErrors(v.errors) });

		try {
			await api(`/accounting/accounts/${id}`, { method: 'DELETE', token: locals.token });
		} catch (error) {
			return fail(400, { errors: formError(apiMessage(error)) });
		}

		return { success: m.accounting_account_deleted() };
	}
};
