/**
 * Los nombres de los catálogos de exoneración (T-717, RN-78).
 *
 * El anexo lo pide con todas las letras: «para efectos de impresión y
 * visualización se debe mostrar la descripción del código». Nadie reconoce una
 * exoneración por el `08`.
 *
 * **Son funciones, no constantes**, por lo mismo que en `fields.ts`: una
 * constante se evaluaría al importar el módulo —una vez por proceso de Node— y
 * congelaría el idioma de la primera petición para todas las demás.
 */

import { m } from '$lib/paraglide/messages.js';

const TIPOS: Record<string, () => string> = {
	'01': () => m.clients_exo_type_01(),
	'02': () => m.clients_exo_type_02(),
	'03': () => m.clients_exo_type_03(),
	'04': () => m.clients_exo_type_04(),
	'05': () => m.clients_exo_type_05(),
	'06': () => m.clients_exo_type_06(),
	'07': () => m.clients_exo_type_07(),
	'08': () => m.clients_exo_type_08(),
	'09': () => m.clients_exo_type_09(),
	'10': () => m.clients_exo_type_10(),
	'11': () => m.clients_exo_type_11(),
	'99': () => m.clients_exo_type_99()
};

const INSTITUCIONES: Record<string, () => string> = {
	'01': () => m.clients_exo_inst_01(),
	'02': () => m.clients_exo_inst_02(),
	'03': () => m.clients_exo_inst_03(),
	'04': () => m.clients_exo_inst_04(),
	'05': () => m.clients_exo_inst_05(),
	'06': () => m.clients_exo_inst_06(),
	'07': () => m.clients_exo_inst_07(),
	'08': () => m.clients_exo_inst_08(),
	'09': () => m.clients_exo_inst_09(),
	'10': () => m.clients_exo_inst_10(),
	'11': () => m.clients_exo_inst_11(),
	'12': () => m.clients_exo_inst_12(),
	'99': () => m.clients_exo_inst_99()
};

/** «08 · Exoneración a zona franca». El código adelante porque es lo que viaja. */
export function exemptionTypeLabel(code: string): string {
	const nombre = TIPOS[code];
	return nombre ? `${code} · ${nombre()}` : code;
}

/** «99 · Otra». */
export function exemptionInstitutionLabel(code: string): string {
	const nombre = INSTITUCIONES[code];
	return nombre ? `${code} · ${nombre()}` : code;
}
