import { fail } from '@sveltejs/kit';
import { api, apiSafe } from '$lib/server/api';
import { requireAdmin } from '$lib/server/auth';
import { loadSettings } from '$lib/server/settings';
import { CABYS_CODE_LENGTH } from '$lib/domain/cabys';
import { rateFromPercent } from '$lib/domain/money';
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

	return { products, categories, defaultTaxRate: stored.settings.tax.rate };
};

export const actions: Actions = {
	/**
	 * Le pone el mismo CABYS —y su tarifa— a los productos marcados (RF-20).
	 *
	 * Los identificadores llegan como casillas repetidas, así que se leen con
	 * `getAll` y no por el `Validator`: ese aplana el formulario con
	 * `Object.fromEntries` y de una casilla marcada cien veces solo sobrevive la
	 * última.
	 */
	asignar: async ({ request, locals, url }) => {
		requireAdmin(locals, url.pathname);
		const form = await request.formData();
		const v = new Validator(form);

		const cabys_code = v.digits('cabys_code', F.cabysCode(), {
			min: CABYS_CODE_LENGTH,
			max: CABYS_CODE_LENGTH
		});
		const tax_rate = rateFromPercent(v.decimal('tax_rate', F.taxRate(), { min: 0, max: 100 }));
		if (!v.ok) return fail(400, { errors: validationErrors(v.errors) });

		const product_ids = form
			.getAll('ids')
			.map((raw) => Number(raw))
			.filter((id) => Number.isInteger(id) && id > 0);
		if (product_ids.length === 0) {
			return fail(400, { errors: formError(m.inventory_classify_pick_products()) });
		}

		try {
			await api('/products/assign_cabys', {
				method: 'PUT',
				token: locals.token,
				body: { product_ids, cabys_code, tax_rate }
			});
		} catch (error) {
			return fail(400, { errors: formError(apiMessage(error)) });
		}
		return { success: m.inventory_classify_done({ count: product_ids.length }) };
	}
};
