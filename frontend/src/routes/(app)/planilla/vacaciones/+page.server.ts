import { apiSafe } from '$lib/server/api';
import { requireAdmin } from '$lib/server/auth';
import type { Employee, Vacations } from '$lib/domain/payroll';
import type { PageServerLoad } from './$types';

/** El saldo por empleado y de dónde sale (RF-60, RN-70). Solo lectura: el
 * disfrute se registra como acción y la acumulación la hace el pago. */
export const load: PageServerLoad = async ({ locals, url }) => {
	requireAdmin(locals, url.pathname);
	const token = locals.token;
	const empleado = Number(url.searchParams.get('empleado') ?? 0) || null;
	const [employees, vacations] = await Promise.all([
		apiSafe<Employee[]>('/payroll/employees', [], { token }),
		empleado ? apiSafe<Vacations | null>(`/payroll/vacations/${empleado}`, null, { token }) : Promise.resolve(null)
	]);
	return { employees, empleado, vacations };
};
