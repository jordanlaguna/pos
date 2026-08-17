/**
 * Modelo de dominio de VentaSys.
 *
 * Los nombres de campo replican exactamente los del backend FastAPI (snake_case,
 * más algunos camelCase heredados en Person) para que el JSON viaje sin traducción.
 * Provienen de postsys/model/*.cs del proyecto WinForms original.
 */

// ---------------------------------------------------------------- autenticación

export type Role = 'admin' | 'cajero';

/** Estado de la suscripción de una compañía (spec §2). */
export type CompanyState = 'prueba' | 'activa' | 'vencida' | 'suspendida' | 'cancelada';

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
 * compañía disponible, RN-25— y con `transito` hay que elegir (RF-27). El token
 * de tránsito no abre ninguna puerta de negocio.
 */
export interface LoginResponse {
	access_token: string;
	token_type: string;
	tipo: 'sesion' | 'transito';
	user_id: number;
	company_id?: number | null;
	companies?: CompanyOption[];
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
}

export type ProductInput = Omit<Product, 'id_product'>;

export interface Category {
	id: number;
	name: string;
}

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
}

export interface SaleItem {
	id_product: number;
	name: string;
	quantity: number;
	price: number;
	subtotal: number;
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
}

/** Producto del catálogo con el que se emparejó una línea del archivo. */
export interface MatchedProduct {
	id_product: number;
	name: string;
	barcode: string;
	stock: number;
	price: number;
}

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
	issue?: string;
}

export interface ParseResult {
	source: StockEntrySource;
	supplier: string | null;
	document_number: string | null;
	issued_at: string | null;
	lines: ParsedLine[];
	/** Avisos no fatales: filas salteadas, columnas que no se encontraron… */
	warnings: string[];
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
