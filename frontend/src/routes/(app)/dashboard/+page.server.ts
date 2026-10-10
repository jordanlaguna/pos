import { apiSafe } from '$lib/server/api';
import { requireAdmin } from '$lib/server/auth';
import { loadSettings } from '$lib/server/settings';
import { toDateInput } from '$lib/ui/format';
import type {
	LowStockProduct,
	PaymentBreakdown,
	PurchasesReport,
	ReportSummary,
	SalesByDay,
	TopProduct
} from '$lib/domain/types';
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
	const admin = requireAdmin(locals, url.pathname);
	const token = locals.token;

	const fallback = defaultRange();
	let from = url.searchParams.get('from') ?? fallback.from;
	let to = url.searchParams.get('to') ?? fallback.to;
	if (!ISO_DAY.test(from)) from = fallback.from;
	if (!ISO_DAY.test(to)) to = fallback.to;
	// Un rango invertido devuelve vacío en vez de fallar: se corrige y ya.
	if (from > to) [from, to] = [to, from];

	const query = { from, to };

	const [summary, topProducts, salesByDay, byPaymentMethod, lowStock, purchases, stored] =
		await Promise.all([
			apiSafe<ReportSummary | null>('/reports/summary', null, { token, query }),
			apiSafe<TopProduct[]>('/reports/top_products', [], {
				token,
				query: { ...query, limit: 8 }
			}),
			apiSafe<SalesByDay[]>('/reports/sales_by_day', [], { token, query }),
			apiSafe<PaymentBreakdown[]>('/reports/by_payment_method', [], { token, query }),
			// Sin umbral: el backend aplica el mínimo de cada producto y, sin él,
			// el general de Configuración (RN-101).
			apiSafe<LowStockProduct[]>('/reports/low_stock', [], { token }),
			// El crédito fiscal del periodo (RF-45). Va con los demás reportes y no
			// bajo /compras porque quien lo mira está conciliando impuestos, no
			// revisando lo que compró. `apiSafe` porque un backend sin F10 no tiene
			// la ruta y el tablero tiene que abrir igual.
			apiSafe<PurchasesReport | null>('/reports/purchases', null, { token, query }),
			loadSettings(token, admin.company_id)
		]);

	return {
		range: { from, to },
		summary,
		topProducts,
		salesByDay,
		byPaymentMethod,
		lowStock,
		purchases,
		/** El mínimo general (RN-101), para decir con qué regla se avisa. */
		lowStockThreshold: stored.settings.inventory.minStock,
		/** Sin summary el backend no tiene el patch de reportes aplicado. */
		reportsAvailable: summary !== null
	};
};
