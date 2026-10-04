import { error, fail, redirect } from '@sveltejs/kit';
import { api, apiSafe, ApiError } from '$lib/server/api';
import { requireAdmin, requireModule } from '$lib/server/auth';
import { formError } from '$lib/application/validation';
import type { Employee, PayrollRunDetail } from '$lib/domain/payroll';
import { m } from '$lib/paraglide/messages.js';
import { apiMessage } from '$lib/ui/messages';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ locals, url, params }) => {
	requireAdmin(locals, url.pathname);
	const token = locals.token;
	let run: PayrollRunDetail;
	try {
		run = await api<PayrollRunDetail>(`/payroll/runs/${params.id}`, { token });
	} catch (e) {
		if (e instanceof ApiError && e.status === 404) error(404, { code: e.code });
		throw e;
	}
	// Las cuentas para la transferencia (plan §14.1): la planilla no mueve la caja.
	const employees = await apiSafe<Employee[]>('/payroll/employees', [], { token });
	return {
		run,
		ibans: Object.fromEntries(employees.map((e) => [e.id, e.iban])) as Record<number, string | null>
	};
};

function escribe(locals: App.Locals, pathname: string) {
	requireAdmin(locals, pathname);
	requireModule(locals, 'payroll', pathname);
}

async function paso(locals: App.Locals, id: string, verbo: string, exito: string) {
	try {
		await api<PayrollRunDetail>(`/payroll/runs/${id}/${verbo}`, { method: 'POST', token: locals.token });
	} catch (e) {
		return fail(400, { errors: formError(apiMessage(e)) });
	}
	return { success: exito };
}

export const actions: Actions = {
	calcular: async ({ locals, url, params }) => {
		escribe(locals, url.pathname);
		return paso(locals, params.id, 'calculate', m.payroll_run_calculated());
	},
	aprobar: async ({ locals, url, params }) => {
		escribe(locals, url.pathname);
		return paso(locals, params.id, 'approve', m.payroll_run_approved());
	},
	pagar: async ({ locals, url, params }) => {
		escribe(locals, url.pathname);
		return paso(locals, params.id, 'pay', m.payroll_run_paid());
	},
	ajustar: async ({ locals, url, params }) => {
		escribe(locals, url.pathname);
		let ajuste: PayrollRunDetail;
		try {
			ajuste = await api<PayrollRunDetail>(`/payroll/runs/${params.id}/adjust`, { method: 'POST', token: locals.token });
		} catch (e) {
			return fail(400, { errors: formError(apiMessage(e)) });
		}
		redirect(303, `/planilla/corridas/${ajuste.id}`);
	}
};
