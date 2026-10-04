import { describe, expect, it } from 'vitest';

import {
	EMPTY_LOCATION,
	NEIGHBORHOOD_MAX,
	OTHER_SIGNS_MAX,
	cantonOptions,
	districtOptions,
	isBlankLocation,
	locationNames,
	locationProblem,
	normalizeLocation,
	provinceOptions
} from './location';
import { CANTONS, DISTRICTS } from './locationsData';

/** La del emisor de la factura de referencia: San José, San José, Zapote. */
const ZAPOTE = {
	province: '1',
	canton: '01',
	district: '05',
	neighborhood: '',
	otherSigns: '600 m oeste de Plaza Cristal'
};

describe('el catálogo de la nota 14', () => {
	it('tiene 7 provincias, 84 cantones y 492 distritos, como el del backend', () => {
		expect(provinceOptions()).toHaveLength(7);
		expect(Object.values(CANTONS).reduce((n, c) => n + Object.keys(c).length, 0)).toBe(84);
		expect(Object.values(DISTRICTS).reduce((n, d) => n + Object.keys(d).length, 0)).toBe(492);
	});

	it('los cantones de una provincia, en orden', () => {
		expect(cantonOptions('7').map((c) => c.name)).toEqual([
			'Limón',
			'Pococí',
			'Siquirres',
			'Talamanca',
			'Matina',
			'Guácimo'
		]);
	});

	it('los distritos de un cantón', () => {
		expect(districtOptions('1', '18')).toEqual([
			{ code: '01', name: 'Curridabat' },
			{ code: '02', name: 'Granadilla' },
			{ code: '03', name: 'Sánchez' },
			{ code: '04', name: 'Tirrases' }
		]);
	});

	it('nada para un padre que no existe', () => {
		expect(cantonOptions('9')).toEqual([]);
		expect(districtOptions('7', '07')).toEqual([]);
	});
});

describe('locationProblem', () => {
	it('la de la factura de referencia sirve', () => {
		expect(locationProblem(ZAPOTE)).toBeNull();
	});

	it('va en el orden de la pantalla: primero la provincia', () => {
		expect(locationProblem(EMPTY_LOCATION)).toEqual({ field: 'province', reason: 'required' });
		expect(locationProblem({ ...ZAPOTE, province: '8' })).toEqual({
			field: 'province',
			reason: 'unknown'
		});
	});

	it('un código solo vale dentro de su padre', () => {
		// Limón tiene seis cantones; Curridabat, cuatro distritos.
		expect(locationProblem({ ...ZAPOTE, province: '7', canton: '07' })).toEqual({
			field: 'canton',
			reason: 'unknown'
		});
		expect(locationProblem({ ...ZAPOTE, canton: '18' })).toEqual({
			field: 'district',
			reason: 'unknown'
		});
	});

	it('lo que falta', () => {
		expect(locationProblem({ ...ZAPOTE, canton: '' })).toEqual({ field: 'canton', reason: 'required' });
		expect(locationProblem({ ...ZAPOTE, district: ' ' })).toEqual({
			field: 'district',
			reason: 'required'
		});
		expect(locationProblem({ ...ZAPOTE, otherSigns: '' })).toEqual({
			field: 'other_signs',
			reason: 'required'
		});
	});

	it('los largos del anexo', () => {
		expect(locationProblem({ ...ZAPOTE, otherSigns: 'casa' })).toEqual({
			field: 'other_signs',
			reason: 'too_short'
		});
		expect(locationProblem({ ...ZAPOTE, otherSigns: 'x'.repeat(OTHER_SIGNS_MAX + 1) })).toEqual({
			field: 'other_signs',
			reason: 'too_long'
		});
		expect(locationProblem({ ...ZAPOTE, neighborhood: 'Sur' })).toEqual({
			field: 'neighborhood',
			reason: 'too_short'
		});
		expect(locationProblem({ ...ZAPOTE, neighborhood: 'x'.repeat(NEIGHBORHOOD_MAX + 1) })).toEqual({
			field: 'neighborhood',
			reason: 'too_long'
		});
	});

	it('el barrio es opcional', () => {
		expect(locationProblem({ ...ZAPOTE, neighborhood: '' })).toBeNull();
		expect(locationProblem({ ...ZAPOTE, neighborhood: 'Barrio Los Ángeles' })).toBeNull();
	});
});

describe('isBlankLocation', () => {
	it('vacía del todo', () => {
		expect(isBlankLocation(null)).toBe(true);
		expect(isBlankLocation(undefined)).toBe(true);
		expect(isBlankLocation(EMPTY_LOCATION)).toBe(true);
		expect(isBlankLocation({ province: ' ', otherSigns: '' })).toBe(true);
	});

	it('a medias no es vacía', () => {
		expect(isBlankLocation({ province: '1' })).toBe(false);
		expect(isBlankLocation({ otherSigns: 'frente al parque' })).toBe(false);
	});
});

describe('normalizeLocation', () => {
	it('sanea lo que llega del backend', () => {
		expect(
			normalizeLocation({
				province: 1,
				canton: ' 01 ',
				district: '05',
				neighborhood: '  Los   Ángeles ',
				otherSigns: '  frente  al parque '
			})
		).toEqual({
			province: '1',
			canton: '01',
			district: '05',
			neighborhood: 'Los Ángeles',
			otherSigns: 'frente al parque'
		});
	});

	it('cualquier otra cosa es una vacía', () => {
		expect(normalizeLocation('San José')).toEqual(EMPTY_LOCATION);
		expect(normalizeLocation(null)).toEqual(EMPTY_LOCATION);
		expect(normalizeLocation({ province: true, otherSigns: 7 })).toEqual(EMPTY_LOCATION);
	});
});

describe('locationNames', () => {
	it('los nombres de Hacienda', () => {
		expect(locationNames(ZAPOTE)).toEqual({
			province: 'San José',
			canton: 'San José',
			district: 'Zapote'
		});
	});

	it('nula si no está completa', () => {
		expect(locationNames({ ...ZAPOTE, district: '' })).toBeNull();
		expect(locationNames(null)).toBeNull();
	});
});
