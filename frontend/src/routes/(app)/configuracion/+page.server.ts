import { fail } from '@sveltejs/kit';

import { api, apiSafe } from '$lib/server/api';
import { requireAdmin, setSessionCookie } from '$lib/server/auth';
import { invalidateSettings, loadSettings, saveSettings } from '$lib/server/settings';
import { formError, Validator } from '$lib/application/validation';
import { F } from '$lib/ui/fields';
import { m } from '$lib/paraglide/messages.js';
import {
	apiMessage,
	firstError,
	issuerMissingMessage,
	locationMessage,
	validationErrors
} from '$lib/ui/messages';
import {
	isHexColor,
	mergeSettings,
	type LogoSettings,
	type Settings
} from '$lib/domain/settings';
import { isBlankLocation, locationProblem, type LocationField } from '$lib/domain/location';
import type { Actions, PageServerLoad } from './$types';

/** Los idiomas con catálogo. La misma lista que `app/domain/locale.py`. */
const LOCALES = ['es', 'en', 'pt'] as const;

/** Un logo más pesado que esto no mejora la factura; solo hace lenta cada pantalla. */
const MAX_LOGO_BYTES = 250 * 1024;

/*
 * SVG queda fuera a propósito. Es XML, admite <script> dentro, y este archivo se
 * sirve tal cual desde el mismo origen que el POS: subir un «logo» sería subir
 * código que corre con la sesión del cajero.
 */
const LOGO_TYPES = ['image/png', 'image/jpeg', 'image/webp'];

/** El mismo techo que `crud_fe.MAX_P12_BYTES`. Se rechaza acá para no subirlo. */
const MAX_P12_BYTES = 256 * 1024;

const AMBIENTES = ['sandbox', 'production'] as const;

/**
 * El estado de los dos ambientes, tal como lo devuelve `GET /fe` (RF-23, RF-30).
 *
 * **No lleva el archivo, ni el PIN, ni la contraseña**, y eso no es una elección
 * de esta pantalla: no existe ningún endpoint que los devuelva (RN-16).
 */
export interface EstadoDeAmbiente {
	environment: string;
	certificate_configured: boolean;
	certificate_name: string | null;
	expires_at: string | null;
	days_left: number | null;
	certificate_status: string;
	uploaded_at: string | null;
	atv_user: string | null;
	atv_configured: boolean;
	atv_verified_at: string | null;
	ready: boolean;
}

/** Una serie de numeración: una caja por un tipo de comprobante (T-616). */
export interface Serie {
	terminal_id: number;
	branch_code: string;
	branch_name: string;
	terminal_code: string;
	terminal_name: string;
	document_type: string;
	/** El último consecutivo emitido; el siguiente sale con uno más. */
	last_number: number;
	/** El sistema ya emitió con esta serie: desde ahí es suya (RN-38). */
	in_use: boolean;
}

export interface EstadoFe {
	environments: EstadoDeAmbiente[];
	active: string;
	/** T-713: si ya se puede pasar a producción y, si no, qué tipos faltan. */
	production_gate?: { ready: boolean; missing: string[] } | null;
}

/**
 * Sucursales, cajas y el cupo del plan, tal como los devuelve `/offices` (RF-26).
 *
 * Las cuatro escrituras devuelven **esto mismo** y no la fila que tocaron: una
 * sola forma de respuesta significa que la pantalla no mezcla lo que tenía con lo
 * que le llega. Acá hace falta de verdad, porque apagar una sucursal apaga sus
 * cajas y crear una consume cupo.
 */
export interface Sucursal {
	id: number;
	codigo: string;
	nombre: string;
	activa: boolean;
}

export interface Caja extends Sucursal {
	branch_id: number;
}

export interface Cupo {
	branches: number;
	max_branches: number;
	terminals: number;
	max_terminals: number;
}

export interface EstadoOficinas {
	branches: Sucursal[];
	terminals: Caja[];
	quota: Cupo;
}

export const load: PageServerLoad = async ({ locals, url }) => {
	const admin = requireAdmin(locals, url.pathname);
	const stored = await loadSettings(locals.token, admin.company_id);

	/*
	 * `apiSafe` y no `api`: la factura electrónica es una de las cuatro pestañas,
	 * y un backend que tropiece pidiéndola no puede dejar sin moneda ni sin
	 * documentos a quien vino a cambiar otra cosa. Sin dato, la pestaña lo dice.
	 */
	const fe = await apiSafe<EstadoFe | null>('/fe', null, { token: locals.token });
	// Las series, para el negocio que viene de otro sistema (T-616). `apiSafe`
	// por lo mismo que `/fe`.
	const series = await apiSafe<{ environment: string; items: Serie[] } | null>(
		'/fe/sequences',
		null,
		{ token: locals.token }
	);
	// Por lo mismo que `/fe`: es una pestaña más y no puede tumbar las otras.
	const oficinas = await apiSafe<EstadoOficinas | null>('/offices', null, {
		token: locals.token
	});

	return {
		configuracion: stored.settings,
		tieneLogo: stored.logo !== null,
		actualizado: stored.updated_at,
		/*
		 * La sucursal y la terminal salen de la **sesión**, no de la configuración
		 * (T-614). El backend las resuelve desde el token —`sucursal_actual()`,
		 * `terminal_actual()`— y `/users/me` ya las publica, así que acá solo se
		 * pasan a la pantalla, que las muestra sin dejar editarlas.
		 */
		branchCode: admin.branch_code,
		terminalCode: admin.terminal_code,
		// La cédula del emisor, de `companies` (RN-45): se muestra sin editarse.
		issuer: stored.issuer,
		fe,
		series,
		oficinas
	};
};

/** El campo del formulario que corresponde a cada campo de la ubicación. */
const CAMPO_DE_UBICACION: Record<LocationField, string> = {
	province: 'negocio_provincia',
	canton: 'negocio_canton',
	district: 'negocio_distrito',
	neighborhood: 'negocio_barrio',
	other_signs: 'negocio_otras_senas'
};

/** Casilla marcada. El navegador no envía nada cuando está desmarcada. */
function checked(form: FormData, field: string): boolean {
	return form.get(field) === 'on' || form.get(field) === 'true';
}

/**
 * Separador de miles o de decimales.
 *
 * No pasa por `Validator.text` porque ahí se recortan los espacios, y tanto el
 * espacio (separador de miles en varias convenciones) como la cadena vacía
 * (miles sin separar) son respuestas válidas.
 */
function separator(form: FormData, field: string, fallback: string): string {
	const value = form.get(field);
	if (typeof value !== 'string') return fallback;
	return value.length <= 1 ? value : fallback;
}

function hex(v: Validator, form: FormData, field: string, label: string, fallback: string): string {
	const value = form.get(field);
	if (isHexColor(value)) return value.toLowerCase();
	v.add(field, m.settings_bad_color({ field: label }));
	return fallback;
}

async function readLogo(form: FormData, v: Validator): Promise<LogoSettings | undefined> {
	const file = form.get('logo');
	// Sin archivo, o el input vacío que manda el navegador: se conserva el actual.
	if (!(file instanceof File) || file.size === 0) return undefined;

	if (!LOGO_TYPES.includes(file.type)) {
		v.add('logo', m.settings_logo_bad_type());
		return undefined;
	}
	if (file.size > MAX_LOGO_BYTES) {
		v.add('logo', m.settings_logo_too_big({ max: Math.round(MAX_LOGO_BYTES / 1024) }));
		return undefined;
	}

	const bytes = Buffer.from(await file.arrayBuffer());
	return { mime: file.type, data: bytes.toString('base64') };
}

export const actions: Actions = {
	guardar: async ({ request, cookies, locals, url }) => {
		const admin = requireAdmin(locals, url.pathname);
		const { settings: stored, issuer } = await loadSettings(locals.token, admin.company_id);

		const form = await request.formData();
		const v = new Validator(form);

		const nombre = v.text('negocio_nombre', F.businessName(), { max: 120 });
		const razonSocial = v.text('negocio_razon_social', F.businessLegalName(), {
			required: false,
			max: 160
		});
		// La identificación ya no sale del formulario (RN-45, T-621): es la de la
		// compañía y la fija soporte. La que queda en la configuración es la que
		// había, y el backend ni la mira.
		const telefono = v.text('negocio_telefono', F.businessTelephone(), { required: false, max: 30 });
		const correo = v.email('negocio_correo', F.businessEmail(), { required: false });
		const direccion = v.text('negocio_direccion', F.businessAddress(), { required: false, max: 300 });
		const sitioWeb = v.text('negocio_sitio_web', F.businessWebsite(), { required: false, max: 120 });

		const codigo = v.text('moneda_codigo', F.currencyCode(), { max: 8 });
		const simbolo = v.text('moneda_simbolo', F.currencySymbol(), { max: 5 });
		const decimales = v.integer('moneda_decimales', F.decimals(), { min: 0, max: 4 });

		const plantilla = v.oneOf('documento_plantilla', F.documentTemplate(), [
			'tiquete',
			'clasica',
			'moderna'
		] as const);
		const anchoTiquete = v.oneOf('documento_ancho', F.documentWidth(), ['58', '80'] as const);
		const mensajeGracias = v.text('documento_mensaje', F.documentFarewell(), {
			required: false,
			max: 120
		});
		const leyenda = v.text('documento_leyenda', F.documentLegend(), { required: false, max: 240 });
		const notas = v.text('documento_notas', F.documentNotes(), { required: false, max: 600 });

		const colorDocumento = hex(v, form, 'documento_color', m.settings_field_document_color(), '#0e7490');
		const colorAcento = hex(v, form, 'apariencia_color', m.settings_field_accent_color(), '#0e7490');

		const actividad = v.text('electronica_actividad', F.einvoicingActivity(), {
			required: false,
			max: 10
		});

		/*
		 * Los dos idiomas de la compañía (T-810, T-811). No entran en la
		 * configuración: viven en columnas de `companies`, porque el de la pantalla
		 * hay que leerlo al emitir el token, antes de que exista configuración que
		 * consultar.
		 */
		const idiomaInterfaz = v.oneOf('idioma_interfaz', F.locale(), LOCALES);
		const idiomaDocumento = v.oneOf('idioma_documento', F.documentLocale(), LOCALES);

		const logo = await readLogo(form, v);
		const quitarLogo = checked(form, 'quitar_logo');

		/*
		 * La ubicación del emisor (T-722, RN-83), con la misma regla que el
		 * servidor: vacía se guarda —quien no emite no tiene por qué dar su
		 * distrito—, a medias no. Y con la factura electrónica encendida es
		 * obligatoria, como el correo.
		 */
		const encendida = checked(form, 'electronica_activa');
		const ubicacion = {
			province: String(form.get('negocio_provincia') ?? ''),
			canton: String(form.get('negocio_canton') ?? ''),
			district: String(form.get('negocio_distrito') ?? ''),
			neighborhood: String(form.get('negocio_barrio') ?? ''),
			otherSigns: String(form.get('negocio_otras_senas') ?? '')
		};
		if (encendida || !isBlankLocation(ubicacion)) {
			const problema = locationProblem(ubicacion);
			if (problema) v.add(CAMPO_DE_UBICACION[problema.field], locationMessage(problema));
		}
		if (encendida && !correo) v.add('negocio_correo', issuerMissingMessage(['email']));

		if (!v.ok) return fail(400, { errors: validationErrors(v.errors) });

		// Sin cédula de emisor no hay clave, y esa no se arregla en esta pantalla.
		if (encendida && !issuer?.identification) {
			return fail(400, { errors: formError(issuerMissingMessage(['identification'])) });
		}

		/*
		 * Se arma el objeto y se vuelve a pasar por `mergeSettings`. Parece
		 * redundante después de validar campo por campo, pero es la misma función
		 * que sanea lo que llega del backend: si algún día se agrega un campo y se
		 * olvida validarlo acá, sigue habiendo un solo lugar donde se decide qué
		 * forma tiene una configuración válida.
		 */
		const settings: Settings = mergeSettings({
			business: {
				nombre,
				legalName: razonSocial,
				// Las de antes, sin tocar: la del emisor es la de la compañía.
				identificacion: stored.business.taxId,
				taxIdType: stored.business.taxIdType,
				telefono,
				correo,
				direccion,
				website: sitioWeb,
				location: ubicacion
			},
			currency: {
				codigo,
				simbolo,
				decimales,
				thousandsSeparator: separator(form, 'moneda_separador_miles', '.'),
				decimalSeparator: separator(form, 'moneda_separador_decimal', ','),
				symbolAtEnd: checked(form, 'moneda_simbolo_al_final'),
				space: checked(form, 'moneda_espacio')
			},
			document: {
				template: plantilla || 'tiquete',
				color: colorDocumento,
				showLogo: checked(form, 'documento_mostrar_logo'),
				showBarcode: checked(form, 'documento_mostrar_codigo'),
				receiptWidth: anchoTiquete === '58' ? 58 : 80,
				thanksMessage: mensajeGracias,
				leyenda,
				notas
			},
			appearance: { accentColor: colorAcento },
			eInvoicing: {
				// La emisión todavía no está implementada; ver la nota de la pantalla.
				// Se guarda la intención, no se activa nada.
				enabled: checked(form, 'electronica_activa'),
				/*
				 * El ambiente **no** sale del formulario (T-611): se cambia por
				 * `PUT /fe/active`, que confirma y deja bitácora. Va el guardado, no
				 * uno por omisión, para que el cuerpo diga la verdad — el backend lo
				 * conserva de todos modos, pero mandarle «sandbox» a un negocio que
				 * está en producción sería escribir una mentira y confiar en que la
				 * ignoren.
				 */
				environment: stored.eInvoicing.environment,
				economicActivity: actividad,
				/*
				 * Los comprobantes que emite (RN-88). Las casillas que no se pueden
				 * mover viajan en un campo oculto cuando están encendidas —una casilla
				 * apagada no se envía—, así que acá llega la lista entera. Y la sanea
				 * `mergeSettings`, con la misma regla que el servidor: sin tiquete ni
				 * factura, o sin la NC, no se guarda así.
				 */
				documentTypes: form.getAll('electronica_comprobantes').map(String)
			}
		});

		try {
			await saveSettings(
				locals.token,
				settings,
				quitarLogo && !logo ? null : logo,
				admin.company_id
			);
		} catch (error) {
			// Se descarta solo la de ESTA compañía: guardar mal la configuración de
			// un negocio no tiene por qué obligar a los demás a volver a pedir la
			// suya (T-224).
			invalidateSettings(admin.company_id);
			return fail(400, { errors: formError(apiMessage(error)) });
		}

		try {
			/*
			 * El backend devuelve un token nuevo porque el idioma de la pantalla vive
			 * en el token: si quien guarda no eligió uno propio, acaba de cambiar el
			 * suyo. Sin renovar la cookie, la pantalla seguiría en el idioma anterior
			 * hasta el siguiente login.
			 */
			const sesion = await api<{ access_token: string }>('/settings/locales', {
				method: 'PUT',
				body: { locale: idiomaInterfaz, document_locale: idiomaDocumento },
				token: locals.token
			});
			setSessionCookie(cookies, sesion.access_token);
		} catch (error) {
			return fail(400, { errors: formError(apiMessage(error)) });
		}

		return { success: m.settings_saved() };
	},

	/*
	 * ------------------------------------------- factura electrónica (F6)
	 *
	 * Cinco acciones aparte y no campos del formulario grande, y no es una
	 * decisión de maquetado: **cada una habla con un endpoint propio que hace algo
	 * irreversible o auditado**. Subir un certificado importa una llave a Vault,
	 * quitarlo la borra, probar la conexión sale a internet y cambiar el ambiente
	 * queda en bitácora. Meterlas en el «Guardar cambios» de la pantalla haría que
	 * corregir una coma en la dirección del negocio disparara las cuatro.
	 *
	 * Todas devuelven el «no» del backend tal cual —código y datos— y la frase la
	 * arma `apiMessage` (RN-30).
	 */

	feCertificado: async ({ request, locals, url }) => {
		requireAdmin(locals, url.pathname);

		const form = await request.formData();
		const v = new Validator(form);
		const ambiente = v.oneOf('ambiente', F.einvoicingEnvironment(), AMBIENTES);
		const pin = v.text('pin', F.certificatePin(), { max: 200 });

		const archivo = form.get('certificado');
		if (!(archivo instanceof File) || archivo.size === 0) {
			v.add('certificado', m.settings_fe_certificate_required());
		} else if (archivo.size > MAX_P12_BYTES) {
			// Se rechaza acá para no gastar la subida: el backend lo rechaza igual,
			// y esta comprobación es una cortesía, no el control.
			v.add('certificado', m.settings_fe_certificate_too_big({ kb: MAX_P12_BYTES / 1024 }));
		}
		if (!v.ok) return fail(400, { errors: validationErrors(v.errors) });

		const bytes = new Uint8Array(await (archivo as File).arrayBuffer());
		try {
			await api(`/fe/${ambiente}/certificate`, {
				method: 'POST',
				token: locals.token,
				/*
				 * `multipart` y no base64 en un JSON: el navegador ya sabe mandarlo y
				 * de paso no se infla un tercio por el camino. **En ningún punto del
				 * trayecto toca el disco**: un temporal con una llave privada adentro
				 * sobrevive al proceso que lo creó.
				 */
				upload: {
					field: 'archivo',
					filename: (archivo as File).name || 'certificado.p12',
					contentType: 'application/x-pkcs12',
					bytes,
					fields: { pin }
				}
			});
		} catch (error) {
			return fail(400, { errors: formError(apiMessage(error)) });
		}
		return { success: m.settings_fe_certificate_saved() };
	},

	feQuitarCertificado: async ({ request, locals, url }) => {
		requireAdmin(locals, url.pathname);

		const form = await request.formData();
		const v = new Validator(form);
		const ambiente = v.oneOf('ambiente', F.einvoicingEnvironment(), AMBIENTES);
		if (!v.ok) return fail(400, { errors: validationErrors(v.errors) });

		try {
			await api(`/fe/${ambiente}/certificate`, { method: 'DELETE', token: locals.token });
		} catch (error) {
			return fail(400, { errors: formError(apiMessage(error)) });
		}
		return { success: m.settings_fe_certificate_removed() };
	},

	feAtv: async ({ request, locals, url }) => {
		requireAdmin(locals, url.pathname);

		const form = await request.formData();
		const v = new Validator(form);
		const ambiente = v.oneOf('ambiente', F.einvoicingEnvironment(), AMBIENTES);
		const usuario = v.text('atv_usuario', F.atvUser(), { max: 160 });
		const clave = v.text('atv_clave', F.atvPassword(), { max: 200 });
		if (!v.ok) return fail(400, { errors: validationErrors(v.errors) });

		try {
			await api(`/fe/${ambiente}/atv`, {
				method: 'PUT',
				token: locals.token,
				body: { user: usuario, password: clave }
			});
		} catch (error) {
			return fail(400, { errors: formError(apiMessage(error)) });
		}
		return { success: m.settings_fe_atv_saved() };
	},

	feProbar: async ({ request, locals, url }) => {
		requireAdmin(locals, url.pathname);

		const form = await request.formData();
		const v = new Validator(form);
		const ambiente = v.oneOf('ambiente', F.einvoicingEnvironment(), AMBIENTES);
		if (!v.ok) return fail(400, { errors: validationErrors(v.errors) });

		try {
			await api(`/fe/${ambiente}/atv/verify`, { method: 'POST', token: locals.token });
		} catch (error) {
			/*
			 * Los tres desenlaces de RF-31 llegan acá como tres códigos distintos y
			 * salen como tres frases distintas. La del tercero **no culpa a las
			 * credenciales**: quien lea «no sirven» va a rotar su contraseña en ATV,
			 * y hacerlo el día que Hacienda está caída es trabajo perdido.
			 */
			return fail(400, { errors: formError(apiMessage(error)) });
		}
		return { success: m.settings_fe_connection_ok() };
	},

	feAmbiente: async ({ request, locals, url }) => {
		const admin = requireAdmin(locals, url.pathname);

		const form = await request.formData();
		const v = new Validator(form);
		const ambiente = v.oneOf('ambiente', F.einvoicingEnvironment(), AMBIENTES);
		if (!v.ok) return fail(400, { errors: validationErrors(v.errors) });

		try {
			await api('/fe/active', {
				method: 'PUT',
				token: locals.token,
				/*
				 * La confirmación viaja al servidor y no se queda en el modal. RN-35
				 * dice que esto «no puede ocurrir por haber tocado un desplegable sin
				 * querer», y un desplegable que hace `PUT` es exactamente eso: sin
				 * este campo, el backend responde `confirmation_required`.
				 */
				body: { environment: ambiente, confirm: checked(form, 'confirmar') }
			});
		} catch (error) {
			return fail(400, { errors: formError(apiMessage(error)) });
		}
		// El ambiente vive en la configuración, así que la copia en caché de esta
		// compañía quedó vieja (T-224).
		invalidateSettings(admin.company_id);
		return { success: m.settings_fe_environment_changed() };
	},

	/**
	 * El último consecutivo de una serie, para el negocio que viene de otro
	 * sistema (T-616, RN-36 a RN-38). Que solo suba y que una serie usada no se
	 * mueva lo decide el servidor; acá solo se revisa que sea un número.
	 */
	feSerie: async ({ request, locals, url }) => {
		requireAdmin(locals, url.pathname);
		const form = await request.formData();
		const v = new Validator(form);
		const terminalId = v.integer('terminal_id', F.terminal(), { min: 1 });
		const ultimo = v.integer('last_number', F.lastSequence(), { min: 0, max: 9_999_999_999 });
		if (!v.ok) return fail(400, { message: firstError(v.errors), errors: validationErrors(v.errors) });
		try {
			await api('/fe/sequences', {
				method: 'PUT',
				token: locals.token,
				body: {
					terminal_id: terminalId,
					document_type: String(form.get('document_type') ?? ''),
					last_number: ultimo
				}
			});
		} catch (error) {
			return fail(400, { errors: formError(apiMessage(error)) });
		}
		return { success: m.settings_fe_sequence_saved() };
	},

	/*
	 * ------------------------------------------ sucursales y cajas (T-608)
	 *
	 * Cuatro acciones y no seis: el alta y la edición comparten formulario porque
	 * comparten campos, y lo único que las distingue es si llega `id`.
	 *
	 * **El código solo viaja al crear.** No es una omisión: no existe en los
	 * esquemas de actualización del backend, porque cambiarlo movería el número de
	 * todos los comprobantes ya emitidos desde esa sucursal. Mandarlo igual sería
	 * ofrecer en la pantalla algo que el servidor va a ignorar.
	 */

	sucursalGuardar: async ({ request, locals, url }) => {
		requireAdmin(locals, url.pathname);

		const form = await request.formData();
		const v = new Validator(form);
		const id = Number(form.get('id') ?? 0) || null;
		const nombre = v.text('nombre', F.officeName(), { max: 120 });
		// Se valida solo al crear: al editar el campo ni se dibuja.
		const codigo = id ? '' : v.text('codigo', F.branchCode(), { max: 10 });
		if (!v.ok) return fail(400, { errors: validationErrors(v.errors) });

		try {
			await api(id ? `/offices/branches/${id}` : '/offices/branches', {
				method: id ? 'PUT' : 'POST',
				token: locals.token,
				body: id ? { nombre, activa: checked(form, 'activa') } : { codigo, nombre }
			});
		} catch (error) {
			return fail(400, { errors: formError(apiMessage(error)) });
		}
		return { success: m.settings_offices_branch_saved() };
	},

	sucursalBorrar: async ({ request, locals, url }) => {
		requireAdmin(locals, url.pathname);

		const form = await request.formData();
		const id = Number(form.get('id') ?? 0);
		try {
			await api(`/offices/branches/${id}`, { method: 'DELETE', token: locals.token });
		} catch (error) {
			/*
			 * Acá llega `branch_in_use` con sus dos cuentas, y la frase las dice: quien
			 * borra necesita saber qué mover primero. La alternativa —«no se puede
			 * borrar»— deja a alguien buscando qué es lo que la retiene.
			 */
			return fail(400, { errors: formError(apiMessage(error)) });
		}
		return { success: m.settings_offices_branch_removed() };
	},

	cajaGuardar: async ({ request, locals, url }) => {
		requireAdmin(locals, url.pathname);

		const form = await request.formData();
		const v = new Validator(form);
		const id = Number(form.get('id') ?? 0) || null;
		const nombre = v.text('nombre', F.officeName(), { max: 120 });
		const codigo = id ? '' : v.text('codigo', F.terminalCode(), { max: 10 });
		const sucursal = id ? 0 : v.integer('branch_id', F.branch(), { min: 1 });
		if (!v.ok) return fail(400, { errors: validationErrors(v.errors) });

		try {
			await api(id ? `/offices/terminals/${id}` : '/offices/terminals', {
				method: id ? 'PUT' : 'POST',
				token: locals.token,
				body: id
					? { nombre, activa: checked(form, 'activa') }
					: { branch_id: sucursal, codigo, nombre }
			});
		} catch (error) {
			return fail(400, { errors: formError(apiMessage(error)) });
		}
		return { success: m.settings_offices_terminal_saved() };
	},

	cajaBorrar: async ({ request, locals, url }) => {
		requireAdmin(locals, url.pathname);

		const form = await request.formData();
		const id = Number(form.get('id') ?? 0);
		try {
			await api(`/offices/terminals/${id}`, { method: 'DELETE', token: locals.token });
		} catch (error) {
			return fail(400, { errors: formError(apiMessage(error)) });
		}
		return { success: m.settings_offices_terminal_removed() };
	}
};
