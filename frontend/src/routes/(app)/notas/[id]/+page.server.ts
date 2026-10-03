import { error } from '@sveltejs/kit';
import { m } from '$lib/paraglide/messages.js';
import { api, apiSafe, ApiError } from '$lib/server/api';
import { requireUser } from '$lib/server/auth';
import { amountNoteDocument } from '$lib/domain/documents';
import type { AmountNote, Client } from '$lib/domain/types';
import type { PageServerLoad } from './$types';

/**
 * Una nota por monto, lista para imprimir (RF-77, T-726).
 *
 * Se imprime como la nota de crédito de una devolución: con la plantilla
 * configurada, en el idioma de la compañía y con la referencia al original.
 */
export const load: PageServerLoad = async ({ locals, params, url }) => {
	requireUser(locals, url.pathname);
	const token = locals.token;
	const id = Number(params.id);
	if (!Number.isInteger(id) || id <= 0) error(404, { message: m.amount_note_not_found() });

	let nota: AmountNote;
	try {
		nota = await api<AmountNote>(`/notes/note/${id}`, { token });
	} catch (err) {
		if (err instanceof ApiError && err.status === 404) {
			error(404, { message: m.amount_note_not_found() });
		}
		throw err;
	}

	const documento = amountNoteDocument(nota);
	const clients = documento.client_id
		? await apiSafe<Client[]>('/clients/clients_list', [], { token })
		: [];

	return {
		nota,
		documento,
		client: clients.find((c) => c.id_client === documento.client_id) ?? null,
		isNew: url.searchParams.get('nueva') === '1'
	};
};
