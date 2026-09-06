import { ApiError } from '../api';
import { LOW_STOCK_THRESHOLD } from '../config';
import {
	COMPANIA_DEMO,
	getDb,
	getEmpresa,
	getRoot,
	nextId,
	persist,
	resetDb,
	type MockPlan,
	type MockSale,
	type MockSettings,
	type MockUser
} from './db';
import {
	DEFAULT_TAX_RATE,
	changeDue,
	computeTotals,
	lineTax,
	round2
} from '$lib/domain/money';
import { COMPANY_STATES } from '$lib/domain/types';
import type {
	CashMovement,
	CashSession,
	CashSessionReport,
	Category,
	LowStockProduct,
	PaymentBreakdown,
	Product,
	ReportSummary,
	ReturnItem,
	SaleItem,
	SaleReturn,
	SalesByDay,
	TopProduct
} from '$lib/domain/types';

/**
 * Backend simulado.
 *
 * Reproduce los contratos exactos de `backend-python` (mismas rutas, mismos
 * nombres de campo, mismos códigos de error) más los endpoints que este proyecto
 * añade. Cambiar `POS_MOCK=1` por la URL de la VM no debe requerir tocar una
 * sola línea del frontend.
 */

interface MockRequest {
	method: string;
	path: string;
	body?: unknown;
	token?: string | null;
}

type Handler = (ctx: {
	params: string[];
	query: URLSearchParams;
	body: any;
	userId: number | null;
	/** La compañía del token. Sin token de sesión, la del demo. */
	companyId: number;
	/**
	 * El token tal como llegó.
	 *
	 * Los tres endpoints de `/auth` lo necesitan crudo porque tienen que
	 * funcionar también con el de tránsito, y `userId` devuelve `null` para ese
	 * a propósito: un token de tránsito no autoriza ninguna ruta de negocio
	 * (RN-26).
	 */
	token: string | null | undefined;
}) => unknown;

const routes: { method: string; pattern: RegExp; handler: Handler }[] = [];

function route(method: string, pattern: string, handler: Handler) {
	// `/sales/sale/:id` → captura los segmentos marcados con `:`
	const regex = new RegExp(
		'^' + pattern.replace(/:[a-zA-Z_]+/g, '([^/]+)').replace(/\//g, '\\/') + '$'
	);
	routes.push({ method, pattern: regex, handler });
}

/**
 * Token del mock, con **forma** de JWT.
 *
 * No está firmado —el mock no verifica nada— pero tiene las tres partes
 * separadas por puntos, y eso importa: `lib/server/auth.ts` lee el payload para
 * saber si el token es de tránsito o de sesión, y lo hace con el mismo código
 * contra el backend de verdad y contra el simulado. Si acá el token tuviera otra
 * forma, ese camino quedaría sin probar justo en el modo en que corren las
 * pruebas de punta a punta.
 */
function makeToken(payload: Record<string, unknown>): string {
	const cuerpo = Buffer.from(JSON.stringify(payload)).toString('base64url');
	return `mock.${cuerpo}.sinfirma`;
}

function tokenPayload(token: string | null | undefined): Record<string, unknown> | null {
	if (!token || !token.startsWith('mock.')) return null;
	const partes = token.split('.');
	if (partes.length !== 3) return null;
	try {
		return JSON.parse(Buffer.from(partes[1], 'base64url').toString('utf-8'));
	} catch {
		return null;
	}
}

/**
 * La compañía del token de sesión, o la del demo si no hay token.
 *
 * Sin token la respuesta no importa —esas rutas no leen datos de negocio— pero
 * devolver la del demo mantiene el mock utilizable desde un guion suelto.
 */
function companyOf(token: string | null | undefined): number {
	const payload = tokenPayload(token);
	const cid = payload?.cid;
	return typeof cid === 'number' ? cid : COMPANIA_DEMO;
}

/**
 * El usuario del token, **solo si el token es de sesión**.
 *
 * Un token de tránsito devuelve null y por lo tanto 401 en toda ruta de negocio,
 * igual que en el backend real (RN-26).
 */
function readToken(token: string | null | undefined): number | null {
	const payload = tokenPayload(token);
	// El de tránsito y el de soporte no abren ninguna ruta de negocio: el primero
	// porque todavía no eligió compañía (RN-26) y el segundo porque no tiene
	// ninguna (RN-4). El de suplantación sí: es soporte mirando desde adentro.
	if (!payload || payload.tipo === 'transito' || payload.tipo === 'soporte') return null;
	return typeof payload.id_user === 'number' ? payload.id_user : null;
}

/**
 * Un «no» del backend simulado, en código y datos, igual que el de verdad.
 *
 * El simulado no escribe frases por la misma razón que el backend (RN-30): la
 * frase la arma el POS con su catálogo. Y tiene que devolver **el mismo código**
 * que FastAPI para la misma situación: si no, el modo simulado probaría una
 * aplicación distinta de la que se despliega.
 */
function fail(status: number, code: string, data: Record<string, unknown> = {}): never {
	throw new ApiError(status, code, data);
}

function nowIso(): string {
	return new Date().toISOString();
}

function personName(idUser: number | null): string | null {
	if (idUser == null) return null;
	// Identidad, no negocio: no depende de ninguna compañía.
	const db = getRoot();
	const user = db.users.find((u) => u.id_user === idUser);
	if (!user) return null;
	const person = db.persons.find((p) => p.id_person === user.id_person);
	return person ? `${person.name} ${person.lastName}`.trim() : user.email;
}

/** Producto en el formato de ProductResponse. */
function productResponse(id: number, companyId: number) {
	const product = getDb(companyId).products.find((p) => p.id_product === id);
	return product ?? null;
}

// ------------------------------------------------------------------- usuarios

// ----------------------------------------------------------- entrar (F2)
//
// El modo simulado representa **una** compañía: afiliado 1, compañía 1. Es
// deliberado y tiene consecuencia: como solo hay una disponible, el login
// devuelve la sesión directa y la pantalla de selección no aparece nunca
// (RN-25). Ese es el camino que recorre la mayoría de los negocios.
//
// Lo que el mock NO simula es el aislamiento entre compañías: no hay dos juegos
// de datos que separar. Eso se verifica contra el stack de verdad, en
// `backend/tests/test_aislamiento.py`, que es donde se puede verificar de veras.

/**
 * Las compañías a las que puede entrar una persona, con su rol en cada una.
 *
 * Sale de `memberships`, igual que en el backend de verdad: el rol es de la
 * membresía y no de la persona, así que la misma cuenta puede ser
 * administradora en una compañía y cajera en otra (RN-3).
 */
function opcionesDe(userId: number) {
	const root = getRoot();
	return root.memberships
		.filter((m) => m.user_id === userId && m.activa)
		.map((m) => {
			const empresa = root.companies.find((c) => c.id === m.company_id)!;
			const pendiente = m.aceptada_el === null;
			return {
				id: empresa.id,
				afiliado: empresa.afiliado,
				compania: empresa.compania,
				nombre: empresa.nombre,
				estado: empresa.estado,
				rol: m.rol,
				puede_entrar: !pendiente,
				motivo: pendiente ? 'invitacion_pendiente' : null,
				pendiente
			};
		});
}

function rolEn(userId: number, companyId: number): string | null {
	const m = getRoot().memberships.find(
		(x) => x.user_id === userId && x.company_id === companyId && x.activa && x.aceptada_el
	);
	return m ? m.rol : null;
}

/** Los idiomas con catálogo. La misma lista que `app/domain/locale.py`. */
const IDIOMAS = ['es', 'en', 'pt'];

/**
 * El idioma de la sesión, con la misma regla que el backend (T-809).
 *
 * Es la traducción a TypeScript de `app/domain/locale.py`: lo de la persona, si
 * no lo de la compañía, si no español. Está duplicada a propósito —el simulado
 * es una reimplementación del backend, no una capa que lo llame— y por eso el
 * contrato tiene que decir lo mismo: si acá el token no trajera `loc`, el modo
 * simulado probaría una aplicación distinta de la que se despliega.
 */
function idiomaDeSesion(userId: number, companyId: number): string {
	const raiz = getRoot();
	const user = raiz.users.find((u) => u.id_user === userId);
	const company = raiz.companies.find((c) => c.id === companyId);
	return user?.locale || company?.locale || 'es';
}

function tokenDeSesion(user: { id_user: number; email: string }, companyId: number, rol: string) {
	return makeToken({
		id_user: user.id_user,
		email: user.email,
		cid: companyId,
		bid: 1,
		tid: 1,
		rol,
		loc: idiomaDeSesion(user.id_user, companyId),
		tipo: 'sesion'
	});
}

/**
 * El token del panel de soporte: **sin compañía** (RN-4).
 *
 * Es todo el diseño. Sin `cid`, ninguna ruta de negocio le responde, ni en el
 * simulado ni contra el backend de verdad.
 */
function tokenDeSoporte(user: MockUser) {
	return makeToken({
		id_user: user.id_user,
		email: user.email,
		loc: user.locale || 'es',
		tipo: 'soporte'
	});
}

/** El token de una visita: la compañía destino, el motivo y media hora. */
function tokenDeSuplantacion(user: MockUser, companyId: number, motivo: string) {
	const empresa = getRoot().companies.find((c) => c.id === companyId);
	return makeToken({
		id_user: user.id_user,
		email: user.email,
		cid: companyId,
		bid: 1,
		tid: 1,
		loc: user.locale || empresa?.locale || 'es',
		mot: motivo.slice(0, 120),
		tipo: 'suplantacion',
		// El simulado no vence tokens: no hay reloj que los invalide. La media hora
		// viaja como dato para que la pantalla pueda decirla, que es lo único que
		// se puede comprobar de este lado.
		minutos: MINUTOS_DE_VISITA
	});
}

const MINUTOS_DE_VISITA = 30;

/**
 * Los cinco estados, tomados del dominio y no escritos otra vez.
 *
 * `COMPANY_STATES` es una tupla de literales y acá se compara contra un `string`
 * que llega del cuerpo de la peticion, así que se ensancha el tipo a proposito:
 * lo que se quiere comprobar es «esto que llegó está en la lista», no «esto es
 * uno de estos cinco», que es justo lo que todavía no se sabe.
 */
const ESTADOS_DE_SUSCRIPCION: readonly string[] = COMPANY_STATES;

/** Anota en la bitácora. Igual que `crud_membership.registrar` (RF-9). */
function registrar(
	userId: number,
	companyId: number | null,
	accion: string,
	detalle: string | null
): void {
	const raiz = getRoot();
	raiz.audit.push({
		id: nextId('audit'),
		creado_el: nowIso(),
		user_id: userId,
		company_id: companyId,
		accion,
		detalle,
		// El simulado no ve la IP: el POS habla con él dentro del mismo proceso.
		ip: null
	});
	persist();
}

/**
 * El estado de la suscripción, con la misma regla que el backend (T-308).
 *
 * Es la traducción a TypeScript de `app/domain/subscription.py`, y está duplicada
 * a propósito por lo mismo que `idiomaDeSesion`: el simulado es una
 * reimplementación del backend, no una capa que lo llame. Si acá la gracia
 * durara ocho días, el modo simulado probaría una aplicación distinta de la que
 * se despliega.
 */
const DIAS_DE_GRACIA = 7;
const DIAS_DE_AVISO = 7;

function evaluarSuscripcion(companyId: number, rol = 'admin') {
	const empresa = getRoot().companies.find((c) => c.id === companyId);
	if (!empresa) return null;

	const guardado = empresa.estado;
	const vence = empresa.vence_el ?? null;
	const dias = vence === null ? null : diasHasta(vence);

	const estado =
		(guardado === 'prueba' || guardado === 'activa') && dias !== null && dias < 0
			? 'vencida'
			: guardado;

	const gracia =
		estado === 'vencida' && dias !== null
			? Math.max(0, Math.min(DIAS_DE_GRACIA, DIAS_DE_GRACIA + dias + 1))
			: 0;

	const puedeEntrar =
		estado === 'suspendida' ? rol === 'admin' : ['prueba', 'activa', 'vencida'].includes(estado);
	const puedeVender =
		estado === 'prueba' || estado === 'activa' || (estado === 'vencida' && gracia > 0);

	return {
		estado,
		guardado,
		vence_el: vence,
		dias,
		gracia,
		puede_entrar: puedeEntrar,
		puede_vender: puedeVender,
		aviso: avisoDe(estado, guardado, dias, gracia)
	};
}

function diasHasta(fecha: string): number {
	// A medianoche los dos, para que la cuenta sea de días y no de horas.
	const hoy = new Date();
	hoy.setHours(0, 0, 0, 0);
	const objetivo = new Date(`${fecha}T00:00:00`);
	return Math.round((objetivo.getTime() - hoy.getTime()) / 86_400_000);
}

function avisoDe(
	estado: string,
	guardado: string,
	dias: number | null,
	gracia: number
): string | null {
	if (estado === 'cancelada') return 'cancelada';
	if (estado === 'suspendida') return 'suspendida';
	if (estado === 'vencida') return gracia > 0 ? 'en_gracia' : 'solo_lectura';
	if (dias !== null && dias <= DIAS_DE_AVISO) return 'vence_pronto';
	if (guardado === 'prueba') return 'en_prueba';
	return null;
}

route('POST', '/auth/login', ({ body }) => {
	const email = String(body?.email ?? '')
		.trim()
		.toLowerCase();
	const password = String(body?.password ?? '');
	const user = getRoot().users.find((u) => u.email.toLowerCase() === email);
	if (!user || user.password !== password) fail(401, 'invalid_credentials');

	/*
	 * Soporte no elige compañía porque no tiene ninguna (RN-4).
	 *
	 * Se decide antes de mirar las membresías y no después: su lista está vacía,
	 * así que el camino normal le diría «no tiene ninguna compañía disponible», que
	 * es cierto y no es lo que hay que hacer con él.
	 */
	if (user.is_support) {
		registrar(user.id_user, null, 'login_soporte', null);
		return {
			access_token: tokenDeSoporte(user),
			token_type: 'bearer',
			tipo: 'soporte',
			user_id: user.id_user,
			companies: []
		};
	}

	const opciones = opcionesDe(user.id_user);
	const disponibles = opciones.filter((o) => o.puede_entrar);

	// Una sola disponible: se entra sin pantalla intermedia (RN-25). Es el caso
	// de los cajeros del demo, que pertenecen solo a la primera compañía.
	if (disponibles.length === 1) {
		registrar(user.id_user, disponibles[0].id, 'login', 'compañía única');
		return {
			access_token: tokenDeSesion(user, disponibles[0].id, disponibles[0].rol),
			token_type: 'bearer',
			tipo: 'sesion',
			user_id: user.id_user,
			company_id: disponibles[0].id,
			companies: opciones
		};
	}

	registrar(
		user.id_user,
		null,
		'login',
		`tránsito, ${disponibles.length} disponibles de ${opciones.length}`
	);
	return {
		access_token: makeToken({ id_user: user.id_user, email: user.email, tipo: 'transito' }),
		token_type: 'bearer',
		tipo: 'transito',
		user_id: user.id_user,
		companies: opciones
	};
});

route('GET', '/auth/companies', ({ token }) => {
	const payload = tokenPayload(token);
	const userId = typeof payload?.id_user === 'number' ? payload.id_user : null;
	if (userId == null) fail(401, 'unauthorized');
	return opcionesDe(userId);
});

route('POST', '/auth/invitation', ({ token }) => {
	const payload = tokenPayload(token);
	if (typeof payload?.id_user !== 'number') fail(401, 'unauthorized');
	// El demo no tiene invitaciones pendientes: sus dos compañías son del mismo
	// dueño. La ruta existe para que el contrato esté completo.
	fail(404, 'membership_not_found');
});

route('POST', '/auth/company', ({ body, token }) => {
	const payload = tokenPayload(token);
	const userId = typeof payload?.id_user === 'number' ? payload.id_user : null;
	if (userId == null) fail(401, 'unauthorized');

	const user = getRoot().users.find((u) => u.id_user === userId);
	const elegida = Number(body?.company_id);
	const rol = user ? rolEn(user.id_user, elegida) : null;
	// 404 y no 403: un 403 confirmaría que esa compañía existe.
	if (!user || !rol) fail(404, 'membership_not_found');

	registrar(user.id_user, elegida, 'elegir_compania', `rol ${rol}`);
	return {
		access_token: tokenDeSesion(user, elegida, rol),
		token_type: 'bearer',
		tipo: 'sesion',
		user_id: user.id_user,
		company_id: elegida,
		rol
	};
});

route('GET', '/users/me', ({ userId, companyId, token }) => {
	if (userId == null) fail(401, 'unauthorized');
	const root = getRoot();
	const user = root.users.find((u) => u.id_user === userId);
	if (!user) fail(404, 'user_not_found');
	const empresa = root.companies.find((c) => c.id === companyId);

	// Si esto es una visita de soporte, el POS necesita saberlo en **cada**
	// petición: la franja permanente se pinta con esto (RF-8).
	const payload = tokenPayload(token);
	const suplantada = payload?.tipo === 'suplantacion';

	return {
		id_user: user.id_user,
		email: user.email,
		id_person: user.id_person,
		role: rolEn(user.id_user, companyId) ?? user.role,
		name: personName(user.id_user) ?? user.email,
		company_id: companyId,
		company_name: empresa?.nombre ?? null,
		branch_code: empresa?.branch_code ?? null,
		terminal_code: empresa?.terminal_code ?? null,
		companies_available: suplantada
			? 0
			: opcionesDe(user.id_user).filter((o) => o.puede_entrar).length,
		locale: user.locale || empresa?.locale || 'es',
		user_locale: user.locale ?? null,
		company_locale: empresa?.locale || 'es',
		document_locale: empresa?.document_locale || 'es',
		subscription: evaluarSuscripcion(companyId, rolEn(user.id_user, companyId) ?? 'admin'),
		impersonated_by: suplantada ? user.email : null,
		impersonation_reason: suplantada && typeof payload?.mot === 'string' ? payload.mot : null
	};
});

route('POST', '/users/membership', ({ body, userId, companyId }) => {
	if (userId == null) fail(401, 'unauthorized');
	const db = getDb(companyId);
	const actor = db.users.find((u) => u.id_user === userId);
	if (actor?.role !== 'admin') fail(403, 'admin_only');

	const email = String(body?.email ?? '').trim().toLowerCase();
	const user = db.users.find((u) => u.email.toLowerCase() === email);
	if (!user) fail(404, 'account_not_found');

	// Con una sola compañía, dar de alta es confirmar el rol.
	const role = body?.role === 'admin' ? 'admin' : 'cajero';
	user.role = role;
	persist();
	return {
		id_user: user.id_user,
		email: user.email,
		id_person: user.id_person,
		role,
		name: personName(user.id_user) ?? user.email
	};
});

route('GET', '/users/', ({ companyId }) =>
	getDb(companyId).users.map((u) => ({
		id_user: u.id_user,
		email: u.email,
		id_person: u.id_person,
		role: u.role,
		name: personName(u.id_user) ?? u.email
	}))
);

route('PUT', '/users/role/:id', ({ params, body, companyId }) => {
	const db = getDb(companyId);
	const id = Number(params[0]);
	const user = db.users.find((u) => u.id_user === id);
	if (!user) fail(404, 'user_not_found');
	const role = String(body?.role ?? '');
	if (role !== 'admin' && role !== 'cajero') fail(400, 'invalid_role', { role });
	// El último admin no puede degradarse: dejaría el sistema sin quien administre.
	if (user.role === 'admin' && role !== 'admin') {
		const admins = db.users.filter((u) => u.role === 'admin').length;
		if (admins <= 1) fail(400, 'last_admin');
	}
	user.role = role;
	persist();
	return { message: 'role_updated', id_user: id };
});

// ------------------------------------------------------------------- personas

route('POST', '/persons/register', ({ body, companyId }) => {
	const db = getDb(companyId);
	const identification = String(body?.identification ?? '').trim();
	const email = String(body?.email ?? '').trim();
	if (db.persons.some((p) => p.identification === identification))
		fail(400, 'person_identification_taken');
	if (db.users.some((u) => u.email.toLowerCase() === email.toLowerCase()))
		fail(400, 'email_taken');

	const idPerson = nextId('persons');
	const idUser = nextId('users');
	db.persons.push({
		id_person: idPerson,
		birth_date: String(body?.birth_date ?? ''),
		identification,
		name: String(body?.name ?? ''),
		lastName: String(body?.lastName ?? ''),
		secondName: String(body?.secondName ?? ''),
		telephone: String(body?.telephone ?? ''),
		id_user: idUser,
		email
	});
	// El primer usuario del sistema es admin; los demás entran como cajero.
	db.users.push({
		id_user: idUser,
		email,
		password: String(body?.password ?? ''),
		role: db.users.length === 0 ? 'admin' : 'cajero',
		id_person: idPerson
	});
	persist();
	return { message: 'person_registered', id_user: idUser, id_person: idPerson };
});

route('GET', '/persons/persons_list', ({ companyId }) => {
	const db = getDb(companyId);
	return db.persons.map((p) => {
		const user = db.users.find((u) => u.id_person === p.id_person);
		return { ...p, id_user: user?.id_user ?? p.id_user, email: user?.email ?? p.email, role: user?.role ?? 'cajero' };
	});
});

route('PUT', '/persons/update/:id', ({ params, body, companyId }) => {
	const db = getDb(companyId);
	const id = Number(params[0]);
	const person = db.persons.find((p) => p.id_person === id);
	if (!person) fail(404, 'person_not_found');
	const user = db.users.find((u) => u.id_person === id);

	for (const key of ['birth_date', 'identification', 'name', 'lastName', 'secondName', 'telephone'] as const) {
		if (body?.[key] != null && body[key] !== '') (person as any)[key] = String(body[key]);
	}
	if (body?.email) {
		const taken = db.users.some(
			(u) => u.id_person !== id && u.email.toLowerCase() === String(body.email).toLowerCase()
		);
		if (taken) fail(400, 'email_taken');
		person.email = String(body.email);
		if (user) user.email = String(body.email);
	}
	persist();
	return { message: 'person_updated', id_person: id };
});

// ------------------------------------------------------------------- clientes

route('GET', '/clients/clients_list', ({ companyId }) => getDb(companyId).clients);

route('POST', '/clients/register_client', ({ body, companyId }) => {
	const db = getDb(companyId);
	const identification = String(body?.identification ?? '').trim();
	if (db.clients.some((c) => c.identification === identification))
		fail(400, 'client_identification_taken');
	const id = nextId('clients');
	db.clients.push({
		id_client: id,
		identification,
		name: String(body?.name ?? ''),
		last_name: String(body?.last_name ?? ''),
		second_name: String(body?.second_name ?? ''),
		email: String(body?.email ?? ''),
		telephone: Number(body?.telephone ?? 0),
		address: String(body?.address ?? ''),
		register_date: String(body?.register_date ?? nowIso().slice(0, 10))
	});
	persist();
	return { message: 'client_registered', id_client: id };
});

route('PUT', '/clients/update_client/:id', ({ params, body, companyId }) => {
	const db = getDb(companyId);
	const id = Number(params[0]);
	const client = db.clients.find((c) => c.id_client === id);
	if (!client) fail(404, 'client_not_found');
	for (const [key, value] of Object.entries(body ?? {})) {
		if (value == null || value === '') continue;
		if (key === 'telephone') client.telephone = Number(value);
		else if (key in client) (client as any)[key] = value;
	}
	persist();
	return { message: 'client_updated', id_client: id };
});

// ------------------------------------------------------------------ productos

/** Columnas donde el nulo **es un valor**. Espejo de `crud_product.VACIABLES`. */
const VACIABLES = new Set(['cabys_code', 'tax_rate']);

route('GET', '/products/products_list', ({ companyId }) => getDb(companyId).products);

route('POST', '/products/add_product', ({ body, companyId }) => {
	const db = getDb(companyId);
	const barcode = String(body?.barcode ?? '').trim();
	if (db.products.some((p) => p.barcode === barcode)) fail(400, 'barcode_taken', { barcode });
	// RN-6: el producto va en la hoja del árbol, y la hoja tiene que estar activa.
	categoriaParaProducto(companyId, Number(body?.category_id ?? 0));
	const id = nextId('products');
	db.products.push({
		id_product: id,
		name: String(body?.name ?? ''),
		description: String(body?.description ?? ''),
		price: round2(Number(body?.price ?? 0)),
		stock: Math.trunc(Number(body?.stock ?? 0)),
		barcode,
		created_at: String(body?.created_at ?? nowIso()),
		category_id: Number(body?.category_id ?? 0),
		// F5: en nulo significa «la tasa configurada del negocio» (RN-9).
		cabys_code: body?.cabys_code != null ? String(body.cabys_code) : null,
		tax_rate: body?.tax_rate != null ? Number(body.tax_rate) : null,
		unit_of_measure: String(body?.unit_of_measure ?? 'Unid')
	});
	persist();
	return { message: 'product_registered', id_product: id };
});

route('PUT', '/products/update_product/:id', ({ params, body, companyId }) => {
	const db = getDb(companyId);
	const id = Number(params[0]);
	const product = db.products.find((p) => p.id_product === id);
	if (!product) fail(404, 'product_not_found', { product_id: id });
	if (body?.barcode && db.products.some((p) => p.id_product !== id && p.barcode === body.barcode))
		fail(400, 'barcode_taken', { barcode: String(body.barcode) });
	// Mover de categoría pasa por la misma regla que crear (RN-6). Solo si de
	// verdad cambia: revalidar la que ya tiene haría que un cambio de precio
	// fallara por una categoría que se desactivó después.
	const categoriaNueva = body?.category_id == null ? null : Number(body.category_id);
	if (categoriaNueva !== null && categoriaNueva !== product.category_id)
		categoriaParaProducto(companyId, categoriaNueva);
	for (const [key, value] of Object.entries(body ?? {})) {
		// En casi todo el formulario un nulo significa «no mandé este campo», que
		// es lo que hace que un PUT parcial no borre el resto. En `VACIABLES` no:
		// ahí el nulo **es** el valor, y sin esa excepción clasificar un producto
		// sería una puerta de una sola dirección (RN-9). Mismo criterio y misma
		// lista que `crud_product.VACIABLES` en el backend.
		if ((value == null || value === '') && !VACIABLES.has(key)) continue;
		if (key === 'price') product.price = round2(Number(value));
		else if (key === 'stock') product.stock = Math.trunc(Number(value));
		else if (key === 'category_id') product.category_id = Number(value);
		else if (key === 'tax_rate') product.tax_rate = value === '' || value == null ? null : Number(value);
		else if (key === 'cabys_code')
			product.cabys_code = value === '' || value == null ? null : String(value);
		else if (key in product) (product as any)[key] = value;
	}
	persist();
	return { message: 'product_updated', id_product: id };
});

/**
 * Asignación de CABYS en lote (RF-20). Todo o nada, como el backend: medio
 * catálogo clasificado es el desorden que esto existe para arreglar.
 */
route('PUT', '/products/assign_cabys', ({ body, companyId }) => {
	const db = getDb(companyId);
	const codigo = String(body?.cabys_code ?? '').trim();
	// Las mismas tres razones que el dominio, y en el mismo orden.
	if (!codigo) fail(400, 'cabys_invalid_code', { value: codigo, reason: 'empty' });
	if (!/^\d+$/.test(codigo)) fail(400, 'cabys_invalid_code', { value: codigo, reason: 'not_digits' });
	if (codigo.length !== 13) fail(400, 'cabys_invalid_code', { value: codigo, reason: 'bad_length' });

	const tarifa = Number(body?.tax_rate);
	if (!Number.isFinite(tarifa) || tarifa < 0 || tarifa > 1)
		fail(400, 'tax_rate_out_of_range', { value: body?.tax_rate });

	const pedidos = [...new Set((body?.product_ids as unknown[]) ?? [])].map(Number);
	const productos = pedidos.map((id) => db.products.find((p) => p.id_product === id));
	const faltante = pedidos.find((id, i) => productos[i] === undefined);
	if (faltante !== undefined) fail(404, 'product_not_found', { product_id: faltante });

	for (const producto of productos) {
		producto!.cabys_code = codigo;
		producto!.tax_rate = tarifa;
	}
	persist();
	return { message: 'cabys_assigned', updated: productos.length };
});

route('DELETE', '/products/delete_product/:id', ({ params, companyId }) => {
	const db = getDb(companyId);
	const id = Number(params[0]);
	const index = db.products.findIndex((p) => p.id_product === id);
	if (index === -1) fail(404, 'product_not_found', { product_id: id });
	// Un producto ya vendido no se borra: rompería el histórico de facturas.
	if (db.sales.some((s) => s.items.some((i) => i.id_product === id)))
		fail(400, 'product_has_sales');
	db.products.splice(index, 1);
	persist();
	return { message: 'product_deleted', id_product: id };
});

/** Búsqueda del escáner: código de barras exacto primero, luego nombre exacto. */
route('GET', '/products/product/:term', ({ params, companyId }) => {
	const term = decodeURIComponent(params[0]).trim();
	const db = getDb(companyId);
	const found =
		db.products.find((p) => p.barcode === term) ??
		db.products.find((p) => p.name.toLowerCase() === term.toLowerCase());
	if (!found) fail(404, 'product_not_found');
	return found;
});

route('GET', '/products/search/:term', ({ params, companyId }) => {
	const term = decodeURIComponent(params[0]).trim().toLowerCase();
	if (!term) return [];
	return getDb(companyId)
		.products.filter(
			(p) => p.name.toLowerCase().includes(term) || p.barcode.includes(term)
		)
		.slice(0, 20);
});

// ----------------------------------------------------------------- categorías
//
// El árbol de dos niveles (F4), con el mismo contrato que FastAPI: los mismos
// códigos de error para las mismas situaciones y el mismo orden en la lista. Las
// reglas viven en `$lib/domain/categories.ts` del lado del POS y en
// `app/domain/categories.py` del lado del servidor; acá está la parte que en el
// backend hace la base.

function categoriaPorId(companyId: number, id: number): Category | undefined {
	return getDb(companyId).categories.find((c) => c.id === id);
}

function hermanas(companyId: number, parentId: number | null): Category[] {
	return getDb(companyId)
		.categories.filter((c) => (c.parent_id ?? null) === parentId)
		.sort((a, b) => a.sort_order - b.sort_order || a.id - b.id);
}

/**
 * El nombre se compara sin tildes ni mayúsculas, como la colación de MySQL.
 *
 * `utf8mb4_0900_ai_ci` ignora las dos cosas, así que «Lácteos» y «lacteos»
 * chocan en la base de verdad. Comparar acá solo con `toLowerCase()` dejaría
 * pasar en el demo un nombre que el servidor rechaza.
 */
function mismoNombre(a: string, b: string): boolean {
	// `sensitivity: 'base'` ignora tildes y mayúsculas, que es exactamente lo que
	// hace la colación de la tabla en MySQL (`utf8mb4_0900_ai_ci`). Comparar solo
	// en minúsculas dejaría pasar en el demo un nombre que el servidor rechaza.
	return a.trim().localeCompare(b.trim(), 'es', { sensitivity: 'base' }) === 0;
}

function nombreTomado(
	companyId: number,
	parentId: number | null,
	name: string,
	excepto?: number
): boolean {
	return hermanas(companyId, parentId).some(
		(c) => c.id !== excepto && mismoNombre(c.name, name)
	);
}

function cuantasHijas(companyId: number, id: number): number {
	return getDb(companyId).categories.filter((c) => c.parent_id === id).length;
}

/**
 * Las hijas que siguen en circulación.
 *
 * Es la cuenta de RN-6 y no la de arriba: una raíz a la que le desactivaron su
 * única subcategoría vuelve a ser una hoja y vuelve a recibir productos. Borrar
 * sí cuenta todas —una hija desactivada sigue siendo una fila—.
 */
function cuantasHijasActivas(companyId: number, id: number): number {
	return getDb(companyId).categories.filter((c) => c.parent_id === id && c.is_active).length;
}

function cuantosProductos(companyId: number, id: number): number {
	return getDb(companyId).products.filter((p) => p.category_id === id).length;
}

/** RN-6: el producto va en la hoja, y la hoja tiene que estar activa. */
function categoriaParaProducto(companyId: number, id: number): Category {
	const categoria = categoriaPorId(companyId, id);
	if (!categoria) fail(404, 'category_not_found', { category_id: id });
	if (!categoria.is_active)
		fail(400, 'category_inactive', { category_id: id, name: categoria.name });
	const hijas = cuantasHijasActivas(companyId, id);
	if (hijas > 0)
		fail(400, 'category_needs_subcategory', {
			category_id: id,
			name: categoria.name,
			children: hijas
		});
	return categoria;
}

/** Primero las raíces y después cada rama junta, igual que el `ORDER BY`. */
function categoriasOrdenadas(companyId: number): Category[] {
	return [...getDb(companyId).categories].sort(
		(a, b) =>
			(a.parent_id ?? 0) - (b.parent_id ?? 0) ||
			a.sort_order - b.sort_order ||
			a.id - b.id
	);
}

route('GET', '/categories/categories_list', ({ companyId }) => categoriasOrdenadas(companyId));

route('POST', '/categories/register_category', ({ body, companyId }) => {
	const db = getDb(companyId);
	const name = String(body?.name ?? '').trim();
	const parentId = body?.parent_id == null ? null : Number(body.parent_id);

	if (parentId !== null) {
		const madre = categoriaPorId(companyId, parentId);
		if (!madre) fail(404, 'category_not_found', { category_id: parentId });
		// RN-5: dos niveles. De una subcategoría no cuelga nada.
		if (madre.parent_id !== null) fail(400, 'category_too_deep', { category_id: parentId });
	}
	if (nombreTomado(companyId, parentId, name)) fail(400, 'category_name_taken', { name });

	const id = nextId('categories');
	const orden = hermanas(companyId, parentId).reduce((max, c) => Math.max(max, c.sort_order), 0);
	db.categories.push({ id, name, parent_id: parentId, sort_order: orden + 1, is_active: true });
	persist();
	return { id, name, parent_id: parentId };
});

route('PUT', '/categories/update_category/:id', ({ params, body, companyId }) => {
	const id = Number(params[0]);
	const categoria = categoriaPorId(companyId, id);
	if (!categoria) fail(404, 'category_not_found', { category_id: id });

	const datos = (body ?? {}) as Record<string, unknown>;
	// `parent_id` ausente es «no se toca» y en nulo es «pasa a raíz», igual que
	// el `model_fields_set` de Pydantic. Sin la diferencia, renombrar una
	// subcategoría la promovería a raíz sin que nadie lo pidiera.
	const pideMadre = 'parent_id' in datos;
	const madreNueva = pideMadre && datos.parent_id != null ? Number(datos.parent_id) : null;
	const seMueve = pideMadre && madreNueva !== categoria.parent_id;
	const destino = seMueve ? madreNueva : categoria.parent_id;
	const nombre = typeof datos.name === 'string' && datos.name.trim() ? datos.name.trim() : categoria.name;

	if (seMueve) {
		if (madreNueva === id) fail(400, 'category_self_parent', { category_id: id });
		if (madreNueva !== null) {
			const madre = categoriaPorId(companyId, madreNueva);
			if (!madre) fail(404, 'category_not_found', { category_id: madreNueva });
			if (madre.parent_id !== null) fail(400, 'category_too_deep', { category_id: madreNueva });
			const hijas = cuantasHijas(companyId, id);
			// La otra mitad de RN-5: con hijas propias, mudarse crea un tercer nivel.
			if (hijas > 0) fail(400, 'category_has_children', { category_id: id, children: hijas });
		}
	}

	if ((nombre !== categoria.name || seMueve) && nombreTomado(companyId, destino, nombre, id))
		fail(400, 'category_name_taken', { name: nombre });

	categoria.name = nombre;
	if (seMueve) {
		categoria.parent_id = destino;
		const orden = hermanas(companyId, destino)
			.filter((c) => c.id !== id)
			.reduce((max, c) => Math.max(max, c.sort_order), 0);
		categoria.sort_order = orden + 1;
	}
	if (typeof datos.is_active === 'boolean') categoria.is_active = datos.is_active;
	persist();
	return categoria;
});

route('PUT', '/categories/reorder', ({ body, companyId }) => {
	const parentId = body?.parent_id == null ? null : Number(body.parent_id);
	const ids = Array.isArray(body?.ids) ? body.ids.map(Number) : [];
	const grupo = hermanas(companyId, parentId);

	// La lista tiene que estar completa: con una parcial, las que faltaran
	// conservarían su número y quedarían empatadas con las renumeradas.
	const esperado = grupo.map((c) => c.id);
	const iguales =
		esperado.length === ids.length &&
		[...esperado].sort((a, b) => a - b).join() === [...ids].sort((a, b) => a - b).join();
	if (!iguales) fail(400, 'category_reorder_incomplete', { expected: esperado, received: ids });

	ids.forEach((id: number, posicion: number) => {
		const categoria = categoriaPorId(companyId, id);
		if (categoria) categoria.sort_order = posicion + 1;
	});
	persist();
	return hermanas(companyId, parentId);
});

route('DELETE', '/categories/delete_category/:id', ({ params, companyId }) => {
	const db = getDb(companyId);
	const id = Number(params[0]);
	const indice = db.categories.findIndex((c) => c.id === id);
	if (indice === -1) fail(404, 'category_not_found', { category_id: id });

	// RN-7: con productos o con hijas no se borra, se desactiva.
	const productos = cuantosProductos(companyId, id);
	const hijas = cuantasHijas(companyId, id);
	if (productos > 0 || hijas > 0)
		fail(409, 'category_in_use', { category_id: id, products: productos, children: hijas });

	db.categories.splice(indice, 1);
	persist();
	return null;
});

// --------------------------------------------------------------------- ventas

function saleResponse(sale: MockSale, companyId: number) {
	const returned = getDb(companyId).returns.some((r) => r.sale_id === sale.id);
	return {
		id: sale.id,
		sale_number: sale.sale_number,
		client_id: sale.client_id,
		user_id: sale.user_id,
		total: sale.total,
		subtotal: sale.subtotal,
		tax: sale.tax,
		payment_method: sale.payment_method,
		cash_received: sale.cash_received,
		change_given: sale.change_given,
		created_at: sale.created_at,
		returned
	};
}

route('GET', '/sales/sales_list', ({ companyId }) =>
	[...getDb(companyId).sales].sort((a, b) => b.created_at.localeCompare(a.created_at)).map(saleResponse)
);

route('GET', '/sales/sale/:id', ({ params, companyId }) => {
	const db = getDb(companyId);
	const sale = db.sales.find((s) => s.id === Number(params[0]));
	if (!sale) fail(404, 'sale_not_found');
	const client = db.clients.find((c) => c.id_client === sale.client_id);
	return {
		...saleResponse(sale, companyId),
		items: sale.items,
		client_name: client ? `${client.name} ${client.last_name}`.trim() : null,
		user_name: personName(sale.user_id)
	};
});

route('POST', '/sales/add_sale', ({ body, companyId }) => {
	const db = getDb(companyId);
	const saleNumber = String(body?.sale_number ?? '').trim();
	// Sin número no hay factura. El backend de verdad lo rechaza por esquema, así
	// que acá se devuelve el código de «cuerpo rechazado» y no uno inventado.
	if (!saleNumber) fail(400, 'invalid_request', { fields: ['sale_number'] });
	if (db.sales.some((s) => s.sale_number === saleNumber))
		fail(400, 'duplicate_sale_number', { sale_number: saleNumber });

	const products = Array.isArray(body?.products) ? body.products : [];
	if (!products.length) fail(400, 'empty_sale');

	// F5: cada línea lleva la tarifa de SU producto; la configurada es solo el
	// respaldo de los que no tienen la suya (RN-9). Se lee UNA vez y no por
	// línea, igual que en `RegisterSale`: si alguien guardara la configuración a
	// mitad del cobro, dos líneas de la misma venta usarían tasas distintas.
	const tasaDelNegocio = configuredTaxRate(companyId);

	// Se valida TODO antes de escribir nada: o entra la venta completa, o no entra.
	const items: SaleItem[] = [];
	for (const line of products) {
		const quantity = Math.trunc(Number(line?.stock ?? 0));
		const product = db.products.find((p) => p.id_product === Number(line?.id_product));
		if (!product) fail(404, 'product_not_found', { product_id: line?.id_product });
		if (quantity <= 0) fail(400, 'invalid_sale_line', { product_id: line?.id_product });
		if (product.stock < quantity)
			fail(400, 'insufficient_stock', {
				product_id: product.id_product,
				product: product.name,
				available: product.stock,
				requested: quantity
			});
		items.push({
			id_product: product.id_product,
			name: product.name,
			quantity,
			price: product.price,
			subtotal: round2(product.price * quantity),
			// Congelada acá, nunca releída del producto: la suya puede cambiar y
			// la devolución tiene que usar la que se cobró (RN-12).
			tax_rate: product.tax_rate ?? tasaDelNegocio,
			// El impuesto de la línea, con su redondeo. Sin esto el desglose del
			// documento (RF-21) saldría en cero: lo lee de acá, no lo recalcula.
			tax_amount: lineTax(
				round2(product.price * quantity),
				product.tax_rate ?? tasaDelNegocio
			)
		});
	}

	/*
	 * La plata la calcula el servidor (T-108b), y el simulado tiene que hacer lo
	 * mismo o dejaría de servir para probar el POS: los totales se recalculan
	 * con los precios del catálogo y la tasa configurada, y lo que mandó la caja
	 * solo se usa para comprobar que ambos ven lo mismo.
	 *
	 * La tolerancia de un céntimo es la misma que la del backend
	 * (`app/domain/sale.py`, TOTALS_TOLERANCE): el POS calcula en coma flotante
	 * y el servidor en decimal exacto, y en los empates a medio céntimo difieren
	 * en 0,01.
	 */
	const calculado = computeTotals(
		items.map((i) => ({
			price: i.price,
			quantity: i.quantity,
			taxRate: db.products.find((p) => p.id_product === i.id_product)?.tax_rate ?? null
		})),
		tasaDelNegocio
	);
	// Los nombres son los del API ('tax', no 'impuesto'): viajan al POS y ahí se
	// vuelven palabra, igual que en el backend de verdad.
	for (const [campo, dicho, dado] of [
		['subtotal', body?.subtotal, calculado.subtotal],
		['tax', body?.tax, calculado.tax],
		['total', body?.total, calculado.total]
	] as const) {
		if (Math.abs(round2(Number(dicho ?? 0)) - dado) > 0.01) {
			fail(400, 'totals_mismatch', {
				field: campo,
				declared: round2(Number(dicho ?? 0)),
				computed: dado
			});
		}
	}

	const cashReceived = round2(Number(body?.cash_received ?? 0));
	if (cashReceived < calculado.total)
		fail(400, 'insufficient_payment', { received: cashReceived, total: calculado.total });

	const id = nextId('sales');
	db.sales.push({
		id,
		sale_number: saleNumber,
		client_id: body?.client_id != null ? Number(body.client_id) : null,
		user_id: Number(body?.user_id ?? 0),
		subtotal: calculado.subtotal,
		tax: calculado.tax,
		total: calculado.total,
		payment_method: String(body?.payment_method ?? 'Efectivo'),
		cash_received: cashReceived,
		// El vuelto ni se recibe: se calcula. Así no puede venir negativo.
		change_given: changeDue(cashReceived, calculado.total),
		created_at: String(body?.created_at ?? nowIso()),
		items
	});
	for (const item of items) {
		const product = db.products.find((p) => p.id_product === item.id_product)!;
		product.stock -= item.quantity;
	}
	persist();
	return { message: 'sale_registered', id_sale: id };
});

// --------------------------------------------------------------- devoluciones

route('GET', '/returns/returns_list', ({ companyId }) =>
	[...getDb(companyId).returns].sort((a, b) => b.created_at.localeCompare(a.created_at))
);

route('GET', '/returns/return/:id', ({ params, companyId }) => {
	const found = getDb(companyId).returns.find((r) => r.id === Number(params[0]));
	if (!found) fail(404, 'return_not_found');
	return found;
});

route('POST', '/returns/add_return', ({ body, companyId }) => {
	const db = getDb(companyId);
	const sale = db.sales.find((s) => s.id === Number(body?.sale_id));
	if (!sale) fail(404, 'sale_not_found');

	const requested = Array.isArray(body?.items) ? body.items : [];
	if (!requested.length) fail(400, 'empty_return');

	// Cantidad ya devuelta por producto, para no devolver dos veces lo mismo.
	const already = new Map<number, number>();
	for (const previous of db.returns.filter((r) => r.sale_id === sale.id)) {
		for (const item of previous.items) {
			already.set(item.id_product, (already.get(item.id_product) ?? 0) + item.quantity);
		}
	}

	// El tipo se escribe acá y no se deja inferir: `requested` viene del cuerpo
	// de la petición, o sea `any`, y sin esto todo lo que sale de este `map`
	// arrastra el `any` hasta el cálculo de los totales —que fue justo donde se
	// coló un `unit_price` que no existe—.
	const items: ReturnItem[] = requested.map((line: any) => {
		const quantity = Math.trunc(Number(line?.quantity ?? 0));
		const sold = sale.items.find((i) => i.id_product === Number(line?.id_product));
		if (!sold) fail(400, 'not_sold_in_this_sale', { product_id: line?.id_product });
		if (quantity <= 0)
			fail(400, 'invalid_return_quantity', {
				product_id: sold.id_product,
				product: sold.name
			});
		const remaining = sold.quantity - (already.get(sold.id_product) ?? 0);
		if (quantity > remaining)
			fail(400, 'excessive_return', {
				product_id: sold.id_product,
				product: sold.name,
				remaining
			});
		return {
			id_product: sold.id_product,
			name: sold.name,
			quantity,
			price: sold.price,
			subtotal: round2(sold.price * quantity)
		};
	});

	// La tasa del ENCABEZADO de la venta, que desde F5 es solo el respaldo: sirve
	// para las ventas anteriores a la migración 006, que llevan una sola tarifa y
	// por eso el cociente la reconstruye exacta. Con tarifas mezcladas sería un
	// PROMEDIO, y devolver una sola línea con el promedio reembolsa de más o de
	// menos. Mismo criterio que `TaxRate.of_sale` en el backend.
	const delEncabezado =
		sale.subtotal > 0 ? sale.tax / sale.subtotal : configuredTaxRate(companyId);
	// Cada línea con la tarifa que se le CONGELÓ al cobrar (RN-12).
	const totales = computeTotals(
		// `price` y no `unit_price`: así se llama el campo de una línea devuelta.
		// Con el nombre equivocado, `lineTotal` recibía `undefined`, `round2` lo
		// convertía en 0 y la devolución entera reembolsaba cero sin fallar.
		items.map((i) => ({
			price: i.price,
			quantity: i.quantity,
			taxRate: sale.items.find((v) => v.id_product === i.id_product)?.tax_rate ?? null
		})),
		delEncabezado
	);
	const netSubtotal = totales.subtotal;
	const total = totales.total;

	// Devolución completa = todas las líneas de la venta quedan en cero.
	const isFull = sale.items.every((sold) => {
		const returningNow = items.find((i: any) => i.id_product === sold.id_product)?.quantity ?? 0;
		return (already.get(sold.id_product) ?? 0) + returningNow >= sold.quantity;
	});

	const id = nextId('returns');
	const record: SaleReturn = {
		id,
		sale_id: sale.id,
		sale_number: sale.sale_number,
		user_id: Number(body?.user_id ?? 0),
		user_name: personName(Number(body?.user_id ?? 0)),
		created_at: nowIso(),
		reason: String(body?.reason ?? '').trim() || 'Sin motivo indicado',
		// El desglose de lo reembolsado (T-509b). Con tarifas mezcladas el
		// impuesto no se puede deducir del total, así que se guarda.
		subtotal: netSubtotal,
		tax: totales.tax,
		total,
		is_full: isFull,
		items
	};
	db.returns.push(record);

	// El stock vuelve al inventario. Esto es lo que el sistema original nunca hacía.
	for (const item of items) {
		const product = db.products.find((p) => p.id_product === item.id_product);
		if (product) product.stock += item.quantity;
	}
	persist();
	return { message: 'return_registered', id_return: id, total };
});

// ----------------------------------------------------------------------- caja

function computeExpected(session: CashSession, companyId: number): CashSessionReport {
	const db = getDb(companyId);
	const from = session.opened_at;
	const to = session.closed_at ?? nowIso();

	const sales = db.sales.filter(
		(s) => s.user_id === session.user_id && s.created_at >= from && s.created_at <= to
	);
	const movements = db.cash_movements.filter((m) => m.session_id === session.id);
	const returns = db.returns.filter(
		(r) => r.user_id === session.user_id && r.created_at >= from && r.created_at <= to
	);

	const byMethod = new Map<string, { count: number; total: number }>();
	for (const sale of sales) {
		const entry = byMethod.get(sale.payment_method) ?? { count: 0, total: 0 };
		entry.count += 1;
		entry.total = round2(entry.total + sale.total);
		byMethod.set(sale.payment_method, entry);
	}

	const cashSales = round2(
		sales.filter((s) => s.payment_method === 'Efectivo').reduce((acc, s) => acc + s.total, 0)
	);
	const movementsIn = round2(
		movements.filter((m) => m.type === 'entrada').reduce((acc, m) => acc + m.amount, 0)
	);
	const movementsOut = round2(
		movements.filter((m) => m.type === 'salida').reduce((acc, m) => acc + m.amount, 0)
	);
	const returnsTotal = round2(returns.reduce((acc, r) => acc + r.total, 0));

	// Solo el efectivo afecta la gaveta: tarjeta y transferencia no pasan por caja.
	const expected = round2(
		session.opening_amount + cashSales + movementsIn - movementsOut - returnsTotal
	);

	return {
		...session,
		expected_amount: expected,
		difference:
			session.closing_amount == null ? null : round2(session.closing_amount - expected),
		movements: movements.sort((a, b) => a.created_at.localeCompare(b.created_at)),
		sales_count: sales.length,
		sales_total: round2(sales.reduce((acc, s) => acc + s.total, 0)),
		by_payment_method: [...byMethod.entries()].map(([payment_method, v]) => ({
			payment_method,
			count: v.count,
			total: v.total
		})),
		cash_sales: cashSales,
		movements_in: movementsIn,
		movements_out: movementsOut,
		returns_total: returnsTotal
	};
}

function currentSession(userId: number, companyId: number): CashSession | null {
	return getDb(companyId).cash_sessions.find((s) => s.user_id === userId && s.status === 'abierta') ?? null;
}

route('GET', '/cash/current', ({ query, userId, companyId }) => {
	const target = Number(query.get('user_id') ?? userId ?? 0);
	const session = currentSession(target, companyId);
	return session ? computeExpected(session, companyId) : null;
});

route('POST', '/cash/open', ({ body, companyId }) => {
	const db = getDb(companyId);
	const user = Number(body?.user_id ?? 0);
	if (currentSession(user, companyId)) fail(400, 'cash_already_open');
	const amount = round2(Number(body?.opening_amount ?? 0));
	if (amount < 0) fail(400, 'cash_opening_negative');

	const session: CashSession = {
		id: nextId('cash_sessions'),
		user_id: user,
		user_name: personName(user),
		opened_at: nowIso(),
		closed_at: null,
		opening_amount: amount,
		closing_amount: null,
		expected_amount: amount,
		difference: null,
		status: 'abierta',
		notes: body?.notes ? String(body.notes) : null
	};
	db.cash_sessions.push(session);
	persist();
	return computeExpected(session, companyId);
});

route('POST', '/cash/movement', ({ body, companyId }) => {
	const db = getDb(companyId);
	const user = Number(body?.user_id ?? 0);
	const session = currentSession(user, companyId);
	if (!session) fail(400, 'cash_no_open_session');

	const type = String(body?.type ?? '');
	if (type !== 'entrada' && type !== 'salida')
		fail(400, 'cash_invalid_movement_type');
	const amount = round2(Number(body?.amount ?? 0));
	if (!(amount > 0)) fail(400, 'cash_amount_not_positive');
	const reason = String(body?.reason ?? '').trim();
	if (!reason) fail(400, 'cash_missing_reason');

	if (type === 'salida') {
		const available = computeExpected(session, companyId).expected_amount;
		if (amount > available)
			fail(400, 'cash_insufficient', { available });
	}

	const movement: CashMovement = {
		id: nextId('cash_movements'),
		session_id: session.id,
		type,
		amount,
		reason,
		created_at: nowIso()
	};
	db.cash_movements.push(movement);
	persist();
	return movement;
});

route('POST', '/cash/close', ({ body, companyId }) => {
	const user = Number(body?.user_id ?? 0);
	const session = currentSession(user, companyId);
	if (!session) fail(400, 'cash_no_open_session');
	const counted = round2(Number(body?.closing_amount ?? 0));
	if (counted < 0) fail(400, 'cash_counted_negative');

	const report = computeExpected(session, companyId);
	session.closing_amount = counted;
	session.closed_at = nowIso();
	session.status = 'cerrada';
	session.expected_amount = report.expected_amount;
	session.difference = round2(counted - report.expected_amount);
	if (body?.notes) session.notes = String(body.notes);
	persist();
	return computeExpected(session, companyId);
});

route('GET', '/cash/sessions', ({ query, companyId }) => {
	const db = getDb(companyId);
	const userFilter = query.get('user_id');
	return db.cash_sessions
		.filter((s) => !userFilter || s.user_id === Number(userFilter))
		.sort((a, b) => b.opened_at.localeCompare(a.opened_at))
		.map((s) => computeExpected(s, companyId));
});

route('GET', '/cash/session/:id', ({ params, companyId }) => {
	const session = getDb(companyId).cash_sessions.find((s) => s.id === Number(params[0]));
	if (!session) fail(404, 'cash_session_not_found');
	return computeExpected(session, companyId);
});

// ------------------------------------------------------------------- reportes

/** Rango [from, to] inclusive, interpretado en hora local del servidor. */
function parseRange(query: URLSearchParams) {
	const to = query.get('to') ?? new Date().toISOString().slice(0, 10);
	const from = query.get('from') ?? to;
	return {
		from,
		to,
		fromTs: new Date(`${from}T00:00:00`).getTime(),
		toTs: new Date(`${to}T23:59:59.999`).getTime()
	};
}

function salesBetween(fromTs: number, toTs: number, companyId: number): MockSale[] {
	return getDb(companyId).sales.filter((s) => {
		const t = new Date(s.created_at).getTime();
		return t >= fromTs && t <= toTs;
	});
}

route('GET', '/reports/summary', ({ query, companyId }) => {
	const { from, to, fromTs, toTs } = parseRange(query);
	const sales = salesBetween(fromTs, toTs, companyId);
	const db = getDb(companyId);

	const gross = round2(sales.reduce((acc, s) => acc + s.total, 0));
	const returnsTotal = round2(
		db.returns
			.filter((r) => {
				const t = new Date(r.created_at).getTime();
				return t >= fromTs && t <= toTs;
			})
			.reduce((acc, r) => acc + r.total, 0)
	);

	// Periodo anterior de igual duración, para el porcentaje de variación.
	const span = toTs - fromTs;
	const previous = salesBetween(fromTs - span - 1, fromTs - 1, companyId);

	const summary: ReportSummary = {
		range: { from, to },
		sales_count: sales.length,
		gross_total: gross,
		returns_total: returnsTotal,
		net_total: round2(gross - returnsTotal),
		tax_total: round2(sales.reduce((acc, s) => acc + s.tax, 0)),
		average_ticket: sales.length ? round2(gross / sales.length) : 0,
		items_sold: sales.reduce((acc, s) => acc + s.items.reduce((a, i) => a + i.quantity, 0), 0),
		previous_net_total: round2(previous.reduce((acc, s) => acc + s.total, 0))
	};
	return summary;
});

route('GET', '/reports/top_products', ({ query, companyId }) => {
	const { fromTs, toTs } = parseRange(query);
	const limit = Number(query.get('limit') ?? 8);
	const totals = new Map<number, TopProduct>();

	for (const sale of salesBetween(fromTs, toTs, companyId)) {
		for (const item of sale.items) {
			const entry = totals.get(item.id_product) ?? {
				id_product: item.id_product,
				name: item.name,
				quantity: 0,
				total: 0
			};
			entry.quantity += item.quantity;
			entry.total = round2(entry.total + item.subtotal);
			totals.set(item.id_product, entry);
		}
	}
	return [...totals.values()].sort((a, b) => b.total - a.total).slice(0, limit);
});

route('GET', '/reports/sales_by_day', ({ query, companyId }) => {
	const { from, to, fromTs, toTs } = parseRange(query);
	const buckets = new Map<string, SalesByDay>();

	// Se siembran todos los días del rango para que el gráfico no tenga huecos.
	for (let d = new Date(`${from}T00:00:00`); d <= new Date(`${to}T00:00:00`); d.setDate(d.getDate() + 1)) {
		const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
		buckets.set(key, { day: key, sales_count: 0, total: 0 });
	}
	for (const sale of salesBetween(fromTs, toTs, companyId)) {
		const d = new Date(sale.created_at);
		const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
		const bucket = buckets.get(key) ?? { day: key, sales_count: 0, total: 0 };
		bucket.sales_count += 1;
		bucket.total = round2(bucket.total + sale.total);
		buckets.set(key, bucket);
	}
	return [...buckets.values()].sort((a, b) => a.day.localeCompare(b.day));
});

route('GET', '/reports/by_payment_method', ({ query, companyId }) => {
	const { fromTs, toTs } = parseRange(query);
	const totals = new Map<string, PaymentBreakdown>();
	for (const sale of salesBetween(fromTs, toTs, companyId)) {
		const entry = totals.get(sale.payment_method) ?? {
			payment_method: sale.payment_method,
			count: 0,
			total: 0
		};
		entry.count += 1;
		entry.total = round2(entry.total + sale.total);
		totals.set(sale.payment_method, entry);
	}
	return [...totals.values()].sort((a, b) => b.total - a.total);
});

route('GET', '/reports/low_stock', ({ query, companyId }) => {
	const threshold = Number(query.get('threshold') ?? LOW_STOCK_THRESHOLD);
	return getDb(companyId)
		.products.filter((p) => p.stock <= threshold)
		.sort((a, b) => a.stock - b.stock)
		.map<LowStockProduct>((p) => ({
			id_product: p.id_product,
			name: p.name,
			barcode: p.barcode,
			stock: p.stock,
			category_id: p.category_id
		}));
});

// -------------------------------------------- entradas de inventario

route('GET', '/inventory/entries', ({ companyId }) =>
	[...getDb(companyId).stock_entries].sort((a, b) => b.created_at.localeCompare(a.created_at))
);

route('GET', '/inventory/entry/:id', ({ params, companyId }) => {
	const found = getDb(companyId).stock_entries.find((e) => e.id === Number(params[0]));
	if (!found) fail(404, 'entry_not_found');
	return found;
});

route('POST', '/inventory/entry', ({ body, companyId }) => {
	const db = getDb(companyId);
	const requested = Array.isArray(body?.lines) ? body.lines : [];
	if (!requested.length) fail(400, 'empty_entry');

	const documentNumber = body?.document_number ? String(body.document_number).trim() : null;
	if (documentNumber) {
		const duplicate = db.stock_entries.find(
			(e) => e.document_number === documentNumber && e.status === 'aplicada'
		);
		if (duplicate) {
			fail(400, 'duplicate_document', {
				document_number: documentNumber,
				loaded_at: duplicate.created_at
			});
		}
	}

	// Se valida todo antes de escribir: o entra la carga completa, o ninguna.
	const resolved: { product: Product; quantity: number; unitCost: number }[] = [];
	let createdProducts = 0;

	for (const [index, raw] of requested.entries()) {
		const quantity = Math.trunc(Number(raw?.quantity ?? 0));
		const unitCost = round2(Number(raw?.unit_cost ?? 0));
		// Un solo código para las dos, como el backend: el dominio rechaza el valor
		// y la línea la nombra la interfaz.
		if (!(quantity > 0) || unitCost < 0)
			fail(400, 'invalid_entry_line', { line: index + 1 });

		if (raw?.id_product) {
			const product = db.products.find((p) => p.id_product === Number(raw.id_product));
			if (!product)
				fail(404, 'entry_product_not_found', { product_id: raw.id_product });
			resolved.push({ product, quantity, unitCost });
		} else if (raw?.new_product) {
			const data = raw.new_product;
			const barcode = String(data.barcode ?? '').trim();
			if (!barcode) fail(400, 'entry_missing_barcode', { line: index + 1 });
			if (db.products.some((p) => p.barcode === barcode))
				fail(400, 'barcode_taken', { barcode });
			// RN-6 también acá: la entrada de mercadería crea productos, así que
			// sin esto el archivo del proveedor es la puerta de atrás de la regla.
			categoriaParaProducto(companyId, Number(data.category_id ?? 0));

			const product: Product = {
				id_product: nextId('products'),
				name: String(data.name ?? ''),
				description: String(data.description ?? data.name ?? ''),
				price: round2(Number(data.price ?? 0)),
				stock: 0,
				barcode,
				created_at: nowIso(),
				category_id: Number(data.category_id ?? 0)
			};
			db.products.push(product);
			createdProducts += 1;
			resolved.push({ product, quantity, unitCost });
		} else {
			fail(400, 'entry_line_without_product', { line: index + 1 });
		}
	}

	const id = nextId('stock_entries');
	let total = 0;
	let units = 0;

	const lines = resolved.map(({ product, quantity, unitCost }) => {
		const subtotal = round2(unitCost * quantity);
		total = round2(total + subtotal);
		units += quantity;
		product.stock += quantity;
		return {
			id_product: product.id_product,
			name: product.name,
			quantity,
			unit_cost: unitCost,
			subtotal
		};
	});

	db.stock_entries.push({
		id,
		document_number: documentNumber,
		supplier: body?.supplier ? String(body.supplier) : null,
		source: ['manual', 'excel', 'xml'].includes(body?.source) ? body.source : 'manual',
		user_id: Number(body?.user_id ?? 0),
		user_name: personName(Number(body?.user_id ?? 0)),
		created_at: nowIso(),
		notes: body?.notes ? String(body.notes) : null,
		status: 'aplicada',
		total_cost: total,
		items_count: units,
		lines
	});
	persist();

	return {
		message: 'entry_registered',
		id_entry: id,
		products_created: createdProducts,
		units_added: units
	};
});

route('POST', '/inventory/entry/:id/cancel', ({ params, companyId }) => {
	const db = getDb(companyId);
	const entry = db.stock_entries.find((e) => e.id === Number(params[0]));
	if (!entry) fail(404, 'entry_not_found');
	if (entry.status === 'anulada') fail(400, 'entry_already_cancelled');

	// Si parte ya se vendió, revertir dejaría el stock en negativo.
	for (const line of entry.lines) {
		const product = db.products.find((p) => p.id_product === line.id_product);
		if (product && product.stock < line.quantity) {
			fail(400, 'entry_cannot_cancel', {
				product_id: product.id_product,
				product: product.name,
				available: product.stock,
				added: line.quantity
			});
		}
	}

	for (const line of entry.lines) {
		const product = db.products.find((p) => p.id_product === line.id_product);
		if (product) product.stock -= line.quantity;
	}
	entry.status = 'anulada';
	persist();
	return { message: 'entry_cancelled', id_entry: entry.id };
});

// -------------------------------------------------------------- configuración

/** Fila única de configuración. Se crea al vuelo si el archivo venía sin ella. */
function settingsRow(companyId: number): MockSettings {
	const db = getDb(companyId);
	if (!db.settings) {
		// Se escribe en la porción de la compañía y no en la vista: la vista es
		// una copia superficial, y reasignarle una propiedad no llega al almacén.
		getEmpresa(companyId).settings = { data: {}, logo: null, updated_at: null, updated_by: null };
		return getEmpresa(companyId).settings!;
	}
	return db.settings;
}

/**
 * Tasa configurada, con el mismo respaldo que `crud_settings.get_tax_rate`.
 *
 * Lee las dos formas de la clave —`tax.rate` y el `impuesto.tasa` de antes de
 * T-113— por lo mismo que `mergeSettings`: una fila guardada con la versión
 * anterior tiene que seguir entendiéndose.
 */
function configuredTaxRate(companyId: number): number {
	const data = settingsRow(companyId).data as {
		tax?: { rate?: unknown };
		impuesto?: { tasa?: unknown };
	};
	const rate = Number(data?.tax?.rate ?? data?.impuesto?.tasa);
	return Number.isFinite(rate) && rate >= 0 && rate <= 1 ? rate : DEFAULT_TAX_RATE;
}

route('GET', '/settings/', ({ userId, companyId }) => {
	// La lee cualquier sesión: el cajero necesita la moneda y los datos del
	// tiquete. No hay secretos guardados acá.
	if (userId == null) fail(401, 'unauthorized');
	return settingsRow(companyId);
});

route('PUT', '/settings/', ({ userId, body, companyId }) => {
	if (userId == null) fail(401, 'unauthorized');
	const db = getDb(companyId);
	const user = db.users.find((u) => u.id_user === userId);
	if (!user) fail(401, 'unauthorized');
	if (user.role !== 'admin') fail(403, 'admin_only');

	const data = body?.data;
	if (!data || typeof data !== 'object' || Array.isArray(data)) {
		fail(400, 'invalid_request', { fields: ['data'] });
	}
	if (JSON.stringify(data).length > 20_000) fail(400, 'settings_too_large');

	const rate = data?.impuesto?.rate;
	if (rate !== undefined) {
		const n = Number(rate);
		if (!Number.isFinite(n)) fail(400, 'tax_rate_not_a_number');
		if (n < 0 || n > 1)
			fail(400, 'tax_rate_out_of_range');
	}

	const row = settingsRow(companyId);
	row.data = data;
	if (body?.logo) {
		if (!/^image\/(png|jpeg|webp)$/.test(String(body.logo.mime ?? '')))
			// El backend de verdad lo rechaza por el patrón del esquema, o sea con
			// un 422 y la lista de campos. Mismo código para la misma situación.
			fail(400, 'invalid_request', { fields: ['logo.mime'] });
		row.logo = { mime: String(body.logo.mime), data: String(body.logo.data ?? '') };
	} else if (body?.keep_logo === false) {
		row.logo = null;
	}
	row.updated_at = nowIso();
	row.updated_by = userId;
	persist();
	return row;
});

// Utilidad exclusiva del modo demo: devuelve todo al estado de fábrica.
route('POST', '/mock/reset', ({ companyId }) => {
	resetDb();
	// Código y no prosa, como los demás «sí» del simulado (T-802): nadie lo
	// muestra hoy, pero una respuesta con una frase adentro es una frase que
	// alguien acabará mostrando.
	return { message: 'mock_reset' };
});

// ------------------------------------------------------------------- CABYS
//
// El catálogo de Hacienda, simulado. Son pocas entradas y con las tarifas
// reales del spec —13 %, 2 % y 0 %—: alcanzan para clasificar el catálogo de
// demostración y para que se vea el desglose de RF-21, que es lo que el modo
// simulado tiene que poder enseñar.
//
// **Aquí `source` es siempre 'hacienda'.** El simulado no tiene red que se
// caiga, así que la degradación de RNF-4 se prueba contra el backend de verdad;
// lo que sí se respeta es el contrato, para que la pantalla no tenga dos formas
// de leer la respuesta.
const CABYS_DEMO = [
	// Los del catálogo de demostración. **Códigos reales**, consultados a Hacienda
	// el 2026-09-06: los de antes eran inventados y con eso el simulado enseñaba
	// una tarifa que el catálogo de verdad no confirma —justo lo que Hacienda
	// rechaza como «IVA incorrecto»—.
	{ code: '2316100000100', description: 'Arroz blanco, fortificado', tax_rate: 0.01 },
	// La harina de arroz al lado del arroz, y con la tarifa distinta, porque es
	// el ejemplo entero de por qué la tarifa la define el código y no el nombre
	// del producto: «arroz» no es una tarifa, `2316100000100` sí.
	{ code: '2312000000300', description: 'Harina de arroz', tax_rate: 0.13 },
	{ code: '0170102000400', description: 'Frijoles negros, secos', tax_rate: 0.01 },
	{ code: '2163200000000', description: 'Aceite de semillas de girasol, refinado', tax_rate: 0.01 },
	{ code: '2352001010000', description: 'Azúcar blanca de plantación', tax_rate: 0.01 },
	{ code: '2399908000200', description: 'Sal refinada', tax_rate: 0.01 },
	{ code: '2371000000200', description: 'Pasta sin huevo, sin cocer', tax_rate: 0.01 },
	{ code: '2391102010200', description: 'Café tostado, sin descafeinar, molido', tax_rate: 0.01 },
	{ code: '2211001030000', description: 'Leche líquida de vaca, entera', tax_rate: 0.01 },
	{ code: '2225101010200', description: 'Queso tipo Turrialba fresco, en barra', tax_rate: 0.01 },
	{ code: '2349002010700', description: 'Pan cuadrado, blanco o integral', tax_rate: 0.01 },
	{ code: '2349001010100', description: 'Tortillas de harina de maíz, sin congelar', tax_rate: 0.01 },
	{ code: '2349002010600', description: 'Bollo u otra presentación de pan dulce', tax_rate: 0.01 },
	{ code: '3219301000000', description: 'Papel higiénico', tax_rate: 0.01 },
	{ code: '2449003000100', description: 'Bebidas a base de agua mineral gaseadas', tax_rate: 0.13 },
	{ code: '2441002020000', description: 'Agua natural embotellada', tax_rate: 0.13 },
	{ code: '2449002000100', description: 'Bebidas a base de jugo de frutas', tax_rate: 0.13 },
	{ code: '2431000000000', description: 'Cerveza de malta', tax_rate: 0.13 },
	{ code: '2449002000200', description: 'Bebidas a base de té', tax_rate: 0.13 },
	{ code: '2223001000200', description: 'Yogurt líquido', tax_rate: 0.13 },
	{ code: '2223099020000', description: 'Crema cultivada', tax_rate: 0.13 },
	{ code: '3532201060000', description: 'Detergentes en polvo', tax_rate: 0.13 },
	{ code: '3532101010199', description: 'Jabón de tocador n.c.p., en barras', tax_rate: 0.13 },
	{ code: '3532201010000', description: 'Blanqueador líquido', tax_rate: 0.13 },
	{ code: '2342001009900', description: 'Galletas dulces con edulcorante', tax_rate: 0.13 },
	{ code: '2314000990300', description: 'Bocadillos de maíz u otros cereales, tostados', tax_rate: 0.13 },
	{ code: '2149500000200', description: 'Maní tostado, salado', tax_rate: 0.13 },
	// Y dos que no vende una pulpería, pero sí una farmacia y una librería. Están
	// para que el simulado pueda enseñar las cuatro tarifas —13, 1, 2 y 0— y para
	// que las pruebas de punta a punta tengan con qué comprobar el desglose.
	{ code: '3563704030201', description: 'Supresores de la tos y mucolíticos', tax_rate: 0.02 },
	{ code: '3229200000000', description: 'Libros infantiles, impresos', tax_rate: 0 }
];

route('GET', '/cabys/buscar', ({ query }) => {
	const texto = (query.get('q') ?? '').trim().toLowerCase();
	const top = Math.min(Math.max(Number(query.get('top') ?? 20), 1), 50);
	if (!texto) return { source: 'hacienda', cached_at: null, items: [] };
	const encontrados = CABYS_DEMO.filter(
		(c) => c.description.toLowerCase().includes(texto) || c.code.includes(texto)
	);
	return { source: 'hacienda', cached_at: null, items: encontrados.slice(0, top) };
});

route('GET', '/cabys/:codigo', ({ params }) => {
	const codigo = decodeURIComponent(params[0]).trim();
	// Las mismas tres razones que el dominio del backend, y en el mismo orden.
	if (!codigo) fail(400, 'cabys_invalid_code', { value: codigo, reason: 'empty' });
	if (!/^\d+$/.test(codigo))
		fail(400, 'cabys_invalid_code', { value: codigo, reason: 'not_digits' });
	if (codigo.length !== 13)
		fail(400, 'cabys_invalid_code', { value: codigo, reason: 'bad_length' });

	const encontrado = CABYS_DEMO.find((c) => c.code === codigo);
	if (!encontrado) fail(404, 'cabys_not_found', { code: codigo });
	return { source: 'hacienda', cached_at: null, items: [encontrado] };
});


// ------------------------------------------------------------------ despachador

/**
 * Las dos puertas y el freno, en un solo sitio (F3).
 *
 * Es la traducción de lo que hace `auth_dependency` en el backend, y va en el
 * despachador por la misma razón que allá va en la dependencia: cuarenta rutas
 * que hay que acordarse de tocar no son un control de acceso.
 *
 * 1. Un token de soporte no abre el POS y uno del POS no abre el panel (T-302).
 * 2. Con la suscripción sin gracia, o de visita, no se escribe (T-308, RF-8).
 */
const METODOS_QUE_ESCRIBEN = ['POST', 'PUT', 'PATCH', 'DELETE'];

/** Las dos que se pueden escribir igual. Ver `ESCRITURA_EN_SOLO_LECTURA` allá. */
const ESCRITURA_EN_SOLO_LECTURA = ['/cash/close', '/auth/locale'];

/** Las que no pasan por la sesión, así que el freno no aplica. Ver SIN_SESION. */
const SIN_SESION = [
	'/auth/login',
	'/auth/company',
	'/auth/companies',
	'/auth/invitation',
	'/persons/register'
];

function guardar(path: string, method: string, token: string | null | undefined): void {
	const payload = tokenPayload(token);
	const tipo = payload?.tipo;
	const esPanel = path.startsWith('/support');

	if (esPanel && tipo !== 'soporte') {
		// 403 y no 401: el token vale, lo que no vale es para esto.
		throw new ApiError(403, 'support_only', {});
	}
	if (tipo === 'soporte' && !esPanel && !path.startsWith('/auth') && path !== '/health') {
		throw new ApiError(401, 'no_company_in_token', {});
	}

	if (
		!METODOS_QUE_ESCRIBEN.includes(method) ||
		esPanel ||
		path.startsWith('/mock') ||
		SIN_SESION.includes(path) ||
		ESCRITURA_EN_SOLO_LECTURA.includes(path)
	) {
		return;
	}

	if (tipo === 'suplantacion') throw new ApiError(403, 'impersonation_read_only', {});

	if (readToken(token) != null) {
		const suscripcion = evaluarSuscripcion(companyOf(token));
		if (suscripcion && !suscripcion.puede_vender) {
			throw new ApiError(403, 'subscription_read_only', { state: suscripcion.estado });
		}
	}
}

export async function mockRequest<T>(request: MockRequest): Promise<T> {
	const [rawPath, rawQuery = ''] = request.path.split('?');
	// `/users/` y `/users` deben resolver igual.
	const path = rawPath.length > 1 && rawPath.endsWith('/') ? rawPath : rawPath;
	const query = new URLSearchParams(rawQuery);
	const userId = readToken(request.token);
	const companyId = companyOf(request.token);

	guardar(path, request.method, request.token);

	for (const entry of routes) {
		if (entry.method !== request.method) continue;
		const match = entry.pattern.exec(path) ?? entry.pattern.exec(`${path}/`);
		if (!match) continue;

		// Latencia simulada: obliga a que los estados de carga se vean de verdad.
		await new Promise((resolve) => setTimeout(resolve, 40 + Math.random() * 60));
		return entry.handler({
			params: match.slice(1),
			query,
			body: request.body,
			userId,
			companyId,
			token: request.token
		}) as T;
	}

	// Solo la ve quien desarrolla, en la consola: es un endpoint que existe en
	// FastAPI y falta acá, o un error de dedo en la ruta.
	throw new ApiError(404, 'unexpected', {
		mock: 'ruta no encontrada',
		method: request.method,
		path
	});
}

/**
 * El idioma de la persona (T-810).
 *
 * Emite un token nuevo por la misma razón que el backend: el idioma vive en el
 * token, así que sin re-emitirlo el cambio no se vería hasta el siguiente login.
 */
route('POST', '/auth/locale', ({ body, userId, companyId }) => {
	if (userId == null) fail(401, 'unauthorized');
	const raiz = getRoot();
	const user = raiz.users.find((u) => u.id_user === userId);
	if (!user) fail(404, 'user_not_found');
	const empresa = raiz.companies.find((c) => c.id === companyId);
	if (!empresa) fail(404, 'membership_not_found');

	const pedido = body?.locale === null || body?.locale === undefined ? null : String(body.locale);
	if (pedido !== null && !IDIOMAS.includes(pedido)) fail(400, 'unsupported_locale', { locale: pedido });

	user.locale = pedido;
	persist();

	const rol = rolEn(user.id_user, companyId) ?? user.role;
	return {
		access_token: tokenDeSesion(user, companyId, rol),
		token_type: 'bearer',
		locale: pedido || empresa.locale || 'es',
		user_locale: pedido,
		document_locale: empresa.document_locale || 'es'
	};
});

/** Los idiomas de la compañía: el de la pantalla y el del documento (T-810, T-811). */
route('PUT', '/settings/locales', ({ body, userId, companyId }) => {
	if (userId == null) fail(401, 'unauthorized');
	const raiz = getRoot();
	const user = raiz.users.find((u) => u.id_user === userId);
	if (!user) fail(404, 'user_not_found');
	if ((rolEn(user.id_user, companyId) ?? user.role) !== 'admin') fail(403, 'admin_only');
	const empresa = raiz.companies.find((c) => c.id === companyId);
	if (!empresa) fail(404, 'membership_not_found');

	const pantalla = String(body?.locale ?? '');
	const documento = String(body?.document_locale ?? '');
	for (const pedido of [pantalla, documento]) {
		if (!IDIOMAS.includes(pedido)) fail(400, 'unsupported_locale', { locale: pedido });
	}

	empresa.locale = pantalla;
	empresa.document_locale = documento;
	persist();

	return {
		access_token: tokenDeSesion(user, companyId, rolEn(user.id_user, companyId) ?? user.role),
		token_type: 'bearer',
		locale: user.locale || pantalla,
		user_locale: user.locale ?? null,
		document_locale: documento
	};
});

// ------------------------------------------------- el panel de soporte (F3)
//
// Siete rutas, con el mismo contrato que `app/router/support_routes.py`. La
// puerta —que solo un token de soporte entre acá, y que uno de soporte no abra
// el POS— la cierra el despachador, en un solo sitio, igual que el backend.

/** El usuario del token, sea de soporte o no. El despachador ya validó el tipo. */
function usuarioDelToken(token: string | null | undefined): MockUser {
	const payload = tokenPayload(token);
	const id = typeof payload?.id_user === 'number' ? payload.id_user : null;
	const user = getRoot().users.find((u) => u.id_user === id);
	if (!user) fail(401, 'unauthorized');
	return user;
}

function planDe(companyId: number): MockPlan | null {
	const raiz = getRoot();
	const empresa = raiz.companies.find((c) => c.id === companyId);
	return raiz.plans.find((p) => p.id === empresa?.plan_id) ?? null;
}

/** El cupo que queda de un recurso. Nulo = el plan no limita (`domain/limits.py`). */
function cupoDe(usados: number, maximo: number): number | null {
	return maximo < 0 ? null : Math.max(0, maximo - usados);
}

/** El uso de una compañía: usuarios, cajas, productos y ventas del mes (RF-5). */
function usoDe(companyId: number) {
	const raiz = getRoot();
	const empresa = getEmpresa(companyId);
	const plan = planDe(companyId);

	const usuarios = raiz.memberships.filter((x) => x.company_id === companyId && x.activa).length;
	// El simulado le da una caja a cada compañía, como el alta de verdad.
	const terminales = 1;

	const inicioDelMes = new Date();
	inicioDelMes.setDate(1);
	inicioDelMes.setHours(0, 0, 0, 0);
	const delMes = empresa.sales.filter((v) => new Date(v.created_at) >= inicioDelMes);

	return {
		usuarios,
		terminales,
		productos: empresa.products.length,
		ventas_del_mes: delMes.length,
		total_del_mes: round2(delMes.reduce((acc, v) => acc + v.total, 0)),
		cupo_usuarios: plan ? cupoDe(usuarios, plan.max_usuarios) : null,
		cupo_terminales: plan ? cupoDe(terminales, plan.max_terminales) : null
	};
}

function companiaParaSoporte(companyId: number) {
	const raiz = getRoot();
	const empresa = raiz.companies.find((c) => c.id === companyId);
	if (!empresa) fail(404, 'company_not_found');

	const administradores = raiz.memberships
		.filter((x) => x.company_id === companyId && x.activa && x.rol === 'admin')
		.map((x) => raiz.users.find((u) => u.id_user === x.user_id)?.email)
		.filter((correo): correo is string => Boolean(correo))
		.sort();

	return {
		id: empresa.id,
		afiliado: empresa.afiliado,
		compania: empresa.compania,
		nombre: empresa.nombre,
		identificacion: empresa.identificacion ?? null,
		creada_el: empresa.creada_el ?? null,
		locale: empresa.locale,
		document_locale: empresa.document_locale,
		plan: planDe(companyId),
		suscripcion: evaluarSuscripcion(companyId),
		uso: usoDe(companyId),
		administradores
	};
}

route('GET', '/support/me', ({ token }) => {
	const user = usuarioDelToken(token);
	return {
		id_user: user.id_user,
		email: user.email,
		name: personName(user.id_user) ?? user.email,
		is_support: true,
		locale: user.locale || 'es'
	};
});

route('GET', '/support/plans', () => getRoot().plans);

route('GET', '/support/companies', () =>
	getRoot()
		.companies.slice()
		.sort((a, b) => a.afiliado - b.afiliado || a.compania - b.compania)
		.map((c) => companiaParaSoporte(c.id))
);

route('GET', '/support/companies/:id', ({ params }) => companiaParaSoporte(Number(params[0])));

/** Alta de compañía (RF-6). Las seis filas, igual que `crud_company.dar_de_alta`. */
route('POST', '/support/companies', ({ body, token }) => {
	const soporte = usuarioDelToken(token);
	const raiz = getRoot();

	const estado = String(body?.estado ?? 'prueba');
	if (!ESTADOS_DE_SUSCRIPCION.includes(estado)) {
		fail(400, 'invalid_company_state', { state: estado });
	}

	const locale = String(body?.locale ?? 'es');
	const documentLocale = String(body?.document_locale ?? 'es');
	for (const pedido of [locale, documentLocale]) {
		if (!IDIOMAS.includes(pedido)) fail(400, 'unsupported_locale', { locale: pedido });
	}

	const planId = Number(body?.plan_id);
	const plan = raiz.plans.find((p) => p.id === planId);
	if (!plan) fail(404, 'plan_not_found', { plan_id: planId });

	// El par se calcula acá cuando no viene, igual que en el backend: es el único
	// que puede hacerlo sin que dos altas elijan el mismo número.
	const afiliado =
		Number(body?.afiliado) || Math.max(0, ...raiz.companies.map((c) => c.afiliado)) + 1;
	const compania =
		Number(body?.compania) ||
		Math.max(0, ...raiz.companies.filter((c) => c.afiliado === afiliado).map((c) => c.compania)) +
			1;

	if (raiz.companies.some((c) => c.afiliado === afiliado && c.compania === compania)) {
		fail(409, 'company_already_exists', { afiliado, compania });
	}

	const admin = (body?.admin ?? {}) as Record<string, string>;
	const email = String(admin.email ?? '')
		.trim()
		.toLowerCase();
	const existente = raiz.users.find((u) => u.email.toLowerCase() === email);
	if (existente?.is_support) fail(400, 'support_cannot_be_member', { email });

	const companyId = nextId('companies');
	raiz.companies.push({
		id: companyId,
		afiliado,
		compania,
		nombre: String(body?.nombre ?? ''),
		estado,
		branch_code: '001',
		terminal_code: '00001',
		locale,
		document_locale: documentLocale,
		plan_id: plan.id,
		vence_el: (body?.vence_el as string | null) ?? null,
		identificacion: (body?.identificacion as string | null) ?? null,
		creada_el: nowIso()
	});

	// La configuración con lo que mandó el POS: los textos del tiquete ya vienen
	// en el idioma del documento (T-304, RN-30).
	const empresa = getEmpresa(companyId);
	empresa.settings = {
		data: body?.settings ?? {},
		logo: null,
		updated_at: nowIso(),
		updated_by: soporte.id_user
	};

	let usuarioNuevo = false;
	let user = existente;
	if (!user) {
		usuarioNuevo = true;
		const idPerson = nextId('persons');
		const idUser = nextId('users');
		raiz.persons.push({
			id_person: idPerson,
			birth_date: String(admin.birth_date ?? '1990-01-01'),
			identification: String(admin.identification || email),
			name: String(admin.name ?? 'Administrador'),
			lastName: String(admin.lastName ?? ''),
			secondName: String(admin.secondName ?? ''),
			telephone: String(admin.telephone ?? ''),
			id_user: idUser,
			email
		});
		user = {
			id_user: idUser,
			email,
			password: String(admin.password ?? ''),
			role: 'admin',
			id_person: idPerson
		};
		raiz.users.push(user);
	}

	// Una identidad que ya existía nace **pendiente**: nadie le puede dar acceso a
	// nombre de otro (T-229). La que se acaba de crear, aceptada.
	raiz.memberships.push({
		user_id: user.id_user,
		company_id: companyId,
		rol: 'admin',
		activa: true,
		aceptada_el: usuarioNuevo ? nowIso() : null
	});

	registrar(
		soporte.id_user,
		companyId,
		'alta_compania',
		`afiliado ${afiliado} · compañía ${compania} — ${body?.nombre}, plan ${plan.nombre}, ` +
			`estado ${estado}, administrador ${email}${usuarioNuevo ? '' : ' (membresía pendiente)'}`
	);
	persist();

	return {
		company_id: companyId,
		afiliado,
		compania,
		nombre: String(body?.nombre ?? ''),
		plan_id: plan.id,
		plan_nombre: plan.nombre,
		estado,
		branch_codigo: '001',
		terminal_codigo: '00001',
		user_id: user.id_user,
		email: user.email,
		usuario_nuevo: usuarioNuevo,
		membresia_pendiente: !usuarioNuevo
	};
});

/** Estado, fecha y plan (RF-7). */
route('PUT', '/support/companies/:id/subscription', ({ params, body, token }) => {
	const soporte = usuarioDelToken(token);
	const companyId = Number(params[0]);
	const empresa = getRoot().companies.find((c) => c.id === companyId);
	if (!empresa) fail(404, 'company_not_found');

	const estado = String(body?.estado ?? '');
	if (!ESTADOS_DE_SUSCRIPCION.includes(estado)) {
		fail(400, 'invalid_company_state', { state: estado });
	}

	const vence = (body?.vence_el as string | null) ?? null;
	const planId = body?.plan_id == null ? null : Number(body.plan_id);
	const plan = planId === null ? null : (getRoot().plans.find((p) => p.id === planId) ?? null);
	if (planId !== null && !plan) fail(404, 'plan_not_found', { plan_id: planId });

	// El detalle se arma con el antes y el después: es lo único que hace útil una
	// bitácora dentro de seis meses.
	const partes: string[] = [];
	if (empresa.estado !== estado) partes.push(`estado ${empresa.estado} → ${estado}`);
	if ((empresa.vence_el ?? null) !== vence) {
		partes.push(`vence ${empresa.vence_el ?? 'sin fecha'} → ${vence ?? 'sin fecha'}`);
	}
	if (plan && empresa.plan_id !== plan.id) {
		partes.push(`plan ${empresa.plan_id} → ${plan.id} (${plan.nombre})`);
	}

	empresa.estado = estado;
	empresa.vence_el = vence;
	if (plan) empresa.plan_id = plan.id;

	registrar(soporte.id_user, companyId, 'suscripcion', partes.join(', ') || 'sin cambios');
	persist();

	return companiaParaSoporte(companyId);
});

/** *Entrar como* (RF-8, RN-4). Motivo obligatorio y solo lectura. */
route('POST', '/support/companies/:id/enter', ({ params, body, token }) => {
	const soporte = usuarioDelToken(token);
	const companyId = Number(params[0]);
	const empresa = getRoot().companies.find((c) => c.id === companyId);
	if (!empresa) fail(404, 'company_not_found');

	const motivo = String(body?.motivo ?? '').trim();
	// El backend lo valida con pydantic y responde 422; el POS ya lo valida antes,
	// así que acá alcanza con no dejar pasar el vacío.
	if (motivo.length < 5) fail(422, 'invalid_request', { field: 'motivo' });

	registrar(soporte.id_user, companyId, 'entrar_como', motivo);

	return {
		access_token: tokenDeSuplantacion(soporte, companyId, motivo),
		token_type: 'bearer',
		tipo: 'suplantacion',
		company_id: companyId,
		company_nombre: empresa.nombre,
		minutos: MINUTOS_DE_VISITA
	};
});

/** La bitácora, filtrable (RF-9). */
route('GET', '/support/audit', ({ query }) => {
	const raiz = getRoot();
	const companyId = query.get('company_id');
	const accion = query.get('accion');
	const limite = Math.min(Number(query.get('limite')) || 50, 500);

	const lineas = raiz.audit
		.filter((l) => !companyId || l.company_id === Number(companyId))
		.filter((l) => !accion || l.accion === accion)
		.slice()
		.sort((a, b) => b.creado_el.localeCompare(a.creado_el) || b.id - a.id)
		.slice(0, limite)
		.map((l) => {
			const user = raiz.users.find((u) => u.id_user === l.user_id);
			const empresa = raiz.companies.find((c) => c.id === l.company_id);
			return {
				...l,
				email: user?.email ?? null,
				nombre: personName(l.user_id),
				company_nombre: empresa?.nombre ?? null
			};
		});

	return {
		lineas,
		acciones: [...new Set(raiz.audit.map((l) => l.accion))].sort()
	};
});
