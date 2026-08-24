import { fail } from '@sveltejs/kit';
import { api } from '$lib/server/api';
import { requireAdmin } from '$lib/server/auth';
import { formError, Validator } from '$lib/application/validation';
import { buildTree, childrenOf, moveInOrder } from '$lib/domain/categories';
import type { Category } from '$lib/domain/types';
import { F } from '$lib/ui/fields';
import { m } from '$lib/paraglide/messages.js';
import { apiMessage, validationErrors } from '$lib/ui/messages';
import type { Actions, PageServerLoad } from './$types';

/**
 * Categorías de dos niveles (T-404, T-405; RF-13, RF-14).
 *
 * Es pantalla propia y no el modal que había en el inventario: crear una
 * categoría era un campo, y esto es un árbol que se reordena, se mueve y se
 * desactiva. Meterlo en un modal habría dejado la mitad de RF-13 sin sitio.
 *
 * Todo se aplica en el servidor —`requireAdmin` en el `load` y en cada acción—
 * y el POS no decide nada del árbol: las reglas están en el backend y acá solo
 * se traduce el «no» que devuelve.
 */
export const load: PageServerLoad = async ({ locals, url }) => {
	requireAdmin(locals, url.pathname);

	const categories = await api<Category[]>('/categories/categories_list', {
		token: locals.token
	});
	// Contar productos por categoría es lo que permite decir «no se puede borrar»
	// antes de que alguien lo intente. Sale del catálogo, que ya está cargado.
	const products = await api<{ category_id: number }[]>('/products/products_list', {
		token: locals.token
	});

	const conteo: Record<number, number> = {};
	for (const producto of products) {
		conteo[producto.category_id] = (conteo[producto.category_id] ?? 0) + 1;
	}

	return { categories, tree: buildTree(categories), productCount: conteo };
};

/** El id de la madre, o nulo si el campo vino vacío: eso es una raíz. */
function readParent(v: Validator): number | null {
	const parent = v.integer('parent_id', F.category(), { required: false, min: 1 });
	return parent > 0 ? parent : null;
}

export const actions: Actions = {
	crear: async ({ request, locals, url }) => {
		requireAdmin(locals, url.pathname);
		const v = new Validator(await request.formData());
		const name = v.text('name', F.categoryName(), { max: 100 });
		const parent_id = readParent(v);
		if (!v.ok) return fail(400, { errors: validationErrors(v.errors), action: 'crear' });

		try {
			await api('/categories/register_category', {
				method: 'POST',
				token: locals.token,
				body: { name, parent_id }
			});
		} catch (error) {
			return fail(400, { errors: formError(apiMessage(error)), action: 'crear' });
		}
		return { success: parent_id ? m.categories_created_child() : m.categories_created_root() };
	},

	renombrar: async ({ request, locals, url }) => {
		requireAdmin(locals, url.pathname);
		const v = new Validator(await request.formData());
		const id = v.integer('id', F.category(), { min: 1 });
		const name = v.text('name', F.categoryName(), { max: 100 });
		if (!v.ok) return fail(400, { errors: validationErrors(v.errors), action: 'renombrar' });

		try {
			await api(`/categories/update_category/${id}`, {
				method: 'PUT',
				token: locals.token,
				body: { name }
			});
		} catch (error) {
			return fail(400, { errors: formError(apiMessage(error)), action: 'renombrar' });
		}
		return { success: m.categories_renamed() };
	},

	/**
	 * Mover una subcategoría a otra raíz, o sacarla a raíz (RF-14).
	 *
	 * `parent_id` viaja siempre —vacío significa «pasa a raíz»— porque omitirlo
	 * es lo que el API entiende como «no la toques». La diferencia es la misma
	 * que en el backend y por eso el campo va explícito en el formulario.
	 */
	mover: async ({ request, locals, url }) => {
		requireAdmin(locals, url.pathname);
		const v = new Validator(await request.formData());
		const id = v.integer('id', F.category(), { min: 1 });
		const parent_id = readParent(v);
		if (!v.ok) return fail(400, { errors: validationErrors(v.errors), action: 'mover' });

		try {
			await api(`/categories/update_category/${id}`, {
				method: 'PUT',
				token: locals.token,
				body: { parent_id }
			});
		} catch (error) {
			return fail(400, { errors: formError(apiMessage(error)), action: 'mover' });
		}
		return { success: m.categories_moved() };
	},

	estado: async ({ request, locals, url }) => {
		requireAdmin(locals, url.pathname);
		const form = await request.formData();
		const v = new Validator(form);
		const id = v.integer('id', F.category(), { min: 1 });
		if (!v.ok) return fail(400, { errors: validationErrors(v.errors), action: 'estado' });
		const activar = form.get('is_active') === 'true';

		try {
			await api(`/categories/update_category/${id}`, {
				method: 'PUT',
				token: locals.token,
				body: { is_active: activar }
			});
		} catch (error) {
			return fail(400, { errors: formError(apiMessage(error)), action: 'estado' });
		}
		return { success: activar ? m.categories_activated() : m.categories_deactivated() };
	},

	borrar: async ({ request, locals, url }) => {
		requireAdmin(locals, url.pathname);
		const v = new Validator(await request.formData());
		const id = v.integer('id', F.category(), { min: 1 });
		if (!v.ok) return fail(400, { errors: validationErrors(v.errors), action: 'borrar' });

		try {
			await api(`/categories/delete_category/${id}`, {
				method: 'DELETE',
				token: locals.token
			});
		} catch (error) {
			return fail(400, { errors: formError(apiMessage(error)), action: 'borrar' });
		}
		return { success: m.categories_deleted() };
	},

	/**
	 * Subir o bajar una categoría un lugar.
	 *
	 * El botón manda **la categoría y la dirección**, no el orden entero: sin
	 * JavaScript no hay forma de reordenar en el navegador, y el API pide la
	 * lista completa. Así que el orden nuevo lo arma acá `moveInOrder`, que es
	 * una función pura con su prueba, y se relee la lista antes de moverla para
	 * no mandar un orden viejo si alguien creó una categoría entretanto.
	 */
	ordenar: async ({ request, locals, url }) => {
		requireAdmin(locals, url.pathname);
		const form = await request.formData();
		const v = new Validator(form);
		const id = v.integer('id', F.category(), { min: 1 });
		if (!v.ok) return fail(400, { errors: validationErrors(v.errors), action: 'ordenar' });
		const direction = form.get('direction') === 'up' ? 'up' : 'down';

		try {
			const categories = await api<Category[]>('/categories/categories_list', {
				token: locals.token
			});
			const actual = categories.find((c) => c.id === id);
			if (!actual) return fail(400, { errors: formError(m.api_category_not_found()) });

			const parent_id = actual.parent_id;
			const hermanas =
				parent_id === null
					? buildTree(categories).map((rama) => rama.root.id)
					: childrenOf(categories, parent_id).map((c) => c.id);

			await api('/categories/reorder', {
				method: 'PUT',
				token: locals.token,
				body: { parent_id, ids: moveInOrder(hermanas, id, direction) }
			});
		} catch (error) {
			return fail(400, { errors: formError(apiMessage(error)), action: 'ordenar' });
		}
		return { success: m.categories_reordered() };
	}
};
