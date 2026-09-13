/**
 * El libro del simulado (F11, T-1112).
 *
 * Es el espejo de `backend/app/domain/ledger.py` y de su adaptador. Tiene que
 * decir lo mismo: el POS se desarrolla contra esto y las pruebas de punta a
 * punta corren contra esto, así que un asiento que acá cuadra y allá no —o al
 * revés— sería peor que no tener simulado.
 *
 * Lo que **no** se copia es la aritmética exacta con decimales: el simulado usa
 * `round2` como el resto del mock, igual que hace con los totales de una venta.
 *
 * Vive aparte de `handler.ts` porque son dos cosas distintas: acá está qué
 * asiento deja cada hecho, allá cómo se contesta cada ruta.
 */

import { round2 } from '$lib/domain/money';
import type {
	Account,
	AccountKind,
	AccountingPeriod,
	EntryKind,
	JournalEntry,
	MappingRow
} from '$lib/domain/types';
import {
	getDb,
	nextId,
	type MockAccountMapping,
	type MockDb,
	type MockJournalLine
} from './db';

/** La cuenta donde cae lo que el mapeo no sabe clasificar (RN-59). */
export const UNCLASSIFIED_CODE = '1.9.99';

/** La única plantilla que hay, la misma de `backend/app/domain/chart.py`. */
export const COMMERCE = 'commerce';
export const TEMPLATES = [COMMERCE];

type Plantilla = { code: string; name: string; kind: AccountKind; is_system?: boolean };

export const CHART: Plantilla[] = [
	{ code: '1.1.01', name: 'Caja', kind: 'asset' },
	{ code: '1.1.02', name: 'Bancos', kind: 'asset' },
	{ code: '1.1.03', name: 'Tarjetas por cobrar', kind: 'asset' },
	{ code: '1.1.04', name: 'Clientes', kind: 'asset' },
	{ code: '1.1.05', name: 'IVA crédito fiscal', kind: 'asset' },
	{ code: '1.1.06', name: 'Retenciones a favor', kind: 'asset', is_system: false },
	{ code: '1.2.01', name: 'Inventario', kind: 'asset' },
	{ code: UNCLASSIFIED_CODE, name: 'Por clasificar', kind: 'asset' },
	{ code: '2.1.01', name: 'Proveedores', kind: 'liability' },
	{ code: '2.1.02', name: 'IVA por pagar', kind: 'liability' },
	{ code: '2.1.03', name: 'Retenciones de renta por pagar', kind: 'liability' },
	{ code: '2.1.04', name: 'CCSS por pagar', kind: 'liability' },
	{ code: '2.1.05', name: 'Salarios por pagar', kind: 'liability' },
	{ code: '2.1.06', name: 'Otras deducciones por pagar', kind: 'liability' },
	{ code: '3.1.01', name: 'Capital', kind: 'equity' },
	{ code: '3.2.01', name: 'Resultados acumulados', kind: 'equity' },
	{ code: '4.1.01', name: 'Ventas 13 %', kind: 'income' },
	{ code: '4.1.02', name: 'Ventas 4 %', kind: 'income' },
	{ code: '4.1.03', name: 'Ventas 2 %', kind: 'income' },
	{ code: '4.1.04', name: 'Ventas 1 %', kind: 'income' },
	{ code: '4.1.05', name: 'Ventas exentas', kind: 'income' },
	{ code: '4.2.01', name: 'Devoluciones sobre ventas', kind: 'income' },
	{ code: '4.9.01', name: 'Sobrantes de caja', kind: 'income' },
	{ code: '5.1.01', name: 'Costo de ventas', kind: 'cost' },
	{ code: '6.1.01', name: 'Salarios', kind: 'expense' },
	{ code: '6.1.02', name: 'Cargas sociales patronales', kind: 'expense' },
	{ code: '6.1.03', name: 'Aguinaldo', kind: 'expense' },
	{ code: '6.2.01', name: 'Comisiones de tarjetas', kind: 'expense', is_system: false },
	{ code: '6.9.01', name: 'Faltantes de caja', kind: 'expense' },
	{ code: '6.9.02', name: 'Gastos generales', kind: 'expense', is_system: false }
];

/** Las tarifas con cuenta propia de ingresos, en porcentaje. */
const TARIFAS_DE_VENTA: [string, number][] = [
	['4.1.01', 13],
	['4.1.02', 4],
	['4.1.03', 2],
	['4.1.04', 1],
	['4.1.05', 0]
];

/** El papel de la venta a esa tarifa: `sales_13`. La tasa llega entre 0 y 1. */
export function salesRole(rate: number): string {
	// `${13}` da '13' y `${2.5}` da '2.5', que es justo lo que hace el
	// `_percent_text` del backend. Lo que no se puede usar es notación
	// científica: 'sales_1E+1' no está en ningún mapeo.
	return `sales_${round2(rate * 100)}`;
}

/** A qué papel va el cobro de una venta, según su método de pago (T-1104). */
const METHOD_ROLES: Record<string, string> = {
	Efectivo: 'cash',
	'Tarjeta de crédito': 'cards_receivable',
	'Transferencia bancaria': 'bank',
	'Pago móvil': 'bank'
};

const SUPPLIER_PAYMENT_ROLES: Record<string, string> = { cash: 'cash', transfer: 'bank' };

/** `(evento, papel) → código de cuenta`. El mismo de `domain/chart.py`. */
export function defaultMapping(): Record<string, string> {
	const mapeo: Record<string, string> = {
		'sale|cash': '1.1.01',
		'sale|cards_receivable': '1.1.03',
		'sale|bank': '1.1.02',
		'sale|receivable': '1.1.04',
		'sale|vat_payable': '2.1.02',
		'sale|cogs': '5.1.01',
		'sale|inventory': '1.2.01',
		'return|sales_returns': '4.2.01',
		'return|vat_payable': '2.1.02',
		'return|cash': '1.1.01',
		'return|cogs': '5.1.01',
		'return|inventory': '1.2.01',
		'cash_close|cash': '1.1.01',
		'cash_close|cash_over': '4.9.01',
		'cash_close|cash_short': '6.9.01',
		'cash_movement|cash': '1.1.01',
		'purchase|inventory': '1.2.01',
		'purchase|vat_credit': '1.1.05',
		'purchase|payables': '2.1.01',
		'supplier_payment|payables': '2.1.01',
		'supplier_payment|cash': '1.1.01',
		'supplier_payment|bank': '1.1.02',
		'payroll|salaries': '6.1.01',
		'payroll|employer_contributions': '6.1.02',
		'payroll|income_tax_payable': '2.1.03',
		'payroll|social_security_payable': '2.1.04',
		'payroll|salaries_payable': '2.1.05',
		'payroll|other_deductions_payable': '2.1.06'
	};
	for (const [codigo, porcentaje] of TARIFAS_DE_VENTA) {
		mapeo[`sale|${salesRole(porcentaje / 100)}`] = codigo;
	}
	return mapeo;
}

/** Los papeles que se dejan sin mapear a propósito, con su evento. */
export const UNMAPPED_ON_PURPOSE: [string, string][] = [
	['cash_movement', 'counterpart'],
	['supplier_payment', 'unclassified'],
	['sale', 'unclassified']
];

// ---------------------------------------------------------------- el asiento

export interface LineaCruda {
	account_id: number;
	debit: number;
	credit: number;
	tax_rate?: number | null;
	memo?: string | null;
}

export interface AsientoCrudo {
	kind: EntryKind;
	entry_date: string;
	description: string;
	lines: LineaCruda[];
	source_type?: string | null;
	source_id?: number | null;
	adjusts_entry_id?: number | null;
}

/** La configuración de contabilidad de esa compañía, o vacía. */
export function configuracion(companyId: number): Record<string, unknown> {
	const datos = getDb(companyId).settings?.data as Record<string, unknown> | undefined;
	const seccion = datos?.accounting;
	return seccion && typeof seccion === 'object' ? (seccion as Record<string, unknown>) : {};
}

export function activa(companyId: number): boolean {
	const config = configuracion(companyId);
	return Boolean(config.active) && typeof config.start_date === 'string';
}

function cuentas(db: MockDb): Account[] {
	return db.accounts ?? [];
}

/** `(evento, papel) → id de cuenta`, con «por clasificar» de respaldo (RN-59). */
function mapeoVigente(db: MockDb): (event: string, role: string) => number {
	const porCodigo = new Map(cuentas(db).map((c) => [c.code, c.id]));
	const porClasificar: number = porCodigo.get(UNCLASSIFIED_CODE) ?? 0;
	const puestas = new Map(
		(db.account_mappings ?? []).map((m: MockAccountMapping) => [`${m.event}|${m.role}`, m.account_id] as [string, number])
	);
	return (event, role) => puestas.get(`${event}|${role}`) ?? porClasificar;
}

function periodoDe(db: MockDb, fecha: string): AccountingPeriod | undefined {
	const [year, month] = fecha.split('-').map(Number);
	return (db.accounting_periods ?? []).find((p: AccountingPeriod) => p.year === year && p.month === month);
}

/**
 * Escribe el asiento, o devuelve `null` si no había qué escribir.
 *
 * Lanza si el periodo está cerrado o si el mes nacería detrás de uno cerrado
 * (RN-61). Quien llama decide qué hacer con eso: el POS lo convierte en código.
 */
export function postEntry(
	companyId: number,
	asiento: AsientoCrudo | null,
	userId: number
): JournalEntry | null {
	if (!asiento || !asiento.lines.length) return null;

	const db = getDb(companyId);
	const config = configuracion(companyId);
	const inicio = String(config.start_date ?? '');
	// RN-60: antes de la fecha de arranque no se escribe nada, y no se lanza: la
	// devolución de una venta vieja tiene que poder registrarse igual.
	if (!inicio || asiento.entry_date < inicio) return null;

	const [year, month] = asiento.entry_date.split('-').map(Number);
	let periodo = periodoDe(db, asiento.entry_date);
	if (!periodo) {
		// Un mes no puede nacer detrás de uno cerrado: una factura vieja
		// capturada tarde cambiaría un balance ya entregado.
		const cerradoDespues = (db.accounting_periods ?? []).some(
			(p: AccountingPeriod) =>
				p.status === 'closed' && (p.year > year || (p.year === year && p.month > month))
		);
		if (cerradoDespues) throw new PeriodoCerrado(year, month);
		periodo = {
			id: nextId('accounting_periods'),
			year,
			month,
			status: 'open',
			closed_at: null,
			closed_by: null
		};
		db.accounting_periods.push(periodo);
	}
	if (periodo.status === 'closed') throw new PeriodoCerrado(year, month);

	const debitos = round2(asiento.lines.reduce((t, l) => t + l.debit, 0));
	const creditos = round2(asiento.lines.reduce((t, l) => t + l.credit, 0));
	if (debitos !== creditos) throw new NoBalancea(debitos, creditos);

	const correlativo =
		Math.max(0, ...db.journal_entries.map((a: JournalEntry) => a.entry_number)) + 1;
	const fila: JournalEntry = {
		id: nextId('journal_entries'),
		entry_number: correlativo,
		entry_date: asiento.entry_date,
		kind: asiento.kind,
		source_type: asiento.source_type ?? null,
		source_id: asiento.source_id ?? null,
		adjusts_entry_id: asiento.adjusts_entry_id ?? null,
		description: asiento.description,
		user_id: userId,
		created_at: new Date().toISOString()
	};
	db.journal_entries.push(fila);
	for (const linea of asiento.lines) {
		db.journal_lines.push({
			id: nextId('journal_lines'),
			entry_id: fila.id,
			account_id: linea.account_id,
			debit: round2(linea.debit),
			credit: round2(linea.credit),
			tax_rate: linea.tax_rate ?? null,
			memo: linea.memo ?? null
		});
	}
	return fila;
}

export class PeriodoCerrado extends Error {
	constructor(
		readonly year: number,
		readonly month: number
	) {
		super(`periodo ${year}-${month} cerrado`);
	}
}

export class NoBalancea extends Error {
	constructor(
		readonly debits: number,
		readonly credits: number
	) {
		super(`el asiento no cuadra: ${debits} contra ${credits}`);
	}
}

// ------------------------------------------------------------- los seis casos

function debito(id: number, monto: number, extra: Partial<LineaCruda> = {}): LineaCruda {
	return { account_id: id, debit: round2(monto), credit: 0, ...extra };
}

function credito(id: number, monto: number, extra: Partial<LineaCruda> = {}): LineaCruda {
	return { account_id: id, debit: 0, credit: round2(monto), ...extra };
}

type LineaVendida = {
	subtotal: number;
	tax: number;
	tax_rate: number;
	quantity: number;
	unit_cost: number | null;
};

function porTarifa(lineas: LineaVendida[]): [number, number, number][] {
	const acumulado = new Map<number, [number, number]>();
	for (const linea of lineas) {
		const [base, impuesto] = acumulado.get(linea.tax_rate) ?? [0, 0];
		acumulado.set(linea.tax_rate, [
			round2(base + linea.subtotal),
			round2(impuesto + linea.tax)
		]);
	}
	return [...acumulado.entries()]
		.sort((a, b) => a[0] - b[0])
		.map(([tarifa, [base, impuesto]]) => [tarifa, base, impuesto]);
}

function costoDe(lineas: LineaVendida[]): number {
	return round2(
		lineas.reduce((t, l) => t + (l.unit_cost == null ? 0 : l.unit_cost * l.quantity), 0)
	);
}

/** La venta: el cobro contra ingresos por tarifa, IVA, y el par costo/inventario. */
export function postSale(
	companyId: number,
	venta: { id: number; date: string; payment_method: string },
	lineas: LineaVendida[],
	userId: number
): JournalEntry | null {
	const db = getDb(companyId);
	const cuenta = mapeoVigente(db);
	const asiento: LineaCruda[] = [];
	const ingresos: LineaCruda[] = [];
	let cobro = 0;

	for (const [tarifa, base, impuesto] of porTarifa(lineas)) {
		const papel = salesRole(tarifa);
		if (base > 0) ingresos.push(credito(cuenta('sale', papel), base, { memo: papel }));
		if (impuesto > 0) {
			ingresos.push(
				credito(cuenta('sale', 'vat_payable'), impuesto, {
					tax_rate: round2(tarifa * 100),
					memo: 'vat_payable'
				})
			);
		}
		cobro = round2(cobro + base + impuesto);
	}

	if (cobro > 0) {
		const papel = METHOD_ROLES[venta.payment_method] ?? 'unclassified';
		asiento.push(debito(cuenta('sale', papel), cobro, { memo: papel }));
	}
	asiento.push(...ingresos);

	const costo = costoDe(lineas);
	if (costo > 0) {
		asiento.push(debito(cuenta('sale', 'cogs'), costo, { memo: 'cogs' }));
		asiento.push(credito(cuenta('sale', 'inventory'), costo, { memo: 'inventory' }));
	}

	return postEntry(
		companyId,
		{
			kind: 'auto',
			entry_date: venta.date,
			description: 'sale',
			lines: asiento,
			source_type: 'sale',
			source_id: venta.id
		},
		userId
	);
}

/** La devolución: la venta al revés, con la tarifa de su venta (RN-12). */
export function postReturn(
	companyId: number,
	devolucion: { id: number; date: string },
	lineas: LineaVendida[],
	userId: number
): JournalEntry | null {
	const db = getDb(companyId);
	const cuenta = mapeoVigente(db);
	const asiento: LineaCruda[] = [];

	const devuelto = round2(lineas.reduce((t, l) => t + l.subtotal, 0));
	if (devuelto > 0) {
		asiento.push(
			debito(cuenta('return', 'sales_returns'), devuelto, { memo: 'sales_returns' })
		);
	}

	let reembolso = 0;
	for (const [tarifa, base, impuesto] of porTarifa(lineas)) {
		if (impuesto > 0) {
			asiento.push(
				debito(cuenta('return', 'vat_payable'), impuesto, {
					tax_rate: round2(tarifa * 100),
					memo: 'vat_payable'
				})
			);
		}
		reembolso = round2(reembolso + base + impuesto);
	}
	if (reembolso > 0) {
		asiento.push(credito(cuenta('return', 'cash'), reembolso, { memo: 'cash' }));
	}

	const costo = costoDe(lineas);
	if (costo > 0) {
		asiento.push(debito(cuenta('return', 'inventory'), costo, { memo: 'inventory' }));
		asiento.push(credito(cuenta('return', 'cogs'), costo, { memo: 'cogs' }));
	}

	return postEntry(
		companyId,
		{
			kind: 'auto',
			entry_date: devolucion.date,
			description: 'return',
			lines: asiento,
			source_type: 'return',
			source_id: devolucion.id
		},
		userId
	);
}

/** El cierre de caja, **solo si no cuadró**. */
export function postCashClose(
	companyId: number,
	turno: { id: number; date: string },
	expected: number,
	counted: number,
	userId: number
): JournalEntry | null {
	const diferencia = round2(counted - expected);
	if (diferencia === 0) return null;

	const cuenta = mapeoVigente(getDb(companyId));
	const lineas =
		diferencia > 0
			? [
					debito(cuenta('cash_close', 'cash'), diferencia, { memo: 'cash' }),
					credito(cuenta('cash_close', 'cash_over'), diferencia, { memo: 'cash_over' })
				]
			: [
					debito(cuenta('cash_close', 'cash_short'), -diferencia, { memo: 'cash_short' }),
					credito(cuenta('cash_close', 'cash'), -diferencia, { memo: 'cash' })
				];

	return postEntry(
		companyId,
		{
			kind: 'auto',
			entry_date: turno.date,
			description: 'cash_close',
			lines: lineas,
			source_type: 'cash_session',
			source_id: turno.id
		},
		userId
	);
}

/** Un movimiento de gaveta, contra «por clasificar». */
export function postCashMovement(
	companyId: number,
	mov: { id: number; date: string; type: string; amount: number; fromSupplierPayment?: boolean },
	userId: number
): JournalEntry | null {
	// El que nació de un abono no deja asiento: lo deja el abono (RN-56).
	if (mov.fromSupplierPayment || mov.amount <= 0) return null;

	const cuenta = mapeoVigente(getDb(companyId));
	const caja = cuenta('cash_movement', 'cash');
	const contra = cuenta('cash_movement', 'counterpart');
	const lineas =
		mov.type === 'entrada'
			? [
					debito(caja, mov.amount, { memo: 'cash' }),
					credito(contra, mov.amount, { memo: 'counterpart' })
				]
			: [
					debito(contra, mov.amount, { memo: 'counterpart' }),
					credito(caja, mov.amount, { memo: 'cash' })
				];

	return postEntry(
		companyId,
		{
			kind: 'auto',
			entry_date: mov.date,
			description: 'cash_movement',
			lines: lineas,
			source_type: 'cash_movement',
			source_id: mov.id
		},
		userId
	);
}

/** La compra: inventario e IVA crédito, **siempre** contra proveedores. */
export function postPurchase(
	companyId: number,
	compra: { id: number; date: string },
	lineas: { subtotal: number; tax: number; tax_rate: number }[],
	userId: number
): JournalEntry | null {
	const cuenta = mapeoVigente(getDb(companyId));
	const asiento: LineaCruda[] = [];

	const inventario = round2(lineas.reduce((t, l) => t + l.subtotal, 0));
	if (inventario > 0) {
		asiento.push(debito(cuenta('purchase', 'inventory'), inventario, { memo: 'inventory' }));
	}

	let deuda = inventario;
	const acumulado = new Map<number, number>();
	for (const linea of lineas) {
		acumulado.set(linea.tax_rate, round2((acumulado.get(linea.tax_rate) ?? 0) + linea.tax));
	}
	for (const [tarifa, impuesto] of [...acumulado.entries()].sort((a, b) => a[0] - b[0])) {
		if (impuesto <= 0) continue;
		asiento.push(
			debito(cuenta('purchase', 'vat_credit'), impuesto, {
				tax_rate: round2(tarifa * 100),
				memo: 'vat_credit'
			})
		);
		deuda = round2(deuda + impuesto);
	}
	if (deuda > 0) {
		asiento.push(credito(cuenta('purchase', 'payables'), deuda, { memo: 'payables' }));
	}

	return postEntry(
		companyId,
		{
			kind: 'auto',
			entry_date: compra.date,
			description: 'purchase',
			lines: asiento,
			source_type: 'stock_entry',
			source_id: compra.id
		},
		userId
	);
}

/** El abono: el pasivo contra de dónde salió la plata. */
export function postSupplierPayment(
	companyId: number,
	abono: { id: number; date: string; amount: number; method: string },
	userId: number
): JournalEntry | null {
	if (abono.amount <= 0) return null;

	const cuenta = mapeoVigente(getDb(companyId));
	const papel = SUPPLIER_PAYMENT_ROLES[abono.method] ?? 'unclassified';
	return postEntry(
		companyId,
		{
			kind: 'auto',
			entry_date: abono.date,
			description: 'supplier_payment',
			lines: [
				debito(cuenta('supplier_payment', 'payables'), abono.amount, { memo: 'payables' }),
				credito(cuenta('supplier_payment', papel), abono.amount, { memo: papel })
			],
			source_type: 'supplier_payment',
			source_id: abono.id
		},
		userId
	);
}

/** Saca de «por clasificar» lo que cayó ahí, con un ajuste (RF-49). */
export function postReclassification(
	companyId: number,
	entryId: number,
	toAccount: number,
	hoy: string,
	userId: number,
	description = ''
): JournalEntry | null {
	const db = getDb(companyId);
	const porClasificar = cuentas(db).find((c) => c.code === UNCLASSIFIED_CODE)?.id ?? 0;
	const movimientos: LineaCruda[] = [];

	for (const linea of db.journal_lines.filter((l: MockJournalLine) => l.entry_id === entryId)) {
		if (linea.account_id !== porClasificar) continue;
		if (linea.debit > 0) {
			movimientos.push(debito(toAccount, linea.debit, { memo: linea.memo }));
			movimientos.push(credito(porClasificar, linea.debit, { memo: linea.memo }));
		} else {
			movimientos.push(debito(porClasificar, linea.credit, { memo: linea.memo }));
			movimientos.push(credito(toAccount, linea.credit, { memo: linea.memo }));
		}
	}
	if (!movimientos.length) return null;

	return postEntry(
		companyId,
		{
			kind: 'adjustment',
			entry_date: hoy,
			description: description || 'reclassify',
			lines: movimientos,
			adjusts_entry_id: entryId
		},
		userId
	);
}

// ------------------------------------------------------------- los reportes

const DEBIT_KINDS = new Set<AccountKind>(['asset', 'cost', 'expense']);

export interface FilaDeSaldo {
	account_id: number;
	code: string;
	name: string;
	kind: AccountKind;
	debits: number;
	credits: number;
	balance: number;
}

/** Suma las líneas del tramo por cuenta, ordenadas por código. */
export function trialBalance(
	companyId: number,
	hasta: string,
	desde?: string
): FilaDeSaldo[] {
	const db = getDb(companyId);
	const porId = new Map(cuentas(db).map((c) => [c.id, c]));
	const enRango = new Set(
		db.journal_entries
			.filter((a: JournalEntry) => a.entry_date <= hasta && (!desde || a.entry_date >= desde))
			.map((a: JournalEntry) => a.id)
	);

	const acumulado = new Map<number, [number, number]>();
	for (const linea of db.journal_lines) {
		if (!enRango.has(linea.entry_id)) continue;
		const [d, c] = acumulado.get(linea.account_id) ?? [0, 0];
		acumulado.set(linea.account_id, [round2(d + linea.debit), round2(c + linea.credit)]);
	}

	return [...acumulado.entries()]
		.map(([id, [debits, credits]]) => {
			const cuenta = porId.get(id)!;
			return {
				account_id: id,
				code: cuenta.code,
				name: cuenta.name,
				kind: cuenta.kind,
				debits,
				credits,
				balance: DEBIT_KINDS.has(cuenta.kind)
					? round2(debits - credits)
					: round2(credits - debits)
			};
		})
		.sort((a, b) => a.code.localeCompare(b.code));
}

export function totalDe(filas: FilaDeSaldo[], ...kinds: AccountKind[]): number {
	return round2(
		filas.filter((f) => kinds.includes(f.kind)).reduce((t, f) => t + f.balance, 0)
	);
}

/** El mapeo tal como lo pinta la pantalla: con lo que falta a la vista. */
export function mapeoParaPantalla(companyId: number): MappingRow[] {
	const db = getDb(companyId);
	const porId = new Map(cuentas(db).map((c) => [c.id, c]));
	const puestas = new Map(
		(db.account_mappings ?? []).map((m: MockAccountMapping) => [`${m.event}|${m.role}`, m.account_id] as [string, number])
	);

	const papeles: [string, string, boolean][] = Object.keys(defaultMapping())
		.map((clave) => {
			const [evento, papel] = clave.split('|');
			return [evento, papel, false] as [string, string, boolean];
		})
		.concat(UNMAPPED_ON_PURPOSE.map(([e, p]) => [e, p, true] as [string, string, boolean]));

	return papeles
		.sort((a, b) => `${a[0]}|${a[1]}`.localeCompare(`${b[0]}|${b[1]}`))
		.map(([evento, papel, aProposito]) => {
			const cuenta = porId.get(puestas.get(`${evento}|${papel}`) ?? -1);
			return {
				event: evento,
				role: papel,
				account_id: cuenta?.id ?? null,
				account_code: cuenta?.code ?? null,
				account_name: cuenta?.name ?? null,
				unmapped_on_purpose: aProposito
			};
		});
}
