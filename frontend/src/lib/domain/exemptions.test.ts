import { describe, expect, it } from 'vitest';
import {
	EXEMPTION_INSTITUTIONS,
	EXEMPTION_OTHER,
	EXEMPTION_TYPES,
	MAX_EXEMPTION_POINTS,
	SELLABLE_EXEMPTION_TYPES,
	exemptionNeedsArticle,
	exemptionVerifiedByHacienda
} from './exemptions';

describe('los catálogos', () => {
	it('son los doce tipos de la nota 10.1', () => {
		expect(EXEMPTION_TYPES.map((t) => t.code)).toEqual([
			'01',
			'02',
			'03',
			'04',
			'05',
			'06',
			'07',
			'08',
			'09',
			'10',
			'11',
			'99'
		]);
	});

	it('y las trece instituciones de la nota 23', () => {
		expect(EXEMPTION_INSTITUTIONS).toHaveLength(13);
		expect(EXEMPTION_INSTITUTIONS.at(-1)).toBe(EXEMPTION_OTHER);
	});

	it('los cuatro que solo valen en notas no se le ofrecen a un cliente', () => {
		// Ponérselos para facturarle es guardar un rechazo.
		expect(SELLABLE_EXEMPTION_TYPES.map((t) => t.code)).toEqual([
			'02',
			'03',
			'04',
			'08',
			'09',
			'10',
			'11',
			'99'
		]);
	});

	it('el tope de puntos es el del XSD: decimal 4,2', () => {
		expect(MAX_EXEMPTION_POINTS).toBe(99.99);
	});
});

describe('exemptionNeedsArticle', () => {
	it.each([
		['02', true],
		['03', true],
		['08', true],
		['04', false],
		['99', false]
	])('%s exige artículo: %s', (codigo, exige) => {
		expect(exemptionNeedsArticle(codigo)).toBe(exige);
	});

	it('un tipo que no existe no exige nada', () => {
		expect(exemptionNeedsArticle('77')).toBe(false);
		expect(exemptionNeedsArticle(null)).toBe(false);
	});
});

describe('exemptionVerifiedByHacienda', () => {
	it('el 04 y el 11 se cruzan contra el registro de exenciones', () => {
		expect(exemptionVerifiedByHacienda('04')).toBe(true);
		expect(exemptionVerifiedByHacienda('11')).toBe(true);
	});

	it('los demás no', () => {
		expect(exemptionVerifiedByHacienda('08')).toBe(false);
		expect(exemptionVerifiedByHacienda(undefined)).toBe(false);
	});
});
