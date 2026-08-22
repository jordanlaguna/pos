import { fail, redirect } from '@sveltejs/kit';
import { api } from '$lib/server/api';
import { formError, Validator } from '$lib/application/validation';
import { F } from '$lib/ui/fields';
import { m } from '$lib/paraglide/messages.js';
import { apiMessage, validationErrors } from '$lib/ui/messages';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ locals }) => {
	if (locals.user) redirect(303, '/ventas');
	return {};
};

export const actions: Actions = {
	default: async ({ request }) => {
		const form = await request.formData();
		const v = new Validator(form);

		const values = {
			name: v.text('name', F.name(), { max: 100 }),
			lastName: v.text('lastName', F.firstLastName(), { max: 100 }),
			secondName: v.text('secondName', F.secondLastName(), { max: 100 }),
			identification: v.digits('identification', F.identification(), { min: 9, max: 12 }),
			telephone: v.digits('telephone', F.telephone(), { min: 8, max: 15 }),
			birth_date: v.date('birth_date', F.birthDate(), { notFuture: true }),
			email: v.email('email', F.email())
		};
		const password = v.password('password', F.password());
		const confirm = String(form.get('confirm') ?? '');

		if (password && password !== confirm) v.add('confirm', m.auth_passwords_differ());

		// Un cajero de 12 años no existe: se corta por lo evidente, no por lo legal.
		if (values.birth_date) {
			const age = (Date.now() - new Date(`${values.birth_date}T00:00:00`).getTime()) / 3.15576e10;
			if (age < 16) v.add('birth_date', m.auth_min_age());
		}

		if (!v.ok) return fail(400, { errors: validationErrors(v.errors), values });

		try {
			await api('/persons/register', { method: 'POST', body: { ...values, password } });
		} catch (error) {
			return fail(400, { errors: formError(apiMessage(error)), values });
		}

		redirect(303, '/login?registrado=1');
	}
};
