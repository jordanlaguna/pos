import { describe, expect, it } from 'vitest';
import { amountInWords } from './amountInWords';

const colones = (amount: number, locale = 'es') =>
	amountInWords(amount, { locale, currency: 'CRC', decimals: 2 });

describe('el monto en letras (T-731)', () => {
	it('dice lo mismo que la factura de referencia', () => {
		// docs/invoice/50624092600310170293400100001010001819201163700346.pdf
		expect(colones(264420)).toBe(
			'DOSCIENTOS SESENTA Y CUATRO MIL CUATROCIENTOS VEINTE CON 00/100 COLONES'
		);
	});

	it('los céntimos van en fracción de cien', () => {
		expect(colones(5863.2)).toBe('CINCO MIL OCHOCIENTOS SESENTA Y TRES CON 20/100 COLONES');
		expect(colones(0.05)).toBe('CERO CON 05/100 COLONES');
	});

	describe('en español', () => {
		it.each([
			[1, 'UNO'],
			[15, 'QUINCE'],
			[16, 'DIECISÉIS'],
			[21, 'VEINTIUNO'],
			[22, 'VEINTIDÓS'],
			[30, 'TREINTA'],
			[31, 'TREINTA Y UNO'],
			[100, 'CIEN'],
			[101, 'CIENTO UNO'],
			[500, 'QUINIENTOS'],
			[999, 'NOVECIENTOS NOVENTA Y NUEVE'],
			[1000, 'MIL'],
			[1001, 'MIL UNO'],
			[21000, 'VEINTIÚN MIL'],
			[31000, 'TREINTA Y UN MIL'],
			[100000, 'CIEN MIL'],
			[101000, 'CIENTO UN MIL'],
			[1000000, 'UN MILLÓN'],
			[1000001, 'UN MILLÓN UNO'],
			[2500000, 'DOS MILLONES QUINIENTOS MIL'],
			[21000000, 'VEINTIÚN MILLONES'],
			[1000000000, 'MIL MILLONES']
		])('%d es %s', (n, palabras) => {
			expect(colones(n)).toBe(`${palabras} CON 00/100 COLONES`);
		});
	});

	describe('en inglés', () => {
		it.each([
			[0, 'ZERO'],
			[13, 'THIRTEEN'],
			[40, 'FORTY'],
			[42, 'FORTY-TWO'],
			[100, 'ONE HUNDRED'],
			[264420, 'TWO HUNDRED SIXTY-FOUR THOUSAND FOUR HUNDRED TWENTY'],
			[1000000, 'ONE MILLION'],
			[2000000001, 'TWO BILLION ONE']
		])('%d es %s', (n, palabras) => {
			expect(colones(n, 'en')).toBe(`${palabras} AND 00/100 COLONES`);
		});
	});

	describe('en portugués', () => {
		it.each([
			[0, 'ZERO'],
			[17, 'DEZESSETE'],
			[20, 'VINTE'],
			[21, 'VINTE E UM'],
			[100, 'CEM'],
			[120, 'CENTO E VINTE'],
			[1100, 'MIL E CEM'],
			[1234, 'MIL DUZENTOS E TRINTA E QUATRO'],
			[264420, 'DUZENTOS E SESSENTA E QUATRO MIL QUATROCENTOS E VINTE'],
			[1000000, 'UM MILHÃO'],
			[2500000, 'DOIS MILHÕES E QUINHENTOS MIL'],
			[1000000000, 'UM BILHÃO'],
			[3000000005, 'TRÊS BILHÕES E CINCO']
		])('%d es %s', (n, palabras) => {
			expect(colones(n, 'pt')).toBe(`${palabras} COM 00/100 COLONES`);
		});
	});

	it('la moneda sale en el idioma del documento', () => {
		expect(amountInWords(12, { locale: 'en', currency: 'USD', decimals: 2 })).toBe(
			'TWELVE AND 00/100 DOLLARS'
		);
		expect(amountInWords(12, { locale: 'es', currency: 'USD', decimals: 2 })).toBe(
			'DOCE CON 00/100 DÓLARES'
		);
	});

	it('una moneda sin nombre sale con su código', () => {
		expect(amountInWords(2, { locale: 'es', currency: 'XYZ', decimals: 2 })).toBe(
			'DOS CON 00/100 XYZ'
		);
	});

	it('sin decimales no hay céntimos que nombrar, y se redondea al entero', () => {
		expect(amountInWords(1500.6, { locale: 'es', currency: 'COP', decimals: 0 })).toBe(
			'MIL QUINIENTOS UNO PESOS'
		);
	});

	it('un idioma desconocido cae al base, sin romper la factura', () => {
		expect(colones(3, 'xx')).toBe('TRES CON 00/100 COLONES');
	});

	it('lo que no cabe o no es un número no se imprime', () => {
		expect(colones(1e12)).toBeNull();
		expect(colones(Number.NaN)).toBeNull();
		expect(colones(Number.POSITIVE_INFINITY)).toBeNull();
	});
});
