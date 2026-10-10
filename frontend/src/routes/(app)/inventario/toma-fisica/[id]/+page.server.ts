import { error, fail } from '@sveltejs/kit';
import { api } from '$lib/server/api';
import { requireAdmin, requireModule, requireUser } from '$lib/server/auth';
import { formError, Validator } from '$lib/application/validation';
import type { Product, StockCount } from '$lib/domain/types';
import { F } from '$lib/ui/fields';
import { m } from '$lib/paraglide/messages.js';
import { apiMessage, validationErrors } from '$lib/ui/messages';
import type { Actions, PageServerLoad } from './$types';

function idDeLaRuta(id: string): number {
	const n = Number(id);
	if (!Number.isInteger(n) || n < 1) error(404, m.api_count_not_found());
	return n;
}

/**
 * Contar lo puede hacer un cajero (RN-100): es quien está en el piso con el
 * lector. Abrir, aplicar y descartar son del administrador, y el backend lo
 * vuelve a comprobar (RNF-1).
 */
export const load: PageServerLoad = async ({ locals, url, params }) => {
	const user = requireUser(locals, url.pathname);
	const id = idDeLaRuta(params.id);
	const token = locals.token;
	const [count, products] = await Promise.all([
		api<StockCount>(`/inventory/counts/${id}`, { token }),
		api<Product[]>('/products/products_list', { token })
	]);
	return { count, products, isAdmin: user.role === 'admin' };
};

export const actions: Actions = {
	contar: async ({ request, locals, url, params }) => {
		requireUser(locals, url.pathname);
		requireModule(locals, 'inventory', url.pathname);
		const id = idDeLaRuta(params.id);
		const v = new Validator(await request.formData());
		const productId = v.integer('id_product', F.product(), { min: 1 });
		const counted = v.integer('counted_qty', F.quantity(), { min: 0 });
		if (!v.ok) return fail(400, { errors: validationErrors(v.errors), action: 'contar' });

		try {
			await api(`/inventory/counts/${id}/lines`, {
				method: 'PUT',
				token: locals.token,
				body: { id_product: productId, counted_qty: counted }
			});
		} catch (err) {
			return fail(400, { errors: formError(apiMessage(err)), action: 'contar' });
		}
		return { success: m.count_recorded(), action: 'contar' };
	},

	aplicar: async ({ locals, url, params }) => {
		requireAdmin(locals, url.pathname);
		requireModule(locals, 'inventory', url.pathname);
		const id = idDeLaRuta(params.id);
		let adjustments = 0;
		try {
			const result = await api<{ adjustments: number }>(`/inventory/counts/${id}/apply`, {
				method: 'POST',
				token: locals.token
			});
			adjustments = result.adjustments;
		} catch (err) {
			return fail(400, { errors: formError(apiMessage(err)), action: 'aplicar' });
		}
		return {
			success: m.count_applied(),
			detail: m.count_applied_detail({ adjustments }),
			action: 'aplicar'
		};
	},

	descartar: async ({ locals, url, params }) => {
		requireAdmin(locals, url.pathname);
		requireModule(locals, 'inventory', url.pathname);
		const id = idDeLaRuta(params.id);
		try {
			await api(`/inventory/counts/${id}/discard`, { method: 'POST', token: locals.token });
		} catch (err) {
			return fail(400, { errors: formError(apiMessage(err)), action: 'descartar' });
		}
		return { success: m.count_discarded(), action: 'descartar' };
	}
};
