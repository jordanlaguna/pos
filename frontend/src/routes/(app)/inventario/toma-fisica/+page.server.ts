import { fail, redirect } from '@sveltejs/kit';
import { api, apiSafe } from '$lib/server/api';
import { requireAdmin, requireModule } from '$lib/server/auth';
import { formError, Validator } from '$lib/application/validation';
import type { Category, StockCount } from '$lib/domain/types';
import { F } from '$lib/ui/fields';
import { apiMessage, validationErrors } from '$lib/ui/messages';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ locals, url }) => {
	requireAdmin(locals, url.pathname);
	const token = locals.token;
	const [counts, categories] = await Promise.all([
		apiSafe<StockCount[]>('/inventory/counts', [], { token }),
		apiSafe<Category[]>('/categories/categories_list', [], { token })
	]);
	return {
		counts,
		categories: categories.filter((c) => c.is_active !== false),
		available: Array.isArray(counts)
	};
};

export const actions: Actions = {
	/** Abre la toma: de toda la sucursal o de una categoría con sus hijas (RN-100). */
	abrir: async ({ request, locals, url }) => {
		requireAdmin(locals, url.pathname);
		requireModule(locals, 'inventory', url.pathname);
		const form = await request.formData();
		const v = new Validator(form);
		// En blanco es toda la sucursal: no es un campo que falte, es un valor.
		const categoryId =
			String(form.get('category_id') ?? '').trim() === ''
				? null
				: v.integer('category_id', F.category(), { min: 1 });
		const notes = v.text('notes', F.notes(), { required: false, max: 255 }) || null;
		if (!v.ok) return fail(400, { errors: validationErrors(v.errors) });

		let countId: number;
		try {
			const result = await api<{ id_count: number }>('/inventory/counts', {
				method: 'POST',
				token: locals.token,
				body: { category_id: categoryId, notes }
			});
			countId = result.id_count;
		} catch (error) {
			return fail(400, { errors: formError(apiMessage(error)) });
		}
		redirect(303, `/inventario/toma-fisica/${countId}?abierta=1`);
	}
};
