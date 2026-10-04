import { fail } from '@sveltejs/kit';
import { api, apiSafe } from '$lib/server/api';
import { requireAdmin, requireModule } from '$lib/server/auth';
import { formError, Validator } from '$lib/application/validation';
import type { InsPolicy, PayrollSettings, Position, WorkSchedule } from '$lib/domain/payroll';
import { F } from '$lib/ui/fields';
import { m } from '$lib/paraglide/messages.js';
import { apiMessage, validationErrors } from '$lib/ui/messages';
import type { Actions, PageServerLoad } from './$types';

const SIN_DATOS: PayrollSettings = { employer_number: null, ina_exempt: false };

export const load: PageServerLoad = async ({ locals, url }) => {
	requireAdmin(locals, url.pathname);
	const token = locals.token;
	const [settings, schedules, positions, policies] = await Promise.all([
		apiSafe<PayrollSettings>('/payroll/settings', SIN_DATOS, { token }),
		apiSafe<WorkSchedule[]>('/payroll/schedules', [], { token }),
		apiSafe<Position[]>('/payroll/positions', [], { token }),
		apiSafe<InsPolicy[]>('/payroll/policies', [], { token })
	]);
	return { settings, schedules, positions, policies };
};

function texto(form: FormData, campo: string): string | null {
	return String(form.get(campo) ?? '').trim() || null;
}

function numero(form: FormData, campo: string): number | null {
	const crudo = String(form.get(campo) ?? '').trim();
	return crudo === '' ? null : Number(crudo);
}

/** Lo que una acción de escritura hace primero: sesión de administración y módulo. */
function escribe(locals: App.Locals, pathname: string) {
	requireAdmin(locals, pathname);
	requireModule(locals, 'payroll', pathname);
}

export const actions: Actions = {
	patronales: async ({ request, locals, url }) => {
		escribe(locals, url.pathname);
		const form = await request.formData();
		try {
			await api<PayrollSettings>('/payroll/settings', {
				method: 'PUT',
				token: locals.token,
				body: { employer_number: texto(form, 'employer_number'), ina_exempt: form.get('ina_exempt') === 'on' }
			});
		} catch (error) {
			return fail(400, { errors: formError(apiMessage(error)) });
		}
		return { success: m.payroll_settings_saved() };
	},

	jornada: async ({ request, locals, url }) => {
		escribe(locals, url.pathname);
		const form = await request.formData();
		const v = new Validator(form);
		const id = Number(form.get('id') ?? 0) || null;
		const name = v.text('name', F.scheduleName(), { max: 80 });
		const workdays = v.integer('workdays_per_week', F.workdaysPerWeek(), { min: 1, max: 6 });
		if (!v.ok) return fail(400, { errors: validationErrors(v.errors) });

		const frequency = String(form.get('frequency') ?? 'monthly');
		// Cada periodicidad manda su dato de corte y solo ese (RN-94): los demás
		// van en nulo para que el backend no los tome por un formulario mal llenado.
		const cuerpo = {
			name,
			frequency,
			shift: String(form.get('shift') ?? 'day'),
			hours_per_day: numero(form, 'hours_per_day'),
			workdays_per_week: workdays,
			rest_day_paid: form.get('rest_day_paid') === 'on',
			first_cut_day: frequency === 'semimonthly' ? numero(form, 'first_cut_day') : null,
			cut_weekday: frequency === 'weekly' ? numero(form, 'cut_weekday') : null,
			series_start: frequency === 'biweekly' ? texto(form, 'series_start') : null,
			...(id ? { is_active: form.get('is_active') === 'on' } : {})
		};
		try {
			await api<WorkSchedule>(id ? `/payroll/schedules/${id}` : '/payroll/schedules', {
				method: id ? 'PUT' : 'POST',
				token: locals.token,
				body: cuerpo
			});
		} catch (error) {
			return fail(400, { errors: formError(apiMessage(error)) });
		}
		return { success: m.payroll_settings_schedule_saved() };
	},

	puesto: async ({ request, locals, url }) => {
		escribe(locals, url.pathname);
		const form = await request.formData();
		const v = new Validator(form);
		const id = Number(form.get('id') ?? 0) || null;
		const name = v.text('name', F.positionName(), { max: 80 });
		const ccss_code = v.text('ccss_code', F.ccssCode(), { max: 10 });
		const ins_code = v.text('ins_code', F.insCode(), { max: 10 });
		if (!v.ok) return fail(400, { errors: validationErrors(v.errors) });
		try {
			await api<Position>(id ? `/payroll/positions/${id}` : '/payroll/positions', {
				method: id ? 'PUT' : 'POST',
				token: locals.token,
				body: { name, ccss_code, ins_code, ...(id ? { is_active: form.get('is_active') === 'on' } : {}) }
			});
		} catch (error) {
			return fail(400, { errors: formError(apiMessage(error)) });
		}
		return { success: m.payroll_settings_position_saved() };
	},

	poliza: async ({ request, locals, url }) => {
		escribe(locals, url.pathname);
		const form = await request.formData();
		const v = new Validator(form);
		const id = Number(form.get('id') ?? 0) || null;
		const number = id ? '' : v.text('number', F.policyNumber(), { max: 20 });
		// La prima se escribe en porcentaje —1,46— y viaja como fracción —0.0146—,
		// igual que las tasas del país.
		const porcentaje = v.decimal('rt_rate', F.rtRate(), { min: 0.0001, max: 99 });
		if (!v.ok) return fail(400, { errors: validationErrors(v.errors) });
		const is_default = form.get('is_default') === 'on';
		try {
			await api<InsPolicy>(id ? `/payroll/policies/${id}` : '/payroll/policies', {
				method: id ? 'PUT' : 'POST',
				token: locals.token,
				body: id
					? { rt_rate: porcentaje / 100, is_default }
					: { number, rt_rate: porcentaje / 100, is_default }
			});
		} catch (error) {
			return fail(400, { errors: formError(apiMessage(error)) });
		}
		return { success: m.payroll_settings_policy_saved() };
	}
};
