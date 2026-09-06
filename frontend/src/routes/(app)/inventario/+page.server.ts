import { fail } from '@sveltejs/kit';
import { api, apiSafe } from '$lib/server/api';
import { requireAdmin } from '$lib/server/auth';
import { loadSettings } from '$lib/server/settings';
import { CABYS_CODE_LENGTH } from '$lib/domain/cabys';
import { rateFromPercent } from '$lib/domain/money';
import { toLocalIso } from '$lib/domain/datetime';
import { formError, Validator } from '$lib/application/validation';
import type { Category, Product } from '$lib/domain/types';
import { F } from '$lib/ui/fields';
import { m } from '$lib/paraglide/messages.js';
import { apiMessage, validationErrors } from '$lib/ui/messages';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ locals, url }) => {
	const admin = requireAdmin(locals, url.pathname);
	const token = locals.token;

	const [products, categories, stored] = await Promise.all([
		api<Product[]>('/products/products_list', { token }),
		apiSafe<Category[]>('/categories/categories_list', [], { token }),
		loadSettings(token, admin.company_id)
	]);

	// La tasa configurada es **el valor por omisión de un producto nuevo**
	// (RN-9), no la del sistema: la ficha la propone y quien clasifica decide.
	// Se lee acá y no del estado de módulo de `money.ts` porque en un `load`
	// todavía no corrió el layout que lo fija.
	return { products, categories, defaultTaxRate: stored.settings.tax.rate };
};

/**
 * La tarifa del producto, leída del formulario en **porcentaje**.
 *
 * Devuelve `null` cuando el campo viene en blanco, y eso es un valor: significa
 * «la tasa configurada del negocio» (RN-9). Por eso se mira la cadena cruda y no
 * el número: `v.decimal` devuelve 0 en un campo vacío, y 0 % es una exoneración
 * de verdad —un libro infantil— que no se puede confundir con no haber elegido.
 */
function readTaxRate(v: Validator, form: FormData): number | null {
	if (String(form.get('tax_rate') ?? '').trim() === '') return null;
	return rateFromPercent(v.decimal('tax_rate', F.taxRate(), { min: 0, max: 100 }));
}

/** Campos comunes al alta y la edición de un producto. */
function readProduct(v: Validator, form: FormData) {
	return {
		name: v.text('name', F.name(), { max: 100 }),
		description: v.text('description', F.description(), { max: 255 }),
		price: v.decimal('price', F.price(), { min: 0 }),
		stock: v.integer('stock', F.stock(), { min: 0 }),
		barcode: v.text('barcode', F.barcode(), { min: 3, max: 100 }),
		category_id: v.integer('category_id', F.category(), { min: 1 }),
		// Sin clasificar es un estado legítimo: el catálogo heredado llega así y
		// se clasifica después, en lote (RF-20). Trece dígitos exactos si viene.
		cabys_code:
			v.digits('cabys_code', F.cabysCode(), {
				required: false,
				min: CABYS_CODE_LENGTH,
				max: CABYS_CODE_LENGTH
			}) || null,
		tax_rate: readTaxRate(v, form)
	};
}

export const actions: Actions = {
	crear: async ({ request, locals, url }) => {
		requireAdmin(locals, url.pathname);
		const form = await request.formData();
		const v = new Validator(form);
		const product = readProduct(v, form);
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
		return { success: m.inventory_created() };
	},

	actualizar: async ({ request, locals, url }) => {
		requireAdmin(locals, url.pathname);
		const form = await request.formData();
		const v = new Validator(form);
		const id = v.integer('id_product', F.product(), { min: 1 });
		const product = readProduct(v, form);
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
		return { success: m.inventory_updated() };
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
		return { success: m.inventory_deleted() };
	}
};
