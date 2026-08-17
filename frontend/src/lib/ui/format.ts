/** Formateo de fechas y textos para la interfaz. Todo en es-CR. */

import { formatNumber } from '$lib/domain/money';

function toDate(value: string | Date | null | undefined): Date | null {
	if (!value) return null;
	const d = value instanceof Date ? value : new Date(value);
	return Number.isNaN(d.getTime()) ? null : d;
}

/** `15/08/2026` */
export function formatDate(value: string | Date | null | undefined): string {
	const d = toDate(value);
	if (!d) return '—';
	return new Intl.DateTimeFormat('es-CR', {
		day: '2-digit',
		month: '2-digit',
		year: 'numeric'
	}).format(d);
}

/** `15/08/2026 14:32` */
export function formatDateTime(value: string | Date | null | undefined): string {
	const d = toDate(value);
	if (!d) return '—';
	return new Intl.DateTimeFormat('es-CR', {
		day: '2-digit',
		month: '2-digit',
		year: 'numeric',
		hour: '2-digit',
		minute: '2-digit',
		hour12: false
	}).format(d);
}

/** `14:32:05` */
export function formatTime(value: string | Date | null | undefined): string {
	const d = toDate(value);
	if (!d) return '—';
	return new Intl.DateTimeFormat('es-CR', {
		hour: '2-digit',
		minute: '2-digit',
		second: '2-digit',
		hour12: false
	}).format(d);
}

/** `lun 15 ago` — etiquetas cortas para el eje del gráfico de ventas. */
export function formatDayLabel(value: string | Date | null | undefined): string {
	const d = toDate(value);
	if (!d) return '—';
	return new Intl.DateTimeFormat('es-CR', {
		weekday: 'short',
		day: 'numeric',
		month: 'short'
	}).format(d);
}

/** `hace 5 min`, `hace 2 h`. Para el listado de movimientos de caja. */
export function formatRelative(value: string | Date | null | undefined): string {
	const d = toDate(value);
	if (!d) return '—';
	const diffSeconds = Math.round((d.getTime() - Date.now()) / 1000);
	const abs = Math.abs(diffSeconds);
	const rtf = new Intl.RelativeTimeFormat('es-CR', { numeric: 'auto' });

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
