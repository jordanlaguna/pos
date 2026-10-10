import { describe, expect, it } from 'vitest';
import { belowMinimum, effectiveMinimum } from './inventory';

describe('bajo mínimo (RN-101)', () => {
	it('con mínimo propio manda el propio', () => {
		expect(belowMinimum(5, 10, 3)).toBe(true);
		expect(belowMinimum(5, 2, 10)).toBe(false);
	});

	it('el mínimo cuenta como bajo', () => {
		expect(belowMinimum(10, 10, null)).toBe(true);
		expect(belowMinimum(11, 10, null)).toBe(false);
	});

	it('sin propio manda el general', () => {
		expect(belowMinimum(5, null, 3)).toBe(false);
		expect(belowMinimum(3, null, 3)).toBe(true);
		// Un producto de antes de F15 ni siquiera trae el campo.
		expect(belowMinimum(3, undefined, 3)).toBe(true);
	});

	it('sin ninguno, nunca', () => {
		expect(belowMinimum(0, null, null)).toBe(false);
		expect(belowMinimum(0, undefined, null)).toBe(false);
	});

	it('cero es un mínimo que solo avisa agotado', () => {
		expect(belowMinimum(1, 0, 10)).toBe(false);
		expect(belowMinimum(0, 0, 10)).toBe(true);
	});
});

describe('el mínimo que se aplica', () => {
	it('es el propio, si no el general, si no ninguno', () => {
		expect(effectiveMinimum(4, 10)).toBe(4);
		expect(effectiveMinimum(null, 10)).toBe(10);
		expect(effectiveMinimum(undefined, 10)).toBe(10);
		expect(effectiveMinimum(null, null)).toBeNull();
	});
});
