import { fail, redirect } from '@sveltejs/kit';
import { api } from '$lib/server/api';
import { requireSoporte } from '$lib/server/auth';
import { formError, Validator } from '$lib/application/validation';
import { locales } from '$lib/paraglide/runtime.js';
import type { NewCompanyResult, Plan } from '$lib/domain/types';
import { F } from '$lib/ui/fields';
import { initialDocumentTexts } from '$lib/ui/documents';
import { apiMessage, validationErrors } from '$lib/ui/messages';
import type { Actions, PageServerLoad } from './$types';

/**
 * Alta de compañía (RF-6, T-304).
 *
 * Los cinco estados de la suscripción se ofrecen todos menos dos: dar de alta
 * algo ya `vencido` o ya `cancelado` no es un caso real, y ofrecerlo solo agrega
 * dos formas de equivocarse en un formulario que ya tiene doce campos.
 */
const ESTADOS_AL_CREAR = ['prueba', 'activa'] as const;

/** Cuántos días de prueba propone el formulario. Se puede cambiar antes de guardar. */
const DIAS_DE_PRUEBA = 30;

export const load: PageServerLoad = async ({ locals, url }) => {
	requireSoporte(locals, url.pathname);

	const plans = await api<Plan[]>('/support/plans', { token: locals.token });

	/*
	 * La fecha que propone el formulario la calcula el **servidor**.
	 *
	 * En el navegador saldría del reloj de la máquina de quien atiende soporte, y
	 * ese reloj no es el que va a decidir después si la suscripción venció (RF-10
	 * la evalúa contra la hora del servidor). Una diferencia de un día entre los
	 * dos relojes se paga en una llamada de un cliente al que se le cortó el POS
	 * un día antes de lo que decía su pantalla.
	 */
	const propuesta = new Date();
	propuesta.setDate(propuesta.getDate() + DIAS_DE_PRUEBA);

	return {
		plans,
		estados: ESTADOS_AL_CREAR,
		// La lista sale de Paraglide y no de una constante escrita a mano: es la de
		// los catálogos que de verdad se compilaron, así que no puede quedar vieja.
		locales,
		vencePropuesto: propuesta.toISOString().slice(0, 10)
	};
};

export const actions: Actions = {
	default: async ({ request, locals, url }) => {
		requireSoporte(locals, url.pathname);

		const form = await request.formData();
		const v = new Validator(form);

		const nombre = v.text('nombre', F.companyName(), { max: 160 });
		const identificacion = v.text('identificacion', F.businessIdentification(), {
			required: false,
			max: 30
		});
		// El par se puede dejar en blanco: lo calcula el backend, que es el único
		// que puede hacerlo sin que dos altas a la vez elijan el mismo número.
		const afiliado = v.integer('afiliado', F.affiliate(), { required: false, min: 1 });
		const compania = v.integer('compania', F.companyNumber(), { required: false, min: 1 });
		const planId = v.integer('plan_id', F.plan(), { min: 1 });
		const estado = v.oneOf('estado', F.companyState(), ESTADOS_AL_CREAR);
		const vence = v.date('vence_el', F.expiresOn(), { required: false });
		const locale = v.oneOf('locale', F.locale(), locales);
		const documentLocale = v.oneOf('document_locale', F.documentLocale(), locales);

		const admin = {
			email: v.email('email', F.email()),
			password: v.password('password', F.password(), { min: 6 }),
			name: v.text('name', F.name(), { max: 100 }),
			lastName: v.text('lastName', F.firstLastName(), { required: false, max: 100 }),
			secondName: v.text('secondName', F.secondLastName(), { required: false, max: 100 }),
			identification: v.digits('identification_person', F.identification(), {
				required: false,
				min: 9,
				max: 12
			}),
			telephone: v.digits('telephone', F.telephone(), { required: false, min: 8, max: 15 })
		};

		if (!v.ok) return fail(400, { errors: validationErrors(v.errors), valores: entradas(form) });

		let creada: NewCompanyResult;
		try {
			creada = await api<NewCompanyResult>('/support/companies', {
				method: 'POST',
				token: locals.token,
				body: {
					nombre,
					identificacion: identificacion || null,
					afiliado: afiliado || null,
					compania: compania || null,
					plan_id: planId,
					estado,
					vence_el: vence || null,
					locale,
					document_locale: documentLocale,
					admin,
					/*
					 * Los textos del tiquete, sembrados por el POS (T-304, RN-30).
					 *
					 * El backend no puede escribirlos: no tiene catálogo y no sabe en qué
					 * idioma. Y el dominio del POS tampoco —ahí nacen vacíos a propósito—.
					 * Este es el único momento en que se conocen las dos cosas a la vez:
					 * el idioma del documento y las palabras.
					 *
					 * Van en el idioma **del documento** y no en el de la pantalla: es
					 * texto que se imprime en la factura del cliente (RN-29).
					 */
					settings: { document: initialDocumentTexts(documentLocale) }
				}
			});
		} catch (error) {
			return fail(400, { errors: formError(apiMessage(error)), valores: entradas(form) });
		}

		// El redirect va fuera del try: lanza una excepción que no es un error. A la
		// ficha de la compañía nueva, que es donde se sigue trabajando —cambiarle la
		// fecha, entrar a mirar— y no de vuelta a la lista.
		redirect(303, `/admin/companias/${creada.company_id}?creada=1`);
	}
};

/**
 * Lo que la persona había escrito, para no perderlo cuando el alta falla.
 *
 * Un formulario de doce campos que se vacía porque el correo estaba repetido es
 * un formulario que se llena dos veces. La contraseña **no** vuelve: que un
 * `value` con la contraseña viaje en el HTML de la respuesta no hace falta para
 * nada.
 */
function entradas(form: FormData): Record<string, string> {
	const valores: Record<string, string> = {};
	for (const [clave, valor] of form.entries()) {
		if (clave === 'password') continue;
		if (typeof valor === 'string') valores[clave] = valor;
	}
	return valores;
}
