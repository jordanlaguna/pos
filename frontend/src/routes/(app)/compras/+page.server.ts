import { redirect } from '@sveltejs/kit';
import { requireAdmin } from '$lib/server/auth';
import type { PageServerLoad } from './$types';

/**
 * `/compras` no es una pantalla: es la entrada del menú.
 *
 * Lleva a cuentas por pagar y no a proveedores porque es lo que se mira todos
 * los días —a quién hay que pagarle esta semana—; la lista de proveedores se
 * abre cuando hay que dar uno de alta, que pasa una vez al mes.
 */
export const load: PageServerLoad = ({ locals, url }) => {
	requireAdmin(locals, url.pathname);
	redirect(302, '/compras/cuentas-por-pagar');
};
