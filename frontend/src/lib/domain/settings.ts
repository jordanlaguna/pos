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
 *
 * **Sobre las claves en español.** Hasta el 2026-08-16 este archivo usaba
 * identificadores en español (`negocio`, `moneda`, `impuesto`…) y esas mismas
 * palabras eran las claves del JSON guardado. T-113 los pasó a inglés, como el
 * resto del código; los textos de la interfaz siguen en español. `mergeSettings`
 * lee **las dos formas** para que una fila escrita antes del cambio se siga
 * entendiendo: si solo leyera las nuevas, actualizar el sistema le borraría al
 * dueño su moneda, su logo y su tasa de impuesto sin decir nada.
 */

import { DEFAULT_ENABLED, enabledTypes } from './documentType';
import { EMPTY_LOCATION, normalizeLocation, type IssuerLocation } from './location';

export interface BusinessSettings {
	name: string;
	legalName: string;
	taxId: string;
	taxIdType: string;
	phone: string;
	email: string;
	address: string;
	website: string;
	/**
	 * La ubicación con los códigos de Hacienda (T-722, RN-83). No reemplaza a
	 * `address`: esa es la del tiquete, en texto libre; esta es la del XML.
	 */
	location: IssuerLocation;
}

export interface CurrencySettings {
	code: string;
	symbol: string;
	decimals: number;
	thousandsSeparator: string;
	decimalSeparator: string;
	/** `1.450,00 ₡` en vez de `₡1.450,00`. El euro se escribe así. */
	symbolAtEnd: boolean;
	/** Espacio entre el símbolo y la cifra. */
	space: boolean;
}

export interface TaxSettings {
	/** Cómo se llama el impuesto en la factura. */
	name: string;
	/** Expresada entre 0 y 1. 0.13 = 13 %. */
	rate: number;
}

/**
 * El impuesto, que **ya no se configura** (QA-05).
 *
 * La tarifa de cada producto la da su CABYS; la de uno sin CABYS es la general
 * del IVA, el 13 % de ley (RN-9). Antes era «la tasa del negocio» de la pestaña
 * Moneda, y con la tarifa por CABYS ese campo solo servía para equivocarse: un
 * 10 % escrito ahí se cobraba en todo producto sin clasificar. El backend tiene
 * la misma tarifa en `domain/tax.py` (`GENERAL_RATE`), y descarta lo que llegue
 * como impuesto al guardar la configuración.
 */
export const VAT: TaxSettings = Object.freeze({ name: 'IVA', rate: 0.13 });

export type TemplateId = 'tiquete' | 'clasica' | 'moderna';

export interface DocumentSettings {
	template: TemplateId;
	/** Color de marca del documento impreso. No es el de la interfaz. */
	color: string;
	showLogo: boolean;
	/** Código de barras junto al nombre de cada línea. */
	showBarcode: boolean;
	/** Ancho del rollo térmico, en milímetros. */
	receiptWidth: 58 | 80;
	thanksMessage: string;
	/** Pie legal. Mientras no se emita factura electrónica, lo dice acá. */
	legalNotice: string;
	/** Condiciones o notas al pie de la factura de página completa. */
	notes: string;
}

export interface AppearanceSettings {
	/** Acento de la interfaz. Se derivan de él el tono claro, el oscuro y la tinta. */
	accentColor: string;
}

/**
 * Lo que la configuración de la compañía tiene que decir sobre factura
 * electrónica, y **solo eso** (T-614).
 *
 * Tenía tres campos más —`branch`, `terminal` y `atvUser`— y los tres estaban
 * en el sitio equivocado, no de más:
 *
 * - **La sucursal y la terminal ya las resuelve la sesión.** `sucursal_actual()`
 *   y `terminal_actual()` las fijan desde el token, cada venta guarda su
 *   `terminal_id` y `/users/me` publica los dos códigos. Acá eran una copia por
 *   compañía de algo que ya es por sesión, y la copia estaba **rota por
 *   construcción**: hay una sola fila de configuración por compañía, así que dos
 *   cajas del mismo negocio declaraban la misma terminal — y dos terminales con
 *   el mismo código producen consecutivos repetidos, que Hacienda rechaza.
 * - **El usuario de ATV es por ambiente**, no por compañía: el de pruebas y el
 *   de producción son credenciales distintas. Vive en `fe_credentials`, con su
 *   contraseña, donde la llave primaria es `(company_id, environment)`.
 *
 * Queda lo que sí es de la compañía y uno solo: si emite, contra qué ambiente y
 * con qué actividad económica.
 */
export interface EInvoiceSettings {
	enabled: boolean;
	/**
	 * `production` y no `produccion`: el código va en inglés y es el mismo valor
	 * que estrena la columna `environment` de `fe_credentials`. Tener dos
	 * vocablos para el mismo estado es cómo se pierde una migración.
	 */
	environment: 'sandbox' | 'production';
	economicActivity: string;
	/**
	 * Los comprobantes que emite este negocio (RN-88): códigos de Hacienda, en
	 * el orden de `ALL_TYPES`. **Siempre saneada**: sin tiquete ni factura, o
	 * sin la NC, no sale de `mergeSettings`.
	 */
	documentTypes: string[];
}

/** El inventario a fondo (F15). */
export interface InventorySettings {
	/**
	 * El mínimo general de existencia (RN-101): lo usa todo producto sin mínimo
	 * propio. **Nulo es «sin general»**, y entonces solo avisan los que tienen el
	 * suyo; no es lo mismo que ausente, que cae al 10 de fábrica.
	 */
	minStock: number | null;
	/** Si la compañía lleva lotes y vencimientos (RN-104, T-1507). */
	lotsEnabled: boolean;
}

export interface Settings {
	business: BusinessSettings;
	currency: CurrencySettings;
	tax: TaxSettings;
	document: DocumentSettings;
	appearance: AppearanceSettings;
	eInvoicing: EInvoiceSettings;
	inventory: InventorySettings;
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
	/**
	 * La identificación del emisor, de `companies` (RN-45). La fija soporte y la
	 * pantalla la muestra sin dejarla editar; nula mientras no la haya fijado.
	 */
	issuer: Issuer | null;
}

/** Lo que `GET /settings/` dice del emisor. */
export interface Issuer {
	identification: string | null;
	identification_type: string | null;
}

/**
 * La configuración con la identificación **de la compañía** en lugar de la
 * escrita en Configuración (RN-45, T-621).
 *
 * La clave de cada comprobante lleva la de `companies`, así que es la que se
 * imprime: dos cédulas distintas en la misma factura —una en la clave y otra en
 * el emisor— son un comprobante que no se sostiene. Sin la de la compañía, queda
 * la escrita, que es lo que había antes.
 */
export function withIssuer(settings: Settings, issuer: Issuer | null | undefined): Settings {
	if (!issuer?.identification) return settings;
	return {
		...settings,
		business: {
			...settings.business,
			taxId: issuer.identification,
			taxIdType: issuer.identification_type ?? settings.business.taxIdType
		}
	};
}

// ------------------------------------------------------------------- monedas

/**
 * Monedas preconfiguradas.
 *
 * Elegir una llena símbolo, decimales y separadores de una vez; después se
 * pueden ajustar a mano. Los separadores no salen de `Intl`: CLDR le asigna a
 * es-CR el espacio duro (`₡3 175 119,20`), que no es como se escribe en el
 * comercio costarricense. Cuando la convención local y el estándar no coinciden,
 * manda la convención local, y para eso hay que poder escribirla.
 */
export const CURRENCIES: CurrencySettings[] = [
	{ code: 'CRC', symbol: '₡', decimals: 2, thousandsSeparator: '.', decimalSeparator: ',', symbolAtEnd: false, space: false },
	{ code: 'USD', symbol: '$', decimals: 2, thousandsSeparator: ',', decimalSeparator: '.', symbolAtEnd: false, space: false },
	{ code: 'EUR', symbol: '€', decimals: 2, thousandsSeparator: '.', decimalSeparator: ',', symbolAtEnd: true, space: true },
	{ code: 'MXN', symbol: '$', decimals: 2, thousandsSeparator: ',', decimalSeparator: '.', symbolAtEnd: false, space: false },
	{ code: 'GTQ', symbol: 'Q', decimals: 2, thousandsSeparator: ',', decimalSeparator: '.', symbolAtEnd: false, space: false },
	{ code: 'HNL', symbol: 'L', decimals: 2, thousandsSeparator: ',', decimalSeparator: '.', symbolAtEnd: false, space: true },
	{ code: 'NIO', symbol: 'C$', decimals: 2, thousandsSeparator: ',', decimalSeparator: '.', symbolAtEnd: false, space: false },
	{ code: 'PAB', symbol: 'B/.', decimals: 2, thousandsSeparator: ',', decimalSeparator: '.', symbolAtEnd: false, space: false },
	{ code: 'DOP', symbol: 'RD$', decimals: 2, thousandsSeparator: ',', decimalSeparator: '.', symbolAtEnd: false, space: false },
	{ code: 'COP', symbol: '$', decimals: 0, thousandsSeparator: '.', decimalSeparator: ',', symbolAtEnd: false, space: false },
	{ code: 'PEN', symbol: 'S/', decimals: 2, thousandsSeparator: ',', decimalSeparator: '.', symbolAtEnd: false, space: true },
	{ code: 'CLP', symbol: '$', decimals: 0, thousandsSeparator: '.', decimalSeparator: ',', symbolAtEnd: false, space: false },
	{ code: 'ARS', symbol: '$', decimals: 2, thousandsSeparator: '.', decimalSeparator: ',', symbolAtEnd: false, space: false }
];

// ---------------------------------------------------------------- plantillas

/**
 * Las plantillas que existen, en el orden en que se ofrecen.
 *
 * Solo los identificadores. El nombre, el papel y la descripción son texto para
 * una persona y viven en el catálogo del idioma (`settings.json`): acá dentro
 * serían una constante de módulo, o sea el mismo texto para todas las
 * peticiones del proceso —el defecto 17— además de intraducible.
 */
export const TEMPLATE_IDS: readonly TemplateId[] = ['tiquete', 'clasica', 'moderna'];

// ------------------------------------------------------- valores por omisión

export const DEFAULT_SETTINGS: Settings = {
	business: {
		name: 'VentaSys',
		legalName: '',
		taxId: '',
		taxIdType: '01',
		phone: '',
		email: '',
		address: '',
		website: '',
		location: { ...EMPTY_LOCATION }
	},
	currency: { ...CURRENCIES[0] },
	tax: { ...VAT },
	document: {
		template: 'tiquete',
		color: '#0e7490',
		showLogo: true,
		showBarcode: false,
		receiptWidth: 80,
		/*
		 * Vacíos, y no «¡Gracias por su compra!» y «Este documento no tiene validez
		 * tributaria.», que es lo que decían (RN-30).
		 *
		 * Son texto que se imprime, y de fábrica venían en español: la factura de
		 * una compañía brasileña salía con la despedida en español hasta que
		 * alguien abriera Configuración. El dominio no puede traducirlos —no lee el
		 * catálogo, y si lo leyera congelaría el idioma de la primera petición
		 * (defecto 17)— y la interfaz no puede ponerlos como respaldo del vacío,
		 * porque `optional()` distingue «nunca se configuró» de «se borró a
		 * propósito» y ese respaldo borraría la diferencia: quien quite la
		 * despedida la vería volver.
		 *
		 * Se siembran al dar de alta la compañía, que es cuando se conoce su idioma
		 * (RF-6, T-304). Las tres plantillas ya los omiten si vienen vacíos.
		 */
		thanksMessage: '',
		legalNotice: '',
		notes: ''
	},
	appearance: { accentColor: '#0e7490' },
	eInvoicing: {
		enabled: false,
		environment: 'sandbox',
		economicActivity: '',
		documentTypes: [...DEFAULT_ENABLED]
	},
	// El 10 que tenía el aviso del panel cuando era una variable de entorno
	// igual para todas las compañías (RN-101): nadie lo pierde al migrar.
	inventory: { minStock: 10, lotsEnabled: false }
};

/**
 * Tipos de identificación de Hacienda (Costa Rica).
 *
 * El rótulo se queda acá, y no en el catálogo, porque es el nombre legal del
 * documento en Costa Rica: «Cédula jurídica» no se traduce a portugués, se
 * cambia por la lista de otro país. El día que VentaSys se venda fuera, lo que
 * cambia es la lista entera según el país de la compañía, no su traducción.
 */
export const ID_TYPES = [
	{ code: '01', label: 'Cédula física' },
	{ code: '02', label: 'Cédula jurídica' },
	{ code: '03', label: 'DIMEX' },
	{ code: '04', label: 'NITE' },
	// Los dos de F7: el extranjero recibe la factura de exportación (T-727) y
	// el no contribuyente, como proveedor, la de compra (T-728).
	{ code: '05', label: 'Extranjero no domiciliado' },
	{ code: '06', label: 'No contribuyente' }
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

/**
 * Un entero dentro de un rango, **o nulo si se guardó nulo a propósito**.
 *
 * Es `num` para los campos donde el vacío es una decisión: quitar el mínimo
 * general (RN-101) no es olvidarlo, y no puede volver al de fábrica solo. Lo
 * ausente o lo inválido sí cae al de fábrica, como en todos los demás.
 */
function nullableInt(value: unknown, fallback: number | null, min: number, max: number): number | null {
	if (value === null) return null;
	const n = num(value, Number.NaN, min, max);
	return Number.isInteger(n) ? n : fallback;
}

/**
 * Número dentro de un rango, o el de fábrica.
 *
 * No usa `Number(value)` a secas: `Number(null)`, `Number('')`, `Number([])` y
 * `Number(false)` valen **0**, y el cero casi siempre cae dentro del rango
 * permitido. Con esa versión, un `tax: { rate: null }` guardado a medias se
 * leía como impuesto del **0 %** en lugar de caer al 13 % —en silencio, y
 * cobrando de menos en cada venta hasta que alguien revisara una factura—.
 * Solo un número o una cadena con algo escrito adentro cuentan como valor.
 */
function num(value: unknown, fallback: number, min: number, max: number): number {
	const n =
		typeof value === 'number'
			? value
			: typeof value === 'string' && value.trim() !== ''
				? Number(value)
				: Number.NaN;
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

/**
 * El ambiente, aceptando lo que se guardó antes en español (T-614).
 *
 * `'produccion'` se lee como `'production'` en vez de caer al de fábrica.
 * Tratarlo como valor inválido tendría un efecto peor que perder el dato:
 * devolvería `'sandbox'`, y un negocio que ya estaba emitiendo en producción
 * pasaría a pruebas sin que nadie lo pidiera ni lo viera.
 *
 * La conversión vive acá y no en una migración de la base porque la
 * configuración es un JSON que se lee entero por este camino: cualquier fila
 * vieja queda al día la primera vez que se abre, y la que nunca se abra no
 * hace daño.
 */
function environment(value: unknown, fallback: 'sandbox' | 'production') {
	if (value === 'produccion') return 'production';
	return pick(value, ['sandbox', 'production'] as const, fallback);
}

function obj(value: unknown): Record<string, unknown> {
	return value && typeof value === 'object' && !Array.isArray(value)
		? (value as Record<string, unknown>)
		: {};
}

/**
 * El valor de una clave, aceptando también el nombre que tenía en español.
 *
 * Una fila guardada antes de T-113 trae `{ moneda: { codigo: 'USD' } }`; una
 * nueva trae `{ currency: { code: 'USD' } }`. Se prefiere la nueva y se cae a la
 * vieja, de modo que actualizar el sistema no le borre la configuración a nadie.
 */
function legacy(source: Record<string, unknown>, key: string, spanish: string): unknown {
	return source[key] !== undefined ? source[key] : source[spanish];
}

/**
 * Convierte lo que sea que haya guardado el backend en una configuración usable.
 * Nunca lanza: cada campo malo se reemplaza por el de fábrica.
 */
export function mergeSettings(raw: unknown): Settings {
	const source = obj(raw);
	const d = DEFAULT_SETTINGS;

	const business = obj(legacy(source, 'business', 'negocio'));
	const currency = obj(legacy(source, 'currency', 'moneda'));
	// `doc` y no `document`: una variable con ese nombre tapa el global del
	// navegador, justo en el módulo que tiene prohibido tocarlo.
	const doc = obj(legacy(source, 'document', 'documento'));
	const appearance = obj(legacy(source, 'appearance', 'apariencia'));
	const eInvoicing = obj(legacy(source, 'eInvoicing', 'electronica'));
	const inventory = obj(legacy(source, 'inventory', 'inventario'));

	const width = num(
		legacy(doc, 'receiptWidth', 'ancho_tiquete'),
		d.document.receiptWidth,
		58,
		80
	);

	return {
		business: {
			name: str(legacy(business, 'name', 'nombre'), d.business.name, 120),
			legalName: optional(legacy(business, 'legalName', 'razon_social'), d.business.legalName, 160),
			taxId: optional(legacy(business, 'taxId', 'identificacion'), d.business.taxId, 30),
			taxIdType: pick(
				legacy(business, 'taxIdType', 'tipo_identificacion'),
				ID_TYPES.map((t) => t.code),
				d.business.taxIdType as '01'
			),
			phone: optional(legacy(business, 'phone', 'telefono'), d.business.phone, 30),
			email: optional(legacy(business, 'email', 'correo'), d.business.email, 120),
			address: optional(legacy(business, 'address', 'direccion'), d.business.address, 300),
			website: optional(legacy(business, 'website', 'sitio_web'), d.business.website, 120),
			location: normalizeLocation(business.location)
		},
		currency: {
			code: str(legacy(currency, 'code', 'codigo'), d.currency.code, 8).toUpperCase(),
			symbol: str(legacy(currency, 'symbol', 'simbolo'), d.currency.symbol, 5),
			decimals: num(legacy(currency, 'decimals', 'decimales'), d.currency.decimals, 0, 4),
			thousandsSeparator: separator(
				legacy(currency, 'thousandsSeparator', 'separador_miles'),
				d.currency.thousandsSeparator
			),
			decimalSeparator: separator(
				legacy(currency, 'decimalSeparator', 'separador_decimal'),
				d.currency.decimalSeparator
			),
			symbolAtEnd: bool(legacy(currency, 'symbolAtEnd', 'simbolo_al_final'), d.currency.symbolAtEnd),
			space: bool(legacy(currency, 'space', 'espacio'), d.currency.space)
		},
		// Lo que haya guardado no cuenta: el impuesto no se configura (QA-05).
		tax: { ...VAT },
		document: {
			template: pick(
				legacy(doc, 'template', 'plantilla'),
				['tiquete', 'clasica', 'moderna'],
				d.document.template
			),
			color: color(doc.color, d.document.color),
			showLogo: bool(legacy(doc, 'showLogo', 'mostrar_logo'), d.document.showLogo),
			showBarcode: bool(legacy(doc, 'showBarcode', 'mostrar_codigo'), d.document.showBarcode),
			receiptWidth: width === 58 ? 58 : 80,
			thanksMessage: optional(
				legacy(doc, 'thanksMessage', 'mensaje_gracias'),
				d.document.thanksMessage,
				120
			),
			legalNotice: optional(
				legacy(doc, 'legalNotice', 'leyenda'),
				d.document.legalNotice,
				240
			),
			notes: optional(legacy(doc, 'notes', 'notas'), d.document.notes, 600)
		},
		appearance: {
			accentColor: color(
				legacy(appearance, 'accentColor', 'color_acento'),
				d.appearance.accentColor
			)
		},
		eInvoicing: {
			enabled: bool(legacy(eInvoicing, 'enabled', 'activa'), d.eInvoicing.enabled),
			environment: environment(
				legacy(eInvoicing, 'environment', 'ambiente'),
				d.eInvoicing.environment
			),
			economicActivity: optional(
				legacy(eInvoicing, 'economicActivity', 'actividad_economica'),
				d.eInvoicing.economicActivity,
				10
			),
			// El mismo saneo que el servidor (RN-88): lo que la pantalla muestra
			// encendido es lo que el backend deja emitir.
			documentTypes: enabledTypes(eInvoicing.documentTypes)
		},
		inventory: {
			// `min_stock` es como lo sembró la migración 023; `minStock`, como lo
			// escribe esta pantalla. El backend lee las dos igual (`get_min_stock`).
			minStock: nullableInt(
				legacy(inventory, 'minStock', 'min_stock'),
				d.inventory.minStock,
				0,
				1_000_000
			),
			lotsEnabled: bool(legacy(inventory, 'lotsEnabled', 'lots_enabled'), d.inventory.lotsEnabled)
		}
	};
}

/** Nombre a mostrar del negocio: el comercial, y si no hay, la razón social. */
export function businessName(settings: Settings): string {
	return settings.business.name || settings.business.legalName || 'VentaSys';
}
