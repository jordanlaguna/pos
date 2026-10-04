import { api, apiSafe } from '$lib/server/api';
import { requireAdmin, requireUser, requireWrite } from '$lib/server/auth';
import { reintentarComprobante } from '$lib/server/fe';
import type { Client, FeQueue, Sale } from '$lib/domain/types';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ locals, url, parent }) => {
	requireUser(locals, url.pathname);
	const token = locals.token;
	const { settings } = await parent();

	const [sales, clients, queue] = await Promise.all([
		api<Sale[]>('/sales/sales_list', { token }),
		apiSafe<Client[]>('/clients/clients_list', [], { token }),
		// La cola ante Hacienda (RF-33, RF-35, T-711), solo con la facturación
		// activa. Con `apiSafe`: un backend anterior a F7 no tiene la ruta y la
		// lista de facturas se tiene que poder abrir igual.
		settings.eInvoicing.enabled
			? apiSafe<FeQueue | null>('/fe/queue', null, { token })
			: Promise.resolve(null)
	]);

	// El backend no ordena; la caja espera ver primero lo último cobrado.
	sales.sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)));

	return { sales, clients, queue };
};

export const actions: Actions = {
	/** RF-36: reintentar un detenido desde la lista. Solo el administrador. */
	reintentar: async ({ request, locals, url }) => {
		requireWrite(requireAdmin(locals, url.pathname));
		return reintentarComprobante(locals.token, await request.formData());
	}
};
