import { fail } from '@sveltejs/kit';
import { api, apiSafe } from '$lib/server/api';
import { requireUser } from '$lib/server/auth';
import { formError, Validator } from '$lib/application/validation';
import type { CashSessionReport } from '$lib/domain/types';
import { F } from '$lib/ui/fields';
import { m } from '$lib/paraglide/messages.js';
import { apiMessage, validationErrors } from '$lib/ui/messages';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ locals, url }) => {
	const user = requireUser(locals, url.pathname);
	const token = locals.token;

	const [current, history] = await Promise.all([
		apiSafe<CashSessionReport | null>('/cash/current', null, {
			token,
			query: { user_id: user.id_user }
		}),
		apiSafe<CashSessionReport[]>('/cash/sessions', [], {
			token,
			// El admin ve todos los turnos; el cajero solo los suyos.
			query: user.role === 'admin' ? {} : { user_id: user.id_user }
		})
	]);

	return { current, history };
};

export const actions: Actions = {
	abrir: async ({ request, locals, url }) => {
		const user = requireUser(locals, url.pathname);
		const v = new Validator(await request.formData());
		const openingAmount = v.decimal('opening_amount', F.openingAmount(), { min: 0 });
		const notes = v.text('notes', F.notes(), { required: false, max: 255 });
		if (!v.ok) return fail(400, { errors: validationErrors(v.errors) });

		try {
			await api('/cash/open', {
				method: 'POST',
				token: locals.token,
				body: { user_id: user.id_user, opening_amount: openingAmount, notes }
			});
		} catch (error) {
			return fail(400, { errors: formError(apiMessage(error)) });
		}
		return { success: m.cash_opened() };
	},

	movimiento: async ({ request, locals, url }) => {
		const user = requireUser(locals, url.pathname);
		const v = new Validator(await request.formData());
		const type = v.oneOf('type', F.movementType(), ['entrada', 'salida'] as const);
		const amount = v.decimal('amount', F.amount(), { min: 0.01 });
		const reason = v.text('reason', F.reason(), { max: 255 });
		if (!v.ok) return fail(400, { errors: validationErrors(v.errors) });

		try {
			await api('/cash/movement', {
				method: 'POST',
				token: locals.token,
				body: { user_id: user.id_user, type, amount, reason }
			});
		} catch (error) {
			return fail(400, { errors: formError(apiMessage(error)) });
		}
		return { success: `Movimiento de ${type} registrado.` };
	},

	cerrar: async ({ request, locals, url }) => {
		const user = requireUser(locals, url.pathname);
		const v = new Validator(await request.formData());
		const closingAmount = v.decimal('closing_amount', F.closingAmount(), { min: 0 });
		const notes = v.text('notes', F.notes(), { required: false, max: 255 });
		if (!v.ok) return fail(400, { errors: validationErrors(v.errors) });

		try {
			const report = await api<CashSessionReport>('/cash/close', {
				method: 'POST',
				token: locals.token,
				body: { user_id: user.id_user, closing_amount: closingAmount, notes }
			});
			return { success: m.cash_closed_done(), closedSessionId: report.id };
		} catch (error) {
			return fail(400, { errors: formError(apiMessage(error)) });
		}
	}
};
