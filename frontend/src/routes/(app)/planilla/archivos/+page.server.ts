import { api, apiSafe, ApiError } from '$lib/server/api';
import { requireAdmin } from '$lib/server/auth';
import type { CcssReport, Employee, IncomeTaxReport, InsPolicy } from '$lib/domain/payroll';
import type { PageServerLoad } from './$types';

/** Lo que falta para un archivo, tal como lo dice `export_data_incomplete`. */
export interface Faltantes {
	missing: { employee_id: number; fields: string[] }[];
	company: string[];
}

function faltantesDe(e: unknown): Faltantes | null {
	if (e instanceof ApiError && e.code === 'export_data_incomplete') {
		return {
			missing: Array.isArray(e.data.missing) ? (e.data.missing as Faltantes['missing']) : [],
			company: Array.isArray(e.data.company) ? (e.data.company as string[]) : []
		};
	}
	return null;
}

/**
 * Los archivos del mes (RF-62, RF-85): el informe de la CCSS, la renta retenida
 * y el archivo del INS por póliza. Todo sale de las corridas pagadas del mes.
 */
export const load: PageServerLoad = async ({ locals, url }) => {
	requireAdmin(locals, url.pathname);
	const token = locals.token;
	const hoy = new Date();
	const year = Number(url.searchParams.get('year') ?? hoy.getFullYear());
	const month = Number(url.searchParams.get('month') ?? hoy.getMonth() + 1);
	const periodo = `year=${year}&month=${month}`;

	let ccss: CcssReport | null = null;
	let ccssFaltantes: Faltantes | null = null;
	try {
		ccss = await api<CcssReport>(`/payroll/exports/ccss?${periodo}`, { token });
	} catch (e) {
		ccssFaltantes = faltantesDe(e);
	}
	const [renta, policies, employees] = await Promise.all([
		apiSafe<IncomeTaxReport | null>(`/payroll/exports/income-tax?${periodo}`, null, { token }),
		apiSafe<InsPolicy[]>('/payroll/policies', [], { token }),
		apiSafe<Employee[]>('/payroll/employees', [], { token })
	]);
	return {
		year,
		month,
		ccss,
		ccssFaltantes,
		renta,
		policies,
		nombres: Object.fromEntries(
			employees.map((e) => [e.id, [e.first_name, e.last_name_1, e.last_name_2].filter(Boolean).join(' ')])
		) as Record<number, string>
	};
};
