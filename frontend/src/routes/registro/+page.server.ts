import { fail, redirect } from '@sveltejs/kit';
import { api, toMessage } from '$lib/server/api';
import { formError, Validator } from '$lib/validation';
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
			name: v.text('name', 'El nombre', { max: 100 }),
			lastName: v.text('lastName', 'El primer apellido', { max: 100 }),
			secondName: v.text('secondName', 'El segundo apellido', { max: 100 }),
			identification: v.digits('identification', 'La cédula', { min: 9, max: 12 }),
			telephone: v.digits('telephone', 'El teléfono', { min: 8, max: 15 }),
			birth_date: v.date('birth_date', 'La fecha de nacimiento', { notFuture: true }),
			email: v.email('email')
		};
		const password = v.password('password');
		const confirm = String(form.get('confirm') ?? '');

		if (password && password !== confirm) v.add('confirm', 'Las contraseñas no coinciden.');

		// Un cajero de 12 años no existe: se corta por lo evidente, no por lo legal.
		if (values.birth_date) {
			const age = (Date.now() - new Date(`${values.birth_date}T00:00:00`).getTime()) / 3.15576e10;
			if (age < 16) v.add('birth_date', 'El usuario debe tener al menos 16 años.');
		}

		if (!v.ok) return fail(400, { errors: v.errors, values });

		try {
			await api('/persons/register', { method: 'POST', body: { ...values, password } });
		} catch (error) {
			return fail(400, { errors: formError(toMessage(error)), values });
		}

		redirect(303, '/login?registrado=1');
	}
};
