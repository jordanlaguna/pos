/**
 * La aritmética del modo simulado de planilla (F12, T-1214).
 *
 * Una versión compacta de `domain/payroll_calendar.py`, `payroll.py` y
 * `payroll_actions.py`: los cortes de las cuatro periodicidades, lo que vale un
 * día, las cargas sobre lo que cotiza, la renta del mes y el trazado del
 * archivo del INS. No sustituye al dominio del backend —que es el que se prueba
 * al céntimo— sino que le da al simulado cifras con la misma forma para que las
 * pantallas y las pruebas de punta a punta tengan algo real que mostrar.
 */

import { round2 } from '$lib/domain/money';
import type { PayrollItem } from '$lib/domain/payroll';
import { PAYROLL_SEED } from './payrollRates';

export interface Jornada {
	frequency: string;
	shift: string;
	hours_per_day: number;
	workdays_per_week: number;
	rest_day_paid: boolean;
	first_cut_day: number | null;
	cut_weekday: number | null;
	series_start: string | null;
}

export interface Periodo {
	desde: string;
	hasta: string;
}

// ------------------------------------------------------------------ fechas

export function fecha(iso: string): Date {
	const [y, m, d] = iso.slice(0, 10).split('-').map(Number);
	return new Date(Date.UTC(y, m - 1, d));
}

export function iso(d: Date): string {
	return d.toISOString().slice(0, 10);
}

export function sumarDias(dia: string, n: number): string {
	const d = fecha(dia);
	d.setUTCDate(d.getUTCDate() + n);
	return iso(d);
}

export function ultimoDiaDelMes(anio: number, mes: number): string {
	return iso(new Date(Date.UTC(anio, mes, 0)));
}

/** Días de calendario entre dos fechas, las dos incluidas. */
export function diasCalendario(desde: string, hasta: string): number {
	return Math.max(0, Math.round((fecha(hasta).getTime() - fecha(desde).getTime()) / 86_400_000) + 1);
}

export function mesDe(dia: string): string {
	return dia.slice(0, 7) + '-01';
}

// ---------------------------------------------------------------- calendario

export const FACTOR: Record<string, number> = {
	monthly: 1,
	semimonthly: 2,
	biweekly: 26 / 12,
	weekly: 52 / 12
};

export function diasPagados(j: Jornada): number {
	if (j.frequency === 'monthly') return 30;
	if (j.frequency === 'semimonthly') return 15;
	const porSemana = j.rest_day_paid ? 7 : 6;
	return porSemana * (j.frequency === 'biweekly' ? 2 : 1);
}

export function valorDia(salario: number, j: Jornada): number {
	return salario / diasPagados(j);
}

export function valorHora(salario: number, j: Jornada): number {
	return valorDia(salario, j) / (j.hours_per_day || 8);
}

function cortesQuincenales(primerCorte: number, anio: number, mes: number): [string, string] {
	const fin = ultimoDiaDelMes(anio, mes);
	const primero = `${anio}-${String(mes).padStart(2, '0')}-${String(primerCorte).padStart(2, '0')}`;
	if (primerCorte === 15) return [primero, fin];
	const diaFin = Number(fin.slice(8, 10));
	const segundo = `${anio}-${String(mes).padStart(2, '0')}-${String(Math.min(primerCorte + 15, diaFin)).padStart(2, '0')}`;
	return [primero, segundo];
}

function mesAnterior(anio: number, mes: number): [number, number] {
	return mes === 1 ? [anio - 1, 12] : [anio, mes - 1];
}

function mesSiguiente(anio: number, mes: number): [number, number] {
	return mes === 12 ? [anio + 1, 1] : [anio, mes + 1];
}

/** El periodo que cierra `corte`, o `null` si no es un corte de la jornada. */
export function periodoDe(j: Jornada, corte: string): Periodo | null {
	const anio = Number(corte.slice(0, 4));
	const mes = Number(corte.slice(5, 7));
	if (j.frequency === 'monthly') {
		return corte === ultimoDiaDelMes(anio, mes) ? { desde: corte.slice(0, 8) + '01', hasta: corte } : null;
	}
	if (j.frequency === 'semimonthly') {
		const dia = j.first_cut_day ?? 15;
		const [primero, segundo] = cortesQuincenales(dia, anio, mes);
		if (corte === segundo) return { desde: sumarDias(primero, 1), hasta: corte };
		if (corte === primero) {
			const [a, m] = mesAnterior(anio, mes);
			return { desde: sumarDias(cortesQuincenales(dia, a, m)[1], 1), hasta: corte };
		}
		return null;
	}
	if (j.frequency === 'biweekly') {
		const inicio = j.series_start ?? corte;
		const dias = diasCalendario(inicio, corte) - 1;
		if (dias < 13 || dias % 14 !== 13) return null;
		return { desde: sumarDias(corte, -13), hasta: corte };
	}
	// semanal: `getUTCDay` da 0 = domingo; el backend usa 0 = lunes.
	const lunesCero = (fecha(corte).getUTCDay() + 6) % 7;
	if (lunesCero !== (j.cut_weekday ?? 0)) return null;
	return { desde: sumarDias(corte, -6), hasta: corte };
}

/** El corte del periodo que contiene `dia`. */
export function corteDesde(j: Jornada, dia: string): string {
	const anio = Number(dia.slice(0, 4));
	const mes = Number(dia.slice(5, 7));
	if (j.frequency === 'monthly') return ultimoDiaDelMes(anio, mes);
	if (j.frequency === 'semimonthly') {
		const d = j.first_cut_day ?? 15;
		const [a2, m2] = mesSiguiente(anio, mes);
		const candidatos = [...cortesQuincenales(d, anio, mes), ...cortesQuincenales(d, a2, m2)];
		return candidatos.find((c) => c >= dia) ?? candidatos[3];
	}
	if (j.frequency === 'biweekly') {
		const inicio = j.series_start ?? dia;
		const transcurridos = diasCalendario(inicio, dia) - 1;
		return sumarDias(inicio, 14 * Math.floor(transcurridos / 14) + 13);
	}
	const lunesCero = (fecha(dia).getUTCDay() + 6) % 7;
	return sumarDias(dia, ((j.cut_weekday ?? 0) - lunesCero + 7) % 7);
}

export function siguienteCorte(j: Jornada, corte: string): string {
	return corteDesde(j, sumarDias(corte, 1));
}

/** Si la corrida es la última del mes: la que liquida la renta (RN-73). */
export function cierraMes(j: Jornada, corte: string): boolean {
	return siguienteCorte(j, corte).slice(0, 7) !== corte.slice(0, 7);
}

/** Los días que cuenta un tramo, en mes comercial para mensual y quincenal (RN-94). */
export function diasContados(j: Jornada, desde: string, hasta: string): number {
	let dias = diasCalendario(desde, hasta);
	if (j.frequency === 'monthly' || j.frequency === 'semimonthly') {
		let dia = desde;
		while (dia <= hasta) {
			const fin = ultimoDiaDelMes(Number(dia.slice(0, 4)), Number(dia.slice(5, 7)));
			if (fin <= hasta) dias += 30 - Number(fin.slice(8, 10));
			dia = sumarDias(fin, 1);
		}
	}
	return Math.max(0, Math.min(dias, diasPagados(j)));
}

// ------------------------------------------------------------------- tasas

export interface Tasa {
	concept: string;
	payer: string;
	value: number;
	valid_from: string;
	valid_to?: string | null;
}

function rige(fila: { valid_from: string; valid_to?: string | null }, dia: string): boolean {
	return fila.valid_from <= dia && (fila.valid_to == null || dia <= fila.valid_to);
}

/** De cada `pagador:concepto`, la fila más reciente que rige. */
export function tasasVigentes(todas: Tasa[], dia: string): Map<string, Tasa> {
	const elegidas = new Map<string, Tasa>();
	for (const fila of todas) {
		if (!rige(fila, dia)) continue;
		const clave = `${fila.payer}:${fila.concept}`;
		const antes = elegidas.get(clave);
		if (!antes || fila.valid_from > antes.valid_from) elegidas.set(clave, fila);
	}
	return elegidas;
}

export function regla(tasas: Map<string, Tasa>, concepto: string, porOmision = 0): number {
	return tasas.get(`rule:${concepto}`)?.value ?? porOmision;
}

export interface Tramo {
	lower: number;
	upper: number | null;
	rate: number;
}

export function tramosVigentes(dia: string): Tramo[] {
	const vigentes = PAYROLL_SEED.brackets.filter((b) => rige(b, dia));
	if (!vigentes.length) return [];
	const ultima = vigentes.map((b) => b.valid_from).sort().at(-1);
	return vigentes
		.filter((b) => b.valid_from === ultima)
		.map((b) => ({ lower: b.lower, upper: b.upper ?? null, rate: b.rate }))
		.sort((a, b) => a.lower - b.lower);
}

export function creditosVigentes(dia: string): { child: number; spouse: number } {
	const monto = (concepto: string) =>
		PAYROLL_SEED.credits
			.filter((c) => c.concept === concepto && rige(c, dia))
			.sort((a, b) => (a.valid_from < b.valid_from ? 1 : -1))[0]?.amount ?? 0;
	return { child: monto('child'), spouse: monto('spouse') };
}

/** Tramos marginales menos créditos, nunca negativo (RN-73). */
export function impuesto(mensual: number, tramos: Tramo[], credito: number): number {
	let total = 0;
	for (const t of tramos) {
		if (mensual <= t.lower) continue;
		const techo = t.upper == null ? mensual : Math.min(mensual, t.upper);
		total += (techo - t.lower) * t.rate;
	}
	return Math.max(0, round2(round2(total) - credito));
}

export function retencion(
	gravable: number,
	frequency: string,
	cierra: boolean,
	baseAntes: number,
	retenidoAntes: number,
	tramos: Tramo[],
	credito: number
): number {
	if (cierra) return round2(impuesto(baseAntes + gravable, tramos, credito) - retenidoAntes);
	return round2(impuesto(gravable * FACTOR[frequency], tramos, credito) / FACTOR[frequency]);
}

// ----------------------------------------------------------------- rubros

export const CONTRIBUTIVOS = new Set([
	'base',
	'overtime',
	'double_time',
	'bonus',
	'sick_leave_ccss',
	'sick_leave_ins',
	'unpaid_leave',
	'absence'
]);
export const GRAVABLES = new Set([...CONTRIBUTIVOS, 'maternity', 'maternity_pay']);

export function baseDe(items: PayrollItem[], conjunto: Set<string>): number {
	const suma = items
		.filter((i) => i.payer === 'earning' && conjunto.has(i.concept))
		.reduce((t, i) => t + i.amount, 0);
	return Math.max(0, round2(suma));
}

export function rubro(
	concept: string,
	payer: string,
	base: number,
	rate: number | null,
	amount: number,
	extra: Partial<PayrollItem> = {}
): PayrollItem {
	return {
		concept,
		payer,
		base: round2(base),
		rate,
		amount: round2(amount),
		action_id: null,
		quantity: null,
		applied_from: null,
		applied_to: null,
		...extra
	};
}

// ------------------------------------------------------------ el INS (V08D)

const ID_INS: Record<string, string> = { national: '0', dimex: '6', nite: '6', passport: '9', work_permit: '8' };
const PATRONO_INS: Record<string, string> = { '01': '0', '02': '2', '03': '6', '04': '6' };

function texto(valor: string | null | undefined, ancho: number): string {
	return (valor ?? '').toUpperCase().slice(0, ancho).padEnd(ancho);
}

function digitos(valor: string | null | undefined): string {
	return (valor ?? '').replace(/\D/g, '');
}

export function polizaIns(numero: string | null): string {
	return digitos(numero).slice(-7).padStart(7, '0');
}

export interface TrabajadorIns {
	identification_type: string;
	identification: string;
	insured_number: string | null;
	first_name: string;
	last_name_1: string;
	last_name_2: string | null;
	salario: number;
	dias: number;
	horas: number;
	jornada: string;
	observacion: string;
	ins_code: string | null;
}

export function registroIns(t: TrabajadorIns): string {
	const asegurado = t.identification_type === 'national' ? '' : (t.insured_number ?? '');
	return (
		(ID_INS[t.identification_type] ?? '0') +
		texto(t.identification.trim(), 19) +
		texto(asegurado, 20) +
		texto(t.first_name, 15) +
		texto(t.last_name_1, 15) +
		texto(t.last_name_2 || '...', 15) +
		Math.max(0, t.salario).toFixed(2).padStart(13, '0') +
		String(t.dias).padStart(3, '0') +
		String(t.horas).padStart(4, '0') +
		t.jornada +
		t.observacion +
		'0' +
		digitos(t.ins_code).padStart(4, '0').slice(-4)
	);
}

export function encabezadoIns(
	patrono: {
		identification_type: string | null;
		identification: string | null;
		phone: string | null;
		email: string | null;
		address: string | null;
	},
	poliza: string,
	anio: number,
	mes: number
): string[] {
	const tipo = PATRONO_INS[patrono.identification_type ?? ''] ?? '0';
	return [
		polizaIns(poliza) +
			'M' +
			String(anio).padStart(4, '0') +
			String(mes).padStart(2, '0') +
			' ' +
			texto(tipo + digitos(patrono.identification), 20) +
			digitos(patrono.phone).slice(-8).padStart(8, '0') +
			'00000000' +
			' V08D',
		'Email ' + (patrono.email ?? '').slice(0, 50).padEnd(50),
		'Domicilio ' + texto(patrono.address, 171)
	];
}

export function nombreArchivoIns(poliza: string, anio: number, mes: number): string {
	return `PL${polizaIns(poliza)}M${String(anio).padStart(4, '0')}${String(mes).padStart(2, '0')}-V08D (Texto).txt`;
}
