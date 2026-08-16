import { fail } from '@sveltejs/kit';
import { api, toMessage } from '$lib/server/api';
import { requireAdmin } from '$lib/server/auth';
import { formError, Validator } from '$lib/validation';
import type { Person } from '$lib/types';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ locals, url }) => {
	requireAdmin(locals, url.pathname);
	const persons = await api<Person[]>('/persons/persons_list', { token: locals.token });
	return { persons };
};

export const actions: Actions = {
	actualizar: async ({ request, locals, url }) => {
		requireAdmin(locals, url.pathname);
		const form = await request.formData();
		const v = new Validator(form);
		const id = v.integer('id_person', 'La persona', { min: 1 });

		const person = {
			name: v.text('name', 'El nombre', { max: 100 }),
			lastName: v.text('lastName', 'El primer apellido', { max: 100 }),
			secondName: v.text('secondName', 'El segundo apellido', { max: 100 }),
			identification: v.digits('identification', 'La cédula', { min: 9, max: 12 }),
			telephone: v.digits('telephone', 'El teléfono', { min: 8, max: 15 }),
			birth_date: v.date('birth_date', 'La fecha de nacimiento', { notFuture: true }),
			email: v.email('email')
		};
		if (!v.ok) return fail(400, { errors: v.errors });

		try {
			await api(`/persons/update/${id}`, {
				method: 'PUT',
				token: locals.token,
				body: person
			});
		} catch (error) {
			return fail(400, { errors: formError(toMessage(error)) });
		}
		return { success: 'Usuario actualizado correctamente.' };
	},

	cambiarRol: async ({ request, locals, url }) => {
		const admin = requireAdmin(locals, url.pathname);
		const form = await request.formData();
		const v = new Validator(form);
		const idUser = v.integer('id_user', 'El usuario', { min: 1 });
		const role = v.oneOf('role', 'El rol', ['admin', 'cajero'] as const);
		if (!v.ok) return fail(400, { errors: v.errors });

		// Quitarse a uno mismo el rol de admin deja la sesión sin permisos a mitad
		// de camino; el backend además protege que quede al menos un administrador.
		if (idUser === admin.id_user && role !== 'admin') {
			return fail(400, {
				errors: formError('No podés quitarte a vos mismo el rol de administrador.')
			});
		}

		try {
			await api(`/users/role/${idUser}`, {
				method: 'PUT',
				token: locals.token,
				body: { role }
			});
		} catch (error) {
			return fail(400, { errors: formError(toMessage(error)) });
		}
		return { success: 'Rol actualizado.' };
	}
};
