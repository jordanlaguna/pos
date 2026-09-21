import { fail } from '@sveltejs/kit';
import { api } from '$lib/server/api';
import { requireUser } from '$lib/server/auth';
import { formError, Validator } from '$lib/application/validation';
import type { Client } from '$lib/domain/types';
import { F } from '$lib/ui/fields';
import { apiMessage, validationErrors } from '$lib/ui/messages';
import { m } from '$lib/paraglide/messages.js';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ locals, url }) => {
	requireUser(locals, url.pathname);
	const clients = await api<Client[]>('/clients/clients_list', { token: locals.token });
	return { clients };
};

/**
 * La exoneración, leída del formulario (T-717, RN-78).
 *
 * **Los ocho campos viajan siempre**, aun vacíos, y eso es lo que permite
 * quitársela a un cliente: el backend los trata como uno solo y los ocho vacíos
 * son «no tiene». Mandarlos solo cuando hay algo dejaría la exoneración vieja
 * pegada a la ficha.
 *
 * No se valida acá contra los catálogos: los desplegables solo ofrecen lo que
 * se puede elegir y el servidor lo comprueba igual, así que repetir la tabla en
 * un tercer sitio sería un lugar más donde desincronizarse.
 */
function readExemption(form: FormData) {
	const campo = (nombre: string) => String(form.get(nombre) ?? '').trim();
	const numero = (nombre: string) => (campo(nombre) ? Number(campo(nombre)) : null);
	return {
		exo_document_type: campo('exo_document_type') || null,
		exo_document_number: campo('exo_document_number') || null,
		exo_institution: campo('exo_institution') || null,
		exo_institution_other: campo('exo_institution_other') || null,
		exo_article: numero('exo_article'),
		exo_subsection: numero('exo_subsection'),
		exo_date: campo('exo_date') || null,
		exo_points: numero('exo_points')
	};
}

function readClient(v: Validator, form: FormData) {
	return {
		identification: v.digits('identification', F.identification(), { min: 9, max: 12 }),
		name: v.text('name', F.name(), { max: 100 }),
		last_name: v.text('last_name', F.firstLastName(), { max: 100 }),
		second_name: v.text('second_name', F.secondLastName(), { max: 100 }),
		email: v.email('email', F.email()),
		// El backend guarda el teléfono como entero, así que se manda numérico.
		telephone: Number(v.digits('telephone', F.telephone(), { min: 8, max: 15 })),
		address: v.text('address', F.address(), { max: 100 }),
		register_date: v.date('register_date', F.registerDate()),
		...readExemption(form)
	};
}

export const actions: Actions = {
	crear: async ({ request, locals, url }) => {
		requireUser(locals, url.pathname);
		const form = await request.formData();
		const v = new Validator(form);
		const client = readClient(v, form);
		if (!v.ok) return fail(400, { errors: validationErrors(v.errors) });

		try {
			await api('/clients/register_client', {
				method: 'POST',
				token: locals.token,
				body: client
			});
		} catch (error) {
			return fail(400, { errors: formError(apiMessage(error)) });
		}
		return { success: m.clients_created() };
	},

	actualizar: async ({ request, locals, url }) => {
		requireUser(locals, url.pathname);
		const form = await request.formData();
		const v = new Validator(form);
		const id = v.integer('id_client', F.client(), { min: 1 });
		const client = readClient(v, form);
		if (!v.ok) return fail(400, { errors: validationErrors(v.errors) });

		try {
			await api(`/clients/update_client/${id}`, {
				method: 'PUT',
				token: locals.token,
				body: client
			});
		} catch (error) {
			return fail(400, { errors: formError(apiMessage(error)) });
		}
		return { success: m.clients_updated() };
	}
};
