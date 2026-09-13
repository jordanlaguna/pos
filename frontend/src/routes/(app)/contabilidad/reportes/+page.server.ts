import { apiSafe } from '$lib/server/api';
import { requireAdmin } from '$lib/server/auth';
import type {
	BalanceSheet,
	IncomeStatement,
	Journal,
	LedgerReport,
	TrialBalance
} from '$lib/domain/types';
import type { PageServerLoad } from './$types';

/**
 * Los cinco libros, en el orden en que un contador los mira.
 *
 * Sin `export`: SvelteKit solo admite `load`, `actions` y un puñado de opciones
 * en un `+page.server.ts`, y cualquier otra exportación tumba la ruta con un 500
 * en tiempo de ejecución —no al compilar—.
 */
const REPORTES = ['trial-balance', 'income', 'balance', 'journal', 'ledger'] as const;

type Reporte = (typeof REPORTES)[number];

export const load: PageServerLoad = async ({ locals, url }) => {
	requireAdmin(locals, url.pathname);

	const hoy = new Date();
	const year = Number(url.searchParams.get('year')) || hoy.getFullYear();
	const mesPedido = url.searchParams.get('month');
	const month = mesPedido === '' ? null : Number(mesPedido) || hoy.getMonth() + 1;
	const pedido = url.searchParams.get('report');
	const reporte: Reporte = (REPORTES as readonly string[]).includes(pedido ?? '')
		? (pedido as Reporte)
		: 'trial-balance';

	const consulta = `year=${year}${month ? `&month=${month}` : ''}`;
	const datos = await apiSafe<
		TrialBalance | IncomeStatement | BalanceSheet | Journal | LedgerReport | null
	>(`/accounting/reports/${reporte}?${consulta}`, null, { token: locals.token });

	return { year, month, reporte, datos };
};
