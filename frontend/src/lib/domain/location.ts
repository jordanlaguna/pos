/**
 * La ubicación del emisor con los códigos de Hacienda (T-722, RN-83).
 *
 * La misma regla que `app/domain/locations.py`, para que la pantalla diga que no
 * antes de que lo diga el servidor: provincia, cantón y distrito **numerados**
 * de la nota 14 del anexo, un código que solo vale dentro de su padre, otras
 * señas obligatorias —de 5 a 250— y el barrio opcional —de 5 a 50—.
 *
 * Los nombres salen del catálogo generado (`locationsData.ts`) y son los de
 * Hacienda: no se traducen, como no se traduce «Cédula jurídica».
 */

import { CANTONS, DISTRICTS, PROVINCES } from './locationsData';

export interface IssuerLocation {
	/** Un dígito: `'1'` San José … `'7'` Limón. */
	province: string;
	/** Dos dígitos, dentro de la provincia. */
	canton: string;
	/** Dos dígitos, dentro del cantón. */
	district: string;
	/** Texto libre y opcional desde la 4.4. */
	neighborhood: string;
	/** Obligatorias. «600 m oeste de Plaza Cristal…». */
	otherSigns: string;
}

export const EMPTY_LOCATION: IssuerLocation = {
	province: '',
	canton: '',
	district: '',
	neighborhood: '',
	otherSigns: ''
};

/** Los largos del anexo (p. 21). */
export const NEIGHBORHOOD_MIN = 5;
export const NEIGHBORHOOD_MAX = 50;
export const OTHER_SIGNS_MIN = 5;
export const OTHER_SIGNS_MAX = 250;

export type LocationField = 'province' | 'canton' | 'district' | 'neighborhood' | 'other_signs';
export type LocationReason = 'required' | 'unknown' | 'too_short' | 'too_long';

export interface LocationProblem {
	field: LocationField;
	reason: LocationReason;
}

export interface Option {
	code: string;
	name: string;
}

function options(source: Readonly<Record<string, string>> | undefined): Option[] {
	return Object.entries(source ?? {}).map(([code, name]) => ({ code, name }));
}

export function provinceOptions(): Option[] {
	return options(PROVINCES);
}

/** Los cantones de una provincia; ninguno si la provincia no existe. */
export function cantonOptions(province: string): Option[] {
	return options(CANTONS[province]);
}

/** Los distritos de un cantón; ninguno si el par no existe. */
export function districtOptions(province: string, canton: string): Option[] {
	return options(DISTRICTS[`${province}-${canton}`]);
}

/** Espacios de más fuera, como los guarda el backend. */
function clean(value: unknown): string {
	return typeof value === 'string' ? value.trim().split(/\s+/).filter(Boolean).join(' ') : '';
}

/** Si no se empezó a llenar: la vacía se guarda, la a medias no. */
export function isBlankLocation(location: Partial<IssuerLocation> | null | undefined): boolean {
	if (!location) return true;
	return [
		location.province,
		location.canton,
		location.district,
		location.neighborhood,
		location.otherSigns
	].every((v) => clean(v) === '');
}

/**
 * El primer problema de la ubicación, en el orden de la pantalla, o nulo.
 *
 * Primero la provincia, porque sin ella el cantón no se puede juzgar.
 */
export function locationProblem(location: Partial<IssuerLocation>): LocationProblem | null {
	const province = clean(location.province);
	const canton = clean(location.canton);
	const district = clean(location.district);

	if (!province) return { field: 'province', reason: 'required' };
	if (!(province in PROVINCES)) return { field: 'province', reason: 'unknown' };
	if (!canton) return { field: 'canton', reason: 'required' };
	// Sin `?? {}`: la provincia ya se validó, así que su lista existe.
	if (!(canton in CANTONS[province])) return { field: 'canton', reason: 'unknown' };
	if (!district) return { field: 'district', reason: 'required' };
	if (!(district in DISTRICTS[`${province}-${canton}`])) return { field: 'district', reason: 'unknown' };

	const neighborhood = clean(location.neighborhood);
	if (neighborhood && neighborhood.length < NEIGHBORHOOD_MIN)
		return { field: 'neighborhood', reason: 'too_short' };
	if (neighborhood.length > NEIGHBORHOOD_MAX) return { field: 'neighborhood', reason: 'too_long' };

	const otherSigns = clean(location.otherSigns);
	if (!otherSigns) return { field: 'other_signs', reason: 'required' };
	if (otherSigns.length < OTHER_SIGNS_MIN) return { field: 'other_signs', reason: 'too_short' };
	if (otherSigns.length > OTHER_SIGNS_MAX) return { field: 'other_signs', reason: 'too_long' };

	return null;
}

/** La ubicación saneada, como se guarda: códigos y texto sin espacios de más. */
export function normalizeLocation(raw: unknown): IssuerLocation {
	const source = raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : {};
	const code = (value: unknown) =>
		typeof value === 'string' || typeof value === 'number' ? clean(String(value)) : '';
	return {
		province: code(source.province),
		canton: code(source.canton),
		district: code(source.district),
		neighborhood: clean(source.neighborhood),
		otherSigns: clean(source.otherSigns)
	};
}

/**
 * Los nombres de provincia, cantón y distrito, para imprimirlos como la factura
 * de referencia: «Provincia: San José / Cantón: San José / Distrito: Zapote».
 * Nulo si la ubicación no está completa.
 */
export function locationNames(
	location: IssuerLocation | null | undefined
): { province: string; canton: string; district: string } | null {
	if (!location || locationProblem(location) !== null) return null;
	return {
		province: PROVINCES[location.province],
		canton: CANTONS[location.province][location.canton],
		district: DISTRICTS[`${location.province}-${location.canton}`][location.district]
	};
}
