import { describe, expect, it } from 'vitest';
import { PAYMENT_METHODS } from './types';

/**
 * `types.ts` es casi todo declaraciones de tipo, que no dejan código al
 * compilar. Lo único que existe en tiempo de ejecución es esta lista, y no es
 * decorativa: es el conjunto cerrado contra el que `Validator.oneOf` decide si
 * un método de pago es válido, y el que separa lo que va a la gaveta de lo que
 * no.
 */

describe('PAYMENT_METHODS', () => {
	it('son los cuatro que acepta el POS', () => {
		expect(PAYMENT_METHODS).toEqual([
			'Efectivo',
			'Tarjeta de crédito',
			'Transferencia bancaria',
			'Pago móvil'
		]);
	});

	it('«Efectivo» está y se escribe así', () => {
		// El arqueo compara con esta cadena exacta para saber qué pasó por la
		// gaveta. Cambiarle una tilde deja todo turno con faltante.
		expect(PAYMENT_METHODS[0]).toBe('Efectivo');
	});

	it('no hay repetidos', () => {
		expect(new Set(PAYMENT_METHODS).size).toBe(PAYMENT_METHODS.length);
	});
});
