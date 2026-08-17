import { api, apiSafe } from '$lib/server/api';
import { requireUser } from '$lib/server/auth';
import type { Client, Sale } from '$lib/domain/types';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ locals, url }) => {
	requireUser(locals, url.pathname);
	const token = locals.token;

	const [sales, clients] = await Promise.all([
		api<Sale[]>('/sales/sales_list', { token }),
		apiSafe<Client[]>('/clients/clients_list', [], { token })
	]);

	// El backend no ordena; la caja espera ver primero lo último cobrado.
	sales.sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)));

	return { sales, clients };
};
