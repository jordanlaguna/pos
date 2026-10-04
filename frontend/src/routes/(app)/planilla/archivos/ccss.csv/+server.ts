import { error } from '@sveltejs/kit';
import { api, ApiError } from '$lib/server/api';
import { requireAdmin } from '$lib/server/auth';
import type { CcssReport } from '$lib/domain/payroll';
import { formatDate } from '$lib/ui/format';
import { m } from '$lib/paraglide/messages.js';
import type { RequestHandler } from './$types';

/**
 * El informe del mes para la CCSS en CSV (RF-62): lo que se teclea en
 * Autogestión, trabajador por trabajador. Lo arma el POS y no el backend porque
 * los encabezados son texto para una persona (RN-30), como el CSV de los libros.
 */
function celda(valor: unknown): string {
	const texto = valor == null ? '' : String(valor);
	return /[",;\n]/.test(texto) ? `"${texto.replace(/"/g, '""')}"` : texto;
}

export const GET: RequestHandler = async ({ locals, url }) => {
	requireAdmin(locals, url.pathname);
	const year = url.searchParams.get('year');
	const month = url.searchParams.get('month');
	let informe: CcssReport;
	try {
		informe = await api<CcssReport>(`/payroll/exports/ccss?year=${year}&month=${month}`, { token: locals.token });
	} catch (e) {
		if (e instanceof ApiError) error(e.status >= 400 && e.status < 500 ? e.status : 502, { code: e.code });
		throw e;
	}
	const filas: unknown[][] = [
		[
			m.payroll_files_col_identification(),
			m.payroll_employees_f_insured_number(),
			m.payroll_files_col_name(),
			m.payroll_files_col_occupation(),
			m.payroll_files_col_shift(),
			m.payroll_files_col_salary(),
			m.payroll_files_col_days(),
			m.payroll_files_col_movements()
		],
		...informe.rows.map((r) => [
			r.identification,
			r.insured_number ?? '',
			r.full_name,
			r.ccss_code,
			m.payroll_ccss_shift({ shift: r.shift }),
			r.salary,
			r.days,
			r.movements
				.map((mov) => {
					const fechas = mov.ends_on
						? m.payroll_period_range({ from: formatDate(mov.starts_on), to: formatDate(mov.ends_on) })
						: formatDate(mov.starts_on);
					return `${m.payroll_movement({ kind: mov.kind })} ${fechas}${mov.detail ? ` (${mov.detail})` : ''}`;
				})
				.join('; ')
		])
	];
	const csv = filas.map((f) => f.map(celda).join(',')).join('\r\n');
	return new Response('﻿' + csv, {
		headers: {
			'content-type': 'text/csv; charset=utf-8',
			'content-disposition': `attachment; filename="planilla-ccss-${year}-${String(month).padStart(2, '0')}.csv"`
		}
	});
};
