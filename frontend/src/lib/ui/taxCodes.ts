/**
 * El nombre de cada código de tarifa del IVA (T-715, RN-76).
 *
 * **Son funciones, no constantes**, por lo mismo que en `fields.ts`: una
 * constante se evaluaría al importar el módulo —una vez por proceso de Node— y
 * congelaría el idioma de la primera petición para todas las demás.
 *
 * El código en sí no se traduce: `08` es `08` en los tres idiomas y es lo que
 * viaja en el XML. Lo que se traduce es qué significa.
 */

import { m } from '$lib/paraglide/messages.js';

const NOMBRES: Record<string, () => string> = {
	'01': () => m.inventory_tax_code_01(),
	'02': () => m.inventory_tax_code_02(),
	'03': () => m.inventory_tax_code_03(),
	'04': () => m.inventory_tax_code_04(),
	'05': () => m.inventory_tax_code_05(),
	'06': () => m.inventory_tax_code_06(),
	'07': () => m.inventory_tax_code_07(),
	'08': () => m.inventory_tax_code_08(),
	'09': () => m.inventory_tax_code_09(),
	'10': () => m.inventory_tax_code_10(),
	'11': () => m.inventory_tax_code_11()
};

/** «08 · General 13 %». El código adelante porque es lo que se busca. */
export function taxCodeLabel(code: string): string {
	const nombre = NOMBRES[code];
	return nombre ? `${code} · ${nombre()}` : code;
}
