import { fail } from '@sveltejs/kit';
import { api, apiSafe } from '$lib/server/api';
import { requireAdmin } from '$lib/server/auth';
import { toLocalIso } from '$lib/domain/datetime';
import { formError, Validator } from '$lib/application/validation';
import type { Category, Product } from '$lib/domain/types';
import { F } from '$lib/ui/fields';
import { apiMessage, validationErrors } from '$lib/ui/messages';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ locals, url }) => {
	requireAdmin(locals, url.pathname);
	const token = locals.token;

	const [products, categories] = await Promise.all([
		api<Product[]>('/products/products_list', { token }),
		apiSafe<Category[]>('/categories/categories_list', [], { token })
	]);

	return { products, categories };
};

/** Campos comunes al alta y la edición de un producto. */
function readProduct(v: Validator) {
	return {
		name: v.text('name', F.name(), { max: 100 }),
		description: v.text('description', F.description(), { max: 255 }),
		price: v.decimal('price', F.price(), { min: 0 }),
		stock: v.integer('stock', F.stock(), { min: 0 }),
		barcode: v.text('barcode', F.barcode(), { min: 3, max: 100 }),
		category_id: v.integer('category_id', F.category(), { min: 1 })
	};
}

export const actions: Actions = {
	crear: async ({ request, locals, url }) => {
		requireAdmin(locals, url.pathname);
		const v = new Validator(await request.formData());
		const product = readProduct(v);
		if (!v.ok) return fail(400, { errors: validationErrors(v.errors), action: 'crear' });

		try {
			await api('/products/add_product', {
				method: 'POST',
				token: locals.token,
				body: { ...product, created_at: toLocalIso(new Date()) }
			});
		} catch (error) {
			return fail(400, { errors: formError(apiMessage(error)), action: 'crear' });
		}
		return { success: 'Producto agregado correctamente.' };
	},

	actualizar: async ({ request, locals, url }) => {
		requireAdmin(locals, url.pathname);
		const form = await request.formData();
		const v = new Validator(form);
		const id = v.integer('id_product', F.product(), { min: 1 });
		const product = readProduct(v);
		if (!v.ok) return fail(400, { errors: validationErrors(v.errors), action: 'actualizar' });

		try {
			await api(`/products/update_product/${id}`, {
				method: 'PUT',
				token: locals.token,
				body: product
			});
		} catch (error) {
			return fail(400, { errors: formError(apiMessage(error)), action: 'actualizar' });
		}
		return { success: 'Producto actualizado correctamente.' };
	},

	eliminar: async ({ request, locals, url }) => {
		requireAdmin(locals, url.pathname);
		const v = new Validator(await request.formData());
		const id = v.integer('id_product', F.product(), { min: 1 });
		if (!v.ok) return fail(400, { errors: validationErrors(v.errors), action: 'eliminar' });

		try {
			await api(`/products/delete_product/${id}`, { method: 'DELETE', token: locals.token });
		} catch (error) {
			return fail(400, { errors: formError(apiMessage(error)), action: 'eliminar' });
		}
		return { success: 'Producto eliminado.' };
	},

	crearCategoria: async ({ request, locals, url }) => {
		requireAdmin(locals, url.pathname);
		const v = new Validator(await request.formData());
		const name = v.text('name', F.categoryName(), { max: 100 });
		if (!v.ok) return fail(400, { errors: validationErrors(v.errors), action: 'categoria' });

		try {
			await api('/categories/register_category', {
				method: 'POST',
				token: locals.token,
				body: { name }
			});
		} catch (error) {
			return fail(400, { errors: formError(apiMessage(error)), action: 'categoria' });
		}
		return { success: 'Categoría creada.' };
	}
};
