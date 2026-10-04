import { ID_TYPES } from './settings';

/**
 * Los tipos de identificación de Hacienda, vistos desde el receptor (T-617).
 *
 * Espejo de `app/domain/hacienda.py`. El receptor del comprobante lleva su tipo
 * y la representación impresa lo nombra —«Cédula física 108840287»—, así que el
 * cliente lo guarda. La lista y sus nombres legales son los de `ID_TYPES`: seis
 * desde F7, y de esos el emisor solo puede ser de los cuatro primeros.
 */
export type IdentificationType = (typeof ID_TYPES)[number]['code'];

/** El extranjero no domiciliado: recibe la factura de exportación (T-727). */
export const FOREIGN: IdentificationType = '05';
/** El no contribuyente: como proveedor, da lugar a la factura de compra (T-728). */
export const NON_TAXPAYER: IdentificationType = '06';

export function isIdentificationType(value: unknown): value is IdentificationType {
	return ID_TYPES.some((t) => t.code === value);
}

/** Si un cliente con este tipo es del extranjero, y por eso se le exporta. */
export function isForeign(type: string | null | undefined): boolean {
	return type === FOREIGN;
}

/**
 * El tipo que deja ver la longitud de la cédula, o `null`.
 *
 * Nueve dígitos son física, diez jurídica, once o doce DIMEX. **El NITE también
 * son diez** y no se distingue de la jurídica mirando el número: se devuelve
 * jurídica porque es órdenes de magnitud más común, y quien tenga un NITE lo
 * elige. Los separadores no cuentan —hay cédulas guardadas como «1-0234-0567»—.
 */
export function identificationTypeFor(identification: string): IdentificationType | null {
	const digitos = identification.replace(/\D/g, '');
	switch (digitos.length) {
		case 9:
			return '01';
		case 10:
			return '02';
		case 11:
		case 12:
			return '03';
		default:
			return null;
	}
}

/**
 * El nombre legal del tipo —«Cédula jurídica»—, o `null` si no es uno de los de
 * Hacienda. No se traduce: es el nombre del documento en Costa Rica (ver
 * `ID_TYPES`).
 */
export function identificationTypeName(code: string | null | undefined): string | null {
	return ID_TYPES.find((t) => t.code === code)?.label ?? null;
}
