/**
 * Planilla en el modo simulado (F12, T-1214): las rutas de `/payroll/*` con el
 * mismo contrato que `payroll_routes.py`.
 *
 * Lo que decide el backend lo decide igual acá —los códigos de los «no», los
 * estados de la corrida, qué acción pide qué— y la aritmética sale de
 * `payrollCalc.ts`, una versión compacta del dominio: alcanza para que las
 * pantallas y las pruebas de punta a punta tengan cifras con la misma forma.
 * Lo que se prueba al céntimo es el dominio del backend.
 */

import { round2 } from '$lib/domain/money';
import type {
	EmploymentContract,
	InsPolicy,
	PayrollItem,
	Position,
	VacationMovement,
	WorkSchedule
} from '$lib/domain/payroll';
import { ApiError } from '../api';
import {
	getEmpresa,
	getRoot,
	nextId,
	persist,
	type MockAction,
	type MockEmployee,
	type MockLine,
	type MockPayrollData,
	type MockRun,
	type MockUser,
	planillaVacia
} from './db';
import { activa as contabilidadActiva, postPayroll } from './ledger';
import {
	CONTRIBUTIVOS,
	GRAVABLES,
	type Jornada,
	type Periodo,
	baseDe,
	cierraMes,
	corteDesde,
	creditosVigentes,
	diasCalendario,
	diasContados,
	diasPagados,
	encabezadoIns,
	mesDe,
	nombreArchivoIns,
	periodoDe,
	regla,
	registroIns,
	retencion,
	rubro,
	sumarDias,
	tasasVigentes,
	tramosVigentes,
	ultimoDiaDelMes,
	valorDia,
	valorHora
} from './payrollCalc';
import { PAYROLL_SEED } from './payrollRates';

type Handler = (ctx: {
	params: string[];
	query: URLSearchParams;
	body: any;
	userId: number | null;
	companyId: number;
}) => unknown;

export interface PayrollMockContext {
	route: (method: string, pattern: string, handler: Handler) => void;
	exigirAdmin: (userId: number | null, companyId: number) => MockUser;
	exigirModulo: (companyId: number, module: string) => void;
	registrar: (userId: number, companyId: number | null, accion: string, detalle: string | null) => void;
	nowIso: () => string;
	tasas: () => { concept: string; payer: string; value: number; valid_from: string; valid_to?: string | null }[];
}

function fail(status: number, code: string, data: Record<string, unknown> = {}): never {
	throw new ApiError(status, code, data);
}

const APROBADA_O_PAGADA = new Set(['approved', 'paid']);
const CON_SALARIO = new Set(['regular', 'adjustment']);
const RANGO = new Set(['sick_leave_ccss', 'sick_leave_ins', 'maternity', 'paid_leave', 'unpaid_leave', 'absence', 'vacation']);
const DEDUCCIONES = ['child_support', 'garnishment', 'deduction'];
const DEL_CONTRATO = new Set(['raise', 'position_change', 'termination']);
const TIPOS = [
	'overtime', 'double_time', 'bonus', 'sick_leave_ccss', 'sick_leave_ins', 'maternity', 'paid_leave',
	'unpaid_leave', 'absence', 'vacation', 'deduction', 'child_support', 'garnishment', 'raise',
	'position_change', 'termination'
];
const CAUSAS = ['resignation', 'dismissal_with_cause', 'dismissal_without_cause', 'mutual', 'end_of_contract'];
const IDENTIFICACIONES = ['national', 'dimex', 'nite', 'passport', 'work_permit'];
const NUMERICAS = new Set(['national', 'dimex', 'nite']);
const GENEROS = ['F', 'M'];
const ESTADOS_CIVILES = ['single', 'married', 'divorced', 'widowed', 'separated', 'free_union', 'unknown'];
const PERIODICIDADES = ['monthly', 'semimonthly', 'biweekly', 'weekly'];
const CLASES: Record<string, number> = { day: 8, mixed: 7, night: 6 };

/** La porción de planilla de la compañía; un archivo viejo nace sin ella. */
function planilla(companyId: number): MockPayrollData {
	const empresa = getEmpresa(companyId);
	if (!empresa.payroll) empresa.payroll = planillaVacia();
	return empresa.payroll;
}

const num = (v: unknown): number | null => (v == null || v === '' ? null : Number(v));
const txt = (v: unknown): string | null => (v == null ? null : String(v).trim() || null);

// ------------------------------------------------------------------ salidas

function contratoOut(c: EmploymentContract) {
	return { ...c };
}

function empleadoOut(p: MockPayrollData, e: MockEmployee) {
	const contratos = p.contracts.filter((c) => c.employee_id === e.id).sort((a, b) => (a.valid_from < b.valid_from ? -1 : 1));
	return { ...e, contract: contratos.length ? contratoOut(contratos[contratos.length - 1]) : null };
}

function nombre(e: MockEmployee | undefined): string {
	return e ? [e.first_name, e.last_name_1, e.last_name_2].filter(Boolean).join(' ') : '';
}

function aplicados(p: MockPayrollData, actionId: number) {
	const salida: {
		run_id: number;
		run_status: string;
		period_from: string;
		period_to: string;
		concept: string;
		payer: string;
		amount: number;
		quantity: number | null;
		applied_from: string | null;
		applied_to: string | null;
	}[] = [];
	for (const linea of p.lines) {
		const corrida = p.runs.find((r) => r.id === linea.run_id);
		if (!corrida || !APROBADA_O_PAGADA.has(corrida.status)) continue;
		for (const i of linea.items) {
			if (i.action_id === actionId) {
				salida.push({
					run_id: corrida.id,
					run_status: corrida.status,
					period_from: corrida.period_from,
					period_to: corrida.period_to,
					concept: i.concept,
					payer: i.payer,
					amount: i.amount,
					quantity: i.quantity,
					applied_from: i.applied_from,
					applied_to: i.applied_to
				});
			}
		}
	}
	return salida.sort((a, b) => (a.period_to < b.period_to ? -1 : 1));
}

function accionOut(p: MockPayrollData, a: MockAction) {
	const aplicado = aplicados(p, a.id);
	const total = round2(aplicado.reduce((t, i) => t + i.amount, 0));
	return {
		...a,
		cancelled_by: p.actions.find((o) => o.cancels_action_id === a.id)?.id ?? null,
		applied: aplicado,
		applied_total: total,
		balance: a.total_amount == null ? null : round2(a.total_amount - total)
	};
}

function lineaOut(p: MockPayrollData, l: MockLine) {
	return {
		id: l.id,
		employee_id: l.employee_id,
		employee_name: nombre(p.employees.find((e) => e.id === l.employee_id)),
		contract_id: l.contract_id,
		gross: l.gross,
		employee_deductions: l.employee_deductions,
		income_tax: l.income_tax,
		other_deductions: l.other_deductions,
		net: l.net,
		employer_charges: l.employer_charges,
		items: l.items
	};
}

function corridaOut(p: MockPayrollData, r: MockRun, conLineas: boolean) {
	const lineas = p.lines.filter((l) => l.run_id === r.id).sort((a, b) => a.employee_id - b.employee_id);
	const salida: Record<string, unknown> = {
		id: r.id,
		kind: r.kind,
		schedule_id: r.schedule_id,
		schedule_name: p.schedules.find((s) => s.id === r.schedule_id)?.name ?? null,
		period_from: r.period_from,
		period_to: r.period_to,
		pay_date: r.pay_date,
		status: r.status,
		adjusts_run_id: r.adjusts_run_id,
		journal_entry_id: r.journal_entry_id,
		employees: lineas.length,
		gross: round2(lineas.reduce((t, l) => t + l.gross, 0)),
		net: round2(lineas.reduce((t, l) => t + l.net, 0)),
		employer_charges: round2(lineas.reduce((t, l) => t + l.employer_charges, 0)),
		created_at: r.created_at,
		approved_at: r.approved_at,
		paid_at: r.paid_at
	};
	if (conLineas) salida.lines = lineas.map((l) => lineaOut(p, l));
	return salida;
}

// ------------------------------------------------------------- validaciones

function revisarJornada(j: Omit<WorkSchedule, 'id'>) {
	if (!PERIODICIDADES.includes(j.frequency)) fail(400, 'invalid_schedule', { field: 'frequency', reason: 'unknown' });
	if (!(j.shift in CLASES)) fail(400, 'invalid_schedule', { field: 'shift', reason: 'unknown' });
	if (!(j.hours_per_day > 0 && j.hours_per_day <= 12)) fail(400, 'invalid_schedule', { field: 'hours_per_day', reason: 'out_of_range' });
	if (!(j.workdays_per_week >= 1 && j.workdays_per_week <= 6)) fail(400, 'invalid_schedule', { field: 'workdays_per_week', reason: 'out_of_range' });
	const pide: Record<string, string | null> = { monthly: null, semimonthly: 'first_cut_day', biweekly: 'series_start', weekly: 'cut_weekday' };
	for (const campo of ['first_cut_day', 'cut_weekday', 'series_start'] as const) {
		const valor = j[campo];
		if (campo === pide[j.frequency] && valor == null) fail(400, 'invalid_schedule', { field: campo, reason: 'required' });
		if (campo !== pide[j.frequency] && valor != null) fail(400, 'invalid_schedule', { field: campo, reason: 'unexpected' });
	}
	if (j.first_cut_day != null && (j.first_cut_day < 8 || j.first_cut_day > 15)) fail(400, 'invalid_schedule', { field: 'first_cut_day', reason: 'out_of_range' });
	if (j.cut_weekday != null && (j.cut_weekday < 0 || j.cut_weekday > 6)) fail(400, 'invalid_schedule', { field: 'cut_weekday', reason: 'out_of_range' });
}

function revisarEmpleado(e: Omit<MockEmployee, 'id' | 'is_active' | 'terminated_on' | 'termination_cause'>) {
	if (!IDENTIFICACIONES.includes(e.identification_type)) fail(400, 'invalid_employee', { field: 'identification_type', reason: 'unknown' });
	if (!e.identification) fail(400, 'invalid_employee', { field: 'identification', reason: 'required' });
	if (NUMERICAS.has(e.identification_type) && !/^\d+$/.test(e.identification)) fail(400, 'invalid_employee', { field: 'identification', reason: 'not_digits' });
	if (!e.first_name) fail(400, 'invalid_employee', { field: 'first_name', reason: 'required' });
	if (!e.last_name_1) fail(400, 'invalid_employee', { field: 'last_name_1', reason: 'required' });
	if (e.birth_date > e.hired_on) fail(400, 'invalid_employee', { field: 'birth_date', reason: 'in_the_future' });
	if (diasCalendario(e.birth_date, e.hired_on) < 15 * 365) fail(400, 'invalid_employee', { field: 'birth_date', reason: 'too_young' });
	if (!GENEROS.includes(e.gender)) fail(400, 'invalid_employee', { field: 'gender', reason: 'unknown' });
	if (!ESTADOS_CIVILES.includes(e.marital_status)) fail(400, 'invalid_employee', { field: 'marital_status', reason: 'unknown' });
	if (!/^[A-Z]{2}$/.test(e.nationality)) fail(400, 'invalid_employee', { field: 'nationality', reason: 'bad_format' });
	if (e.email && !e.email.includes('@')) fail(400, 'invalid_employee', { field: 'email', reason: 'bad_format' });
	if (e.iban && !/^[A-Z]{2}\d{2}[0-9A-Z]{11,30}$/.test(e.iban.replace(/ /g, '').toUpperCase())) fail(400, 'invalid_employee', { field: 'iban', reason: 'bad_format' });
	if (e.dependent_children < 0) fail(400, 'invalid_employee', { field: 'dependent_children', reason: 'negative' });
}

function revisarAccion(a: { kind: string; starts_on: string; ends_on: string | null; hours: number | null; days: number | null; amount: number | null; total_amount: number | null; new_salary: number | null; position_id: number | null; is_recurring: boolean }) {
	if (!TIPOS.includes(a.kind)) fail(400, 'invalid_action', { field: 'kind', reason: 'unknown' });
	const pide: Record<string, string[]> = {
		overtime: ['hours'], double_time: ['hours'], bonus: ['amount'], vacation: ['ends_on', 'days'],
		deduction: ['amount'], child_support: ['amount'], garnishment: ['total_amount'], raise: ['new_salary'],
		position_change: ['position_id']
	};
	const campos = [...(RANGO.has(a.kind) ? ['ends_on'] : []), ...(pide[a.kind] ?? [])];
	for (const campo of campos) {
		if ((a as Record<string, unknown>)[campo] == null) fail(400, 'invalid_action', { field: campo, reason: 'required' });
	}
	for (const campo of ['hours', 'days', 'amount', 'total_amount', 'new_salary'] as const) {
		const v = a[campo];
		if (v != null && v <= 0) fail(400, 'invalid_action', { field: campo, reason: 'not_positive' });
	}
	if (!RANGO.has(a.kind) && a.ends_on != null && a.ends_on !== a.starts_on) fail(400, 'invalid_action', { field: 'ends_on', reason: 'single_day' });
	if (a.ends_on != null && a.ends_on < a.starts_on) fail(400, 'invalid_action', { field: 'ends_on', reason: 'before_start' });
	if (a.kind === 'vacation' && a.days != null && a.ends_on && a.days > diasCalendario(a.starts_on, a.ends_on)) fail(400, 'invalid_action', { field: 'days', reason: 'too_many' });
	if (a.is_recurring && !['deduction', 'child_support'].includes(a.kind)) fail(400, 'invalid_action', { field: 'is_recurring', reason: 'not_allowed' });
}

function jornadaDe(s: WorkSchedule): Jornada {
	return s;
}

function contratoVigente(p: MockPayrollData, employeeId: number, dia: string): EmploymentContract | undefined {
	return p.contracts.find((c) => c.employee_id === employeeId && c.valid_from <= dia && (c.valid_to == null || dia <= c.valid_to));
}

function saldoVacaciones(p: MockPayrollData, employeeId: number): number {
	const signo: Record<string, number> = { opening: 1, accrual: 1, taken: -1, paid: -1 };
	return round2(p.vacations.filter((m) => m.employee_id === employeeId).reduce((t, m) => t + (signo[m.kind] ?? 0) * m.days, 0));
}

// ------------------------------------------------------------------ cálculo

function tasasAl(ctx: PayrollMockContext, dia: string) {
	return tasasVigentes(ctx.tasas(), dia);
}

function faltantes(tasas: Map<string, { concept: string; payer: string }>): string[] {
	return PAYROLL_SEED.required.filter((r) => {
		const [concepto, pagador] = r.split(':');
		return !tasas.has(`${pagador}:${concepto}`);
	});
}

/** `(base gravable, renta retenida)` del mes en las aprobadas o pagadas, sin una. */
function retencionDelMes(p: MockPayrollData, employeeId: number, mes: string, sinCorrida: number): [number, number] {
	let base = 0;
	let retenido = 0;
	for (const linea of p.lines) {
		const corrida = p.runs.find((r) => r.id === linea.run_id);
		if (!corrida || corrida.id === sinCorrida || !CON_SALARIO.has(corrida.kind) || !APROBADA_O_PAGADA.has(corrida.status)) continue;
		if (corrida.period_to.slice(0, 7) !== mes || linea.employee_id !== employeeId) continue;
		base += baseDe(linea.items, GRAVABLES);
		retenido += linea.income_tax;
	}
	return [round2(base), round2(retenido)];
}

function totales(employeeId: number, contractId: number, items: PayrollItem[], ccss: Set<string>): Omit<MockLine, 'id' | 'run_id'> {
	const suma = (f: (i: PayrollItem) => boolean) => round2(items.filter(f).reduce((t, i) => t + i.amount, 0));
	const gross = suma((i) => i.payer === 'earning');
	const cargas = suma((i) => i.payer === 'employee' && ccss.has(i.concept));
	const renta = suma((i) => i.payer === 'employee' && i.concept === 'income_tax');
	const otras = suma((i) => i.payer === 'employee' && !ccss.has(i.concept) && i.concept !== 'income_tax');
	return {
		employee_id: employeeId,
		contract_id: contractId,
		gross,
		employee_deductions: cargas,
		income_tax: renta,
		other_deductions: otras,
		net: round2(gross - cargas - renta - otras),
		employer_charges: suma((i) => i.payer === 'employer'),
		items
	};
}

/** Las líneas de una corrida regular (o el recálculo de un ajuste). */
function lineasRegulares(ctx: PayrollMockContext, companyId: number, corrida: MockRun, sinCorrida: number): Omit<MockLine, 'id' | 'run_id'>[] {
	const p = planilla(companyId);
	const jornada = p.schedules.find((s) => s.id === corrida.schedule_id)!;
	const periodo: Periodo = { desde: corrida.period_from, hasta: corrida.period_to };
	const tasas = tasasAl(ctx, corrida.period_to);
	const faltan = faltantes(tasas);
	if (faltan.length) fail(409, 'rates_missing_for_date', { missing: faltan, on: corrida.period_to });
	const tramos = tramosVigentes(corrida.period_to);
	const creditos = creditosVigentes(corrida.period_to);
	const cierra = cierraMes(jornadaDe(jornada), corrida.period_to);
	const obreras = [...tasas.values()].filter((t) => t.payer === 'employee').sort((a, b) => (a.concept < b.concept ? -1 : 1));
	const patronales = [...tasas.values()].filter((t) => t.payer === 'employer' && !(p.settings.ina_exempt && t.concept === 'ina')).sort((a, b) => (a.concept < b.concept ? -1 : 1));
	const ccss = new Set(obreras.map((t) => t.concept));
	const porOmision = p.policies.find((pol) => pol.is_default);

	const contratos = p.contracts.filter((c) => c.schedule_id === jornada.id && c.valid_from <= periodo.hasta && (c.valid_to == null || c.valid_to >= periodo.desde));
	const porEmpleado = new Map<number, EmploymentContract[]>();
	for (const c of contratos) porEmpleado.set(c.employee_id, [...(porEmpleado.get(c.employee_id) ?? []), c]);

	const lineas: Omit<MockLine, 'id' | 'run_id'>[] = [];
	for (const employeeId of [...porEmpleado.keys()].sort((a, b) => a - b)) {
		const empleado = p.employees.find((e) => e.id === employeeId)!;
		const suyos = porEmpleado.get(employeeId)!.sort((a, b) => (a.valid_from < b.valid_from ? -1 : 1));
		const items: PayrollItem[] = [];
		for (const c of suyos) {
			const desde = [periodo.desde, c.valid_from, empleado.hired_on].sort().at(-1)!;
			const hasta = [periodo.hasta, c.valid_to ?? periodo.hasta, empleado.terminated_on ?? periodo.hasta].sort()[0];
			if (desde > hasta) continue;
			if (desde === periodo.desde && hasta === periodo.hasta) {
				items.push(rubro('base', 'earning', c.period_salary, null, c.period_salary, { quantity: diasPagados(jornada), applied_from: desde, applied_to: hasta }));
			} else {
				const dias = diasContados(jornada, desde, hasta);
				const dia = valorDia(c.period_salary, jornada);
				items.push(rubro('base', 'earning', dia, null, dias * dia, { quantity: dias, applied_from: desde, applied_to: hasta }));
			}
		}
		if (!items.length) continue;
		const actual = suyos[suyos.length - 1];
		const salario = actual.period_salary;
		const dia = valorDia(salario, jornada);
		const hora = valorHora(salario, jornada);
		const acciones = p.actions.filter((a) => a.employee_id === employeeId).sort((a, b) => (a.starts_on < b.starts_on ? -1 : a.starts_on > b.starts_on ? 1 : a.id - b.id));
		const anuladas = new Set(acciones.filter((a) => a.cancels_action_id != null).map((a) => a.cancels_action_id as number));

		// Los devengos y ausencias de las acciones que ninguna corrida aplicó.
		for (const a of acciones) {
			if (a.cancels_action_id != null) {
				// La anulación: lo que la original aplicó, al revés; o un rubro de cero.
				if (aplicados(p, a.id).length) continue;
				const originales = aplicados(p, a.cancels_action_id);
				if (!originales.length) {
					items.push(rubro(a.kind, 'earning', 0, null, 0, { action_id: a.id, applied_from: a.starts_on, applied_to: a.starts_on }));
				} else {
					for (const o of originales) {
						items.push(rubro(o.concept, o.payer, 0, null, -o.amount, { action_id: a.id, quantity: o.quantity, applied_from: o.applied_from, applied_to: o.applied_to }));
					}
				}
				continue;
			}
			if (anuladas.has(a.id) || DEL_CONTRATO.has(a.kind) || DEDUCCIONES.includes(a.kind)) continue;
			const previos = aplicados(p, a.id);
			const fechas = previos.map((i) => i.applied_to).filter((f): f is string => !!f).sort();
			const primero = fechas.length ? sumarDias(fechas[fechas.length - 1], 1) : a.starts_on;
			if (!RANGO.has(a.kind)) {
				if (!(primero <= a.starts_on && a.starts_on <= periodo.hasta)) continue;
				const fechasAccion = { action_id: a.id, applied_from: a.starts_on, applied_to: a.starts_on };
				if (a.kind === 'overtime' || a.kind === 'double_time') {
					const factor = a.kind === 'overtime' ? 1.5 : 2;
					items.push(rubro(a.kind, 'earning', hora, factor, (a.hours ?? 0) * hora * factor, { ...fechasAccion, quantity: a.hours }));
				} else if (a.kind === 'bonus') {
					items.push(rubro('bonus', 'earning', a.amount ?? 0, null, a.amount ?? 0, { ...fechasAccion, quantity: 1 }));
				}
				continue;
			}
			const desde = [a.starts_on, primero].sort().at(-1)!;
			const hasta = [a.ends_on ?? periodo.hasta, periodo.hasta].sort()[0];
			if (desde > hasta) continue;
			// Un tramo por cada periodo de la jornada que cruza, con sus fechas.
			let inicio = desde;
			while (inicio <= hasta) {
				const suyo = periodoDe(jornada, corteDesde(jornada, inicio))!;
				const fin = [hasta, suyo.hasta].sort()[0];
				const dias = diasContados(jornada, inicio, fin);
				const desfase = diasCalendario(a.starts_on, inicio) - 1;
				const fechas2 = { action_id: a.id, quantity: dias, applied_from: inicio, applied_to: fin };
				if (a.kind === 'paid_leave' || a.kind === 'vacation') {
					items.push(rubro(a.kind, 'earning', dia, null, 0, fechas2));
				} else {
					items.push(rubro(a.kind, 'earning', dia, null, -dias * dia, fechas2));
					if (a.kind === 'sick_leave_ccss' || a.kind === 'sick_leave_ins') {
						const prefijo = a.kind === 'sick_leave_ccss' ? 'sick_leave' : 'ins';
						const concepto = a.kind === 'sick_leave_ccss' ? 'sick_leave_subsidy' : 'ins_subsidy';
						const pagaDias = regla(tasas, `${prefijo}_employer_days`);
						const tasa = regla(tasas, `${prefijo}_employer_rate`);
						const pagados = Math.max(0, Math.min(pagaDias - desfase, dias));
						if (pagados > 0) items.push(rubro(concepto, 'earning', dia, tasa, pagados * dia * tasa, { ...fechas2, quantity: pagados }));
					} else if (a.kind === 'maternity') {
						const tasa = regla(tasas, 'maternity_employer_rate');
						items.push(rubro('maternity_pay', 'earning', dia, tasa, dias * dia * tasa, fechas2));
					}
				}
				inicio = sumarDias(fin, 1);
			}
		}

		const cotiza = baseDe(items, CONTRIBUTIVOS);
		for (const t of obreras) items.push(rubro(t.concept, 'employee', cotiza, t.value, cotiza * t.value));
		if (actual.solidarista_rate) items.push(rubro('solidarista', 'employee', cotiza, actual.solidarista_rate, cotiza * actual.solidarista_rate));
		const gravable = baseDe(items, GRAVABLES);
		const [baseAntes, retenidoAntes] = retencionDelMes(p, employeeId, periodo.hasta.slice(0, 7), sinCorrida);
		const credito = creditos.child * empleado.dependent_children + (empleado.spouse_credit ? creditos.spouse : 0);
		items.push(rubro('income_tax', 'employee', gravable, null, retencion(gravable, jornada.frequency, cierra, baseAntes, retenidoAntes, tramos, credito)));

		// Las deducciones, en el orden de RN-93 y sin dejar el neto negativo.
		let neto = round2(items.filter((i) => i.payer === 'earning').reduce((t, i) => t + i.amount, 0) - items.filter((i) => i.payer === 'employee').reduce((t, i) => t + i.amount, 0));
		let disponible = Math.max(0, neto);
		const candidatas = acciones
			.filter((a) => DEDUCCIONES.includes(a.kind) && a.cancels_action_id == null && !anuladas.has(a.id))
			.sort((a, b) => DEDUCCIONES.indexOf(a.kind) - DEDUCCIONES.indexOf(b.kind) || (a.starts_on < b.starts_on ? -1 : 1) || a.id - b.id);
		const inembargable = regla(tasas, 'minimum_wage_unseizable');
		let cupoEmbargo: number | null = null;
		let cupoPension = disponible * 0.5;
		for (const a of candidatas) {
			const vigente = a.starts_on <= periodo.hasta && (a.ends_on == null || a.ends_on >= periodo.desde) && (a.suspended_at == null || a.suspended_at.slice(0, 10) > periodo.hasta);
			const previos = aplicados(p, a.id);
			const suma = round2(previos.reduce((t, i) => t + i.amount, 0));
			let pide = 0;
			if (a.kind === 'garnishment') {
				if (cupoEmbargo == null) {
					const mensual = neto * (jornada.frequency === 'monthly' ? 1 : jornada.frequency === 'semimonthly' ? 2 : jornada.frequency === 'biweekly' ? 26 / 12 : 52 / 12);
					const embargable = mensual <= inembargable ? 0 : mensual <= 3 * inembargable ? (mensual - inembargable) / 8 : (2 * inembargable) / 8 + (mensual - 3 * inembargable) / 4;
					cupoEmbargo = round2(embargable / (jornada.frequency === 'monthly' ? 1 : jornada.frequency === 'semimonthly' ? 2 : jornada.frequency === 'biweekly' ? 26 / 12 : 52 / 12));
				}
				if (vigente) pide = Math.min(Math.max(0, (a.total_amount ?? 0) - suma), cupoEmbargo, a.amount ?? Infinity);
				cupoEmbargo = round2(cupoEmbargo - pide);
			} else {
				if (vigente && (a.is_recurring || !previos.length)) {
					pide = a.total_amount == null ? (a.amount ?? 0) : Math.min(a.amount ?? 0, Math.max(0, a.total_amount - suma));
				}
				if (a.kind === 'child_support') {
					pide = Math.min(pide, cupoPension);
					cupoPension = round2(cupoPension - pide);
				}
			}
			const cabe = round2(Math.min(pide, disponible));
			disponible = round2(disponible - cabe);
			if (cabe > 0) items.push(rubro(a.kind, 'employee', pide, null, cabe, { action_id: a.id, applied_from: periodo.desde, applied_to: periodo.hasta }));
		}

		const poliza = actual.ins_policy_id != null ? p.policies.find((pol) => pol.id === actual.ins_policy_id) : porOmision;
		for (const t of patronales) items.push(rubro(t.concept, 'employer', cotiza, t.value, cotiza * t.value));
		items.push(rubro('rt', 'employer', cotiza, poliza?.rt_rate ?? 0, cotiza * (poliza?.rt_rate ?? 0)));
		lineas.push(totales(employeeId, actual.id, items, ccss));
	}
	return lineas;
}

/** Lo devengado pagado (regulares y ajustes) de un empleado, por corte, en un periodo. */
function devengado(p: MockPayrollData, employeeId: number, desde: string, hasta: string): { dia: string; monto: number }[] {
	const salida: { dia: string; monto: number }[] = [];
	for (const linea of p.lines) {
		const corrida = p.runs.find((r) => r.id === linea.run_id);
		if (!corrida || corrida.status !== 'paid' || !CON_SALARIO.has(corrida.kind) || linea.employee_id !== employeeId) continue;
		if (corrida.period_to < desde || corrida.period_to > hasta) continue;
		salida.push({ dia: corrida.period_to, monto: baseDe(linea.items, GRAVABLES) });
	}
	for (const o of p.opening) {
		if (o.employee_id === employeeId && o.period_month >= desde && o.period_month <= hasta) salida.push({ dia: o.period_month, monto: o.gross });
	}
	return salida.sort((a, b) => (a.dia < b.dia ? -1 : 1));
}

function lineasAguinaldo(companyId: number, corrida: MockRun): Omit<MockLine, 'id' | 'run_id'>[] {
	const p = planilla(companyId);
	const empleados = new Set(p.contracts.filter((c) => c.valid_from <= corrida.period_to && (c.valid_to == null || c.valid_to >= corrida.period_from)).map((c) => c.employee_id));
	const lineas: Omit<MockLine, 'id' | 'run_id'>[] = [];
	for (const employeeId of [...empleados].sort((a, b) => a - b)) {
		const e = p.employees.find((x) => x.id === employeeId)!;
		if (e.terminated_on && e.terminated_on <= corrida.period_to) continue;
		const ganado = devengado(p, employeeId, corrida.period_from, corrida.period_to);
		const total = round2(ganado.reduce((t, g) => t + g.monto, 0));
		const monto = round2(total / 12);
		if (monto <= 0) continue;
		const contrato = p.contracts.filter((c) => c.employee_id === employeeId).sort((a, b) => (a.valid_from < b.valid_from ? -1 : 1)).at(-1)!;
		lineas.push(totales(employeeId, contrato.id, [rubro('aguinaldo', 'earning', total, null, monto)], new Set()));
	}
	return lineas;
}

function mesesEntre(desde: string, hasta: string): number {
	const tope = fecha(sumarDias(hasta, 1));
	const inicio = fecha(desde);
	let meses = (tope.getUTCFullYear() - inicio.getUTCFullYear()) * 12 + (tope.getUTCMonth() - inicio.getUTCMonth());
	if (tope.getUTCDate() < inicio.getUTCDate()) meses -= 1;
	return Math.max(0, meses);
}

function fecha(iso: string): Date {
	const [y, m, d] = iso.split('-').map(Number);
	return new Date(Date.UTC(y, m - 1, d));
}

function diasDeCesantia(meses: number): number {
	if (meses < 3) return 0;
	if (meses < 12) return meses <= 6 ? 7 : 14;
	const anios = Math.floor(meses / 12) + (meses % 12 > 6 ? 1 : 0);
	const fila = PAYROLL_SEED.severance.find((s) => s.years_from <= anios && (s.years_to == null || anios < s.years_to));
	return round2((fila?.days ?? 0) * Math.min(anios, 8));
}

function lineasLiquidacion(companyId: number, corrida: MockRun): Omit<MockLine, 'id' | 'run_id'>[] {
	const p = planilla(companyId);
	const existente = p.lines.find((l) => l.run_id === corrida.id);
	if (!existente) fail(409, 'settlement_requires_termination', { run_id: corrida.id, employee_id: null });
	const e = p.employees.find((x) => x.id === existente.employee_id);
	if (!e || !e.terminated_on || !e.termination_cause) fail(409, 'settlement_requires_termination', { run_id: corrida.id, employee_id: existente.employee_id });
	const salida = e.terminated_on;
	const contrato = p.contracts.filter((c) => c.employee_id === e.id).sort((a, b) => (a.valid_from < b.valid_from ? -1 : 1)).at(-1)!;
	const jornada = p.schedules.find((s) => s.id === contrato.schedule_id)!;

	// El promedio de los seis meses anteriores al de la salida, o el salario mensual.
	const mesSalida = mesDe(salida);
	const inicioVentana = iso6(mesSalida, -6);
	const porMes = new Map<string, number>();
	for (const g of devengado(p, e.id, inicioVentana, sumarDias(mesSalida, -1))) porMes.set(mesDe(g.dia), round2((porMes.get(mesDe(g.dia)) ?? 0) + g.monto));
	const meses = [...porMes.keys()].sort().slice(-6).map((m) => porMes.get(m)!);
	const promedio = meses.length ? round2(meses.reduce((t, m) => t + m, 0) / meses.length) : round2(contrato.period_salary * (jornada.frequency === 'monthly' ? 1 : jornada.frequency === 'semimonthly' ? 2 : jornada.frequency === 'biweekly' ? 26 / 12 : 52 / 12));
	const diario = promedio / 30;

	const movimientos = p.vacations.filter((m) => m.employee_id === e.id);
	let ganados = movimientos.filter((m) => m.kind === 'opening' || m.kind === 'accrual').reduce((t, m) => t + m.days, 0);
	const usados = movimientos.filter((m) => m.kind === 'taken' || m.kind === 'paid').reduce((t, m) => t + m.days, 0);
	const antiguedad = mesesEntre(e.hired_on, salida);
	if (diasCalendario(e.hired_on, salida) < 350) ganados = Math.max(ganados, antiguedad);
	const dias = round2(Math.max(0, ganados - usados));

	const anioAguinaldo = Number(salida.slice(5, 7)) === 12 ? Number(salida.slice(0, 4)) + 1 : Number(salida.slice(0, 4));
	const ganadoDesdeDiciembre = round2(devengado(p, e.id, `${anioAguinaldo - 1}-12-01`, salida).reduce((t, g) => t + g.monto, 0));

	const items: PayrollItem[] = [];
	if (e.termination_cause === 'dismissal_without_cause') {
		const preaviso = antiguedad < 3 ? 0 : antiguedad < 6 ? 7 : antiguedad < 12 ? 15 : 30;
		items.push(rubro('notice', 'earning', diario, null, preaviso * diario, { quantity: preaviso }));
		const cesantia = diasDeCesantia(antiguedad);
		items.push(rubro('severance', 'earning', diario, null, cesantia * diario, { quantity: cesantia }));
	}
	if (dias > 0) items.push(rubro('vacation_payout', 'earning', diario, null, dias * diario, { quantity: dias }));
	items.push(rubro('aguinaldo', 'earning', ganadoDesdeDiciembre, null, ganadoDesdeDiciembre / 12));
	return [totales(e.id, contrato.id, items, new Set())];
}

/** `meses` meses antes del primer día de mes `iso` (negativo) como ISO. */
function iso6(mes: string, meses: number): string {
	const d = fecha(mes);
	d.setUTCMonth(d.getUTCMonth() + meses);
	return d.toISOString().slice(0, 10);
}

function lineasAjuste(ctx: PayrollMockContext, companyId: number, corrida: MockRun): Omit<MockLine, 'id' | 'run_id'>[] {
	const p = planilla(companyId);
	const original = p.runs.find((r) => r.id === corrida.adjusts_run_id)!;
	const antes = new Map(p.lines.filter((l) => l.run_id === original.id).map((l) => [l.employee_id, l]));
	const ahora = new Map(lineasRegulares(ctx, companyId, { ...corrida, schedule_id: original.schedule_id }, original.id).map((l) => [l.employee_id, l]));
	const clave = (i: PayrollItem) => `${i.concept}|${i.payer}|${i.action_id}|${i.applied_from}|${i.applied_to}`;
	const tasas = tasasAl(ctx, corrida.period_to);
	const ccss = new Set([...tasas.values()].filter((t) => t.payer === 'employee').map((t) => t.concept));
	const lineas: Omit<MockLine, 'id' | 'run_id'>[] = [];
	for (const employeeId of [...new Set([...antes.keys(), ...ahora.keys()])].sort((a, b) => a - b)) {
		const viejos = new Map((antes.get(employeeId)?.items ?? []).map((i) => [clave(i), i]));
		const nuevos = new Map((ahora.get(employeeId)?.items ?? []).map((i) => [clave(i), i]));
		const items: PayrollItem[] = [];
		for (const k of [...nuevos.keys(), ...[...viejos.keys()].filter((k) => !nuevos.has(k))]) {
			const diferencia = round2((nuevos.get(k)?.amount ?? 0) - (viejos.get(k)?.amount ?? 0));
			if (diferencia === 0) continue;
			const modelo = (nuevos.get(k) ?? viejos.get(k))!;
			items.push({ ...modelo, amount: diferencia });
		}
		if (!items.length) continue;
		lineas.push(totales(employeeId, ahora.get(employeeId)?.contract_id ?? antes.get(employeeId)!.contract_id, items, ccss));
	}
	return lineas;
}

// -------------------------------------------------------------------- rutas

export function rutasDePlanilla(ctx: PayrollMockContext): void {
	const { route, exigirAdmin, exigirModulo, registrar, nowIso } = ctx;
	const hoy = () => nowIso().slice(0, 10);

	function admin(userId: number | null, companyId: number, escribe = false): MockUser {
		const u = exigirAdmin(userId, companyId);
		if (escribe) exigirModulo(companyId, 'payroll');
		return u;
	}

	// --------------------------------------------------------- configuración
	route('GET', '/payroll/settings', ({ userId, companyId }) => {
		admin(userId, companyId);
		return { ...planilla(companyId).settings };
	});
	route('PUT', '/payroll/settings', ({ body, userId, companyId }) => {
		admin(userId, companyId, true);
		const numero = txt(body?.employer_number);
		if (numero && (!/^[0-9-]+$/.test(numero) || numero.length < 9 || numero.length > 25)) {
			fail(400, 'invalid_payroll_settings', { field: 'employer_number', reason: 'bad_format' });
		}
		planilla(companyId).settings = { employer_number: numero, ina_exempt: Boolean(body?.ina_exempt) };
		persist();
		return { ...planilla(companyId).settings };
	});

	route('GET', '/payroll/schedules', ({ userId, companyId }) => {
		admin(userId, companyId);
		return [...planilla(companyId).schedules].sort((a, b) => a.name.localeCompare(b.name));
	});
	route('POST', '/payroll/schedules', ({ body, userId, companyId }) => {
		admin(userId, companyId, true);
		const p = planilla(companyId);
		const nombre = String(body?.name ?? '').trim();
		const shift = String(body?.shift ?? 'day');
		const fila: WorkSchedule = {
			id: 0,
			name: nombre,
			frequency: String(body?.frequency ?? ''),
			shift,
			hours_per_day: num(body?.hours_per_day) ?? CLASES[shift] ?? 8,
			workdays_per_week: num(body?.workdays_per_week) ?? 6,
			rest_day_paid: body?.rest_day_paid ?? true,
			first_cut_day: num(body?.first_cut_day),
			cut_weekday: num(body?.cut_weekday),
			series_start: txt(body?.series_start),
			is_active: true
		};
		revisarJornada(fila);
		if (p.schedules.some((s) => s.name === nombre)) fail(409, 'payroll_name_taken', { resource: 'schedules', name: nombre });
		fila.id = nextId('payroll_schedules');
		p.schedules.push(fila);
		persist();
		return fila;
	});
	route('PUT', '/payroll/schedules/:id', ({ params, body, userId, companyId }) => {
		admin(userId, companyId, true);
		const p = planilla(companyId);
		const fila = p.schedules.find((s) => s.id === Number(params[0]));
		if (!fila) fail(404, 'schedule_not_found', { schedule_id: Number(params[0]) });
		const cambios = body ?? {};
		const bloqueados = ['frequency', 'first_cut_day', 'cut_weekday', 'series_start'] as const;
		const tocaCortes = bloqueados.some((c) => c in cambios && cambios[c] !== (fila as unknown as Record<string, unknown>)[c]);
		if (tocaCortes && p.runs.some((r) => r.schedule_id === fila.id && r.status === 'paid')) fail(409, 'schedule_locked', { schedule_id: fila.id });
		const nueva: WorkSchedule = {
			...fila,
			...('name' in cambios ? { name: String(cambios.name).trim() } : {}),
			...('frequency' in cambios ? { frequency: String(cambios.frequency) } : {}),
			...('shift' in cambios ? { shift: String(cambios.shift) } : {}),
			...('hours_per_day' in cambios ? { hours_per_day: Number(cambios.hours_per_day) } : {}),
			...('workdays_per_week' in cambios ? { workdays_per_week: Number(cambios.workdays_per_week) } : {}),
			...('rest_day_paid' in cambios ? { rest_day_paid: Boolean(cambios.rest_day_paid) } : {}),
			...('first_cut_day' in cambios ? { first_cut_day: num(cambios.first_cut_day) } : {}),
			...('cut_weekday' in cambios ? { cut_weekday: num(cambios.cut_weekday) } : {}),
			...('series_start' in cambios ? { series_start: txt(cambios.series_start) } : {}),
			...('is_active' in cambios ? { is_active: Boolean(cambios.is_active) } : {})
		};
		revisarJornada(nueva);
		if (p.schedules.some((s) => s.id !== fila.id && s.name === nueva.name)) fail(409, 'payroll_name_taken', { resource: 'schedules', name: nueva.name });
		Object.assign(fila, nueva);
		persist();
		return fila;
	});

	route('GET', '/payroll/positions', ({ userId, companyId }) => {
		admin(userId, companyId);
		return [...planilla(companyId).positions].sort((a, b) => a.name.localeCompare(b.name));
	});
	function revisarPuesto(p: MockPayrollData, puesto: Position) {
		if (!puesto.name) fail(400, 'invalid_payroll_settings', { field: 'name', reason: 'required' });
		if (!/^\d{4}$/.test(puesto.ccss_code)) fail(400, 'invalid_payroll_settings', { field: 'ccss_code', reason: 'bad_format' });
		if (!/^[0-9A-Za-z]{1,5}$/.test(puesto.ins_code)) fail(400, 'invalid_payroll_settings', { field: 'ins_code', reason: 'bad_format' });
		if (p.positions.some((x) => x.id !== puesto.id && x.name === puesto.name)) fail(409, 'payroll_name_taken', { resource: 'positions', name: puesto.name });
	}
	route('POST', '/payroll/positions', ({ body, userId, companyId }) => {
		admin(userId, companyId, true);
		const p = planilla(companyId);
		const puesto: Position = { id: 0, name: String(body?.name ?? '').trim(), ccss_code: String(body?.ccss_code ?? '').trim(), ins_code: String(body?.ins_code ?? '').trim(), is_active: true };
		revisarPuesto(p, puesto);
		puesto.id = nextId('payroll_positions');
		p.positions.push(puesto);
		persist();
		return puesto;
	});
	route('PUT', '/payroll/positions/:id', ({ params, body, userId, companyId }) => {
		admin(userId, companyId, true);
		const p = planilla(companyId);
		const puesto = p.positions.find((x) => x.id === Number(params[0]));
		if (!puesto) fail(404, 'position_not_found', { position_id: Number(params[0]) });
		const nuevo: Position = {
			...puesto,
			...(body?.name != null ? { name: String(body.name).trim() } : {}),
			...(body?.ccss_code != null ? { ccss_code: String(body.ccss_code).trim() } : {}),
			...(body?.ins_code != null ? { ins_code: String(body.ins_code).trim() } : {}),
			...(body?.is_active != null ? { is_active: Boolean(body.is_active) } : {})
		};
		revisarPuesto(p, nuevo);
		Object.assign(puesto, nuevo);
		persist();
		return puesto;
	});

	route('GET', '/payroll/policies', ({ userId, companyId }) => {
		admin(userId, companyId);
		return [...planilla(companyId).policies].sort((a, b) => Number(b.is_default) - Number(a.is_default) || a.number.localeCompare(b.number));
	});
	route('POST', '/payroll/policies', ({ body, userId, companyId }) => {
		admin(userId, companyId, true);
		const p = planilla(companyId);
		const numero = String(body?.number ?? '').trim();
		const prima = Number(body?.rt_rate);
		if (!numero) fail(400, 'invalid_payroll_settings', { field: 'number', reason: 'required' });
		if (numero.length > 20) fail(400, 'invalid_payroll_settings', { field: 'number', reason: 'too_long' });
		if (!(prima > 0 && prima < 1)) fail(400, 'invalid_payroll_settings', { field: 'rt_rate', reason: 'out_of_range' });
		if (p.policies.some((x) => x.number === numero)) fail(409, 'payroll_name_taken', { resource: 'policies', name: numero });
		const poliza: InsPolicy = { id: nextId('payroll_policies'), number: numero, rt_rate: prima, is_default: false };
		if (body?.is_default || !p.policies.length) {
			for (const otra of p.policies) otra.is_default = false;
			poliza.is_default = true;
		}
		p.policies.push(poliza);
		persist();
		return poliza;
	});
	route('PUT', '/payroll/policies/:id', ({ params, body, userId, companyId }) => {
		admin(userId, companyId, true);
		const p = planilla(companyId);
		const poliza = p.policies.find((x) => x.id === Number(params[0]));
		if (!poliza) fail(404, 'policy_not_found', { policy_id: Number(params[0]) });
		if (body?.rt_rate != null) {
			const prima = Number(body.rt_rate);
			if (!(prima > 0 && prima < 1)) fail(400, 'invalid_payroll_settings', { field: 'rt_rate', reason: 'out_of_range' });
			poliza.rt_rate = prima;
		}
		if (body?.is_default) {
			for (const otra of p.policies) otra.is_default = false;
			poliza.is_default = true;
		}
		persist();
		return poliza;
	});

	// -------------------------------------------------------------- empleados
	route('GET', '/payroll/employees', ({ userId, companyId }) => {
		admin(userId, companyId);
		const p = planilla(companyId);
		return [...p.employees].sort((a, b) => a.last_name_1.localeCompare(b.last_name_1) || a.first_name.localeCompare(b.first_name) || a.id - b.id).map((e) => empleadoOut(p, e));
	});
	function fichaDe(body: any, base?: MockEmployee): MockEmployee {
		const v = (campo: keyof MockEmployee, porOmision: unknown) => (body && campo in body ? body[campo] : base ? base[campo] : porOmision);
		return {
			id: base?.id ?? 0,
			user_id: num(v('user_id', null)),
			identification_type: String(v('identification_type', '')),
			identification: String(v('identification', '')).trim(),
			first_name: String(v('first_name', '')).trim(),
			last_name_1: String(v('last_name_1', '')).trim(),
			last_name_2: txt(v('last_name_2', null)),
			insured_number: txt(v('insured_number', null)),
			birth_date: String(v('birth_date', '')),
			gender: String(v('gender', '')),
			marital_status: String(v('marital_status', '')),
			nationality: String(v('nationality', 'CR')),
			phone: txt(v('phone', null)),
			email: txt(v('email', null)),
			is_pensioner: Boolean(v('is_pensioner', false)),
			iban: txt(v('iban', null)),
			hired_on: String(v('hired_on', '')),
			terminated_on: base?.terminated_on ?? null,
			termination_cause: base?.termination_cause ?? null,
			dependent_children: Number(v('dependent_children', 0)) || 0,
			spouse_credit: Boolean(v('spouse_credit', false)),
			is_active: base?.is_active ?? true
		};
	}
	route('POST', '/payroll/employees', ({ body, userId, companyId }) => {
		admin(userId, companyId, true);
		const p = planilla(companyId);
		const e = fichaDe(body);
		revisarEmpleado(e);
		if (p.employees.some((x) => x.identification === e.identification)) fail(409, 'employee_identification_taken', { identification: e.identification });
		// El contrato del alta (RF-55) se revisa antes de guardar nada: los dos o ninguno.
		const contrato = body?.contract ? contratoDe(p, e, body.contract, e.hired_on).nuevo : null;
		e.id = nextId('payroll_employees');
		p.employees.push(e);
		if (contrato) p.contracts.push({ ...contrato, employee_id: e.id });
		persist();
		return empleadoOut(p, e);
	});
	function empleado(p: MockPayrollData, id: number): MockEmployee {
		const e = p.employees.find((x) => x.id === id);
		if (!e) fail(404, 'employee_not_found', { employee_id: id });
		return e;
	}
	route('GET', '/payroll/employees/:id', ({ params, userId, companyId }) => {
		admin(userId, companyId);
		const p = planilla(companyId);
		return empleadoOut(p, empleado(p, Number(params[0])));
	});
	route('PUT', '/payroll/employees/:id', ({ params, body, userId, companyId }) => {
		admin(userId, companyId, true);
		const p = planilla(companyId);
		const e = empleado(p, Number(params[0]));
		const nuevo = fichaDe(body, e);
		revisarEmpleado(nuevo);
		if (p.employees.some((x) => x.id !== e.id && x.identification === nuevo.identification)) fail(409, 'employee_identification_taken', { identification: nuevo.identification });
		Object.assign(e, nuevo);
		persist();
		return empleadoOut(p, e);
	});
	route('POST', '/payroll/employees/:id/terminate', ({ params, body, userId, companyId }) => {
		const u = admin(userId, companyId, true);
		const p = planilla(companyId);
		const e = empleado(p, Number(params[0]));
		if (e.terminated_on) fail(409, 'employee_terminated', { employee_id: e.id, terminated_on: e.terminated_on });
		const salida = String(body?.terminated_on ?? '');
		const causa = String(body?.cause ?? '');
		if (!CAUSAS.includes(causa)) fail(400, 'invalid_employee', { field: 'termination_cause', reason: 'unknown' });
		if (salida < e.hired_on) fail(400, 'invalid_employee', { field: 'terminated_on', reason: 'before_hire' });
		const contratos = p.contracts.filter((c) => c.employee_id === e.id).sort((a, b) => (a.valid_from < b.valid_from ? -1 : 1));
		if (!contratos.length) fail(409, 'contract_missing', { employee_id: e.id });
		for (const c of contratos) if (c.valid_to == null || c.valid_to > salida) c.valid_to = salida;
		e.terminated_on = salida;
		e.termination_cause = causa;
		e.is_active = false;
		p.actions.push({
			id: nextId('payroll_actions'), employee_id: e.id, kind: 'termination', starts_on: salida, ends_on: null, hours: null, days: null,
			amount: null, total_amount: null, new_salary: null, position_id: null, is_recurring: false, memo: causa, cancels_action_id: null,
			suspended_at: null, suspended_by: null, suspension_reason: null, source: 'system', created_by: u.id_user, created_at: nowIso()
		});
		const liquidacion: MockRun = {
			id: nextId('payroll_runs'), kind: 'settlement', schedule_id: null, period_from: salida, period_to: salida, pay_date: salida,
			status: 'draft', adjusts_run_id: null, journal_entry_id: null, created_by: u.id_user, created_at: nowIso(),
			approved_by: null, approved_at: null, paid_by: null, paid_at: null
		};
		p.runs.push(liquidacion);
		p.lines.push({ id: nextId('payroll_lines'), run_id: liquidacion.id, ...totales(e.id, contratos[contratos.length - 1].id, [], new Set()) });
		persist();
		return { employee: empleadoOut(p, e), settlement_run_id: liquidacion.id };
	});
	route('GET', '/payroll/employees/:id/actions', ({ params, userId, companyId }) => {
		admin(userId, companyId);
		const p = planilla(companyId);
		const e = empleado(p, Number(params[0]));
		return p.actions.filter((a) => a.employee_id === e.id).sort((a, b) => (a.starts_on < b.starts_on ? -1 : a.starts_on > b.starts_on ? 1 : a.id - b.id)).map((a) => accionOut(p, a));
	});

	// -------------------------------------------------------------- contratos
	route('GET', '/payroll/contracts', ({ query, userId, companyId }) => {
		admin(userId, companyId);
		const p = planilla(companyId);
		const e = empleado(p, Number(query.get('employee')));
		return p.contracts.filter((c) => c.employee_id === e.id).sort((a, b) => (a.valid_from < b.valid_from ? -1 : 1)).map(contratoOut);
	});
	route('POST', '/payroll/contracts', ({ body, userId, companyId }) => {
		admin(userId, companyId, true);
		const p = planilla(companyId);
		const e = empleado(p, Number(body?.employee_id));
		if (e.terminated_on) fail(409, 'employee_terminated', { employee_id: e.id, terminated_on: e.terminated_on });
		const { nuevo, cierra } = contratoDe(p, e, body, String(body?.valid_from ?? ''));
		if (cierra) cierra.valid_to = sumarDias(nuevo.valid_from, -1);
		p.contracts.push(nuevo);
		persist();
		return contratoOut(nuevo);
	});

	/** Revisa un contrato y lo devuelve sin guardarlo: lo usan el alta y el contrato suelto. */
	function contratoDe(p: MockPayrollData, e: MockEmployee, body: any, desde: string) {
		const jornada = p.schedules.find((s) => s.id === Number(body?.schedule_id));
		if (!jornada) fail(404, 'schedule_not_found', { schedule_id: Number(body?.schedule_id) });
		const puesto = p.positions.find((x) => x.id === Number(body?.position_id));
		if (!puesto) fail(404, 'position_not_found', { position_id: Number(body?.position_id) });
		const polizaId = num(body?.ins_policy_id);
		if (polizaId != null && !p.policies.some((x) => x.id === polizaId)) fail(404, 'policy_not_found', { policy_id: polizaId });
		const salario = Number(body?.period_salary);
		const solidarista = num(body?.solidarista_rate);
		const previos = p.contracts.filter((c) => c.employee_id === e.id).sort((a, b) => (a.valid_from < b.valid_from ? -1 : 1));
		const ultimo = previos.at(-1);
		const tope = ultimo ? (ultimo.valid_to ?? ultimo.valid_from) : null;
		if (!(salario > 0)) fail(400, 'invalid_contract', { field: 'period_salary', reason: 'not_positive' });
		if (desde < e.hired_on) fail(400, 'invalid_contract', { field: 'valid_from', reason: 'before_hire' });
		if (tope != null && desde <= tope) fail(400, 'invalid_contract', { field: 'valid_from', reason: 'overlaps' });
		if (solidarista != null && !(solidarista >= 0 && solidarista < 1)) fail(400, 'invalid_contract', { field: 'solidarista_rate', reason: 'out_of_range' });
		if (!jornada.is_active) fail(400, 'invalid_contract', { field: 'schedule_id', reason: 'inactive' });
		if (!puesto.is_active) fail(400, 'invalid_contract', { field: 'position_id', reason: 'inactive' });
		const nuevo: EmploymentContract = { id: nextId('payroll_contracts'), employee_id: e.id, schedule_id: jornada.id, position_id: puesto.id, ins_policy_id: polizaId, valid_from: desde, valid_to: null, period_salary: round2(salario), solidarista_rate: solidarista };
		return { nuevo, cierra: ultimo && ultimo.valid_to == null ? ultimo : null };
	}

	// --------------------------------------------------------------- acciones
	function pedido(body: any) {
		return {
			starts_on: String(body?.starts_on ?? ''),
			ends_on: txt(body?.ends_on),
			hours: num(body?.hours),
			days: num(body?.days),
			amount: num(body?.amount),
			total_amount: num(body?.total_amount),
			new_salary: num(body?.new_salary),
			position_id: num(body?.position_id),
			is_recurring: Boolean(body?.is_recurring),
			memo: txt(body?.memo)
		};
	}
	function accion(p: MockPayrollData, id: number): MockAction {
		const a = p.actions.find((x) => x.id === id);
		if (!a) fail(404, 'action_not_found', { action_id: id });
		return a;
	}
	function revisarSaldo(p: MockPayrollData, employeeId: number, dias: number, devuelve = 0) {
		const saldo = round2(saldoVacaciones(p, employeeId) + devuelve);
		if (dias > saldo) fail(409, 'vacation_balance_exceeded', { employee_id: employeeId, balance: saldo, requested: dias });
	}
	route('POST', '/payroll/actions', ({ body, userId, companyId }) => {
		const u = admin(userId, companyId, true);
		const p = planilla(companyId);
		const kind = String(body?.kind ?? '');
		if (kind === 'termination') fail(400, 'invalid_action', { field: 'kind', reason: 'not_allowed' });
		const datos = pedido(body);
		revisarAccion({ kind, ...datos });
		const e = empleado(p, Number(body?.employee_id));
		if (e.terminated_on && datos.starts_on > e.terminated_on) fail(409, 'employee_terminated', { employee_id: e.id, terminated_on: e.terminated_on });
		const contrato = contratoVigente(p, e.id, datos.starts_on);
		if (!contrato) fail(409, 'contract_missing', { employee_id: e.id });
		if (kind === 'vacation') revisarSaldo(p, e.id, datos.days ?? 0);
		if (kind === 'raise' || kind === 'position_change') {
			if (datos.starts_on <= contrato.valid_from) fail(400, 'invalid_contract', { field: 'valid_from', reason: 'overlaps' });
			let posicion = contrato.position_id;
			if (kind === 'position_change') {
				const puesto = p.positions.find((x) => x.id === datos.position_id);
				if (!puesto) fail(404, 'position_not_found', { position_id: datos.position_id });
				if (!puesto.is_active) fail(400, 'invalid_contract', { field: 'position_id', reason: 'inactive' });
				posicion = puesto.id;
			}
			contrato.valid_to = sumarDias(datos.starts_on, -1);
			p.contracts.push({ id: nextId('payroll_contracts'), employee_id: e.id, schedule_id: contrato.schedule_id, position_id: posicion, ins_policy_id: contrato.ins_policy_id, valid_from: datos.starts_on, valid_to: null, period_salary: kind === 'raise' ? round2(datos.new_salary ?? 0) : contrato.period_salary, solidarista_rate: contrato.solidarista_rate });
		}
		const nueva: MockAction = { id: nextId('payroll_actions'), employee_id: e.id, kind, ...datos, cancels_action_id: null, suspended_at: null, suspended_by: null, suspension_reason: null, source: 'manual', created_by: u.id_user, created_at: nowIso() };
		p.actions.push(nueva);
		if (kind === 'vacation') p.vacations.push({ id: nextId('payroll_vacations'), employee_id: e.id, kind: 'taken', days: datos.days ?? 0, on_date: datos.starts_on, run_id: null, action_id: nueva.id });
		persist();
		return accionOut(p, nueva);
	});
	function editable(p: MockPayrollData, a: MockAction) {
		if (a.cancels_action_id != null) fail(409, 'action_not_editable', { action_id: a.id, reason: 'cancellation' });
		if (DEL_CONTRATO.has(a.kind)) fail(409, 'action_not_editable', { action_id: a.id, reason: 'contract' });
		if (p.actions.some((o) => o.cancels_action_id === a.id)) fail(409, 'action_already_cancelled', { action_id: a.id });
	}
	route('PUT', '/payroll/actions/:id', ({ params, body, userId, companyId }) => {
		admin(userId, companyId, true);
		const p = planilla(companyId);
		const a = accion(p, Number(params[0]));
		editable(p, a);
		if (aplicados(p, a.id).length) fail(409, 'action_not_editable', { action_id: a.id, reason: 'applied' });
		const datos = pedido(body);
		revisarAccion({ kind: a.kind, ...datos, new_salary: null, position_id: null });
		if (a.kind === 'vacation') {
			revisarSaldo(p, a.employee_id, datos.days ?? 0, a.days ?? 0);
			const mov = p.vacations.find((m) => m.action_id === a.id);
			if (mov) Object.assign(mov, { days: datos.days ?? 0, on_date: datos.starts_on });
		}
		Object.assign(a, { ...datos, new_salary: null, position_id: null });
		persist();
		return accionOut(p, a);
	});
	route('POST', '/payroll/actions/:id/cancel', ({ params, body, userId, companyId }) => {
		const u = admin(userId, companyId, true);
		const p = planilla(companyId);
		const a = accion(p, Number(params[0]));
		editable(p, a);
		const nueva: MockAction = { id: nextId('payroll_actions'), employee_id: a.employee_id, kind: a.kind, starts_on: a.starts_on, ends_on: a.ends_on, hours: null, days: null, amount: null, total_amount: null, new_salary: null, position_id: null, is_recurring: false, memo: txt(body?.memo), cancels_action_id: a.id, suspended_at: null, suspended_by: null, suspension_reason: null, source: 'manual', created_by: u.id_user, created_at: nowIso() };
		p.actions.push(nueva);
		if (a.kind === 'vacation' && a.days) p.vacations.push({ id: nextId('payroll_vacations'), employee_id: a.employee_id, kind: 'taken', days: -a.days, on_date: a.starts_on, run_id: null, action_id: nueva.id });
		persist();
		return accionOut(p, nueva);
	});
	route('POST', '/payroll/actions/:id/suspend', ({ params, body, userId, companyId }) => {
		const u = admin(userId, companyId, true);
		const p = planilla(companyId);
		const a = accion(p, Number(params[0]));
		if (!['deduction', 'child_support'].includes(a.kind) || !a.is_recurring) fail(409, 'action_not_recurring', { action_id: a.id });
		if (p.actions.some((o) => o.cancels_action_id === a.id)) fail(409, 'action_already_cancelled', { action_id: a.id });
		if (a.suspended_at) fail(409, 'action_already_suspended', { action_id: a.id });
		const motivo = String(body?.reason ?? '').trim();
		if (motivo.length < 3) fail(422, 'invalid_request');
		Object.assign(a, { suspended_at: nowIso(), suspended_by: u.id_user, suspension_reason: motivo });
		persist();
		return accionOut(p, a);
	});

	// --------------------------------------------------------------- corridas
	function corrida(p: MockPayrollData, id: number): MockRun {
		const r = p.runs.find((x) => x.id === id);
		if (!r) fail(404, 'run_not_found', { run_id: id });
		return r;
	}
	route('GET', '/payroll/runs', ({ userId, companyId }) => {
		admin(userId, companyId);
		const p = planilla(companyId);
		return [...p.runs].sort((a, b) => (a.period_to > b.period_to ? -1 : a.period_to < b.period_to ? 1 : b.id - a.id)).map((r) => corridaOut(p, r, false));
	});
	route('POST', '/payroll/runs', ({ body, userId, companyId }) => {
		const u = admin(userId, companyId, true);
		const p = planilla(companyId);
		const jornada = p.schedules.find((s) => s.id === Number(body?.schedule_id));
		if (!jornada) fail(404, 'schedule_not_found', { schedule_id: Number(body?.schedule_id) });
		if (!jornada.is_active) fail(400, 'invalid_schedule', { field: 'is_active', reason: 'inactive' });
		const corte = String(body?.cut_date ?? '');
		const periodo = periodoDe(jornada, corte);
		if (!periodo) fail(400, 'invalid_cut_date', { cut: corte, frequency: jornada.frequency });
		const existente = p.runs.find((r) => r.schedule_id === jornada.id && r.period_to === corte && r.kind === 'regular');
		if (existente) fail(409, 'run_already_exists', { run_id: existente.id });
		const nueva: MockRun = { id: nextId('payroll_runs'), kind: 'regular', schedule_id: jornada.id, period_from: periodo.desde, period_to: corte, pay_date: txt(body?.pay_date) ?? corte, status: 'draft', adjusts_run_id: null, journal_entry_id: null, created_by: u.id_user, created_at: nowIso(), approved_by: null, approved_at: null, paid_by: null, paid_at: null };
		p.runs.push(nueva);
		persist();
		return corridaOut(p, nueva, true);
	});
	route('POST', '/payroll/runs/aguinaldo', ({ body, userId, companyId }) => {
		const u = admin(userId, companyId, true);
		const p = planilla(companyId);
		const anio = Number(body?.year);
		if (!(anio >= 2000 && anio <= 2100)) fail(422, 'invalid_request');
		const hasta = `${anio}-11-30`;
		const existente = p.runs.find((r) => r.schedule_id == null && r.period_to === hasta && r.kind === 'aguinaldo');
		if (existente) fail(409, 'run_already_exists', { run_id: existente.id });
		const nueva: MockRun = { id: nextId('payroll_runs'), kind: 'aguinaldo', schedule_id: null, period_from: `${anio - 1}-12-01`, period_to: hasta, pay_date: txt(body?.pay_date) ?? `${anio}-12-20`, status: 'draft', adjusts_run_id: null, journal_entry_id: null, created_by: u.id_user, created_at: nowIso(), approved_by: null, approved_at: null, paid_by: null, paid_at: null };
		p.runs.push(nueva);
		persist();
		return corridaOut(p, nueva, true);
	});
	route('GET', '/payroll/runs/:id', ({ params, userId, companyId }) => {
		admin(userId, companyId);
		const p = planilla(companyId);
		return corridaOut(p, corrida(p, Number(params[0])), true);
	});
	route('POST', '/payroll/runs/:id/calculate', ({ params, userId, companyId }) => {
		admin(userId, companyId, true);
		const p = planilla(companyId);
		const r = corrida(p, Number(params[0]));
		if (r.status === 'paid') fail(409, 'run_already_paid', { run_id: r.id });
		if (r.status !== 'draft') fail(409, 'run_not_editable', { run_id: r.id, reason: r.status });
		const lineas =
			r.kind === 'aguinaldo' ? lineasAguinaldo(companyId, r)
			: r.kind === 'settlement' ? lineasLiquidacion(companyId, r)
			: r.kind === 'adjustment' ? lineasAjuste(ctx, companyId, r)
			: lineasRegulares(ctx, companyId, r, r.id);
		p.lines = p.lines.filter((l) => l.run_id !== r.id);
		for (const l of lineas) p.lines.push({ id: nextId('payroll_lines'), run_id: r.id, ...l });
		getEmpresa(companyId).payroll = p;
		persist();
		return corridaOut(p, r, true);
	});
	route('POST', '/payroll/runs/:id/approve', ({ params, userId, companyId }) => {
		const u = admin(userId, companyId, true);
		const p = planilla(companyId);
		const r = corrida(p, Number(params[0]));
		if (r.status === 'paid') fail(409, 'run_already_paid', { run_id: r.id });
		if (r.status !== 'draft') fail(409, 'run_not_editable', { run_id: r.id, reason: r.status });
		if (!p.lines.some((l) => l.run_id === r.id)) fail(409, 'run_not_calculated', { run_id: r.id });
		Object.assign(r, { status: 'approved', approved_by: u.id_user, approved_at: nowIso() });
		persist();
		return corridaOut(p, r, true);
	});
	route('POST', '/payroll/runs/:id/pay', ({ params, userId, companyId }) => {
		const u = admin(userId, companyId, true);
		const p = planilla(companyId);
		const r = corrida(p, Number(params[0]));
		if (r.status === 'paid') fail(409, 'run_already_paid', { run_id: r.id });
		if (r.status !== 'approved') fail(409, 'run_not_approved', { run_id: r.id, status: r.status });
		const lineas = p.lines.filter((l) => l.run_id === r.id);
		let asiento: number | null = null;
		if (contabilidadActiva(companyId)) {
			const suma = (f: (l: MockLine) => number) => round2(lineas.reduce((t, l) => t + f(l), 0));
			asiento = postPayroll(companyId, { id: r.id, date: r.pay_date, gross: suma((l) => l.gross), employer_charges: suma((l) => l.employer_charges), social_security: suma((l) => l.employee_deductions), income_tax: suma((l) => l.income_tax), other_deductions: suma((l) => l.other_deductions), net: suma((l) => l.net) }, u.id_user)?.id ?? null;
		}
		Object.assign(r, { status: 'paid', paid_by: u.id_user, paid_at: nowIso(), journal_entry_id: asiento });
		if (r.kind === 'regular') {
			const jornada = p.schedules.find((s) => s.id === r.schedule_id)!;
			for (const l of lineas) {
				const dias = l.items.filter((i) => i.concept === 'base' && i.payer === 'earning' && i.applied_from && i.applied_to).reduce((t, i) => t + diasCalendario(i.applied_from!, i.applied_to!), 0);
				p.vacations.push({ id: nextId('payroll_vacations'), employee_id: l.employee_id, kind: 'accrual', days: round2((dias * 2 * jornada.workdays_per_week) / 350), on_date: r.period_to, run_id: r.id, action_id: null });
			}
		} else if (r.kind === 'settlement') {
			for (const l of lineas) for (const i of l.items) if (i.concept === 'vacation_payout' && i.quantity) p.vacations.push({ id: nextId('payroll_vacations'), employee_id: l.employee_id, kind: 'paid', days: i.quantity, on_date: r.period_to, run_id: r.id, action_id: null });
		}
		registrar(u.id_user, companyId, 'planilla_pagada', `corrida ${r.id} (${r.period_from} a ${r.period_to})`);
		persist();
		return corridaOut(p, r, true);
	});
	route('POST', '/payroll/runs/:id/adjust', ({ params, userId, companyId }) => {
		const u = admin(userId, companyId, true);
		const p = planilla(companyId);
		const original = corrida(p, Number(params[0]));
		if (original.status !== 'paid') fail(409, 'run_not_paid', { run_id: original.id, status: original.status });
		if (original.kind !== 'regular') fail(409, 'run_not_editable', { run_id: original.id, reason: original.kind });
		const ajuste: MockRun = { id: nextId('payroll_runs'), kind: 'adjustment', schedule_id: original.schedule_id, period_from: original.period_from, period_to: original.period_to, pay_date: hoy(), status: 'draft', adjusts_run_id: original.id, journal_entry_id: null, created_by: u.id_user, created_at: nowIso(), approved_by: null, approved_at: null, paid_by: null, paid_at: null };
		p.runs.push(ajuste);
		persist();
		return corridaOut(p, ajuste, true);
	});
	route('GET', '/payroll/runs/:id/payslips/:employee', ({ params, userId, companyId }) => {
		admin(userId, companyId);
		const p = planilla(companyId);
		const r = corrida(p, Number(params[0]));
		const l = p.lines.find((x) => x.run_id === r.id && x.employee_id === Number(params[1]));
		if (!l) fail(404, 'employee_not_found', { employee_id: Number(params[1]) });
		const e = empleado(p, l.employee_id);
		const contrato = p.contracts.find((c) => c.id === l.contract_id);
		const puesto = contrato ? p.positions.find((x) => x.id === contrato.position_id) : undefined;
		const jornada = contrato ? p.schedules.find((x) => x.id === contrato.schedule_id) : undefined;
		const accionDe = (id: number | null) => (id == null ? undefined : p.actions.find((a) => a.id === id));
		return {
			run: { id: r.id, kind: r.kind, period_from: r.period_from, period_to: r.period_to, pay_date: r.pay_date, status: r.status, paid_at: r.paid_at, adjusts_run_id: r.adjusts_run_id },
			employer_number: p.settings.employer_number,
			employee: { id: e.id, first_name: e.first_name, last_name_1: e.last_name_1, last_name_2: e.last_name_2, identification_type: e.identification_type, identification: e.identification, insured_number: e.insured_number, hired_on: e.hired_on, terminated_on: e.terminated_on, iban: e.iban, position_name: puesto?.name ?? null, schedule_name: jornada?.name ?? null, frequency: jornada?.frequency ?? null, period_salary: contrato?.period_salary ?? null },
			line: { gross: l.gross, employee_deductions: l.employee_deductions, income_tax: l.income_tax, other_deductions: l.other_deductions, net: l.net, employer_charges: l.employer_charges },
			items: l.items.map((i) => ({ ...i, action_kind: accionDe(i.action_id)?.kind ?? null, action_memo: accionDe(i.action_id)?.memo ?? null }))
		};
	});

	// ------------------------------------------------------------- vacaciones
	route('GET', '/payroll/vacations/:id', ({ params, userId, companyId }) => {
		admin(userId, companyId);
		const p = planilla(companyId);
		const e = empleado(p, Number(params[0]));
		return {
			employee_id: e.id,
			balance: saldoVacaciones(p, e.id),
			movements: p.vacations.filter((m) => m.employee_id === e.id).sort((a, b) => (a.on_date < b.on_date ? -1 : a.on_date > b.on_date ? 1 : a.id - b.id)).map(({ employee_id: _e, ...m }) => m)
		};
	});

	// ------------------------------------------------------------- importación
	route('POST', '/payroll/import', ({ query, body, userId, companyId }) => {
		const u = admin(userId, companyId, true);
		const p = planilla(companyId);
		const ensayo = query.get('dry_run') !== 'false';
		const asOf = String(body?.as_of ?? hoy());
		const puestos: any[] = body?.positions ?? [];
		const empleados: any[] = body?.employees ?? [];
		const devengados: any[] = body?.earnings ?? [];
		const deducciones: any[] = body?.deductions ?? [];
		const errores: { sheet: string; row: number; code: string; field: string | null; reason: string | null }[] = [];
		const error = (sheet: string, row: number, code: string, field: string | null = null, reason: string | null = null) => errores.push({ sheet, row, code, field, reason });

		const puestosDelArchivo = new Set<string>();
		for (const f of puestos) {
			const nombre = String(f.name ?? '').trim();
			if (!nombre) { error('positions', f.row, 'invalid_payroll_settings', 'name', 'required'); continue; }
			if (!/^\d{4}$/.test(String(f.ccss_code ?? '').trim())) { error('positions', f.row, 'invalid_payroll_settings', 'ccss_code', 'bad_format'); continue; }
			if (!/^[0-9A-Za-z]{1,5}$/.test(String(f.ins_code ?? '').trim())) { error('positions', f.row, 'invalid_payroll_settings', 'ins_code', 'bad_format'); continue; }
			if (puestosDelArchivo.has(nombre)) { error('positions', f.row, 'payroll_name_taken', 'name', 'duplicate'); continue; }
			puestosDelArchivo.add(nombre);
		}
		const cedulas = new Set<string>();
		const conocida = (c: string) => cedulas.has(c) || p.employees.some((e) => e.identification === c);
		for (const f of empleados) {
			const ficha = fichaDe(f);
			try {
				revisarEmpleado(ficha);
			} catch (e) {
				if (e instanceof ApiError) { error('employees', f.row, e.code, String(e.data.field ?? ''), String(e.data.reason ?? '')); continue; }
				throw e;
			}
			if (cedulas.has(ficha.identification) || p.employees.some((e) => e.identification === ficha.identification)) { error('employees', f.row, 'employee_identification_taken', 'identification', 'duplicate'); continue; }
			if (f.vacation_days != null && Number(f.vacation_days) < 0) { error('employees', f.row, 'invalid_employee', 'vacation_days', 'negative'); continue; }
			const jornada = p.schedules.find((s) => s.name === String(f.schedule ?? '').trim());
			if (!jornada) { error('employees', f.row, 'schedule_not_found', 'schedule'); continue; }
			const puesto = p.positions.find((x) => x.name === String(f.position ?? '').trim());
			if (!puesto && !puestosDelArchivo.has(String(f.position ?? '').trim())) { error('employees', f.row, 'position_not_found', 'position'); continue; }
			if (f.policy && !p.policies.some((x) => x.number === String(f.policy).trim())) { error('employees', f.row, 'policy_not_found', 'policy'); continue; }
			if (!(Number(f.period_salary) > 0)) { error('employees', f.row, 'invalid_contract', 'period_salary', 'not_positive'); continue; }
			if ((f.contract_from ?? ficha.hired_on) < ficha.hired_on) { error('employees', f.row, 'invalid_contract', 'valid_from', 'before_hire'); continue; }
			if (!jornada.is_active) { error('employees', f.row, 'invalid_contract', 'schedule_id', 'inactive'); continue; }
			if (puesto && !puesto.is_active) { error('employees', f.row, 'invalid_contract', 'position_id', 'inactive'); continue; }
			cedulas.add(ficha.identification);
		}
		const meses = new Set<string>();
		for (const f of devengados) {
			const cedula = String(f.identification ?? '').trim();
			if (!conocida(cedula)) { error('earnings', f.row, 'employee_not_found', 'identification'); continue; }
			if (Number(f.gross) < 0) { error('earnings', f.row, 'invalid_employee', 'gross', 'negative'); continue; }
			const clave = `${cedula}|${mesDe(String(f.month))}`;
			if (meses.has(clave)) { error('earnings', f.row, 'invalid_employee', 'month', 'duplicate'); continue; }
			meses.add(clave);
		}
		for (const f of deducciones) {
			const cedula = String(f.identification ?? '').trim();
			if (!conocida(cedula)) { error('deductions', f.row, 'employee_not_found', 'identification'); continue; }
			if (!DEDUCCIONES.includes(String(f.kind))) { error('deductions', f.row, 'invalid_action', 'kind', 'unknown'); continue; }
			try {
				revisarAccion({ kind: String(f.kind), starts_on: String(f.starts_on ?? ''), ends_on: txt(f.ends_on), hours: null, days: null, amount: num(f.amount), total_amount: num(f.balance), new_salary: null, position_id: null, is_recurring: (f.is_recurring ?? true) && f.kind !== 'garnishment' });
			} catch (e) {
				if (e instanceof ApiError) { error('deductions', f.row, e.code, String(e.data.field ?? ''), String(e.data.reason ?? '')); continue; }
				throw e;
			}
		}
		const resumen = { dry_run: ensayo, ok: errores.length === 0, errors: errores, positions: puestos.filter((f) => !p.positions.some((x) => x.name === String(f.name ?? '').trim())).length, employees: empleados.length, earnings: devengados.length, deductions: deducciones.length };
		if (ensayo) return resumen;
		if (errores.length) fail(400, 'import_has_errors', { errors: errores });

		for (const f of puestos) {
			const nombre = String(f.name).trim();
			if (!p.positions.some((x) => x.name === nombre)) p.positions.push({ id: nextId('payroll_positions'), name: nombre, ccss_code: String(f.ccss_code).trim(), ins_code: String(f.ins_code).trim(), is_active: true });
		}
		const ids = new Map<string, number>();
		for (const f of empleados) {
			const ficha = fichaDe(f);
			ficha.id = nextId('payroll_employees');
			p.employees.push(ficha);
			ids.set(ficha.identification, ficha.id);
			const jornada = p.schedules.find((s) => s.name === String(f.schedule).trim())!;
			const puesto = p.positions.find((x) => x.name === String(f.position).trim())!;
			const poliza = f.policy ? p.policies.find((x) => x.number === String(f.policy).trim()) : undefined;
			p.contracts.push({ id: nextId('payroll_contracts'), employee_id: ficha.id, schedule_id: jornada.id, position_id: puesto.id, ins_policy_id: poliza?.id ?? null, valid_from: String(f.contract_from ?? ficha.hired_on), valid_to: null, period_salary: round2(Number(f.period_salary)), solidarista_rate: num(f.solidarista_rate) });
			if (Number(f.vacation_days) > 0) p.vacations.push({ id: nextId('payroll_vacations'), employee_id: ficha.id, kind: 'opening', days: Number(f.vacation_days), on_date: asOf, run_id: null, action_id: null });
		}
		const idDe = (cedula: string) => ids.get(cedula) ?? p.employees.find((e) => e.identification === cedula)!.id;
		for (const f of devengados) p.opening.push({ id: nextId('payroll_opening'), employee_id: idDe(String(f.identification).trim()), period_month: mesDe(String(f.month)), gross: round2(Number(f.gross)) });
		for (const f of deducciones) {
			p.actions.push({ id: nextId('payroll_actions'), employee_id: idDe(String(f.identification).trim()), kind: String(f.kind), starts_on: String(f.starts_on), ends_on: txt(f.ends_on), hours: null, days: null, amount: num(f.amount), total_amount: num(f.balance), new_salary: null, position_id: null, is_recurring: (f.is_recurring ?? true) && f.kind !== 'garnishment', memo: txt(f.memo), cancels_action_id: null, suspended_at: null, suspended_by: null, suspension_reason: null, source: 'import', created_by: u.id_user, created_at: nowIso() });
		}
		persist();
		return resumen;
	});

	// ---------------------------------------------------------- archivos del mes
	function mesPagado(p: MockPayrollData, anio: number, mes: number) {
		const desde = `${anio}-${String(mes).padStart(2, '0')}-01`;
		const hasta = ultimoDiaDelMes(anio, mes);
		const porEmpleado = new Map<number, { items: PayrollItem[]; contract_id: number }>();
		for (const r of [...p.runs].sort((a, b) => (a.period_to < b.period_to ? -1 : 1))) {
			if (r.status !== 'paid' || !CON_SALARIO.has(r.kind) || r.period_to < desde || r.period_to > hasta) continue;
			for (const l of p.lines.filter((x) => x.run_id === r.id)) {
				const previo = porEmpleado.get(l.employee_id);
				porEmpleado.set(l.employee_id, { items: [...(previo?.items ?? []), ...l.items], contract_id: l.contract_id });
			}
		}
		return { desde, hasta, porEmpleado };
	}
	function trabajadores(p: MockPayrollData, anio: number, mes: number) {
		const { desde, hasta, porEmpleado } = mesPagado(p, anio, mes);
		const porOmision = p.policies.find((x) => x.is_default);
		return {
			desde,
			hasta,
			lista: [...porEmpleado.entries()].map(([employeeId, { items, contract_id }]) => {
				const e = p.employees.find((x) => x.id === employeeId)!;
				const contrato = p.contracts.find((c) => c.id === contract_id)!;
				const puesto = p.positions.find((x) => x.id === contrato.position_id);
				const jornada = p.schedules.find((x) => x.id === contrato.schedule_id)!;
				const poliza = contrato.ins_policy_id != null ? p.policies.find((x) => x.id === contrato.ins_policy_id) : porOmision;
				return { e, items, puesto, jornada, poliza, nombre: nombre(e) };
			}).sort((a, b) => a.e.last_name_1.localeCompare(b.e.last_name_1) || a.e.first_name.localeCompare(b.e.first_name) || a.e.id - b.e.id)
		};
	}
	function rangos(items: PayrollItem[], concepto: string): [string, string][] {
		const porAccion = new Map<number | null, [string, string]>();
		for (const i of items) {
			if (i.concept !== concepto || i.payer !== 'earning' || !i.applied_from || !i.applied_to) continue;
			const previo = porAccion.get(i.action_id);
			porAccion.set(i.action_id, previo ? [previo[0] < i.applied_from ? previo[0] : i.applied_from, previo[1] > i.applied_to ? previo[1] : i.applied_to] : [i.applied_from, i.applied_to]);
		}
		return [...porAccion.values()].sort();
	}
	function faltanDatos(lista: ReturnType<typeof trabajadores>['lista'], ins: boolean, empresa: [string, unknown][]) {
		const missing = lista.map(({ e, puesto, poliza }) => {
			const campos: string[] = [];
			if (e.identification_type !== 'national' && !e.insured_number) campos.push('insured_number');
			if (ins ? !puesto?.ins_code : !puesto?.ccss_code) campos.push(ins ? 'ins_code' : 'ccss_code');
			if (ins && !poliza) campos.push('policy');
			return { employee_id: e.id, fields: campos };
		}).filter((m) => m.fields.length);
		const company = empresa.filter(([, v]) => !v).map(([k]) => k);
		if (missing.length || company.length) fail(409, 'export_data_incomplete', { missing, company });
	}
	route('GET', '/payroll/exports/ccss', ({ query, userId, companyId }) => {
		admin(userId, companyId);
		const p = planilla(companyId);
		const anio = Number(query.get('year'));
		const mes = Number(query.get('month'));
		const { desde, hasta, lista } = trabajadores(p, anio, mes);
		faltanDatos(lista, false, [['employer_number', p.settings.employer_number]]);
		const periodoMes = (d: string) => d >= desde && d <= hasta;
		const rows = lista.map(({ e, items, puesto, jornada, nombre: n }) => {
			const movimientos: { kind: string; starts_on: string; ends_on: string | null; detail: string | null }[] = [];
			if (periodoMes(e.hired_on)) movimientos.push({ kind: 'inclusion', starts_on: e.hired_on, ends_on: null, detail: null });
			if (e.terminated_on && periodoMes(e.terminated_on)) movimientos.push({ kind: 'exclusion', starts_on: e.terminated_on, ends_on: null, detail: e.termination_cause });
			for (const [concepto, kind] of [['sick_leave_ccss', 'sick_leave_sem'], ['sick_leave_ins', 'sick_leave_ins'], ['maternity', 'maternity'], ['paid_leave', 'leave_paid'], ['unpaid_leave', 'leave_unpaid']] as const) {
				for (const [d, h] of rangos(items, concepto)) movimientos.push({ kind, starts_on: d, ends_on: h, detail: null });
			}
			for (const a of p.actions) {
				if (a.employee_id === e.id && a.kind === 'position_change' && periodoMes(a.starts_on) && a.cancels_action_id == null) movimientos.push({ kind: 'occupation_change', starts_on: a.starts_on, ends_on: null, detail: p.positions.find((x) => x.id === a.position_id)?.ccss_code ?? null });
			}
			movimientos.sort((a, b) => (a.starts_on < b.starts_on ? -1 : a.starts_on > b.starts_on ? 1 : a.kind.localeCompare(b.kind)));
			return {
				employee_id: e.id,
				identification: e.identification_type === 'national' ? e.identification.padStart(9, '0') : (e.insured_number ?? e.identification),
				insured_number: e.insured_number,
				full_name: n,
				ccss_code: puesto?.ccss_code ?? '',
				shift: jornada.hours_per_day <= 4 ? 'parcial' : ({ day: 'diurna', mixed: 'mixta', night: 'nocturna' }[jornada.shift] ?? 'diurna'),
				salary: baseDe(items, CONTRIBUTIVOS),
				days: round2(items.filter((i) => i.concept === 'base' && i.payer === 'earning').reduce((t, i) => t + (i.quantity ?? 0), 0)),
				movements: movimientos
			};
		});
		return { employer_number: p.settings.employer_number, period_from: desde, period_to: hasta, total_salary: round2(rows.reduce((t, r) => t + r.salary, 0)), rows };
	});
	route('GET', '/payroll/exports/income-tax', ({ query, userId, companyId }) => {
		admin(userId, companyId);
		const p = planilla(companyId);
		const { desde, hasta, lista } = trabajadores(p, Number(query.get('year')), Number(query.get('month')));
		const rows = lista.map(({ e, items, nombre: n }) => ({ employee_id: e.id, identification: e.identification, full_name: n, taxable: baseDe(items, GRAVABLES), withheld: round2(items.filter((i) => i.payer === 'employee' && i.concept === 'income_tax').reduce((t, i) => t + i.amount, 0)) }));
		return { period_from: desde, period_to: hasta, total_taxable: round2(rows.reduce((t, r) => t + r.taxable, 0)), total_withheld: round2(rows.reduce((t, r) => t + r.withheld, 0)), rows };
	});
	route('GET', '/payroll/exports/ins', ({ query, userId, companyId }) => {
		admin(userId, companyId);
		const p = planilla(companyId);
		const anio = Number(query.get('year'));
		const mes = Number(query.get('month'));
		const poliza = p.policies.find((x) => x.id === Number(query.get('policy')));
		if (!poliza) fail(404, 'policy_not_found', { policy_id: Number(query.get('policy')) });
		const empresa = getRoot().companies.find((c) => c.id === companyId);
		const negocio = ((getEmpresa(companyId).settings?.data as Record<string, any>)?.business ?? {}) as Record<string, any>;
		const { desde, hasta, lista } = trabajadores(p, anio, mes);
		const suyos = lista.filter((t) => t.poliza?.id === poliza.id);
		faltanDatos(suyos, true, [['identification', empresa?.identificacion], ['policy_number', poliza.number.replace(/\D/g, '') || null]]);
		const periodoMes = (d: string) => d >= desde && d <= hasta;
		const lineas = encabezadoIns({ identification_type: empresa?.identification_type ?? null, identification: empresa?.identificacion ?? null, phone: negocio.phone ?? null, email: negocio.email ?? null, address: negocio.address ?? null }, poliza.number, anio, mes);
		for (const { e, items, puesto, jornada } of suyos) {
			const dias = Math.min(31, Math.round(items.filter((i) => i.concept === 'base' && i.payer === 'earning').reduce((t, i) => t + (i.quantity ?? 0), 0)));
			const ingreso = periodoMes(e.hired_on);
			const salida = !!e.terminated_on && periodoMes(e.terminated_on);
			const observacion = ingreso && salida ? '05' : ingreso ? '01' : salida ? '02' : rangos(items, 'maternity').length ? '07' : rangos(items, 'sick_leave_ccss').length ? '03' : rangos(items, 'sick_leave_ins').length ? '04' : rangos(items, 'unpaid_leave').length ? '06' : '00';
			lineas.push(registroIns({ identification_type: e.identification_type, identification: e.identification, insured_number: e.insured_number, first_name: e.first_name, last_name_1: e.last_name_1, last_name_2: e.last_name_2, salario: baseDe(items, GRAVABLES), dias, horas: Math.round(dias * jornada.hours_per_day), jornada: jornada.hours_per_day >= 6 ? '01' : '02', observacion, ins_code: puesto?.ins_code ?? null }));
		}
		return { __file: { filename: nombreArchivoIns(poliza.number, anio, mes), content: lineas.join('\r\n') + '\r\n', content_type: 'text/plain; charset=iso-8859-1' } };
	});
}
