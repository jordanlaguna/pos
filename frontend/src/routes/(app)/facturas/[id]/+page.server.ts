import { error } from '@sveltejs/kit';
import { api, apiSafe, ApiError } from '$lib/server/api';
import { requireUser } from '$lib/server/auth';
import { USE_MOCK } from '$lib/server/config';
import type { Client, Product, Sale, SaleDetail, SaleReturn } from '$lib/types';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ locals, params, url }) => {
	requireUser(locals, url.pathname);
	const token = locals.token;
	const id = Number(params.id);
	if (!Number.isInteger(id) || id <= 0) error(404, { message: 'Factura no encontrada.' });

	let sale: SaleDetail;
	try {
		sale = await api<SaleDetail>(`/sales/sale/${id}`, { token });
	} catch (err) {
		if (err instanceof ApiError && err.status === 404) {
			/*
			 * El backend sin el patch de este proyecto no expone el detalle de una
			 * venta. Se reconstruye la cabecera desde el listado para que la factura
			 * siga siendo consultable; las líneas quedan vacías y la página lo dice.
			 */
			const all = await apiSafe<Sale[]>('/sales/sales_list', [], { token });
			const header = all.find((s) => s.id === id);
			if (!header) error(404, { message: 'Factura no encontrada.' });

			sale = {
				...header,
				subtotal: Number((header as any).subtotal ?? 0),
				tax: Number((header as any).tax ?? 0),
				cash_received: Number((header as any).cash_received ?? 0),
				change_given: Number((header as any).change_given ?? 0),
				client_id: (header as any).client_id ?? null,
				user_id: (header as any).user_id ?? null,
				items: []
			};
		} else {
			throw err;
		}
	}

	const [clients, returns, products] = await Promise.all([
		apiSafe<Client[]>('/clients/clients_list', [], { token }),
		apiSafe<SaleReturn[]>('/returns/returns_list', [], { token }),
		apiSafe<Product[]>('/products/products_list', [], { token })
	]);

	const client = sale.client_id
		? (clients.find((c) => c.id_client === sale.client_id) ?? null)
		: null;

	/*
	 * Códigos de barras de las líneas de esta venta. La venta guarda el nombre
	 * del producto pero no su código, y la plantilla puede pedirlo. Solo se
	 * mandan los que hacen falta: el catálogo entero no tiene por qué viajar
	 * hasta el navegador para imprimir cuatro renglones.
	 */
	const barcodes: Record<number, string> = {};
	for (const item of sale.items) {
		const product = products.find((p) => p.id_product === item.id_product);
		if (product?.barcode) barcodes[item.id_product] = product.barcode;
	}

	return {
		sale,
		client,
		barcodes,
		saleReturns: returns.filter((r) => r.sale_id === id),
		/** El PDF del backend no existe en modo demo; ahí se imprime desde el navegador. */
		canDownloadPdf: !USE_MOCK,
		isNew: url.searchParams.get('nueva') === '1'
	};
};
