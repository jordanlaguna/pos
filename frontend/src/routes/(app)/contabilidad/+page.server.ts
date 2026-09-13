import { fail } from '@sveltejs/kit';
import { api, apiSafe } from '$lib/server/api';
import { requireAdmin, requireModule } from '$lib/server/auth';
import { formError, Validator } from '$lib/application/validation';
import { F } from '$lib/ui/fields';
import { m } from '$lib/paraglide/messages.js';
import { apiMessage, validationErrors } from '$lib/ui/messages';
import type {
	AccountingPeriod,
	AccountingStatus,
	IncomeStatement,
	JournalEntry,
	TrialBalance
} from '$lib/domain/types';
import type { Actions, PageServerLoad } from './$types';

/** El código de la cuenta donde cae lo que el mapeo no supo clasificar. */
const POR_CLASIFICAR = '1.9.99';

export const load: PageServerLoad = async ({ locals, url, parent }) => {
	requireAdmin(locals, url.pathname);
	const { status } = (await parent()) as { status: AccountingStatus };
	if (!status.active) return { periodos: [], asientos: [], porClasificar: 0, resultado: 0 };

	const hoy = new Date();
	const periodo = `year=${hoy.getFullYear()}&month=${hoy.getMonth() + 1}`;

	// Las cuatro lecturas en paralelo: son independientes y la pantalla no
	// puede pintar nada hasta tenerlas todas.
	const [periodos, asientos, balance, resultado] = await Promise.all([
		apiSafe<AccountingPeriod[]>('/accounting/periods', [], { token: locals.token }),
		apiSafe<JournalEntry[]>('/accounting/entries', [], { token: locals.token }),
		apiSafe<TrialBalance | null>(`/accounting/reports/trial-balance?${periodo}`, null, {
			token: locals.token
		}),
		apiSafe<IncomeStatement | null>(`/accounting/reports/income?${periodo}`, null, {
			token: locals.token
		})
	]);

	return {
		periodos,
		// Los últimos ocho: el resumen es para mirar de reojo, no para auditar.
		asientos: [...asientos].reverse().slice(0, 8),
		// **El saldo acumulado**, no el del mes: lo que quedó sin clasificar en
		// agosto sigue sin clasificar hoy, y esconderlo al cambiar de mes sería
		// la peor forma de resolverlo.
		porClasificar:
			balance?.rows.find((fila) => fila.code === POR_CLASIFICAR)?.balance ?? 0,
		resultado: resultado?.result ?? 0
	};
};

export const actions: Actions = {
	activar: async ({ request, locals, url }) => {
		requireAdmin(locals, url.pathname);
		requireModule(locals, 'accounting', url.pathname);
		const form = await request.formData();
		const v = new Validator(form);

		const inicio = v.date('start_date', F.accountingStartDate());
		if (!v.ok) return fail(400, { errors: validationErrors(v.errors) });

		// Los saldos iniciales llegan como tres listas paralelas del formulario:
		// una fila es un código con su débito y su crédito.
		const codigos = form.getAll('opening_code').map(String);
		const debitos = form.getAll('opening_debit').map(String);
		const creditos = form.getAll('opening_credit').map(String);
		const opening = codigos
			.map((account_code, i) => ({
				account_code,
				debit: Number(debitos[i] ?? 0) || 0,
				credit: Number(creditos[i] ?? 0) || 0
			}))
			.filter((linea) => linea.account_code && (linea.debit !== 0 || linea.credit !== 0));

		try {
			const activada = await api<{ accounts_created: number; mappings_created: number }>(
				'/accounting/activate',
				{
					method: 'POST',
					token: locals.token,
					body: {
						template: String(form.get('template') ?? 'commerce'),
						start_date: inicio,
						description: String(form.get('description') ?? '').trim(),
						opening
					}
				}
			);
			return {
				success: m.accounting_activated({
					accounts: activada.accounts_created,
					mappings: activada.mappings_created
				})
			};
		} catch (error) {
			return fail(400, { errors: formError(apiMessage(error)) });
		}
	}
};
