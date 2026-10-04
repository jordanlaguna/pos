import { requireAdmin } from '$lib/server/auth';
import type { LayoutServerLoad } from './$types';

/**
 * Todo `/planilla` es de administración, también leer (RN-50): la planilla es
 * lo más delicado que guarda el sistema después del libro.
 *
 * El módulo del plan no cierra la lectura —una compañía que bajó de plan sigue
 * viendo sus boletas— pero sí la escritura; las acciones lo exigen con
 * `requireModule` y las pantallas esconden lo que no se va a poder guardar.
 */
export const load: LayoutServerLoad = async ({ locals, url }) => {
	const user = requireAdmin(locals, url.pathname);
	return { payrollEnabled: user.modules.payroll === true };
};
