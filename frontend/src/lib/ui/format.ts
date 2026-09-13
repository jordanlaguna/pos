/**
 * Formateo de fechas y textos para la interfaz.
 *
 * **La fecha depende del idioma** (T-806): en español `15/08/2026`, en inglés
 * `08/15/2026`, y los meses cortos del eje del gráfico cambian de nombre. Sale
 * del idioma de la petición, el mismo que los mensajes, así que una pantalla no
 * puede quedar con los rótulos en un idioma y las fechas en otro.
 *
 * Cada función acepta un `locale` explícito, y eso no es un adorno: el documento
 * impreso se emite en el idioma de la compañía y no en el de la pantalla (RN-29,
 * T-811), así que las tres plantillas pasan el suyo.
 *
 * **La hora no depende del idioma, a propósito.** Se fuerza el reloj de 24 horas
 * en los tres: las horas de esta aplicación son de turnos de caja y movimientos
 * de efectivo, se leen en columna, y `2:05 PM` junto a `14:05` es una columna que
 * no se puede comparar de un vistazo. T-806 pide que dependan del locale «los
 * meses y el orden», que es lo que sí cambia.
 */

import { getLocale } from '$lib/paraglide/runtime.js';
import { formatNumber } from '$lib/domain/money';

/**
 * De idioma a etiqueta de Intl.
 *
 * Hace falta la región porque el idioma solo no dice el orden: `en` a secas se
 * resuelve como `en-US` en Node y como lo que sea en un navegador cualquiera, y
 * el orden de la fecha es justo lo que cambia entre `en-US` y `en-GB`. Fijarla
 * acá es lo que hace que la pantalla se vea igual en la caja y en el servidor.
 */
const INTL: Record<string, string> = {
	es: 'es-CR',
	en: 'en-US',
	pt: 'pt-BR'
};

/** La etiqueta de Intl del idioma pedido, o la del idioma de esta petición. */
function tag(locale?: string): string {
	const pedido = locale ?? getLocale();
	return INTL[pedido] ?? INTL.es;
}

/** `2026-09-10`: fecha de calendario, sin hora y por lo tanto sin huso. */
const SOLO_FECHA = /^\d{4}-\d{2}-\d{2}$/;

function toDate(value: string | Date | null | undefined): Date | null {
	if (!value) return null;

	/*
	 * Una fecha **sin hora** se interpreta como local y no como UTC.
	 *
	 * `new Date('2026-09-10')` devuelve medianoche UTC por especificación, así
	 * que al oeste de Greenwich se muestra el día anterior: en Costa Rica
	 * —UTC−6— una factura del 10 salía como «09/09/2026». No es un detalle de
	 * presentación: el vencimiento de una compra parecería caer un día antes y
	 * el de una suscripción también.
	 *
	 * Con hora no se toca: `2026-09-10T14:32:00` sí es un instante, y ahí
	 * convertir al huso del navegador es lo correcto.
	 */
	const d =
		value instanceof Date
			? value
			: new Date(SOLO_FECHA.test(value) ? `${value}T00:00:00` : value);
	return Number.isNaN(d.getTime()) ? null : d;
}

/** `15/08/2026` en español, `08/15/2026` en inglés. */
export function formatDate(value: string | Date | null | undefined, locale?: string): string {
	const d = toDate(value);
	if (!d) return '—';
	return new Intl.DateTimeFormat(tag(locale), {
		day: '2-digit',
		month: '2-digit',
		year: 'numeric'
	}).format(d);
}

/** `15/08/2026 14:32`. La hora va en 24 h en los tres idiomas. */
export function formatDateTime(value: string | Date | null | undefined, locale?: string): string {
	const d = toDate(value);
	if (!d) return '—';
	return new Intl.DateTimeFormat(tag(locale), {
		day: '2-digit',
		month: '2-digit',
		year: 'numeric',
		hour: '2-digit',
		minute: '2-digit',
		hour12: false
	}).format(d);
}

/** `14:32:05`. Igual en los tres: es una hora de turno, no de agenda. */
export function formatTime(value: string | Date | null | undefined, locale?: string): string {
	const d = toDate(value);
	if (!d) return '—';
	return new Intl.DateTimeFormat(tag(locale), {
		hour: '2-digit',
		minute: '2-digit',
		second: '2-digit',
		hour12: false
	}).format(d);
}

/** `lun 15 ago` / `Mon, Aug 15` — etiquetas cortas para el eje del gráfico. */
export function formatDayLabel(value: string | Date | null | undefined, locale?: string): string {
	const d = toDate(value);
	if (!d) return '—';
	return new Intl.DateTimeFormat(tag(locale), {
		weekday: 'short',
		day: 'numeric',
		month: 'short'
	}).format(d);
}

/** `hace 5 min`, `hace 2 h`. Para el listado de movimientos de caja. */
export function formatRelative(value: string | Date | null | undefined, locale?: string): string {
	const d = toDate(value);
	if (!d) return '—';
	const diffSeconds = Math.round((d.getTime() - Date.now()) / 1000);
	const abs = Math.abs(diffSeconds);
	const rtf = new Intl.RelativeTimeFormat(tag(locale), { numeric: 'auto' });

	if (abs < 60) return rtf.format(Math.round(diffSeconds), 'second');
	if (abs < 3600) return rtf.format(Math.round(diffSeconds / 60), 'minute');
	if (abs < 86400) return rtf.format(Math.round(diffSeconds / 3600), 'hour');
	return rtf.format(Math.round(diffSeconds / 86400), 'day');
}

/**
 * `1.234` — enteros con separador de miles.
 * El separador es el que configuró el negocio, igual que el de los montos: sería
 * raro leer «1.234 unidades» al lado de «$1,234.00».
 */
export function formatInt(value: number | null | undefined): string {
	return formatNumber(value, 0);
}

/** `+12,5 %` / `−8,1 %`. Devuelve null cuando no hay base con la cual comparar. */
export function formatDelta(current: number, previous: number): string | null {
	if (!previous) return null;
	const pct = ((current - previous) / Math.abs(previous)) * 100;
	if (!Number.isFinite(pct)) return null;
	const sign = pct >= 0 ? '+' : '−';
	const abs = Math.abs(pct);
	return `${sign}${formatNumber(abs, Number.isInteger(abs) ? 0 : 1)} %`;
}


/** `YYYY-MM-DD` en hora local — el formato que esperan los <input type="date">. */
export function toDateInput(value: Date | string | null | undefined): string {
	const d = toDate(value) ?? new Date();
	const pad = (n: number) => String(n).padStart(2, '0');
	return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** Nombre completo a partir de las tres partes que guarda el backend. */
export function fullName(
	parts: { name?: string | null; last_name?: string | null; second_name?: string | null } & {
		lastName?: string | null;
		secondName?: string | null;
	}
): string {
	return [
		parts.name,
		parts.last_name ?? parts.lastName,
		parts.second_name ?? parts.secondName
	]
		.filter((p) => p && String(p).trim())
		.join(' ')
		.trim();
}

/** Inicial(es) para los avatares del menú. */
export function initials(name: string): string {
	const parts = name.trim().split(/\s+/).filter(Boolean);
	if (!parts.length) return '?';
	if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
	return (parts[0][0] + parts[1][0]).toUpperCase();
}
