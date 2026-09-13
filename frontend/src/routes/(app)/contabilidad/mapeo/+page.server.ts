import { fail } from '@sveltejs/kit';
import { api, apiSafe } from '$lib/server/api';
import { requireAdmin, requireModule } from '$lib/server/auth';
import { formError } from '$lib/application/validation';
import { m } from '$lib/paraglide/messages.js';
import { apiMessage } from '$lib/ui/messages';
import type { Account, MappingRow } from '$lib/domain/types';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ locals, url }) => {
	requireAdmin(locals, url.pathname);
	const [mapeo, cuentas] = await Promise.all([
		apiSafe<{ mappings: MappingRow[] }>('/accounting/mappings', { mappings: [] }, {
			token: locals.token
		}),
		apiSafe<Account[]>('/accounting/accounts', [], { token: locals.token })
	]);
	return {
		mapeo: mapeo.mappings,
		// Solo las activas: mandar un saldo a una cuenta que la pantalla ya no
		// muestra cambiaría un problema por otro.
		cuentas: cuentas.filter((cuenta) => cuenta.is_active)
	};
};

export const actions: Actions = {
	guardar: async ({ request, locals, url }) => {
		requireAdmin(locals, url.pathname);
		requireModule(locals, 'accounting', url.pathname);
		const form = await request.formData();

		// Llega una entrada por papel, con la clave `evento|papel`. Solo viajan
		// las que tienen cuenta: una fila en blanco es un papel sin asignar, y
		// eso no se manda, se deja como está.
		const mappings = [...form.entries()]
			.filter(([clave, valor]) => clave.includes('|') && String(valor))
			.map(([clave, valor]) => {
				const [event, role] = clave.split('|');
				return { event, role, account_id: Number(valor) };
			});

		try {
			await api('/accounting/mappings', {
				method: 'PUT',
				token: locals.token,
				body: { mappings }
			});
		} catch (error) {
			return fail(400, { errors: formError(apiMessage(error)) });
		}

		return { success: m.accounting_mapping_saved() };
	}
};
