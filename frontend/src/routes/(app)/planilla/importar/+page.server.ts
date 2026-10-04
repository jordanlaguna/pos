import { fail } from '@sveltejs/kit';
import { api, ApiError, toLog } from '$lib/server/api';
import { requireAdmin, requireModule } from '$lib/server/auth';
import { HOJAS, leerHoja, type Hoja } from '$lib/server/import/payroll';
import { formError, Validator } from '$lib/application/validation';
import type { ImportResult, ImportRowError } from '$lib/domain/payroll';
import { F } from '$lib/ui/fields';
import { m } from '$lib/paraglide/messages.js';
import { apiMessage, validationErrors } from '$lib/ui/messages';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ locals, url }) => {
	requireAdmin(locals, url.pathname);
	return { hojas: HOJAS };
};

interface Carga {
	as_of: string;
	positions: Record<string, unknown>[];
	employees: Record<string, unknown>[];
	earnings: Record<string, unknown>[];
	deductions: Record<string, unknown>[];
}

function escribe(locals: App.Locals, pathname: string) {
	requireAdmin(locals, pathname);
	requireModule(locals, 'payroll', pathname);
}

/** La respuesta del ensayo, con la carga para confirmar sin volver a subir nada. */
function respuesta(resultado: ImportResult, carga: Carga) {
	return { preview: resultado, payload: JSON.stringify(carga) };
}

export const actions: Actions = {
	revisar: async ({ request, locals, url }) => {
		escribe(locals, url.pathname);
		const form = await request.formData();
		const v = new Validator(form);
		const as_of = v.date('as_of', F.asOf());
		if (!v.ok) return fail(400, { errors: validationErrors(v.errors) });

		const carga: Carga = { as_of, positions: [], employees: [], earnings: [], deductions: [] };
		const lecturas: string[] = [];
		for (const hoja of HOJAS as Hoja[]) {
			const archivo = form.get(hoja);
			if (!(archivo instanceof File) || archivo.size === 0) continue;
			try {
				carga[hoja] = await leerHoja(hoja, archivo);
			} catch (e) {
				lecturas.push(m.payroll_import_read_error({ file: archivo.name, reason: toLog(e) }));
			}
		}
		if (lecturas.length) return fail(400, { errors: formError(lecturas.join(' ')) });
		if (!carga.employees.length && !carga.positions.length && !carga.earnings.length && !carga.deductions.length) {
			return fail(400, { errors: formError(m.payroll_import_no_files()) });
		}
		try {
			const resultado = await api<ImportResult>('/payroll/import?dry_run=true', {
				method: 'POST',
				token: locals.token,
				body: carga
			});
			return respuesta(resultado, carga);
		} catch (e) {
			return fail(400, { errors: formError(apiMessage(e)) });
		}
	},

	confirmar: async ({ request, locals, url }) => {
		escribe(locals, url.pathname);
		const form = await request.formData();
		let carga: Carga;
		try {
			carga = JSON.parse(String(form.get('payload') ?? '')) as Carga;
		} catch {
			return fail(400, { errors: formError(m.payroll_import_no_files()) });
		}
		try {
			const resultado = await api<ImportResult>('/payroll/import?dry_run=false', {
				method: 'POST',
				token: locals.token,
				body: carga
			});
			return { success: m.payroll_import_done({ employees: resultado.employees }), done: resultado };
		} catch (e) {
			// Las filas malas vuelven con su código, para listarlas como en el ensayo.
			if (e instanceof ApiError && e.code === 'import_has_errors') {
				const errores = (e.data.errors ?? []) as ImportRowError[];
				return fail(400, {
					errors: formError(apiMessage(e)),
					preview: { dry_run: true, ok: false, errors: errores, positions: 0, employees: 0, earnings: 0, deductions: 0 } as ImportResult,
					payload: String(form.get('payload') ?? '')
				});
			}
			return fail(400, { errors: formError(apiMessage(e)) });
		}
	}
};
