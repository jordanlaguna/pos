import { error } from '@sveltejs/kit';
import { m } from '$lib/paraglide/messages.js';
import { api, apiSafe, ApiError } from '$lib/server/api';
import { requireUser } from '$lib/server/auth';
import { creditNoteDocument } from '$lib/domain/documents';
import type { Client, SaleReturn } from '$lib/domain/types';
import type { PageServerLoad } from './$types';

/**
 * La nota de crédito de una devolución, lista para imprimir (RN-89, T-725).
 *
 * Solo existe si la venta fue comprobante: una devolución de algo que no se
 * emitió no tiene a qué referirse, y no hay nota que mostrar.
 */
export const load: PageServerLoad = async ({ locals, params, url }) => {
	requireUser(locals, url.pathname);
	const token = locals.token;
	const id = Number(params.id);
	if (!Number.isInteger(id) || id <= 0) error(404, { message: m.credit_note_not_found() });

	let devolucion: SaleReturn;
	try {
		devolucion = await api<SaleReturn>(`/returns/return/${id}`, { token });
	} catch (err) {
		if (err instanceof ApiError && err.status === 404) {
			error(404, { message: m.credit_note_not_found() });
		}
		throw err;
	}

	const nota = creditNoteDocument(devolucion);
	if (!nota) error(404, { message: m.credit_note_not_found() });

	const clients = nota.client_id
		? await apiSafe<Client[]>('/clients/clients_list', [], { token })
		: [];

	return {
		devolucion,
		nota,
		client: clients.find((c) => c.id_client === nota.client_id) ?? null,
		isNew: url.searchParams.get('nueva') === '1'
	};
};
