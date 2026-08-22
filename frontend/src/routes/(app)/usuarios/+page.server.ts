import { fail } from '@sveltejs/kit';
import { api } from '$lib/server/api';
import { requireAdmin } from '$lib/server/auth';
import { formError, Validator } from '$lib/application/validation';
import type { Person } from '$lib/domain/types';
import { F } from '$lib/ui/fields';
import { apiMessage, validationErrors } from '$lib/ui/messages';
import { m } from '$lib/paraglide/messages.js';
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
		const id = v.integer('id_person', F.person(), { min: 1 });

		const person = {
			name: v.text('name', F.name(), { max: 100 }),
			lastName: v.text('lastName', F.firstLastName(), { max: 100 }),
			secondName: v.text('secondName', F.secondLastName(), { max: 100 }),
			identification: v.digits('identification', F.identification(), { min: 9, max: 12 }),
			telephone: v.digits('telephone', F.telephone(), { min: 8, max: 15 }),
			birth_date: v.date('birth_date', F.birthDate(), { notFuture: true }),
			email: v.email('email', F.email())
		};
		if (!v.ok) return fail(400, { errors: validationErrors(v.errors) });

		try {
			await api(`/persons/update/${id}`, {
				method: 'PUT',
				token: locals.token,
				body: person
			});
		} catch (error) {
			return fail(400, { errors: formError(apiMessage(error)) });
		}
		return { success: m.users_updated() };
	},

	cambiarRol: async ({ request, locals, url }) => {
		const admin = requireAdmin(locals, url.pathname);
		const form = await request.formData();
		const v = new Validator(form);
		const idUser = v.integer('id_user', F.user(), { min: 1 });
		const role = v.oneOf('role', F.role(), ['admin', 'cajero'] as const);
		if (!v.ok) return fail(400, { errors: validationErrors(v.errors) });

		// Quitarse a uno mismo el rol de admin deja la sesión sin permisos a mitad
		// de camino; el backend además protege que quede al menos un administrador.
		if (idUser === admin.id_user && role !== 'admin') {
			return fail(400, {
				errors: formError(m.users_cannot_demote_self())
			});
		}

		try {
			await api(`/users/role/${idUser}`, {
				method: 'PUT',
				token: locals.token,
				body: { role }
			});
		} catch (error) {
			return fail(400, { errors: formError(apiMessage(error)) });
		}
		return { success: m.users_role_updated() };
	}
};
