import { describe, expect, it } from 'vitest';
import { COMPANY_STATES, PAYMENT_METHODS } from './types';

/**
 * `types.ts` es casi todo declaraciones de tipo, que no dejan código al
 * compilar. Lo único que existe en tiempo de ejecución son estas dos listas, y
 * ninguna es decorativa: son los conjuntos cerrados contra los que
 * `Validator.oneOf` decide si un valor es válido —el método de pago que separa
 * lo que va a la gaveta de lo que no, y el estado de suscripción que el panel de
 * soporte puede escribir—.
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

describe('COMPANY_STATES', () => {
	it('son los cinco del spec, en el orden del ciclo de vida', () => {
		// El orden importa dos veces: es el del desplegable de la ficha y el que
		// hace que «activa» quede al lado de «prueba» y no al final.
		expect(COMPANY_STATES).toEqual([
			'prueba',
			'activa',
			'vencida',
			'suspendida',
			'cancelada'
		]);
	});

	it('son los valores de la base, sin traducir', () => {
		// Se comparan contra `companies.estado` en el backend. Traducirlos sería
		// corromper datos: un `<option value="expired">` dejaría de coincidir con
		// nada y el «no» llegaría como `invalid_company_state`.
		for (const estado of COMPANY_STATES) {
			expect(estado).toMatch(/^[a-z]+$/);
		}
	});

	it('no hay repetidos', () => {
		expect(new Set(COMPANY_STATES).size).toBe(COMPANY_STATES.length);
	});
});
