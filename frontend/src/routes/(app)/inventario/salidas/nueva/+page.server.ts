import { fail, redirect } from '@sveltejs/kit';
import { api, apiSafe } from '$lib/server/api';
import { requireAdmin, requireModule } from '$lib/server/auth';
import { formError, Validator } from '$lib/application/validation';
import type { Product, StockReason } from '$lib/domain/types';
import { F } from '$lib/ui/fields';
import { m } from '$lib/paraglide/messages.js';
import { apiMessage, validationErrors } from '$lib/ui/messages';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ locals, url }) => {
	requireAdmin(locals, url.pathname);
	const token = locals.token;
	const [products, reasons] = await Promise.all([
		api<Product[]>('/products/products_list', { token }),
		apiSafe<StockReason[]>('/inventory/reasons', [], { token })
	]);
	return {
		products,
		// Solo los que se pueden elegir (RN-99, RN-100): activos y de la compañía.
		// El de la toma física lo pone la toma, no la persona.
		reasons: reasons.filter((r) => r.is_active && !r.is_system)
	};
};

export const actions: Actions = {
	/** Aplica la salida: baja existencias al promedio de hoy y deja el kárdex. */
	confirmar: async ({ request, locals, url }) => {
		requireAdmin(locals, url.pathname);
		requireModule(locals, 'inventory', url.pathname);
		const form = await request.formData();
		const v = new Validator(form);
		const reasonId = v.integer('reason_id', F.stockReason(), { min: 1 });
		const notes = v.text('notes', F.notes(), { required: false, max: 255 }) || null;
		if (!v.ok) return fail(400, { errors: validationErrors(v.errors) });

		let lines: unknown;
		try {
			lines = JSON.parse(String(form.get('lines') ?? '[]'));
		} catch {
			return fail(400, { errors: formError(m.exit_lines_unreadable()) });
		}
		if (!Array.isArray(lines) || lines.length === 0) {
			return fail(400, { errors: formError(m.exit_add_line()) });
		}
		// Se relee línea por línea en vez de reenviar lo que mandó el navegador:
		// lo que llega por un formulario es de quien tenga la pantalla abierta.
		const limpias = lines.map((l) => ({
			id_product: Number((l as { id_product?: unknown }).id_product) || 0,
			quantity: Math.trunc(Number((l as { quantity?: unknown }).quantity) || 0)
		}));

		let exitId: number;
		try {
			const result = await api<{ id_exit: number }>('/inventory/exits', {
				method: 'POST',
				token: locals.token,
				body: { reason_id: reasonId, notes, lines: limpias }
			});
			exitId = result.id_exit;
		} catch (error) {
			return fail(400, { errors: formError(apiMessage(error)) });
		}

		redirect(303, `/inventario/salidas?creada=${exitId}`);
	}
};
