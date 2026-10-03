import { fail, redirect } from '@sveltejs/kit';
import { api, apiSafe } from '$lib/server/api';
import { requireAdmin, requireModule } from '$lib/server/auth';
import { formError, Validator } from '$lib/application/validation';
import type { PayrollRun, PayrollRunDetail, WorkSchedule } from '$lib/domain/payroll';
import { F } from '$lib/ui/fields';
import { apiMessage, validationErrors } from '$lib/ui/messages';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ locals, url }) => {
	requireAdmin(locals, url.pathname);
	const token = locals.token;
	const [runs, schedules] = await Promise.all([
		apiSafe<PayrollRun[]>('/payroll/runs', [], { token }),
		apiSafe<WorkSchedule[]>('/payroll/schedules', [], { token })
	]);
	return { runs, schedules: schedules.filter((s) => s.is_active) };
};

function escribe(locals: App.Locals, pathname: string) {
	requireAdmin(locals, pathname);
	requireModule(locals, 'payroll', pathname);
}

export const actions: Actions = {
	crear: async ({ request, locals, url }) => {
		escribe(locals, url.pathname);
		const form = await request.formData();
		const v = new Validator(form);
		const cut_date = v.date('cut_date', F.cutDate());
		if (!v.ok) return fail(400, { errors: validationErrors(v.errors) });
		let creada: PayrollRunDetail;
		try {
			creada = await api<PayrollRunDetail>('/payroll/runs', {
				method: 'POST',
				token: locals.token,
				body: {
					schedule_id: Number(form.get('schedule_id')),
					cut_date,
					pay_date: String(form.get('pay_date') ?? '').trim() || null
				}
			});
		} catch (error) {
			return fail(400, { errors: formError(apiMessage(error)) });
		}
		redirect(303, `/planilla/corridas/${creada.id}`);
	},

	aguinaldo: async ({ request, locals, url }) => {
		escribe(locals, url.pathname);
		const form = await request.formData();
		const v = new Validator(form);
		const year = v.integer('year', F.year(), { min: 2000, max: 2100 });
		if (!v.ok) return fail(400, { errors: validationErrors(v.errors) });
		let creada: PayrollRunDetail;
		try {
			creada = await api<PayrollRunDetail>('/payroll/runs/aguinaldo', {
				method: 'POST',
				token: locals.token,
				body: { year, pay_date: String(form.get('pay_date') ?? '').trim() || null }
			});
		} catch (error) {
			return fail(400, { errors: formError(apiMessage(error)) });
		}
		redirect(303, `/planilla/corridas/${creada.id}`);
	}
};
