import { fail } from '@sveltejs/kit';
import { api, apiSafe } from '$lib/server/api';
import { requireAdmin, requireModule } from '$lib/server/auth';
import { formError, Validator } from '$lib/application/validation';
import type { Supplier } from '$lib/domain/types';
import { F } from '$lib/ui/fields';
import { m } from '$lib/paraglide/messages.js';
import { apiMessage, validationErrors } from '$lib/ui/messages';
import type { Actions, PageServerLoad } from './$types';

/** Los cuatro de Hacienda. La lista vive en el backend; acá se copia el orden. */
const TIPOS = ['01', '02', '03', '04'];

export const load: PageServerLoad = async ({ locals, url }) => {
	requireAdmin(locals, url.pathname);

	const inactivos = url.searchParams.get('inactivos') === '1';
	// Con `apiSafe`: leer proveedores no exige el módulo (RN-50), pero un backend
	// sin F10 no tiene la ruta y la pantalla tiene que abrir igual.
	const suppliers = await apiSafe<Supplier[]>(
		`/suppliers?incluir_inactivos=${inactivos}`,
		[],
		{ token: locals.token }
	);

	return { suppliers, inactivos };
};

export const actions: Actions = {
	guardar: async ({ request, locals, url }) => {
		requireAdmin(locals, url.pathname);
		// Y el módulo, porque esto escribe (RN-49). El backend lo exige igual;
		// esto impide que se ofrezca, que es lo que RN-2 pide para el bloqueo por
		// suscripción y vale igual acá: enterarse después de llenar la ficha es
		// la peor manera de enterarse.
		requireModule(locals, 'purchases', url.pathname);
		const form = await request.formData();
		const v = new Validator(form);

		const id = Number(form.get('id') ?? 0) || null;
		const name = v.text('name', F.name(), { min: 2, max: 160 });
		if (!v.ok) return fail(400, { errors: validationErrors(v.errors) });

		const tipo = String(form.get('identification_type') ?? '').trim();
		const cuerpo = {
			name,
			// El tipo vacío es «sin identificación», que es un proveedor informal
			// y no un error: el de la fruta del martes no tiene cédula, y
			// obligarlo haría que alguien la invente.
			identification_type: TIPOS.includes(tipo) ? tipo : null,
			identification: String(form.get('identification') ?? '').trim() || null,
			email: String(form.get('email') ?? '').trim() || null,
			phone: String(form.get('phone') ?? '').trim() || null,
			payment_terms_days: Number(form.get('payment_terms_days') ?? 0) || 0,
			...(id ? { is_active: form.get('is_active') === 'on' } : {})
		};

		try {
			await api<Supplier>(id ? `/suppliers/${id}` : '/suppliers', {
				method: id ? 'PUT' : 'POST',
				token: locals.token,
				body: cuerpo
			});
		} catch (error) {
			return fail(400, { errors: formError(apiMessage(error)) });
		}

		return { success: m.suppliers_saved() };
	}
};
