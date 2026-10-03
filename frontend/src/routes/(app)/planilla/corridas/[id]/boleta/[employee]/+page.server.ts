import { error } from '@sveltejs/kit';
import { api, ApiError } from '$lib/server/api';
import { requireAdmin } from '$lib/server/auth';
import type { Payslip } from '$lib/domain/payroll';
import type { PageServerLoad } from './$types';

/** La boleta, de los rubros congelados (RF-58): el backend no recalcula nada. */
export const load: PageServerLoad = async ({ locals, url, params }) => {
	requireAdmin(locals, url.pathname);
	try {
		const payslip = await api<Payslip>(`/payroll/runs/${params.id}/payslips/${params.employee}`, {
			token: locals.token
		});
		return { payslip };
	} catch (e) {
		if (e instanceof ApiError && e.status === 404) error(404, { code: e.code });
		throw e;
	}
};
