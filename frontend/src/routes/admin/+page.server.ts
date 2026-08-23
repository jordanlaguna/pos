import { api } from '$lib/server/api';
import { requireSoporte } from '$lib/server/auth';
import type { SupportCompany } from '$lib/domain/types';
import type { PageServerLoad } from './$types';

/**
 * El listado de clientes (RF-5, T-303).
 *
 * Sin paginar y sin filtro por ahora: son los clientes del producto y la lista
 * es la herramienta de trabajo. El día que sean cientos habrá que paginar, y ese
 * día se sabrá porque la pantalla tarda —no antes—.
 */
export const load: PageServerLoad = async ({ locals, url }) => {
	requireSoporte(locals, url.pathname);

	const companies = await api<SupportCompany[]>('/support/companies', { token: locals.token });
	return { companies };
};
