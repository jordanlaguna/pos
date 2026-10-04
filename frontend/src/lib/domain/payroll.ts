/**
 * Planilla (F12): los datos tal como viajan por el API y las listas cerradas.
 *
 * Los valores cerrados —periodicidad, clase de jornada, tipo de acción, causa
 * de la baja— van **en inglés y sin traducir**: son datos, y el backend los
 * revisa (`domain/payroll_*.py`). La pantalla les pone nombre con su catálogo
 * (`m.payroll_action_kind({ kind })`). Las listas de acá existen para armar los
 * desplegables en el mismo orden que el backend, no para validar: un valor que
 * el backend no admita vuelve con su código.
 */

export const FREQUENCIES = ['monthly', 'semimonthly', 'biweekly', 'weekly'] as const;
export type Frequency = (typeof FREQUENCIES)[number];

export const SHIFTS = ['day', 'mixed', 'night'] as const;
export const IDENTIFICATION_TYPES = ['national', 'dimex', 'nite', 'passport', 'work_permit'] as const;
export const GENDERS = ['F', 'M'] as const;
export const MARITAL_STATUSES = [
	'single',
	'married',
	'divorced',
	'widowed',
	'separated',
	'free_union',
	'unknown'
] as const;
export const TERMINATION_CAUSES = [
	'resignation',
	'dismissal_with_cause',
	'dismissal_without_cause',
	'mutual',
	'end_of_contract'
] as const;

/** Los dieciséis de RN-90, en los cuatro grupos del spec. */
export const EARNING_KINDS = ['overtime', 'double_time', 'bonus'] as const;
export const ABSENCE_KINDS = [
	'sick_leave_ccss',
	'sick_leave_ins',
	'maternity',
	'paid_leave',
	'unpaid_leave',
	'absence',
	'vacation'
] as const;
export const DEDUCTION_KINDS = ['deduction', 'child_support', 'garnishment'] as const;
export const CONTRACT_KINDS = ['raise', 'position_change'] as const;
/** Los que se registran desde la pantalla: la baja tiene su propio botón. */
export const REGISTRABLE_KINDS = [
	...EARNING_KINDS,
	...ABSENCE_KINDS,
	...DEDUCTION_KINDS,
	...CONTRACT_KINDS
] as const;
export type ActionKind = (typeof REGISTRABLE_KINDS)[number] | 'termination';

export const RUN_KINDS = ['regular', 'aguinaldo', 'settlement', 'adjustment'] as const;
export const RUN_STATUSES = ['draft', 'approved', 'paid'] as const;

/** Qué campos pide cada tipo de acción, para pintar solo esos (`check_action`). */
export interface ActionFields {
	endsOn: boolean;
	hours: boolean;
	days: boolean;
	amount: boolean;
	totalAmount: boolean;
	newSalary: boolean;
	position: boolean;
	recurring: boolean;
}

export function actionFields(kind: string): ActionFields {
	const rango = (ABSENCE_KINDS as readonly string[]).includes(kind);
	return {
		endsOn: rango,
		hours: kind === 'overtime' || kind === 'double_time',
		days: kind === 'vacation',
		amount: kind === 'bonus' || kind === 'deduction' || kind === 'child_support' || kind === 'garnishment',
		totalAmount: kind === 'deduction' || kind === 'child_support' || kind === 'garnishment',
		newSalary: kind === 'raise',
		position: kind === 'position_change',
		recurring: kind === 'deduction' || kind === 'child_support'
	};
}

export interface PayrollSettings {
	employer_number: string | null;
	ina_exempt: boolean;
}

export interface WorkSchedule {
	id: number;
	name: string;
	frequency: string;
	shift: string;
	hours_per_day: number;
	workdays_per_week: number;
	rest_day_paid: boolean;
	first_cut_day: number | null;
	cut_weekday: number | null;
	series_start: string | null;
	is_active: boolean;
}

export interface Position {
	id: number;
	name: string;
	ccss_code: string;
	ins_code: string;
	is_active: boolean;
}

export interface InsPolicy {
	id: number;
	number: string;
	rt_rate: number;
	is_default: boolean;
}

export interface EmploymentContract {
	id: number;
	employee_id: number;
	schedule_id: number;
	position_id: number;
	ins_policy_id: number | null;
	valid_from: string;
	valid_to: string | null;
	period_salary: number;
	solidarista_rate: number | null;
}

export interface Employee {
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
	contract: EmploymentContract | null;
}

/** El nombre como lo imprimen los archivos: nombre y los dos apellidos. */
export function employeeName(e: {
	first_name: string;
	last_name_1: string;
	last_name_2?: string | null;
}): string {
	return [e.first_name, e.last_name_1, e.last_name_2].filter(Boolean).join(' ');
}

export interface AppliedItem {
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
}

export interface PersonnelAction {
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
	cancelled_by: number | null;
	suspended_at: string | null;
	suspended_by: number | null;
	suspension_reason: string | null;
	source: string;
	created_by: number;
	created_at: string;
	applied: AppliedItem[];
	applied_total: number;
	balance: number | null;
}

export interface PayrollItem {
	concept: string;
	payer: string;
	base: number;
	rate: number | null;
	amount: number;
	action_id: number | null;
	quantity: number | null;
	applied_from: string | null;
	applied_to: string | null;
}

export interface PayrollLine {
	id: number;
	employee_id: number;
	employee_name: string;
	contract_id: number;
	gross: number;
	employee_deductions: number;
	income_tax: number;
	other_deductions: number;
	net: number;
	employer_charges: number;
	items: PayrollItem[];
}

export interface PayrollRun {
	id: number;
	kind: string;
	schedule_id: number | null;
	schedule_name: string | null;
	period_from: string;
	period_to: string;
	pay_date: string;
	status: string;
	adjusts_run_id: number | null;
	journal_entry_id: number | null;
	employees: number;
	gross: number;
	net: number;
	employer_charges: number;
	created_at: string;
	approved_at: string | null;
	paid_at: string | null;
}

export interface PayrollRunDetail extends PayrollRun {
	lines: PayrollLine[];
}

export interface PayslipItem extends PayrollItem {
	action_kind: string | null;
	action_memo: string | null;
}

export interface Payslip {
	run: {
		id: number;
		kind: string;
		period_from: string;
		period_to: string;
		pay_date: string;
		status: string;
		paid_at: string | null;
		adjusts_run_id: number | null;
	};
	employer_number: string | null;
	employee: {
		id: number;
		first_name: string;
		last_name_1: string;
		last_name_2: string | null;
		identification_type: string;
		identification: string;
		insured_number: string | null;
		hired_on: string;
		terminated_on: string | null;
		iban: string | null;
		position_name: string | null;
		schedule_name: string | null;
		frequency: string | null;
		period_salary: number | null;
	};
	line: {
		gross: number;
		employee_deductions: number;
		income_tax: number;
		other_deductions: number;
		net: number;
		employer_charges: number;
	};
	items: PayslipItem[];
}

export interface VacationMovement {
	id: number;
	kind: string;
	days: number;
	on_date: string;
	run_id: number | null;
	action_id: number | null;
}

export interface Vacations {
	employee_id: number;
	balance: number;
	movements: VacationMovement[];
}

export interface PayrollRate {
	concept: string;
	payer: string;
	value: number;
	valid_from: string;
	valid_to: string | null;
	source: string;
	verified_at: string;
	stale: boolean;
}

export interface PayrollRates {
	on: string;
	country: string;
	rates: PayrollRate[];
	brackets: { lower: number; upper: number | null; rate: number; valid_from: string; source: string; verified_at: string }[];
	credits: { concept: string; amount: number; valid_from: string; source: string }[];
	severance: { years_from: number; years_to: number | null; days: number; source: string }[];
	missing: string[];
	stale: boolean;
}

export interface CcssMovement {
	kind: string;
	starts_on: string;
	ends_on: string | null;
	detail: string | null;
}

export interface CcssRow {
	employee_id: number;
	identification: string;
	insured_number: string | null;
	full_name: string;
	ccss_code: string;
	shift: string;
	salary: number;
	days: number;
	movements: CcssMovement[];
}

export interface CcssReport {
	employer_number: string;
	period_from: string;
	period_to: string;
	total_salary: number;
	rows: CcssRow[];
}

export interface IncomeTaxReport {
	period_from: string;
	period_to: string;
	total_taxable: number;
	total_withheld: number;
	rows: { employee_id: number; identification: string; full_name: string; taxable: number; withheld: number }[];
}

export interface ImportRowError {
	sheet: string;
	row: number;
	code: string;
	field: string | null;
	reason: string | null;
}

export interface ImportResult {
	dry_run: boolean;
	ok: boolean;
	errors: ImportRowError[];
	positions: number;
	employees: number;
	earnings: number;
	deductions: number;
}

/** Los rubros de una línea, en el orden en que la boleta los lista. */
export function itemsByPayer<T extends { payer: string }>(items: T[]) {
	return {
		earnings: items.filter((i) => i.payer === 'earning'),
		deductions: items.filter((i) => i.payer === 'employee'),
		employer: items.filter((i) => i.payer === 'employer')
	};
}
