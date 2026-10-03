import { apiSafe } from '$lib/server/api';
import { requireAdmin } from '$lib/server/auth';
import type { PayrollRates } from '$lib/domain/payroll';
import { toDateInput } from '$lib/ui/format';
import type { PageServerLoad } from './$types';

/** Las tasas que rigen a una fecha, con su fuente (RF-56). Solo lectura: las
 * carga soporte para todas las compañías (RN-67). */
export const load: PageServerLoad = async ({ locals, url }) => {
	requireAdmin(locals, url.pathname);
	const on = url.searchParams.get('on') || toDateInput(new Date());
	const rates = await apiSafe<PayrollRates | null>(`/payroll/rates?on=${encodeURIComponent(on)}`, null, {
		token: locals.token
	});
	return { on, rates };
};
