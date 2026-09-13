import { fail, redirect } from '@sveltejs/kit';
import { api, apiSafe } from '$lib/server/api';
import { requireAdmin } from '$lib/server/auth';
import { parseHaciendaXml } from '$lib/server/import/hacienda';
import { ImportError } from '$lib/server/import/errors';
import { parseSpreadsheet } from '$lib/server/import/spreadsheet';
import { matchLines } from '$lib/server/import/match';
import { formError } from '$lib/application/validation';
import type { Category, ParseResult, Product, Supplier } from '$lib/domain/types';
import type { Actions, PageServerLoad } from './$types';
import { m } from '$lib/paraglide/messages.js';
import { apiMessage, importFailureMessage } from '$lib/ui/messages';

/** Tope de tamaño. Una factura de proveedor no llega ni de lejos a esto. */
const MAX_BYTES = 5 * 1024 * 1024;

/**
 * El proveedor que vino en el XML y todavía no está dado de alta (RF-42).
 *
 * Se relee campo por campo en vez de reenviar lo que mandó el navegador: lo que
 * llega por un formulario es de quien tenga la pantalla abierta, y darlo de alta
 * tal cual dejaría crear un proveedor con las llaves que se le antojen.
 */
function leerProveedorNuevo(raw: FormDataEntryValue | null) {
	if (typeof raw !== 'string' || !raw.trim()) return null;

	let datos: Record<string, unknown>;
	try {
		datos = JSON.parse(raw) as Record<string, unknown>;
	} catch {
		return null;
	}

	const texto = (valor: unknown) => (typeof valor === 'string' && valor.trim() ? valor.trim() : null);
	const name = texto(datos.name);
	// Sin nombre no hay proveedor que dar de alta, y el backend lo rechazaría.
	if (!name) return null;

	return {
		name,
		identification_type: texto(datos.identification_type),
		identification: texto(datos.identification),
		email: texto(datos.email),
		phone: texto(datos.phone),
		payment_terms_days: Number(datos.payment_terms_days) || 0
	};
}

export const load: PageServerLoad = async ({ locals, url }) => {
	requireAdmin(locals, url.pathname);
	const token = locals.token;

	const [products, categories, suppliers] = await Promise.all([
		api<Product[]>('/products/products_list', { token }),
		apiSafe<Category[]>('/categories/categories_list', [], { token }),
		// Con `apiSafe`: una compañía sin el módulo de compras sigue cargando
		// entradas, y sin proveedores la pantalla se comporta como antes de F10.
		apiSafe<Supplier[]>('/suppliers', [], { token })
	]);

	return { products, categories, suppliers };
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
			return fail(400, { errors: formError(m.entry_pick_file_first()) });
		}
		if (file.size > MAX_BYTES) {
			return fail(400, {
				errors: formError(
					m.entry_file_too_big({
						size: (file.size / 1024 / 1024).toFixed(1),
						max: MAX_BYTES / 1024 / 1024
					})
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
					errors: formError(m.entry_format_unsupported())
				});
			}
		} catch (error) {
			// El lector devuelve código y datos (RN-30): la frase se arma acá, que es
			// la interfaz. Lo que no sea un ImportError es un fallo nuestro.
			return fail(400, {
				errors: formError(
					error instanceof ImportError
						? importFailureMessage(error.failure)
						: m.entry_read_failed()
				)
			});
		}

		try {
			const products = await api<Product[]>('/products/products_list', {
				token: locals.token
			});
			parsed.lines = matchLines(parsed.lines, products);
		} catch (error) {
			return fail(502, { errors: formError(apiMessage(error)) });
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
			return fail(400, { errors: formError(m.entry_detail_unreadable()) });
		}
		if (!Array.isArray(lines) || lines.length === 0) {
			return fail(400, { errors: formError(m.entry_mark_one_line()) });
		}

		const source = String(form.get('source') ?? 'manual');
		const supplier = String(form.get('supplier') ?? '').trim() || null;
		const documentNumber = String(form.get('document_number') ?? '').trim() || null;
		const notes = String(form.get('notes') ?? '').trim() || null;

		// ------------------------------------------------------- compra (F10)
		//
		// Sin proveedor esto sigue siendo una entrada y nada de lo de abajo se
		// usa: no genera cuenta por pagar ni crédito fiscal (RN-52).
		let supplierId = Number(form.get('supplier_id') ?? 0) || null;
		const documentKey = String(form.get('document_key') ?? '').trim() || null;
		const documentDate = String(form.get('document_date') ?? '').trim() || null;
		const paymentTerms = form.get('payment_terms') === 'credit' ? 'credit' : 'cash';
		const paymentTermsDays = Number(form.get('payment_terms_days') ?? 0) || null;
		const paymentMethod = String(form.get('payment_method') ?? '').trim() || null;

		// El proveedor del XML que todavía no existe se da de alta acá (RF-42).
		// Va **antes** que la compra y no dentro de ella a propósito: si la
		// compra falla, el proveedor queda dado de alta y el segundo intento lo
		// encuentra en la lista. Al revés —crearlo después— dejaría una compra
		// sin a quién pagarle.
		if (!supplierId) {
			const nuevo = leerProveedorNuevo(form.get('new_supplier'));
			if (nuevo) {
				try {
					supplierId = (await api<Supplier>('/suppliers', {
						method: 'POST',
						token: locals.token,
						body: nuevo
					})).id;
				} catch (error) {
					return fail(400, { errors: formError(apiMessage(error)) });
				}
			}
		}

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
						lines,
						supplier_id: supplierId,
						document_key: documentKey,
						document_date: documentDate,
						payment_terms: paymentTerms,
						payment_terms_days: paymentTermsDays,
						// Solo con proveedor y de contado: el backend lo ignora en
						// cualquier otro caso, pero mandarlo igual invitaría a
						// creer que una entrada se puede pagar.
						payment_method: supplierId && paymentTerms === 'cash' ? paymentMethod : null,
						payment_reason: String(form.get('payment_reason') ?? '').trim()
					}
				}
			);
			entryId = result.id_entry;
		} catch (error) {
			return fail(400, { errors: formError(apiMessage(error)) });
		}

		redirect(303, `/inventario/entradas?creada=${entryId}`);
	}
};
