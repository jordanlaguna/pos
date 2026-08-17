import { fail, redirect } from '@sveltejs/kit';
import { api, apiSafe, toMessage } from '$lib/server/api';
import { requireAdmin } from '$lib/server/auth';
import { parseHaciendaXml } from '$lib/server/import/hacienda';
import { parseSpreadsheet } from '$lib/server/import/spreadsheet';
import { matchLines } from '$lib/server/import/match';
import { formError } from '$lib/application/validation';
import type { Category, ParseResult, Product } from '$lib/domain/types';
import type { Actions, PageServerLoad } from './$types';

/** Tope de tamaño. Una factura de proveedor no llega ni de lejos a esto. */
const MAX_BYTES = 5 * 1024 * 1024;

export const load: PageServerLoad = async ({ locals, url }) => {
	requireAdmin(locals, url.pathname);
	const token = locals.token;

	const [products, categories] = await Promise.all([
		api<Product[]>('/products/products_list', { token }),
		apiSafe<Category[]>('/categories/categories_list', [], { token })
	]);

	return { products, categories };
};

export const actions: Actions = {
	/**
	 * Lee el archivo y lo empareja con el catálogo. No toca el inventario: solo
	 * devuelve la vista previa para que el usuario decida qué entra.
	 */
	analizar: async ({ request, locals, url }) => {
		requireAdmin(locals, url.pathname);
		const form = await request.formData();
		const file = form.get('archivo');

		if (!(file instanceof File) || file.size === 0) {
			return fail(400, { errors: formError('Elegí un archivo primero.') });
		}
		if (file.size > MAX_BYTES) {
			return fail(400, {
				errors: formError(
					`El archivo pesa ${(file.size / 1024 / 1024).toFixed(1)} MB; el máximo es 5 MB.`
				)
			});
		}

		const buffer = Buffer.from(await file.arrayBuffer());
		const name = file.name.toLowerCase();

		let parsed: ParseResult;
		try {
			if (name.endsWith('.xml')) {
				parsed = parseHaciendaXml(buffer.toString('utf-8'));
			} else if (name.endsWith('.xlsx') || name.endsWith('.csv')) {
				parsed = await parseSpreadsheet(buffer, name);
			} else {
				return fail(400, {
					errors: formError('Formato no soportado. Usá .xml, .xlsx o .csv.')
				});
			}
		} catch (error) {
			return fail(400, {
				errors: formError(error instanceof Error ? error.message : 'No se pudo leer el archivo.')
			});
		}

		try {
			const products = await api<Product[]>('/products/products_list', {
				token: locals.token
			});
			parsed.lines = matchLines(parsed.lines, products);
		} catch (error) {
			return fail(502, { errors: formError(toMessage(error)) });
		}

		return { parsed, filename: file.name };
	},

	/** Aplica la entrada: suma stock y crea los productos que se hayan marcado. */
	confirmar: async ({ request, locals, url }) => {
		const user = requireAdmin(locals, url.pathname);
		const form = await request.formData();

		let lines: unknown;
		try {
			lines = JSON.parse(String(form.get('lines') ?? '[]'));
		} catch {
			return fail(400, { errors: formError('No se pudo leer el detalle de la entrada.') });
		}
		if (!Array.isArray(lines) || lines.length === 0) {
			return fail(400, { errors: formError('Marcá al menos una línea para ingresar.') });
		}

		const source = String(form.get('source') ?? 'manual');
		const supplier = String(form.get('supplier') ?? '').trim() || null;
		const documentNumber = String(form.get('document_number') ?? '').trim() || null;
		const notes = String(form.get('notes') ?? '').trim() || null;

		let entryId: number;
		try {
			const result = await api<{ id_entry: number; products_created: number; units_added: number }>(
				'/inventory/entry',
				{
					method: 'POST',
					token: locals.token,
					body: {
						user_id: user.id_user,
						supplier,
						document_number: documentNumber,
						source: ['manual', 'excel', 'xml'].includes(source) ? source : 'manual',
						notes,
						lines
					}
				}
			);
			entryId = result.id_entry;
		} catch (error) {
			return fail(400, { errors: formError(toMessage(error)) });
		}

		redirect(303, `/inventario/entradas?creada=${entryId}`);
	}
};
