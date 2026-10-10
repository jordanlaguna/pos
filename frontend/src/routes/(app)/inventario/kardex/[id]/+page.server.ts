import { error } from '@sveltejs/kit';
import { api, apiSafe } from '$lib/server/api';
import { requireAdmin } from '$lib/server/auth';
import type { Product, StockLevel, StockMovement } from '$lib/domain/types';
import { m } from '$lib/paraglide/messages.js';
import type { PageServerLoad } from './$types';

/**
 * El kárdex de un producto (F15, RF-87): sus movimientos, del más reciente al
 * más viejo, y su existencia por sucursal.
 *
 * El producto sale de la lista del catálogo y no de una ruta por id —no la
 * hay—: es la misma lectura que ya hace la pantalla de inventario.
 */
export const load: PageServerLoad = async ({ locals, url, params }) => {
	requireAdmin(locals, url.pathname);
	const id = Number(params.id);
	if (!Number.isInteger(id) || id < 1) error(404, m.kardex_product_missing());

	const token = locals.token;
	const [products, movements, levels] = await Promise.all([
		api<Product[]>('/products/products_list', { token }),
		apiSafe<StockMovement[]>(`/inventory/kardex?product_id=${id}`, [], { token }),
		apiSafe<StockLevel[]>(`/inventory/levels?product_id=${id}`, [], { token })
	]);
	const product = products.find((p) => p.id_product === id);
	if (!product) error(404, m.kardex_product_missing());

	return { product, movements, levels };
};
