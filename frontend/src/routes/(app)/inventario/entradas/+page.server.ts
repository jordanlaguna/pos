import { fail } from '@sveltejs/kit';
import { api, apiSafe } from '$lib/server/api';
import { requireAdmin, requireWrite } from '$lib/server/auth';
import { reintentarComprobante } from '$lib/server/fe';
import { formError, Validator } from '$lib/application/validation';
import type { DocumentFile, StockEntry } from '$lib/domain/types';
import { F } from '$lib/ui/fields';
import { m } from '$lib/paraglide/messages.js';
import { apiMessage, validationErrors } from '$lib/ui/messages';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ locals, url }) => {
	requireAdmin(locals, url.pathname);
	const entries = await apiSafe<StockEntry[]>('/inventory/entries', [], {
		token: locals.token
	});
	// El expediente ante Hacienda de cada factura de compra (T-728): son pocas
	// —solo las compras a no contribuyentes— y la pantalla las abre en su
	// detalle. Con `apiSafe`, como la factura: un backend anterior a F7 no lo
	// tiene y la lista se abre igual.
	const expedientes: Record<number, DocumentFile | null> = {};
	await Promise.all(
		entries
			.filter((e) => e.einvoice?.id)
			.map(async (e) => {
				expedientes[e.id] = await apiSafe<DocumentFile | null>(
					`/fe/documents/${e.einvoice!.id}`,
					null,
					{ token: locals.token }
				);
			})
	);
	return {
		entries,
		expedientes,
		/** Sin el endpoint, el backend no tiene el módulo de entradas aplicado. */
		available: Array.isArray(entries)
	};
};

export const actions: Actions = {
	/** RF-36: vuelve a la cola la factura de compra detenida. */
	reintentar: async ({ request, locals, url }) => {
		requireWrite(requireAdmin(locals, url.pathname));
		return reintentarComprobante(locals.token, await request.formData());
	},
	anular: async ({ request, locals, url }) => {
		requireAdmin(locals, url.pathname);
		const form = await request.formData();
		const v = new Validator(form);
		const id = v.integer('id_entry', F.entry(), { min: 1 });
		if (!v.ok) return fail(400, { errors: validationErrors(v.errors) });

		// El motivo va siempre que venga. Quién lo exige es el backend, y solo
		// para una compra (RF-46): una entrada nunca lo pidió y seguir
		// pidiéndoselo acá sería inventar una regla que no existe.
		const reason = String(form.get('reason') ?? '').trim() || null;

		try {
			await api(`/inventory/entry/${id}/cancel`, {
				method: 'POST',
				token: locals.token,
				body: { reason }
			});
		} catch (error) {
			return fail(400, { errors: formError(apiMessage(error)) });
		}
		return { success: m.entries_cancelled_ok() };
	}
};
