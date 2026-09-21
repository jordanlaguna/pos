import { describe, expect, it } from 'vitest';
import {
	SELLABLE_TAX_CODES,
	TAX_CODES,
	TAX_CODE_GENERAL,
	rateForTaxCode,
	suggestedTaxCode
} from './taxCodes';

describe('el catálogo de la nota 8.1', () => {
	it('son los once, en su orden', () => {
		expect(TAX_CODES.map((t) => t.code)).toEqual([
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
			'11'
		]);
	});

	it('los transitorios no se le ofrecen a un producto', () => {
		// Existen solo para corregir con una nota de crédito una factura de
		// cuando esas tarifas regían: ofrecerlos en la ficha es ofrecer un
		// rechazo.
		expect(SELLABLE_TAX_CODES.map((t) => t.code)).toEqual([
			'01',
			'02',
			'03',
			'04',
			'08',
			'09',
			'10',
			'11'
		]);
	});

	it('la general es la del 13 %', () => {
		expect(rateForTaxCode(TAX_CODE_GENERAL)).toBe(0.13);
	});
});

describe('rateForTaxCode', () => {
	it.each([
		['01', 0],
		['04', 0.04],
		['08', 0.13],
		['09', 0.005],
		['10', 0],
		['11', 0]
	])('%s cobra %s', (codigo, tarifa) => {
		expect(rateForTaxCode(codigo)).toBe(tarifa);
	});

	it('perdona los espacios de alrededor', () => {
		expect(rateForTaxCode(' 08 ')).toBe(0.13);
	});

	it.each([['12'], ['8'], [''], [null], [undefined]])(
		'«%s» no está en el catálogo',
		(malo) => {
			expect(rateForTaxCode(malo as string | null | undefined)).toBeNull();
		}
	);
});

describe('suggestedTaxCode', () => {
	it.each([
		[0.13, '08'],
		[0.04, '04'],
		[0.02, '03'],
		[0.01, '02'],
		[0.005, '09']
	])('%s deja una sola posibilidad: %s', (tarifa, codigo) => {
		expect(suggestedTaxCode(tarifa)).toBe(codigo);
	});

	it('el 0 % no se deduce: entre el 01, el 10 y el 11 no decide la aritmética', () => {
		// El 01 da derecho a crédito pleno y el 11 no da ninguno. Proponer uno
		// sería elegirle a quien factura el derecho de su cliente (RN-76).
		expect(suggestedTaxCode(0)).toBeNull();
	});

	it('el 8 % tampoco: solo existe como transitorio', () => {
		expect(suggestedTaxCode(0.08)).toBeNull();
	});

	it('una tarifa que no está en el catálogo no tiene código', () => {
		expect(suggestedTaxCode(0.07)).toBeNull();
	});

	it('sin tarifa no hay nada que proponer', () => {
		expect(suggestedTaxCode(null)).toBeNull();
		expect(suggestedTaxCode(undefined)).toBeNull();
	});
});
