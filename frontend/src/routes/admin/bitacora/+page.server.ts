import { api } from '$lib/server/api';
import { requireSoporte } from '$lib/server/auth';
import type { AuditLine, SupportCompany } from '$lib/domain/types';
import type { PageServerLoad } from './$types';

/**
 * La bitácora (RF-9, T-307).
 *
 * Los filtros van en la URL y no en el estado del componente, y es a propósito:
 * «la bitácora de esta compañía» tiene que ser un enlace que se pueda pegar en
 * un correo, y el enlace desde la ficha (`?company_id=…`) es justamente eso.
 * Además así funciona sin JavaScript, igual que el resto del POS.
 */
const LIMITE = 50;

export const load: PageServerLoad = async ({ locals, url }) => {
	requireSoporte(locals, url.pathname);

	const companyId = url.searchParams.get('company_id') ?? '';
	const accion = url.searchParams.get('accion') ?? '';

	const consulta = new URLSearchParams({ limite: String(LIMITE) });
	if (companyId) consulta.set('company_id', companyId);
	if (accion) consulta.set('accion', accion);

	const [pagina, companies] = await Promise.all([
		api<{ lineas: AuditLine[]; acciones: string[] }>(`/support/audit?${consulta}`, {
			token: locals.token
		}),
		// La lista de compañías es para el desplegable del filtro. Se pide entera
		// porque es la misma que ya tiene el panel y no hay endpoint más barato;
		// el día que haya cientos, el filtro será un campo de búsqueda.
		api<SupportCompany[]>('/support/companies', { token: locals.token })
	]);

	return {
		lineas: pagina.lineas,
		acciones: pagina.acciones,
		companies,
		filtro: { companyId, accion },
		limite: LIMITE
	};
};
