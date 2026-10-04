import { fail } from '@sveltejs/kit';
import { api } from '$lib/server/api';
import { formError, Validator } from '$lib/application/validation';
import type { PersonnelAction } from '$lib/domain/payroll';
import { F } from '$lib/ui/fields';
import { m } from '$lib/paraglide/messages.js';
import { apiMessage, validationErrors } from '$lib/ui/messages';

/**
 * Lo que la ficha del empleado y la pantalla de acciones hacen igual (F12):
 * anular y suspender una acción. Una sola copia para que las dos pantallas
 * digan lo mismo del mismo «no».
 */

export async function anularAccion(token: string | null | undefined, form: FormData) {
	const id = Number(form.get('action_id') ?? 0);
	const memo = String(form.get('memo') ?? '').trim() || null;
	try {
		await api<PersonnelAction>(`/payroll/actions/${id}/cancel`, { method: 'POST', token, body: { memo } });
	} catch (error) {
		return fail(400, { errors: formError(apiMessage(error)) });
	}
	return { success: m.payroll_actions_cancelled_ok() };
}

export async function suspenderAccion(token: string | null | undefined, form: FormData) {
	const v = new Validator(form);
	const id = Number(form.get('action_id') ?? 0);
	const reason = v.text('reason', F.reason(), { min: 3, max: 160 });
	if (!v.ok) return fail(400, { errors: validationErrors(v.errors) });
	try {
		await api<PersonnelAction>(`/payroll/actions/${id}/suspend`, { method: 'POST', token, body: { reason } });
	} catch (error) {
		return fail(400, { errors: formError(apiMessage(error)) });
	}
	return { success: m.payroll_actions_suspended_ok() };
}

/** Lo que una acción muestra en una columna: horas, días, monto o salario. */
export function detalleDeAccion(a: PersonnelAction): { hours?: number; days?: number; amount?: number } {
	return {
		...(a.hours != null ? { hours: a.hours } : {}),
		...(a.days != null ? { days: a.days } : {}),
		...(a.amount != null ? { amount: a.amount } : a.new_salary != null ? { amount: a.new_salary } : {})
	};
}
