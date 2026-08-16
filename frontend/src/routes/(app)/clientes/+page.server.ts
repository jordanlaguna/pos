import { fail } from '@sveltejs/kit';
import { api, toMessage } from '$lib/server/api';
import { requireUser } from '$lib/server/auth';
import { formError, Validator } from '$lib/validation';
import type { Client } from '$lib/types';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ locals, url }) => {
	requireUser(locals, url.pathname);
	const clients = await api<Client[]>('/clients/clients_list', { token: locals.token });
	return { clients };
};

function readClient(v: Validator) {
	return {
		identification: v.digits('identification', 'La cédula', { min: 9, max: 12 }),
		name: v.text('name', 'El nombre', { max: 100 }),
		last_name: v.text('last_name', 'El primer apellido', { max: 100 }),
		second_name: v.text('second_name', 'El segundo apellido', { max: 100 }),
		email: v.email('email'),
		// El backend guarda el teléfono como entero, así que se manda numérico.
		telephone: Number(v.digits('telephone', 'El teléfono', { min: 8, max: 15 })),
		address: v.text('address', 'La dirección', { max: 100 }),
		register_date: v.date('register_date', 'La fecha de registro')
	};
}

export const actions: Actions = {
	crear: async ({ request, locals, url }) => {
		requireUser(locals, url.pathname);
		const v = new Validator(await request.formData());
		const client = readClient(v);
		if (!v.ok) return fail(400, { errors: v.errors });

		try {
			await api('/clients/register_client', {
				method: 'POST',
				token: locals.token,
				body: client
			});
		} catch (error) {
			return fail(400, { errors: formError(toMessage(error)) });
		}
		return { success: 'Cliente registrado correctamente.' };
	},

	actualizar: async ({ request, locals, url }) => {
		requireUser(locals, url.pathname);
		const form = await request.formData();
		const v = new Validator(form);
		const id = v.integer('id_client', 'El cliente', { min: 1 });
		const client = readClient(v);
		if (!v.ok) return fail(400, { errors: v.errors });

		try {
			await api(`/clients/update_client/${id}`, {
				method: 'PUT',
				token: locals.token,
				body: client
			});
		} catch (error) {
			return fail(400, { errors: formError(toMessage(error)) });
		}
		return { success: 'Cliente actualizado correctamente.' };
	}
};
