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
 * Los módulos, en el orden del menú (RN-49, QA-01). Desde QA-01 cada sección
 * del POS es uno, y los planes son paquetes de ellos; Configuración no, porque
 * sin ella no hay negocio. Es la misma lista que `MODULES` en
 * `backend/app/domain/modules.py`.
 */
export const MODULES = [
	'sales',
	'cash',
	'invoices',
	'returns',
	'reports',
	'inventory',
	'purchases',
	'suppliers',
	'accounting',
	'payroll',
	'clients',
	'users'
] as const;

export type ModuleName = (typeof MODULES)[number];

/**
 * Los módulos que un plan incluye o no. Las claves están siempre, también en
 * `false`: una clave ausente y una en `false` no se leen igual, y la navegación
 * tiene que poder distinguir «no lo tiene» de «no vino el dato».
 */
export type Modules = Record<ModuleName, boolean>;

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
	/** El tipo de Hacienda de la cédula del emisor (RN-45). */
	identification_type?: string | null;
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
	/**
	 * El tipo de Hacienda (T-617): `'01'` física, `'02'` jurídica, `'03'` DIMEX,
	 * `'04'` NITE. Lo imprime el receptor del comprobante. Nulo en un cliente que
	 * ni la migración 011 pudo clasificar por la longitud de su cédula.
	 */
	identification_type?: string | null;
	name: string;
	last_name: string;
	second_name: string;
	email: string;
	telephone: number;
	address: string;
	/**
	 * Las otras señas de un cliente del extranjero (RF-78, T-727): van en el
	 * receptor de la factura de exportación en lugar de la ubicación del país.
	 */
	foreign_address?: string | null;
	register_date: string;

	// --- F7: la exoneración del cliente (RF-67, RN-78) -----------------------
	//
	// **Son puntos de tarifa, no una tarifa**: `exo_points` en 9 quiere decir
	// nueve puntos perdonados, así que una línea al 13 % pasa a pagar 4 %. No
	// existe ninguna tarifa del 9 %.
	//
	// Los ocho se ponen y se quitan juntos: si viaja cualquiera, viajan todos, y
	// los ocho vacíos es cómo se le quita la exoneración a un cliente.

	/** Nota 10.1 del anexo: qué clase de autorización es. */
	exo_document_type?: string | null;
	exo_document_number?: string | null;
	/** Nota 23: quién la emitió. El `'99'` obliga a escribir cuál. */
	exo_institution?: string | null;
	exo_institution_other?: string | null;
	/** Obligatorios cuando el tipo de documento remite a una ley. */
	exo_article?: number | null;
	exo_subsection?: number | null;
	/** La fecha de emisión del documento, `YYYY-MM-DD`. */
	exo_date?: string | null;
	/** Los **puntos** perdonados: 9, no 0.09 ni 4. */
	exo_points?: number | null;
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
	/**
	 * La partida arancelaria (RF-78, T-727): doce dígitos, lo que una mercancía
	 * necesita para salir en una factura de exportación. Nula es «no tiene».
	 */
	tariff_heading?: string | null;

	// --- F7: el código de tarifa de Hacienda (RN-76) -------------------------

	/**
	 * El código de la nota 8.1 del anexo: `'08'` es la tarifa general del 13 %.
	 *
	 * **No es el porcentaje.** Hay once códigos para nueve porcentajes: el 0 %
	 * con derecho a crédito pleno (`'01'`) y el 0 % sin derecho (`'11'`) son el
	 * mismo número y dan derechos opuestos. Cuando se manda, **la tarifa sale
	 * de él**: el servidor reescribe `tax_rate`.
	 *
	 * `null` o ausente es «sin clasificar para factura electrónica».
	 */
	tax_code?: string | null;

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
	/**
	 * El comprobante que se emitió (RN-85): `'01'` factura, `'04'` tiquete.
	 *
	 * `null` o ausente es «sin facturación electrónica», que es lo que tienen
	 * todas las ventas anteriores a la migración 014. Se decide al cobrar y no
	 * cambia: el documento reimpreso dice lo que se emitió, no lo que la compañía
	 * tenga configurado hoy.
	 */
	document_type?: string | null;
	/** En qué va ante Hacienda (RN-39); nulo sin comprobante o en un backend anterior a F7. */
	einvoice_status?: DocumentState | null;
}

/**
 * Lo que Hacienda le asignó al comprobante (RN-86).
 *
 * **Todavía no viaja.** Es el contrato que T-705 tiene que llenar: ni el backend
 * ni el simulado lo mandan hoy, y el documento lo sabe —dice «pendiente de
 * emisión», que es la verdad—. Está escrito acá para que las tres plantillas ya
 * sepan imprimirlo el día que llegue, y para que quien lo implemente no tenga
 * que adivinar qué forma espera la pantalla.
 */
export interface EmittedDocument {
	/** Los 50 dígitos. Va impresa y se entrega en el mostrador (RN-43). */
	clave: string;
	/** Los 20: sucursal, terminal, tipo y secuencia. */
	consecutive: string;
	/** Lo emitido en pruebas no tiene efecto fiscal, y lo dice (RN-17). */
	environment: 'sandbox' | 'production';
	/** El código con el que se declaró, que puede no ser el configurado hoy. */
	economic_activity?: string | null;
	/** 1 normal, 2 contingencia, 3 sin internet: la posición 42 de la clave. */
	situation?: string;

	// ------------------------------------------- el recorrido (F7, T-707)
	/** El id del comprobante en `fe_documents`; con él se pide el expediente. */
	id?: number | null;
	document_type?: string | null;
	/** De dónde nació, para ir a su pantalla desde la lista de detenidos. */
	source_type?: 'sale' | 'return' | 'note' | 'purchase' | null;
	source_id?: number | null;
	/** Ver `DocumentState`. Nulo en un backend anterior a F7. */
	status?: DocumentState | null;
	/** Por qué se detuvo (`StopReason`), y lo que dijo Hacienda o la falla. */
	stop_reason?: StopReason | null;
	stop_detail?: string | null;
	hacienda_status?: string | null;
	failures?: number;
	polls?: number;
	issued_at?: string | null;
	signed_at?: string | null;
	sent_at?: string | null;
	resolved_at?: string | null;
	last_attempt_at?: string | null;
	next_attempt_at?: string | null;
	has_xml?: boolean;
	has_response?: boolean;
}

/** Los siete estados del recorrido (RN-39). */
export type DocumentState =
	| 'numbered'
	| 'signed'
	| 'sent'
	| 'accepted'
	| 'rejected'
	| 'retrying'
	| 'stopped';

/** Por qué un comprobante se detuvo (`domain/fe_transmission.STOP_*`). */
export type StopReason =
	| 'certificate_missing'
	| 'certificate_expired'
	| 'credentials_missing'
	| 'credentials_rejected'
	| 'document_invalid'
	| 'reception_rejected'
	| 'forbidden'
	| 'hacienda_error'
	| 'retries_exhausted'
	| 'no_verdict';

/** Un paso del recorrido, con su hora (T-721). */
export interface DocumentEvent {
	at: string;
	event:
		| 'signed'
		| 'sent'
		| 'polled'
		| 'accepted'
		| 'rejected'
		| 'deferred'
		| 'stopped'
		| 'resumed'
		| 'xml_lost';
	detail?: string | null;
}

/** El expediente de un comprobante: `GET /fe/documents/{id}`. */
export interface DocumentFile {
	document: EmittedDocument;
	source_type: 'sale' | 'return' | 'note' | 'purchase';
	source_id: number;
	events: DocumentEvent[];
}

/** La cola de la compañía: `GET /fe/queue` (RF-33, RF-35, T-711). */
export interface FeQueue {
	counts: Record<string, number>;
	pending: number;
	stopped: EmittedDocument[];
	oldest_pending_at: string | null;
	alarm: 'ok' | 'warning' | 'danger';
	contingency: boolean;
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
	/**
	 * Lo que costó **al momento de venderse** (RN-63), congelado como la tarifa
	 * y por lo mismo: comprar más caro mañana no puede cambiar el costo de lo que
	 * ya salió. `null` es «no se sabe» —un producto que nunca se compró—, y esa
	 * línea no asienta el par costo / inventario.
	 */
	unit_cost?: number | null;
	/** El código de tarifa de Hacienda con que se cobró (RN-76). */
	tax_code?: string | null;
	/**
	 * El CABYS y la unidad con que se vendió, congelados en la línea (T-731,
	 * RN-86): el comprobante los imprime y el producto puede cambiarlos después.
	 * Ausentes en lo anterior a la migración 016.
	 */
	cabys_code?: string | null;
	unit_of_measure?: string | null;
	/** La partida arancelaria con que se exportó (T-727). Solo en la FEE. */
	tariff_heading?: string | null;
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
	/** La clave y el consecutivo, cuando los haya. Ver `EmittedDocument`. */
	einvoice?: EmittedDocument | null;
	/**
	 * El comprobante que este documento modifica, cuando es una nota (RN-89).
	 * Una venta no lo lleva nunca; lo arma la pantalla de la nota.
	 */
	reference?: DocumentReference | null;
}

export interface SalePayload {
	sale_number: string;
	client_id: number | null;
	/** `'01'` o `'04'` (RN-85). Sin él, el servidor aplica la sugerencia. */
	document_type?: string | null;
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
	/**
	 * Las notas por monto del turno (T-726): lo cobrado con ND —todo, y lo que
	 * fue en efectivo, que es lo que entra a la gaveta— y lo reembolsado con NC.
	 * Ausentes en un backend anterior: valen cero.
	 */
	debit_notes_total?: number;
	debit_notes_cash?: number;
	credit_notes_total?: number;
}

// ---------------------------------------------------------------- devoluciones

export interface ReturnItem {
	id_product: number;
	name: string;
	quantity: number;
	price: number;
	subtotal: number;
	/** La tarifa con que se cobró y lo reembolsado de impuesto: los desglosa la nota. */
	tax_rate?: number | null;
	tax_amount?: number | null;
	/** Los de la línea de la venta: la nota repite con qué se vendió (RN-86). */
	cabys_code?: string | null;
	unit_of_measure?: string | null;
}

/** Una línea de una nota por monto (T-726): a qué producto y por cuánto. */
export interface AmountNoteItem {
	id_product: number;
	name: string;
	subtotal: number;
	/** La tarifa de la línea de la venta, no la de hoy (RN-12). */
	tax_rate: number;
	tax_amount: number;
	tax_code?: string | null;
	/** Los de la línea de la venta: la nota repite con qué se vendió (RN-86). */
	cabys_code?: string | null;
	unit_of_measure?: string | null;
}

/**
 * Una nota por monto sobre un comprobante (RF-77, T-726): la ND o la NC que no
 * mueve mercadería. La plata se mueve en el momento: la ND se cobra con su
 * `payment_method` y la NC sale de la gaveta, sin medio.
 */
export interface AmountNote {
	id: number;
	sale_id: number;
	sale_number: string;
	user_id: number;
	user_name?: string | null;
	created_at: string;
	/** `'02'` nota de débito, `'03'` nota de crédito. */
	document_type: string;
	/** El motivo de Hacienda. Hoy solo `'02'`, corrige monto. */
	reference_code: string;
	reason: string;
	payment_method: string | null;
	subtotal: number;
	tax: number;
	total: number;
	items: AmountNoteItem[];
	/** Lo que la nota impresa dice del original (RN-89). */
	sale_document_type?: string | null;
	sale_created_at?: string | null;
	sale_client_id?: number | null;
	/** La nota numerada (T-705). */
	einvoice?: EmittedDocument | null;
	/** La clave del comprobante que modifica: es como se lo referencia. */
	sale_clave?: string | null;
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
	/**
	 * La nota de crédito (RN-89): `'03'` y el motivo de Hacienda —`'06'`
	 * devolución de mercancía, `'01'` anula—. Nulos cuando la venta no fue
	 * comprobante: no hay qué referenciar.
	 */
	document_type?: string | null;
	reference_code?: string | null;
	/** Lo que la nota impresa dice del original. */
	sale_document_type?: string | null;
	sale_created_at?: string | null;
	sale_client_id?: number | null;
	sale_payment_method?: string | null;
	/** La nota de crédito numerada, y la clave del original (T-705). */
	einvoice?: EmittedDocument | null;
	sale_clave?: string | null;
}

/** El comprobante que una nota modifica (RN-89), tal como se imprime. */
export interface DocumentReference {
	/** El tipo del original: `'01'` o `'04'`. */
	document_type: string;
	/**
	 * Cómo se lo nombra: su **clave** desde T-705, que es como lo referencia el
	 * XML; su número de venta si es anterior y nunca se numeró.
	 */
	number: string;
	/** Su fecha de emisión. */
	date: string;
	/** El motivo del catálogo de Hacienda: `'01'` anula, `'06'` devolución. */
	code: string;
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
	/**
	 * La factura electrónica de compra (T-728): `'08'` y su recorrido ante
	 * Hacienda cuando la compra fue a un no contribuyente y la compañía la
	 * emite. Nulos en toda compra a un proveedor inscrito.
	 */
	document_type?: string | null;
	einvoice?: EmittedDocument | null;
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

/**
 * Lo que se le debe a los proveedores hoy (F10, RF-44).
 *
 * **El saldo no se guarda en ninguna parte**: el de una compra es su total
 * menos sus abonos y el de un proveedor es la suma de los de sus compras
 * (RN-55). Todo esto lo calcula el servidor al preguntarlo.
 */
export interface PayablePurchase {
	entry_id: number;
	document_number: string | null;
	document_date: string | null;
	due_date: string | null;
	total: number;
	paid: number;
	balance: number;
	/**
	 * El piso del tramo de antigüedad **en días**: 0, 30, 60 o 90.
	 *
	 * Un número y no una etiqueta, porque la frase la arma el POS (RN-30).
	 */
	bucket: number;
	/** Negativo mientras no venza. `null` si no vence. */
	days_overdue: number | null;
}

export interface PayableSupplier {
	supplier_id: number;
	name: string;
	balance: number;
	purchases: PayablePurchase[];
}

export interface Payables {
	/** Contra qué día se calculó la antigüedad. La pone el servidor. */
	as_of: string;
	total: number;
	/** Los cuatro tramos, siempre los cuatro aunque vayan en cero. */
	by_bucket: { bucket: number; balance: number }[];
	suppliers: PayableSupplier[];
}

/**
 * El crédito fiscal de un periodo, por tarifa (F10, RF-45).
 *
 * Es la mitad de compras del D-104. Agrupa por la tarifa **del documento del
 * proveedor** y no por la del producto: lo que se acredita es lo que se pagó
 * (RN-53), y el periodo es el de la **fecha de la factura**, no el de su carga.
 */
export interface PurchaseRateLine {
	/** En porcentaje, como lo dice el documento: 13 y no 0,13. */
	tax_rate: number;
	base: number;
	tax: number;
}

export interface PurchasesReport {
	date_from: string;
	date_to: string;
	subtotal: number;
	tax: number;
	total: number;
	by_rate: PurchaseRateLine[];
}

// --------------------------------------------------------------- contabilidad
//
// F11. El libro de la compañía: catálogo de cuentas, mapeo de eventos a cuentas,
// asientos con sus líneas, periodos mensuales y los cinco reportes.

/** Los seis tipos de cuenta. De esto salen los tres estados financieros. */
export const ACCOUNT_KINDS = [
	'asset',
	'liability',
	'equity',
	'income',
	'cost',
	'expense'
] as const;

export type AccountKind = (typeof ACCOUNT_KINDS)[number];

/** Cómo nació un asiento. */
export const ENTRY_KINDS = ['auto', 'manual', 'adjustment', 'opening'] as const;

export type EntryKind = (typeof ENTRY_KINDS)[number];

export interface Account {
	id: number;
	/** '1.1.01'. La jerarquía va por el texto, y es lo que ordena el catálogo. */
	code: string;
	name: string;
	kind: AccountKind;
	parent_id: number | null;
	/** La usa el mapeo: no se borra ni se desactiva (RN-64). */
	is_system: boolean;
	is_active: boolean;
}

/** Una cuenta de la plantilla, antes de que exista: no tiene id todavía. */
export interface ChartAccount {
	code: string;
	name: string;
	kind: AccountKind;
	is_system: boolean;
}

export interface AccountingStatus {
	active: boolean;
	template: string | null;
	/** Desde cuándo se llevan libros (RN-60). Lo anterior no se reconstruye. */
	start_date: string | null;
	templates: string[];
	/** La plantilla entera. Viene aunque no esté activa: es lo que la pantalla
	 * de activación necesita para ofrecer los saldos iniciales. */
	chart: ChartAccount[];
}

export interface MappingRow {
	event: string;
	role: string;
	account_id: number | null;
	account_code: string | null;
	account_name: string | null;
	/** Los que caen en «por clasificar» a propósito: no se pintan en rojo,
	 * porque no están mal, es que el sistema no sabe. */
	unmapped_on_purpose: boolean;
}

export interface JournalLine {
	account_id: number;
	account_code: string;
	account_name: string;
	debit: number;
	credit: number;
	/** En porcentaje —13, no 0,13—, solo en las líneas de IVA (RN-65). */
	tax_rate: number | null;
	memo: string | null;
}

export interface JournalEntry {
	id: number;
	/** Correlativo por compañía, sin huecos. */
	entry_number: number;
	entry_date: string;
	kind: EntryKind;
	/** De qué tabla salió. Nulo en los manuales y en la apertura. */
	source_type: string | null;
	source_id: number | null;
	/** A cuál corrige, si es de ajuste (RN-61). */
	adjusts_entry_id: number | null;
	/** Código del evento en los automáticos; frase de quien lo dictó en los
	 * manuales. El POS decide cuál muestra. */
	description: string;
	user_id: number;
	created_at: string;
	lines?: JournalLine[];
	total?: number;
}

export interface AccountingPeriod {
	id: number;
	year: number;
	month: number;
	status: 'open' | 'closed';
	closed_at: string | null;
	closed_by: number | null;
}

export interface BalanceRow {
	account_id: number;
	code: string;
	name: string;
	kind: AccountKind;
	debits: number;
	credits: number;
	/** En su signo natural: positivo es «lo que esta cuenta normalmente tiene». */
	balance: number;
}

export interface TrialBalance {
	year: number;
	month: number | null;
	rows: BalanceRow[];
	debits: number;
	credits: number;
	/** Falso significa que alguien escribió sin pasar por el dominio. */
	is_balanced: boolean;
}

export interface IncomeStatement {
	year: number;
	month: number | null;
	income: number;
	cost: number;
	expense: number;
	gross_profit: number;
	result: number;
	rows: BalanceRow[];
}

export interface BalanceSheet {
	year: number;
	month: number | null;
	assets: number;
	liabilities: number;
	equity: number;
	/** El del periodo, que todavía no se capitalizó: entra en la igualdad aparte. */
	result: number;
	is_balanced: boolean;
	rows: BalanceRow[];
}

/** El libro diario: los asientos del periodo, con sus líneas. */
export interface Journal {
	year: number;
	month: number | null;
	entries: JournalEntry[];
}

export interface LedgerMovement {
	entry_id: number;
	entry_number: number;
	entry_date: string;
	description: string;
	debit: number;
	credit: number;
	memo: string | null;
}

export interface LedgerAccount extends BalanceRow {
	/** Lo acumulado **antes** del periodo. Sin esto el mayor no sirve. */
	opening: number;
	closing: number;
	movements: LedgerMovement[];
}

/** El mayor: cada cuenta con lo que movió en el periodo. */
export interface LedgerReport {
	year: number;
	month: number | null;
	accounts: LedgerAccount[];
}

export interface VatLine {
	/** Entre 0 y 1, como se congela en la línea de la venta. */
	tax_rate: number;
	sales_base: number;
	debit: number;
	returns_tax: number;
	purchases_base: number;
	credit: number;
	balance: number;
}

export interface VatDraft {
	year: number;
	month: number | null;
	lines: VatLine[];
	debit: number;
	credit: number;
	/** Positivo se paga; negativo queda a favor. */
	balance: number;
	in_favor: boolean;
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
	/** Las notas por monto del periodo (T-726). `net_total` ya las cuenta. */
	debit_notes_total?: number;
	credit_notes_total?: number;
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

// ---------------------------------------------------------------------------
// F15: el kárdex y las salidas con motivo (T-1502)
// ---------------------------------------------------------------------------

/** Los once tipos de movimiento del kárdex (RN-98), tal como los guarda el backend. */
export type StockMovementKind =
	| 'opening'
	| 'sale'
	| 'sale_void'
	| 'return'
	| 'entry'
	| 'entry_void'
	| 'exit'
	| 'exit_void'
	| 'count'
	| 'transfer_out'
	| 'transfer_in';

/** Una fila del kárdex: nunca se edita ni se borra. */
export interface StockMovement {
	id: number;
	product_id: number;
	branch_id: number;
	kind: StockMovementKind;
	/** Con signo: negativo baja. */
	quantity: number;
	/** En ESTA sucursal, no el total del producto (RN-102). */
	before_qty: number;
	after_qty: number;
	/** Con el que se valoró; cero es «sin costo» (RN-98). */
	unit_cost: number;
	/** El promedio del producto después de este movimiento (RN-103). */
	avg_cost_after: number;
	lot_id: number | null;
	source_type: string;
	source_id: number;
	source_line: number | null;
	user_id: number;
	moved_at: string;
}

/** La existencia de un producto en una sucursal (RN-102). */
export interface StockLevel {
	product_id: number;
	branch_id: number;
	quantity: number;
}

/** Por qué sale la mercadería (RN-99). Se apaga, no se borra. */
export interface StockReason {
	id: number;
	code: string;
	name: string;
	/** El de la toma física (RN-100): no se elige en una salida ni se apaga. */
	is_system: boolean;
	is_active: boolean;
}

export interface StockExitLine {
	id_product: number;
	name: string;
	quantity: number;
	/** El promedio al salir (RN-99). */
	unit_cost: number;
	subtotal: number;
	lot_id: number | null;
}

export type StockExitStatus = 'applied' | 'voided';

/** Una salida con motivo. No se edita: se anula con motivo y bitácora. */
export interface StockExit {
	id: number;
	branch_id: number;
	reason_id: number;
	reason_code: string;
	reason_name: string;
	user_id: number;
	user_name?: string | null;
	created_at: string;
	notes: string | null;
	status: StockExitStatus;
	total_cost: number;
	items_count: number;
	voided_at: string | null;
	void_reason: string | null;
	lines: StockExitLine[];
}
