import { describe, expect, it } from 'vitest';
import {
	FOREIGN,
	NON_TAXPAYER,
	identificationTypeFor,
	identificationTypeName,
	isForeign,
	isIdentificationType
} from './identification';

describe('el tipo de identificación (T-617)', () => {
	it('son los seis de Hacienda', () => {
		for (const code of ['01', '02', '03', '04', '05', '06']) {
			expect(isIdentificationType(code)).toBe(true);
		}
		expect(isIdentificationType('07')).toBe(false);
		expect(isIdentificationType(null)).toBe(false);
	});

	it('el 05 es el extranjero y el 06 el no contribuyente (F7)', () => {
		expect(FOREIGN).toBe('05');
		expect(NON_TAXPAYER).toBe('06');
		expect(identificationTypeName('05')).toBe('Extranjero no domiciliado');
		expect(identificationTypeName('06')).toBe('No contribuyente');
		expect(isForeign('05')).toBe(true);
		for (const otro of ['01', '06', null, undefined, '']) expect(isForeign(otro)).toBe(false);
	});

	it('la longitud de la cédula deja ver el tipo, como en el backend', () => {
		expect(identificationTypeFor('108840287')).toBe('01');
		expect(identificationTypeFor('3101702934')).toBe('02');
		expect(identificationTypeFor('15520012345')).toBe('03');
		expect(identificationTypeFor('155200123456')).toBe('03');
	});

	it('los separadores no cuentan', () => {
		expect(identificationTypeFor('1-0884-0287')).toBe('01');
	});

	it('lo que no se sabe se dice que no se sabe', () => {
		expect(identificationTypeFor('')).toBeNull();
		expect(identificationTypeFor('12345')).toBeNull();
	});

	it('el nombre es el legal, sin traducir', () => {
		expect(identificationTypeName('01')).toBe('Cédula física');
		expect(identificationTypeName('02')).toBe('Cédula jurídica');
		expect(identificationTypeName('99')).toBeNull();
		expect(identificationTypeName(null)).toBeNull();
	});
});
