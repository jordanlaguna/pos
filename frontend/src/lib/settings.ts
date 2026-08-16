/**
 * Configuración del negocio.
 *
 * Todo lo que antes estaba escrito en el código —el colón, el IVA al 13 %, el
 * nombre «VentaSys» impreso en cada tiquete— vive acá y lo edita el dueño desde
 * `/configuracion`. Se guarda como un objeto JSON en una sola fila del backend
 * (`GET/PUT /settings/`), así que agregar una casilla no exige migrar la base.
 *
 * La contraparte de esa flexibilidad es que lo que llega del backend puede tener
 * cualquier forma: una versión vieja, un campo que se renombró, una fila que
 * quedó a medias. Por eso nada lee el JSON crudo. Todo pasa por `mergeSettings`,
 * que lo funde sobre los valores por omisión y convierte cada campo al tipo que
 * corresponde. Un POS que no abre porque la configuración tiene una coma de más
 * es peor que uno con la moneda de fábrica.
 */

export interface BusinessSettings {
	nombre: string;
	razon_social: string;
	identificacion: string;
	tipo_identificacion: string;
	telefono: string;
	correo: string;
	direccion: string;
	sitio_web: string;
}

export interface CurrencySettings {
	codigo: string;
	simbolo: string;
	decimales: number;
	separador_miles: string;
	separador_decimal: string;
	/** `1.450,00 ₡` en vez de `₡1.450,00`. El euro se escribe así. */
	simbolo_al_final: boolean;
	/** Espacio entre el símbolo y la cifra. */
	espacio: boolean;
}

export interface TaxSettings {
	/** Cómo se llama el impuesto en la factura: IVA, ISV, IGV… */
	nombre: string;
	/** Expresada entre 0 y 1. 0.13 = 13 %. */
	tasa: number;
}

export type PlantillaId = 'tiquete' | 'clasica' | 'moderna';

export interface DocumentSettings {
	plantilla: PlantillaId;
	/** Color de marca del documento impreso. No es el de la interfaz. */
	color: string;
	mostrar_logo: boolean;
	/** Código de barras junto al nombre de cada línea. */
	mostrar_codigo: boolean;
	/** Ancho del rollo térmico, en milímetros. */
	ancho_tiquete: 58 | 80;
	mensaje_gracias: string;
	/** Pie legal. Mientras no se emita factura electrónica, lo dice acá. */
	leyenda: string;
	/** Condiciones o notas al pie de la factura de página completa. */
	notas: string;
}

export interface AppearanceSettings {
	/** Acento de la interfaz. Se derivan de él el tono claro, el oscuro y la tinta. */
	color_acento: string;
}

export interface EInvoiceSettings {
	activa: boolean;
	ambiente: 'sandbox' | 'produccion';
	actividad_economica: string;
	sucursal: string;
	terminal: string;
	usuario_atv: string;
}

export interface Settings {
	negocio: BusinessSettings;
	moneda: CurrencySettings;
	impuesto: TaxSettings;
	documento: DocumentSettings;
	apariencia: AppearanceSettings;
	electronica: EInvoiceSettings;
}

/** Logo del negocio, tal como lo guarda el backend. */
export interface LogoSettings {
	mime: string;
	/** base64 sin el prefijo `data:`. */
	data: string;
}

/** Respuesta completa de `GET /settings/`. */
export interface StoredSettings {
	settings: Settings;
	logo: LogoSettings | null;
	updated_at: string | null;
	/**
	 * Sello de versión del logo. Cambia cuando cambia la imagen, y solo entonces,
	 * así que `/marca/logo?v=…` se puede cachear para siempre sin quedar viejo.
	 */
	logo_version: string;
}

// ------------------------------------------------------------------- monedas

export interface CurrencyPreset extends CurrencySettings {
	nombre: string;
}

/**
 * Monedas preconfiguradas.
 *
 * Elegir una llena símbolo, decimales y separadores de una vez; después se
 * pueden ajustar a mano. Los separadores no salen de `Intl`: CLDR le asigna a
 * es-CR el espacio duro (`₡3 175 119,20`), que no es como se escribe en el
 * comercio costarricense. Cuando la convención local y el estándar no coinciden,
 * manda la convención local, y para eso hay que poder escribirla.
 */
export const MONEDAS: CurrencyPreset[] = [
	{ codigo: 'CRC', nombre: 'Colón costarricense', simbolo: '₡', decimales: 2, separador_miles: '.', separador_decimal: ',', simbolo_al_final: false, espacio: false },
	{ codigo: 'USD', nombre: 'Dólar estadounidense', simbolo: '$', decimales: 2, separador_miles: ',', separador_decimal: '.', simbolo_al_final: false, espacio: false },
	{ codigo: 'EUR', nombre: 'Euro', simbolo: '€', decimales: 2, separador_miles: '.', separador_decimal: ',', simbolo_al_final: true, espacio: true },
	{ codigo: 'MXN', nombre: 'Peso mexicano', simbolo: '$', decimales: 2, separador_miles: ',', separador_decimal: '.', simbolo_al_final: false, espacio: false },
	{ codigo: 'GTQ', nombre: 'Quetzal guatemalteco', simbolo: 'Q', decimales: 2, separador_miles: ',', separador_decimal: '.', simbolo_al_final: false, espacio: false },
	{ codigo: 'HNL', nombre: 'Lempira hondureño', simbolo: 'L', decimales: 2, separador_miles: ',', separador_decimal: '.', simbolo_al_final: false, espacio: true },
	{ codigo: 'NIO', nombre: 'Córdoba nicaragüense', simbolo: 'C$', decimales: 2, separador_miles: ',', separador_decimal: '.', simbolo_al_final: false, espacio: false },
	{ codigo: 'PAB', nombre: 'Balboa panameño', simbolo: 'B/.', decimales: 2, separador_miles: ',', separador_decimal: '.', simbolo_al_final: false, espacio: false },
	{ codigo: 'DOP', nombre: 'Peso dominicano', simbolo: 'RD$', decimales: 2, separador_miles: ',', separador_decimal: '.', simbolo_al_final: false, espacio: false },
	{ codigo: 'COP', nombre: 'Peso colombiano', simbolo: '$', decimales: 0, separador_miles: '.', separador_decimal: ',', simbolo_al_final: false, espacio: false },
	{ codigo: 'PEN', nombre: 'Sol peruano', simbolo: 'S/', decimales: 2, separador_miles: ',', separador_decimal: '.', simbolo_al_final: false, espacio: true },
	{ codigo: 'CLP', nombre: 'Peso chileno', simbolo: '$', decimales: 0, separador_miles: '.', separador_decimal: ',', simbolo_al_final: false, espacio: false },
	{ codigo: 'ARS', nombre: 'Peso argentino', simbolo: '$', decimales: 2, separador_miles: '.', separador_decimal: ',', simbolo_al_final: false, espacio: false }
];

// ---------------------------------------------------------------- plantillas

export interface PlantillaInfo {
	id: PlantillaId;
	nombre: string;
	descripcion: string;
	/** Papel para el que está pensada. */
	papel: string;
}

export const PLANTILLAS: PlantillaInfo[] = [
	{
		id: 'tiquete',
		nombre: 'Tiquete térmico',
		descripcion:
			'Una columna, sin colores, pensado para el rollo de la impresora del mostrador. Es lo que quiere una pulpería o un abarrotes: sale en dos segundos y no gasta tinta.',
		papel: 'Rollo de 58 u 80 mm'
	},
	{
		id: 'clasica',
		nombre: 'Factura clásica',
		descripcion:
			'Página completa, franja de color con el nombre del negocio, datos del emisor y del cliente enfrentados, tabla sobria y bloque de totales a la derecha. Sirve para mandar por correo.',
		papel: 'Carta / A4'
	},
	{
		id: 'moderna',
		nombre: 'Factura moderna',
		descripcion:
			'Página completa con encabezado en diagonal, logo destacado, tabla con cabecera de color y pie de contacto. La misma información que la clásica, con más presencia de marca.',
		papel: 'Carta / A4'
	}
];

// ------------------------------------------------------- valores por omisión

export const DEFAULT_SETTINGS: Settings = {
	negocio: {
		nombre: 'VentaSys',
		razon_social: '',
		identificacion: '',
		tipo_identificacion: '01',
		telefono: '',
		correo: '',
		direccion: '',
		sitio_web: ''
	},
	moneda: { ...MONEDAS[0] } as CurrencySettings,
	impuesto: { nombre: 'IVA', tasa: 0.13 },
	documento: {
		plantilla: 'tiquete',
		color: '#0e7490',
		mostrar_logo: true,
		mostrar_codigo: false,
		ancho_tiquete: 80,
		mensaje_gracias: '¡Gracias por su compra!',
		leyenda: 'Este documento no tiene validez tributaria.',
		notas: ''
	},
	apariencia: { color_acento: '#0e7490' },
	electronica: {
		activa: false,
		ambiente: 'sandbox',
		actividad_economica: '',
		sucursal: '001',
		terminal: '00001',
		usuario_atv: ''
	}
};

/** Tipos de identificación de Hacienda (Costa Rica). */
export const TIPOS_IDENTIFICACION = [
	{ codigo: '01', nombre: 'Cédula física' },
	{ codigo: '02', nombre: 'Cédula jurídica' },
	{ codigo: '03', nombre: 'DIMEX' },
	{ codigo: '04', nombre: 'NITE' }
] as const;

// ------------------------------------------------------------------- fusión

function str(value: unknown, fallback: string, max = 500): string {
	if (typeof value !== 'string') return fallback;
	const trimmed = value.trim();
	return trimmed ? trimmed.slice(0, max) : fallback;
}

/** Igual que `str` pero acepta el vacío como valor legítimo (campos opcionales). */
function optional(value: unknown, fallback: string, max = 500): string {
	if (typeof value !== 'string') return fallback;
	return value.trim().slice(0, max);
}

function bool(value: unknown, fallback: boolean): boolean {
	return typeof value === 'boolean' ? value : fallback;
}

function num(value: unknown, fallback: number, min: number, max: number): number {
	const n = typeof value === 'number' ? value : Number(value);
	return Number.isFinite(n) && n >= min && n <= max ? n : fallback;
}

/** Un separador es exactamente un carácter, o ninguno (miles sin separar). */
function separator(value: unknown, fallback: string): string {
	return typeof value === 'string' && value.length <= 1 ? value : fallback;
}

/** `#rrggbb`. Cualquier otra cosa se descarta: va a parar a un `style`. */
export function isHexColor(value: unknown): value is string {
	return typeof value === 'string' && /^#[0-9a-fA-F]{6}$/.test(value);
}

function color(value: unknown, fallback: string): string {
	return isHexColor(value) ? value.toLowerCase() : fallback;
}

function pick<T extends string>(value: unknown, allowed: readonly T[], fallback: T): T {
	return typeof value === 'string' && (allowed as readonly string[]).includes(value)
		? (value as T)
		: fallback;
}

function obj(value: unknown): Record<string, unknown> {
	return value && typeof value === 'object' && !Array.isArray(value)
		? (value as Record<string, unknown>)
		: {};
}

/**
 * Convierte lo que sea que haya guardado el backend en una configuración usable.
 * Nunca lanza: cada campo malo se reemplaza por el de fábrica.
 */
export function mergeSettings(raw: unknown): Settings {
	const source = obj(raw);
	const d = DEFAULT_SETTINGS;

	const negocio = obj(source.negocio);
	const moneda = obj(source.moneda);
	const impuesto = obj(source.impuesto);
	const documento = obj(source.documento);
	const apariencia = obj(source.apariencia);
	const electronica = obj(source.electronica);

	return {
		negocio: {
			nombre: str(negocio.nombre, d.negocio.nombre, 120),
			razon_social: optional(negocio.razon_social, d.negocio.razon_social, 160),
			identificacion: optional(negocio.identificacion, d.negocio.identificacion, 30),
			tipo_identificacion: pick(
				negocio.tipo_identificacion,
				TIPOS_IDENTIFICACION.map((t) => t.codigo),
				d.negocio.tipo_identificacion as '01'
			),
			telefono: optional(negocio.telefono, d.negocio.telefono, 30),
			correo: optional(negocio.correo, d.negocio.correo, 120),
			direccion: optional(negocio.direccion, d.negocio.direccion, 300),
			sitio_web: optional(negocio.sitio_web, d.negocio.sitio_web, 120)
		},
		moneda: {
			codigo: str(moneda.codigo, d.moneda.codigo, 8).toUpperCase(),
			simbolo: str(moneda.simbolo, d.moneda.simbolo, 5),
			decimales: num(moneda.decimales, d.moneda.decimales, 0, 4),
			separador_miles: separator(moneda.separador_miles, d.moneda.separador_miles),
			separador_decimal: separator(moneda.separador_decimal, d.moneda.separador_decimal),
			simbolo_al_final: bool(moneda.simbolo_al_final, d.moneda.simbolo_al_final),
			espacio: bool(moneda.espacio, d.moneda.espacio)
		},
		impuesto: {
			nombre: str(impuesto.nombre, d.impuesto.nombre, 20),
			tasa: num(impuesto.tasa, d.impuesto.tasa, 0, 1)
		},
		documento: {
			plantilla: pick(documento.plantilla, ['tiquete', 'clasica', 'moderna'], d.documento.plantilla),
			color: color(documento.color, d.documento.color),
			mostrar_logo: bool(documento.mostrar_logo, d.documento.mostrar_logo),
			mostrar_codigo: bool(documento.mostrar_codigo, d.documento.mostrar_codigo),
			ancho_tiquete: num(documento.ancho_tiquete, d.documento.ancho_tiquete, 58, 80) === 58 ? 58 : 80,
			mensaje_gracias: optional(documento.mensaje_gracias, d.documento.mensaje_gracias, 120),
			leyenda: optional(documento.leyenda, d.documento.leyenda, 240),
			notas: optional(documento.notas, d.documento.notas, 600)
		},
		apariencia: {
			color_acento: color(apariencia.color_acento, d.apariencia.color_acento)
		},
		electronica: {
			activa: bool(electronica.activa, d.electronica.activa),
			ambiente: pick(electronica.ambiente, ['sandbox', 'produccion'], d.electronica.ambiente),
			actividad_economica: optional(
				electronica.actividad_economica,
				d.electronica.actividad_economica,
				10
			),
			sucursal: optional(electronica.sucursal, d.electronica.sucursal, 3),
			terminal: optional(electronica.terminal, d.electronica.terminal, 5),
			usuario_atv: optional(electronica.usuario_atv, d.electronica.usuario_atv, 120)
		}
	};
}

/** Nombre a mostrar del negocio: el comercial, y si no hay, la razón social. */
export function businessName(settings: Settings): string {
	return settings.negocio.nombre || settings.negocio.razon_social || 'VentaSys';
}
