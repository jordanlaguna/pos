/**
 * Aritmética monetaria del POS.
 *
 * WinForms usaba `decimal`, que es exacto en base 10. JavaScript solo tiene
 * `number` (binario), así que 0.1 + 0.2 !== 0.3 y un carrito largo acumula
 * centavos fantasma. Todas las operaciones redondean a 2 decimales en cada
 * paso, igual que hacía el original al escribir `.ToString("0.00")` en la grilla.
 *
 * La moneda y el impuesto ya no están fijos: los configura el dueño del negocio
 * (ver `$lib/settings.ts`). Este módulo guarda la configuración vigente para no
 * tener que pasarla por parámetro en cada una de las cien llamadas a
 * `formatMoney` que hay repartidas por la interfaz.
 *
 * Ese estado de módulo es compartido —en el servidor lo ven todas las peticiones
 * a la vez— y eso es correcto acá y solo acá: VentaSys atiende UN negocio, con
 * UNA moneda. El día que atienda varios, esto se convierte en un contexto por
 * petición. Mientras tanto, la alternativa (encadenar la moneda por cada
 * componente) solo agregaría ruido.
 *
 * Lo que NO usa este estado es el cálculo: `computeTotals` recibe la tasa por
 * parámetro. La plata se calcula en el servidor, dentro de un `load`, y ahí
 * todavía no corrió ningún componente que haya configurado nada.
 */

import type { CurrencySettings, TaxSettings } from './settings';

/** IVA de Costa Rica: el que traía fijo el WinForms y el que se usa si nadie configura otro. */
export const DEFAULT_TAX_RATE = 0.13;

const DEFAULT_CURRENCY: CurrencySettings = {
	codigo: 'CRC',
	simbolo: '₡',
	decimales: 2,
	separador_miles: '.',
	separador_decimal: ',',
	simbolo_al_final: false,
	espacio: false
};

let currency: CurrencySettings = { ...DEFAULT_CURRENCY };
let tax: TaxSettings = { nombre: 'IVA', tasa: DEFAULT_TAX_RATE };

/**
 * Fija la moneda y el impuesto con los que se va a mostrar todo.
 *
 * Lo llama el layout de la aplicación, cuyo script corre antes de que se
 * renderice cualquier hijo, tanto en el servidor como al hidratar.
 */
export function configureMoney(config: { moneda: CurrencySettings; impuesto: TaxSettings }): void {
	currency = { ...config.moneda };
	tax = { ...config.impuesto };
}

/** Moneda vigente. Para quien necesite el símbolo suelto (etiquetas de campos). */
export function currencySettings(): CurrencySettings {
	return currency;
}

/** Tasa vigente. Para mostrar; para calcular se pasa explícita. */
export function taxRate(): number {
	return tax.tasa;
}

export function taxName(): string {
	return tax.nombre;
}

/** `IVA (13 %)` — el encabezado que se repite en tickets, carrito y devoluciones. */
export function taxLabel(): string {
	const pct = tax.tasa * 100;
	// Sin decimales cuando es redondo (13 %), con uno cuando no (4,5 %).
	const text = Number.isInteger(pct) ? String(pct) : formatNumber(pct, 1);
	return `${tax.nombre} (${text} %)`;
}

/** Redondeo a 2 decimales, medio hacia arriba, inmune al épsilon binario. */
export function round2(value: number): number {
	if (!Number.isFinite(value)) return 0;
	return Math.round((value + Number.EPSILON) * 100) / 100;
}

export function lineTotal(price: number, quantity: number): number {
	return round2(price * quantity);
}

export interface Totals {
	subtotal: number;
	tax: number;
	total: number;
}

/**
 * Subtotal → impuesto → total, en el mismo orden que `CalculateTotalNew()` del
 * original. La tasa se pasa siempre desde quien conoce la configuración.
 */
export function computeTotals(
	lines: { price: number; quantity: number }[],
	taxRateValue: number = DEFAULT_TAX_RATE
): Totals {
	const subtotal = round2(lines.reduce((acc, l) => acc + lineTotal(l.price, l.quantity), 0));
	const taxAmount = round2(subtotal * taxRateValue);
	return { subtotal, tax: taxAmount, total: round2(subtotal + taxAmount) };
}

/** Vuelto. Nunca negativo: un pago insuficiente se bloquea antes de llegar aquí. */
export function changeDue(cashReceived: number, total: number): number {
	return Math.max(0, round2(cashReceived - total));
}

// ------------------------------------------------------------------- formato

const MINUS = '−'; // U+2212, no el guion del teclado: alinea con las cifras.

/**
 * Cifra con separadores, sin símbolo.
 *
 * No usa `Intl.NumberFormat` a propósito. CLDR le asigna a es-CR el espacio duro
 * como separador de miles (`3 175 119,20`) y en el comercio costarricense se
 * escribe con punto; la versión anterior de este archivo arreglaba eso con un
 * `replace` sobre la salida de Intl, que era frágil y solo servía para una
 * moneda. Ahora los separadores son configurables y componerlos a mano es más
 * corto que pelear con la biblioteca.
 */
export function formatNumber(value: number | null | undefined, decimals?: number): string {
	const n = typeof value === 'number' && Number.isFinite(value) ? value : 0;
	const places = decimals ?? currency.decimales;
	const fixed = Math.abs(n).toFixed(places);
	const [whole, fraction] = fixed.split('.');

	const grouped = currency.separador_miles
		? whole.replace(/\B(?=(\d{3})+(?!\d))/g, currency.separador_miles)
		: whole;

	const sign = n < 0 ? MINUS : '';
	return fraction ? `${sign}${grouped}${currency.separador_decimal}${fraction}` : `${sign}${grouped}`;
}

/** Antepone o pospone el símbolo según la convención de la moneda configurada. */
function withSymbol(text: string): string {
	// Espacio duro: el símbolo y la cifra nunca se parten en dos renglones.
	const gap = currency.espacio ? ' ' : '';
	return currency.simbolo_al_final
		? `${text}${gap}${currency.simbolo}`
		: `${currency.simbolo}${gap}${text}`;
}

/** `₡3.175.119,20` con la moneda configurada. */
export function formatMoney(value: number | null | undefined): string {
	const n = typeof value === 'number' && Number.isFinite(value) ? value : 0;
	// El signo va antes del símbolo: −₡1.450,00, no ₡−1.450,00.
	const body = withSymbol(formatNumber(Math.abs(n)));
	return n < 0 ? `${MINUS}${body}` : body;
}

/** Igual que formatMoney pero sin símbolo, para columnas numéricas y tickets. */
export function formatAmount(value: number | null | undefined): string {
	return formatNumber(value);
}

/**
 * Monto abreviado para ejes y etiquetas donde no cabe la cifra completa:
 * `₡1,2 M`, `₡845 k`. Nunca para importes que el cajero deba cuadrar.
 */
export function formatCompact(value: number | null | undefined): string {
	const n = typeof value === 'number' && Number.isFinite(value) ? value : 0;
	const abs = Math.abs(n);
	const sign = n < 0 ? MINUS : '';

	if (abs >= 1_000_000) return `${sign}${withSymbol(formatNumber(abs / 1_000_000, 1))} M`;
	if (abs >= 1_000) return `${sign}${withSymbol(formatNumber(abs / 1_000, 0))} k`;
	return `${sign}${withSymbol(formatNumber(abs, 0))}`;
}

/**
 * Lee un monto escrito por el cajero. Acepta `1.234,56`, `1234.56`, `₡1 234`.
 * Devuelve null si no hay un número interpretable — el llamador decide qué hacer.
 *
 * Deliberadamente no usa los separadores configurados: quien escribe en el campo
 * de efectivo teclea como le sale, y adivinar por la forma del número acierta
 * más que exigir la convención configurada.
 */
export function parseAmount(input: string | number | null | undefined): number | null {
	if (typeof input === 'number') return Number.isFinite(input) ? round2(input) : null;
	if (input == null) return null;

	let s = String(input).trim();
	if (!s) return null;
	// Fuera todo lo que no sea dígito, coma, punto o signo: símbolos de moneda,
	// espacios normales y duros.
	s = s.replace(/[^\d,.\-−]/g, '').replace(/[−]/g, '-');
	if (!s) return null;

	const lastComma = s.lastIndexOf(',');
	const lastDot = s.lastIndexOf('.');

	if (lastComma > -1 && lastDot > -1) {
		// El separador decimal es el que aparece de último: "1.234,56" vs "1,234.56".
		if (lastComma > lastDot) s = s.replace(/\./g, '').replace(',', '.');
		else s = s.replace(/,/g, '');
	} else if (lastComma > -1) {
		// Una sola coma: decimal si deja 1-2 dígitos ("12,50"), miles si deja 3 ("1,234").
		s = s.length - lastComma - 1 <= 2 ? s.replace(',', '.') : s.replace(/,/g, '');
	} else if (lastDot > -1 && s.length - lastDot - 1 === 3 && s.split('.').length > 2) {
		// "1.234.567" — todos los puntos son separadores de miles.
		s = s.replace(/\./g, '');
	}

	const n = Number(s);
	return Number.isFinite(n) ? round2(n) : null;
}
