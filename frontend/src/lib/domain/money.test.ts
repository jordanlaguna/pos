import { beforeEach, describe, expect, it } from 'vitest';
import {
	DEFAULT_TAX_RATE,
	changeDue,
	computeTotals,
	configureMoney,
	currencySettings,
	formatAmount,
	formatCompact,
	formatMoney,
	formatNumber,
	lineTax,
	lineTotal,
	parseAmount,
	rateFromPercent,
	ratePercentText,
	round2,
	taxLabel,
	taxName,
	taxRate
} from './money';
import { CURRENCIES, type CurrencySettings } from './settings';

const CRC = CURRENCIES[0];
const USD = CURRENCIES[1];
const EUR = CURRENCIES[2]; // símbolo al final y con espacio
const COP = CURRENCIES[9]; // sin decimales

const IVA = { name: 'IVA', rate: 0.13 };

/** El módulo guarda la moneda vigente; cada prueba arranca con la de fábrica. */
function usar(currency: CurrencySettings, tax = IVA) {
	configureMoney({ currency, tax });
}

beforeEach(() => usar(CRC));

// ---------------------------------------------------------------- invariantes
//
// Estas cifras están en .specify/progress.json → invariantes_verificados. Se
// verificaron a mano contra el sistema corriendo; acá dejan de depender de que
// alguien se acuerde de repetirlo.

describe('invariantes de progress.json', () => {
	it('venta de 3 × 1450 da 4 915,50 y vuelve 84,50 de 5 000', () => {
		const t = computeTotals([{ price: 1450, quantity: 3 }], 0.13);
		expect(t).toEqual({
			subtotal: 4350,
			tax: 565.5,
			total: 4915.5,
			byRate: [{ rate: 0.13, base: 4350, tax: 565.5 }]
		});
		expect(changeDue(5000, t.total)).toBe(84.5);
	});

	it('arroz 1450 + café 4250 da 6 441,00 y vuelve 3 559,00 de 10 000', () => {
		const t = computeTotals(
			[
				{ price: 1450, quantity: 1 },
				{ price: 4250, quantity: 1 }
			],
			0.13
		);
		expect(t).toEqual({
			subtotal: 5700,
			tax: 741,
			total: 6441,
			byRate: [{ rate: 0.13, base: 5700, tax: 741 }]
		});
		expect(changeDue(10000, t.total)).toBe(3559);
	});

	it('factura de ejemplo: arroz + té + chiverre da 5 796,90', () => {
		const t = computeTotals(
			[
				{ price: 1450, quantity: 1 },
				{ price: 950, quantity: 1 },
				{ price: 2730, quantity: 1 }
			],
			0.13
		);
		expect(t).toEqual({
			subtotal: 5130,
			tax: 666.9,
			total: 5796.9,
			byRate: [{ rate: 0.13, base: 5130, tax: 666.9 }]
		});
		expect(changeDue(6000, t.total)).toBe(203.1);
	});

	it('devolución de una unidad de 1450 reembolsa 1 638,50', () => {
		expect(computeTotals([{ price: 1450, quantity: 1 }], 0.13).total).toBe(1638.5);
	});

	it('formato en colones', () => {
		expect(formatMoney(1450)).toBe('₡1.450,00');
		expect(formatMoney(3175119.2)).toBe('₡3.175.119,20');
		expect(formatMoney(-277)).toBe('−₡277,00');
	});

	it('formato en dólares: cambian símbolo y separadores a la vez', () => {
		usar(USD);
		expect(formatMoney(1450)).toBe('$1,450.00');
		expect(formatMoney(3175119.2)).toBe('$3,175,119.20');
		expect(formatMoney(-277)).toBe('−$277.00');
	});
});

// -------------------------------------------------------------- redondeo base

describe('round2', () => {
	it('redondea a dos decimales, medio hacia arriba', () => {
		expect(round2(1.005)).toBe(1.01);
		expect(round2(2.675)).toBe(2.68);
		expect(round2(2.665)).toBe(2.67);
		expect(round2(0.125)).toBe(0.13);
		expect(round2(1450)).toBe(1450);
	});

	it('el empate se aleja del cero, también en los negativos', () => {
		/*
		 * `Math.round(-0.5)` da −0 porque redondea hacia +∞, así que la versión
		 * anterior devolvía −1,00 para −1,005 mientras el servidor decía −1,01.
		 * Desde T-108b el servidor **verifica** los totales, así que un céntimo
		 * de desacuerdo entre los dos redondeos sería una venta rechazada.
		 */
		expect(round2(-1.005)).toBe(-1.01);
		expect(round2(-2.665)).toBe(-2.67);
		expect(round2(-2.675)).toBe(-2.68);
		expect(round2(-277.005)).toBe(-277.01);
	});

	it('el mismo modo que `ROUNDING` en backend/app/domain/money.py', () => {
		// ROUND_HALF_UP: si uno de los dos cambia y el otro no, el servidor
		// empieza a rechazar ventas buenas.
		const casos: [number, number][] = [
			[2.665, 2.67],
			[2.675, 2.68],
			[1.005, 1.01],
			[0.125, 0.13],
			[-2.665, -2.67],
			[-1.005, -1.01]
		];
		for (const [entrada, esperado] of casos) expect(round2(entrada)).toBe(esperado);
	});

	it('el ajuste escala con la magnitud', () => {
		// Un épsilon fijo es insignificante en cifras grandes: no movería nada
		// en 1450,555 y el empate se resolvería hacia abajo.
		expect(round2(1450.555)).toBe(1450.56);
		expect(round2(99999.995)).toBe(100000);
	});

	it('sobrevive al épsilon binario que rompía al original', () => {
		expect(round2(0.1 + 0.2)).toBe(0.3);
	});

	it('lo que no es un número finito vale cero', () => {
		expect(round2(Number.NaN)).toBe(0);
		expect(round2(Number.POSITIVE_INFINITY)).toBe(0);
	});
});

describe('lineTotal', () => {
	it('multiplica y redondea en el mismo paso', () => {
		expect(lineTotal(1450, 3)).toBe(4350);
		expect(lineTotal(0.1, 3)).toBe(0.3);
	});
});

describe('computeTotals', () => {
	it('sin líneas da todo en cero', () => {
		expect(computeTotals([], 0.13)).toEqual({ subtotal: 0, tax: 0, total: 0, byRate: [] });
	});

	it('sin tasa explícita usa la de Costa Rica', () => {
		expect(DEFAULT_TAX_RATE).toBe(0.13);
		expect(computeTotals([{ price: 1000, quantity: 1 }])).toEqual({
			subtotal: 1000,
			tax: 130,
			total: 1130,
			byRate: [{ rate: 0.13, base: 1000, tax: 130 }]
		});
	});

	it('con tasa cero el total es el subtotal', () => {
		expect(computeTotals([{ price: 1450, quantity: 2 }], 0)).toEqual({
			subtotal: 2900,
			tax: 0,
			total: 2900,
			byRate: [{ rate: 0, base: 2900, tax: 0 }]
		});
	});

	it('redondea línea por línea, no al final', () => {
		// 3 × 0,335 = 1,005 → 1,01 por línea. Sumar sin redondear daría 1,00.
		expect(computeTotals([{ price: 0.335, quantity: 3 }], 0).subtotal).toBe(1.01);
	});
});

describe('computeTotals con tarifa por línea (F5, RN-10)', () => {
	const IVA = 0.13;
	const MEDICAMENTO = 0.02;

	it('la tarifa de la línea manda sobre la del documento', () => {
		expect(computeTotals([{ price: 1000, quantity: 1, taxRate: 0 }], IVA).tax).toBe(0);
		expect(computeTotals([{ price: 1000, quantity: 1 }], IVA).tax).toBe(130);
	});

	it('una línea sin tarifa toma la del documento, que es RN-9', () => {
		// `null` y `undefined` significan lo mismo: el backend manda null y el
		// carrito puede no traer el campo.
		expect(computeTotals([{ price: 1000, quantity: 1, taxRate: null }], IVA).tax).toBe(130);
	});

	it('el caso del spec: medicamento al 2 % y arroz al 13 %', () => {
		const t = computeTotals(
			[
				{ price: 1000, quantity: 1, taxRate: MEDICAMENTO },
				{ price: 1000, quantity: 1, taxRate: IVA }
			],
			IVA
		);
		expect(t.subtotal).toBe(2000);
		expect(t.tax).toBe(150); // 20 + 130, no 150 por promedio
		expect(t.total).toBe(2150);
	});

	it('el desglose suma el subtotal y el impuesto', () => {
		const t = computeTotals(
			[
				{ price: 1000, quantity: 1, taxRate: MEDICAMENTO },
				{ price: 1000, quantity: 1, taxRate: IVA },
				{ price: 500, quantity: 2, taxRate: 0 }
			],
			IVA
		);
		expect(round2(t.byRate.reduce((a, g) => a + g.base, 0))).toBe(t.subtotal);
		expect(round2(t.byRate.reduce((a, g) => a + g.tax, 0))).toBe(t.tax);
	});

	it('el desglose va de menor a mayor y no depende del orden de las líneas', () => {
		const uno = computeTotals(
			[
				{ price: 100, quantity: 1, taxRate: IVA },
				{ price: 100, quantity: 1, taxRate: 0 }
			],
			IVA
		);
		const otro = computeTotals(
			[
				{ price: 100, quantity: 1, taxRate: 0 },
				{ price: 100, quantity: 1, taxRate: IVA }
			],
			IVA
		);
		expect(uno.byRate.map((g) => g.rate)).toEqual([0, IVA]);
		expect(uno.byRate).toEqual(otro.byRate);
	});

	it('las líneas de la misma tarifa caen en un solo grupo', () => {
		const t = computeTotals(
			[
				{ price: 100, quantity: 1, taxRate: IVA },
				{ price: 200, quantity: 1 }
			],
			IVA
		);
		expect(t.byRate).toEqual([{ rate: IVA, base: 300, tax: 39 }]);
	});

	it('con colones enteros da igual por línea que sobre el subtotal', () => {
		// Por qué los invariantes no se movieron: el catálogo son colones
		// enteros, y ahí las dos formas de redondear coinciden.
		const t = computeTotals(
			[
				{ price: 1450, quantity: 3 },
				{ price: 950, quantity: 1 },
				{ price: 2730, quantity: 1 },
				{ price: 4250, quantity: 2 }
			],
			IVA
		);
		expect(t.tax).toBe(round2(t.subtotal * IVA));
	});

	it('el impuesto del documento es la suma del de sus líneas', () => {
		// La propiedad que hace que la factura cuadre consigo misma: es lo que
		// se guarda en cada `sale_details`. Con céntimos, que es donde la otra
		// forma de redondear se separaba.
		const lineas = [
			{ price: 333.33, quantity: 3 },
			{ price: 0.335, quantity: 7 },
			{ price: 1999.99, quantity: 1 }
		];
		const t = computeTotals(lineas, IVA);
		const sumaDeLineas = round2(
			lineas.reduce((a, l) => a + lineTax(lineTotal(l.price, l.quantity), IVA), 0)
		);
		expect(sumaDeLineas).toBe(t.tax);
	});
});

describe('changeDue', () => {
	it('devuelve la diferencia', () => {
		expect(changeDue(5000, 4915.5)).toBe(84.5);
	});

	it('nunca es negativo', () => {
		expect(changeDue(1000, 4915.5)).toBe(0);
	});
});

// ------------------------------------------------------------------ tax

describe('impuesto configurado', () => {
	it('expone tasa y nombre vigentes', () => {
		expect(taxRate()).toBe(0.13);
		expect(taxName()).toBe('IVA');
	});

	it('la etiqueta omite decimales cuando el porcentaje es redondo', () => {
		expect(taxLabel()).toBe('IVA (13 %)');
	});

	it('y los muestra cuando no lo es', () => {
		usar(CRC, { name: 'ISV', rate: 0.045 });
		expect(taxLabel()).toBe('ISV (4,5 %)');
	});

	it('la moneda vigente se puede leer suelta', () => {
		expect(currencySettings().code).toBe('CRC');
		usar(USD);
		expect(currencySettings().symbol).toBe('$');
	});

	it('configureMoney copia y no comparte referencia con quien la pasó', () => {
		const currency = { ...CRC };
		usar(currency);
		currency.symbol = 'XXX';
		expect(currencySettings().symbol).toBe('₡');
	});
});

describe('rateFromPercent (F5: la ficha se escribe en porcentaje)', () => {
	it.each([
		[13, 0.13],
		[0, 0],
		[1, 0.01],
		[2, 0.02],
		[4.5, 0.045],
		[100, 1]
	])('«%s» es %s', (percent, esperado) => {
		expect(rateFromPercent(percent)).toBe(esperado);
	});

	it('recorta a seis decimales, que es lo que guarda la columna', () => {
		// `tax_rate` es DECIMAL(7,6). Sin recortar acá lo haría la base, en
		// silencio, y la tarifa releída dejaría de ser igual a la guardada: RN-11
		// avisaría de una diferencia que nadie hizo.
		expect(rateFromPercent(0.1234567)).toBe(0.001235);
		expect(rateFromPercent(100 / 3)).toBe(0.333333);
	});

	it('es la vuelta exacta de ratePercentText', () => {
		for (const rate of [0, 0.01, 0.02, 0.04, 0.045, 0.13, 1]) {
			expect(rateFromPercent(Number(ratePercentText(rate).replace(',', '.')))).toBe(rate);
		}
	});

	it.each([101, -1, 1300])('«%s» está fuera de rango y no se acepta', (percent) => {
		expect(rateFromPercent(percent)).toBeNull();
	});

	it.each([NaN, Infinity, -Infinity])('«%s» no es un número', (percent) => {
		expect(rateFromPercent(percent)).toBeNull();
	});
});

// -------------------------------------------------------------------- formato

describe('formatNumber', () => {
	it('agrupa de tres en tres', () => {
		expect(formatNumber(3175119.2)).toBe('3.175.119,20');
		expect(formatNumber(999)).toBe('999,00');
		expect(formatNumber(1000)).toBe('1.000,00');
	});

	it('acepta una cantidad de decimales distinta a la de la moneda', () => {
		expect(formatNumber(4.5, 1)).toBe('4,5');
		expect(formatNumber(1234, 0)).toBe('1.234');
	});

	it('usa el signo menos tipográfico, no el guion del teclado', () => {
		expect(formatNumber(-277)).toBe('−277,00');
		expect(formatNumber(-277).charCodeAt(0)).toBe(0x2212);
	});

	it('lo que no es número vale cero', () => {
		expect(formatNumber(null)).toBe('0,00');
		expect(formatNumber(undefined)).toBe('0,00');
		expect(formatNumber(Number.NaN)).toBe('0,00');
	});

	it('una moneda sin separador de miles no agrupa', () => {
		usar({ ...CRC, thousandsSeparator: '' });
		expect(formatNumber(3175119.2)).toBe('3175119,20');
	});

	it('una moneda sin decimales no escribe separador decimal', () => {
		usar(COP);
		expect(formatNumber(3175119.2)).toBe('3.175.119');
	});
});

describe('formatMoney', () => {
	it('antepone el símbolo por omisión', () => {
		expect(formatMoney(1450)).toBe('₡1.450,00');
	});

	it('lo pospone con espacio duro cuando la moneda lo pide', () => {
		usar(EUR);
		// U+00A0 y no un espacio normal: el símbolo no se parte del monto al
		// llegar al borde del renglón.
		expect(formatMoney(1450)).toBe('1.450,00 €');
	});

	it('pone el signo antes del símbolo, no después', () => {
		expect(formatMoney(-1450)).toBe('−₡1.450,00');
	});

	it('lo que no es número vale cero', () => {
		expect(formatMoney(null)).toBe('₡0,00');
		expect(formatMoney(Number.NaN)).toBe('₡0,00');
	});

	it('formatAmount es lo mismo sin símbolo', () => {
		expect(formatAmount(1450)).toBe('1.450,00');
	});
});

describe('formatCompact', () => {
	it('abrevia millones y miles', () => {
		expect(formatCompact(3175119.2)).toBe('₡3,2 M');
		expect(formatCompact(845000)).toBe('₡845 k');
	});

	it('deja las cifras chicas enteras', () => {
		expect(formatCompact(450)).toBe('₡450');
	});

	it('conserva el signo', () => {
		expect(formatCompact(-2500000)).toBe('−₡2,5 M');
		expect(formatCompact(-4500)).toBe('−₡5 k');
		expect(formatCompact(-450)).toBe('−₡450');
	});

	it('lo que no es número vale cero', () => {
		expect(formatCompact(null)).toBe('₡0');
	});
});

// -------------------------------------------------------------------- lectura

describe('parseAmount', () => {
	it('lee lo que teclea el cajero, con o sin separadores', () => {
		expect(parseAmount('1234.56')).toBe(1234.56);
		expect(parseAmount('1.234,56')).toBe(1234.56);
		expect(parseAmount('1,234.56')).toBe(1234.56);
		expect(parseAmount('1.234.567')).toBe(1234567);
		expect(parseAmount('12,50')).toBe(12.5);
		expect(parseAmount('1,234')).toBe(1234);
		expect(parseAmount('5000')).toBe(5000);
	});

	it('ignora símbolos y espacios', () => {
		expect(parseAmount('₡1 234')).toBe(1234);
		expect(parseAmount(' $ 4.915,50 ')).toBe(4915.5);
	});

	it('entiende el menos tipográfico igual que el del teclado', () => {
		expect(parseAmount('−277')).toBe(-277);
		expect(parseAmount('-277')).toBe(-277);
	});

	it('acepta un número y lo redondea', () => {
		expect(parseAmount(1234.567)).toBe(1234.57);
		expect(parseAmount(Number.NaN)).toBeNull();
	});

	it('devuelve null cuando no hay nada interpretable', () => {
		expect(parseAmount(null)).toBeNull();
		expect(parseAmount(undefined)).toBeNull();
		expect(parseAmount('')).toBeNull();
		expect(parseAmount('   ')).toBeNull();
		expect(parseAmount('abc')).toBeNull();
		expect(parseAmount('-')).toBeNull();
	});

	it('no depende de los separadores configurados: se teclea como salga', () => {
		usar(USD);
		expect(parseAmount('1.234,56')).toBe(1234.56);
	});
});
