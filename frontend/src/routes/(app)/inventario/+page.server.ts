import { fail } from '@sveltejs/kit';
import { api, apiSafe, toMessage } from '$lib/server/api';
import { requireAdmin } from '$lib/server/auth';
import { toLocalIso } from '$lib/domain/datetime';
import { formError, Validator } from '$lib/application/validation';
import type { Category, Product } from '$lib/domain/types';
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
		name: v.text('name', 'El nombre', { max: 100 }),
		description: v.text('description', 'La descripción', { max: 255 }),
		price: v.decimal('price', 'El precio', { min: 0 }),
		stock: v.integer('stock', 'El stock', { min: 0 }),
		barcode: v.text('barcode', 'El código de barras', { min: 3, max: 100 }),
		category_id: v.integer('category_id', 'La categoría', { min: 1 })
	};
}

export const actions: Actions = {
	crear: async ({ request, locals, url }) => {
		requireAdmin(locals, url.pathname);
		const v = new Validator(await request.formData());
		const product = readProduct(v);
		if (!v.ok) return fail(400, { errors: v.errors, action: 'crear' });

		try {
			await api('/products/add_product', {
				method: 'POST',
				token: locals.token,
				body: { ...product, created_at: toLocalIso(new Date()) }
			});
		} catch (error) {
			return fail(400, { errors: formError(toMessage(error)), action: 'crear' });
		}
		return { success: 'Producto agregado correctamente.' };
	},

	actualizar: async ({ request, locals, url }) => {
		requireAdmin(locals, url.pathname);
		const form = await request.formData();
		const v = new Validator(form);
		const id = v.integer('id_product', 'El producto', { min: 1 });
		const product = readProduct(v);
		if (!v.ok) return fail(400, { errors: v.errors, action: 'actualizar' });

		try {
			await api(`/products/update_product/${id}`, {
				method: 'PUT',
				token: locals.token,
				body: product
			});
		} catch (error) {
			return fail(400, { errors: formError(toMessage(error)), action: 'actualizar' });
		}
		return { success: 'Producto actualizado correctamente.' };
	},

	eliminar: async ({ request, locals, url }) => {
		requireAdmin(locals, url.pathname);
		const v = new Validator(await request.formData());
		const id = v.integer('id_product', 'El producto', { min: 1 });
		if (!v.ok) return fail(400, { errors: v.errors, action: 'eliminar' });

		try {
			await api(`/products/delete_product/${id}`, { method: 'DELETE', token: locals.token });
		} catch (error) {
			return fail(400, { errors: formError(toMessage(error)), action: 'eliminar' });
		}
		return { success: 'Producto eliminado.' };
	},

	crearCategoria: async ({ request, locals, url }) => {
		requireAdmin(locals, url.pathname);
		const v = new Validator(await request.formData());
		const name = v.text('name', 'El nombre de la categoría', { max: 100 });
		if (!v.ok) return fail(400, { errors: v.errors, action: 'categoria' });

		try {
			await api('/categories/register_category', {
				method: 'POST',
				token: locals.token,
				body: { name }
			});
		} catch (error) {
			return fail(400, { errors: formError(toMessage(error)), action: 'categoria' });
		}
		return { success: 'Categoría creada.' };
	}
};
