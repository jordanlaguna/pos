import { fail } from '@sveltejs/kit';

import { api } from '$lib/server/api';
import { requireAdmin, setSessionCookie } from '$lib/server/auth';
import { invalidateSettings, loadSettings, saveSettings } from '$lib/server/settings';
import { formError, Validator } from '$lib/application/validation';
import { F } from '$lib/ui/fields';
import { m } from '$lib/paraglide/messages.js';
import { apiMessage, validationErrors } from '$lib/ui/messages';
import {
	isHexColor,
	mergeSettings,
	ID_TYPES,
	type LogoSettings,
	type Settings
} from '$lib/domain/settings';
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

export const load: PageServerLoad = async ({ locals, url }) => {
	const admin = requireAdmin(locals, url.pathname);
	const stored = await loadSettings(locals.token, admin.company_id);

	return {
		configuracion: stored.settings,
		tieneLogo: stored.logo !== null,
		actualizado: stored.updated_at
	};
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

		const form = await request.formData();
		const v = new Validator(form);

		const nombre = v.text('negocio_nombre', F.businessName(), { max: 120 });
		const razonSocial = v.text('negocio_razon_social', F.businessLegalName(), {
			required: false,
			max: 160
		});
		const identificacion = v.text('negocio_identificacion', F.businessIdentification(), {
			required: false,
			max: 30
		});
		const tipoIdentificacion = v.oneOf(
			'negocio_tipo_identificacion',
			F.businessIdType(),
			ID_TYPES.map((t) => t.code),
			{ required: false }
		);
		const telefono = v.text('negocio_telefono', F.businessTelephone(), { required: false, max: 30 });
		const correo = v.email('negocio_correo', F.businessEmail(), { required: false });
		const direccion = v.text('negocio_direccion', F.businessAddress(), { required: false, max: 300 });
		const sitioWeb = v.text('negocio_sitio_web', F.businessWebsite(), { required: false, max: 120 });

		const codigo = v.text('moneda_codigo', F.currencyCode(), { max: 8 });
		const simbolo = v.text('moneda_simbolo', F.currencySymbol(), { max: 5 });
		const decimales = v.integer('moneda_decimales', F.decimals(), { min: 0, max: 4 });

		const impuestoNombre = v.text('impuesto_nombre', F.taxName(), { max: 20 });
		// En pantalla se escribe 13, no 0.13: nadie piensa el IVA en fracciones.
		const tasaPorcentaje = v.decimal('impuesto_tasa', F.taxRate(), { min: 0, max: 100 });

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

		const ambiente = v.oneOf('electronica_ambiente', F.einvoicingEnvironment(), [
			'sandbox',
			'produccion'
		] as const);
		const actividad = v.text('electronica_actividad', F.einvoicingActivity(), {
			required: false,
			max: 10
		});
		const sucursal = v.text('electronica_sucursal', F.einvoicingBranch(), { required: false, max: 3 });
		const terminal = v.text('electronica_terminal', F.einvoicingTerminal(), { required: false, max: 5 });
		const usuarioAtv = v.text('electronica_usuario', F.einvoicingAtvUser(), {
			required: false,
			max: 120
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

		if (!v.ok) return fail(400, { errors: validationErrors(v.errors) });

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
				identificacion,
				taxIdType: tipoIdentificacion || '01',
				telefono,
				correo,
				direccion,
				website: sitioWeb
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
			tax: {
				nombre: impuestoNombre,
				// 13 → 0.13, sin arrastrar el error binario de la división.
				rate: Math.round((tasaPorcentaje / 100) * 1e6) / 1e6
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
				environment: ambiente || 'sandbox',
				economicActivity: actividad,
				sucursal,
				terminal,
				atvUser: usuarioAtv
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
	}
};
