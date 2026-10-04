import { error, fail, redirect } from '@sveltejs/kit';
import { m } from '$lib/paraglide/messages.js';
import { api, apiSafe, ApiError } from '$lib/server/api';
import { requireAdmin, requireUser, requireWrite } from '$lib/server/auth';
import { reintentarComprobante } from '$lib/server/fe';
import { formError, Validator } from '$lib/application/validation';
import { F } from '$lib/ui/fields';
import { apiMessage, validationErrors } from '$lib/ui/messages';
import { CREDIT_NOTE, DEBIT_NOTE } from '$lib/domain/documentType';
import { CORRECTS_AMOUNT } from '$lib/domain/documents';
import type {
	AmountNote,
	Client,
	DocumentFile,
	Product,
	Sale,
	SaleDetail,
	SaleReturn
} from '$lib/domain/types';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ locals, params, url }) => {
	requireUser(locals, url.pathname);
	const token = locals.token;
	const id = Number(params.id);
	if (!Number.isInteger(id) || id <= 0) error(404, { message: m.invoice_not_found() });

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
			if (!header) error(404, { message: m.invoice_not_found() });

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

	const [clients, returns, products, notes] = await Promise.all([
		apiSafe<Client[]>('/clients/clients_list', [], { token }),
		apiSafe<SaleReturn[]>('/returns/returns_list', [], { token }),
		apiSafe<Product[]>('/products/products_list', [], { token }),
		// Las notas por monto (T-726). Con `apiSafe`: un backend anterior no tiene
		// la ruta, y la factura se tiene que poder abrir igual.
		sale.document_type
			? apiSafe<AmountNote[]>(`/notes/by_sale/${id}`, [], { token })
			: Promise.resolve([] as AmountNote[])
	]);

	const client = sale.client_id
		? (clients.find((c) => c.id_client === sale.client_id) ?? null)
		: null;

	// El expediente ante Hacienda (T-721): solo si la venta tiene comprobante, y
	// con `apiSafe` porque un backend anterior a F7 no lo tiene y la factura se
	// abre igual.
	const expediente = sale.einvoice?.id
		? await apiSafe<DocumentFile | null>(`/fe/documents/${sale.einvoice.id}`, null, { token })
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
		saleNotes: notes,
		expediente,
		isNew: url.searchParams.get('nueva') === '1'
	};
};

export const actions: Actions = {
	/** RF-36: vuelve a la cola el comprobante detenido. Solo el administrador. */
	reintentar: async ({ request, locals, url }) => {
		requireWrite(requireAdmin(locals, url.pathname));
		return reintentarComprobante(locals.token, await request.formData());
	},
	/**
	 * Anular el comprobante (RN-89): una devolución entera con motivo «anula».
	 *
	 * Las líneas salen de la venta que el servidor acaba de leer, no del
	 * formulario: anular es devolver **todo**, y dejar que el navegador diga qué
	 * es «todo» sería dejarle decidir qué se reembolsa. El servidor vuelve a
	 * exigir que esté entera y sin devoluciones.
	 */
	anular: async ({ request, locals, params, url }) => {
		const user = requireWrite(requireUser(locals, url.pathname));
		const form = await request.formData();
		const v = new Validator(form);
		const reason = v.text('reason', F.reason(), { max: 255 });
		if (!v.ok) return fail(400, { errors: validationErrors(v.errors) });

		const id = Number(params.id);
		let result: { id_return: number };
		try {
			const venta = await api<SaleDetail>(`/sales/sale/${id}`, { token: locals.token });
			result = await api<{ id_return: number }>('/returns/add_return', {
				method: 'POST',
				token: locals.token,
				body: {
					sale_id: id,
					user_id: user.id_user,
					reason,
					annul: true,
					items: venta.items.map((i) => ({ id_product: i.id_product, quantity: i.quantity }))
				}
			});
		} catch (err) {
			return fail(400, { errors: formError(apiMessage(err)) });
		}

		redirect(303, `/devoluciones/${result.id_return}?nueva=1`);
	},

	/**
	 * Una nota por monto (RF-77, T-726): la ND que se cobra o la NC que se
	 * reembolsa, sin mercadería.
	 *
	 * **Solo el administrador**, como en el servidor: mueve plata sin que nada
	 * vuelva al inventario. Cada línea llega como `monto_<producto>` con el
	 * impuesto incluido; las vacías no cuentan. El servidor la parte en base e
	 * impuesto con la tarifa de la venta y vuelve a comprobar todo.
	 */
	nota: async ({ request, locals, params, url }) => {
		requireWrite(requireAdmin(locals, url.pathname));
		const form = await request.formData();
		const v = new Validator(form);
		const tipo = String(form.get('document_type') ?? '');
		const reason = v.text('reason', F.reason(), { max: 255 });

		const items: { id_product: number; amount: number }[] = [];
		for (const [campo, valor] of form.entries()) {
			const producto = /^monto_(\d+)$/.exec(campo);
			if (!producto || !String(valor).trim()) continue;
			const amount = v.decimal(campo, F.amount(), { min: 0 });
			if (amount > 0) items.push({ id_product: Number(producto[1]), amount });
		}
		if (!v.ok) return fail(400, { errors: validationErrors(v.errors) });

		let result: { id_note: number };
		try {
			result = await api<{ id_note: number }>('/notes/add_note', {
				method: 'POST',
				token: locals.token,
				body: {
					sale_id: Number(params.id),
					document_type: tipo === DEBIT_NOTE ? DEBIT_NOTE : CREDIT_NOTE,
					reference_code: CORRECTS_AMOUNT,
					reason,
					items,
					// La ND se cobra; la NC sale de la gaveta y no lleva medio.
					payment_method: tipo === DEBIT_NOTE ? String(form.get('payment_method') ?? '') : null
				}
			});
		} catch (err) {
			return fail(400, { errors: formError(apiMessage(err)) });
		}

		redirect(303, `/notas/${result.id_note}?nueva=1`);
	}
};
