import { apiSafe } from '$lib/server/api';
import { requireAdmin } from '$lib/server/auth';
import type {
	Employee,
	InsPolicy,
	PayrollRates,
	PayrollRun,
	PayrollSettings
} from '$lib/domain/payroll';
import type { PageServerLoad } from './$types';

/** El 30 de noviembre cierra el aguinaldo; del 1 de noviembre en adelante se avisa. */
const MES_DE_AVISO = 11;

/**
 * El resumen (plan §14.4): lo que está en curso y lo que falta antes de pagar y
 * declarar. Cinco lecturas en paralelo, todas tolerantes: un backend sin F12
 * deja la pantalla vacía, no rota.
 */
export const load: PageServerLoad = async ({ locals, url }) => {
	requireAdmin(locals, url.pathname);
	const token = locals.token;
	const [corridas, empleados, configuracion, polizas, tasas] = await Promise.all([
		apiSafe<PayrollRun[]>('/payroll/runs', [], { token }),
		apiSafe<Employee[]>('/payroll/employees', [], { token }),
		apiSafe<PayrollSettings | null>('/payroll/settings', null, { token }),
		apiSafe<InsPolicy[]>('/payroll/policies', [], { token }),
		apiSafe<PayrollRates | null>('/payroll/rates', null, { token })
	]);

	const activos = empleados.filter((e) => e.is_active);
	const hoy = new Date();
	const anio = hoy.getFullYear();
	const aguinaldoHecho = corridas.some(
		(c) => c.kind === 'aguinaldo' && c.period_to === `${anio}-11-30`
	);

	return {
		enCurso: corridas.filter((c) => c.status !== 'paid'),
		activos: activos.length,
		sinEmpleados: empleados.length === 0,
		faltantes: {
			employerNumber: !configuracion?.employer_number,
			policy: polizas.length === 0,
			sinContrato: activos.filter((e) => !e.contract),
			sinAsegurado: activos.filter(
				(e) => e.identification_type !== 'national' && !e.insured_number
			)
		},
		tasas: tasas
			? {
					stale: tasas.stale,
					verifiedAt: tasas.rates.map((r) => r.verified_at).sort().at(-1) ?? null
				}
			: null,
		aguinaldoPendiente: hoy.getMonth() + 1 >= MES_DE_AVISO && !aguinaldoHecho ? anio : null
	};
};
