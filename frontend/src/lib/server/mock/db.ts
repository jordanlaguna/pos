import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import type { StockCount, StockExit, StockMovement, StockReason } from '$lib/domain/types';
import { dirname, resolve } from 'node:path';
import type { DocumentState, StopReason,
	AmountNote,
	Account,
	AccountingPeriod,
	CashMovement,
	CashSession,
	Category,
	Client,
	Person,
	Product,
	Role,
	SaleItem,
	SaleReturn,
	JournalEntry,
	StockEntry,
	Supplier
} from '$lib/domain/types';
import { DEFAULT_TAX_RATE, round2 } from '$lib/domain/money';
import type {
	EmploymentContract,
	InsPolicy,
	PayrollItem,
	Position,
	WorkSchedule
} from '$lib/domain/payroll';

/**
 * Base de datos del modo mock.
 *
 * Vive en memoria y se vuelca a `.data/mock-db.json` en cada escritura, para que
 * al reiniciar el servidor no se pierda lo que se estuvo probando. No pretende ser
 * una base de datos: es el doble de pruebas del FastAPI real.
 */

export interface MockUser {
	id_user: number;
	email: string;
	password: string;
	role: Role;
	id_person: number | null;
	/** Idioma que eligió la persona. En nulo hereda el de la compañía (T-809). */
	locale?: string | null;
	/**
	 * Soporte: administra la plataforma y no pertenece a ninguna compañía (RN-4).
	 *
	 * Es una marca positiva y no la ausencia de membresías, igual que en la base
	 * de verdad: quien rechaza la única invitación que tenía también se queda sin
	 * ninguna.
	 */
	is_support?: boolean;
}

/** Un plan del catálogo: lo que el sistema deja hacer (F3). */
export interface MockPlan {
	id: number;
	nombre: string;
	precio_mensual: number;
	max_sucursales: number;
	max_terminales: number;
	max_usuarios: number;
	factura_electronica: boolean;
	/** Los módulos que incluye (RN-49, QA-01). Todos siempre, también apagados. */
	sales: boolean;
	cash: boolean;
	invoices: boolean;
	returns: boolean;
	reports: boolean;
	inventory: boolean;
	purchases: boolean;
	suppliers: boolean;
	accounting: boolean;
	payroll: boolean;
	clients: boolean;
	users: boolean;
}

/** Una línea de la bitácora (RF-9). */
export interface MockAudit {
	id: number;
	creado_el: string;
	user_id: number;
	company_id: number | null;
	accion: string;
	detalle: string | null;
	ip: string | null;
}

export interface MockSale {
	id: number;
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
	items: SaleItem[];
	/**
	 * `'01'` factura, `'04'` tiquete, nulo sin facturación electrónica (RN-85).
	 * Ausente en las ventas del seed y en las guardadas antes de T-723, y ausente
	 * vale lo mismo que nulo: por eso no hace falta subir `SEED_VERSION`.
	 */
	document_type?: string | null;
}

/** Fila única de configuración, igual que la tabla `settings` del backend. */
export interface MockSettings {
	data: unknown;
	logo: { mime: string; data: string } | null;
	updated_at: string | null;
	updated_by: number | null;
}

/** Una compañía del sistema simulado. */
export interface MockCompany {
	id: number;
	afiliado: number;
	compania: number;
	nombre: string;
	estado: string;
	branch_code: string;
	terminal_code: string;
	/** Idioma con el que arranca quien entra a esta compañía (T-809). */
	locale: string;
	/** Idioma del documento impreso, que no es el de la pantalla (RN-29, T-811). */
	document_locale: string;
	/** Suscripción (F3): en qué plan está y hasta cuándo. */
	plan_id?: number;
	/** `YYYY-MM-DD`, o nulo si no vence. */
	vence_el?: string | null;
	identificacion?: string | null;
	/** El tipo de Hacienda de la cédula del emisor (RN-45). */
	identification_type?: string | null;
	creada_el?: string;
}

/**
 * Un comprobante numerado (T-704, T-705), como `fe_documents`: cuelga de su
 * origen —la venta, la devolución o la nota— con su consecutivo y su clave.
 */
export interface MockFeDocument {
	source_type: 'sale' | 'return' | 'note' | 'purchase';
	source_id: number;
	document_type: string;
	environment: 'sandbox' | 'production';
	sequence: number;
	consecutive: string;
	clave: string;
	situation: string;
	economic_activity: string | null;
	issued_at: string;
	/**
	 * El recorrido (F7). Lo que la de verdad guarda en `fe_documents`; el
	 * simulado lo avanza por el tiempo transcurrido desde `issued_at` cada vez
	 * que alguien lo lee (`avanzar` en el manejador). Opcional porque los
	 * comprobantes de un estado guardado anterior no lo traen.
	 */
	id?: number;
	status?: DocumentState;
	stop_reason?: StopReason | null;
	stop_detail?: string | null;
	hacienda_status?: string | null;
	signed_at?: string | null;
	sent_at?: string | null;
	resolved_at?: string | null;
	/** Cuándo se reintentó a mano por última vez: el reloj del recorrido vuelve a empezar ahí. */
	resumed_at?: string | null;
	events?: { at: string; event: string; detail?: string | null }[];
}

/** Quién entra a qué compañía y con qué rol. */
export interface MockMembership {
	user_id: number;
	company_id: number;
	rol: Role;
	activa: boolean;
	aceptada_el: string | null;
}

/** Los datos de **una** compañía. Cada una tiene los suyos, sin mezclar. */
export interface MockCompanyData {
	clients: Client[];
	categories: Category[];
	products: Product[];
	sales: MockSale[];
	returns: SaleReturn[];
	/** Las notas por monto (T-726): la ND y la NC que no mueven mercadería. */
	notes?: AmountNote[];
	cash_sessions: CashSession[];
	cash_movements: CashMovement[];
	stock_entries: StockEntry[];
	/** Proveedores y sus abonos (F10). Cada compañía tiene los suyos. */
	suppliers: Supplier[];
	supplier_payments: MockSupplierPayment[];
	/**
	 * El libro (F11). Las cinco tablas nacen vacías y se llenan al activar: una
	 * compañía sin contabilidad las tiene en cero, que es exactamente su estado
	 * en la base de verdad.
	 */
	accounts: Account[];
	account_mappings: MockAccountMapping[];
	accounting_periods: AccountingPeriod[];
	journal_entries: JournalEntry[];
	journal_lines: MockJournalLine[];
	settings?: MockSettings;
	/**
	 * Las credenciales de Hacienda (F6). Una fila por ambiente, como la tabla
	 * `fe_credentials`, y **nace vacío**: un negocio recién dado de alta no tiene
	 * certificado, que es lo que la pantalla tiene que saber pintar.
	 */
	fe_credentials?: MockFeCredentials[];
	/**
	 * Sucursales y cajas (F6, T-608). **Nunca vacías**: una compañía nace con
	 * una de cada, porque sin ellas no se puede vender — lo mismo que hace
	 * `crud_company.dar_de_alta` en el backend de verdad.
	 */
	branches?: MockBranch[];
	terminals?: MockTerminal[];
	/**
	 * La numeración (T-704, T-705): la última secuencia de cada serie —tipo y
	 * ambiente; la oficina es una sola en el simulado— y los comprobantes.
	 */
	fe_sequences?: Record<string, number>;
	fe_documents?: MockFeDocument[];
	/**
	 * La planilla (F12, T-1214): las once tablas de la compañía, en un solo
	 * objeto. Un archivo de antes de F12 no lo trae y nace vacío al tocarlo.
	 */
	payroll?: MockPayrollData;
	/**
	 * El inventario a fondo (F15, T-1502): los motivos de salida, las salidas
	 * y el kárdex. Un archivo de antes de F15 no los trae; `SEED_VERSION` lo
	 * resiembra, y las tres nacen al tocarlas por si acaso.
	 */
	stock_reasons?: StockReason[];
	stock_exits?: StockExit[];
	stock_movements?: StockMovement[];
	/** Las tomas físicas (T-1503). Nacen al tocarlas, como las salidas. */
	stock_counts?: StockCount[];
}

/** Un empleado tal como se guarda; el contrato vigente se le pega al salir. */
export interface MockEmployee {
	id: number;
	user_id: number | null;
	identification_type: string;
	identification: string;
	first_name: string;
	last_name_1: string;
	last_name_2: string | null;
	insured_number: string | null;
	birth_date: string;
	gender: string;
	marital_status: string;
	nationality: string;
	phone: string | null;
	email: string | null;
	is_pensioner: boolean;
	iban: string | null;
	hired_on: string;
	terminated_on: string | null;
	termination_cause: string | null;
	dependent_children: number;
	spouse_credit: boolean;
	is_active: boolean;
}

/** Una acción de personal (RN-90); lo aplicado se calcula al salir. */
export interface MockAction {
	id: number;
	employee_id: number;
	kind: string;
	starts_on: string;
	ends_on: string | null;
	hours: number | null;
	days: number | null;
	amount: number | null;
	total_amount: number | null;
	new_salary: number | null;
	position_id: number | null;
	is_recurring: boolean;
	memo: string | null;
	cancels_action_id: number | null;
	suspended_at: string | null;
	suspended_by: number | null;
	suspension_reason: string | null;
	source: string;
	created_by: number;
	created_at: string;
}

export interface MockRun {
	id: number;
	kind: string;
	schedule_id: number | null;
	period_from: string;
	period_to: string;
	pay_date: string;
	status: string;
	adjusts_run_id: number | null;
	journal_entry_id: number | null;
	created_by: number;
	created_at: string;
	approved_by: number | null;
	approved_at: string | null;
	paid_by: number | null;
	paid_at: string | null;
}

/** Una línea con sus rubros congelados (RN-66). */
export interface MockLine {
	id: number;
	run_id: number;
	employee_id: number;
	contract_id: number;
	gross: number;
	employee_deductions: number;
	income_tax: number;
	other_deductions: number;
	net: number;
	employer_charges: number;
	items: PayrollItem[];
}

export interface MockPayrollData {
	settings: { employer_number: string | null; ina_exempt: boolean };
	schedules: WorkSchedule[];
	positions: Position[];
	policies: InsPolicy[];
	employees: MockEmployee[];
	contracts: EmploymentContract[];
	actions: MockAction[];
	runs: MockRun[];
	lines: MockLine[];
	vacations: {
		id: number;
		employee_id: number;
		kind: string;
		days: number;
		on_date: string;
		run_id: number | null;
		action_id: number | null;
	}[];
	opening: { id: number; employee_id: number; period_month: string; gross: number }[];
}

export function planillaVacia(): MockPayrollData {
	return {
		settings: { employer_number: null, ina_exempt: false },
		schedules: [],
		positions: [],
		policies: [],
		employees: [],
		contracts: [],
		actions: [],
		runs: [],
		lines: [],
		vacations: [],
		opening: []
	};
}

/**
 * La planilla del negocio de demostración (T-1214): dos jornadas, dos puestos,
 * una póliza y dos empleados con contrato, sin corridas. Las personas son
 * inventadas y los números también.
 */
export function planillaDemo(): MockPayrollData {
	return {
		...planillaVacia(),
		settings: { employer_number: '2-03101000000-001-001', ina_exempt: true },
		schedules: [
			{ id: 1, name: 'Quincenal', frequency: 'semimonthly', shift: 'day', hours_per_day: 8, workdays_per_week: 6, rest_day_paid: true, first_cut_day: 15, cut_weekday: null, series_start: null, is_active: true },
			{ id: 2, name: 'Mensual', frequency: 'monthly', shift: 'day', hours_per_day: 8, workdays_per_week: 6, rest_day_paid: true, first_cut_day: null, cut_weekday: null, series_start: null, is_active: true }
		],
		positions: [
			{ id: 1, name: 'Caja', ccss_code: '4211', ins_code: '52', is_active: true },
			{ id: 2, name: 'Bodega', ccss_code: '9333', ins_code: '93', is_active: true }
		],
		policies: [{ id: 1, number: 'RT-100200', rt_rate: 0.0146, is_default: true }],
		employees: [
			{ id: 1, user_id: null, identification_type: 'national', identification: '112340567', first_name: 'María Fernanda', last_name_1: 'Rojas', last_name_2: 'Vega', insured_number: null, birth_date: '1992-03-15', gender: 'F', marital_status: 'single', nationality: 'CR', phone: '8888-0001', email: null, is_pensioner: false, iban: 'CR05015202001026284066', hired_on: '2025-02-01', terminated_on: null, termination_cause: null, dependent_children: 1, spouse_credit: false, is_active: true },
			{ id: 2, user_id: null, identification_type: 'national', identification: '204560789', first_name: 'Carlos Andrés', last_name_1: 'Jiménez', last_name_2: 'Mora', insured_number: null, birth_date: '1988-07-20', gender: 'M', marital_status: 'married', nationality: 'CR', phone: '8888-0002', email: null, is_pensioner: false, iban: null, hired_on: '2024-09-01', terminated_on: null, termination_cause: null, dependent_children: 0, spouse_credit: true, is_active: true }
		],
		contracts: [
			{ id: 1, employee_id: 1, schedule_id: 1, position_id: 1, ins_policy_id: null, valid_from: '2025-02-01', valid_to: null, period_salary: 325000, solidarista_rate: null },
			{ id: 2, employee_id: 2, schedule_id: 2, position_id: 2, ins_policy_id: 1, valid_from: '2024-09-01', valid_to: null, period_salary: 540000, solidarista_rate: 0.03 }
		]
	};
}

/** Una sucursal. El código son tres dígitos y va en el consecutivo (RN-15). */
export interface MockBranch {
	id: number;
	codigo: string;
	nombre: string;
	activa: boolean;
}

/** Una caja. Cinco dígitos, y su código es único **por sucursal**. */
export interface MockTerminal {
	id: number;
	branch_id: number;
	codigo: string;
	nombre: string;
	activa: boolean;
}

/**
 * Una fila de `fe_credentials`, por ambiente (F6).
 *
 * **No hay `p12` ni `pin` ni contraseña en claro**, igual que en la tabla de
 * verdad: la llave privada vive en Vault y el PIN no se guarda en ninguna parte.
 * Lo que el simulado guarda de la contraseña es una marca de que la hay, para
 * poder contestar `atv_configured` sin inventarse un secreto que nadie debería
 * poder leer.
 */
export interface MockFeCredentials {
	environment: 'sandbox' | 'production';
	certificate_name: string | null;
	expires_at: string | null;
	cert_uploaded_at: string | null;
	atv_user: string | null;
	atv_configured: boolean;
	atv_verified_at: string | null;
	/**
	 * Solo del simulado: qué va a contestar el IdP al comprobar.
	 *
	 * Los tres desenlaces de RF-31 no se pueden provocar contra un servicio de
	 * verdad —«Hacienda caída» hay que esperar a que pase— así que la prueba de
	 * punta a punta necesita poder pedirlos. Se deduce de la contraseña que se
	 * guardó, sin guardarla: ver `veredictoDe` en el manejador.
	 */
	atv_verdict: 'ok' | 'rejected' | 'unreachable';
}

/** Una fila del mapeo: qué cuenta usa cada papel de cada evento. */
export interface MockAccountMapping {
	id: number;
	event: string;
	role: string;
	account_id: number;
}

/** Una línea de asiento, como se guarda. */
export interface MockJournalLine {
	id: number;
	entry_id: number;
	account_id: number;
	debit: number;
	credit: number;
	/** En porcentaje —13, no 0,13—, solo en las líneas de IVA (RN-65). */
	tax_rate: number | null;
	memo: string | null;
}

/** Un abono a **una** compra (RN-55). El saldo no se guarda: es una resta. */
export interface MockSupplierPayment {
	id: number;
	supplier_id: number;
	entry_id: number;
	amount: number;
	/** 'cash' | 'transfer' | 'other'. Solo el primero mueve la gaveta (RN-56). */
	method: string;
	reference: string | null;
	cash_movement_id: number | null;
	user_id: number;
	paid_at: string;
}

/**
 * Lo global: la identidad y las membresías, que no son de ninguna compañía.
 *
 * Es la misma división que en la base de verdad —`users` y `persons` son
 * identidad (RN-3)— y no una simplificación del mock.
 */
export interface MockRoot {
	/** Versión del seed que escribió este archivo. Ver `SEED_VERSION`. */
	seed_version?: number;
	persons: Person[];
	users: MockUser[];
	companies: MockCompany[];
	memberships: MockMembership[];
	/** El catálogo de planes y la bitácora: de la plataforma, no de una compañía. */
	plans: MockPlan[];
	audit: MockAudit[];
	/**
	 * Las tasas de planilla que se agregaron **después** de la siembra (T-1204).
	 * Son del país, como las de la API: una lista para todas las compañías. Lo
	 * sembrado sale de `payrollRates.ts` y no se guarda, así que un archivo de un
	 * seed viejo no necesita `SEED_VERSION` nuevo: le falta esta lista y ya.
	 */
	payroll_rates?: MockPayrollRate[];
	empresas: Record<number, MockCompanyData>;
	counters: Record<string, number>;
}

/** Una fila de `payroll_rates` agregada desde el panel (`PUT /support/payroll/rates`). */
export interface MockPayrollRate {
	concept: string;
	payer: string;
	value: number;
	valid_from: string;
	source: string;
	verified_at: string;
}

/**
 * Vista de trabajo: lo global más los datos de UNA compañía.
 *
 * Las propiedades apuntan a los mismos arreglos que guarda `MockRoot`, así que
 * mutar `db.products` muta el almacén de verdad. Es lo que permite que los
 * manejadores sigan escritos igual que cuando el mock tenía una sola compañía:
 * lo único que cambió es que hay que decir de cuál se habla.
 */
export type MockDb = MockRoot & MockCompanyData;

/*
 * Las pruebas de punta a punta escriben **en su propio archivo** (T-920).
 *
 * `POS_MOCK_FRESH` hace que no se lea lo guardado, pero `persist()` escribe en
 * cada cambio: con un solo archivo, la primera venta de la batería reemplazaba
 * la demostración de quien estuviera usando el POS a mano, que es justo lo que
 * T-920 prometía no tocar. No se notaba porque la bandera nunca llegaba —la
 * configuración de Playwright tenía dos `env` y el segundo pisaba al primero—.
 * Se lee directo de `process.env` porque `SEMBRAR_DE_CERO` se define más abajo.
 */
const DB_PATH = resolve(
	process.cwd(),
	'.data',
	process.env.POS_MOCK_FRESH === '1' ? 'mock-db.e2e.json' : 'mock-db.json'
);

/**
 * Versión de los datos de demostración. **Se sube al cambiar el seed.**
 *
 * El estado del simulado se guarda en disco para que las ventas de una sesión de
 * demostración sigan ahí al reiniciar. El precio es que un archivo viejo
 * sobrevive a un cambio del seed, y eso se paga en tiempo perdido: al darle a
 * Carlos el POS en inglés (T-809), el archivo de antes no tenía ese campo, el
 * token seguía diciendo `es` y la prueba de punta a punta fallaba señalando la
 * pantalla —que era el único sitio donde no estaba el problema—.
 *
 * Con la versión, un seed nuevo descarta el archivo viejo y vuelve a sembrar. Se
 * pierde el estado de la demostración, que es exactamente lo que hay que perder:
 * los datos de prueba no valen más que la prueba.
 */
// 6 (F5, 2026-09-05): los productos llevan `cabys_code`, `tax_rate` y
// `unit_of_measure`, y cada línea de venta guarda la tarifa que se le congeló al
// cobrar. Un archivo de la 5 no tiene esos campos.
//
// La subida arregló además algo que no era de forma sino de acumulación: el
// archivo guardado tenía **29 compañías**, una «Repuestos Yamaha» por cada
// corrida pasada de `categorias.spec.ts`, y esa pila hacía fallar cuatro pruebas
// de tres archivos distintos —incluida una del aviso de vencimiento, que no toca
// nada de eso—. Las pruebas que dan de alta su propia compañía no la retiran, así
// que el archivo crece sin techo entre corridas; sembrar de nuevo es lo que hay
// hoy para vaciarlo, y queda anotado como pendiente en T-920.
// 7 (2026-09-06): el catálogo de demostración **viene clasificado**. Antes los
// 26 productos nacían sin CABYS, así que todos heredaban el 13 % configurado y
// la pantalla enseñaba F5 como si no existiera: el arroz y los frijoles, que son
// canasta básica al 1 %, cobraban 13 %. Los códigos son reales.
//
// Tres quedan sin clasificar **a propósito** —yogurt, natilla y maní—: es el
// estado en que llega un catálogo heredado, y sin él la asignación en lote no
// tiene nada que hacer y el aviso de «sin clasificar» del carrito no se ve nunca.
// 9 (F10, 2026-09-12): proveedores y abonos, y los productos nacen con `cost`.
// Sin costo, la pantalla de compras no tendría contra qué comparar el de la
// factura y el promedio ponderado (RN-54) se vería igual que no tenerlo.
//
// Los dos proveedores son a propósito **distintos** del emisor de
// `tests/fixtures/factura-proveedor-v43.xml`: así el XML del demo muestra el
// caso que importa de RF-42, el del proveedor que todavía no existe.
// 13 (F6, T-608): los contadores de `branches` y `terminals`. Sin ellos la
// primera sucursal creada desde la pantalla nace con el id 1, que ya es el de la
// sembrada, y editar una editaba la otra.
// 14 (F7, T-715): los productos llevan `tax_code`, el código de tarifa de
// Hacienda. Los tres sin clasificar siguen sin él, que es lo cierto: su tarifa
// es la del negocio y del porcentaje no se vuelve al código (RN-76).
// 15 (F7, T-731): las líneas de venta congelan el CABYS y la unidad, y los
// clientes llevan su tipo de identificación (T-617). Sin eso el comprobante del
// demo imprimiría la línea sin CABYS y al receptor sin su tipo.
// 17 (F12, T-1214): la compañía de demostración trae su planilla —dos
// jornadas, dos puestos, una póliza y dos empleados con contrato— y los
// contadores que siguen. Un archivo de la 16 no tiene nada de eso.
// 19 (F15, T-1502): los seis motivos de salida con los que nace toda compañía
// y una apertura en el kárdex por cada producto con existencia. Un archivo de
// la 18 tendría existencias sin movimiento que las explique.
const SEED_VERSION = 19;

/** La compañía del negocio de demostración. Es la que tiene datos. */
export const COMPANIA_DEMO = 1;

let raiz: MockRoot | null = null;

/**
 * Siguiente id para una colección, al estilo AUTO_INCREMENT.
 *
 * El contador es **global** y no por compañía, igual que en MySQL: los
 * identificadores no se reciclan entre compañías, y eso es justamente lo que
 * hace que una prueba de aislamiento pruebe algo —si cada compañía empezara en
 * 1, pedir «el producto 1» de la otra devolvería el propio por casualidad—.
 */
export function nextId(key: string): number {
	const state = cargar();
	const current = state.counters[key] ?? 0;
	const next = current + 1;
	state.counters[key] = next;
	return next;
}

/**
 * `POS_MOCK_FRESH=1` ignora lo guardado y siembra de cero (T-920).
 *
 * Lo pone la configuración de Playwright. Las pruebas de punta a punta que dan
 * de alta su propia compañía —la salida correcta de T-310— no la retiran al
 * terminar, así que el archivo **acumula una por corrida**: llegó a 29
 * compañías, y esa pila tumbó cuatro pruebas de tres archivos, incluida una del
 * aviso de vencimiento que no toca nada de eso.
 *
 * La salida no es que cada prueba limpie lo suyo —una que falla a mitad no
 * limpia nada— sino **empezar limpio**, que es la misma lección de T-310 vista
 * desde el otro lado. Se ignora el archivo en vez de borrarlo: la demostración
 * de quien esté usando el POS a mano no se toca.
 */
const SEMBRAR_DE_CERO = process.env.POS_MOCK_FRESH === '1';

function cargar(): MockRoot {
	if (raiz) return raiz;

	if (!SEMBRAR_DE_CERO && existsSync(DB_PATH)) {
		try {
			const parsed = JSON.parse(readFileSync(DB_PATH, 'utf-8')) as MockRoot;
			// Si el archivo quedó de una versión anterior del seed, se descarta.
			const vigente = parsed?.seed_version === SEED_VERSION;
			if (vigente && parsed.empresas && parsed.counters && Array.isArray(parsed.users) && Array.isArray(parsed.plans)) {
				raiz = parsed;
				return raiz;
			}
		} catch {
			// Archivo corrupto: se regenera desde el seed.
		}
	}

	raiz = seed();
	persist();
	return raiz;
}

/** Las compañías y las membresías, sin ninguna en particular. */
export function getRoot(): MockRoot {
	return cargar();
}

/** Los datos de una compañía, creándolos vacíos si es la primera vez. */
export function getEmpresa(companyId: number): MockCompanyData {
	const state = cargar();
	if (!state.empresas[companyId]) {
		state.empresas[companyId] = empresaVacia();
	}
	return state.empresas[companyId];
}

/**
 * La vista de trabajo de una compañía.
 *
 * El `spread` copia **referencias** a los arreglos, no los arreglos, así que
 * `db.products.push(...)` escribe en el almacén. Lo único que no puede hacerse
 * sobre esta vista es reasignar una colección entera (`db.products = []`),
 * porque eso cambiaría la copia y no el original.
 */
export function getDb(companyId: number = COMPANIA_DEMO): MockDb {
	const state = cargar();
	return { ...state, ...getEmpresa(companyId) };
}

/**
 * Los motivos de salida con los que nace toda compañía (F15, RN-99), como
 * `crud_company._motivos` en el backend. Con `primerId` los ids van seguidos
 * desde ahí —es lo que usa la semilla, que todavía no tiene contadores—; sin
 * él los pide al contador, que es lo que hace una compañía creada en vivo.
 */
const MOTIVOS_DE_FABRICA: [string, string, boolean][] = [
	['shrinkage', 'Merma', false],
	['damage', 'Daño', false],
	['expired', 'Vencido', false],
	['internal_use', 'Consumo interno', false],
	['sample', 'Muestra', false],
	['count', 'Toma física', true]
];

export function motivosDeFabrica(primerId?: number): StockReason[] {
	return MOTIVOS_DE_FABRICA.map(([code, name, is_system], i) => ({
		id: primerId === undefined ? nextId('stock_reasons') : primerId + i,
		code,
		name,
		is_system,
		is_active: true
	}));
}

/**
 * La apertura del kárdex de cada producto con existencia (RN-105): es lo que
 * la migración 023 hace con una base que ya tenía mercadería.
 */
function aperturasDe(products: Product[]): StockMovement[] {
	let id = 0;
	return products
		.filter((p) => p.stock > 0)
		.map((p) => ({
			id: ++id,
			product_id: p.id_product,
			branch_id: 1,
			kind: 'opening',
			quantity: p.stock,
			before_qty: 0,
			after_qty: p.stock,
			unit_cost: 0,
			avg_cost_after: Number(p.cost ?? 0),
			lot_id: null,
			source_type: 'product',
			source_id: p.id_product,
			source_line: null,
			user_id: 1,
			moved_at: p.created_at
		}));
}

export function empresaVacia(motivos: StockReason[] = motivosDeFabrica()): MockCompanyData {
	return {
		clients: [],
		categories: [],
		products: [],
		sales: [],
		returns: [],
		notes: [],
		cash_sessions: [],
		cash_movements: [],
		stock_entries: [],
		suppliers: [],
		supplier_payments: [],
		accounts: [],
		account_mappings: [],
		accounting_periods: [],
		journal_entries: [],
		journal_lines: [],
		settings: { data: {}, logo: null, updated_at: null, updated_by: null },
		fe_credentials: [],
		// Una sucursal y una caja, como las que crea `dar_de_alta`: sin ellas no
		// se puede vender, así que no pueden ser un paso que alguien tenga que
		// acordarse de dar.
		branches: [{ id: 1, codigo: '001', nombre: 'Casa matriz', activa: true }],
		terminals: [{ id: 1, branch_id: 1, codigo: '00001', nombre: 'Caja 1', activa: true }],
		payroll: planillaVacia(),
		// F15: los motivos de fábrica y nada en el kárdex, como una compañía
		// recién dada de alta.
		stock_reasons: motivos,
		stock_exits: [],
		stock_movements: [],
		stock_counts: []
	};
}

export function persist(): void {
	if (!raiz) return;
	try {
		mkdirSync(dirname(DB_PATH), { recursive: true });
		writeFileSync(DB_PATH, JSON.stringify(raiz, null, '\t'), 'utf-8');
	} catch {
		// Sin permisos de escritura el mock sigue funcionando, solo que en memoria.
	}
}

/** Reinicia la base al estado de fábrica. Lo usa el botón "Reiniciar demo". */
export function resetDb(): void {
	raiz = seed();
	persist();
}

function iso(date: Date): string {
	return date.toISOString();
}

/** `YYYY-MM-DD` a `days` de hoy. Para las fechas de vencimiento del demo. */
function enDias(days: number): string {
	const d = new Date();
	d.setDate(d.getDate() + days);
	return d.toISOString().slice(0, 10);
}

function daysAgo(days: number, hour = 12, minute = 0): Date {
	const d = new Date();
	d.setDate(d.getDate() - days);
	d.setHours(hour, minute, 0, 0);
	return d;
}

// ------------------------------------------------------------------ datos base

// El árbol de dos niveles (F4). «Bebidas» viene repartida en subcategorías y las
// demás raíces no: el demo tiene que mostrar los dos casos, porque son los dos
// que la grilla de ventas y la ficha del producto tratan distinto —una raíz sin
// hijas admite productos, una con hijas muestra fichas (RN-6)—.
const CATEGORIES: Category[] = [
	{ id: 1, name: 'Abarrotes', parent_id: null, sort_order: 1, is_active: true },
	{ id: 2, name: 'Bebidas', parent_id: null, sort_order: 2, is_active: true },
	{ id: 3, name: 'Lácteos', parent_id: null, sort_order: 3, is_active: true },
	{ id: 4, name: 'Panadería', parent_id: null, sort_order: 4, is_active: true },
	{ id: 5, name: 'Limpieza', parent_id: null, sort_order: 5, is_active: true },
	{ id: 6, name: 'Snacks', parent_id: null, sort_order: 6, is_active: true },
	{ id: 7, name: 'Gaseosas', parent_id: 2, sort_order: 1, is_active: true },
	{ id: 8, name: 'Aguas y jugos', parent_id: 2, sort_order: 2, is_active: true },
	{ id: 9, name: 'Cervezas', parent_id: 2, sort_order: 3, is_active: true },
	{ id: 10, name: 'Café y té', parent_id: 2, sort_order: 4, is_active: true }
];

const PRODUCT_SEED: Omit<Product, 'id_product' | 'created_at'>[] = [
	{ name: 'Arroz Tío Pelón 1kg', description: 'Arroz blanco 80% grano entero', price: 1450, stock: 120, barcode: '7441000100015', cabys_code: '2316100000100', tax_rate: 0.01, category_id: 1 },
	{ name: 'Frijoles negros 900g', description: 'Frijol negro seleccionado', price: 1690, stock: 84, barcode: '7441000100022', cabys_code: '0170102000400', tax_rate: 0.01, category_id: 1 },
	{ name: 'Aceite Sabemas 900ml', description: 'Aceite vegetal de girasol', price: 2350, stock: 46, barcode: '7441000100039', cabys_code: '2163200000000', tax_rate: 0.01, category_id: 1 },
	{ name: 'Azúcar Doña María 1kg', description: 'Azúcar blanca refinada', price: 1250, stock: 95, barcode: '7441000100046', cabys_code: '2352001010000', tax_rate: 0.01, category_id: 1 },
	{ name: 'Sal Sol 1kg', description: 'Sal refinada yodada', price: 620, stock: 140, barcode: '7441000100053', cabys_code: '2399908000200', tax_rate: 0.01, category_id: 1 },
	{ name: 'Pasta espagueti 400g', description: 'Pasta de sémola de trigo', price: 890, stock: 72, barcode: '7441000100060', cabys_code: '2371000000200', tax_rate: 0.01, category_id: 1 },
	{ name: 'Café 1820 500g', description: 'Café molido tueste medio', price: 4250, stock: 38, barcode: '7441000200014', cabys_code: '2391102010200', tax_rate: 0.01, category_id: 10 },
	{ name: 'Coca-Cola 2L', description: 'Refresco de cola', price: 1790, stock: 64, barcode: '7441000200021', cabys_code: '2449003000100', tax_rate: 0.13, category_id: 7 },
	{ name: 'Agua Cristal 600ml', description: 'Agua purificada sin gas', price: 690, stock: 180, barcode: '7441000200038', cabys_code: '2441002020000', tax_rate: 0.13, category_id: 8 },
	{ name: 'Jugo Del Valle 1L', description: 'Néctar de naranja', price: 1390, stock: 52, barcode: '7441000200045', cabys_code: '2449002000100', tax_rate: 0.13, category_id: 8 },
	{ name: 'Cerveza Imperial 350ml', description: 'Cerveza lager, lata', price: 1150, stock: 96, barcode: '7441000200052', cabys_code: '2431000000000', tax_rate: 0.13, category_id: 9 },
	{ name: 'Té helado Lipton 500ml', description: 'Té negro con limón', price: 950, stock: 7, barcode: '7441000200069', cabys_code: '2449002000200', tax_rate: 0.13, category_id: 10 },
	{ name: 'Leche Dos Pinos 1L', description: 'Leche entera UHT', price: 1290, stock: 58, barcode: '7441000300013', cabys_code: '2211001030000', tax_rate: 0.01, category_id: 3 },
	{ name: 'Queso Turrialba 400g', description: 'Queso fresco artesanal', price: 3450, stock: 22, barcode: '7441000300020', cabys_code: '2225101010200', tax_rate: 0.01, category_id: 3 },
	{ name: 'Yogurt natural 1kg', description: 'Yogurt sin azúcar añadida', price: 2290, stock: 31, barcode: '7441000300037', category_id: 3 },
	{ name: 'Natilla Dos Pinos 200g', description: 'Crema agria', price: 1180, stock: 9, barcode: '7441000300044', category_id: 3 },
	{ name: 'Pan cuadrado Bimbo', description: 'Pan blanco de molde 680g', price: 1850, stock: 40, barcode: '7441000400012', cabys_code: '2349002010700', tax_rate: 0.01, category_id: 4 },
	{ name: 'Tortillas de maíz 20u', description: 'Tortilla de maíz nixtamalizado', price: 1090, stock: 55, barcode: '7441000400029', cabys_code: '2349001010100', tax_rate: 0.01, category_id: 4 },
	{ name: 'Pan dulce surtido', description: 'Bolsa de 6 unidades', price: 1650, stock: 18, barcode: '7441000400036', cabys_code: '2349002010600', tax_rate: 0.01, category_id: 4 },
	{ name: 'Detergente Irex 1kg', description: 'Detergente en polvo multiusos', price: 2790, stock: 44, barcode: '7441000500011', cabys_code: '3532201060000', tax_rate: 0.13, category_id: 5 },
	{ name: 'Jabón de baño Protex', description: 'Jabón antibacterial 110g', price: 890, stock: 76, barcode: '7441000500028', cabys_code: '3532101010199', tax_rate: 0.13, category_id: 5 },
	{ name: 'Papel higiénico Scott 4u', description: 'Papel higiénico doble hoja', price: 2450, stock: 5, barcode: '7441000500035', cabys_code: '3219301000000', tax_rate: 0.01, category_id: 5 },
	{ name: 'Cloro Magia Blanca 1L', description: 'Blanqueador desinfectante', price: 1120, stock: 62, barcode: '7441000500042', cabys_code: '3532201010000', tax_rate: 0.13, category_id: 5 },
	{ name: 'Galletas Chiky 12u', description: 'Galleta con chispas de chocolate', price: 1590, stock: 68, barcode: '7441000600010', cabys_code: '2342001009900', tax_rate: 0.13, category_id: 6 },
	{ name: 'Tostitos original 200g', description: 'Tortilla chips de maíz', price: 1950, stock: 34, barcode: '7441000600027', cabys_code: '2314000990300', tax_rate: 0.13, category_id: 6 },
	{ name: 'Maní salado 150g', description: 'Maní tostado con sal', price: 1150, stock: 3, barcode: '7441000600034', category_id: 6 }
];

const PERSON_SEED: Omit<Person, 'id_person' | 'id_user'>[] = [
	{ birth_date: '1990-04-12', identification: '113450678', name: 'Jordan', lastName: 'Laguna', secondName: 'Mora', telephone: '88451230', email: 'admin@ventasys.cr' },
	{ birth_date: '1996-11-03', identification: '118920345', name: 'María', lastName: 'Rojas', secondName: 'Vargas', telephone: '87123344', email: 'cajero@ventasys.cr' },
	{ birth_date: '1988-07-25', identification: '109887654', name: 'Carlos', lastName: 'Jiménez', secondName: 'Solano', telephone: '89905512', email: 'carlos@ventasys.cr' },
	{ birth_date: '1985-02-19', identification: '104556677', name: 'Sole', lastName: 'Soporte', secondName: 'Vargas', telephone: '88880000', email: 'soporte@ventasys.cr' }
];

/**
 * Dos proveedores para el demo (F10).
 *
 * Uno con plazo y otro de contado, que son los dos casos que la pantalla de
 * compras trata distinto: el primero propone 30 días y abre una cuenta por
 * pagar, el segundo pide decir cómo se pagó. Con uno solo no se ve la
 * diferencia.
 */
const SUPPLIERS: Supplier[] = [
	{
		id: 1,
		identification_type: '02',
		identification: '3101987654',
		// A propósito NO es «Distribuidora La Central», que es quien emite la
		// factura de ejemplo: así el XML del demo muestra el caso de un proveedor
		// que todavía no existe y se da de alta al confirmar (RF-42).
		name: 'Mayorista del Este',
		email: 'ventas@mayoristadeleste.cr',
		phone: '22221111',
		payment_terms_days: 30,
		is_active: true
	},
	{
		id: 2,
		identification_type: '01',
		identification: '109990888',
		name: 'Verduras del Valle',
		email: null,
		phone: '87776655',
		payment_terms_days: 0,
		is_active: true
	}
];

/**
 * El catálogo de planes del demo.
 *
 * Los precios son de mentira y el demo es el único lugar donde eso está bien: la
 * base de verdad trae un solo plan y cuánto se cobra es una decisión comercial,
 * no un dato que un seed pueda inventar. Acá hacen falta tres para que el panel
 * se pueda mostrar: con uno solo, el desplegable de plan y la columna «uso» no
 * enseñan nada.
 */
const PLAN_SEED: MockPlan[] = [
	{
		id: 1,
		nombre: 'Básico',
		precio_mensual: 15000,
		max_sucursales: 1,
		max_terminales: 1,
		max_usuarios: 3,
		// El plan de la segunda compañía del demo: la base del POS y ninguno de
		// los que se venden aparte. Es lo que permite comprobar el rechazo de
		// RN-49 sin dar de alta nada (T-1004).
		factura_electronica: false,
		sales: true,
		cash: true,
		invoices: true,
		returns: true,
		reports: true,
		inventory: true,
		purchases: false,
		suppliers: false,
		accounting: false,
		payroll: false,
		clients: true,
		users: true
	},
	{
		id: 2,
		nombre: 'Comercio',
		precio_mensual: 25000,
		max_sucursales: 1,
		max_terminales: 3,
		max_usuarios: 10,
		factura_electronica: false,
		// El de la primera: con todo, para poder recorrerlo en el demo.
		sales: true,
		cash: true,
		invoices: true,
		returns: true,
		reports: true,
		inventory: true,
		purchases: true,
		suppliers: true,
		accounting: true,
		payroll: true,
		clients: true,
		users: true
	},
	{
		id: 3,
		nombre: 'Cadena',
		precio_mensual: 60000,
		max_sucursales: 5,
		max_terminales: 15,
		max_usuarios: 40,
		factura_electronica: true,
		sales: true,
		cash: true,
		invoices: true,
		returns: true,
		reports: true,
		inventory: true,
		purchases: true,
		suppliers: true,
		accounting: true,
		payroll: true,
		clients: true,
		users: true
	},
	{
		// Uno de los paquetes de QA-01, como los da de alta la migración 022.
		id: 4,
		nombre: 'Restaurante',
		precio_mensual: 0,
		max_sucursales: 1,
		max_terminales: 3,
		max_usuarios: 10,
		factura_electronica: false,
		sales: true,
		cash: false,
		invoices: true,
		returns: false,
		reports: false,
		inventory: false,
		purchases: false,
		suppliers: false,
		accounting: false,
		payroll: false,
		clients: true,
		users: true
	},
	{
		// Uno de los paquetes de QA-01, como los da de alta la migración 022.
		id: 5,
		nombre: 'Comercio con compras',
		precio_mensual: 0,
		max_sucursales: 1,
		max_terminales: 3,
		max_usuarios: 10,
		factura_electronica: false,
		sales: true,
		cash: true,
		invoices: true,
		returns: true,
		reports: true,
		inventory: true,
		purchases: true,
		suppliers: true,
		accounting: false,
		payroll: false,
		clients: true,
		users: true
	},
	{
		// Uno de los paquetes de QA-01, como los da de alta la migración 022.
		id: 6,
		nombre: 'Completo',
		precio_mensual: 0,
		max_sucursales: 1,
		max_terminales: 3,
		max_usuarios: 10,
		factura_electronica: false,
		sales: true,
		cash: true,
		invoices: true,
		returns: true,
		reports: true,
		inventory: true,
		purchases: true,
		suppliers: true,
		accounting: true,
		payroll: true,
		clients: true,
		users: true
	}
];

const CLIENT_SEED: Omit<Client, 'id_client'>[] = [
	{ identification: '115670987', name: 'Ana', last_name: 'Castro', second_name: 'Núñez', email: 'ana.castro@correo.cr', telephone: 88012233, address: 'San José, Curridabat, 200m sur del parque', register_date: '2026-02-11' },
	{ identification: '107654321', name: 'Luis', last_name: 'Fernández', second_name: 'Alpízar', email: 'luis.f@correo.cr', telephone: 87334455, address: 'Heredia, San Francisco, Av. 7', register_date: '2026-03-04' },
	{ identification: '119870654', name: 'Gabriela', last_name: 'Méndez', second_name: 'Quirós', email: 'gaby.mendez@correo.cr', telephone: 86220099, address: 'Cartago, El Carmen, calle 3', register_date: '2026-05-20' },
	{ identification: '112233445', name: 'Roberto', last_name: 'Salas', second_name: 'Ureña', email: 'rsalas@correo.cr', telephone: 83445566, address: 'Alajuela, centro, 100m oeste del mercado', register_date: '2026-06-30' }
];

const PAYMENT_MIX = [
	'Efectivo',
	'Efectivo',
	'Efectivo',
	'Tarjeta de crédito',
	'Tarjeta de crédito',
	'Transferencia bancaria',
	'Pago móvil'
];

function seed(): MockRoot {
	const now = new Date();
	const created = iso(daysAgo(120));

	const persons: Person[] = PERSON_SEED.map((p, i) => ({
		...p,
		id_person: i + 1,
		id_user: i + 1
	}));

	const users: MockUser[] = [
		{ id_user: 1, email: 'admin@ventasys.cr', password: 'admin123', role: 'admin', id_person: 1 },
		{ id_user: 2, email: 'cajero@ventasys.cr', password: 'cajero123', role: 'cajero', id_person: 2 },
		/*
		 * Carlos tiene el POS **en inglés**, y es el único.
		 *
		 * No es un adorno del demo: es lo que hace que el idioma del token se
		 * pruebe de punta a punta sin tocar a los otros dos (T-809). Con todos en
		 * español, la única prueba posible sería que el reclamo `loc` viaja, no
		 * que la pantalla lo obedece.
		 */
		{
			id_user: 3,
			email: 'carlos@ventasys.cr',
			password: 'cajero123',
			role: 'cajero',
			id_person: 3,
			locale: 'en'
		},
		/*
		 * La cuenta de soporte (F3, RN-4).
		 *
		 * Sin membresías: no aparece en `memberships` y por eso su login devuelve
		 * un token sin compañía y su pantalla es el panel. Es lo que hace que el
		 * demo pueda mostrar las dos aplicaciones —el POS y el panel— con las
		 * mismas credenciales de siempre a la vista.
		 *
		 * `role` no significa nada acá y se pone 'admin' porque el tipo lo pide: el
		 * rol es de la membresía y soporte no tiene ninguna.
		 */
		{
			id_user: 4,
			email: 'soporte@ventasys.cr',
			password: 'soporte123',
			role: 'admin',
			id_person: 4,
			is_support: true
		}
	];

	const products: Product[] = PRODUCT_SEED.map((p, i) => ({
		...p,
		id_product: i + 1,
		created_at: created,
		// El código de tarifa de Hacienda (RN-76). Se deriva acá y no se escribe
		// en cada fila porque el demo usa dos tarifas y las dos tienen un solo
		// código posible: 1 % es `02` y 13 % es `08`. Lo que **no** se deriva es
		// el 0 % —ahí hay tres códigos y la diferencia es el derecho a crédito—,
		// y por eso los productos sin tarifa nacen sin clasificar, igual que en
		// la base de verdad.
		tax_code: p.tax_rate === 0.01 ? '02' : p.tax_rate === 0.13 ? '08' : null,
		// Un margen aproximado del 30 % hacia atrás, para que el demo tenga un
		// costo de dónde partir (RN-54). Cero sería «no se sabe», que es lo que
		// tiene un catálogo antes de su primera compra, y dejaría la pantalla de
		// compras sin nada con qué comparar.
		cost: round2(p.price / 1.3)
	}));

	// Las cuatro cédulas son de nueve dígitos: física, como las clasificaría la 011.
	const clients: Client[] = CLIENT_SEED.map((c, i) => ({
		...c,
		id_client: i + 1,
		identification_type: '01'
	}));

	/*
	 * Dos compañías (T-228). La segunda nace **vacía**, que es exactamente lo que
	 * pasa cuando se da de alta una: sin catálogo, sin clientes, sin ventas.
	 *
	 * No es un adorno del demo. Es lo que permite que las pruebas de punta a
	 * punta recorran la pantalla de selección y comprueben que cambiar de
	 * compañía deja la pantalla de ventas vacía (T-223) —con una sola compañía
	 * no hay nada de eso que probar—.
	 *
	 * El administrador pertenece a las dos; los cajeros, solo a la primera. Así
	 * el demo muestra los dos caminos: con varias compañías se elige (RF-27) y
	 * con una sola se entra directo (RN-25).
	 */
	const raizNueva: MockRoot = {
		seed_version: SEED_VERSION,
		persons,
		users,
		companies: [
			{
				id: 1,
				afiliado: 1,
				compania: 1,
				nombre: 'Abastecedor La Esquina',
				estado: 'activa',
				branch_code: '001',
				terminal_code: '00001',
				locale: 'es',
				document_locale: 'es',
				plan_id: 2,
				// Un mes por delante: el demo no arranca con un aviso de pago encima,
				// que sería lo primero que se ve al entrar.
				vence_el: enDias(30),
				identificacion: '3101234567',
				identification_type: '02',
				creada_el: created
			},
			{
				id: 2,
				afiliado: 1,
				compania: 2,
				nombre: 'La Esquina · Sucursal Norte',
				estado: 'prueba',
				branch_code: '001',
				terminal_code: '00001',
				locale: 'es',
				document_locale: 'es',
				plan_id: 1,
				/*
				 * La segunda nace **en prueba y por vencer**, a propósito.
				 *
				 * Es lo que hace que el aviso de RF-11 se pueda ver en el demo sin
				 * configurar nada, y lo que le da a la prueba de punta a punta un caso
				 * donde mirar. La primera queda al día, que es el estado normal.
				 */
				vence_el: enDias(4),
				identificacion: null,
				creada_el: created
			}
		],
		memberships: [
			{ user_id: 1, company_id: 1, rol: 'admin', activa: true, aceptada_el: created },
			{ user_id: 1, company_id: 2, rol: 'admin', activa: true, aceptada_el: created },
			{ user_id: 2, company_id: 1, rol: 'cajero', activa: true, aceptada_el: created },
			{ user_id: 3, company_id: 1, rol: 'cajero', activa: true, aceptada_el: created }
		],
		plans: PLAN_SEED.map((plan) => ({ ...plan })),
		// La bitácora arranca vacía: lo que hay que ver en el demo es lo que se hace
		// durante el demo. Una sembrada con líneas inventadas se confunde con las de
		// verdad justo cuando se está probando el filtro.
		audit: [],
		empresas: {
			1: {
				clients,
				categories: [...CATEGORIES],
				products,
				sales: [],
				returns: [],
				cash_sessions: [],
				cash_movements: [],
				stock_entries: [],
				suppliers: [...SUPPLIERS],
				supplier_payments: [],
				// El libro arranca vacío incluso en la compañía con datos: la
				// contabilidad se activa (RF-47) y la fecha de arranque manda
				// (RN-60). Sembrar asientos de ventas anteriores a esa fecha sería
				// justo lo que el sistema de verdad se niega a hacer.
				accounts: [],
				account_mappings: [],
				accounting_periods: [],
				journal_entries: [],
				journal_lines: [],
				/*
				 * Con correo y ubicación de emisor (T-722): la facturación sigue
				 * apagada, pero se puede encender sin llenar nada, que es lo que las
				 * pruebas de punta a punta de comprobantes necesitan.
				 */
				settings: {
					data: {
						business: {
							email: 'facturas@laesquina.cr',
							location: {
								province: '1',
								canton: '18',
								district: '01',
								neighborhood: '',
								otherSigns: '200 m sur del parque de Curridabat'
							}
						}
					},
					logo: null,
					updated_at: null,
					updated_by: null
				},
				// La planilla de muestra (T-1214): dos empleados con contrato y
				// ninguna corrida, que es como se encuentra una compañía que acaba
				// de cargar su gente y todavía no ha pagado nada desde acá.
				payroll: planillaDemo(),
				// Sin certificado, igual que el libro. La factura electrónica se
				// configura (F6) y sembrar un certificado sería sembrar uno que no
				// existe: la pantalla nace teniendo que decir qué falta.
				fe_credentials: [],
				branches: [{ id: 1, codigo: '001', nombre: 'Casa matriz', activa: true }],
				terminals: [
					{ id: 1, branch_id: 1, codigo: '00001', nombre: 'Caja 1', activa: true }
				],
				// F15: los motivos del 1 al 6 y la apertura de cada producto con
				// existencia, que es lo que explica el kárdex del demo.
				stock_reasons: motivosDeFabrica(1),
				stock_exits: [],
				stock_movements: aperturasDe(products),
				stock_counts: []
			},
			2: empresaVacia(motivosDeFabrica(7))
		},
		counters: {
			persons: persons.length,
			users: users.length,
			clients: clients.length,
			categories: CATEGORIES.length,
			products: products.length,
			sales: 0,
			returns: 0,
			cash_sessions: 0,
			cash_movements: 0,
			stock_entries: 0,
			suppliers: SUPPLIERS.length,
			supplier_payments: 0,
			payroll_schedules: 2,
			payroll_positions: 2,
			payroll_policies: 1,
			payroll_employees: 2,
			payroll_contracts: 2,
			accounts: 0,
			account_mappings: 0,
			accounting_periods: 0,
			journal_entries: 0,
			journal_lines: 0,
			audit: 0,
			companies: 2,
			plans: PLAN_SEED.length,
			// En 1 porque `empresaVacia` siembra la sucursal y la caja con ese id;
			// en 0, la primera que se cree desde la pantalla nacería repetida.
			branches: 1,
			terminals: 1,
			// F15: seis motivos por compañía sembrada, y una apertura por producto
			// con existencia.
			stock_reasons: 12,
			stock_exits: 0,
			stock_movements: products.filter((p) => p.stock > 0).length,
			stock_counts: 0
		}
	};

	// El historial de abajo se escribe sobre la compañía con datos.
	const state = { ...raizNueva, ...raizNueva.empresas[1] } as MockDb;

	// Historial de 45 días para que el dashboard tenga de dónde graficar.
	let saleId = 0;
	for (let day = 45; day >= 0; day--) {
		const date = daysAgo(day);
		const isWeekend = date.getDay() === 0 || date.getDay() === 6;
		const salesToday = Math.floor((isWeekend ? 9 : 5) + Math.random() * (isWeekend ? 10 : 8));

		for (let s = 0; s < salesToday; s++) {
			const at = new Date(date);
			at.setHours(8 + Math.floor(Math.random() * 12), Math.floor(Math.random() * 60), 0, 0);
			if (at > now) continue;

			const lineCount = 1 + Math.floor(Math.random() * 5);
			const chosen = new Map<number, number>();
			for (let l = 0; l < lineCount; l++) {
				const product = products[Math.floor(Math.random() * products.length)];
				chosen.set(product.id_product, (chosen.get(product.id_product) ?? 0) + 1 + Math.floor(Math.random() * 3));
			}

			const items: SaleItem[] = [...chosen.entries()].map(([id, quantity]) => {
				const product = products.find((p) => p.id_product === id)!;
				return {
					id_product: product.id_product,
					name: product.name,
					quantity,
					price: product.price,
					subtotal: round2(product.price * quantity),
					cabys_code: product.cabys_code ?? null,
					unit_of_measure: 'Unid'
				};
			});

			const subtotal = round2(items.reduce((acc, i) => acc + i.subtotal, 0));
			const tax = round2(subtotal * DEFAULT_TAX_RATE);
			const total = round2(subtotal + tax);
			const paymentMethod = PAYMENT_MIX[Math.floor(Math.random() * PAYMENT_MIX.length)];
			const cashReceived =
				paymentMethod === 'Efectivo' ? Math.ceil(total / 1000) * 1000 : total;

			saleId += 1;
			const stamp = at
				.toISOString()
				.replace(/[-:TZ.]/g, '')
				.slice(0, 14);

			state.sales.push({
				id: saleId,
				sale_number: stamp,
				client_id: Math.random() < 0.35 ? clients[Math.floor(Math.random() * clients.length)].id_client : null,
				user_id: users[1 + Math.floor(Math.random() * 2)].id_user,
				subtotal,
				tax,
				total,
				payment_method: paymentMethod,
				cash_received: cashReceived,
				change_given: round2(cashReceived - total),
				created_at: iso(at),
				items
			});
		}
	}

	state.sales.sort((a, b) => a.created_at.localeCompare(b.created_at));
	state.sales.forEach((sale, index) => {
		sale.id = index + 1;
	});
	state.counters.sales = state.sales.length;

	return raizNueva;
}
