import { apiSafe } from '$lib/server/api';
import { requireAdmin } from '$lib/server/auth';
import { LOW_STOCK_THRESHOLD } from '$lib/server/config';
import { toDateInput } from '$lib/format';
import type {
	LowStockProduct,
	PaymentBreakdown,
	ReportSummary,
	SalesByDay,
	TopProduct
} from '$lib/types';
import type { PageServerLoad } from './$types';

/** Rango por defecto: los últimos 30 días, incluido hoy. */
function defaultRange() {
	const to = new Date();
	const from = new Date();
	from.setDate(from.getDate() - 29);
	return { from: toDateInput(from), to: toDateInput(to) };
}

const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/;

export const load: PageServerLoad = async ({ locals, url }) => {
	requireAdmin(locals, url.pathname);
	const token = locals.token;

	const fallback = defaultRange();
	let from = url.searchParams.get('from') ?? fallback.from;
	let to = url.searchParams.get('to') ?? fallback.to;
	if (!ISO_DAY.test(from)) from = fallback.from;
	if (!ISO_DAY.test(to)) to = fallback.to;
	// Un rango invertido devuelve vacío en vez de fallar: se corrige y ya.
	if (from > to) [from, to] = [to, from];

	const query = { from, to };

	const [summary, topProducts, salesByDay, byPaymentMethod, lowStock] = await Promise.all([
		apiSafe<ReportSummary | null>('/reports/summary', null, { token, query }),
		apiSafe<TopProduct[]>('/reports/top_products', [], {
			token,
			query: { ...query, limit: 8 }
		}),
		apiSafe<SalesByDay[]>('/reports/sales_by_day', [], { token, query }),
		apiSafe<PaymentBreakdown[]>('/reports/by_payment_method', [], { token, query }),
		apiSafe<LowStockProduct[]>('/reports/low_stock', [], {
			token,
			query: { threshold: LOW_STOCK_THRESHOLD }
		})
	]);

	return {
		range: { from, to },
		summary,
		topProducts,
		salesByDay,
		byPaymentMethod,
		lowStock,
		lowStockThreshold: LOW_STOCK_THRESHOLD,
		/** Sin summary el backend no tiene el patch de reportes aplicado. */
		reportsAvailable: summary !== null
	};
};
