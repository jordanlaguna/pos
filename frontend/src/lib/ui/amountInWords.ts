/**
 * El monto en letras del comprobante (T-731): «DOSCIENTOS SESENTA Y CUATRO MIL
 * CUATROCIENTOS VEINTE CON 00/100 COLONES».
 *
 * Es texto para una persona y por eso vive en la interfaz y no en el dominio
 * (RN-30). Las palabras de los números no pueden ir al catálogo —son reglas, no
 * frases: el «veintiún» de «veintiún mil», el «cien» que es «ciento» cuando le
 * sigue algo, la «e» portuguesa antes del último grupo—; lo que sí va al
 * catálogo es la forma de la frase, con su «con» o su «and».
 *
 * En mayúsculas, como se escribe en un cheque o una factura: es la forma que no
 * se puede alterar agregando un trazo.
 *
 * Hasta 999 999 999 999. Más allá devuelve `null` y el documento no la imprime:
 * la columna del total no llega ni a cien millones, así que es un límite que no
 * se toca, y una frase a medias sería peor que ninguna.
 */

import { m } from '$lib/paraglide/messages.js';
import { baseLocale, isLocale, type Locale } from '$lib/paraglide/runtime.js';

const LIMITE = 1e12;

// ------------------------------------------------------------------- español

const ES_UNIDADES = [
	'', 'UNO', 'DOS', 'TRES', 'CUATRO', 'CINCO', 'SEIS', 'SIETE', 'OCHO', 'NUEVE',
	'DIEZ', 'ONCE', 'DOCE', 'TRECE', 'CATORCE', 'QUINCE', 'DIECISÉIS', 'DIECISIETE',
	'DIECIOCHO', 'DIECINUEVE', 'VEINTE', 'VEINTIUNO', 'VEINTIDÓS', 'VEINTITRÉS',
	'VEINTICUATRO', 'VEINTICINCO', 'VEINTISÉIS', 'VEINTISIETE', 'VEINTIOCHO', 'VEINTINUEVE'
];
const ES_DECENAS = ['', '', '', 'TREINTA', 'CUARENTA', 'CINCUENTA', 'SESENTA', 'SETENTA', 'OCHENTA', 'NOVENTA'];
const ES_CENTENAS = [
	'', 'CIENTO', 'DOSCIENTOS', 'TRESCIENTOS', 'CUATROCIENTOS', 'QUINIENTOS',
	'SEISCIENTOS', 'SETECIENTOS', 'OCHOCIENTOS', 'NOVECIENTOS'
];

/**
 * De 1 a 999. `apocope` es para cuando lo que sigue es «mil» o «millones»: ahí
 * el uno se apocopa —«veintiún mil», «treinta y un millones»—.
 */
function es999(n: number, apocope: boolean): string {
	if (n === 100) return 'CIEN';
	const partes: string[] = [];
	const centenas = Math.floor(n / 100);
	const resto = n % 100;
	if (centenas) partes.push(ES_CENTENAS[centenas]);
	if (resto) {
		if (resto < 30) {
			partes.push(apocope && resto === 1 ? 'UN' : apocope && resto === 21 ? 'VEINTIÚN' : ES_UNIDADES[resto]);
		} else {
			const unidad = resto % 10;
			const decena = ES_DECENAS[Math.floor(resto / 10)];
			partes.push(unidad ? `${decena} Y ${apocope && unidad === 1 ? 'UN' : ES_UNIDADES[unidad]}` : decena);
		}
	}
	return partes.join(' ');
}

function es(n: number, apocope: boolean): string {
	if (n >= 1e6) {
		const millones = Math.floor(n / 1e6);
		const resto = n % 1e6;
		const cabeza = millones === 1 ? 'UN MILLÓN' : `${es(millones, true)} MILLONES`;
		return resto ? `${cabeza} ${es(resto, apocope)}` : cabeza;
	}
	if (n >= 1000) {
		const miles = Math.floor(n / 1000);
		const resto = n % 1000;
		const cabeza = miles === 1 ? 'MIL' : `${es999(miles, true)} MIL`;
		return resto ? `${cabeza} ${es999(resto, apocope)}` : cabeza;
	}
	return es999(n, apocope);
}

// ------------------------------------------------------------------- inglés

const EN_UNIDADES = [
	'', 'ONE', 'TWO', 'THREE', 'FOUR', 'FIVE', 'SIX', 'SEVEN', 'EIGHT', 'NINE', 'TEN',
	'ELEVEN', 'TWELVE', 'THIRTEEN', 'FOURTEEN', 'FIFTEEN', 'SIXTEEN', 'SEVENTEEN',
	'EIGHTEEN', 'NINETEEN'
];
const EN_DECENAS = ['', '', 'TWENTY', 'THIRTY', 'FORTY', 'FIFTY', 'SIXTY', 'SEVENTY', 'EIGHTY', 'NINETY'];

function en999(n: number): string {
	const partes: string[] = [];
	const centenas = Math.floor(n / 100);
	const resto = n % 100;
	if (centenas) partes.push(`${EN_UNIDADES[centenas]} HUNDRED`);
	if (resto) {
		const unidad = resto % 10;
		partes.push(
			resto < 20
				? EN_UNIDADES[resto]
				: unidad
					? `${EN_DECENAS[Math.floor(resto / 10)]}-${EN_UNIDADES[unidad]}`
					: EN_DECENAS[Math.floor(resto / 10)]
		);
	}
	return partes.join(' ');
}

function en(n: number): string {
	const partes: string[] = [];
	for (const [valor, nombre] of [
		[1e9, 'BILLION'],
		[1e6, 'MILLION'],
		[1e3, 'THOUSAND']
	] as const) {
		if (n >= valor) {
			partes.push(`${en999(Math.floor(n / valor))} ${nombre}`);
			n %= valor;
		}
	}
	if (n) partes.push(en999(n));
	return partes.join(' ');
}

// ---------------------------------------------------------------- portugués

const PT_UNIDADES = [
	'', 'UM', 'DOIS', 'TRÊS', 'QUATRO', 'CINCO', 'SEIS', 'SETE', 'OITO', 'NOVE', 'DEZ',
	'ONZE', 'DOZE', 'TREZE', 'CATORZE', 'QUINZE', 'DEZESSEIS', 'DEZESSETE', 'DEZOITO',
	'DEZENOVE'
];
const PT_DECENAS = ['', '', 'VINTE', 'TRINTA', 'QUARENTA', 'CINQUENTA', 'SESSENTA', 'SETENTA', 'OITENTA', 'NOVENTA'];
const PT_CENTENAS = [
	'', 'CENTO', 'DUZENTOS', 'TREZENTOS', 'QUATROCENTOS', 'QUINHENTOS', 'SEISCENTOS',
	'SETECENTOS', 'OITOCENTOS', 'NOVECENTOS'
];

function pt999(n: number): string {
	if (n === 100) return 'CEM';
	const partes: string[] = [];
	const centenas = Math.floor(n / 100);
	const resto = n % 100;
	if (centenas) partes.push(PT_CENTENAS[centenas]);
	if (resto) {
		const unidad = resto % 10;
		partes.push(
			resto < 20
				? PT_UNIDADES[resto]
				: unidad
					? `${PT_DECENAS[Math.floor(resto / 10)]} E ${PT_UNIDADES[unidad]}`
					: PT_DECENAS[Math.floor(resto / 10)]
		);
	}
	// En portugués la «e» va también entre centena y decena: «duzentos e vinte».
	return partes.join(' E ');
}

function pt(n: number): string {
	const grupos: { valor: number; texto: string }[] = [];
	for (const [valor, uno, varios] of [
		[1e9, 'UM BILHÃO', 'BILHÕES'],
		[1e6, 'UM MILHÃO', 'MILHÕES'],
		[1e3, 'MIL', 'MIL']
	] as const) {
		if (n >= valor) {
			const cuantos = Math.floor(n / valor);
			grupos.push({ valor: cuantos, texto: cuantos === 1 ? uno : `${pt999(cuantos)} ${varios}` });
			n %= valor;
		}
	}
	if (n) grupos.push({ valor: n, texto: pt999(n) });

	// La «e» va antes del último grupo cuando es menor que cien o una centena
	// redonda: «mil e cem», «dois milhões e quinhentos mil», pero «mil duzentos
	// e trinta».
	return grupos
		.map((grupo, i) => {
			if (i === 0) return grupo.texto;
			const ultimo = i === grupos.length - 1;
			const conE = ultimo && (grupo.valor < 100 || grupo.valor % 100 === 0);
			return `${conE ? 'E ' : ''}${grupo.texto}`;
		})
		.join(' ');
}

// ------------------------------------------------------------------ monedas

/**
 * El nombre de la moneda, en plural y en mayúsculas, por idioma.
 *
 * Solo las de `CURRENCIES`. Una moneda escrita a mano en Configuración sale con
 * su código, que es mejor que un nombre inventado.
 */
const MONEDAS: Record<Locale, Record<string, string>> = {
	es: {
		CRC: 'COLONES', USD: 'DÓLARES', EUR: 'EUROS', MXN: 'PESOS', GTQ: 'QUETZALES',
		HNL: 'LEMPIRAS', NIO: 'CÓRDOBAS', PAB: 'BALBOAS', DOP: 'PESOS', COP: 'PESOS',
		PEN: 'SOLES', CLP: 'PESOS', ARS: 'PESOS'
	},
	en: {
		CRC: 'COLONES', USD: 'DOLLARS', EUR: 'EUROS', MXN: 'PESOS', GTQ: 'QUETZALES',
		HNL: 'LEMPIRAS', NIO: 'CÓRDOBAS', PAB: 'BALBOAS', DOP: 'PESOS', COP: 'PESOS',
		PEN: 'SOLES', CLP: 'PESOS', ARS: 'PESOS'
	},
	pt: {
		CRC: 'COLONES', USD: 'DÓLARES', EUR: 'EUROS', MXN: 'PESOS', GTQ: 'QUETZALES',
		HNL: 'LEMPIRAS', NIO: 'CÓRDOBAS', PAB: 'BALBOAS', DOP: 'PESOS', COP: 'PESOS',
		PEN: 'SOLES', CLP: 'PESOS', ARS: 'PESOS'
	}
};

const ENTERO: Record<Locale, (n: number) => string> = {
	es: (n) => es(n, false),
	en,
	pt
};

const CERO: Record<Locale, string> = { es: 'CERO', en: 'ZERO', pt: 'ZERO' };

/**
 * El monto en letras, en el idioma del documento (RN-29), o `null` si no cabe.
 *
 * `decimals` es el de la moneda configurada: con cero —el peso colombiano, el
 * chileno— no hay «con 00/100», porque no hay céntimos que nombrar.
 */
export function amountInWords(
	amount: number,
	opts: { locale: string; currency: string; decimals: number }
): string | null {
	const locale: Locale = isLocale(opts.locale) ? opts.locale : baseLocale;
	if (!Number.isFinite(amount)) return null;
	const centimos = Math.round(Math.abs(amount) * 100);
	// Sin decimales se redondea al entero, como lo muestra `formatMoney`; con
	// ellos, el entero es lo que queda antes de los céntimos.
	const entero = opts.decimals === 0 ? Math.round(centimos / 100) : Math.floor(centimos / 100);
	if (entero >= LIMITE) return null;

	const integer = entero === 0 ? CERO[locale] : ENTERO[locale](entero);
	const currency = MONEDAS[locale][opts.currency] ?? opts.currency;
	const o = { locale } as const;
	if (opts.decimals === 0) return m.doc_amount_in_words_whole({ integer, currency }, o);
	const cents = String(centimos % 100).padStart(2, '0');
	return m.doc_amount_in_words({ integer, cents, currency }, o);
}
