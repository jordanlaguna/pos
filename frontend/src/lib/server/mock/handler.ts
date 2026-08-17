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
	type MockSale,
	type MockSettings
} from './db';
import { DEFAULT_TAX_RATE, changeDue, computeTotals, round2 } from '$lib/domain/money';
import type {
	CashMovement,
	CashSession,
	CashSessionReport,
	LowStockProduct,
	PaymentBreakdown,
	Product,
	ReportSummary,
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
	if (!payload || payload.tipo === 'transito') return null;
	return typeof payload.id_user === 'number' ? payload.id_user : null;
}

function fail(status: number, detail: string): never {
	throw new ApiError(status, detail, { detail });
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

function tokenDeSesion(user: { id_user: number; email: string }, companyId: number, rol: string) {
	return makeToken({
		id_user: user.id_user,
		email: user.email,
		cid: companyId,
		bid: 1,
		tid: 1,
		rol,
		tipo: 'sesion'
	});
}

route('POST', '/auth/login', ({ body }) => {
	const email = String(body?.email ?? '')
		.trim()
		.toLowerCase();
	const password = String(body?.password ?? '');
	const user = getRoot().users.find((u) => u.email.toLowerCase() === email);
	if (!user || user.password !== password) fail(401, 'Credenciales incorrectas');

	const opciones = opcionesDe(user.id_user);
	const disponibles = opciones.filter((o) => o.puede_entrar);

	// Una sola disponible: se entra sin pantalla intermedia (RN-25). Es el caso
	// de los cajeros del demo, que pertenecen solo a la primera compañía.
	if (disponibles.length === 1) {
		return {
			access_token: tokenDeSesion(user, disponibles[0].id, disponibles[0].rol),
			token_type: 'bearer',
			tipo: 'sesion',
			user_id: user.id_user,
			company_id: disponibles[0].id,
			companies: opciones
		};
	}

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
	if (userId == null) fail(401, 'Token inválido o ausente');
	return opcionesDe(userId);
});

route('POST', '/auth/invitation', ({ token }) => {
	const payload = tokenPayload(token);
	if (typeof payload?.id_user !== 'number') fail(401, 'Token inválido o ausente');
	// El demo no tiene invitaciones pendientes: sus dos compañías son del mismo
	// dueño. La ruta existe para que el contrato esté completo.
	fail(404, 'No encontrada');
});

route('POST', '/auth/company', ({ body, token }) => {
	const payload = tokenPayload(token);
	const userId = typeof payload?.id_user === 'number' ? payload.id_user : null;
	if (userId == null) fail(401, 'Token inválido o ausente');

	const user = getRoot().users.find((u) => u.id_user === userId);
	const elegida = Number(body?.company_id);
	const rol = user ? rolEn(user.id_user, elegida) : null;
	// 404 y no 403: un 403 confirmaría que esa compañía existe.
	if (!user || !rol) fail(404, 'No encontrada');

	return {
		access_token: tokenDeSesion(user, elegida, rol),
		token_type: 'bearer',
		tipo: 'sesion',
		user_id: user.id_user,
		company_id: elegida,
		rol
	};
});

route('GET', '/users/me', ({ userId, companyId }) => {
	if (userId == null) fail(401, 'Token inválido o ausente');
	const root = getRoot();
	const user = root.users.find((u) => u.id_user === userId);
	if (!user) fail(404, 'Usuario no encontrado');
	const empresa = root.companies.find((c) => c.id === companyId);
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
		companies_available: opcionesDe(user.id_user).filter((o) => o.puede_entrar).length
	};
});

route('POST', '/users/membership', ({ body, userId, companyId }) => {
	if (userId == null) fail(401, 'Token inválido o ausente');
	const db = getDb(companyId);
	const actor = db.users.find((u) => u.id_user === userId);
	if (actor?.role !== 'admin') fail(403, 'Esta operación es solo para administradores.');

	const email = String(body?.email ?? '').trim().toLowerCase();
	const user = db.users.find((u) => u.email.toLowerCase() === email);
	if (!user) fail(404, 'No hay ninguna cuenta con ese correo.');

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
	if (!user) fail(404, 'Usuario no encontrado');
	const role = String(body?.role ?? '');
	if (role !== 'admin' && role !== 'cajero') fail(400, "El rol debe ser 'admin' o 'cajero'.");
	// El último admin no puede degradarse: dejaría el sistema sin quien administre.
	if (user.role === 'admin' && role !== 'admin') {
		const admins = db.users.filter((u) => u.role === 'admin').length;
		if (admins <= 1) fail(400, 'Debe existir al menos un administrador.');
	}
	user.role = role;
	persist();
	return { message: 'Rol actualizado exitosamente', id_user: id };
});

// ------------------------------------------------------------------- personas

route('POST', '/persons/register', ({ body, companyId }) => {
	const db = getDb(companyId);
	const identification = String(body?.identification ?? '').trim();
	const email = String(body?.email ?? '').trim();
	if (db.persons.some((p) => p.identification === identification))
		fail(400, 'Ya existe una persona con esta cédula.');
	if (db.users.some((u) => u.email.toLowerCase() === email.toLowerCase()))
		fail(400, 'Ya existe un usuario con este correo.');

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
	return { message: 'Registro exitoso', id_user: idUser, id_person: idPerson };
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
	if (!person) fail(404, 'Persona no encontrada.');
	const user = db.users.find((u) => u.id_person === id);

	for (const key of ['birth_date', 'identification', 'name', 'lastName', 'secondName', 'telephone'] as const) {
		if (body?.[key] != null && body[key] !== '') (person as any)[key] = String(body[key]);
	}
	if (body?.email) {
		const taken = db.users.some(
			(u) => u.id_person !== id && u.email.toLowerCase() === String(body.email).toLowerCase()
		);
		if (taken) fail(400, 'Ya existe un usuario con este correo.');
		person.email = String(body.email);
		if (user) user.email = String(body.email);
	}
	persist();
	return { message: 'Persona actualizada exitosamente', id_person: id };
});

// ------------------------------------------------------------------- clientes

route('GET', '/clients/clients_list', ({ companyId }) => getDb(companyId).clients);

route('POST', '/clients/register_client', ({ body, companyId }) => {
	const db = getDb(companyId);
	const identification = String(body?.identification ?? '').trim();
	if (db.clients.some((c) => c.identification === identification))
		fail(400, 'Ya existe un cliente con esta identificación.');
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
	return { message: 'Client registered successfully', id_client: id };
});

route('PUT', '/clients/update_client/:id', ({ params, body, companyId }) => {
	const db = getDb(companyId);
	const id = Number(params[0]);
	const client = db.clients.find((c) => c.id_client === id);
	if (!client) fail(404, 'Cliente no encontrado.');
	for (const [key, value] of Object.entries(body ?? {})) {
		if (value == null || value === '') continue;
		if (key === 'telephone') client.telephone = Number(value);
		else if (key in client) (client as any)[key] = value;
	}
	persist();
	return { message: 'Client information updated successfully', id_client: id };
});

// ------------------------------------------------------------------ productos

route('GET', '/products/products_list', ({ companyId }) => getDb(companyId).products);

route('POST', '/products/add_product', ({ body, companyId }) => {
	const db = getDb(companyId);
	const barcode = String(body?.barcode ?? '').trim();
	if (db.products.some((p) => p.barcode === barcode))
		fail(400, 'Ya existe un producto con este código de barras.');
	const id = nextId('products');
	db.products.push({
		id_product: id,
		name: String(body?.name ?? ''),
		description: String(body?.description ?? ''),
		price: round2(Number(body?.price ?? 0)),
		stock: Math.trunc(Number(body?.stock ?? 0)),
		barcode,
		created_at: String(body?.created_at ?? nowIso()),
		category_id: Number(body?.category_id ?? 0)
	});
	persist();
	return { message: 'Producto registrado exitosamente', id_product: id };
});

route('PUT', '/products/update_product/:id', ({ params, body, companyId }) => {
	const db = getDb(companyId);
	const id = Number(params[0]);
	const product = db.products.find((p) => p.id_product === id);
	if (!product) fail(404, 'Producto no encontrado.');
	if (body?.barcode && db.products.some((p) => p.id_product !== id && p.barcode === body.barcode))
		fail(400, 'Ya existe un producto con este código de barras.');
	for (const [key, value] of Object.entries(body ?? {})) {
		if (value == null || value === '') continue;
		if (key === 'price') product.price = round2(Number(value));
		else if (key === 'stock') product.stock = Math.trunc(Number(value));
		else if (key === 'category_id') product.category_id = Number(value);
		else if (key in product) (product as any)[key] = value;
	}
	persist();
	return { message: 'Información del producto actualizada exitosamente', id_product: id };
});

route('DELETE', '/products/delete_product/:id', ({ params, companyId }) => {
	const db = getDb(companyId);
	const id = Number(params[0]);
	const index = db.products.findIndex((p) => p.id_product === id);
	if (index === -1) fail(404, 'Producto no encontrado.');
	// Un producto ya vendido no se borra: rompería el histórico de facturas.
	if (db.sales.some((s) => s.items.some((i) => i.id_product === id)))
		fail(400, 'No se puede eliminar: el producto tiene ventas registradas.');
	db.products.splice(index, 1);
	persist();
	return { message: 'Producto eliminado exitosamente', id_product: id };
});

/** Búsqueda del escáner: código de barras exacto primero, luego nombre exacto. */
route('GET', '/products/product/:term', ({ params, companyId }) => {
	const term = decodeURIComponent(params[0]).trim();
	const db = getDb(companyId);
	const found =
		db.products.find((p) => p.barcode === term) ??
		db.products.find((p) => p.name.toLowerCase() === term.toLowerCase());
	if (!found) fail(404, 'Producto no encontrado');
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

route('GET', '/categories/categories_list', ({ companyId }) => getDb(companyId).categories);

route('POST', '/categories/register_category', ({ body, companyId }) => {
	const db = getDb(companyId);
	const name = String(body?.name ?? '').trim();
	if (db.categories.some((c) => c.name.toLowerCase() === name.toLowerCase()))
		fail(400, 'Categoría ya registrada con este nombre.');
	const id = nextId('categories');
	db.categories.push({ id, name });
	persist();
	return { id, name };
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
	if (!sale) fail(404, 'Venta no encontrada');
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
	if (!saleNumber) fail(400, 'El número de venta es obligatorio.');
	if (db.sales.some((s) => s.sale_number === saleNumber))
		fail(400, 'Ya existe una venta con este número de venta.');

	const products = Array.isArray(body?.products) ? body.products : [];
	if (!products.length) fail(400, 'La venta debe contener al menos un producto.');

	// Se valida TODO antes de escribir nada: o entra la venta completa, o no entra.
	const items: SaleItem[] = [];
	for (const line of products) {
		const quantity = Math.trunc(Number(line?.stock ?? 0));
		const product = db.products.find((p) => p.id_product === Number(line?.id_product));
		if (!product) fail(404, `Producto ID ${line?.id_product} no encontrado.`);
		if (quantity <= 0)
			fail(400, `Producto ID ${line?.id_product} no válido o cantidad insuficiente.`);
		if (product.stock < quantity)
			fail(400, `Stock insuficiente para el producto ID ${product.id_product}.`);
		items.push({
			id_product: product.id_product,
			name: product.name,
			quantity,
			price: product.price,
			subtotal: round2(product.price * quantity)
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
		items.map((i) => ({ price: i.price, quantity: i.quantity })),
		configuredTaxRate(companyId)
	);
	for (const [campo, dicho, dado] of [
		['subtotal', body?.subtotal, calculado.subtotal],
		['impuesto', body?.tax, calculado.tax],
		['total', body?.total, calculado.total]
	] as const) {
		if (Math.abs(round2(Number(dicho ?? 0)) - dado) > 0.01) {
			fail(
				400,
				`El ${campo} no coincide con el que calcula el servidor: ` +
					`la caja dice ${round2(Number(dicho ?? 0))} y el servidor ${dado}. ` +
					`Recargá el catálogo: los precios pueden haber cambiado.`
			);
		}
	}

	const cashReceived = round2(Number(body?.cash_received ?? 0));
	if (cashReceived < calculado.total)
		fail(
			400,
			`El efectivo recibido (${cashReceived}) no puede ser menor ` +
				`al total de la venta (${calculado.total}).`
		);

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
	return { message: 'Venta registrada exitosamente', id_sale: id };
});

// --------------------------------------------------------------- devoluciones

route('GET', '/returns/returns_list', ({ companyId }) =>
	[...getDb(companyId).returns].sort((a, b) => b.created_at.localeCompare(a.created_at))
);

route('GET', '/returns/return/:id', ({ params, companyId }) => {
	const found = getDb(companyId).returns.find((r) => r.id === Number(params[0]));
	if (!found) fail(404, 'Devolución no encontrada');
	return found;
});

route('POST', '/returns/add_return', ({ body, companyId }) => {
	const db = getDb(companyId);
	const sale = db.sales.find((s) => s.id === Number(body?.sale_id));
	if (!sale) fail(404, 'Venta no encontrada');

	const requested = Array.isArray(body?.items) ? body.items : [];
	if (!requested.length) fail(400, 'Debe indicar al menos un producto a devolver.');

	// Cantidad ya devuelta por producto, para no devolver dos veces lo mismo.
	const already = new Map<number, number>();
	for (const previous of db.returns.filter((r) => r.sale_id === sale.id)) {
		for (const item of previous.items) {
			already.set(item.id_product, (already.get(item.id_product) ?? 0) + item.quantity);
		}
	}

	const items = requested.map((line: any) => {
		const quantity = Math.trunc(Number(line?.quantity ?? 0));
		const sold = sale.items.find((i) => i.id_product === Number(line?.id_product));
		if (!sold) fail(400, `El producto ID ${line?.id_product} no pertenece a esta venta.`);
		if (quantity <= 0) fail(400, `Cantidad inválida para ${sold.name}.`);
		const remaining = sold.quantity - (already.get(sold.id_product) ?? 0);
		if (quantity > remaining)
			fail(400, `Solo quedan ${remaining} unidades por devolver de ${sold.name}.`);
		return {
			id_product: sold.id_product,
			name: sold.name,
			quantity,
			price: sold.price,
			subtotal: round2(sold.price * quantity)
		};
	});

	const netSubtotal = round2(items.reduce((acc: number, i: any) => acc + i.subtotal, 0));
	// La tasa se deduce de la venta que se está devolviendo, no de la configurada
	// hoy: si el negocio cambió el impuesto, lo que se reembolsa es lo que se
	// cobró. Mismo criterio que `_sale_tax_rate` en crud_return.py.
	const soldRate = sale.subtotal > 0 ? sale.tax / sale.subtotal : configuredTaxRate(companyId);
	const total = round2(netSubtotal * (1 + soldRate));

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
	return { message: 'Devolución registrada exitosamente', id_return: id, total };
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
	if (currentSession(user, companyId)) fail(400, 'Ya existe una caja abierta para este usuario.');
	const amount = round2(Number(body?.opening_amount ?? 0));
	if (amount < 0) fail(400, 'El monto de apertura no puede ser negativo.');

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
	if (!session) fail(400, 'No hay una caja abierta. Abra la caja antes de registrar movimientos.');

	const type = String(body?.type ?? '');
	if (type !== 'entrada' && type !== 'salida')
		fail(400, "El tipo de movimiento debe ser 'entrada' o 'salida'.");
	const amount = round2(Number(body?.amount ?? 0));
	if (!(amount > 0)) fail(400, 'El monto debe ser mayor que cero.');
	const reason = String(body?.reason ?? '').trim();
	if (!reason) fail(400, 'Indique el motivo del movimiento.');

	if (type === 'salida') {
		const available = computeExpected(session, companyId).expected_amount;
		if (amount > available)
			fail(400, `No hay suficiente efectivo en caja. Disponible: ${available.toFixed(2)}.`);
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
	if (!session) fail(400, 'No hay una caja abierta para este usuario.');
	const counted = round2(Number(body?.closing_amount ?? 0));
	if (counted < 0) fail(400, 'El monto contado no puede ser negativo.');

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
	if (!session) fail(404, 'Sesión de caja no encontrada');
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
	if (!found) fail(404, 'Entrada no encontrada');
	return found;
});

route('POST', '/inventory/entry', ({ body, companyId }) => {
	const db = getDb(companyId);
	const requested = Array.isArray(body?.lines) ? body.lines : [];
	if (!requested.length) fail(400, 'La entrada debe tener al menos una línea.');

	const documentNumber = body?.document_number ? String(body.document_number).trim() : null;
	if (documentNumber) {
		const duplicate = db.stock_entries.find(
			(e) => e.document_number === documentNumber && e.status === 'aplicada'
		);
		if (duplicate) {
			fail(
				400,
				`El documento ${documentNumber} ya se cargó. Anulá esa entrada si querés repetirla.`
			);
		}
	}

	// Se valida todo antes de escribir: o entra la carga completa, o ninguna.
	const resolved: { product: Product; quantity: number; unitCost: number }[] = [];
	let createdProducts = 0;

	for (const [index, raw] of requested.entries()) {
		const quantity = Math.trunc(Number(raw?.quantity ?? 0));
		const unitCost = round2(Number(raw?.unit_cost ?? 0));
		if (!(quantity > 0)) fail(400, `La línea ${index + 1} tiene una cantidad inválida.`);
		if (unitCost < 0) fail(400, `La línea ${index + 1} tiene un costo negativo.`);

		if (raw?.id_product) {
			const product = db.products.find((p) => p.id_product === Number(raw.id_product));
			if (!product) fail(404, `El producto ID ${raw.id_product} no existe.`);
			resolved.push({ product, quantity, unitCost });
		} else if (raw?.new_product) {
			const data = raw.new_product;
			const barcode = String(data.barcode ?? '').trim();
			if (!barcode)
				fail(400, `La línea ${index + 1} crea un producto sin código de barras.`);
			if (db.products.some((p) => p.barcode === barcode))
				fail(400, `Ya existe un producto con el código de barras ${barcode}.`);

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
			fail(400, `La línea ${index + 1} no indica producto existente ni producto a crear.`);
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
		message: 'Entrada registrada exitosamente',
		id_entry: id,
		products_created: createdProducts,
		units_added: units
	};
});

route('POST', '/inventory/entry/:id/cancel', ({ params, companyId }) => {
	const db = getDb(companyId);
	const entry = db.stock_entries.find((e) => e.id === Number(params[0]));
	if (!entry) fail(404, 'Entrada no encontrada');
	if (entry.status === 'anulada') fail(400, 'La entrada ya está anulada.');

	// Si parte ya se vendió, revertir dejaría el stock en negativo.
	for (const line of entry.lines) {
		const product = db.products.find((p) => p.id_product === line.id_product);
		if (product && product.stock < line.quantity) {
			fail(
				400,
				`No se puede anular: de ${product.name} quedan ${product.stock} unidades y la entrada agregó ${line.quantity}.`
			);
		}
	}

	for (const line of entry.lines) {
		const product = db.products.find((p) => p.id_product === line.id_product);
		if (product) product.stock -= line.quantity;
	}
	entry.status = 'anulada';
	persist();
	return { message: 'Entrada anulada; el stock volvió atrás', id_entry: entry.id };
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
	if (userId == null) fail(401, 'Token inválido o ausente');
	return settingsRow(companyId);
});

route('PUT', '/settings/', ({ userId, body, companyId }) => {
	if (userId == null) fail(401, 'Token inválido o ausente');
	const db = getDb(companyId);
	const user = db.users.find((u) => u.id_user === userId);
	if (!user) fail(401, 'Token inválido o ausente');
	if (user.role !== 'admin') fail(403, 'Esta operación es solo para administradores.');

	const data = body?.data;
	if (!data || typeof data !== 'object' || Array.isArray(data)) {
		fail(400, 'La configuración debe ser un objeto.');
	}
	if (JSON.stringify(data).length > 20_000) fail(400, 'La configuración es demasiado grande.');

	const rate = data?.impuesto?.rate;
	if (rate !== undefined) {
		const n = Number(rate);
		if (!Number.isFinite(n)) fail(400, 'La tasa de impuesto no es un número.');
		if (n < 0 || n > 1)
			fail(400, 'La tasa de impuesto se expresa entre 0 y 1 (0.13 = 13 %).');
	}

	const row = settingsRow(companyId);
	row.data = data;
	if (body?.logo) {
		if (!/^image\/(png|jpeg|webp)$/.test(String(body.logo.mime ?? '')))
			fail(400, 'Formato de imagen no admitido.');
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
	return { message: 'Datos de demostración reiniciados' };
});

// ------------------------------------------------------------------ despachador

export async function mockRequest<T>(request: MockRequest): Promise<T> {
	const [rawPath, rawQuery = ''] = request.path.split('?');
	// `/users/` y `/users` deben resolver igual.
	const path = rawPath.length > 1 && rawPath.endsWith('/') ? rawPath : rawPath;
	const query = new URLSearchParams(rawQuery);
	const userId = readToken(request.token);
	const companyId = companyOf(request.token);

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

	throw new ApiError(404, `Ruta no encontrada en el backend simulado: ${request.method} ${path}`);
}
