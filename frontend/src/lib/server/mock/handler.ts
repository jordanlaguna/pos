import { isForeign, identificationTypeFor, isIdentificationType } from '$lib/domain/identification';
import {
	FOREIGN_ADDRESS_MAX_LENGTH,
	exportLineProblem,
	hasForeignAddress,
	isTariffHeading
} from '$lib/domain/export';
import { ApiError, type ApiUpload } from '../api';
import {
	CHART,
	COMMERCE,
	NoBalancea,
	PeriodoCerrado,
	TEMPLATES,
	activa as activaLaContabilidad,
	configuracion as configuracionContable,
	defaultMapping,
	mapeoParaPantalla,
	postCashClose,
	postCashMovement,
	postEntry,
	postPurchase,
	postReclassification,
	postReturn,
	postSale,
	postSupplierPayment,
	totalDe,
	trialBalance
} from './ledger';
import { LOW_STOCK_THRESHOLD } from '../config';
import {
	COMPANIA_DEMO,
	getDb,
	getEmpresa,
	getRoot,
	nextId,
	persist,
	resetDb,
	type MockBranch,
	type MockFeCredentials,
	type MockPayrollRate,
	type MockPlan,
	type MockTerminal,
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
import { COMPANY_STATES, MODULES as MODULOS, PAYMENT_METHODS } from '$lib/domain/types';
import {
	CREDIT_NOTE,
	DEBIT_NOTE,
	EXPORT_INVOICE,
	INVOICE,
	enabledTypes,
	isCounterDocumentType,
	purchaseDocumentType,
	suggestedDocumentType
} from '$lib/domain/documentType';
import { CORRECTS_AMOUNT } from '$lib/domain/documents';
import { isBlankLocation, locationProblem, normalizeLocation } from '$lib/domain/location';
import { mergeSettings } from '$lib/domain/settings';
import type { MockFeDocument } from './db';
import { motivosDeFabrica } from './db';
import { postStockExit } from './ledger';
import type { StockExit, StockMovement, StockMovementKind, StockReason } from '$lib/domain/types';
import { PAYROLL_SEED } from './payrollRates';
import { rutasDePlanilla } from './payroll';
import type { Account, JournalEntry } from '$lib/domain/types';
import type {
	AmountNote,
	AmountNoteItem,
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
	StockEntry,
	Supplier,
	TopProduct,
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
	upload?: ApiUpload;
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
	/** El archivo, cuando la ruta es `multipart`. Hoy solo el `.p12` de F6. */
	upload?: ApiUpload;
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

/**
 * Los módulos que incluye un plan (RN-49). Sin plan, ninguno: falla cerrado,
 * igual que `crud_membership.modulos_de`.
 */
function modulosDelPlan(planId: number | undefined): Record<string, boolean> {
	const plan = planId == null ? undefined : getRoot().plans.find((p) => p.id === planId);
	return Object.fromEntries(MODULOS.map((nombre) => [nombre, plan?.[nombre] === true]));
}

/**
 * Exige que el plan de la compañía incluya el módulo (RN-49), igual que
 * `require_module` en el backend.
 *
 * **Solo se llama desde lo que escribe**, que es la mitad que importa de RN-50:
 * apagar un módulo no borra nada, lo deja en solo lectura. Un `GET` no pasa por
 * acá ni le cuesta una consulta.
 */
function exigirModulo(companyId: number, module: string): void {
	const empresa = getRoot().companies.find((c) => c.id === companyId);
	if (modulosDelPlan(empresa?.plan_id)[module] !== true)
		fail(403, 'module_not_in_plan', { module });
}

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
		// Los módulos del plan (RF-40). Igual que `crud_membership.modulos_de`:
		// se leen acá, en cada petición, y no viajan en el token.
		modules: modulosDelPlan(empresa?.plan_id),
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
	exigirModulo(companyId, 'users'); // QA-01
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
	exigirModulo(companyId, 'users'); // QA-01
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

/**
 * Los ocho campos de la exoneración, espejo de `crud_client.CAMPOS_EXONERACION`.
 *
 * **Se tratan como uno solo**: si viene cualquiera, vienen los ocho, y los ocho
 * vacíos es cómo se le quita la exoneración a un cliente (RN-78).
 */
const CAMPOS_EXONERACION = [
	'exo_document_type',
	'exo_document_number',
	'exo_institution',
	'exo_institution_other',
	'exo_article',
	'exo_subsection',
	'exo_date',
	'exo_points'
] as const;

/** Los cuatro tipos de la nota 10.1 que solo valen en notas de crédito y débito. */
const EXO_SOLO_EN_NOTAS = new Set(['01', '05', '06', '07']);
/** Los que obligan a decir el artículo de la ley. */
const EXO_CON_ARTICULO = new Set(['02', '03', '06', '07', '08']);
const EXO_TIPOS = new Set([
	'01', '02', '03', '04', '05', '06', '07', '08', '09', '10', '11', '99'
]);
const EXO_INSTITUCIONES = new Set([
	'01', '02', '03', '04', '05', '06', '07', '08', '09', '10', '11', '12', '99'
]);

/** Los ocho comprobados, los ocho en nulo, o 400. Espejo de `revisar_exoneracion`. */
function revisarExoneracion(body: Record<string, unknown> | null): Record<string, unknown> {
	if (!body || !CAMPOS_EXONERACION.some((k) => k in body)) return {};
	const crudo = (k: string) => {
		const v = body[k];
		return v == null || v === '' ? null : v;
	};
	if (!CAMPOS_EXONERACION.some((k) => crudo(k) !== null))
		return Object.fromEntries(CAMPOS_EXONERACION.map((k) => [k, null]));

	const no = (reason: string) => fail(400, 'invalid_exemption', { reason });
	const tipo = String(crudo('exo_document_type') ?? '');
	if (!EXO_TIPOS.has(tipo)) no('unknown_document_type');
	if (EXO_SOLO_EN_NOTAS.has(tipo)) no('document_type_only_in_notes');
	if (crudo('exo_document_number') === null) no('missing_document_number');
	const institucion = String(crudo('exo_institution') ?? '');
	if (!EXO_INSTITUCIONES.has(institucion)) no('unknown_institution');
	if (institucion === '99' && crudo('exo_institution_other') === null)
		no('missing_institution_name');
	const fecha = crudo('exo_date');
	if (fecha === null) no('missing_date');
	if (Number.isNaN(Date.parse(String(fecha)))) no('bad_date');
	const articulo = crudo('exo_article');
	if (EXO_CON_ARTICULO.has(tipo) && articulo === null) no('missing_article');
	const puntos = Number(crudo('exo_points'));
	if (!Number.isFinite(puntos) || puntos <= 0 || puntos > 99.99) no('points_out_of_range');

	return {
		exo_document_type: tipo,
		exo_document_number: String(crudo('exo_document_number')),
		exo_institution: institucion,
		exo_institution_other: crudo('exo_institution_other')
			? String(crudo('exo_institution_other'))
			: null,
		exo_article: articulo === null ? null : Number(articulo),
		exo_subsection: crudo('exo_subsection') === null ? null : Number(crudo('exo_subsection')),
		exo_date: String(fecha).slice(0, 10),
		exo_points: puntos
	};
}

route('GET', '/clients/clients_list', ({ companyId }) => getDb(companyId).clients);

/**
 * El tipo de identificación con que se guarda un cliente (T-617). Espejo de
 * `hacienda.client_identification_type`: el elegido, o el que deja ver la
 * longitud de la cédula; si tampoco así se sabe, no se guarda.
 */
function tipoDeIdentificacion(pedido: unknown, identificacion: string): string {
	const tipo = String(pedido ?? '').trim();
	if (tipo) {
		if (!isIdentificationType(tipo)) fail(400, 'invalid_identification_type', { identification_type: tipo });
		return tipo;
	}
	const deducido = identificationTypeFor(identificacion);
	if (!deducido) fail(400, 'identification_type_required');
	return deducido;
}

/** La dirección de un cliente del extranjero (RF-78), limpia; nula en blanco. */
function senasExtranjeras(valor: unknown): string | null {
	const limpia = String(valor ?? '').trim();
	if (!limpia) return null;
	if (limpia.length > FOREIGN_ADDRESS_MAX_LENGTH)
		fail(400, 'invalid_foreign_address', { max_length: FOREIGN_ADDRESS_MAX_LENGTH });
	return limpia;
}

route('POST', '/clients/register_client', ({ body, companyId }) => {
	exigirModulo(companyId, 'clients'); // QA-01
	const db = getDb(companyId);
	const identification = String(body?.identification ?? '').trim();
	if (db.clients.some((c) => c.identification === identification))
		fail(400, 'client_identification_taken');
	const identificationType = tipoDeIdentificacion(body?.identification_type, identification);
	const foreignAddress = senasExtranjeras(body?.foreign_address);
	const id = nextId('clients');
	db.clients.push({
		id_client: id,
		identification,
		identification_type: identificationType,
		name: String(body?.name ?? ''),
		last_name: String(body?.last_name ?? ''),
		second_name: String(body?.second_name ?? ''),
		email: String(body?.email ?? ''),
		telephone: Number(body?.telephone ?? 0),
		address: String(body?.address ?? ''),
		foreign_address: foreignAddress,
		register_date: String(body?.register_date ?? nowIso().slice(0, 10)),
		...revisarExoneracion(body)
	});
	persist();
	return { message: 'client_registered', id_client: id };
});

route('PUT', '/clients/update_client/:id', ({ params, body, companyId }) => {
	exigirModulo(companyId, 'clients'); // QA-01
	const db = getDb(companyId);
	const id = Number(params[0]);
	const client = db.clients.find((c) => c.id_client === id);
	if (!client) fail(404, 'client_not_found');
	// La exoneración se comprueba y se asigna entera, antes del bucle: sus ocho
	// campos se ponen y se quitan juntos, y el nulo en ellos **es** un valor.
	for (const [key, value] of Object.entries(revisarExoneracion(body)))
		(client as any)[key] = value;
	// El tipo se cambia solo si viene con valor (T-617): en blanco es «no lo toqué».
	const tipo = String(body?.identification_type ?? '').trim();
	if (tipo) {
		if (!isIdentificationType(tipo)) fail(400, 'invalid_identification_type', { identification_type: tipo });
		client.identification_type = tipo;
	}
	// Las señas extranjeras se ponen y se quitan con el campo (T-727): en blanco
	// es «ya no», no «no lo toqué».
	if (body && 'foreign_address' in body) client.foreign_address = senasExtranjeras(body.foreign_address);
	for (const [key, value] of Object.entries(body ?? {})) {
		if ((CAMPOS_EXONERACION as readonly string[]).includes(key)) continue;
		if (key === 'identification_type' || key === 'foreign_address') continue;
		if (value == null || value === '') continue;
		if (key === 'telephone') client.telephone = Number(value);
		else if (key in client) (client as any)[key] = value;
	}
	persist();
	return { message: 'client_updated', id_client: id };
});

// ------------------------------------------------------------------ productos

/** Columnas donde el nulo **es un valor**. Espejo de `crud_product.VACIABLES`. */
const VACIABLES = new Set(['cabys_code', 'tax_rate', 'tax_code', 'tariff_heading']);

/** La partida saneada (T-727), nula si viene vacía, o 400. Espejo de `crud_product`. */
function partidaArancelaria(valor: unknown): string | null {
	const limpia = String(valor ?? '').trim();
	if (!limpia) return null;
	if (!isTariffHeading(limpia)) fail(400, 'invalid_tariff_heading', { tariff_heading: String(valor) });
	return limpia;
}

/**
 * La nota 8.1 del anexo de Hacienda: once códigos para nueve porcentajes.
 * Espejo de `app/domain/fe_tax_codes.py`.
 *
 * El `01` (0 % con derecho a crédito pleno) y el `11` (0 % sin derecho) son el
 * mismo número con derechos opuestos, así que **el código no se deduce de la
 * tarifa**; la tarifa sí se deduce del código, y eso es lo que hace esta tabla.
 */
const TARIFAS_IVA: Record<string, { rate: number; onlyInNotes: boolean }> = {
	'01': { rate: 0, onlyInNotes: false },
	'02': { rate: 0.01, onlyInNotes: false },
	'03': { rate: 0.02, onlyInNotes: false },
	'04': { rate: 0.04, onlyInNotes: false },
	'05': { rate: 0, onlyInNotes: true },
	'06': { rate: 0.04, onlyInNotes: true },
	'07': { rate: 0.08, onlyInNotes: true },
	'08': { rate: 0.13, onlyInNotes: false },
	'09': { rate: 0.005, onlyInNotes: false },
	'10': { rate: 0, onlyInNotes: false },
	'11': { rate: 0, onlyInNotes: false }
};

/** El código limpio y su tarifa, o 400. Espejo de `crud_product.codigo_y_tarifa`. */
function codigoYTarifa(crudo: unknown): [string, number] {
	const codigo = String(crudo ?? '').trim();
	const fila = TARIFAS_IVA[codigo];
	if (!fila) fail(400, 'invalid_tax_code', { tax_code: String(crudo) });
	return [codigo, fila.rate];
}

/**
 * El código que le toca a una tarifa, o `null` si hay más de uno.
 * Espejo de `fe_tax_codes.suggested_code`: en el 0 % hay tres y la diferencia
 * es el derecho a crédito del cliente, así que no se propone ninguno.
 */
function codigoSugerido(tarifa: number): string | null {
	const posibles = Object.entries(TARIFAS_IVA).filter(
		([, f]) => !f.onlyInNotes && f.rate === tarifa
	);
	return posibles.length === 1 ? posibles[0][0] : null;
}

route('GET', '/products/products_list', ({ companyId }) => getDb(companyId).products);

route('POST', '/products/add_product', ({ body, companyId, userId }) => {
	exigirModulo(companyId, 'inventory'); // QA-01
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
		// Nace en cero y la apertura de abajo le pone lo suyo (RF-94).
		stock: 0,
		barcode,
		created_at: nowIso(),
		category_id: Number(body?.category_id ?? 0),
		// F5: en nulo significa «la tasa configurada del negocio» (RN-9).
		cabys_code: body?.cabys_code != null ? String(body.cabys_code) : null,
		// F7: con código de Hacienda la tarifa sale de él (RN-76).
		tax_rate: body?.tax_code
			? codigoYTarifa(body.tax_code)[1]
			: body?.tax_rate != null
				? Number(body.tax_rate)
				: null,
		tax_code: body?.tax_code ? codigoYTarifa(body.tax_code)[0] : null,
		unit_of_measure: String(body?.unit_of_measure ?? 'Unid'),
		tariff_heading: partidaArancelaria(body?.tariff_heading)
	});
	// La existencia inicial es un movimiento de apertura en el kárdex (RN-98),
	// a costo cero: no se conoce hasta la primera compra.
	const inicial = Math.trunc(Number(body?.stock ?? 0));
	if (inicial) {
		moverStock(companyId, {
			product: db.products.find((p) => p.id_product === id)!,
			delta: inicial,
			kind: 'opening',
			unit_cost: 0,
			source_type: 'product',
			source_id: id,
			user_id: userId
		});
	}
	persist();
	return { message: 'product_registered', id_product: id };
});

route('PUT', '/products/update_product/:id', ({ params, body, companyId }) => {
	exigirModulo(companyId, 'inventory'); // QA-01
	const db = getDb(companyId);
	const id = Number(params[0]);
	const product = db.products.find((p) => p.id_product === id);
	if (!product) fail(404, 'product_not_found', { product_id: id });
	// F15 (RN-98): la existencia se mueve con una entrada, una salida o una
	// toma, nunca desde la ficha. Mismo código que `crud_product.py`.
	if (body?.stock != null) fail(400, 'stock_not_editable', { product_id: id });
	if (body?.barcode && db.products.some((p) => p.id_product !== id && p.barcode === body.barcode))
		fail(400, 'barcode_taken', { barcode: String(body.barcode) });
	// Mover de categoría pasa por la misma regla que crear (RN-6). Solo si de
	// verdad cambia: revalidar la que ya tiene haría que un cambio de precio
	// fallara por una categoría que se desactivó después.
	const categoriaNueva = body?.category_id == null ? null : Number(body.category_id);
	if (categoriaNueva !== null && categoriaNueva !== product.category_id)
		categoriaParaProducto(companyId, categoriaNueva);
	// El código de Hacienda manda sobre la tarifa (RN-76): si viene, la reescribe
	// aunque el formulario haya mandado otra.
	if (body?.tax_code) {
		const [codigo, tarifa] = codigoYTarifa(body.tax_code);
		body = { ...body, tax_code: codigo, tax_rate: tarifa };
	}
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
		else if (key === 'tax_code')
			product.tax_code = value === '' || value == null ? null : String(value);
		else if (key === 'tariff_heading') product.tariff_heading = partidaArancelaria(value);
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
	exigirModulo(companyId, 'inventory'); // QA-01
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

	// El CABYS trae una tarifa, no un código de Hacienda. Se pone el de la nota
	// 8.1 solo cuando esa tarifa deja una sola posibilidad (RN-76).
	const codigoIVA = codigoSugerido(tarifa);
	for (const producto of productos) {
		producto!.cabys_code = codigo;
		producto!.tax_rate = tarifa;
		producto!.tax_code = codigoIVA;
	}
	persist();
	return { message: 'cabys_assigned', updated: productos.length };
});

route('DELETE', '/products/delete_product/:id', ({ params, companyId }) => {
	exigirModulo(companyId, 'inventory'); // QA-01
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
	exigirModulo(companyId, 'inventory'); // QA-01
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
	exigirModulo(companyId, 'inventory'); // QA-01
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
	exigirModulo(companyId, 'inventory'); // QA-01
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
	exigirModulo(companyId, 'inventory'); // QA-01
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

// ------------------------------------------------ numeración (T-704, T-705)
//
// La misma aritmética que `domain/fe_key.py`: consecutivo de 20 —oficina, caja,
// tipo y secuencia— y clave de 50 —país, fecha, emisor, consecutivo, situación
// y código de seguridad—. La serie es por tipo y por ambiente, y el número se
// toma después de que todo lo que podía decir que no, dijo que sí.

/** El día de la emisión en Costa Rica, `ddmmyy`: la hora del simulado es UTC. */
function fechaDeLaClave(iso: string): string {
	const partes = new Intl.DateTimeFormat('en-GB', {
		timeZone: 'America/Costa_Rica',
		day: '2-digit',
		month: '2-digit',
		year: '2-digit'
	}).formatToParts(new Date(iso));
	const parte = (tipo: string) => partes.find((p) => p.type === tipo)?.value ?? '00';
	return `${parte('day')}${parte('month')}${parte('year')}`;
}

interface EmisorSimulado {
	identification: string;
	environment: 'sandbox' | 'production';
	economic_activity: string | null;
	branch_code: string;
	terminal_code: string;
}

/**
 * El emisor, o el «no» de `NumberDocument.prepare`: sin cédula —o con una que no
 * cabe en la clave— no hay comprobante (RN-45).
 */
function prepararNumeracion(companyId: number): EmisorSimulado {
	const empresa = getRoot().companies.find((c) => c.id === companyId);
	const cedula = (empresa?.identificacion ?? '').replace(/[-\s]/g, '');
	if (!cedula) fail(409, 'issuer_identification_required', { reason: 'missing' });
	if (!/^\d{1,12}$/.test(cedula)) fail(409, 'issuer_identification_required', { reason: 'invalid' });
	const ajustes = mergeSettings(settingsRow(companyId).data);
	return {
		identification: cedula,
		environment: ajustes.eInvoicing.environment,
		economic_activity: ajustes.eInvoicing.economicActivity || null,
		branch_code: empresa?.branch_code ?? '001',
		terminal_code: empresa?.terminal_code ?? '00001'
	};
}

function numerar(
	companyId: number,
	emisor: EmisorSimulado,
	origen: { source_type: MockFeDocument['source_type']; source_id: number; document_type: string; issued_at: string }
): MockFeDocument {
	const empresa = getEmpresa(companyId);
	const series = (empresa.fe_sequences ??= {});
	const serie = `${origen.document_type}|${emisor.environment}`;
	const ultima = series[serie] ?? 0;
	const secuencia = ultima >= 9_999_999_999 ? 1 : ultima + 1;
	series[serie] = secuencia;

	const consecutivo = `${emisor.branch_code}${emisor.terminal_code}${origen.document_type}${String(secuencia).padStart(10, '0')}`;
	const seguridad = String(Math.floor(Math.random() * 100_000_000)).padStart(8, '0');
	const clave = `506${fechaDeLaClave(origen.issued_at)}${emisor.identification.padStart(12, '0')}${consecutivo}1${seguridad}`;
	const documento: MockFeDocument = {
		...origen,
		id: nextId('fe_documents'),
		environment: emisor.environment,
		sequence: secuencia,
		consecutive: consecutivo,
		clave,
		situation: '1',
		economic_activity: emisor.economic_activity,
		status: 'numbered',
		events: []
	};
	(empresa.fe_documents ??= []).push(documento);
	return documento;
}

// ------------------------------------------- el arranque de las series (T-616)
//
// Como `crud_fe_sequences`. El simulado numera con una sola oficina —la de la
// sesión, ver `numerar`—, así que lista esa caja y rechaza las demás.

function cajaDeLaSesion(companyId: number) {
	// La misma oficina que pone `prepararNumeracion`: la del registro de la compañía.
	const registro = getRoot().companies.find((c) => c.id === companyId);
	const cajas = cajasDe(companyId);
	const caja = cajas.find((c) => c.codigo === (registro?.terminal_code ?? '00001')) ?? cajas[0];
	const sucursal = sucursalesDe(companyId).find((s) => s.id === caja?.branch_id);
	return { caja, sucursal };
}

function serieUsada(companyId: number, tipo: string, ambiente: string): boolean {
	return (getEmpresa(companyId).fe_documents ?? []).some(
		(d) => d.document_type === tipo && d.environment === ambiente
	);
}

route('GET', '/fe/sequences', ({ userId, companyId }) => {
	exigirAdmin(userId, companyId);
	const ambiente = ambienteActivo(companyId);
	const tipos = [...mergeSettings(settingsRow(companyId).data).eInvoicing.documentTypes].sort();
	const { caja, sucursal } = cajaDeLaSesion(companyId);
	if (!caja) return { environment: ambiente, items: [] };
	const series = getEmpresa(companyId).fe_sequences ?? {};
	return {
		environment: ambiente,
		items: tipos.map((tipo) => ({
			terminal_id: caja.id,
			branch_code: sucursal?.codigo ?? '001',
			branch_name: sucursal?.nombre ?? '',
			terminal_code: caja.codigo,
			terminal_name: caja.nombre,
			document_type: tipo,
			last_number: series[`${tipo}|${ambiente}`] ?? 0,
			in_use: serieUsada(companyId, tipo, ambiente)
		}))
	};
});

route('PUT', '/fe/sequences', ({ body, userId, companyId }) => {
	const user = exigirAdmin(userId, companyId);
	const ambiente = ambienteActivo(companyId);
	const tipo = String(body?.document_type ?? '');
	if (!mergeSettings(settingsRow(companyId).data).eInvoicing.documentTypes.includes(tipo))
		fail(400, 'invalid_sale_document_type', { document_type: tipo });
	const { caja, sucursal } = cajaDeLaSesion(companyId);
	const pedidaCaja = Number(body?.terminal_id);
	if (!caja || caja.id !== pedidaCaja) fail(404, 'terminal_not_found', { terminal_id: pedidaCaja });

	const pedido = body?.last_number;
	if (!Number.isInteger(pedido) || pedido < 0 || pedido > 9_999_999_999)
		fail(400, 'invalid_sequence_start', { value: String(pedido) });
	if (serieUsada(companyId, tipo, ambiente)) fail(409, 'sequence_in_use', { document_type: tipo });
	const empresa = getEmpresa(companyId);
	const clave = `${tipo}|${ambiente}`;
	const antes = empresa.fe_sequences?.[clave] ?? 0;
	if (pedido < antes) fail(409, 'sequence_cannot_go_down', { current: antes, requested: pedido });

	(empresa.fe_sequences ??= {})[clave] = pedido;
	registrar(
		user.id_user,
		companyId,
		'serie_arranque',
		`${tipo} ${sucursal?.codigo ?? '001'}-${caja.codigo} (${ambiente}): ${antes} → ${pedido}`
	);
	persist();
	return { terminal_id: caja.id, document_type: tipo, environment: ambiente, last_number: pedido };
});

// ----------------------------------------------------------- el recorrido (F7)
//
// La de verdad tiene una cola que firma, envía y consulta con sus cadencias
// (`domain/fe_transmission.py`). El simulado no tiene hilos: avanza cada
// documento **cuando alguien lo lee**, por el tiempo que pasó desde que se
// numeró (o desde que se reintentó a mano), con los mismos estados y el mismo
// contrato. Con el certificado y las credenciales del ambiente cargados, un
// comprobante tarda unos segundos en quedar aceptado; sin ellos se detiene en
// la firma o en el envío y dice qué falta, que es lo que la pantalla tiene que
// saber enseñar.

const SEGUNDOS = { firmado: 2, enviado: 4, aceptado: 7 };

function listoParaEmitir(companyId: number, environment: 'sandbox' | 'production') {
	const salida = feSalida(feFila(companyId, environment));
	return { certificado: salida.certificate_configured && salida.certificate_status !== 'expired', atv: salida.atv_configured };
}

function masTarde(desde: string, segundos: number): string {
	return new Date(new Date(desde).getTime() + segundos * 1000).toISOString();
}

/** El estado que le toca por el tiempo transcurrido; escribe las huellas una sola vez. */
function avanzar(companyId: number, d: MockFeDocument): MockFeDocument {
	if (!d.status) d.status = 'numbered';
	if (!d.events) d.events = [];
	if (!d.id) d.id = nextId('fe_documents');
	if (d.status === 'accepted' || d.status === 'rejected' || d.status === 'stopped') return d;
	const desde = d.resumed_at ?? d.issued_at;
	const transcurrido = (Date.now() - new Date(desde).getTime()) / 1000;
	const listo = listoParaEmitir(companyId, d.environment);

	if (d.status === 'numbered' && transcurrido >= SEGUNDOS.firmado) {
		if (!listo.certificado) {
			d.status = 'stopped';
			d.stop_reason = 'certificate_missing';
			d.events.push({ at: masTarde(desde, SEGUNDOS.firmado), event: 'stopped', detail: 'certificate_missing' });
			persist();
			return d;
		}
		d.status = 'signed';
		d.signed_at = masTarde(desde, SEGUNDOS.firmado);
		d.events.push({ at: d.signed_at, event: 'signed' });
	}
	if (d.status === 'signed' && transcurrido >= SEGUNDOS.enviado) {
		if (!listo.atv) {
			d.status = 'stopped';
			d.stop_reason = 'credentials_missing';
			d.events.push({ at: masTarde(desde, SEGUNDOS.enviado), event: 'stopped', detail: 'credentials_missing' });
			persist();
			return d;
		}
		d.status = 'sent';
		d.sent_at = masTarde(desde, SEGUNDOS.enviado);
		d.hacienda_status = 'recibido';
		d.events.push({ at: d.sent_at, event: 'sent' });
	}
	if (d.status === 'sent' && transcurrido >= SEGUNDOS.aceptado) {
		// Una clave que termina en 99 se rechaza: es la forma de ver ese camino.
		const rechazada = d.clave.endsWith('99');
		d.status = rechazada ? 'rejected' : 'accepted';
		d.hacienda_status = rechazada ? 'rechazado' : 'aceptado';
		d.resolved_at = masTarde(desde, SEGUNDOS.aceptado);
		d.stop_detail = rechazada ? 'Rechazado en el simulado: la clave termina en 99' : 'Aceptado en el simulado';
		d.events.push({ at: d.resolved_at, event: rechazada ? 'rejected' : 'accepted', detail: d.stop_detail });
	}
	persist();
	return d;
}

function documentoOut(d: MockFeDocument) {
	const pendiente = d.status === 'numbered' || d.status === 'signed' || d.status === 'sent';
	return {
		id: d.id,
		clave: d.clave,
		consecutive: d.consecutive,
		environment: d.environment,
		economic_activity: d.economic_activity,
		situation: d.situation,
		document_type: d.document_type,
		source_type: d.source_type,
		source_id: d.source_id,
		status: d.status,
		stop_reason: d.stop_reason ?? null,
		stop_detail: d.stop_detail ?? null,
		hacienda_status: d.hacienda_status ?? null,
		failures: 0,
		polls: d.status === 'sent' ? 1 : d.resolved_at ? 1 : 0,
		issued_at: d.issued_at,
		signed_at: d.signed_at ?? null,
		sent_at: d.sent_at ?? null,
		resolved_at: d.resolved_at ?? null,
		last_attempt_at: d.resolved_at ?? d.sent_at ?? d.signed_at ?? null,
		next_attempt_at: pendiente ? masTarde(d.resumed_at ?? d.issued_at, SEGUNDOS.aceptado) : null,
		has_xml: Boolean(d.signed_at),
		has_response: Boolean(d.resolved_at)
	};
}

function documentoPorId(companyId: number, id: number): MockFeDocument {
	const hallado = (getEmpresa(companyId).fe_documents ?? []).find((d) => d.id === id);
	if (!hallado) fail(404, 'document_not_found', { document_id: id });
	return avanzar(companyId, hallado);
}

function expedienteOut(companyId: number, d: MockFeDocument) {
	return {
		document: documentoOut(d),
		source_type: d.source_type,
		source_id: d.source_id,
		events: (d.events ?? []).map((e) => ({ at: e.at, event: e.event, detail: e.detail ?? null }))
	};
}

/** Un XML con la forma del de verdad, para que la pantalla tenga qué bajar. */
function xmlSimulado(d: MockFeDocument): string {
	const raiz =
		{
			'01': 'FacturaElectronica',
			'02': 'NotaDebitoElectronica',
			'03': 'NotaCreditoElectronica',
			'04': 'TiqueteElectronico',
			'08': 'FacturaElectronicaCompra',
			'09': 'FacturaElectronicaExportacion'
		}[d.document_type] ?? 'TiqueteElectronico';
	return (
		`<?xml version='1.0' encoding='utf-8'?><${raiz} xmlns="https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.4/${raiz[0].toLowerCase()}${raiz.slice(1)}">` +
		`<Clave>${d.clave}</Clave><NumeroConsecutivo>${d.consecutive}</NumeroConsecutivo><FechaEmision>${d.issued_at}</FechaEmision>` +
		`<ds:Signature xmlns:ds="http://www.w3.org/2000/09/xmldsig#" Id="xades-Signature-simulada"><ds:SignatureValue>simulada</ds:SignatureValue></ds:Signature></${raiz}>`
	);
}

function respuestaSimulada(d: MockFeDocument): string {
	const mensaje = d.status === 'rejected' ? '3' : '1';
	return (
		`<?xml version="1.0" encoding="utf-8"?><MensajeHacienda xmlns="https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.4/mensajeHacienda">` +
		`<Clave>${d.clave}</Clave><Mensaje>${mensaje}</Mensaje><DetalleMensaje>${d.stop_detail ?? ''}</DetalleMensaje></MensajeHacienda>`
	);
}

function archivo(nombre: string, contenido: string) {
	return { __file: { filename: nombre, content: contenido, content_type: 'application/xml; charset=utf-8' } };
}

route('GET', '/fe/queue', ({ companyId }) => {
	const docs = (getEmpresa(companyId).fe_documents ?? []).map((d) => avanzar(companyId, d));
	const counts: Record<string, number> = { numbered: 0, signed: 0, sent: 0, accepted: 0, rejected: 0, retrying: 0, stopped: 0 };
	for (const d of docs) counts[d.status ?? 'numbered'] = (counts[d.status ?? 'numbered'] ?? 0) + 1;
	const pendientes = docs.filter((d) => ['numbered', 'signed', 'sent', 'retrying'].includes(d.status ?? ''));
	const masViejo = pendientes.map((d) => d.issued_at).sort()[0] ?? null;
	const edadHoras = masViejo ? (Date.now() - new Date(masViejo).getTime()) / 3_600_000 : 0;
	return {
		counts,
		pending: pendientes.length,
		stopped: docs.filter((d) => d.status === 'stopped').sort((a, b) => a.issued_at.localeCompare(b.issued_at)).map(documentoOut),
		oldest_pending_at: masViejo,
		alarm: edadHoras >= 120 ? 'danger' : edadHoras >= 24 ? 'warning' : 'ok',
		contingency: false
	};
});

route('GET', '/fe/documents/:id', ({ params, companyId }) => {
	return expedienteOut(companyId, documentoPorId(companyId, Number(params[0])));
});

route('GET', '/fe/documents/:id/xml', ({ params, companyId }) => {
	const d = documentoPorId(companyId, Number(params[0]));
	if (!d.signed_at) fail(409, 'document_not_signed', { document_id: d.id, status: d.status });
	return archivo(`${d.clave}.xml`, xmlSimulado(d));
});

route('GET', '/fe/documents/:id/response', ({ params, companyId }) => {
	const d = documentoPorId(companyId, Number(params[0]));
	if (!d.resolved_at) fail(409, 'document_not_resolved', { document_id: d.id, status: d.status });
	return archivo(`${d.clave}-respuesta.xml`, respuestaSimulada(d));
});

route('POST', '/fe/documents/:id/retry', ({ params, userId, companyId }) => {
	const user = exigirAdmin(userId, companyId);
	const d = documentoPorId(companyId, Number(params[0]));
	if (d.status !== 'stopped') fail(409, 'document_not_stopped', { document_id: d.id, status: d.status });
	// Vuelve al paso que le tocaba: si ya estaba firmado, a enviar; si no, a firmar.
	d.status = d.sent_at ? 'sent' : d.signed_at ? 'signed' : 'numbered';
	d.stop_reason = null;
	d.stop_detail = null;
	d.resumed_at = nowIso();
	(d.events ??= []).push({ at: d.resumed_at, event: 'resumed', detail: `user:${user.id_user}` });
	registrar(user.id_user, companyId, 'fe_reintento', `${d.clave} ← reintento`);
	persist();
	return expedienteOut(companyId, d);
});

/** T-713: qué falta ver aceptado en pruebas para pasar a producción. */
function puertaDeProduccion(companyId: number) {
	const aceptados = new Set(
		(getEmpresa(companyId).fe_documents ?? [])
			.map((d) => avanzar(companyId, d))
			.filter((d) => d.status === 'accepted' && d.environment === 'sandbox')
			.map((d) => d.document_type)
	);
	const faltan = ['01', '04', '03'].filter((t) => !aceptados.has(t));
	return { ready: faltan.length === 0, missing: faltan };
}

/** El comprobante vigente de un origen, con la forma de `EinvoiceOut`. */
function comprobanteDe(companyId: number, source_type: MockFeDocument['source_type'], source_id: number) {
	const hallado = [...(getEmpresa(companyId).fe_documents ?? [])]
		.reverse()
		.find((d) => d.source_type === source_type && d.source_id === source_id);
	if (!hallado) return null;
	return documentoOut(avanzar(companyId, hallado));
}

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
		// Nulo y no ausente, como el backend: las ventas del seed no lo tienen.
		document_type: sale.document_type ?? null,
		returned,
		// RF-33: en qué va la venta ante Hacienda; nulo sin comprobante.
		einvoice_status: comprobanteDe(companyId, 'sale', sale.id)?.status ?? null
	};
}

route('GET', '/sales/sales_list', ({ companyId }) =>
	// `map(saleResponse)` le pasaba el índice como compañía: el comprobante de
	// cada venta salía de otra empresa o de ninguna.
	[...getDb(companyId).sales]
		.sort((a, b) => b.created_at.localeCompare(a.created_at))
		.map((venta) => saleResponse(venta, companyId))
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
		user_name: personName(sale.user_id),
		einvoice: comprobanteDe(companyId, 'sale', sale.id)
	};
});

function numeroDeVentaLibre(db: { sales: { sale_number: string }[] }): string {
	const ahora = new Date();
	const dos = (n: number) => String(n).padStart(2, '0');
	const base = `${ahora.getFullYear()}${dos(ahora.getMonth() + 1)}${dos(ahora.getDate())}${dos(ahora.getHours())}${dos(ahora.getMinutes())}${dos(ahora.getSeconds())}`;
	let candidato = base;
	let sufijo = 2;
	while (db.sales.some((s) => s.sale_number === candidato)) candidato = `${base}-${sufijo++}`;
	return candidato;
}

route('POST', '/sales/add_sale', ({ body, companyId, userId }) => {
	exigirModulo(companyId, 'sales'); // QA-01
	const db = getDb(companyId);
	// T-706: sin número, lo pone el servidor con su reloj —`yyyyMMddHHmmss` y un
	// sufijo si ese segundo ya tiene venta—, igual que `RegisterSale`.
	const saleNumber = String(body?.sale_number ?? '').trim() || numeroDeVentaLibre(db);
	if (db.sales.some((s) => s.sale_number === saleNumber))
		fail(400, 'duplicate_sale_number', { sale_number: saleNumber });

	// T-1104: el método de pago es un conjunto cerrado, y se comprueba antes de
	// tocar nada, como en `RegisterSale`: no depende de nada que haya que leer.
	const paymentMethod = String(body?.payment_method ?? '');
	if (!(PAYMENT_METHODS as readonly string[]).includes(paymentMethod))
		fail(400, 'invalid_sale_payment_method', { method: paymentMethod });

	const products = Array.isArray(body?.products) ? body.products : [];
	if (!products.length) fail(400, 'empty_sale');

	for (const line of products) {
		if (!Number(line?.id_product) || Math.trunc(Number(line?.stock ?? 0)) <= 0)
			fail(400, 'invalid_sale_line', { product_id: line?.id_product });
	}

	// El cliente tiene que ser de esta compañía (RN-85). En el backend la foránea
	// no sabe de compañías y el caso de uso lo pregunta; acá cada compañía tiene
	// su porción, así que basta con buscarlo en la suya.
	const clientId = body?.client_id != null ? Number(body.client_id) : null;
	const cliente = clientId === null ? null : db.clients.find((c) => c.id_client === clientId);
	if (clientId !== null && !cliente) fail(404, 'client_not_found', { client_id: clientId });
	// Quién es ante Hacienda (RN-87, T-727): al del extranjero se le exporta.
	const extranjero = isForeign(cliente?.identification_type);

	// El comprobante, con la misma regla y el mismo orden que
	// `domain/fe_document_type.py`: un valor desconocido se rechaza siempre, con
	// la facturación apagada no lleva tipo, sin pedirlo sale la sugerencia, y la
	// factura sin cliente no entra.
	const pedido = body?.document_type ?? null;
	if (pedido !== null && !isCounterDocumentType(pedido))
		fail(400, 'invalid_sale_document_type', { document_type: pedido });
	let documentType: string | null = null;
	if (einvoicingEnabled(companyId)) {
		// Lo que la compañía emite (RN-88), saneado como en el backend.
		const encendidos = enabledTypes(seccionElectronica(companyId)?.documentTypes);
		if (pedido === null)
			documentType = suggestedDocumentType(clientId !== null, encendidos, extranjero);
		else if (!encendidos.includes(pedido))
			fail(400, 'document_type_not_enabled', { document_type: pedido });
		else documentType = pedido;
		if (documentType === INVOICE && clientId === null) fail(400, 'invoice_needs_receiver');
		if (documentType === INVOICE && extranjero) fail(400, 'invoice_needs_resident');
		if (documentType === EXPORT_INVOICE && clientId === null) fail(400, 'export_needs_receiver');
		if (documentType === EXPORT_INVOICE && !extranjero) fail(400, 'export_needs_foreign_receiver');
		// La exportación lleva las señas del receptor en vez de su ubicación (RF-78).
		if (documentType === EXPORT_INVOICE && !hasForeignAddress(cliente?.foreign_address))
			fail(400, 'export_needs_foreign_address', { client_id: clientId });
	}

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
			),
			// El costo, congelado igual que la tarifa (RN-63). En cero significa
			// «nunca se compró», y eso se guarda como nulo: cero diría que fue
			// gratis y le inflaría el margen al negocio.
			unit_cost: (product.cost ?? 0) > 0 ? product.cost! : null,
			// El CABYS y la unidad, congelados igual (T-731, RN-86): el comprobante
			// los imprime por línea. La unidad nace en 'Unid', como la columna.
			cabys_code: product.cabys_code ?? null,
			unit_of_measure: product.unit_of_measure ?? 'Unid',
			// La partida, solo en la exportación (T-727): en una venta del país no
			// significa nada y no se congela.
			tariff_heading: documentType === EXPORT_INVOICE ? (product.tariff_heading ?? null) : null
		});
	}

	// Lo que una exportación exige de cada línea (RF-78, T-720), antes de la
	// plata y con el producto, como `RegisterSale`.
	if (documentType === EXPORT_INVOICE) {
		for (const item of items) {
			const product = db.products.find((p) => p.id_product === item.id_product)!;
			const problema = exportLineProblem(product);
			if (problema?.code === 'export_tariff_not_allowed')
				fail(400, 'export_tariff_not_allowed', {
					product_id: product.id_product,
					name: product.name,
					tax_code: problema.taxCode
				});
			if (problema?.code === 'export_line_needs_tariff_heading')
				fail(400, 'export_line_needs_tariff_heading', {
					product_id: product.id_product,
					name: product.name
				});
		}
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

	// El emisor antes de escribir nada, como `NumberDocument.prepare` (T-705).
	const emisor = documentType ? prepararNumeracion(companyId) : null;

	const id = nextId('sales');
	db.sales.push({
		id,
		sale_number: saleNumber,
		client_id: clientId,
		document_type: documentType,
		user_id: Number(body?.user_id ?? 0),
		subtotal: calculado.subtotal,
		tax: calculado.tax,
		total: calculado.total,
		payment_method: paymentMethod,
		cash_received: cashReceived,
		// El vuelto ni se recibe: se calcula. Así no puede venir negativo.
		change_given: changeDue(cashReceived, calculado.total),
		/*
		 * **La hora la pone el servidor, nunca el cliente** (spec §8, regla 2).
		 * El simulado hacía lo contrario y el efecto era grande: el POS manda su
		 * hora **local** (`toLocalIso`) y el turno de caja se sella en UTC, así
		 * que en UTC−6 la venta quedaba seis horas por detrás de la apertura y
		 * caía fuera de la ventana del turno. En modo demo el arqueo mostraba
		 * «0 ventas» siempre, y el faltante o el sobrante salían por el monto
		 * entero de lo vendido.
		 */
		created_at: nowIso(),
		items
	});
	// El número y la clave con la venta, con su misma hora (T-704, T-705).
	if (emisor && documentType) {
		const venta = db.sales.find((v) => v.id === id)!;
		numerar(companyId, emisor, {
			source_type: 'sale',
			source_id: id,
			document_type: documentType,
			issued_at: venta.created_at
		});
	}
	// Cada línea deja su fila en el kárdex (RN-98), al promedio del momento.
	items.forEach((item, i) =>
		moverStock(companyId, {
			product: db.products.find((p) => p.id_product === item.id_product)!,
			delta: -item.quantity,
			kind: 'sale',
			unit_cost: Number(item.unit_cost ?? 0),
			source_type: 'sale',
			source_id: id,
			source_line: i + 1,
			user_id: userId
		})
	);

	// El asiento, en el mismo paso que la venta (RN-59). Con contabilidad
	// apagada no hace nada.
	asentar(companyId, () =>
		postSale(
			companyId,
			{ id, date: nowIso().slice(0, 10), payment_method: paymentMethod },
			items.map((i) => ({
				subtotal: i.subtotal,
				tax: i.tax_amount ?? 0,
				tax_rate: i.tax_rate ?? tasaDelNegocio,
				quantity: i.quantity,
				unit_cost: i.unit_cost ?? null
			})),
			Number(body?.user_id ?? 0)
		)
	);

	persist();
	return { message: 'sale_registered', id_sale: id };
});

// --------------------------------------------------------------- devoluciones

/**
 * Una devolución como la devuelve el backend: con la nota y lo que la nota dice
 * del original. Las del seed y las guardadas antes de T-725 no traen esos
 * campos, y el backend los manda en nulo —o los lee de la venta—, así que acá
 * también.
 */
function returnResponse(r: SaleReturn, companyId: number): SaleReturn {
	const venta = getDb(companyId).sales.find((s) => s.id === r.sale_id);
	// Con qué CABYS y qué unidad se vendió cada producto: la nota lo repite (RN-86).
	const vendida = (id: number) => venta?.items.find((i) => i.id_product === id);
	return {
		...r,
		items: r.items.map((item) => ({
			...item,
			cabys_code: vendida(item.id_product)?.cabys_code ?? null,
			unit_of_measure: vendida(item.id_product)?.unit_of_measure ?? null
		})),
		document_type: r.document_type ?? null,
		reference_code: r.reference_code ?? null,
		sale_document_type: venta?.document_type ?? null,
		sale_created_at: venta?.created_at ?? null,
		sale_client_id: venta?.client_id ?? null,
		sale_payment_method: venta?.payment_method ?? null,
		// La NC numerada y la clave del original, que es como se referencia (T-705).
		einvoice: comprobanteDe(companyId, 'return', r.id),
		sale_clave: comprobanteDe(companyId, 'sale', r.sale_id)?.clave ?? null
	};
}

route('GET', '/returns/returns_list', ({ companyId }) =>
	[...getDb(companyId).returns]
		.sort((a, b) => b.created_at.localeCompare(a.created_at))
		.map((r) => returnResponse(r, companyId))
);

route('GET', '/returns/return/:id', ({ params, companyId }) => {
	const found = getDb(companyId).returns.find((r) => r.id === Number(params[0]));
	if (!found) fail(404, 'return_not_found');
	return returnResponse(found, companyId);
});

route('POST', '/returns/add_return', ({ body, companyId, userId }) => {
	exigirModulo(companyId, body?.annul === true ? 'invoices' : 'returns'); // QA-01
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

	// Anular es todo o nada (RN-89), y se mira antes que las cantidades, como en
	// `RegisterReturn`: anular una venta a medio devolver es «ya tiene
	// devoluciones», no «pidió de más».
	const anular = body?.annul === true;
	// Lo que las notas por monto le cambiaron a cada línea (T-726).
	const ajustes = ajustesDeNotas(companyId, sale.id);
	if (anular) {
		if ([...already.values()].some((cantidad) => cantidad > 0))
			fail(409, 'annul_after_return', { sale_id: sale.id });
		const pedido = new Map<number, number>();
		for (const line of requested) {
			const producto = Number(line?.id_product);
			pedido.set(producto, (pedido.get(producto) ?? 0) + Math.trunc(Number(line?.quantity ?? 0)));
		}
		const vendido = sale.items.filter((i) => i.quantity > 0);
		const entera =
			pedido.size === vendido.length && vendido.every((i) => pedido.get(i.id_product) === i.quantity);
		if (!entera) fail(400, 'annul_must_be_full', { sale_id: sale.id });
		// Con una ND encima no devolvería lo cobrado de más; con una NC, dos veces.
		if (ajustes.size) fail(409, 'annul_after_note', { sale_id: sale.id });
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
		// Con una NC por monto encima reembolsaría dos veces la misma plata (T-726).
		if ((ajustes.get(sold.id_product)?.restado ?? 0) > 0)
			fail(409, 'return_after_credit_note', { product_id: sold.id_product });
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

	// Cada línea con su tarifa y lo reembolsado de impuesto: lo desglosa la nota
	// impresa, como el backend lo guarda en `return_details`.
	for (const item of items) {
		const tarifa =
			sale.items.find((v) => v.id_product === item.id_product)?.tax_rate ?? delEncabezado;
		item.tax_rate = tarifa;
		item.tax_amount = lineTax(item.subtotal, tarifa);
	}

	// La nota la decide la venta ORIGINAL, no la configuración de hoy (RN-89):
	// mismo criterio que `fe_notes.credit_note_for_return`.
	const nota = sale.document_type
		? { document_type: '03', reference_code: anular ? '01' : '06' }
		: { document_type: null, reference_code: null };
	// El emisor antes de escribir, solo si hay nota (T-705).
	const emisorDeLaNota = nota.document_type ? prepararNumeracion(companyId) : null;

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
		items,
		...nota,
		// Lo que la nota impresa dice del original.
		sale_document_type: sale.document_type ?? null,
		sale_created_at: sale.created_at,
		sale_client_id: sale.client_id,
		sale_payment_method: sale.payment_method
	};
	db.returns.push(record);
	// La NC en su serie, la `03`, con la devolución.
	if (emisorDeLaNota && nota.document_type) {
		numerar(companyId, emisorDeLaNota, {
			source_type: 'return',
			source_id: id,
			document_type: nota.document_type,
			issued_at: record.created_at
		});
	}

	// El stock vuelve al inventario —lo que el sistema original nunca hacía— y
	// deja su fila en el kárdex **al costo con que salió** (RN-98, RN-63); anular
	// se ve como anulación, no como devolución.
	items.forEach((item, i) => {
		const product = db.products.find((p) => p.id_product === item.id_product);
		if (!product) return;
		moverStock(companyId, {
			product,
			delta: item.quantity,
			kind: anular ? 'sale_void' : 'return',
			unit_cost: Number(sale.items.find((s) => s.id_product === item.id_product)?.unit_cost ?? 0),
			source_type: 'return',
			source_id: id,
			source_line: i + 1,
			user_id: userId
		});
	});

	// El inverso de la venta, con la tarifa y el costo **de su venta** (RN-12,
	// RN-63): reponer al inventario por lo que cuesta hoy inventaría utilidad.
	asentar(companyId, () =>
		postReturn(
			companyId,
			{ id, date: nowIso().slice(0, 10) },
			items.map((i: any) => {
				const vendida = sale.items.find((v) => v.id_product === i.id_product);
				const tarifa = vendida?.tax_rate ?? delEncabezado;
				const base = round2(i.price * i.quantity);
				return {
					subtotal: base,
					tax: lineTax(base, tarifa),
					tax_rate: tarifa,
					quantity: i.quantity,
					unit_cost: vendida?.unit_cost ?? null
				};
			}),
			Number(body?.user_id ?? 0)
		)
	);

	persist();
	return { message: 'return_registered', id_return: id, total, document_type: nota.document_type };
});

// ------------------------------------------------------ notas por monto (T-726)
//
// Espejo de `RegisterAmountNote`. La ND se cobra con su medio y la NC sale de la
// gaveta; las dos ajustan líneas de la venta con la tarifa con que se cobraron.

/** Lo que las notas le sumaron (ND) y restaron (NC) a cada línea, con impuesto. */
function ajustesDeNotas(
	companyId: number,
	saleId: number
): Map<number, { sumado: number; restado: number }> {
	const ajustes = new Map<number, { sumado: number; restado: number }>();
	for (const nota of getDb(companyId).notes ?? []) {
		if (nota.sale_id !== saleId) continue;
		for (const item of nota.items) {
			const previo = ajustes.get(item.id_product) ?? { sumado: 0, restado: 0 };
			const total = round2(item.subtotal + item.tax_amount);
			if (nota.document_type === DEBIT_NOTE) previo.sumado = round2(previo.sumado + total);
			else previo.restado = round2(previo.restado + total);
			ajustes.set(item.id_product, previo);
		}
	}
	return ajustes;
}

function noteResponse(nota: AmountNote, companyId: number): AmountNote {
	const venta = getDb(companyId).sales.find((s) => s.id === nota.sale_id);
	return {
		...nota,
		sale_number: venta?.sale_number ?? '',
		sale_document_type: venta?.document_type ?? null,
		sale_created_at: venta?.created_at ?? null,
		sale_client_id: venta?.client_id ?? null,
		einvoice: comprobanteDe(companyId, 'note', nota.id),
		sale_clave: comprobanteDe(companyId, 'sale', nota.sale_id)?.clave ?? null
	};
}

route('POST', '/notes/add_note', ({ body, userId, companyId }) => {
	exigirModulo(companyId, 'invoices'); // QA-01
	// Solo el administrador (T-726): mueve plata sin mercadería.
	const actor = getRoot().users.find((u) => u.id_user === userId);
	if (!actor || (rolEn(actor.id_user, companyId) ?? actor.role) !== 'admin') fail(403, 'admin_only');

	const db = getDb(companyId);
	const sale = db.sales.find((s) => s.id === Number(body?.sale_id));
	if (!sale) fail(404, 'sale_not_found');
	if (!sale.document_type) fail(400, 'note_needs_document', { sale_id: sale.id });

	const tipo = String(body?.document_type ?? '');
	if (tipo !== DEBIT_NOTE && tipo !== CREDIT_NOTE) fail(400, 'invalid_note_type', { document_type: tipo });
	const motivo = String(body?.reference_code ?? '');
	if (motivo !== CORRECTS_AMOUNT)
		fail(400, 'invalid_note_reason', { document_type: tipo, reference_code: motivo });
	if (!enabledTypes(seccionElectronica(companyId)?.documentTypes).includes(tipo))
		fail(400, 'document_type_not_enabled', { document_type: tipo });

	const reason = String(body?.reason ?? '').trim();
	if (!reason) fail(400, 'note_reason_required');

	const esDebito = tipo === DEBIT_NOTE;
	const paymentMethod = esDebito ? String(body?.payment_method ?? '') : null;
	if (esDebito && !(PAYMENT_METHODS as readonly string[]).includes(paymentMethod!))
		fail(400, 'invalid_sale_payment_method', { method: paymentMethod });

	// Una línea pedida dos veces es una sola, con los montos sumados.
	const pedido = new Map<number, number>();
	for (const linea of Array.isArray(body?.items) ? body.items : []) {
		const producto = Number(linea?.id_product);
		pedido.set(producto, round2((pedido.get(producto) ?? 0) + Number(linea?.amount ?? 0)));
	}
	if (!pedido.size) fail(400, 'empty_note');

	const devuelto = new Map<number, number>();
	for (const previa of db.returns.filter((r) => r.sale_id === sale.id))
		for (const item of previa.items)
			devuelto.set(item.id_product, (devuelto.get(item.id_product) ?? 0) + item.quantity);
	const ajustes = ajustesDeNotas(companyId, sale.id);
	const delEncabezado =
		sale.subtotal > 0 ? sale.tax / sale.subtotal : configuredTaxRate(companyId);

	const items: AmountNoteItem[] = [];
	for (const [producto, monto] of pedido) {
		const vendida = sale.items.find((i) => i.id_product === producto);
		if (!vendida) fail(400, 'note_line_not_in_sale', { product_id: producto });
		if (!(monto > 0)) fail(400, 'invalid_note_amount', { product_id: producto });
		const tarifa = vendida.tax_rate ?? delEncabezado;
		// Con impuesto adentro: la base es el monto entre uno más la tarifa.
		const base = round2(monto / (1 + tarifa));
		const impuesto = lineTax(base, tarifa);
		if (!esDebito) {
			const cobrado = round2(vendida.price * vendida.quantity * (1 + tarifa));
			const yaDevuelto = round2(vendida.price * (devuelto.get(producto) ?? 0) * (1 + tarifa));
			const { sumado = 0, restado = 0 } = ajustes.get(producto) ?? {};
			const queda = round2(cobrado + sumado - yaDevuelto - restado);
			const pedidoTotal = round2(base + impuesto);
			if (pedidoTotal > queda)
				fail(400, 'credit_exceeds_line', {
					product_id: producto,
					available: queda,
					requested: pedidoTotal
				});
		}
		items.push({
			id_product: producto,
			name: vendida.name,
			subtotal: base,
			tax_rate: tarifa,
			tax_amount: impuesto,
			tax_code: vendida.tax_code ?? null,
			cabys_code: vendida.cabys_code ?? null,
			unit_of_measure: vendida.unit_of_measure ?? null
		});
	}

	const subtotal = round2(items.reduce((t, i) => t + i.subtotal, 0));
	const tax = round2(items.reduce((t, i) => t + i.tax_amount, 0));
	// La nota siempre es un comprobante: el emisor antes de escribir (T-705).
	const emisorDeLaNota = prepararNumeracion(companyId);
	const id = nextId('notes');
	const nota: AmountNote = {
		id,
		sale_id: sale.id,
		sale_number: sale.sale_number,
		user_id: Number(userId),
		user_name: personName(Number(userId)),
		created_at: nowIso(),
		document_type: tipo,
		reference_code: motivo,
		reason,
		payment_method: paymentMethod,
		subtotal,
		tax,
		total: round2(subtotal + tax),
		items
	};
	(getEmpresa(companyId).notes ??= []).push(nota);
	numerar(companyId, emisorDeLaNota, {
		source_type: 'note',
		source_id: id,
		document_type: tipo,
		issued_at: nota.created_at
	});

	// El asiento de la venta o el de la devolución, sin costo y con su origen.
	const vendidas = items.map((i) => ({
		subtotal: i.subtotal,
		tax: i.tax_amount,
		tax_rate: i.tax_rate,
		quantity: 1,
		unit_cost: null
	}));
	const fecha = nota.created_at.slice(0, 10);
	asentar(companyId, () =>
		esDebito
			? postSale(companyId, { id, date: fecha, payment_method: paymentMethod! }, vendidas, Number(userId), 'note')
			: postReturn(companyId, { id, date: fecha }, vendidas, Number(userId), 'note')
	);

	persist();
	return { message: 'note_registered', id_note: id, document_type: tipo, total: nota.total };
});

route('GET', '/notes/note/:id', ({ params, companyId }) => {
	const nota = (getDb(companyId).notes ?? []).find((n) => n.id === Number(params[0]));
	if (!nota) fail(404, 'note_not_found');
	return noteResponse(nota, companyId);
});

route('GET', '/notes/by_sale/:id', ({ params, companyId }) =>
	(getDb(companyId).notes ?? [])
		.filter((n) => n.sale_id === Number(params[0]))
		.sort((a, b) => a.created_at.localeCompare(b.created_at) || a.id - b.id)
		.map((n) => noteResponse(n, companyId))
);

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

	// Las notas por monto del mismo cajero en la misma ventana (T-726).
	const notas = (db.notes ?? []).filter(
		(n) => n.user_id === session.user_id && n.created_at >= from && n.created_at <= to
	);
	const debitos = notas.filter((n) => n.document_type === DEBIT_NOTE);
	const debitNotesTotal = round2(debitos.reduce((acc, n) => acc + n.total, 0));
	const debitNotesCash = round2(
		debitos.filter((n) => n.payment_method === 'Efectivo').reduce((acc, n) => acc + n.total, 0)
	);
	const creditNotesTotal = round2(
		notas.filter((n) => n.document_type === CREDIT_NOTE).reduce((acc, n) => acc + n.total, 0)
	);

	// Solo el efectivo afecta la gaveta: tarjeta y transferencia no pasan por caja.
	const expected = round2(
		session.opening_amount +
			cashSales +
			debitNotesCash +
			movementsIn -
			movementsOut -
			returnsTotal -
			creditNotesTotal
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
		returns_total: returnsTotal,
		debit_notes_total: debitNotesTotal,
		debit_notes_cash: debitNotesCash,
		credit_notes_total: creditNotesTotal
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
	exigirModulo(companyId, 'cash'); // QA-01
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
	exigirModulo(companyId, 'cash'); // QA-01
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

	// Contra «por clasificar»: el sistema sabe que entraron ₡5 000, no de dónde
	// salieron.
	asentar(companyId, () =>
		postCashMovement(
			companyId,
			{ id: movement.id, date: nowIso().slice(0, 10), type, amount },
			user
		)
	);

	persist();
	return movement;
});

route('POST', '/cash/close', ({ body, companyId }) => {
	exigirModulo(companyId, 'cash'); // QA-01
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

	// Un turno que cuadra no deja asiento: no pasó nada que anotar.
	asentar(companyId, () =>
		postCashClose(
			companyId,
			{ id: session.id, date: nowIso().slice(0, 10) },
			report.expected_amount,
			counted,
			user
		)
	);

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

	// Las notas por monto (T-726): la ND suma a lo vendido y la NC resta.
	const notasDelPeriodo = (db.notes ?? []).filter((n) => {
		const t = new Date(n.created_at).getTime();
		return t >= fromTs && t <= toTs;
	});
	const debitNotes = round2(
		notasDelPeriodo.filter((n) => n.document_type === DEBIT_NOTE).reduce((a, n) => a + n.total, 0)
	);
	const creditNotes = round2(
		notasDelPeriodo.filter((n) => n.document_type === CREDIT_NOTE).reduce((a, n) => a + n.total, 0)
	);

	// Periodo anterior de igual duración, para el porcentaje de variación.
	const span = toTs - fromTs;
	const previous = salesBetween(fromTs - span - 1, fromTs - 1, companyId);

	const summary: ReportSummary = {
		range: { from, to },
		sales_count: sales.length,
		gross_total: gross,
		returns_total: returnsTotal,
		debit_notes_total: debitNotes,
		credit_notes_total: creditNotes,
		net_total: round2(gross + debitNotes - returnsTotal - creditNotes),
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

// ------------------------------------------------------------- proveedores

route('GET', '/suppliers', ({ companyId, query }) => {
	const todos = getDb(companyId).suppliers ?? [];
	// Sin `require_module`: leer se puede siempre (RN-50).
	return query.get('incluir_inactivos') === 'true' ? todos : todos.filter((p) => p.is_active);
});

route('POST', '/suppliers', ({ body, companyId }) => {
	const db = getDb(companyId);
	exigirModulo(companyId, 'suppliers');
	validarIdentificacion(body);

	const identificacion = String(body?.identification ?? '').trim() || null;
	if (identificacion) {
		// La misma identificación es el mismo proveedor: dos fichas del mismo
		// mayorista se reparten sus compras y ninguno de los dos saldos sirve.
		const existente = (db.suppliers ?? []).find(
			(p) => (p.identification ?? '').trim() === identificacion
		);
		if (existente) {
			fail(400, 'supplier_identification_taken', {
				identification: identificacion,
				name: existente.name
			});
		}
	}

	const proveedor: Supplier = {
		id: nextId('suppliers'),
		identification_type: String(body?.identification_type ?? '').trim() || null,
		identification: identificacion,
		name: String(body?.name ?? '').trim(),
		email: String(body?.email ?? '').trim() || null,
		phone: String(body?.phone ?? '').trim() || null,
		payment_terms_days: Math.trunc(Number(body?.payment_terms_days ?? 0)) || 0,
		is_active: true
	};
	db.suppliers.push(proveedor);
	persist();
	return proveedor;
});

route('PUT', '/suppliers/:id', ({ params, body, companyId }) => {
	const db = getDb(companyId);
	exigirModulo(companyId, 'suppliers');
	const proveedor = (db.suppliers ?? []).find((p) => p.id === Number(params[0]));
	if (!proveedor) fail(404, 'supplier_not_found', { supplier_id: Number(params[0]) });
	validarIdentificacion(body);

	const identificacion = String(body?.identification ?? '').trim() || null;
	if (identificacion) {
		const otro = db.suppliers.find(
			(p) => p.id !== proveedor.id && (p.identification ?? '').trim() === identificacion
		);
		if (otro) {
			fail(400, 'supplier_identification_taken', {
				identification: identificacion,
				name: otro.name
			});
		}
	}

	if (body?.name != null) proveedor.name = String(body.name).trim();
	if (body?.identification_type !== undefined)
		proveedor.identification_type = String(body.identification_type ?? '').trim() || null;
	if (body?.identification !== undefined) proveedor.identification = identificacion;
	if (body?.email !== undefined) proveedor.email = String(body.email ?? '').trim() || null;
	if (body?.phone !== undefined) proveedor.phone = String(body.phone ?? '').trim() || null;
	if (body?.payment_terms_days != null)
		proveedor.payment_terms_days = Math.trunc(Number(body.payment_terms_days)) || 0;
	// No se borra: se desactiva. Sus compras respaldan el crédito fiscal.
	if (body?.is_active != null) proveedor.is_active = Boolean(body.is_active);

	persist();
	return proveedor;
});

/** Los dos «no» de la identificación de Hacienda, iguales a los del backend. */
function validarIdentificacion(body: Record<string, unknown> | null): void {
	const tipo = String(body?.identification_type ?? '').trim();
	if (!tipo) return;
	// Los seis de Hacienda (F7): el 06, no contribuyente, es a quien se le emite
	// la factura de compra (T-728).
	if (!isIdentificationType(tipo))
		fail(400, 'invalid_identification_type', { identification_type: tipo });
	if (!String(body?.identification ?? '').trim()) fail(400, 'identification_required');
}

// ------------------------------------------------ compras: lo compartido

/**
 * El costo del producto después de entrarle `quantity` a `unitCost` (RN-54).
 *
 * Con existencia menor o igual a cero, el costo es el de la compra: promediar
 * contra una existencia nula sería dividir entre cero, y contra una negativa
 * daría un costo negativo que se arrastraría a todos los asientos siguientes.
 */
function promedioPonderado(stock: number, cost: number, quantity: number, unitCost: number): number {
	if (stock <= 0) return round2(unitCost);
	return round2((cost * stock + unitCost * quantity) / (stock + quantity));
}

function sumarDias(desde: string, dias: number): string {
	const d = new Date(`${desde}T00:00:00`);
	d.setDate(d.getDate() + Math.max(0, dias));
	return d.toISOString().slice(0, 10);
}

/** Lo abonado a una compra. El saldo es su total menos esto (RN-55). */
function abonadoA(companyId: number, entryId: number): number {
	return round2(
		(getDb(companyId).supplier_payments ?? [])
			.filter((a) => a.entry_id === entryId)
			.reduce((suma, a) => suma + a.amount, 0)
	);
}

/**
 * Escribe un abono, y su salida de caja si fue en efectivo (RN-56).
 *
 * **La gaveta primero**, porque el abono la apunta. Quien decide si hace falta
 * turno abierto es el método: solo el efectivo sale de la caja, y un pago por
 * transferencia no la necesita —el administrador que registra facturas en la
 * oficina no tiene por qué tener caja—.
 */
function abonar(
	companyId: number,
	datos: {
		entryId: number;
		supplierId: number;
		amount: number;
		method: string;
		reference: string | null;
		reason: string;
		userId: number;
	}
): number {
	const db = getDb(companyId);
	const monto = round2(datos.amount);
	if (!(monto > 0)) fail(400, 'payment_not_positive');
	if (!['cash', 'transfer', 'other'].includes(datos.method))
		fail(400, 'invalid_payment_method', { method: datos.method });

	let cashMovementId: number | null = null;
	if (datos.method === 'cash') {
		const turno = db.cash_sessions.find(
			(s) => s.user_id === datos.userId && s.status === 'abierta'
		);
		if (!turno) fail(400, 'cash_no_open_session');
		if (!datos.reason.trim()) fail(400, 'cash_missing_reason');

		// El mismo cálculo del arqueo: sin esto, una salida de más deja el
		// esperado del turno en negativo y el corte Z deja de significar nada.
		const disponible = computeExpected(turno, companyId).expected_amount;
		if (round2(disponible - monto) < 0)
			fail(400, 'cash_insufficient', { available: disponible });

		cashMovementId = nextId('cash_movements');
		db.cash_movements.push({
			id: cashMovementId,
			session_id: turno.id,
			type: 'salida',
			amount: monto,
			reason: datos.reason.trim(),
			created_at: nowIso()
		});
	}

	const id = nextId('supplier_payments');
	db.supplier_payments.push({
		id,
		supplier_id: datos.supplierId,
		entry_id: datos.entryId,
		amount: monto,
		method: datos.method,
		reference: datos.reference,
		cash_movement_id: cashMovementId,
		user_id: datos.userId,
		paid_at: nowIso()
	});

	// Proveedores contra caja, banco o «por clasificar». La salida de caja de
	// arriba **no** deja asiento propio: lo deja este abono, o las dos juntas
	// sacarían de la gaveta el doble de lo que salió (RN-56).
	asentar(companyId, () =>
		postSupplierPayment(
			companyId,
			{ id, date: nowIso().slice(0, 10), amount: monto, method: datos.method },
			datos.userId
		)
	);
	return id;
}

// --------------------------------------- abonos y cuentas por pagar (F10)

route('POST', '/purchases/:id/payments', ({ params, body, companyId, userId }) => {
	const db = getDb(companyId);
	exigirModulo(companyId, 'purchases');
	const compra = db.stock_entries.find((e) => e.id === Number(params[0]));
	// Una entrada sin proveedor no genera cuenta por pagar (RN-52), así que
	// desde cuentas por pagar no existe: el mismo criterio del backend.
	if (!compra || compra.supplier_id == null) fail(404, 'entry_not_found');
	if (compra.status === 'anulada') fail(400, 'purchase_cancelled');

	const monto = round2(Number(body?.amount ?? 0));
	const saldo = round2(compra.total_cost - abonadoA(companyId, compra.id));
	// Se comprueba antes de tocar la gaveta: un abono que no cabe no puede
	// dejar una salida de caja escrita (RN-55).
	if (monto > saldo)
		fail(400, 'payment_exceeds_balance', {
			balance: saldo.toFixed(2),
			requested: monto.toFixed(2)
		});

	const id = abonar(companyId, {
		entryId: compra.id,
		supplierId: compra.supplier_id,
		amount: monto,
		method: String(body?.method ?? ''),
		reference: String(body?.reference ?? '').trim() || null,
		reason: String(body?.reason ?? ''),
		userId: Number(userId ?? 0)
	});
	const abono = db.supplier_payments.find((a) => a.id === id)!;
	persist();

	return {
		message: 'payment_registered',
		id_payment: id,
		balance: round2(saldo - monto),
		cash_movement_id: abono.cash_movement_id
	};
});

route('GET', '/payables', ({ query, companyId }) => {
	const db = getDb(companyId);
	const filtro = Number(query.get('supplier_id') ?? 0) || null;
	const hoy = nowIso().slice(0, 10);

	const tramos = [0, 30, 60, 90];
	const porTramo = new Map(tramos.map((t) => [t, 0]));
	const porProveedor = new Map<number, { supplier_id: number; name: string; balance: number; purchases: unknown[] }>();
	let total = 0;

	const compras = db.stock_entries
		// Solo compras aplicadas: anular revierte la cuenta por pagar (RN-57) y
		// una entrada sin proveedor no debe nada (RN-52).
		.filter((e) => e.supplier_id != null && e.status === 'aplicada')
		.filter((e) => !filtro || e.supplier_id === filtro)
		.sort((a, b) => (a.due_date ?? '9999').localeCompare(b.due_date ?? '9999') || a.id - b.id);

	for (const compra of compras) {
		const pagado = abonadoA(companyId, compra.id);
		const saldo = round2(Math.max(0, compra.total_cost - pagado));
		// Una pagada ya no es una cuenta por pagar.
		if (saldo <= 0) continue;

		const proveedor = (db.suppliers ?? []).find((p) => p.id === compra.supplier_id);
		const tramo = tramoDe(compra.due_date ?? null, hoy);
		const bloque = porProveedor.get(compra.supplier_id!) ?? {
			supplier_id: compra.supplier_id!,
			name: proveedor?.name ?? compra.supplier ?? '',
			balance: 0,
			purchases: []
		};
		bloque.purchases.push({
			entry_id: compra.id,
			document_number: compra.document_number,
			document_date: compra.document_date ?? null,
			due_date: compra.due_date ?? null,
			total: compra.total_cost,
			paid: pagado,
			balance: saldo,
			bucket: tramo,
			days_overdue: compra.due_date ? diasEntre(compra.due_date, hoy) : null
		});
		bloque.balance = round2(bloque.balance + saldo);
		porProveedor.set(compra.supplier_id!, bloque);
		porTramo.set(tramo, round2((porTramo.get(tramo) ?? 0) + saldo));
		total = round2(total + saldo);
	}

	return {
		as_of: hoy,
		total,
		// Los cuatro siempre: una tabla que cambia de columnas según los datos se
		// lee distinto cada vez.
		by_bucket: tramos.map((t) => ({ bucket: t, balance: porTramo.get(t) ?? 0 })),
		suppliers: [...porProveedor.values()].sort((a, b) => b.balance - a.balance)
	};
});

route('GET', '/reports/purchases', ({ query, companyId }) => {
	const db = getDb(companyId);
	const { from, to } = parseRange(query);

	const porTarifa = new Map<number, { tax_rate: number; base: number; tax: number }>();
	for (const compra of db.stock_entries) {
		if (compra.supplier_id == null || compra.status !== 'aplicada') continue;
		// Por la fecha DEL DOCUMENTO: una factura del 28 digitada el 3 es IVA del
		// mes de la factura. La de carga es el respaldo cuando no la trae.
		const dia = (compra.document_date ?? compra.created_at).slice(0, 10);
		if (dia < from || dia > to) continue;

		for (const linea of compra.lines) {
			const tarifa = round2(Number(linea.tax_rate ?? 0));
			const fila = porTarifa.get(tarifa) ?? { tax_rate: tarifa, base: 0, tax: 0 };
			fila.base = round2(fila.base + linea.subtotal);
			fila.tax = round2(fila.tax + Number(linea.tax_amount ?? 0));
			porTarifa.set(tarifa, fila);
		}
	}

	const byRate = [...porTarifa.values()].sort((a, b) => a.tax_rate - b.tax_rate);
	const subtotal = round2(byRate.reduce((s, r) => s + r.base, 0));
	const tax = round2(byRate.reduce((s, r) => s + r.tax, 0));

	return { date_from: from, date_to: to, subtotal, tax, total: round2(subtotal + tax), by_rate: byRate };
});

/** El piso del tramo de antigüedad en días: 0, 30, 60 o 90 (RF-44). */
function tramoDe(dueDate: string | null, hoy: string): number {
	// Sin vencimiento cae en el primero: lo caro sería marcar de morosa una
	// compra de contado que nunca tuvo fecha.
	if (!dueDate) return 0;
	const dias = diasEntre(dueDate, hoy);
	for (const tramo of [90, 60, 30]) if (dias > tramo) return tramo;
	return 0;
}

function diasEntre(desde: string, hasta: string): number {
	const a = new Date(`${desde}T00:00:00`).getTime();
	const b = new Date(`${hasta}T00:00:00`).getTime();
	return Math.round((b - a) / 86_400_000);
}

// -------------------------------------------- entradas de inventario

/** La entrada con su factura de compra, si la tiene (T-728), como el backend. */
function entradaOut(companyId: number, e: StockEntry) {
	return {
		...e,
		einvoice: e.document_type ? comprobanteDe(companyId, 'purchase', e.id) : null
	};
}

route('GET', '/inventory/entries', ({ companyId }) =>
	[...getDb(companyId).stock_entries]
		.sort((a, b) => b.created_at.localeCompare(a.created_at))
		.map((e) => entradaOut(companyId, e))
);

route('GET', '/inventory/entry/:id', ({ params, companyId }) => {
	const found = getDb(companyId).stock_entries.find((e) => e.id === Number(params[0]));
	if (!found) fail(404, 'entry_not_found');
	return entradaOut(companyId, found);
});

route('POST', '/inventory/entry', ({ body, companyId, userId }) => {
	const db = getDb(companyId);
	const requested = Array.isArray(body?.lines) ? body.lines : [];
	if (!requested.length) fail(400, 'empty_entry');

	// ------------------------------------------------------- compra (F10)
	//
	// Con `supplier_id` esto es una compra (RN-52): abre cuenta por pagar y
	// crédito fiscal. Sin él es la entrada de siempre y nada de esto se usa.
	const supplierId = Number(body?.supplier_id ?? 0) || null;
	// Los módulos según lo que trae, como `create_entry` en el backend (QA-01):
	// recibir es del inventario, nombrar al proveedor es de proveedores y
	// comprar a crédito —que deja una cuenta por pagar— es de compras.
	exigirModulo(companyId, 'inventory');
	if (supplierId) {
		exigirModulo(companyId, 'suppliers');
		if (body?.payment_terms === 'credit') exigirModulo(companyId, 'purchases');
	}
	const proveedor = supplierId
		? (db.suppliers ?? []).find((p) => p.id === supplierId)
		: undefined;
	if (supplierId && !proveedor) fail(404, 'supplier_not_found', { supplier_id: supplierId });
	if (proveedor && !proveedor.is_active) fail(400, 'supplier_inactive', { name: proveedor.name });

	// La factura electrónica de compra (RF-79, T-728): nace de comprarle a un no
	// contribuyente, si la compañía la emite. Se decide y se prepara el emisor
	// antes de escribir nada, como `RegisterStockEntry`.
	const documentType = proveedor
		? purchaseDocumentType(
				einvoicingEnabled(companyId),
				enabledTypes(seccionElectronica(companyId)?.documentTypes),
				proveedor.identification_type
			)
		: null;
	const emisorDeCompra = documentType ? prepararNumeracion(companyId) : null;

	const documentNumber = body?.document_number ? String(body.document_number).trim() : null;
	if (documentNumber) {
		// Por proveedor desde F10: la factura 1234 de un mayorista no es la 1234
		// de otro, y compararlas rechazaría una compra legítima.
		const duplicate = db.stock_entries.find(
			(e) =>
				e.document_number === documentNumber &&
				e.status === 'aplicada' &&
				(e.supplier_id ?? null) === supplierId
		);
		if (duplicate) {
			fail(400, 'duplicate_document', {
				document_number: documentNumber,
				loaded_at: duplicate.created_at
			});
		}
	}

	// Se valida todo antes de escribir: o entra la carga completa, o ninguna.
	const resolved: {
		product: Product;
		quantity: number;
		unitCost: number;
		taxRate: number;
		taxAmount: number;
	}[] = [];
	let createdProducts = 0;

	for (const [index, raw] of requested.entries()) {
		const quantity = Math.trunc(Number(raw?.quantity ?? 0));
		const unitCost = round2(Number(raw?.unit_cost ?? 0));
		// El impuesto **del documento** (RN-53): es el crédito fiscal, y lo que
		// se acredita es lo que se pagó. No se recalcula desde el producto.
		const taxRate = round2(Number(raw?.tax_rate ?? 0));
		const taxAmount = round2(Number(raw?.tax_amount ?? 0));
		// Un solo código para las dos, como el backend: el dominio rechaza el valor
		// y la línea la nombra la interfaz.
		if (!(quantity > 0) || unitCost < 0)
			fail(400, 'invalid_entry_line', { line: index + 1 });

		if (raw?.id_product) {
			const product = db.products.find((p) => p.id_product === Number(raw.id_product));
			if (!product)
				fail(404, 'entry_product_not_found', { product_id: raw.id_product });
			resolved.push({ product, quantity, unitCost, taxRate, taxAmount });
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
			resolved.push({ product, quantity, unitCost, taxRate, taxAmount });
		} else {
			fail(400, 'entry_line_without_product', { line: index + 1 });
		}
	}

	const id = nextId('stock_entries');
	let subtotalTotal = 0;
	let impuestoTotal = 0;
	let units = 0;

	const lines = resolved.map(({ product, quantity, unitCost, taxRate, taxAmount }, indice) => {
		const subtotal = round2(unitCost * quantity);
		subtotalTotal = round2(subtotalTotal + subtotal);
		impuestoTotal = round2(impuestoTotal + taxAmount);
		units += quantity;

		// El costo **antes** que el stock y los dos en el mismo paso, como el
		// backend: si un producto aparece dos veces en la misma factura, el
		// segundo promedio tiene que ver las existencias que dejó el primero
		// (RN-54).
		product.cost = promedioPonderado(product.stock, Number(product.cost ?? 0), quantity, unitCost);
		moverStock(companyId, {
			product,
			delta: quantity,
			kind: 'entry',
			unit_cost: unitCost,
			source_type: 'stock_entry',
			source_id: id,
			source_line: indice + 1,
			user_id: userId
		});

		return {
			id_product: product.id_product,
			name: product.name,
			quantity,
			unit_cost: unitCost,
			subtotal,
			tax_rate: taxRate,
			tax_amount: taxAmount
		};
	});
	const total = round2(subtotalTotal + impuestoTotal);

	// El vencimiento se cuenta desde la fecha DEL DOCUMENTO, no la de carga: el
	// proveedor cobra desde su factura. Un plazo de cero días es contado.
	const documentDate = String(body?.document_date ?? '').trim() || null;
	const dias = Math.trunc(
		Number(body?.payment_terms_days ?? proveedor?.payment_terms_days ?? 0) || 0
	);
	const aCredito = Boolean(proveedor) && body?.payment_terms === 'credit' && dias > 0;
	const dueDate = aCredito ? sumarDias(documentDate ?? nowIso().slice(0, 10), dias) : null;

	const creadaEn = nowIso();
	db.stock_entries.push({
		id,
		document_number: documentNumber,
		// El nombre se copia aunque haya `supplier_id`: así la compra lo recuerda
		// si después se desactiva al proveedor o se le corrige la razón social.
		supplier: body?.supplier ? String(body.supplier) : (proveedor?.name ?? null),
		source: ['manual', 'excel', 'xml'].includes(body?.source) ? body.source : 'manual',
		user_id: Number(body?.user_id ?? 0),
		user_name: personName(Number(body?.user_id ?? 0)),
		created_at: creadaEn,
		notes: body?.notes ? String(body.notes) : null,
		status: 'aplicada',
		total_cost: total,
		items_count: units,
		lines,
		supplier_id: supplierId,
		document_key: String(body?.document_key ?? '').trim() || null,
		document_date: documentDate,
		payment_terms: dueDate ? 'credit' : 'cash',
		due_date: dueDate,
		subtotal: subtotalTotal,
		tax: impuestoTotal,
		document_type: documentType
	});
	// El número y la clave de la factura de compra, con la misma hora que la
	// entrada (T-704, T-705, T-728).
	if (emisorDeCompra && documentType) {
		numerar(companyId, emisorDeCompra, {
			source_type: 'purchase',
			source_id: id,
			document_type: documentType,
			issued_at: creadaEn
		});
	}

	// El abono de una compra de contado, si se dijo CÓMO se pagó. Sin método
	// queda con saldo: adivinar «efectivo» descuadraría un arqueo (RN-56).
	let idPayment: number | null = null;
	const metodo = String(body?.payment_method ?? '').trim();
	if (supplierId && !dueDate && metodo) {
		idPayment = abonar(companyId, {
			entryId: id,
			supplierId,
			amount: total,
			method: metodo,
			reference: documentNumber,
			reason: String(body?.payment_reason ?? ''),
			userId: Number(body?.user_id ?? 0)
		});
	}

	// Solo una **compra** deja asiento: una entrada sin proveedor es un ajuste
	// de inventario, y de esos el sistema no sabe la contrapartida (RN-52).
	if (supplierId) {
		asentar(companyId, () =>
			postPurchase(
				companyId,
				{ id, date: documentDate ?? nowIso().slice(0, 10) },
				lines.map((l: any) => ({
					subtotal: round2(l.unit_cost * l.quantity),
					tax: l.tax_amount ?? 0,
					tax_rate: (l.tax_rate ?? 0) / 100
				})),
				Number(body?.user_id ?? 0)
			)
		);
	}

	persist();

	return {
		message: 'entry_registered',
		id_entry: id,
		products_created: createdProducts,
		units_added: units,
		id_payment: idPayment
	};
});

route('POST', '/inventory/entry/:id/cancel', ({ params, body, companyId, userId }) => {
	exigirModulo(companyId, 'inventory'); // QA-01
	const db = getDb(companyId);
	const entry = db.stock_entries.find((e) => e.id === Number(params[0]));
	if (!entry) fail(404, 'entry_not_found');
	if (entry.status === 'anulada') fail(400, 'entry_already_cancelled');

	// Se pregunta siempre, sin mirar antes `supplier_id`: una entrada que no es
	// compra no tiene abonos y contesta con la lista vacía (RN-57).
	const abonos = (db.supplier_payments ?? []).filter((a) => a.entry_id === entry.id);
	if (abonos.length)
		fail(400, 'purchase_has_payments', { entry_id: entry.id, payments: abonos.length });

	// El motivo es obligatorio solo si es compra (RF-46): la pantalla de
	// entradas nunca lo pidió y exigirlo siempre la rompería.
	const motivo = String(body?.reason ?? '').trim();
	if (entry.supplier_id != null && !motivo) fail(400, 'void_reason_required');

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

	// La reversión es un movimiento propio con signo contrario (RN-98), al
	// costo de la entrada; el promedio no se deshace.
	entry.lines.forEach((line, i) => {
		const product = db.products.find((p) => p.id_product === line.id_product);
		if (product)
			moverStock(companyId, {
				product,
				delta: -line.quantity,
				kind: 'entry_void',
				unit_cost: Number(line.unit_cost ?? 0),
				source_type: 'stock_entry',
				source_id: entry.id,
				source_line: i + 1,
				user_id: userId
			});
	});
	entry.status = 'anulada';
	persist();
	return { message: 'entry_cancelled', id_entry: entry.id };
});


// --------------------------------------------- F15: kárdex, motivos y salidas

function movimientosDe(companyId: number): StockMovement[] {
	const empresa = getEmpresa(companyId);
	if (!empresa.stock_movements) empresa.stock_movements = [];
	return empresa.stock_movements;
}

function motivosDe(companyId: number): StockReason[] {
	const empresa = getEmpresa(companyId);
	// Un archivo de antes de F15 no los trae: nacen los de fábrica, como en una
	// compañía recién dada de alta.
	if (!empresa.stock_reasons) empresa.stock_reasons = motivosDeFabrica();
	return empresa.stock_reasons;
}

function salidasDe(companyId: number): StockExit[] {
	const empresa = getEmpresa(companyId);
	if (!empresa.stock_exits) empresa.stock_exits = [];
	return empresa.stock_exits;
}

/** La sucursal de la sesión. El simulado tiene una por compañía hasta T-1505. */
function sucursalDe(companyId: number): number {
	return getDb(companyId).branches?.[0]?.id ?? 1;
}

/**
 * El único escritor de existencias del simulado, como `MoveStock` en el backend
 * (plan §15.1): mueve `stock` y deja la fila del kárdex con antes y después
 * (RN-98). Lo que no hay no sale, con el mismo código que la venta.
 */
function moverStock(
	companyId: number,
	args: {
		product: { id_product: number; name: string; stock: number; cost?: number };
		delta: number;
		kind: StockMovementKind;
		unit_cost: number;
		source_type: string;
		source_id: number;
		source_line?: number | null;
		user_id: number | null;
	}
): StockMovement {
	const { product, delta } = args;
	const antes = product.stock;
	const despues = antes + delta;
	if (despues < 0) {
		fail(400, 'insufficient_stock', {
			product_id: product.id_product,
			product: product.name,
			available: antes,
			requested: -delta
		});
	}
	product.stock = despues;
	const movimiento: StockMovement = {
		id: nextId('stock_movements'),
		product_id: product.id_product,
		branch_id: sucursalDe(companyId),
		kind: args.kind,
		quantity: delta,
		before_qty: antes,
		after_qty: despues,
		unit_cost: round2(args.unit_cost),
		// El promedio del producto DESPUÉS del movimiento (RN-103): la entrada ya
		// escribió el costo antes de llamar acá, como `RegisterStockEntry`.
		avg_cost_after: round2(Number(product.cost ?? 0)),
		lot_id: null,
		source_type: args.source_type,
		source_id: args.source_id,
		source_line: args.source_line ?? null,
		user_id: args.user_id ?? 0,
		moved_at: nowIso()
	};
	movimientosDe(companyId).push(movimiento);
	return movimiento;
}

route('GET', '/inventory/kardex', ({ query, companyId }) => {
	const productId = query.get('product_id');
	const sourceType = query.get('source_type');
	const sourceId = query.get('source_id');
	if (!productId && !(sourceType && sourceId)) fail(400, 'kardex_filter_required');

	let filas = movimientosDe(companyId);
	if (productId) filas = filas.filter((m) => m.product_id === Number(productId));
	if (sourceType && sourceId)
		filas = filas.filter((m) => m.source_type === sourceType && m.source_id === Number(sourceId));
	const branchId = query.get('branch_id');
	if (branchId) filas = filas.filter((m) => m.branch_id === Number(branchId));
	// Por producto, del más reciente al más viejo; por documento, en el orden en
	// que se anotó. Igual que `SqlAlchemyKardex`.
	return productId
		? [...filas].sort((a, b) => b.moved_at.localeCompare(a.moved_at) || b.id - a.id)
		: [...filas].sort((a, b) => a.id - b.id);
});

route('GET', '/inventory/levels', ({ query, companyId }) => {
	const productId = query.get('product_id');
	const branchId = query.get('branch_id');
	if (!productId && !branchId) fail(400, 'kardex_filter_required');

	// El nivel es la suma de los movimientos por (producto, sucursal): el
	// simulado no tiene caché que mantener, y así no puede separarse del kárdex.
	const niveles = new Map<string, { product_id: number; branch_id: number; quantity: number }>();
	for (const m of movimientosDe(companyId)) {
		if (productId && m.product_id !== Number(productId)) continue;
		if (branchId && m.branch_id !== Number(branchId)) continue;
		const clave = `${m.product_id}|${m.branch_id}`;
		const nivel = niveles.get(clave) ?? { product_id: m.product_id, branch_id: m.branch_id, quantity: 0 };
		nivel.quantity += m.quantity;
		niveles.set(clave, nivel);
	}
	return [...niveles.values()].sort(
		(a, b) => a.product_id - b.product_id || a.branch_id - b.branch_id
	);
});

route('GET', '/inventory/reasons', ({ companyId }) =>
	[...motivosDe(companyId)].sort((a, b) => a.id - b.id)
);

route('POST', '/inventory/reasons', ({ body, companyId }) => {
	exigirModulo(companyId, 'inventory');
	const code = String(body?.code ?? '').trim();
	const name = String(body?.name ?? '').trim();
	if (motivosDe(companyId).some((m) => m.code === code))
		fail(400, 'reason_code_taken', { reason_code: code });
	const motivo: StockReason = { id: nextId('stock_reasons'), code, name, is_system: false, is_active: true };
	motivosDe(companyId).push(motivo);
	persist();
	return motivo;
});

route('PUT', '/inventory/reasons/:id', ({ params, body, companyId }) => {
	exigirModulo(companyId, 'inventory');
	const id = Number(params[0]);
	const motivo = motivosDe(companyId).find((m) => m.id === id);
	if (!motivo) fail(404, 'reason_not_found', { reason_id: id });
	// El de la toma física no se apaga (RN-100).
	if (body?.is_active === false && motivo.is_system) fail(400, 'reason_is_system', { reason_id: id });
	if (typeof body?.name === 'string' && body.name.trim()) motivo.name = body.name.trim();
	if (typeof body?.is_active === 'boolean') motivo.is_active = body.is_active;
	persist();
	return motivo;
});

route('GET', '/inventory/exits', ({ companyId }) =>
	[...salidasDe(companyId)].sort((a, b) => b.created_at.localeCompare(a.created_at) || b.id - a.id)
);

route('POST', '/inventory/exits', ({ body, companyId, userId }) => {
	exigirModulo(companyId, 'inventory');
	const db = getDb(companyId);
	const requested: any[] = Array.isArray(body?.lines) ? body.lines : [];
	if (!requested.length) fail(400, 'empty_exit');
	requested.forEach((l, i) => {
		if (!Number(l?.id_product) || !(Number(l?.quantity) > 0)) fail(400, 'invalid_exit_line', { line: i + 1 });
	});

	// El motivo, antes de tocar nada: existe, está activo y no es el de la toma.
	const reasonId = Number(body?.reason_id ?? 0);
	const motivo = motivosDe(companyId).find((m) => m.id === reasonId);
	if (!motivo) fail(404, 'reason_not_found', { reason_id: reasonId });
	if (!motivo.is_active) fail(400, 'reason_inactive', { reason_id: reasonId });
	if (motivo.is_system) fail(400, 'reason_is_system', { reason_id: reasonId });

	// Al promedio del momento (RN-99); sin compras, a cero.
	const lineas = requested.map((l) => {
		const product = db.products.find((p) => p.id_product === Number(l.id_product));
		if (!product) fail(404, 'product_not_found', { product_id: Number(l.id_product) });
		const quantity = Math.trunc(Number(l.quantity));
		const unitCost = round2(Number(product.cost ?? 0));
		return { product, quantity, unit_cost: unitCost, subtotal: round2(unitCost * quantity) };
	});
	// Lo que no hay no sale, comprobado antes de mover nada: el simulado no
	// tiene transacción que revertir a medias.
	for (const l of lineas) {
		if (l.product.stock < l.quantity)
			fail(400, 'insufficient_stock', {
				product_id: l.product.id_product,
				product: l.product.name,
				available: l.product.stock,
				requested: l.quantity
			});
	}

	const id = nextId('stock_exits');
	const createdAt = nowIso();
	lineas.forEach((l, i) =>
		moverStock(companyId, {
			product: l.product,
			delta: -l.quantity,
			kind: 'exit',
			unit_cost: l.unit_cost,
			source_type: 'stock_exit',
			source_id: id,
			source_line: i + 1,
			user_id: userId
		})
	);
	const total = round2(lineas.reduce((t, l) => t + l.subtotal, 0));
	const salida: StockExit = {
		id,
		branch_id: sucursalDe(companyId),
		reason_id: motivo.id,
		reason_code: motivo.code,
		reason_name: motivo.name,
		user_id: userId ?? 0,
		user_name: null,
		created_at: createdAt,
		notes: String(body?.notes ?? '').trim() || null,
		status: 'applied',
		total_cost: total,
		items_count: lineas.reduce((t, l) => t + l.quantity, 0),
		voided_at: null,
		void_reason: null,
		lines: lineas.map((l) => ({
			id_product: l.product.id_product,
			name: l.product.name,
			quantity: l.quantity,
			unit_cost: l.unit_cost,
			subtotal: l.subtotal,
			lot_id: null
		}))
	};
	salidasDe(companyId).push(salida);

	// Del inventario al gasto, con la salida (RN-59). Apagado, no hace nada.
	asentar(companyId, () =>
		postStockExit(companyId, { id, date: createdAt.slice(0, 10) }, total, userId ?? 0)
	);
	persist();
	return { message: 'exit_registered', id_exit: id, units: salida.items_count, total_cost: total };
});

route('POST', '/inventory/exits/:id/cancel', ({ params, body, companyId, userId }) => {
	exigirModulo(companyId, 'inventory');
	const db = getDb(companyId);
	const id = Number(params[0]);
	const salida = salidasDe(companyId).find((s) => s.id === id);
	if (!salida) fail(404, 'exit_not_found', { exit_id: id });
	if (salida.status === 'voided') fail(400, 'exit_cancelled', { exit_id: id });
	// El motivo es obligatorio siempre (RN-99): toda salida nació con motivo.
	const motivo = String(body?.reason ?? '').trim();
	if (!motivo) fail(400, 'void_reason_required');

	// Repone al costo de la salida, no al promedio de hoy (RN-98).
	salida.lines.forEach((l, i) => {
		const product = db.products.find((p) => p.id_product === l.id_product);
		if (product)
			moverStock(companyId, {
				product,
				delta: l.quantity,
				kind: 'exit_void',
				unit_cost: l.unit_cost,
				source_type: 'stock_exit',
				source_id: id,
				source_line: i + 1,
				user_id: userId
			});
	});
	const ahora = nowIso();
	salida.status = 'voided';
	salida.voided_at = ahora;
	salida.void_reason = motivo;
	asentar(companyId, () =>
		postStockExit(companyId, { id, date: ahora.slice(0, 10) }, salida.total_cost, userId ?? 0, true)
	);
	persist();
	return { message: 'exit_voided', id_exit: id, units_returned: salida.items_count };
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

/**
 * Si la compañía factura electrónicamente, con la misma regla que
 * `crud_settings.get_einvoicing_enabled`: la clave nueva manda si **está**, y
 * solo un booleano de verdad cuenta.
 */
function einvoicingEnabled(companyId: number): boolean {
	const s = seccionElectronica(companyId);
	if (!s) return false;
	return ('enabled' in s ? s.enabled : s.activa) === true;
}

/** La sección de factura electrónica, con la misma regla que `crud_settings`. */
function seccionElectronica(companyId: number): Record<string, unknown> | null {
	const data = (settingsRow(companyId).data ?? {}) as Record<string, unknown>;
	const seccion = 'eInvoicing' in data ? data.eInvoicing : data.electronica;
	if (!seccion || typeof seccion !== 'object' || Array.isArray(seccion)) return null;
	return seccion as Record<string, unknown>;
}

route('GET', '/settings/', ({ userId, companyId }) => {
	// La lee cualquier sesión: el cajero necesita la moneda y los datos del
	// tiquete. No hay secretos guardados acá.
	if (userId == null) fail(401, 'unauthorized');
	return { ...settingsRow(companyId), issuer: emisorParaConfiguracion(companyId) };
});

/** La cédula del emisor, de la compañía y no de la configuración (RN-45). */
function emisorParaConfiguracion(companyId: number) {
	const empresa = getRoot().companies.find((c) => c.id === companyId);
	const cedula = (empresa?.identificacion ?? '').trim();
	return {
		identification: cedula || null,
		identification_type: empresa?.identification_type ?? (cedula ? identificationTypeFor(cedula) : null)
	};
}

/**
 * La puerta de `crud_settings._validar_emisor` (T-722): la ubicación a medias no
 * se guarda, y la facturación no se enciende sin cédula, correo y ubicación.
 */
function validarEmisor(companyId: number, data: Record<string, any>) {
	const negocio = (data.business ?? data.negocio ?? {}) as Record<string, any>;
	const ubicacion = negocio.location;
	if (!isBlankLocation(ubicacion)) {
		const problema = locationProblem(normalizeLocation(ubicacion));
		if (problema) fail(400, 'invalid_location', { field: problema.field, reason: problema.reason });
	}
	const seccion = (data.eInvoicing ?? data.electronica ?? {}) as Record<string, any>;
	const encendida = ('enabled' in seccion ? seccion.enabled : seccion.activa) === true;
	if (!encendida) return;

	const faltan: string[] = [];
	if (!/\d/.test(getRoot().companies.find((c) => c.id === companyId)?.identificacion ?? ''))
		faltan.push('identification');
	const correo = String(negocio.email ?? negocio.correo ?? '').trim();
	if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(correo)) faltan.push('email');
	if (isBlankLocation(ubicacion) || locationProblem(normalizeLocation(ubicacion)))
		faltan.push('location');
	if (faltan.length) fail(400, 'einvoicing_needs_issuer', { missing: faltan });
}

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

	// El ambiente de factura electrónica **tiene su propia puerta** (T-611): se
	// cambia por `PUT /fe/active`, que confirma y deja bitácora. Si se pudiera
	// mover por acá, RN-35 sería decoración. Se conserva lo que ya estaba —no se
	// rechaza la petición— porque el POS manda la configuración completa en cada
	// guardado. Es el mismo `PROTECTED_PATHS` de `crud_settings.py`.
	conservarAmbiente(data, settingsRow(companyId).data);

	// El impuesto no se configura (QA-05): lo que llegue se descarta, como
	// `sin_impuesto` en `crud_settings.py`.
	delete (data as Record<string, unknown>).tax;
	delete (data as Record<string, unknown>).impuesto;

	validarEmisor(companyId, data as Record<string, any>);

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
	return { ...row, issuer: emisorParaConfiguracion(companyId) };
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
			token: request.token,
			upload: request.upload
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
		identification_type: empresa.identification_type ?? null,
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

/** El idioma del panel (QA-02): como `/auth/locale`, pero con token de soporte. */
route('POST', '/support/locale', ({ body, token }) => {
	const user = usuarioDelToken(token);
	const pedido = body?.locale === null || body?.locale === undefined ? null : String(body.locale);
	if (pedido !== null && !IDIOMAS.includes(pedido)) fail(400, 'unsupported_locale', { locale: pedido });
	user.locale = pedido;
	persist();
	return {
		access_token: tokenDeSoporte(user),
		token_type: 'bearer',
		locale: pedido || 'es',
		user_locale: pedido,
		document_locale: 'es'
	};
});

route('GET', '/support/plans', () => getRoot().plans);

/**
 * Los módulos de un plan (RF-39, T-1003).
 *
 * Los tres llegan siempre, no un parche: una casilla sin marcar no viaja en el
 * formulario, así que con un parche «la desmarcó» y «no la tocó» se verían igual.
 *
 * Alcanza a todas las compañías del plan, y por eso la bitácora anota cuántas
 * son —igual que `crud_support.cambiar_modulos`—.
 */
route('PUT', '/support/plans/:id/modules', ({ params, body, token }) => {
	const soporte = usuarioDelToken(token);
	const planId = Number(params[0]);
	const plan = getRoot().plans.find((p) => p.id === planId);
	if (!plan) fail(404, 'plan_not_found', { plan_id: planId });

	const partes: string[] = [];
	for (const nombre of MODULOS) {
		const pedido = Boolean(body?.[nombre]);
		if (plan[nombre] !== pedido) {
			partes.push(`${nombre} ${plan[nombre] ? 'sí' : 'no'} → ${pedido ? 'sí' : 'no'}`);
		}
		plan[nombre] = pedido;
	}

	/*
	 * Se registra **siempre**, también cuando no cambió nada, igual que
	 * `cambiar_suscripcion`: haber abierto el panel y pulsado guardar es un hecho,
	 * y saber quién estuvo tocando los planes es justo para lo que sirve.
	 */
	const alcanzadas = getRoot().companies.filter((c) => c.plan_id === plan.id).length;
	registrar(
		soporte.id_user,
		// Sin compañía: el cambio es del catálogo, no de un cliente.
		null,
		'plan_modulos',
		partes.length > 0
			? `${plan.nombre}: ${partes.join(', ')} (${alcanzadas} compañías)`
			: `${plan.nombre}: sin cambios`
	);
	persist();

	return plan;
});

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

	// La cédula del emisor, limpia y con tipo: va en la clave (RN-45, T-705).
	const emisorDeAlta = emisorLimpio(body?.identificacion, body?.identification_type);
	// Y la ubicación, si viene (RF-73): opcional, pero a medias no.
	const ubicacionDeAlta = body?.settings?.business?.location;
	if (!isBlankLocation(ubicacionDeAlta)) {
		const problema = locationProblem(normalizeLocation(ubicacionDeAlta));
		if (problema) fail(400, 'invalid_location', { field: problema.field, reason: problema.reason });
	}
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
		identificacion: emisorDeAlta.cedula,
		identification_type: emisorDeAlta.tipo,
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

/**
 * La cédula del emisor limpia y con tipo, como `support_routes._emisor`: sin
 * guiones, de 9 a 12 dígitos, y el tipo el elegido o el que deja ver la cédula.
 * Vacía es «todavía no se sabe» y vuelve nula.
 */
function emisorLimpio(identificacion: unknown, pedido: unknown): { cedula: string | null; tipo: string | null } {
	const escrita = String(identificacion ?? '').trim();
	if (!escrita) return { cedula: null, tipo: null };
	const cedula = escrita.replace(/[-\s]/g, '');
	if (!/^\d{9,12}$/.test(cedula)) fail(409, 'issuer_identification_required', { reason: 'invalid' });
	if (pedido == null || pedido === '') {
		const tipo = identificationTypeFor(cedula);
		if (!tipo) fail(400, 'identification_type_required');
		return { cedula, tipo };
	}
	if (!isIdentificationType(pedido)) fail(400, 'invalid_identification_type', { identification_type: String(pedido) });
	return { cedula, tipo: String(pedido) };
}

/** La cédula del emisor (RN-45, T-621): la fija y la corrige soporte. */
route('PUT', '/support/companies/:id/issuer', ({ params, body, token }) => {
	const soporte = usuarioDelToken(token);
	const companyId = Number(params[0]);
	const empresa = getRoot().companies.find((c) => c.id === companyId);
	if (!empresa) fail(404, 'company_not_found');

	const { cedula, tipo } = emisorLimpio(body?.identificacion, body?.identification_type);
	if (!cedula || !tipo) fail(400, 'identification_required');

	const antes = `${empresa.identificacion || 'sin cédula'} (${empresa.identification_type ?? '—'})`;
	empresa.identificacion = cedula;
	empresa.identification_type = tipo;
	registrar(soporte.id_user, companyId, 'emisor', `emisor ${antes} → ${cedula} (${tipo})`);
	persist();
	return companiaParaSoporte(companyId);
});

// ------------------------------------------------ tasas de planilla (T-1204)

/*
 * Las mismas que siembra la API al arrancar (`payrollRates.ts` se genera de su
 * archivo de datos) más las que soporte agregó. Son del país, no de una
 * compañía (RN-67): la misma lista para todas.
 */

/** Más de seis meses sin comprobar: `domain/payroll.STALE_AFTER_DAYS`. */
const TASA_VIEJA_DIAS = 183;

interface TasaDePlanilla {
	concept: string;
	payer: string;
	value: number;
	valid_from: string;
	valid_to: string | null;
	source: string;
	verified_at: string;
}

function tasasDePlanilla(): TasaDePlanilla[] {
	const sembradas = PAYROLL_SEED.rates.map((r) => ({
		...r,
		valid_to: null,
		verified_at: PAYROLL_SEED.verified_at
	}));
	const agregadas = (getRoot().payroll_rates ?? []).map((r) => ({ ...r, valid_to: null }));
	return [...sembradas, ...agregadas];
}

function esVieja(verificada: string, hoy: string): boolean {
	return diasEntre(verificada, hoy) > TASA_VIEJA_DIAS;
}

function rige(fila: { valid_from: string; valid_to?: string | null }, dia: string): boolean {
	return fila.valid_from <= dia && (fila.valid_to == null || dia <= fila.valid_to);
}

/** Lo mismo que `crud_payroll_rates.vigentes`: de cada clave, la más reciente que rige. */
function vigentesDePlanilla(dia: string, hoy: string) {
	const elegidas = new Map<string, TasaDePlanilla>();
	for (const fila of tasasDePlanilla()) {
		if (!rige(fila, dia)) continue;
		const clave = `${fila.payer}:${fila.concept}`;
		const antes = elegidas.get(clave);
		if (!antes || fila.valid_from > antes.valid_from) elegidas.set(clave, fila);
	}
	const tasas = [...elegidas.entries()]
		.sort(([a], [b]) => (a < b ? -1 : 1))
		.map(([, t]) => ({ ...t, stale: esVieja(t.verified_at, hoy) }));
	const presentes = new Set(tasas.map((t) => `${t.concept}:${t.payer}`));
	const tramos = PAYROLL_SEED.brackets.filter((b) => rige(b, dia));
	const cesantia = PAYROLL_SEED.severance_valid_from <= dia ? PAYROLL_SEED.severance : [];
	return {
		on: dia,
		country: PAYROLL_SEED.country,
		rates: tasas,
		brackets: tramos.map((b) => ({ ...b, verified_at: PAYROLL_SEED.verified_at })),
		credits: PAYROLL_SEED.credits.filter((c) => rige(c, dia)),
		severance: cesantia,
		missing: PAYROLL_SEED.required.filter((r) => !presentes.has(r)),
		stale:
			tasas.some((t) => t.stale) ||
			(tramos.length > 0 && esVieja(PAYROLL_SEED.verified_at, hoy))
	};
}

route('GET', '/payroll/rates', ({ query, userId, companyId }) => {
	if (userId == null) fail(401, 'unauthorized');
	const user = getRoot().users.find((u) => u.id_user === userId);
	if (!user) fail(404, 'user_not_found');
	if ((rolEn(user.id_user, companyId) ?? user.role) !== 'admin') fail(403, 'admin_only');
	const hoy = nowIso().slice(0, 10);
	return vigentesDePlanilla(query.get('on') || hoy, hoy);
});

route('PUT', '/support/payroll/rates', ({ body, token }) => {
	const soporte = usuarioDelToken(token);
	const concept = String(body?.concept ?? '');
	const payer = String(body?.payer ?? '');
	const valid_from = String(body?.valid_from ?? '');
	const source = String(body?.source ?? '');
	const value = Number(body?.value);
	// Lo que en la API rechaza pydantic con un 422.
	if (
		!/^[a-z][a-z0-9_]{1,39}$/.test(concept) ||
		!/^\d{4}-\d{2}-\d{2}$/.test(valid_from) ||
		source.length < 5 ||
		source.length > 255 ||
		!Number.isFinite(value) ||
		(body?.country ?? 'CR') !== 'CR'
	) {
		fail(422, 'invalid_request');
	}
	// Lo que en la API decide el dominio (`check_new_rate`).
	if (!['employee', 'employer', 'rule'].includes(payer)) {
		fail(400, 'invalid_payroll_rate', { field: 'payer', reason: 'unknown' });
	}
	if (value < 0 || (payer !== 'rule' && value >= 1)) {
		fail(400, 'invalid_payroll_rate', { field: 'value', reason: 'out_of_range' });
	}
	const ultima = tasasDePlanilla()
		.filter((t) => t.concept === concept && t.payer === payer)
		.map((t) => t.valid_from)
		.sort()
		.at(-1);
	if (ultima && valid_from <= ultima) {
		fail(409, 'payroll_rate_not_newer', { concept, payer, latest: ultima });
	}

	const hoy = nowIso().slice(0, 10);
	const fila: MockPayrollRate = { concept, payer, value, valid_from, source, verified_at: hoy };
	const raiz = getRoot();
	raiz.payroll_rates = [...(raiz.payroll_rates ?? []), fila];
	registrar(soporte.id_user, null, 'tasa_planilla', `${concept}:${payer} = ${value} desde ${valid_from}`);
	persist();
	return { ...fila, valid_to: null, stale: false };
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

// ------------------------------------------------------- contabilidad (F11)
//
// El contrato es el mismo del backend. Lo que asienta cada hecho vive en
// `./ledger.ts`, que es el espejo de `domain/ledger.py`.

/** Corre algo que escribe en el libro y convierte sus «no» en códigos. */
function asentar<T>(companyId: number, escribir: () => T): T | null {
	if (!activaLaContabilidad(companyId)) return null;
	try {
		return escribir();
	} catch (error) {
		if (error instanceof PeriodoCerrado)
			fail(400, 'period_closed', { year: error.year, month: error.month });
		if (error instanceof NoBalancea)
			fail(400, 'entry_not_balanced', {
				debits: error.debits.toFixed(2),
				credits: error.credits.toFixed(2)
			});
		throw error;
	}
}

function estadoContable(companyId: number) {
	const config = configuracionContable(companyId);
	return {
		active: Boolean(config.active),
		template: (config.template as string) ?? null,
		start_date: (config.start_date as string) ?? null,
		templates: [...TEMPLATES],
		chart: CHART.map((c) => ({
			code: c.code,
			name: c.name,
			kind: c.kind,
			is_system: c.is_system !== false
		}))
	};
}

function guardarConfigContable(companyId: number, config: Record<string, unknown>): void {
	// `settingsRow` y no `getDb(...).settings = …`: `getDb` devuelve una **copia
	// superficial** de lo global más la compañía, así que asignarle una propiedad
	// escribe en la copia y se pierde. Mutar el objeto que ya está sí llega al
	// almacén, y es lo que hace el resto del simulado.
	const fila = settingsRow(companyId);
	const datos = (fila.data ?? {}) as Record<string, unknown>;
	fila.data = { ...datos, accounting: config };
}

function rangoDelPeriodo(year: number, month: number | null): [string, string] {
	if (!month) return [`${year}-01-01`, `${year}-12-31`];
	const ultimo = new Date(year, month, 0).getDate();
	const mm = String(month).padStart(2, '0');
	return [`${year}-${mm}-01`, `${year}-${mm}-${String(ultimo).padStart(2, '0')}`];
}

function restarUnDia(dia: string): string {
	const fecha = new Date(`${dia}T00:00:00`);
	fecha.setDate(fecha.getDate() - 1);
	return fecha.toISOString().slice(0, 10);
}

route('GET', '/accounting', ({ companyId }) => estadoContable(companyId));

route('POST', '/accounting/activate', ({ body, companyId, userId }) => {
	exigirModulo(companyId, 'accounting');
	const db = getDb(companyId);
	if (configuracionContable(companyId).active) fail(400, 'accounting_already_active');

	const plantilla = String(body?.template ?? COMMERCE);
	if (!TEMPLATES.includes(plantilla)) fail(422, 'invalid_request', { fields: ['template'] });
	const inicio = String(body?.start_date ?? '').slice(0, 10);

	// Lo que ya existe no se toca: una activación que falló a mitad pudo dejar
	// cuentas escritas, y volver a crearlas chocaría con el código único.
	const porCodigo = new Map(db.accounts.map((c) => [c.code, c]));
	let creadas = 0;
	for (const plantillaCuenta of CHART) {
		if (porCodigo.has(plantillaCuenta.code)) continue;
		const cuenta = {
			id: nextId('accounts'),
			code: plantillaCuenta.code,
			name: plantillaCuenta.name,
			kind: plantillaCuenta.kind,
			parent_id: null,
			is_system: plantillaCuenta.is_system !== false,
			is_active: true
		};
		db.accounts.push(cuenta);
		porCodigo.set(cuenta.code, cuenta);
		creadas++;
	}

	const yaMapeadas = new Set(db.account_mappings.map((m) => `${m.event}|${m.role}`));
	let mapeadas = 0;
	for (const [clave, codigo] of Object.entries(defaultMapping())) {
		if (yaMapeadas.has(clave)) continue;
		const [event, role] = clave.split('|');
		db.account_mappings.push({
			id: nextId('account_mappings'),
			event,
			role,
			account_id: porCodigo.get(codigo)!.id
		});
		mapeadas++;
	}

	const [year, month] = inicio.split('-').map(Number);
	if (!db.accounting_periods.some((p) => p.year === year && p.month === month)) {
		db.accounting_periods.push({
			id: nextId('accounting_periods'),
			year,
			month,
			status: 'open',
			closed_at: null,
			closed_by: null
		});
	}

	// La configuración **antes** de la apertura: el libro mira `start_date` para
	// decidir si escribe, igual que el adaptador de verdad.
	guardarConfigContable(companyId, {
		active: true,
		template: plantilla,
		start_date: inicio,
		activated_at: nowIso(),
		activated_by: Number(userId ?? 0)
	});

	let apertura: number | null = null;
	const saldos = Array.isArray(body?.opening) ? body.opening : [];
	const lineas = saldos
		.filter(
			(l: any) => round2(Number(l?.debit ?? 0)) !== 0 || round2(Number(l?.credit ?? 0)) !== 0
		)
		.map((l: any) => {
			const cuenta = porCodigo.get(String(l?.account_code ?? ''));
			if (!cuenta) fail(422, 'invalid_request', { fields: ['opening'] });
			return {
				account_id: cuenta.id,
				debit: round2(Number(l?.debit ?? 0)),
				credit: round2(Number(l?.credit ?? 0))
			};
		});

	if (lineas.length) {
		const debitos = round2(lineas.reduce((t: number, l: any) => t + l.debit, 0));
		const creditos = round2(lineas.reduce((t: number, l: any) => t + l.credit, 0));
		if (debitos !== creditos) {
			// No queda nada a medias: se deshace lo sembrado, como hace la
			// transacción del backend.
			db.accounts.length = 0;
			db.account_mappings.length = 0;
			db.accounting_periods.length = 0;
			guardarConfigContable(companyId, {});
			persist();
			fail(400, 'invalid_opening_balance', {
				debits: debitos.toFixed(2),
				credits: creditos.toFixed(2)
			});
		}
		apertura =
			postEntry(
				companyId,
				{
					kind: 'opening',
					entry_date: inicio,
					description: String(body?.description ?? '').trim() || 'opening',
					lines: lineas
				},
				Number(userId ?? 0)
			)?.id ?? null;
	}

	persist();
	return {
		accounts_created: creadas,
		mappings_created: mapeadas,
		opening_entry_id: apertura,
		...estadoContable(companyId)
	};
});

// ---------------------------------------------------------------- el catálogo

route('GET', '/accounting/accounts', ({ companyId }) =>
	[...getDb(companyId).accounts].sort((a, b) => a.code.localeCompare(b.code))
);

route('POST', '/accounting/accounts', ({ body, companyId }) => {
	exigirModulo(companyId, 'accounting');
	const db = getDb(companyId);
	const codigo = String(body?.code ?? '').trim();
	if (db.accounts.some((c) => c.code === codigo))
		fail(400, 'account_code_taken', { account_code: codigo });

	const cuenta: Account = {
		id: nextId('accounts'),
		code: codigo,
		name: String(body?.name ?? ''),
		kind: String(body?.kind ?? 'expense') as Account['kind'],
		parent_id: body?.parent_id != null ? Number(body.parent_id) : null,
		// Solo la plantilla crea cuentas de sistema (RN-64).
		is_system: false,
		is_active: true
	};
	db.accounts.push(cuenta);
	persist();
	return cuenta;
});

route('PUT', '/accounting/accounts/:id', ({ params, body, companyId }) => {
	exigirModulo(companyId, 'accounting');
	const db = getDb(companyId);
	const cuenta = db.accounts.find((c) => c.id === Number(params[0]));
	if (!cuenta) fail(404, 'account_not_found', { account_id: Number(params[0]) });

	if (body?.is_active === false && cuenta.is_system)
		fail(400, 'account_is_system', { account_code: cuenta.code });

	if (body?.name != null) cuenta.name = String(body.name);
	if (body?.is_active != null) cuenta.is_active = Boolean(body.is_active);
	persist();
	return cuenta;
});

route('DELETE', '/accounting/accounts/:id', ({ params, companyId }) => {
	exigirModulo(companyId, 'accounting');
	const db = getDb(companyId);
	const cuenta = db.accounts.find((c) => c.id === Number(params[0]));
	if (!cuenta) fail(404, 'account_not_found', { account_id: Number(params[0]) });
	if (cuenta.is_system) fail(400, 'account_is_system', { account_code: cuenta.code });

	const lineas = db.journal_lines.filter((l) => l.account_id === cuenta.id).length;
	if (lineas) fail(400, 'account_in_use', { account_code: cuenta.code, lines: lineas });

	db.accounts.splice(db.accounts.indexOf(cuenta), 1);
	persist();
	return { deleted: cuenta.id };
});

// ------------------------------------------------------------------- el mapeo

route('GET', '/accounting/mappings', ({ companyId }) => ({
	mappings: mapeoParaPantalla(companyId)
}));

route('PUT', '/accounting/mappings', ({ body, companyId }) => {
	exigirModulo(companyId, 'accounting');
	const db = getDb(companyId);
	for (const fila of Array.isArray(body?.mappings) ? body.mappings : []) {
		const cuenta = db.accounts.find((c) => c.id === Number(fila?.account_id));
		if (!cuenta || !cuenta.is_active)
			fail(404, 'account_not_found', { account_id: Number(fila?.account_id) });

		const existente = db.account_mappings.find(
			(m) => m.event === fila.event && m.role === fila.role
		);
		if (existente) existente.account_id = cuenta.id;
		else
			db.account_mappings.push({
				id: nextId('account_mappings'),
				event: String(fila.event),
				role: String(fila.role),
				account_id: cuenta.id
			});
	}
	persist();
	return { mappings: mapeoParaPantalla(companyId) };
});

// --------------------------------------------------------------- los asientos

function lineasDelAsiento(companyId: number, entryId: number) {
	const db = getDb(companyId);
	return db.journal_lines
		.filter((l) => l.entry_id === entryId)
		.map((l) => {
			const cuenta = db.accounts.find((c) => c.id === l.account_id);
			return {
				account_id: l.account_id,
				account_code: cuenta?.code ?? '',
				account_name: cuenta?.name ?? '',
				debit: l.debit,
				credit: l.credit,
				tax_rate: l.tax_rate,
				memo: l.memo
			};
		});
}

function asientoConLineas(companyId: number, asiento: JournalEntry) {
	const lineas = lineasDelAsiento(companyId, asiento.id);
	return {
		...asiento,
		lines: lineas,
		total: round2(lineas.reduce((t, l) => t + l.debit, 0))
	};
}

route('GET', '/accounting/entries', ({ query, companyId }) => {
	const db = getDb(companyId);
	const year = query.get('year');
	const month = query.get('month');
	const kind = query.get('kind');

	return db.journal_entries
		.filter((a) => !year || a.entry_date.slice(0, 4) === String(year))
		.filter((a) => !month || Number(a.entry_date.slice(5, 7)) === Number(month))
		.filter((a) => !kind || a.kind === kind)
		.sort(
			(a, b) => a.entry_date.localeCompare(b.entry_date) || a.entry_number - b.entry_number
		);
});

route('POST', '/accounting/entries', ({ body, companyId, userId }) => {
	exigirModulo(companyId, 'accounting');
	const db = getDb(companyId);
	const descripcion = String(body?.description ?? '').trim();
	if (!descripcion) fail(400, 'journal_missing_description');

	const activas = new Set(db.accounts.filter((c) => c.is_active).map((c) => c.id));
	const lineas = (Array.isArray(body?.lines) ? body.lines : [])
		.filter(
			(l: any) => round2(Number(l?.debit ?? 0)) !== 0 || round2(Number(l?.credit ?? 0)) !== 0
		)
		.map((l: any) => {
			if (!activas.has(Number(l?.account_id)))
				fail(404, 'account_not_found', { account_id: Number(l?.account_id) });
			const debit = round2(Number(l?.debit ?? 0));
			const credit = round2(Number(l?.credit ?? 0));
			if (debit < 0 || credit < 0) fail(400, 'invalid_journal_line', { reason: 'negative' });
			if (debit > 0 && credit > 0)
				fail(400, 'invalid_journal_line', { reason: 'both_sides' });
			return { account_id: Number(l.account_id), debit, credit, memo: l?.memo ?? null };
		});
	if (!lineas.length) fail(400, 'invalid_journal_line', { reason: 'no_lines' });

	const asiento = asentar(companyId, () =>
		postEntry(
			companyId,
			{
				kind: String(body?.kind ?? 'manual') as JournalEntry['kind'],
				entry_date: String(body?.entry_date ?? '').slice(0, 10),
				description: descripcion,
				lines: lineas,
				adjusts_entry_id:
					body?.adjusts_entry_id != null ? Number(body.adjusts_entry_id) : null
			},
			Number(userId ?? 0)
		)
	);
	if (!asiento) fail(400, 'accounting_not_active');

	persist();
	return asientoConLineas(companyId, asiento);
});

route('GET', '/accounting/entries/:id', ({ params, companyId }) => {
	const asiento = getDb(companyId).journal_entries.find((a) => a.id === Number(params[0]));
	if (!asiento) fail(404, 'journal_entry_not_found', { entry_id: Number(params[0]) });
	return asientoConLineas(companyId, asiento);
});

route('POST', '/accounting/entries/:id/reclassify', ({ params, body, companyId, userId }) => {
	exigirModulo(companyId, 'accounting');
	const db = getDb(companyId);
	const entryId = Number(params[0]);
	if (!db.journal_entries.some((a) => a.id === entryId))
		fail(404, 'journal_entry_not_found', { entry_id: entryId });

	const destino = db.accounts.find((c) => c.id === Number(body?.account_id));
	if (!destino || !destino.is_active)
		fail(404, 'account_not_found', { account_id: Number(body?.account_id) });

	const ajuste = asentar(companyId, () =>
		postReclassification(
			companyId,
			entryId,
			destino.id,
			nowIso().slice(0, 10),
			Number(userId ?? 0),
			String(body?.description ?? '')
		)
	);
	if (!ajuste) fail(400, 'nothing_to_reclassify', { entry_id: entryId });

	persist();
	return { adjustment_entry_id: ajuste.id };
});

// --------------------------------------------------------------- los periodos

route('GET', '/accounting/periods', ({ companyId }) =>
	[...getDb(companyId).accounting_periods].sort((a, b) => b.year - a.year || b.month - a.month)
);

route('POST', '/accounting/periods/:year/:month/close', ({ params, companyId, userId }) => {
	exigirModulo(companyId, 'accounting');
	const db = getDb(companyId);
	const year = Number(params[0]);
	const month = Number(params[1]);

	const periodo = db.accounting_periods.find((p) => p.year === year && p.month === month);
	if (!periodo) fail(404, 'period_not_found', { year, month });
	if (periodo.status === 'closed') fail(400, 'period_closed', { year, month });

	const [anteriorAnio, anteriorMes] = month === 1 ? [year - 1, 12] : [year, month - 1];
	const anterior = db.accounting_periods.find(
		(p) => p.year === anteriorAnio && p.month === anteriorMes
	);
	if (anterior && anterior.status !== 'closed')
		fail(400, 'period_not_closeable', {
			year,
			month,
			blocking_year: anteriorAnio,
			blocking_month: anteriorMes
		});

	periodo.status = 'closed';
	periodo.closed_at = nowIso();
	periodo.closed_by = Number(userId ?? 0);
	registrar(
		Number(userId ?? 0),
		companyId,
		'cerrar_periodo',
		`${year}-${String(month).padStart(2, '0')}`
	);
	persist();
	return periodo;
});

// -------------------------------------------------------------- los reportes

route('GET', '/accounting/reports/trial-balance', ({ query, companyId }) => {
	const year = Number(query.get('year'));
	const month = query.get('month') ? Number(query.get('month')) : null;
	const [desde, hasta] = rangoDelPeriodo(year, month);
	const filas = trialBalance(companyId, hasta, desde);
	const debits = round2(filas.reduce((t, f) => t + f.debits, 0));
	const credits = round2(filas.reduce((t, f) => t + f.credits, 0));
	return { year, month, rows: filas, debits, credits, is_balanced: debits === credits };
});

route('GET', '/accounting/reports/income', ({ query, companyId }) => {
	const year = Number(query.get('year'));
	const month = query.get('month') ? Number(query.get('month')) : null;
	const [desde, hasta] = rangoDelPeriodo(year, month);
	const filas = trialBalance(companyId, hasta, desde);
	const income = totalDe(filas, 'income');
	const cost = totalDe(filas, 'cost');
	const expense = totalDe(filas, 'expense');
	return {
		year,
		month,
		income,
		cost,
		expense,
		gross_profit: round2(income - cost),
		result: round2(income - cost - expense),
		rows: filas.filter((f) => ['income', 'cost', 'expense'].includes(f.kind))
	};
});

route('GET', '/accounting/reports/balance', ({ query, companyId }) => {
	const year = Number(query.get('year'));
	const month = query.get('month') ? Number(query.get('month')) : null;
	// Acumulado, no del mes: el efectivo que hay hoy es todo lo que entró y
	// salió desde que existe el libro.
	const [, hasta] = rangoDelPeriodo(year, month);
	const filas = trialBalance(companyId, hasta);
	const assets = totalDe(filas, 'asset');
	const liabilities = totalDe(filas, 'liability');
	const equity = totalDe(filas, 'equity');
	const result = round2(
		totalDe(filas, 'income') - totalDe(filas, 'cost') - totalDe(filas, 'expense')
	);
	return {
		year,
		month,
		assets,
		liabilities,
		equity,
		result,
		is_balanced: assets === round2(liabilities + equity + result),
		rows: filas.filter((f) => ['asset', 'liability', 'equity'].includes(f.kind))
	};
});

route('GET', '/accounting/reports/journal', ({ query, companyId }) => {
	const db = getDb(companyId);
	const year = Number(query.get('year'));
	const month = query.get('month') ? Number(query.get('month')) : null;
	const [desde, hasta] = rangoDelPeriodo(year, month);
	return {
		year,
		month,
		entries: db.journal_entries
			.filter((a) => a.entry_date >= desde && a.entry_date <= hasta)
			.sort(
				(a, b) => a.entry_date.localeCompare(b.entry_date) || a.entry_number - b.entry_number
			)
			.map((a) => asientoConLineas(companyId, a))
	};
});

route('GET', '/accounting/reports/ledger', ({ query, companyId }) => {
	const db = getDb(companyId);
	const year = Number(query.get('year'));
	const month = query.get('month') ? Number(query.get('month')) : null;
	const filtro = query.get('account_id') ? Number(query.get('account_id')) : null;
	const [desde, hasta] = rangoDelPeriodo(year, month);

	const antes = new Map(
		trialBalance(companyId, restarUnDia(desde)).map((f) => [f.account_id, f.balance])
	);
	const delPeriodo = trialBalance(companyId, hasta, desde);
	const porId = new Map(db.journal_entries.map((a) => [a.id, a]));

	return {
		year,
		month,
		accounts: delPeriodo
			.filter((f) => filtro == null || f.account_id === filtro)
			.map((f) => {
				const inicial = antes.get(f.account_id) ?? 0;
				return {
					...f,
					opening: inicial,
					closing: round2(inicial + f.balance),
					movements: db.journal_lines
						.filter((l) => l.account_id === f.account_id)
						.map((l) => ({ linea: l, asiento: porId.get(l.entry_id) }))
						.filter(
							(par) =>
								par.asiento &&
								par.asiento.entry_date >= desde &&
								par.asiento.entry_date <= hasta
						)
						.sort(
							(a, b) =>
								a.asiento!.entry_date.localeCompare(b.asiento!.entry_date) ||
								a.asiento!.entry_number - b.asiento!.entry_number
						)
						.map((par) => ({
							entry_id: par.asiento!.id,
							entry_number: par.asiento!.entry_number,
							entry_date: par.asiento!.entry_date,
							description: par.asiento!.description,
							debit: par.linea.debit,
							credit: par.linea.credit,
							memo: par.linea.memo
						}))
				};
			})
	};
});

function ventasPorTarifa(companyId: number, desde: string, hasta: string) {
	const db = getDb(companyId);
	const acumulado = new Map<
		number,
		{ base: number; tax: number; returnsBase: number; returnsTax: number }
	>();
	const tasaDelNegocio = configuredTaxRate(companyId);

	const entrada = (tarifa: number) => {
		if (!acumulado.has(tarifa))
			acumulado.set(tarifa, { base: 0, tax: 0, returnsBase: 0, returnsTax: 0 });
		return acumulado.get(tarifa)!;
	};

	for (const venta of db.sales) {
		const dia = venta.created_at.slice(0, 10);
		if (dia < desde || dia > hasta) continue;
		for (const linea of venta.items) {
			const tarifa = linea.tax_rate ?? tasaDelNegocio;
			const fila = entrada(tarifa);
			fila.base = round2(fila.base + linea.subtotal);
			fila.tax = round2(fila.tax + (linea.tax_amount ?? 0));
		}
	}
	for (const devolucion of db.returns) {
		const dia = devolucion.created_at.slice(0, 10);
		if (dia < desde || dia > hasta) continue;
		const venta = db.sales.find((s) => s.id === devolucion.sale_id);
		for (const linea of devolucion.items) {
			const tarifa =
				venta?.items.find((v) => v.id_product === linea.id_product)?.tax_rate ??
				tasaDelNegocio;
			const fila = entrada(tarifa);
			const base = round2(linea.price * linea.quantity);
			fila.returnsBase = round2(fila.returnsBase + base);
			fila.returnsTax = round2(fila.returnsTax + lineTax(base, tarifa));
		}
	}
	return acumulado;
}

function comprasPorTarifa(companyId: number, desde: string, hasta: string) {
	const db = getDb(companyId);
	const acumulado = new Map<number, { base: number; tax: number }>();
	for (const compra of db.stock_entries) {
		if (compra.status !== 'aplicada' || compra.supplier_id == null) continue;
		const dia = (compra.document_date ?? compra.created_at).slice(0, 10);
		if (dia < desde || dia > hasta) continue;
		for (const linea of compra.lines ?? []) {
			// La tarifa de una compra viaja **en porcentaje** —13 y no 0,13—
			// porque es la que dice la factura del proveedor. Cruzarla con la de
			// ventas sin convertir parte el D-104 en dos filas.
			const tarifa = round2((linea.tax_rate ?? 0) / 100);
			const fila = acumulado.get(tarifa) ?? { base: 0, tax: 0 };
			acumulado.set(tarifa, {
				base: round2(fila.base + linea.subtotal),
				tax: round2(fila.tax + Number(linea.tax_amount ?? 0))
			});
		}
	}
	return acumulado;
}

route('GET', '/accounting/vat', ({ query, companyId }) => {
	const year = Number(query.get('year'));
	const month = query.get('month') ? Number(query.get('month')) : null;
	const [desde, hasta] = rangoDelPeriodo(year, month);

	const ventas = ventasPorTarifa(companyId, desde, hasta);
	const compras = comprasPorTarifa(companyId, desde, hasta);

	const tarifas = [...new Set([...ventas.keys(), ...compras.keys()])].sort((a, b) => a - b);
	const lineas = tarifas.map((tarifa) => {
		const v = ventas.get(tarifa) ?? { base: 0, tax: 0, returnsBase: 0, returnsTax: 0 };
		const c = compras.get(tarifa) ?? { base: 0, tax: 0 };
		const debit = round2(v.tax - v.returnsTax);
		return {
			tax_rate: tarifa,
			sales_base: round2(v.base - v.returnsBase),
			debit,
			returns_tax: v.returnsTax,
			purchases_base: c.base,
			credit: c.tax,
			balance: round2(debit - c.tax)
		};
	});

	const debit = round2(lineas.reduce((t, l) => t + l.debit, 0));
	const credit = round2(lineas.reduce((t, l) => t + l.credit, 0));
	return {
		year,
		month,
		lines: lineas,
		debit,
		credit,
		balance: round2(debit - credit),
		in_favor: round2(debit - credit) < 0
	};
});

route('GET', '/reports/sales_by_rate', ({ query, companyId }) => {
	const { from, to } = parseRange(query);
	const ventas = ventasPorTarifa(companyId, from, to);
	const lineas = [...ventas.entries()]
		.sort((a, b) => a[0] - b[0])
		.map(([tarifa, v]) => ({
			tax_rate: tarifa,
			base: v.base,
			tax: v.tax,
			returns_base: v.returnsBase,
			returns_tax: v.returnsTax,
			net_base: round2(v.base - v.returnsBase),
			net_tax: round2(v.tax - v.returnsTax)
		}));
	return {
		date_from: from,
		date_to: to,
		by_rate: lineas,
		tax: round2(lineas.reduce((t, l) => t + l.tax, 0)),
		returns_tax: round2(lineas.reduce((t, l) => t + l.returns_tax, 0)),
		net_tax: round2(lineas.reduce((t, l) => t + l.net_tax, 0))
	};
});

// ------------------------------------------- factura electrónica (F6, T-615)
//
// Los seis endpoints de `/fe`, con el contrato de `app/router/fe_routes.py`.
// Sin esto la fase no tiene ninguna prueba de flujo: la batería de punta a punta
// corre con `POS_MOCK=1`. Es el agujero que en F5 hizo que el simulado
// reembolsara cero durante dos días.
//
// **Acá tampoco existe el camino que devuelve el archivo, el PIN o la
// contraseña** (RF-23, RN-16), y la ausencia es deliberada: un simulado que los
// devolviera dejaría sin probar justo la propiedad que importa.

const AMBIENTES = ['sandbox', 'production'] as const;
type Ambiente = (typeof AMBIENTES)[number];

/** Lo mismo que `crud_fe.MAX_P12_BYTES`. */
const MAX_P12_BYTES = 256 * 1024;

/**
 * Los 30 días de `domain/fe_credentials.WARNING_DAYS`.
 *
 * No se llama `DIAS_DE_AVISO` a secas porque ya hay uno: el de la suscripción,
 * que son 7. Son dos avisos distintos sobre dos cosas distintas y el día que
 * alguien los unifique por el nombre, un certificado avisará con una semana.
 */
const DIAS_DE_AVISO_DEL_CERTIFICADO = 30;

function ambienteValido(valor: string): Ambiente {
	if (!(AMBIENTES as readonly string[]).includes(valor))
		fail(400, 'invalid_environment', { environment: valor });
	return valor as Ambiente;
}

function feFilas(companyId: number): MockFeCredentials[] {
	const empresa = getEmpresa(companyId);
	// Se escribe en la porción de la compañía y no en la vista, por lo mismo que
	// `settingsRow`: la vista es una copia superficial.
	if (!empresa.fe_credentials) empresa.fe_credentials = [];
	return empresa.fe_credentials;
}

function feFila(companyId: number, environment: Ambiente): MockFeCredentials {
	const filas = feFilas(companyId);
	let fila = filas.find((f) => f.environment === environment);
	if (!fila) {
		fila = {
			environment,
			certificate_name: null,
			expires_at: null,
			cert_uploaded_at: null,
			atv_user: null,
			atv_configured: false,
			atv_verified_at: null,
			atv_verdict: 'ok'
		};
		filas.push(fila);
	}
	return fila;
}

/**
 * El ambiente en uso, con el mismo respaldo que `crud_fe._activo`.
 *
 * Por omisión pruebas: una compañía que nunca lo configuró **no** está emitiendo
 * en producción, y suponer lo contrario sería suponer efecto fiscal donde no lo
 * hay. Lo mismo con un valor que no se entiende.
 */
function ambienteActivo(companyId: number): Ambiente {
	const data = settingsRow(companyId).data as { eInvoicing?: { environment?: unknown } };
	const guardado = String(data?.eInvoicing?.environment ?? '');
	return (AMBIENTES as readonly string[]).includes(guardado) ? (guardado as Ambiente) : 'sandbox';
}

/**
 * Días enteros hasta el vencimiento del certificado.
 *
 * Aparte de `diasHasta`, que cuenta días de calendario para la suscripción: el
 * `notAfter` de un certificado **tiene hora**, y uno que vence a las 10:00 no
 * sirve a las 11:00. Redondear a medianoche diría que sirve durante catorce
 * horas en que no sirve, y esas catorce horas son un día de facturación entero.
 */
function diasHastaElVencimiento(iso: string | null): number | null {
	if (!iso) return null;
	// Truncado hacia abajo con signo, como `timedelta.days`: lo que vence en
	// veintitrés horas devuelve 0, porque no alcanza para un día más de trabajo.
	return Math.floor((new Date(iso).getTime() - Date.now()) / 86_400_000);
}

function estadoDelCertificado(iso: string | null): string {
	if (!iso) return 'missing';
	if (new Date(iso).getTime() <= Date.now()) return 'expired';
	return diasHastaElVencimiento(iso)! <= DIAS_DE_AVISO_DEL_CERTIFICADO ? 'expiring' : 'valid';
}

/**
 * El espejo de `crud_settings._conservar_protegidos`, para el único campo
 * protegido que hay hoy.
 *
 * Un campo que no estaba sigue sin estar: si nadie eligió ambiente todavía, esto
 * no inventa uno.
 */
function conservarAmbiente(nuevo: any, anterior: any): void {
	const guardado = anterior?.eInvoicing?.environment;
	if (guardado === undefined || guardado === null) {
		if (nuevo?.eInvoicing && typeof nuevo.eInvoicing === 'object')
			delete nuevo.eInvoicing.environment;
		return;
	}
	if (!nuevo.eInvoicing || typeof nuevo.eInvoicing !== 'object') nuevo.eInvoicing = {};
	nuevo.eInvoicing.environment = guardado;
}

function feSalida(fila: MockFeCredentials) {
	const estado = estadoDelCertificado(fila.expires_at);
	return {
		environment: fila.environment,
		certificate_configured: estado !== 'missing',
		certificate_name: fila.certificate_name,
		expires_at: fila.expires_at,
		days_left: diasHastaElVencimiento(fila.expires_at),
		certificate_status: estado,
		uploaded_at: fila.cert_uploaded_at,
		atv_user: fila.atv_user,
		atv_configured: fila.atv_configured,
		atv_verified_at: fila.atv_verified_at,
		// Las tres condiciones, y la tercera es la que se olvida: un certificado
		// vencido está configurado y no sirve.
		ready: (estado === 'valid' || estado === 'expiring') && fila.atv_configured
	};
}

function feEstado(companyId: number) {
	return {
		environments: AMBIENTES.map((a) => feSalida(feFila(companyId, a))),
		active: ambienteActivo(companyId),
		production_gate: puertaDeProduccion(companyId)
	};
}

/**
 * Un administrador de **esta** compañía, o el «no» que corresponda.
 *
 * No se llama `feAdmin` aunque naciera con `/fe`: lo usan también las rutas de
 * `/offices`, y allá el `require_admin` del backend es el que hace que el
 * bloqueo por suscripción las alcance sin tocar nada.
 */
function exigirAdmin(userId: number | null, companyId: number): MockUser {
	if (userId == null) fail(401, 'unauthorized');
	const user = getDb(companyId).users.find((u) => u.id_user === userId);
	if (!user) fail(401, 'unauthorized');
	if ((rolEn(user.id_user, companyId) ?? user.role) !== 'admin') fail(403, 'admin_only');
	return user;
}

/**
 * Qué va a contestar el IdP, deducido de la contraseña **sin guardarla**.
 *
 * Los tres desenlaces de RF-31 no se pueden provocar contra un servicio de
 * verdad —«Hacienda caída» hay que esperar a que pase— así que una prueba de
 * punta a punta que quiera ver los tres necesita poder pedirlos. La convención
 * vive acá y en ningún otro sitio: una contraseña que empieza por `mal-` la
 * rechazan, y una que empieza por `caido-` no contesta.
 *
 * Lo que **no** hace es guardar la contraseña para mirarla después: se lee al
 * llegar, se deja el veredicto y el valor se descarta — igual que el de verdad
 * la cifra y no la vuelve a mostrar nunca.
 */
function veredictoDe(password: string): MockFeCredentials['atv_verdict'] {
	if (password.startsWith('mal-')) return 'rejected';
	if (password.startsWith('caido-')) return 'unreachable';
	return 'ok';
}

route('GET', '/fe', ({ userId, companyId }) => {
	exigirAdmin(userId, companyId);
	return feEstado(companyId);
});

route('POST', '/fe/:ambiente/certificate', ({ params, userId, companyId, upload }) => {
	exigirAdmin(userId, companyId);
	const ambiente = ambienteValido(params[0]);

	const bytes = upload?.bytes ?? new Uint8Array();
	const pin = String(upload?.fields?.pin ?? '');
	if (bytes.byteLength > MAX_P12_BYTES)
		fail(413, 'certificate_too_large', { limit: MAX_P12_BYTES });

	// El simulado no abre un PKCS#12 de verdad, pero sí reproduce los cuatro
	// motivos por los que el de verdad se niega, que es lo que la pantalla tiene
	// que saber distinguir.
	//
	// El primero se deduce igual que allá: un `.p12` verdadero empieza por 0x30,
	// porque en DER siempre es una SEQUENCE. Los otros tres se piden por el
	// contenido, como `veredictoDe`.
	const texto = Buffer.from(bytes).toString('utf-8');
	if (bytes.byteLength === 0 || bytes[0] !== 0x30)
		fail(400, 'invalid_certificate', { reason: 'not_a_p12' });
	if (!pin) fail(400, 'invalid_certificate', { reason: 'bad_pin' });
	for (const motivo of ['bad_pin', 'no_private_key', 'no_certificate'])
		if (texto.includes(motivo)) fail(400, 'invalid_certificate', { reason: motivo });

	// El nombre sale del certificado y no del archivo: «llave (1).p12» no le dice
	// nada a nadie seis meses después.
	const sujeto = /SUJETO=([^|]+)/.exec(texto)?.[1]?.trim() || 'CERTIFICADO DE PRUEBA S.A.';
	const dias = Number(/DIAS=(-?\d+)/.exec(texto)?.[1] ?? 365);

	const fila = feFila(companyId, ambiente);
	fila.certificate_name = sujeto;
	fila.expires_at = new Date(Date.now() + dias * 86_400_000).toISOString();
	fila.cert_uploaded_at = nowIso();
	persist();
	return feEstado(companyId);
});

route('DELETE', '/fe/:ambiente/certificate', ({ params, userId, companyId }) => {
	exigirAdmin(userId, companyId);
	const fila = feFila(companyId, ambienteValido(params[0]));
	fila.certificate_name = null;
	fila.expires_at = null;
	fila.cert_uploaded_at = null;
	// RF-24: quitar el certificado **no** toca las credenciales de transmisión.
	persist();
	return feEstado(companyId);
});

route('PUT', '/fe/:ambiente/atv', ({ params, body, userId, companyId }) => {
	exigirAdmin(userId, companyId);
	const ambiente = ambienteValido(params[0]);

	const usuario = String(body?.user ?? '').trim();
	const password = String(body?.password ?? '');
	if (!usuario) fail(400, 'atv_user_required');

	const fila = feFila(companyId, ambiente);
	fila.atv_user = usuario;
	fila.atv_configured = password.length > 0;
	fila.atv_verdict = veredictoDe(password);
	// La verificación anterior deja de valer: son otras credenciales.
	fila.atv_verified_at = null;
	persist();
	return feEstado(companyId);
});

route('POST', '/fe/:ambiente/atv/verify', ({ params, userId, companyId }) => {
	exigirAdmin(userId, companyId);
	const ambiente = ambienteValido(params[0]);
	const fila = feFila(companyId, ambiente);

	if (!fila.atv_user || !fila.atv_configured)
		fail(409, 'atv_not_configured', { environment: ambiente });

	if (fila.atv_verdict === 'rejected') {
		// El «no» de Hacienda es más fuerte que cualquier marca anterior.
		fila.atv_verified_at = null;
		persist();
		fail(400, 'atv_invalid_credentials', { environment: ambiente });
	}
	if (fila.atv_verdict === 'unreachable') {
		// **No se toca nada**: no se aprendió nada sobre las credenciales, y tirar
		// una verificación buena porque Hacienda estaba caída sería convertir su
		// caída en un problema del cliente (RF-31).
		fail(503, 'atv_unreachable', { environment: ambiente });
	}

	fila.atv_verified_at = nowIso();
	persist();
	return feEstado(companyId);
});

route('PUT', '/fe/active', ({ body, userId, companyId }) => {
	const user = exigirAdmin(userId, companyId);
	const destino = ambienteValido(String(body?.environment ?? ''));
	const anterior = ambienteActivo(companyId);
	if (destino === anterior) return feEstado(companyId);

	// Solo producción se confirma (RN-35). Volver a pruebas no: exigir
	// confirmación para deshacer convierte la salida de un error en un segundo
	// trámite, justo cuando alguien acaba de darse cuenta del error.
	if (destino === 'production' && body?.confirm !== true)
		fail(400, 'confirmation_required', { environment: destino });
	// T-713, RN-46: sin una factura, un tiquete y una nota de crédito aceptados
	// en pruebas, no se pasa, y se dice cuál falta.
	if (destino === 'production') {
		const puerta = puertaDeProduccion(companyId);
		if (!puerta.ready) fail(409, 'production_gate_locked', { missing: puerta.missing });
	}

	const fila = settingsRow(companyId);
	const data = (fila.data ?? {}) as { eInvoicing?: Record<string, unknown> };
	data.eInvoicing = { ...(data.eInvoicing ?? {}), environment: destino };
	fila.data = data;
	fila.updated_at = nowIso();
	fila.updated_by = user.id_user;

	registrar(user.id_user, companyId, 'fe_ambiente', `${anterior} → ${destino}`);
	persist();
	return feEstado(companyId);
});

// ------------------------------------------ sucursales y cajas (F6, T-608)
//
// Las siete rutas de `/offices`, con el contrato de `app/router/office_routes.py`:
// **todas devuelven el estado completo** —las sucursales, sus cajas y el cupo del
// plan— y no la fila que tocaron. Una sola forma de respuesta significa que la
// pantalla no mezcla lo que tenía con lo que le llega, y acá hace falta de
// verdad, porque apagar una sucursal apaga sus cajas y crear una consume cupo.

/** Los que fija Hacienda, como en `domain/office.py`. No se configuran. */
const DIGITOS_DE_SUCURSAL = 3;
const DIGITOS_DE_CAJA = 5;

/** Lo que se escribe en el plan para decir «sin techo» (`domain/limits.py`). */
const SIN_LIMITE = -1;

/**
 * El código normalizado, o el «no» con su motivo. El espejo de `_normalizar`.
 *
 * «1» entra como «001»: sin rellenar acá, la caja 1 y la caja 001 serían dos
 * filas con el mismo número en el comprobante. Y **lo que no cabe no se
 * recorta**: recortar en silencio sería cambiarle el número a alguien.
 *
 * Con una diferencia sabida: `\d` es ASCII y el `isdigit()` de Python acepta
 * también «٣». La puerta de acá es más angosta, nunca más ancha, así que el
 * simulado no deja pasar nada que el backend fuera a rechazar.
 */
function codigoDeOficina(valor: unknown, digitos: number): string {
	if (typeof valor !== 'string' && typeof valor !== 'number')
		fail(400, 'invalid_office_code', { reason: 'not_text', digits: digitos });

	const limpio = String(valor).trim();
	if (!limpio) fail(400, 'invalid_office_code', { reason: 'empty', digits: digitos });
	if (!/^\d+$/.test(limpio))
		fail(400, 'invalid_office_code', { reason: 'not_digits', digits: digitos });
	// Los dígitos **significativos**: «00001» con tres es 1 y cabe; «1234» no.
	if ((limpio.replace(/^0+/, '') || '0').length > digitos)
		fail(400, 'invalid_office_code', { reason: 'too_long', digits: digitos });

	return limpio.padStart(digitos, '0').slice(-digitos);
}

function sucursalesDe(companyId: number): MockBranch[] {
	const empresa = getEmpresa(companyId);
	// Se escribe en la porción de la compañía y no en la vista de `getDb`, por lo
	// mismo que `feFilas`: la vista es una copia superficial.
	if (!empresa.branches) empresa.branches = [];
	return empresa.branches;
}

function cajasDe(companyId: number): MockTerminal[] {
	const empresa = getEmpresa(companyId);
	if (!empresa.terminals) empresa.terminals = [];
	return empresa.terminals;
}

/** Cuántas **activas**. Lo que el plan vende es cuántas puede operar. */
function cuantasActivas(filas: { activa: boolean }[]): number {
	return filas.filter((f) => f.activa).length;
}

function hayLugar(actuales: number, maximo: number): boolean {
	// `<` y no `<=`: la que se está creando todavía no está contada.
	return maximo < 0 || actuales < maximo;
}

function cabeOtraSucursal(companyId: number): void {
	const plan = planDe(companyId);
	if (!plan) return;
	const actuales = cuantasActivas(sucursalesDe(companyId));
	if (!hayLugar(actuales, plan.max_sucursales))
		fail(400, 'plan_limit_reached', {
			resource: 'branches',
			current: actuales,
			max: plan.max_sucursales
		});
}

function cabeOtraCaja(companyId: number): void {
	const plan = planDe(companyId);
	if (!plan) return;
	// El máximo es **por compañía** y no por sucursal, igual que allá: un techo
	// por sucursal dejaría que un plan de tres cajas tuviera treinta abriendo
	// diez locales.
	const actuales = cuantasActivas(cajasDe(companyId));
	if (!hayLugar(actuales, plan.max_terminales))
		fail(400, 'plan_limit_reached', {
			resource: 'terminals',
			current: actuales,
			max: plan.max_terminales
		});
}

function cupoDeOficinas(companyId: number) {
	const plan = planDe(companyId);
	return {
		branches: cuantasActivas(sucursalesDe(companyId)),
		max_branches: plan ? plan.max_sucursales : SIN_LIMITE,
		terminals: cuantasActivas(cajasDe(companyId)),
		max_terminals: plan ? plan.max_terminales : SIN_LIMITE
	};
}

function officeEstado(companyId: number) {
	return {
		branches: [...sucursalesDe(companyId)].sort((a, b) => a.codigo.localeCompare(b.codigo)),
		terminals: [...cajasDe(companyId)].sort(
			(a, b) => a.branch_id - b.branch_id || a.codigo.localeCompare(b.codigo)
		),
		quota: cupoDeOficinas(companyId)
	};
}

/**
 * Cuántas filas de negocio nombran a esta sucursal (RN-7).
 *
 * En el simulado las ventas no llevan `branch_id` —nada más lo necesita— así que
 * la historia se le atribuye a la sucursal **con la que la compañía vende**, que
 * es la que declara su sesión (`companies.branch_code`, lo que allá resuelve
 * `sucursal_actual()`). Es donde de verdad se hizo: el seed vende desde la única
 * que hay.
 *
 * Con eso la pantalla tiene los dos casos que hay que poder distinguir: la que
 * arrastra historia no se borra, y una creada desde la pantalla nace sin nada y
 * sí se borra.
 */
function historiaDeLaSucursal(companyId: number, sucursal: MockBranch): number {
	const empresa = getRoot().companies.find((c) => c.id === companyId);
	if (empresa?.branch_code !== sucursal.codigo) return 0;
	const db = getDb(companyId);
	// Las tres suman un número porque para quien decide son lo mismo: historial
	// que se quedaría apuntando a la nada.
	return db.sales.length + db.returns.length + db.stock_entries.length;
}

/**
 * Lo mismo para una caja: arqueos y ventas, por separado.
 *
 * Se piden los **dos** códigos, el de la caja y el de su sucursal: el de caja es
 * único por sucursal, así que el «00001» de un local nuevo no es el «00001» con
 * el que la compañía vende, y atribuirle la historia de ese haría que una caja
 * recién creada naciera imposible de borrar.
 */
function historiaDeLaCaja(companyId: number, caja: MockTerminal) {
	const empresa = getRoot().companies.find((c) => c.id === companyId);
	const sucursal = sucursalesDe(companyId).find((s) => s.id === caja.branch_id);
	const db = getDb(companyId);
	const suya =
		empresa?.terminal_code === caja.codigo && empresa?.branch_code === sucursal?.codigo;
	return {
		sessions: suya ? db.cash_sessions.length : 0,
		sales: suya ? db.sales.length : 0
	};
}

/** No se deja a la compañía sin sucursal activa: sin una no se puede vender. */
function ultimaSucursalNo(companyId: number, sucursal: MockBranch): void {
	if (!sucursal.activa) return;
	if (cuantasActivas(sucursalesDe(companyId)) <= 1) fail(409, 'last_active_branch');
}

/**
 * Ni a una sucursal activa sin caja activa.
 *
 * Con las dos salidas de `_ultima_terminal_no`: una caja ya apagada no deja a
 * nadie sin caja al irse, y las de una sucursal apagada pueden estarlo todas
 * —apagarla es justamente lo que las apaga—.
 */
function ultimaCajaNo(companyId: number, caja: MockTerminal): void {
	if (!caja.activa) return;
	const sucursal = sucursalesDe(companyId).find((s) => s.id === caja.branch_id);
	if (!sucursal || !sucursal.activa) return;
	const suyas = cajasDe(companyId).filter((c) => c.branch_id === caja.branch_id);
	if (cuantasActivas(suyas) <= 1) fail(409, 'last_active_terminal');
}

/**
 * El nombre tal como se guarda.
 *
 * El «no» sale con el código `unexpected` a propósito: allá lo rechaza el
 * `min_length=1` del esquema, y el 422 de Pydantic no es un `{code, data}` —el
 * POS lo pinta igual, como «algo salió mal»—. Inventar un código acá haría que
 * el simulado contestara algo que el backend no contesta nunca.
 */
function nombreDeOficina(valor: unknown): string {
	const limpio = String(valor ?? '').trim();
	if (!limpio || limpio.length > 120) fail(422, 'unexpected', { field: 'nombre' });
	return limpio;
}

route('GET', '/offices', ({ userId, companyId }) => {
	exigirAdmin(userId, companyId);
	return officeEstado(companyId);
});

route('POST', '/offices/branches', ({ body, userId, companyId }) => {
	exigirAdmin(userId, companyId);
	const codigo = codigoDeOficina(body?.codigo, DIGITOS_DE_SUCURSAL);
	const nombre = nombreDeOficina(body?.nombre);
	cabeOtraSucursal(companyId);

	const filas = sucursalesDe(companyId);
	if (filas.some((s) => s.codigo === codigo))
		fail(409, 'branch_code_taken', { branch_code: codigo });

	filas.push({ id: nextId('branches'), codigo, nombre, activa: true });
	persist();
	return officeEstado(companyId);
});

route('PUT', '/offices/branches/:id', ({ params, body, userId, companyId }) => {
	exigirAdmin(userId, companyId);
	const sucursal = sucursalesDe(companyId).find((s) => s.id === Number(params[0]));
	if (!sucursal) fail(404, 'branch_not_found');

	// El código **no** se cambia y por eso no se lee: moverlo cambiaría el número
	// de todos los comprobantes ya emitidos desde esa sucursal.
	if (body?.nombre !== undefined && body.nombre !== null)
		sucursal.nombre = nombreDeOficina(body.nombre);

	const activa = body?.activa;
	if (typeof activa === 'boolean' && activa !== sucursal.activa) {
		// Reactivar consume cupo: si no, apagar y encender sería la forma de tener
		// cinco con un plan de tres.
		if (activa) cabeOtraSucursal(companyId);
		else ultimaSucursalNo(companyId, sucursal);
		sucursal.activa = activa;
		if (!activa) {
			// Las cajas de una sucursal apagada no pueden quedar encendidas: el POS
			// las ofrecería y el consecutivo saldría de un local cerrado.
			for (const caja of cajasDe(companyId)) {
				if (caja.branch_id === sucursal.id) caja.activa = false;
			}
		}
	}

	persist();
	return officeEstado(companyId);
});

route('DELETE', '/offices/branches/:id', ({ params, userId, companyId }) => {
	exigirAdmin(userId, companyId);
	const filas = sucursalesDe(companyId);
	const sucursal = filas.find((s) => s.id === Number(params[0]));
	if (!sucursal) fail(404, 'branch_not_found');

	const ventas = historiaDeLaSucursal(companyId, sucursal);
	const cajas = cajasDe(companyId).filter((c) => c.branch_id === sucursal.id).length;
	// Las dos cuentas, porque quien lo lee necesita saber qué mover primero.
	if (ventas || cajas) fail(409, 'branch_in_use', { sales: ventas, terminals: cajas });

	ultimaSucursalNo(companyId, sucursal);
	filas.splice(filas.indexOf(sucursal), 1);
	persist();
	return officeEstado(companyId);
});

route('POST', '/offices/terminals', ({ body, userId, companyId }) => {
	exigirAdmin(userId, companyId);
	const codigo = codigoDeOficina(body?.codigo, DIGITOS_DE_CAJA);
	const nombre = nombreDeOficina(body?.nombre);
	const branchId = Number(body?.branch_id);

	if (!sucursalesDe(companyId).some((s) => s.id === branchId)) fail(404, 'branch_not_found');
	cabeOtraCaja(companyId);

	const filas = cajasDe(companyId);
	// El UNIQUE es **por sucursal**: dos locales pueden tener los dos su «00001».
	if (filas.some((c) => c.branch_id === branchId && c.codigo === codigo))
		fail(409, 'terminal_code_taken', { terminal_code: codigo });

	filas.push({ id: nextId('terminals'), branch_id: branchId, codigo, nombre, activa: true });
	persist();
	return officeEstado(companyId);
});

route('PUT', '/offices/terminals/:id', ({ params, body, userId, companyId }) => {
	exigirAdmin(userId, companyId);
	const caja = cajasDe(companyId).find((c) => c.id === Number(params[0]));
	if (!caja) fail(404, 'terminal_not_found');

	if (body?.nombre !== undefined && body.nombre !== null)
		caja.nombre = nombreDeOficina(body.nombre);

	const activa = body?.activa;
	if (typeof activa === 'boolean' && activa !== caja.activa) {
		if (activa) cabeOtraCaja(companyId);
		else ultimaCajaNo(companyId, caja);
		caja.activa = activa;
	}

	persist();
	return officeEstado(companyId);
});

route('DELETE', '/offices/terminals/:id', ({ params, userId, companyId }) => {
	exigirAdmin(userId, companyId);
	const filas = cajasDe(companyId);
	const caja = filas.find((c) => c.id === Number(params[0]));
	if (!caja) fail(404, 'terminal_not_found');

	const { sessions, sales } = historiaDeLaCaja(companyId, caja);
	if (sessions || sales) fail(409, 'terminal_in_use', { sessions, sales });

	ultimaCajaNo(companyId, caja);
	filas.splice(filas.indexOf(caja), 1);
	persist();
	return officeEstado(companyId);
});

// ------------------------------------------------------------ planilla (F12)
//
// Las rutas de `/payroll/*` viven en `payroll.ts`, con su aritmética en
// `payrollCalc.ts`: son unas treinta y este archivo ya no las aguanta. Reciben
// de acá lo que comparten con el resto —la ruta, el admin, el módulo, la
// bitácora y las tasas del país—.
rutasDePlanilla({
	route,
	exigirAdmin,
	exigirModulo,
	registrar,
	nowIso,
	tasas: tasasDePlanilla
});
