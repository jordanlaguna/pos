import { error, fail, redirect } from '@sveltejs/kit';
import { api, apiSafe, ApiError } from '$lib/server/api';
import { requireAdmin, requireModule } from '$lib/server/auth';
import { anularAccion, suspenderAccion } from '$lib/server/payroll';
import { formError, Validator } from '$lib/application/validation';
import type {
	Employee,
	EmploymentContract,
	InsPolicy,
	PersonnelAction,
	Position,
	Vacations,
	WorkSchedule
} from '$lib/domain/payroll';
import { F } from '$lib/ui/fields';
import { m } from '$lib/paraglide/messages.js';
import { apiMessage, validationErrors } from '$lib/ui/messages';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ locals, url, params }) => {
	requireAdmin(locals, url.pathname);
	const token = locals.token;
	const id = Number(params.id);
	let employee: Employee;
	try {
		employee = await api<Employee>(`/payroll/employees/${id}`, { token });
	} catch (e) {
		if (e instanceof ApiError && e.status === 404) error(404, { code: e.code });
		throw e;
	}
	const [contracts, history, vacations, schedules, positions, policies] = await Promise.all([
		apiSafe<EmploymentContract[]>(`/payroll/contracts?employee=${id}`, [], { token }),
		apiSafe<PersonnelAction[]>(`/payroll/employees/${id}/actions`, [], { token }),
		apiSafe<Vacations | null>(`/payroll/vacations/${id}`, null, { token }),
		apiSafe<WorkSchedule[]>('/payroll/schedules', [], { token }),
		apiSafe<Position[]>('/payroll/positions', [], { token }),
		apiSafe<InsPolicy[]>('/payroll/policies', [], { token })
	]);
	return { employee, contracts, history: [...history].reverse(), vacations, schedules, positions, policies };
};

function escribe(locals: App.Locals, pathname: string) {
	requireAdmin(locals, pathname);
	requireModule(locals, 'payroll', pathname);
}

export const actions: Actions = {
	contrato: async ({ request, locals, url, params }) => {
		escribe(locals, url.pathname);
		const form = await request.formData();
		const v = new Validator(form);
		const valid_from = v.date('valid_from', F.validFrom());
		const period_salary = v.decimal('period_salary', F.periodSalary(), { min: 0.01 });
		if (!v.ok) return fail(400, { errors: validationErrors(v.errors) });
		const solidarista = String(form.get('solidarista_rate') ?? '').trim();
		try {
			await api<EmploymentContract>('/payroll/contracts', {
				method: 'POST',
				token: locals.token,
				body: {
					employee_id: Number(params.id),
					schedule_id: Number(form.get('schedule_id')),
					position_id: Number(form.get('position_id')),
					ins_policy_id: Number(form.get('ins_policy_id') ?? 0) || null,
					valid_from,
					period_salary,
					// En porcentaje en la pantalla, como fracción en el API.
					solidarista_rate: solidarista ? Number(solidarista) / 100 : null
				}
			});
		} catch (e) {
			return fail(400, { errors: formError(apiMessage(e)) });
		}
		return { success: m.payroll_employee_contract_saved() };
	},

	baja: async ({ request, locals, url, params }) => {
		escribe(locals, url.pathname);
		const form = await request.formData();
		const v = new Validator(form);
		const terminated_on = v.date('terminated_on', F.terminatedOn());
		if (!v.ok) return fail(400, { errors: validationErrors(v.errors) });
		let liquidacion: number;
		try {
			const salida = await api<{ settlement_run_id: number }>(`/payroll/employees/${params.id}/terminate`, {
				method: 'POST',
				token: locals.token,
				body: { terminated_on, cause: String(form.get('cause') ?? '') }
			});
			liquidacion = salida.settlement_run_id;
		} catch (e) {
			return fail(400, { errors: formError(apiMessage(e)) });
		}
		// Redirección del servidor y no un `goto` en el cliente: `use:enhance`
		// aplica el resultado después del callback y esa actualización cancelaba
		// la navegación que acababa de empezar; la persona se quedaba en la ficha.
		redirect(303, `/planilla/corridas/${liquidacion}`);
	},

	anular: async ({ request, locals, url }) => {
		escribe(locals, url.pathname);
		return anularAccion(locals.token, await request.formData());
	},

	suspender: async ({ request, locals, url }) => {
		escribe(locals, url.pathname);
		return suspenderAccion(locals.token, await request.formData());
	}
};
