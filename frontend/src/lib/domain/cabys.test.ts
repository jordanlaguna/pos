import { describe, expect, it } from 'vitest';
import {
	CABYS_CODE_LENGTH,
	cabysCodeProblem,
	differsFromOfficial,
	normalizeCabysCode
} from './cabys';

describe('cabysCodeProblem', () => {
	it('acepta un código real del catálogo', () => {
		expect(cabysCodeProblem('2312000000300')).toBeNull();
	});

	it('acepta los espacios de alrededor, que arrastra quien lo pega', () => {
		expect(cabysCodeProblem('  2312000000300  ')).toBeNull();
	});

	it('conserva los ceros a la izquierda: son parte del código', () => {
		expect(cabysCodeProblem('0113100000000')).toBeNull();
		expect(normalizeCabysCode('0113100000000')).toBe('0113100000000');
	});

	it.each([
		['', 'empty'],
		['   ', 'empty'],
		[null, 'empty'],
		[undefined, 'empty']
	])('«%s» está vacío', (entrada, esperado) => {
		expect(cabysCodeProblem(entrada as string | null | undefined)).toBe(esperado);
	});

	it.each(['2312-00000030', 'abcdefghijklm', '231200000030a', '2 312000000300'])(
		'«%s» no es solo dígitos',
		(entrada) => {
			expect(cabysCodeProblem(entrada)).toBe('not_digits');
		}
	);

	it.each(['231200000030', '23120000003000', '1'])('«%s» no mide trece', (entrada) => {
		expect(cabysCodeProblem(entrada)).toBe('bad_length');
	});

	it('no rellena con ceros un código corto: adivinar es peor que rechazar', () => {
		expect(normalizeCabysCode('231200000030')).toBeNull();
	});

	it('trece es trece', () => {
		expect(CABYS_CODE_LENGTH).toBe(13);
		expect('2312000000300'.length).toBe(CABYS_CODE_LENGTH);
	});
});

describe('normalizeCabysCode', () => {
	it('devuelve el código limpio cuando es válido', () => {
		expect(normalizeCabysCode(' 3521000000100 ')).toBe('3521000000100');
	});

	it('devuelve null cuando no lo es', () => {
		expect(normalizeCabysCode('nada')).toBeNull();
		expect(normalizeCabysCode(null)).toBeNull();
	});
});

describe('differsFromOfficial', () => {
	it('no avisa cuando la tarifa es la del catálogo', () => {
		expect(differsFromOfficial(0.13, 0.13)).toBe(false);
	});

	it('avisa cuando el usuario la cambió (RN-11)', () => {
		expect(differsFromOfficial(0, 0.13)).toBe(true);
		expect(differsFromOfficial(0.02, 0.13)).toBe(true);
	});

	it('no avisa si no hay tarifa oficial con qué comparar', () => {
		// Pasa con un producto sin clasificar y con un catálogo que no se pudo
		// leer. Avisar ahí sería inventarse una diferencia que nadie comprueba.
		expect(differsFromOfficial(0.13, null)).toBe(false);
		expect(differsFromOfficial(0.13, undefined)).toBe(false);
	});

	it('no avisa si no hay tarifa elegida', () => {
		// `tax_rate` en nulo significa «la configurada del negocio», que no es
		// una elección del usuario y por eso no se compara contra el catálogo.
		expect(differsFromOfficial(null, 0.13)).toBe(false);
	});

	it('el cero es una tarifa, no una ausencia', () => {
		// Un libro infantil paga 0 %. Si `0` se tratara como «sin tarifa», el
		// único producto exonerado de verdad sería el que nunca avisa.
		expect(differsFromOfficial(0, 0)).toBe(false);
		expect(differsFromOfficial(0, 0.02)).toBe(true);
	});
});
