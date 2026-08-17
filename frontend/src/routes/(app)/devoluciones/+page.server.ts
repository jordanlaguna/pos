import { fail, redirect } from '@sveltejs/kit';
import { api, apiSafe, toMessage } from '$lib/server/api';
import { requireUser } from '$lib/server/auth';
import { formError, Validator } from '$lib/application/validation';
import type { Sale, SaleDetail, SaleReturn } from '$lib/domain/types';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ locals, url }) => {
	requireUser(locals, url.pathname);
	const token = locals.token;
	const saleParam = url.searchParams.get('venta');

	const [returns, sales] = await Promise.all([
		apiSafe<SaleReturn[]>('/returns/returns_list', [], { token }),
		apiSafe<Sale[]>('/sales/sales_list', [], { token })
	]);

	let selected: SaleDetail | null = null;
	let alreadyReturned: Record<number, number> = {};

	if (saleParam) {
		const id = Number(saleParam);
		selected = await apiSafe<SaleDetail | null>(`/sales/sale/${id}`, null, { token });

		// Lo ya devuelto se descuenta para no permitir devolver dos veces lo mismo.
		if (selected) {
			for (const previous of returns.filter((r) => r.sale_id === id)) {
				for (const item of previous.items) {
					alreadyReturned[item.id_product] =
						(alreadyReturned[item.id_product] ?? 0) + item.quantity;
				}
			}
		}
	}

	sales.sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)));

	return {
		returns,
		// Solo se ofrecen ventas que aún tengan algo por devolver.
		sales: sales.filter((s) => !returns.some((r) => r.sale_id === s.id && r.is_full)).slice(0, 200),
		selected,
		alreadyReturned
	};
};

export const actions: Actions = {
	crear: async ({ request, locals, url }) => {
		const user = requireUser(locals, url.pathname);
		const form = await request.formData();
		const v = new Validator(form);
		const saleId = v.integer('sale_id', 'La venta', { min: 1 });
		const reason = v.text('reason', 'El motivo', { max: 255 });
		if (!v.ok) return fail(400, { errors: v.errors });

		// Los campos vienen como `cantidad_<id_producto>`; se toman los mayores que cero.
		const items: { id_product: number; quantity: number }[] = [];
		for (const [key, value] of form.entries()) {
			if (!key.startsWith('cantidad_')) continue;
			const idProduct = Number(key.slice('cantidad_'.length));
			const quantity = Math.trunc(Number(value));
			if (Number.isInteger(idProduct) && quantity > 0) {
				items.push({ id_product: idProduct, quantity });
			}
		}

		if (!items.length) {
			return fail(400, {
				errors: formError('Indicá al menos un producto con cantidad mayor que cero.')
			});
		}

		let returnId: number;
		try {
			const result = await api<{ id_return: number }>('/returns/add_return', {
				method: 'POST',
				token: locals.token,
				body: { sale_id: saleId, user_id: user.id_user, reason, items }
			});
			returnId = result.id_return;
		} catch (error) {
			return fail(400, { errors: formError(toMessage(error)) });
		}

		redirect(303, `/devoluciones?creada=${returnId}`);
	}
};
