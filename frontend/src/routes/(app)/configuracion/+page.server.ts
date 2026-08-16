import { fail } from '@sveltejs/kit';
import { toMessage } from '$lib/server/api';
import { requireAdmin } from '$lib/server/auth';
import { invalidateSettings, loadSettings, saveSettings } from '$lib/server/settings';
import { formError, Validator } from '$lib/validation';
import {
	isHexColor,
	mergeSettings,
	TIPOS_IDENTIFICACION,
	type LogoSettings,
	type Settings
} from '$lib/settings';
import type { Actions, PageServerLoad } from './$types';

/** Un logo más pesado que esto no mejora la factura; solo hace lenta cada pantalla. */
const MAX_LOGO_BYTES = 250 * 1024;

/*
 * SVG queda fuera a propósito. Es XML, admite <script> dentro, y este archivo se
 * sirve tal cual desde el mismo origen que el POS: subir un «logo» sería subir
 * código que corre con la sesión del cajero.
 */
const LOGO_TYPES = ['image/png', 'image/jpeg', 'image/webp'];

export const load: PageServerLoad = async ({ locals, url }) => {
	requireAdmin(locals, url.pathname);
	const stored = await loadSettings(locals.token);

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
	v.add(field, `${label} debe ser un color en formato #rrggbb.`);
	return fallback;
}

async function readLogo(form: FormData, v: Validator): Promise<LogoSettings | undefined> {
	const file = form.get('logo');
	// Sin archivo, o el input vacío que manda el navegador: se conserva el actual.
	if (!(file instanceof File) || file.size === 0) return undefined;

	if (!LOGO_TYPES.includes(file.type)) {
		v.add('logo', 'El logo debe ser PNG, JPG o WebP. Los SVG no se admiten por seguridad.');
		return undefined;
	}
	if (file.size > MAX_LOGO_BYTES) {
		v.add('logo', `El logo no puede pesar más de ${Math.round(MAX_LOGO_BYTES / 1024)} KB.`);
		return undefined;
	}

	const bytes = Buffer.from(await file.arrayBuffer());
	return { mime: file.type, data: bytes.toString('base64') };
}

export const actions: Actions = {
	guardar: async ({ request, locals, url }) => {
		requireAdmin(locals, url.pathname);

		const form = await request.formData();
		const v = new Validator(form);

		const nombre = v.text('negocio_nombre', 'El nombre del negocio', { max: 120 });
		const razonSocial = v.text('negocio_razon_social', 'La razón social', {
			required: false,
			max: 160
		});
		const identificacion = v.text('negocio_identificacion', 'La cédula', {
			required: false,
			max: 30
		});
		const tipoIdentificacion = v.oneOf(
			'negocio_tipo_identificacion',
			'El tipo de identificación',
			TIPOS_IDENTIFICACION.map((t) => t.codigo),
			{ required: false }
		);
		const telefono = v.text('negocio_telefono', 'El teléfono', { required: false, max: 30 });
		const correo = v.email('negocio_correo', 'El correo', { required: false });
		const direccion = v.text('negocio_direccion', 'La dirección', { required: false, max: 300 });
		const sitioWeb = v.text('negocio_sitio_web', 'El sitio web', { required: false, max: 120 });

		const codigo = v.text('moneda_codigo', 'El código de moneda', { max: 8 });
		const simbolo = v.text('moneda_simbolo', 'El símbolo de moneda', { max: 5 });
		const decimales = v.integer('moneda_decimales', 'Los decimales', { min: 0, max: 4 });

		const impuestoNombre = v.text('impuesto_nombre', 'El nombre del impuesto', { max: 20 });
		// En pantalla se escribe 13, no 0.13: nadie piensa el IVA en fracciones.
		const tasaPorcentaje = v.decimal('impuesto_tasa', 'La tasa de impuesto', { min: 0, max: 100 });

		const plantilla = v.oneOf('documento_plantilla', 'La plantilla', [
			'tiquete',
			'clasica',
			'moderna'
		] as const);
		const anchoTiquete = v.oneOf('documento_ancho', 'El ancho del tiquete', ['58', '80'] as const);
		const mensajeGracias = v.text('documento_mensaje', 'El mensaje de despedida', {
			required: false,
			max: 120
		});
		const leyenda = v.text('documento_leyenda', 'La leyenda', { required: false, max: 240 });
		const notas = v.text('documento_notas', 'Las notas', { required: false, max: 600 });

		const colorDocumento = hex(v, form, 'documento_color', 'El color del documento', '#0e7490');
		const colorAcento = hex(v, form, 'apariencia_color', 'El color de la interfaz', '#0e7490');

		const ambiente = v.oneOf('electronica_ambiente', 'El ambiente', [
			'sandbox',
			'produccion'
		] as const);
		const actividad = v.text('electronica_actividad', 'La actividad económica', {
			required: false,
			max: 10
		});
		const sucursal = v.text('electronica_sucursal', 'La sucursal', { required: false, max: 3 });
		const terminal = v.text('electronica_terminal', 'La terminal', { required: false, max: 5 });
		const usuarioAtv = v.text('electronica_usuario', 'El usuario de ATV', {
			required: false,
			max: 120
		});

		const logo = await readLogo(form, v);
		const quitarLogo = checked(form, 'quitar_logo');

		if (!v.ok) return fail(400, { errors: v.errors });

		/*
		 * Se arma el objeto y se vuelve a pasar por `mergeSettings`. Parece
		 * redundante después de validar campo por campo, pero es la misma función
		 * que sanea lo que llega del backend: si algún día se agrega un campo y se
		 * olvida validarlo acá, sigue habiendo un solo lugar donde se decide qué
		 * forma tiene una configuración válida.
		 */
		const settings: Settings = mergeSettings({
			negocio: {
				nombre,
				razon_social: razonSocial,
				identificacion,
				tipo_identificacion: tipoIdentificacion || '01',
				telefono,
				correo,
				direccion,
				sitio_web: sitioWeb
			},
			moneda: {
				codigo,
				simbolo,
				decimales,
				separador_miles: separator(form, 'moneda_separador_miles', '.'),
				separador_decimal: separator(form, 'moneda_separador_decimal', ','),
				simbolo_al_final: checked(form, 'moneda_simbolo_al_final'),
				espacio: checked(form, 'moneda_espacio')
			},
			impuesto: {
				nombre: impuestoNombre,
				// 13 → 0.13, sin arrastrar el error binario de la división.
				tasa: Math.round((tasaPorcentaje / 100) * 1e6) / 1e6
			},
			documento: {
				plantilla: plantilla || 'tiquete',
				color: colorDocumento,
				mostrar_logo: checked(form, 'documento_mostrar_logo'),
				mostrar_codigo: checked(form, 'documento_mostrar_codigo'),
				ancho_tiquete: anchoTiquete === '58' ? 58 : 80,
				mensaje_gracias: mensajeGracias,
				leyenda,
				notas
			},
			apariencia: { color_acento: colorAcento },
			electronica: {
				// La emisión todavía no está implementada; ver la nota de la pantalla.
				// Se guarda la intención, no se activa nada.
				activa: checked(form, 'electronica_activa'),
				ambiente: ambiente || 'sandbox',
				actividad_economica: actividad,
				sucursal,
				terminal,
				usuario_atv: usuarioAtv
			}
		});

		try {
			await saveSettings(locals.token, settings, quitarLogo && !logo ? null : logo);
		} catch (error) {
			invalidateSettings();
			return fail(400, { errors: formError(toMessage(error)) });
		}

		return { success: 'Configuración guardada.' };
	}
};
