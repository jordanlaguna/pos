/**
 * Modelo de dominio de VentaSys.
 *
 * Los nombres de campo replican exactamente los del backend FastAPI (snake_case,
 * más algunos camelCase heredados en Person) para que el JSON viaje sin traducción.
 * Provienen de postsys/model/*.cs del proyecto WinForms original.
 */

// ---------------------------------------------------------------- autenticación

export type Role = 'admin' | 'cajero';

/**
 * Los cinco estados de la suscripción (spec §2).
 *
 * Es un arreglo y no solo un tipo porque hace falta en ejecución: es el conjunto
 * cerrado contra el que `Validator.oneOf` decide si el estado que manda el panel
 * de soporte es válido, y el que llena el `<select>` de la ficha. Los valores son
 * los que guarda `companies.estado` en la base y **no se traducen**: la palabra
 * que se muestra la resuelve `companyStateLabel` en `$lib/ui/messages.ts`.
 *
 * El orden es el del ciclo de vida, que es también el que tiene sentido en un
 * desplegable: se prueba, se activa, vence, se suspende, se cancela.
 */
export const COMPANY_STATES = ['prueba', 'activa', 'vencida', 'suspendida', 'cancelada'] as const;

export type CompanyState = (typeof COMPANY_STATES)[number];

/**
 * Una compañía a la que la persona podría entrar.
 *
 * `motivo` es un **código**, no una frase: el backend no escribe texto para
 * personas (RN-30) y la interfaz se traduce. Quien arma la oración es el POS.
 */
export interface CompanyOption {
	id: number;
	afiliado: number;
	compania: number;
	nombre: string;
	estado: CompanyState;
	rol: Role;
	puede_entrar: boolean;
	motivo: string | null;
	/**
	 * Invitación sin aceptar (T-229). Viaja aparte de `puede_entrar` porque la
	 * diferencia entre «no podés» y «todavía no dijiste que sí» es justo lo que
	 * decide si la pantalla muestra un botón o una explicación.
	 */
	pendiente: boolean;
}

/**
 * Respuesta de `POST /auth/login`.
 *
 * `tipo` decide qué pasa después: con `sesion` se entra directo —una sola
 * compañía disponible, RN-25—, con `transito` hay que elegir (RF-27) y con
 * `soporte` no hay compañía que elegir porque no tiene ninguna (RN-4): esa
 * sesión va al panel `/admin`. El token de tránsito no abre ninguna puerta de
 * negocio.
 */
export interface LoginResponse {
	access_token: string;
	token_type: string;
	tipo: 'sesion' | 'transito' | 'soporte';
	user_id: number;
	company_id?: number | null;
	companies?: CompanyOption[];
}

/**
 * El estado de la suscripción, ya evaluado por el servidor (T-308, RF-10).
 *
 * Lo calcula el backend y no el POS, y es a propósito: depende del día de hoy, y
 * la hora la pone el servidor —dos relojes no se pueden comparar—. Acá solo se
 * pinta.
 *
 * `aviso` es un **código** y no una frase (RN-30). La oración la arma
 * `subscriptionNotice()` en `$lib/ui/messages.ts` con estos mismos datos.
 */
export interface Subscription {
	/** El efectivo: `activa` con la fecha pasada llega como `vencida`. */
	estado: CompanyState;
	/** El que está guardado. El panel muestra los dos; el POS usa el efectivo. */
	guardado: CompanyState;
	vence_el: string | null;
	/** Días hasta el vencimiento. Negativo si pasó, nulo si no hay fecha. */
	dias: number | null;
	/** Días de gracia que quedan, contando hoy. 0 = ya no se vende. */
	gracia: number;
	puede_entrar: boolean;
	puede_vender: boolean;
	aviso: 'en_prueba' | 'vence_pronto' | 'en_gracia' | 'solo_lectura' | 'suspendida' | 'cancelada' | null;
}

export interface ChooseCompanyResponse {
	access_token: string;
	token_type: string;
	tipo: 'sesion';
	user_id: number;
	company_id: number;
	rol: Role;
}

/** Usuario resuelto contra /users/me, disponible en locals y en $page.data. */
export interface SessionUser {
	id_user: number;
	email: string;
	role: Role;
	name: string;
	id_person: number | null;
	/** En qué compañía está trabajando esta sesión, y desde qué caja (T-211). */
	company_id: number;
	company_name: string | null;
	branch_code: string | null;
	terminal_code: string | null;
	/** Cuántas compañías tiene disponibles; con una sola no se ofrece cambiar. */
	companies_available: number;
	/**
	 * Los módulos que incluye el plan (RF-40, RN-49).
	 *
	 * Se releen en cada petición junto con el resto de la sesión, así que una
	 * compañía que sube de plan lo ve en su siguiente clic. **Sirven para armar
	 * la navegación, no para autorizar**: quien manda es `require_module` en el
	 * servidor, que es el que ve un `curl`.
	 */
	modules: Modules;
	/**
	 * Los dos idiomas, que no son el mismo (RN-28, RN-29).
	 *
	 * `locale` es el de la pantalla —el efectivo, ya resuelto— y está acá para que
	 * el selector pueda marcar cuál está activo; quien traduce no lo lee de aquí,
	 * lo toma del contexto de la petición. `user_locale` es lo que eligió la
	 * persona, en nulo si hereda: la diferencia importa porque «como esté la
	 * compañía» no es lo mismo que «español». `document_locale` es el de la
	 * factura, que se emite en el idioma de la compañía.
	 */
	locale: string;
	user_locale: string | null;
	company_locale: string;
	document_locale: string;
	/**
	 * El estado de la suscripción (T-308). Nulo solo si el backend es viejo y no
	 * lo manda; el POS trata eso como «se puede todo», que es lo que hacía antes.
	 */
	subscription?: Subscription | null;
	/**
	 * Correo de quien está suplantando, si esta sesión es un *entrar como*
	 * (RF-8). Es lo que enciende la franja permanente, y por eso viaja en cada
	 * `/users/me` y no una sola vez al entrar: una franja que se puede perder al
	 * navegar no es permanente.
	 */
	impersonated_by?: string | null;
	impersonation_reason?: string | null;
}

// ------------------------------------------------------------------- soporte

/**
 * Quién es el de soporte. **Sin compañía**, porque no tiene (RN-4).
 *
 * Es un tipo aparte de `SessionUser` y no un `SessionUser` con la compañía en
 * nulo: la mitad del POS lee `user.company_id` sin preguntar, y hacerlo
 * anulable convertiría cada una de esas lecturas en un caso que nadie probó.
 * Soporte no entra al POS, entra al panel.
 */
export interface SupportUser {
	id_user: number;
	email: string;
	name: string;
	locale: string;
}

/** Un plan: lo que el sistema deja hacer, no una lista de precios. */
/**
 * Los módulos que un plan incluye o no (RN-49, F10 a F12).
 *
 * Las tres claves están siempre, también en `false`: una clave ausente y una en
 * `false` no se leen igual, y la navegación tiene que poder distinguir «no lo
 * tiene» de «no vino el dato».
 */
export interface Modules {
	purchases: boolean;
	accounting: boolean;
	payroll: boolean;
}

/** Los nombres de los módulos, para recorrerlos sin escribirlos tres veces. */
export const MODULES = ['purchases', 'accounting', 'payroll'] as const;

export type ModuleName = (typeof MODULES)[number];

export interface Plan extends Modules {
	id: number;
	nombre: string;
	precio_mensual: number;
	max_sucursales: number;
	max_terminales: number;
	max_usuarios: number;
	factura_electronica: boolean;
}

/** Cuánto de su plan usa una compañía (RF-5). */
export interface CompanyUsage {
	usuarios: number;
	terminales: number;
	productos: number;
	ventas_del_mes: number;
	total_del_mes: number;
	/** Cuántos más caben. Nulo es «el plan no limita». */
	cupo_usuarios: number | null;
	cupo_terminales: number | null;
}

/** Una compañía como la ve el panel de soporte. */
export interface SupportCompany {
	id: number;
	afiliado: number;
	compania: number;
	nombre: string;
	identificacion: string | null;
	creada_el: string | null;
	locale: string;
	document_locale: string;
	plan: Plan | null;
	suscripcion: Subscription;
	uso: CompanyUsage;
	administradores: string[];
}

/** Una línea de la bitácora, con los nombres ya resueltos (RF-9). */
export interface AuditLine {
	id: number;
	creado_el: string;
	user_id: number;
	email: string | null;
	nombre: string | null;
	company_id: number | null;
	company_nombre: string | null;
	accion: string;
	detalle: string | null;
	ip: string | null;
}

/** Lo que devuelve el alta de una compañía (RF-6). */
export interface NewCompanyResult {
	company_id: number;
	afiliado: number;
	compania: number;
	nombre: string;
	plan_id: number;
	plan_nombre: string;
	estado: CompanyState;
	branch_codigo: string;
	terminal_codigo: string;
	user_id: number;
	email: string;
	usuario_nuevo: boolean;
	membresia_pendiente: boolean;
}

/**
 * Autenticado pero todavía sin compañía.
 *
 * Es el estado que crea el login de dos pasos y que no existía antes: la
 * persona ya probó quién es, pero hasta que no diga dónde entra no tiene
 * permiso para nada (RN-26). Vale solo para `/compania`.
 */
export interface PendingSession {
	user_id: number;
	email: string;
}

// -------------------------------------------------------------------- personas

export interface Person {
	id_person: number;
	birth_date: string;
	identification: string;
	name: string;
	lastName: string;
	secondName: string;
	telephone: string;
	id_user: number;
	email: string;
	role?: Role;
}

export interface PersonInput {
	birth_date: string;
	identification: string;
	name: string;
	lastName: string;
	secondName: string;
	telephone: string;
	email: string;
	password?: string;
}

// -------------------------------------------------------------------- clientes

export interface Client {
	id_client: number;
	identification: string;
	name: string;
	last_name: string;
	second_name: string;
	email: string;
	telephone: number;
	address: string;
	register_date: string;
}

export type ClientInput = Omit<Client, 'id_client'>;

// ------------------------------------------------------------------- productos

export interface Product {
	id_product: number;
	name: string;
	description: string;
	price: number;
	stock: number;
	barcode: string;
	created_at: string;
	category_id: number;

	// --- F5: el impuesto es del producto, no del negocio (RN-9) -------------

	/** Código del catálogo de Hacienda. Trece dígitos, con ceros a la izquierda. */
	cabys_code?: string | null;
	/**
	 * La tarifa de ESTE producto, entre 0 y 1: el 13 % es `0.13`.
	 *
	 * `null` o ausente significa **la tasa configurada del negocio**, que es lo
	 * que tienen los productos anteriores a F5 y los que nadie ha clasificado.
	 * No es lo mismo que `0`, que es una exoneración de verdad.
	 */
	tax_rate?: number | null;
	/** Unidad de medida del comprobante de Hacienda. 'Unid' por omisión. */
	unit_of_measure?: string;

	// --- F10: lo que cuesta, no lo que vale (RN-54) --------------------------

	/**
	 * Promedio ponderado móvil de las compras. **Solo de lectura**: lo escribe
	 * el backend al recibir mercadería y no hay forma de fijarlo a mano.
	 *
	 * Cero es «no se sabe todavía» —lo que tienen los productos anteriores a
	 * F10— y no «sale gratis». Quien lo muestre tiene que distinguirlos.
	 */
	cost?: number;
}

/** Lo que se manda al crear o editar. El costo no entra: lo pone la compra. */
export type ProductInput = Omit<Product, 'id_product' | 'cost'>;

export interface Category {
	id: number;
	name: string;
	/** Nulo es una raíz. El árbol tiene dos niveles y no más (RN-5). */
	parent_id: number | null;
	/** El orden que eligió el dueño para la grilla de ventas (RF-13). */
	sort_order: number;
	/**
	 * Una categoría con productos o con hijas no se borra, se desactiva (RN-7).
	 * La lista trae las dos: el inventario tiene que poder nombrar la categoría
	 * de un producto viejo y volver a activarla.
	 */
	is_active: boolean;
}

export type CategoryInput = Pick<Category, 'name'> & { parent_id?: number | null };

// ---------------------------------------------------------------------- ventas

export interface Sale {
	id: number;
	sale_number: string;
	created_at: string;
	payment_method: string;
	total: number;
}

/** Línea del carrito en el navegador. Nunca se envía tal cual al backend. */
export interface CartLine {
	id_product: number;
	barcode: string;
	name: string;
	price: number;
	quantity: number;
	stock: number;
	/**
	 * La tarifa de ESTE producto, copiada al agregarlo (F5, RN-9).
	 *
	 * `null` o ausente significa «la tasa configurada del negocio», que es lo que
	 * aplica mientras nadie lo clasifique. Ausente además en los carritos que
	 * quedaron guardados antes de F5: se recuperan y caen a la configurada, que
	 * es exactamente lo que se les estaba cobrando.
	 */
	taxRate?: number | null;
}

export interface SaleItem {
	id_product: number;
	name: string;
	quantity: number;
	price: number;
	subtotal: number;
	/**
	 * La tarifa **congelada** al cobrar, no la que tenga el producto hoy
	 * (RN-12). Ausente en las ventas anteriores a la migración 006, que llevan
	 * una sola tarifa y la reconstruyen del encabezado.
	 */
	tax_rate?: number | null;
	/** Lo que se cobró de impuesto en esta línea, con su redondeo. */
	tax_amount?: number | null;
}

/** Respuesta de GET /sales/sale/{id} — endpoint añadido por este proyecto. */
export interface SaleDetail extends Sale {
	subtotal: number;
	tax: number;
	cash_received: number;
	change_given: number;
	client_id: number | null;
	user_id: number | null;
	client_name?: string | null;
	user_name?: string | null;
	items: SaleItem[];
	returned?: boolean;
}

export interface SalePayload {
	sale_number: string;
	client_id: number | null;
	user_id: number;
	subtotal: number;
	tax: number;
	total: number;
	payment_method: string;
	cash_received: number;
	change_given: number;
	created_at: string;
	products: { id_product: number; stock: number; price: number; name: string }[];
}

export const PAYMENT_METHODS = [
	'Efectivo',
	'Tarjeta de crédito',
	'Transferencia bancaria',
	'Pago móvil'
] as const;

export type PaymentMethod = (typeof PAYMENT_METHODS)[number];

// ------------------------------------------------------------------------ caja

export type CashSessionStatus = 'abierta' | 'cerrada';

export interface CashSession {
	id: number;
	user_id: number;
	user_name?: string | null;
	opened_at: string;
	closed_at: string | null;
	opening_amount: number;
	/** Efectivo contado por el cajero al cerrar. Null mientras la caja siga abierta. */
	closing_amount: number | null;
	/** Apertura + ventas en efectivo + entradas − salidas. */
	expected_amount: number;
	/** closing_amount − expected_amount. Negativo = faltante. */
	difference: number | null;
	status: CashSessionStatus;
	notes: string | null;
}

export type CashMovementType = 'entrada' | 'salida';

export interface CashMovement {
	id: number;
	session_id: number;
	type: CashMovementType;
	amount: number;
	reason: string;
	created_at: string;
}

/** Corte Z: lo que se imprime al cerrar el turno. */
export interface CashSessionReport extends CashSession {
	movements: CashMovement[];
	sales_count: number;
	sales_total: number;
	/** Total vendido desglosado por método de pago. */
	by_payment_method: { payment_method: string; count: number; total: number }[];
	cash_sales: number;
	movements_in: number;
	movements_out: number;
	returns_total: number;
}

// ---------------------------------------------------------------- devoluciones

export interface ReturnItem {
	id_product: number;
	name: string;
	quantity: number;
	price: number;
	subtotal: number;
}

export interface SaleReturn {
	id: number;
	sale_id: number;
	sale_number: string;
	user_id: number;
	user_name?: string | null;
	created_at: string;
	reason: string;
	/**
	 * El desglose de lo reembolsado (F5, T-509b).
	 *
	 * Con una sola tarifa el impuesto se deducía del total; con tarifas mezcladas
	 * no hay de dónde, así que se guarda al devolver. Ausente en las devoluciones
	 * anteriores a la migración 006.
	 */
	subtotal?: number | null;
	tax?: number | null;
	total: number;
	/** Devolución completa de la venta (todas las líneas, cantidad total). */
	is_full: boolean;
	items: ReturnItem[];
}

export interface ReturnPayload {
	sale_id: number;
	user_id: number;
	reason: string;
	items: { id_product: number; quantity: number }[];
}

// ------------------------------------------------- entradas de inventario

export type StockEntrySource = 'manual' | 'excel' | 'xml';
export type StockEntryStatus = 'aplicada' | 'anulada';

export interface StockEntryLine {
	id_product: number;
	name: string;
	quantity: number;
	/** Lo que costó la unidad al comprarla. No es el precio de venta. */
	unit_cost: number;
	subtotal: number;
	/**
	 * El impuesto **del documento del proveedor** (RN-53), la tarifa en
	 * porcentaje: 13 y no 0,13, que es como la dice la factura. Cero cuando la
	 * entrada no viene de una: sin factura no hay crédito fiscal.
	 */
	tax_rate?: number;
	tax_amount?: number;
}

export interface StockEntry {
	id: number;
	/** Número de factura del proveedor, o consecutivo del XML. */
	document_number: string | null;
	supplier: string | null;
	source: StockEntrySource;
	user_id: number;
	user_name?: string | null;
	created_at: string;
	notes: string | null;
	status: StockEntryStatus;
	total_cost: number;
	items_count: number;
	lines: StockEntryLine[];

	// --- F10: lo que convierte una entrada en compra (RN-52) -----------------

	/**
	 * **Lo que decide si esto es una compra.** Con proveedor hay cuenta por
	 * pagar y crédito fiscal, y anularla exige motivo; sin él es una entrada de
	 * las de siempre y nada de lo de abajo significa nada.
	 */
	supplier_id?: number | null;
	/** La clave de 50 dígitos del comprobante, cuando vino de un XML. */
	document_key?: string | null;
	/** La del documento, que no es la de carga: el IVA es del día de la factura. */
	document_date?: string | null;
	payment_terms?: 'cash' | 'credit';
	due_date?: string | null;
	/** Sin impuesto, y el impuesto. `total_cost` es la suma de los dos. */
	subtotal?: number;
	tax?: number;
}

/**
 * A quién se le compra (F10, RF-41).
 *
 * La identificación es lo que lo identifica de verdad: la misma identificación
 * es el mismo proveedor, y es con lo que se lo reconoce al leer el XML de una
 * factura sin preguntarle nada a nadie.
 */
export interface Supplier {
	id: number;
	/** 01/02/03/04, la lista de Hacienda. Nulo en un proveedor informal. */
	identification_type?: string | null;
	identification?: string | null;
	name: string;
	email?: string | null;
	phone?: string | null;
	/** Plazo habitual en días. 0 es contado, y es lo que propone una compra. */
	payment_terms_days: number;
	/** No se borra: se desactiva. Uno inactivo no recibe compras nuevas. */
	is_active: boolean;
}

/** Producto del catálogo con el que se emparejó una línea del archivo. */
export interface MatchedProduct {
	id_product: number;
	name: string;
	barcode: string;
	stock: number;
	price: number;

	// --- F10: para poder comparar contra lo que dice el documento ------------

	/**
	 * La tarifa **del producto**, entre 0 y 1. `null` es «la configurada».
	 *
	 * No se usa para calcular nada: la compra guarda la del documento, que es
	 * lo que se pagó (RN-53). Está para **avisar** cuando las dos no coinciden
	 * (RF-43), que suele significar o que el proveedor clasificó distinto o que
	 * el CABYS del producto está mal.
	 */
	tax_rate?: number | null;
	/** El costo promedio de hoy, para verlo al lado del de la factura. */
	cost?: number;
}

/**
 * Lo que un lector de archivos tiene que decir, en código y datos.
 *
 * Los lectores (`$lib/server/import/*`) son adaptadores, no la interfaz: no
 * saben en qué idioma está la pantalla. Devuelven qué pasó y la frase la arma
 * `importMessage()` en `$lib/ui/messages` (RN-30, el mismo trato que el
 * backend).
 */
export type ImportNote =
	| { code: 'import_lines_need_review'; count: number }
	| { code: 'import_no_cost_column' }
	| { code: 'import_bad_quantity' }
	| { code: 'import_bad_quantity_in_row'; row: number }
	| { code: 'import_fractional_quantity'; quantity: number }
	| { code: 'import_fractional_quantity_in_row'; quantity: number; row: number };

/** Lo que impide leer el archivo del todo. */
export type ImportFailure =
	| { code: 'import_csv_unreadable' }
	| { code: 'import_xlsx_unreadable' }
	| { code: 'import_sheet_empty' }
	| { code: 'import_no_quantity_column' }
	| { code: 'import_no_identifier_column' }
	| { code: 'import_no_data_rows' }
	| { code: 'import_not_an_invoice' }
	| { code: 'import_xml_unreadable' }
	| { code: 'import_invoice_without_lines' };

/**
 * Línea leída de un archivo, antes de confirmar. Todavía no tocó el inventario:
 * el cajero revisa la vista previa y decide qué entra.
 */
export interface ParsedLine {
	/** Código tal como venía en el archivo. */
	code: string;
	description: string;
	quantity: number;
	unit_cost: number;
	matched: MatchedProduct | null;
	/** Cómo se emparejó, para que se entienda por qué. */
	matched_by: 'barcode' | 'name' | null;
	/** Problema de la línea que impide usarla (cantidad inválida, etc.). */
	issue?: ImportNote;
	/**
	 * El impuesto de la línea **tal como lo dice el documento** (RN-53, F10).
	 *
	 * No se recalcula desde la tarifa del producto: el crédito fiscal es lo que
	 * se pagó, no lo que se habría cobrado. En 0 cuando la línea va exenta o
	 * cuando el archivo no trae impuesto —una hoja de Excel, por ejemplo—.
	 */
	tax_rate: number;
	tax_amount: number;
}

/**
 * Quién emitió el documento (F10, RF-42).
 *
 * Con la identificación alcanza para reconocer al proveedor sin preguntarle
 * nada a nadie: la misma identificación es el mismo proveedor. Lo demás sirve
 * para darlo de alta si no existe todavía.
 */
export interface ParsedSupplier {
	name: string;
	identification_type: string | null;
	identification: string | null;
	email: string | null;
	phone: string | null;
}

export interface ParseResult {
	source: StockEntrySource;
	supplier: string | null;
	document_number: string | null;
	issued_at: string | null;
	lines: ParsedLine[];
	/** Avisos no fatales: filas salteadas, columnas que no se encontraron… */
	warnings: ImportNote[];

	/**
	 * Lo que solo trae un comprobante electrónico (F10). Nulo en las otras dos
	 * vías —manual y Excel—, donde el proveedor se elige a mano.
	 */
	supplier_details?: ParsedSupplier | null;
	/** La clave de 50 dígitos. `document_number` sigue siendo el consecutivo. */
	document_key?: string | null;
	/** 'cash' | 'credit', leído de `CondicionVenta`. */
	payment_terms?: 'cash' | 'credit';
	/** Días de `PlazoCredito`. 0 cuando es de contado o no lo dice. */
	credit_days?: number;
}

// -------------------------------------------------------------------- reportes

export interface ReportSummary {
	range: { from: string; to: string };
	sales_count: number;
	gross_total: number;
	returns_total: number;
	net_total: number;
	tax_total: number;
	average_ticket: number;
	items_sold: number;
	/** Comparación contra el periodo inmediatamente anterior de igual duración. */
	previous_net_total: number;
}

export interface TopProduct {
	id_product: number;
	name: string;
	quantity: number;
	total: number;
}

export interface SalesByDay {
	day: string;
	sales_count: number;
	total: number;
}

export interface PaymentBreakdown {
	payment_method: string;
	count: number;
	total: number;
}

export interface LowStockProduct {
	id_product: number;
	name: string;
	barcode: string;
	stock: number;
	category_id: number;
}

export interface DashboardData {
	summary: ReportSummary;
	top_products: TopProduct[];
	sales_by_day: SalesByDay[];
	by_payment_method: PaymentBreakdown[];
	low_stock: LowStockProduct[];
}

// ----------------------------------------------------------------------- común

/** Forma de error uniforme que devuelven las acciones y los endpoints /api. */
export interface ApiFailure {
	message: string;
	fields?: Record<string, string>;
}
