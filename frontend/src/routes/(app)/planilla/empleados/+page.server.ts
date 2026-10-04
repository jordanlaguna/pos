import { fail } from '@sveltejs/kit';
import { api, apiSafe } from '$lib/server/api';
import { requireAdmin, requireModule } from '$lib/server/auth';
import { formError, Validator } from '$lib/application/validation';
import type { Employee, InsPolicy, Position, WorkSchedule } from '$lib/domain/payroll';
import { F } from '$lib/ui/fields';
import { m } from '$lib/paraglide/messages.js';
import { apiMessage, firstError, validationErrors } from '$lib/ui/messages';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ locals, url }) => {
	requireAdmin(locals, url.pathname);
	const token = locals.token;
	const [employees, schedules, positions, policies] = await Promise.all([
		apiSafe<Employee[]>('/payroll/employees', [], { token }),
		apiSafe<WorkSchedule[]>('/payroll/schedules', [], { token }),
		apiSafe<Position[]>('/payroll/positions', [], { token }),
		apiSafe<InsPolicy[]>('/payroll/policies', [], { token })
	]);
	return {
		employees,
		schedules,
		positions,
		policies,
		inactivos: url.searchParams.get('inactivos') === '1',
		// `?editar=` abre la ficha de uno: es como vuelve la pantalla de detalle.
		editar: Number(url.searchParams.get('editar') ?? 0) || null
	};
};

function texto(form: FormData, campo: string): string | null {
	return String(form.get(campo) ?? '').trim() || null;
}

export const actions: Actions = {
	guardar: async ({ request, locals, url }) => {
		requireAdmin(locals, url.pathname);
		requireModule(locals, 'payroll', url.pathname);
		const form = await request.formData();
		const v = new Validator(form);
		const id = Number(form.get('id') ?? 0) || null;

		const identification = v.text('identification', F.identification(), { max: 30 });
		const first_name = v.text('first_name', F.firstName(), { max: 60 });
		const last_name_1 = v.text('last_name_1', F.lastName1(), { max: 40 });
		const birth_date = v.date('birth_date', F.birthDate(), { notFuture: true });
		const hired_on = v.date('hired_on', F.hiredOn());
		const dependent_children = v.integer('dependent_children', F.dependentChildren(), { min: 0, max: 20 });
		/*
		 * El contrato del alta (RF-55): solo al crear y si se pidió. Va en el mismo
		 * envío porque el backend guarda los dos o ninguno; rige desde el ingreso,
		 * así que no lleva fecha.
		 */
		const conContrato = !id && form.get('con_contrato') === 'on';
		const period_salary = conContrato ? v.decimal('period_salary', F.periodSalary(), { min: 0.01 }) : null;
		// `message`: sin él, `submit` no tiene qué avisar y el error no se ve.
		if (!v.ok) return fail(400, { message: firstError(v.errors), errors: validationErrors(v.errors) });
		const solidarista = String(form.get('solidarista_rate') ?? '').trim();

		const cuerpo = {
			identification_type: String(form.get('identification_type') ?? 'national'),
			identification,
			first_name,
			last_name_1,
			last_name_2: texto(form, 'last_name_2'),
			insured_number: texto(form, 'insured_number'),
			birth_date,
			gender: String(form.get('gender') ?? 'F'),
			marital_status: String(form.get('marital_status') ?? 'single'),
			nationality: (texto(form, 'nationality') ?? 'CR').toUpperCase(),
			phone: texto(form, 'phone'),
			email: texto(form, 'email'),
			is_pensioner: form.get('is_pensioner') === 'on',
			iban: texto(form, 'iban')?.replace(/\s+/g, '').toUpperCase() ?? null,
			hired_on,
			dependent_children,
			spouse_credit: form.get('spouse_credit') === 'on',
			...(conContrato && {
				contract: {
					schedule_id: Number(form.get('schedule_id')),
					position_id: Number(form.get('position_id')),
					ins_policy_id: Number(form.get('ins_policy_id') ?? 0) || null,
					period_salary,
					// En porcentaje en la pantalla, como fracción en el API.
					solidarista_rate: solidarista ? Number(solidarista) / 100 : null
				}
			})
		};
		try {
			await api<Employee>(id ? `/payroll/employees/${id}` : '/payroll/employees', {
				method: id ? 'PUT' : 'POST',
				token: locals.token,
				body: cuerpo
			});
		} catch (error) {
			return fail(400, { errors: formError(apiMessage(error)) });
		}
		return { success: m.payroll_employees_saved() };
	}
};
