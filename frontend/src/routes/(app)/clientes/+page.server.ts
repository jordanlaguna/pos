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

function readClient(v: Validator) {
	return {
		identification: v.digits('identification', F.identification(), { min: 9, max: 12 }),
		name: v.text('name', F.name(), { max: 100 }),
		last_name: v.text('last_name', F.firstLastName(), { max: 100 }),
		second_name: v.text('second_name', F.secondLastName(), { max: 100 }),
		email: v.email('email', F.email()),
		// El backend guarda el teléfono como entero, así que se manda numérico.
		telephone: Number(v.digits('telephone', F.telephone(), { min: 8, max: 15 })),
		address: v.text('address', F.address(), { max: 100 }),
		register_date: v.date('register_date', F.registerDate())
	};
}

export const actions: Actions = {
	crear: async ({ request, locals, url }) => {
		requireUser(locals, url.pathname);
		const v = new Validator(await request.formData());
		const client = readClient(v);
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
		const client = readClient(v);
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
