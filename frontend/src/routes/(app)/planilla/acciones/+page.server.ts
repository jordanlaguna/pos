import { fail } from '@sveltejs/kit';
import { api, apiSafe, toLog } from '$lib/server/api';
import { requireAdmin, requireModule } from '$lib/server/auth';
import { anularAccion, suspenderAccion } from '$lib/server/payroll';
import { formError, Validator } from '$lib/application/validation';
import { REGISTRABLE_KINDS, type Employee, type PersonnelAction, type Position } from '$lib/domain/payroll';
import { F } from '$lib/ui/fields';
import { m } from '$lib/paraglide/messages.js';
import { apiMessage, validationErrors } from '$lib/ui/messages';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ locals, url }) => {
	requireAdmin(locals, url.pathname);
	const token = locals.token;
	const empleado = Number(url.searchParams.get('empleado') ?? 0) || null;
	const [employees, positions, history] = await Promise.all([
		apiSafe<Employee[]>('/payroll/employees', [], { token }),
		apiSafe<Position[]>('/payroll/positions', [], { token }),
		empleado
			? apiSafe<PersonnelAction[]>(`/payroll/employees/${empleado}/actions`, [], { token })
			: Promise.resolve([] as PersonnelAction[])
	]);
	return {
		employees: employees.filter((e) => e.is_active),
		positions: positions.filter((p) => p.is_active),
		empleado,
		history: [...history].reverse()
	};
};

function escribe(locals: App.Locals, pathname: string) {
	requireAdmin(locals, pathname);
	requireModule(locals, 'payroll', pathname);
}

function numero(form: FormData, campo: string): number | null {
	const crudo = String(form.get(campo) ?? '').trim();
	return crudo === '' ? null : Number(crudo);
}

export const actions: Actions = {
	registrar: async ({ request, locals, url }) => {
		escribe(locals, url.pathname);
		const form = await request.formData();
		const v = new Validator(form);
		const empleados = form.getAll('employee_id').map(Number).filter(Boolean);
		if (!empleados.length) v.text('employee_id', F.employee());
		const kind = String(form.get('kind') ?? '');
		const starts_on = v.date('starts_on', F.startsOn());
		if (!v.ok) return fail(400, { errors: validationErrors(v.errors) });
		if (!(REGISTRABLE_KINDS as readonly string[]).includes(kind)) {
			// El mismo «no» que daría el backend: el desplegable no lo produce, pero
			// un formulario enviado a mano sí.
			return fail(400, {
				errors: formError(apiMessage({ status: 400, code: 'invalid_action', data: { field: 'kind', reason: 'unknown' } }))
			});
		}

		const cuerpo = {
			kind,
			starts_on,
			ends_on: String(form.get('ends_on') ?? '').trim() || null,
			hours: numero(form, 'hours'),
			days: numero(form, 'days'),
			amount: numero(form, 'amount'),
			total_amount: numero(form, 'total_amount'),
			new_salary: numero(form, 'new_salary'),
			position_id: numero(form, 'position_id'),
			is_recurring: form.get('is_recurring') === 'on',
			memo: String(form.get('memo') ?? '').trim() || null
		};
		// Una por empleado, en orden. Si una falla, las anteriores ya quedaron: se
		// dice cuál falló y por qué, y las demás se vuelven a intentar sin ella.
		let hechas = 0;
		for (const employee_id of empleados) {
			try {
				await api<PersonnelAction>('/payroll/actions', { method: 'POST', token: locals.token, body: { employee_id, ...cuerpo } });
				hechas += 1;
			} catch (error) {
				console.error(`acción para el empleado ${employee_id}: ${toLog(error)}`);
				return fail(400, { errors: formError(apiMessage(error)), hechas });
			}
		}
		return {
			success: hechas === 1 ? m.payroll_actions_registered() : m.payroll_actions_registered_many({ count: hechas })
		};
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
