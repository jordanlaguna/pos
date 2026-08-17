import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import type {
	CashMovement,
	CashSession,
	Category,
	Client,
	Person,
	Product,
	Role,
	SaleItem,
	SaleReturn,
	StockEntry
} from '$lib/domain/types';
import { DEFAULT_TAX_RATE, round2 } from '$lib/domain/money';

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
	cash_sessions: CashSession[];
	cash_movements: CashMovement[];
	stock_entries: StockEntry[];
	settings?: MockSettings;
}

/**
 * Lo global: la identidad y las membresías, que no son de ninguna compañía.
 *
 * Es la misma división que en la base de verdad —`users` y `persons` son
 * identidad (RN-3)— y no una simplificación del mock.
 */
export interface MockRoot {
	persons: Person[];
	users: MockUser[];
	companies: MockCompany[];
	memberships: MockMembership[];
	empresas: Record<number, MockCompanyData>;
	counters: Record<string, number>;
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

const DB_PATH = resolve(process.cwd(), '.data', 'mock-db.json');

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

function cargar(): MockRoot {
	if (raiz) return raiz;

	if (existsSync(DB_PATH)) {
		try {
			const parsed = JSON.parse(readFileSync(DB_PATH, 'utf-8')) as MockRoot;
			// Si el archivo quedó de una versión anterior del seed, se descarta.
			if (parsed && parsed.empresas && parsed.counters && Array.isArray(parsed.users)) {
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

export function empresaVacia(): MockCompanyData {
	return {
		clients: [],
		categories: [],
		products: [],
		sales: [],
		returns: [],
		cash_sessions: [],
		cash_movements: [],
		stock_entries: [],
		settings: { data: {}, logo: null, updated_at: null, updated_by: null }
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

function daysAgo(days: number, hour = 12, minute = 0): Date {
	const d = new Date();
	d.setDate(d.getDate() - days);
	d.setHours(hour, minute, 0, 0);
	return d;
}

// ------------------------------------------------------------------ datos base

const CATEGORIES: Category[] = [
	{ id: 1, name: 'Abarrotes' },
	{ id: 2, name: 'Bebidas' },
	{ id: 3, name: 'Lácteos' },
	{ id: 4, name: 'Panadería' },
	{ id: 5, name: 'Limpieza' },
	{ id: 6, name: 'Snacks' }
];

const PRODUCT_SEED: Omit<Product, 'id_product' | 'created_at'>[] = [
	{ name: 'Arroz Tío Pelón 1kg', description: 'Arroz blanco 80% grano entero', price: 1450, stock: 120, barcode: '7441000100015', category_id: 1 },
	{ name: 'Frijoles negros 900g', description: 'Frijol negro seleccionado', price: 1690, stock: 84, barcode: '7441000100022', category_id: 1 },
	{ name: 'Aceite Sabemas 900ml', description: 'Aceite vegetal de girasol', price: 2350, stock: 46, barcode: '7441000100039', category_id: 1 },
	{ name: 'Azúcar Doña María 1kg', description: 'Azúcar blanca refinada', price: 1250, stock: 95, barcode: '7441000100046', category_id: 1 },
	{ name: 'Sal Sol 1kg', description: 'Sal refinada yodada', price: 620, stock: 140, barcode: '7441000100053', category_id: 1 },
	{ name: 'Pasta espagueti 400g', description: 'Pasta de sémola de trigo', price: 890, stock: 72, barcode: '7441000100060', category_id: 1 },
	{ name: 'Café 1820 500g', description: 'Café molido tueste medio', price: 4250, stock: 38, barcode: '7441000200014', category_id: 2 },
	{ name: 'Coca-Cola 2L', description: 'Refresco de cola', price: 1790, stock: 64, barcode: '7441000200021', category_id: 2 },
	{ name: 'Agua Cristal 600ml', description: 'Agua purificada sin gas', price: 690, stock: 180, barcode: '7441000200038', category_id: 2 },
	{ name: 'Jugo Del Valle 1L', description: 'Néctar de naranja', price: 1390, stock: 52, barcode: '7441000200045', category_id: 2 },
	{ name: 'Cerveza Imperial 350ml', description: 'Cerveza lager, lata', price: 1150, stock: 96, barcode: '7441000200052', category_id: 2 },
	{ name: 'Té helado Lipton 500ml', description: 'Té negro con limón', price: 950, stock: 7, barcode: '7441000200069', category_id: 2 },
	{ name: 'Leche Dos Pinos 1L', description: 'Leche entera UHT', price: 1290, stock: 58, barcode: '7441000300013', category_id: 3 },
	{ name: 'Queso Turrialba 400g', description: 'Queso fresco artesanal', price: 3450, stock: 22, barcode: '7441000300020', category_id: 3 },
	{ name: 'Yogurt natural 1kg', description: 'Yogurt sin azúcar añadida', price: 2290, stock: 31, barcode: '7441000300037', category_id: 3 },
	{ name: 'Natilla Dos Pinos 200g', description: 'Crema agria', price: 1180, stock: 9, barcode: '7441000300044', category_id: 3 },
	{ name: 'Pan cuadrado Bimbo', description: 'Pan blanco de molde 680g', price: 1850, stock: 40, barcode: '7441000400012', category_id: 4 },
	{ name: 'Tortillas de maíz 20u', description: 'Tortilla de maíz nixtamalizado', price: 1090, stock: 55, barcode: '7441000400029', category_id: 4 },
	{ name: 'Pan dulce surtido', description: 'Bolsa de 6 unidades', price: 1650, stock: 18, barcode: '7441000400036', category_id: 4 },
	{ name: 'Detergente Irex 1kg', description: 'Detergente en polvo multiusos', price: 2790, stock: 44, barcode: '7441000500011', category_id: 5 },
	{ name: 'Jabón de baño Protex', description: 'Jabón antibacterial 110g', price: 890, stock: 76, barcode: '7441000500028', category_id: 5 },
	{ name: 'Papel higiénico Scott 4u', description: 'Papel higiénico doble hoja', price: 2450, stock: 5, barcode: '7441000500035', category_id: 5 },
	{ name: 'Cloro Magia Blanca 1L', description: 'Blanqueador desinfectante', price: 1120, stock: 62, barcode: '7441000500042', category_id: 5 },
	{ name: 'Galletas Chiky 12u', description: 'Galleta con chispas de chocolate', price: 1590, stock: 68, barcode: '7441000600010', category_id: 6 },
	{ name: 'Tostitos original 200g', description: 'Tortilla chips de maíz', price: 1950, stock: 34, barcode: '7441000600027', category_id: 6 },
	{ name: 'Maní salado 150g', description: 'Maní tostado con sal', price: 1150, stock: 3, barcode: '7441000600034', category_id: 6 }
];

const PERSON_SEED: Omit<Person, 'id_person' | 'id_user'>[] = [
	{ birth_date: '1990-04-12', identification: '113450678', name: 'Jordan', lastName: 'Laguna', secondName: 'Mora', telephone: '88451230', email: 'admin@ventasys.cr' },
	{ birth_date: '1996-11-03', identification: '118920345', name: 'María', lastName: 'Rojas', secondName: 'Vargas', telephone: '87123344', email: 'cajero@ventasys.cr' },
	{ birth_date: '1988-07-25', identification: '109887654', name: 'Carlos', lastName: 'Jiménez', secondName: 'Solano', telephone: '89905512', email: 'carlos@ventasys.cr' }
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
		{ id_user: 3, email: 'carlos@ventasys.cr', password: 'cajero123', role: 'cajero', id_person: 3 }
	];

	const products: Product[] = PRODUCT_SEED.map((p, i) => ({
		...p,
		id_product: i + 1,
		created_at: created
	}));

	const clients: Client[] = CLIENT_SEED.map((c, i) => ({ ...c, id_client: i + 1 }));

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
				terminal_code: '00001'
			},
			{
				id: 2,
				afiliado: 1,
				compania: 2,
				nombre: 'La Esquina · Sucursal Norte',
				estado: 'activa',
				branch_code: '001',
				terminal_code: '00001'
			}
		],
		memberships: [
			{ user_id: 1, company_id: 1, rol: 'admin', activa: true, aceptada_el: created },
			{ user_id: 1, company_id: 2, rol: 'admin', activa: true, aceptada_el: created },
			{ user_id: 2, company_id: 1, rol: 'cajero', activa: true, aceptada_el: created },
			{ user_id: 3, company_id: 1, rol: 'cajero', activa: true, aceptada_el: created }
		],
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
				settings: { data: {}, logo: null, updated_at: null, updated_by: null }
			},
			2: empresaVacia()
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
			stock_entries: 0
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
					subtotal: round2(product.price * quantity)
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
