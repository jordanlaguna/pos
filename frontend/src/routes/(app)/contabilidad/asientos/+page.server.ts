import { fail } from '@sveltejs/kit';
import { api, apiSafe } from '$lib/server/api';
import { requireAdmin, requireModule } from '$lib/server/auth';
import { formError, Validator } from '$lib/application/validation';
import { F } from '$lib/ui/fields';
import { m } from '$lib/paraglide/messages.js';
import { apiMessage, validationErrors } from '$lib/ui/messages';
import type { Account, JournalEntry } from '$lib/domain/types';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ locals, url }) => {
	requireAdmin(locals, url.pathname);

	const hoy = new Date();
	const year = Number(url.searchParams.get('year')) || hoy.getFullYear();
	const mesPedido = url.searchParams.get('month');
	const month = mesPedido === '' ? null : Number(mesPedido) || hoy.getMonth() + 1;
	const entrada = Number(url.searchParams.get('entry')) || null;

	const consulta = `year=${year}${month ? `&month=${month}` : ''}`;
	const [asientos, cuentas, detalle] = await Promise.all([
		apiSafe<JournalEntry[]>(`/accounting/entries?${consulta}`, [], { token: locals.token }),
		apiSafe<Account[]>('/accounting/accounts', [], { token: locals.token }),
		entrada
			? apiSafe<JournalEntry | null>(`/accounting/entries/${entrada}`, null, {
					token: locals.token
				})
			: Promise.resolve(null)
	]);

	return {
		year,
		month,
		asientos,
		cuentas: cuentas.filter((cuenta) => cuenta.is_active),
		detalle
	};
};

export const actions: Actions = {
	crear: async ({ request, locals, url }) => {
		requireAdmin(locals, url.pathname);
		requireModule(locals, 'accounting', url.pathname);
		const form = await request.formData();
		const v = new Validator(form);

		const entry_date = v.date('entry_date', F.entryDate());
		const description = v.text('description', F.description(), { max: 255 });
		if (!v.ok) return fail(400, { errors: validationErrors(v.errors) });

		// Tres listas paralelas, como en la activación: una fila es una cuenta
		// con su débito y su crédito.
		const cuentas = form.getAll('line_account').map(String);
		const debitos = form.getAll('line_debit').map(String);
		const creditos = form.getAll('line_credit').map(String);
		const lines = cuentas
			.map((account_id, i) => ({
				account_id: Number(account_id),
				debit: Number(debitos[i] ?? 0) || 0,
				credit: Number(creditos[i] ?? 0) || 0
			}))
			.filter((linea) => linea.account_id && (linea.debit !== 0 || linea.credit !== 0));

		try {
			await api('/accounting/entries', {
				method: 'POST',
				token: locals.token,
				body: {
					entry_date,
					description,
					kind: String(form.get('kind') ?? 'manual'),
					lines
				}
			});
		} catch (error) {
			return fail(400, { errors: formError(apiMessage(error)) });
		}

		return { success: m.accounting_entry_saved() };
	},

	reclasificar: async ({ request, locals, url }) => {
		requireAdmin(locals, url.pathname);
		requireModule(locals, 'accounting', url.pathname);
		const form = await request.formData();
		const v = new Validator(form);

		const entryId = v.integer('entry_id', F.entry(), { min: 1 });
		const accountId = v.integer('account_id', F.account(), { min: 1 });
		if (!v.ok) return fail(400, { errors: validationErrors(v.errors) });

		try {
			await api(`/accounting/entries/${entryId}/reclassify`, {
				method: 'POST',
				token: locals.token,
				body: {
					account_id: accountId,
					description: String(form.get('description') ?? '').trim()
				}
			});
		} catch (error) {
			return fail(400, { errors: formError(apiMessage(error)) });
		}

		return { success: m.accounting_reclassified() };
	}
};
