import { describe, expect, it } from 'vitest';
import { nextAffiliate, nextCompanyOf } from './affiliates';

const PARES = [
	{ afiliado: 1, compania: 1 },
	{ afiliado: 1, compania: 2 },
	{ afiliado: 3, compania: 1 }
];

describe('la numeración del alta (QA-04)', () => {
	it('propone el siguiente afiliado al mayor, aunque haya huecos', () => {
		expect(nextAffiliate(PARES)).toBe(4);
	});

	it('sin compañías, el primero es el 1', () => {
		expect(nextAffiliate([])).toBe(1);
		expect(nextCompanyOf([], 1)).toBe(1);
	});

	it('la compañía se cuenta dentro de su afiliado', () => {
		expect(nextCompanyOf(PARES, 1)).toBe(3);
		expect(nextCompanyOf(PARES, 3)).toBe(2);
	});

	it('un afiliado nuevo empieza en la compañía 1', () => {
		expect(nextCompanyOf(PARES, 4)).toBe(1);
	});
});
