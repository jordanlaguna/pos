import { apiSafe } from '$lib/server/api';
import { requireAdmin } from '$lib/server/auth';
import type { AccountingStatus } from '$lib/domain/types';
import type { LayoutServerLoad } from './$types';

/**
 * Contabilidad todavía sin activar, o sin backend.
 *
 * La plantilla viene vacía a propósito: si el servidor no contesta, la pantalla
 * de activación no puede ofrecer saldos iniciales contra cuentas que no sabe si
 * existen.
 */
const SIN_LIBROS: AccountingStatus = {
	active: false,
	template: null,
	start_date: null,
	templates: [],
	chart: []
};

/**
 * El estado de la contabilidad, para todas las pestañas.
 *
 * Se carga en el layout y no en cada página porque las siete lo necesitan: la
 * que está activa decide si se muestran las pestañas o la invitación a activar.
 */
export const load: LayoutServerLoad = async ({ locals, url }) => {
	requireAdmin(locals, url.pathname);
	const status = await apiSafe<AccountingStatus>('/accounting', SIN_LIBROS, {
		token: locals.token
	});
	return { status };
};
