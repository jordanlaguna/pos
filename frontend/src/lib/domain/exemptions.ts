/**
 * La exoneración del cliente, del lado del POS (T-717, RF-67, RN-78).
 *
 * Espejo de `backend/app/domain/fe_exemptions.py`. El servidor sigue siendo el
 * que manda y valida igual; esto es lo que permite que el formulario sepa qué
 * campo pedir **antes** de mandar, que es donde se arregla.
 *
 * **Son puntos de tarifa, no una tarifa**: nueve puntos sobre el 13 % dejan la
 * línea pagando 4 %. No existe ninguna tarifa del 9 %, así que guardar «4» o
 * «0.09» sería guardar el resultado en vez del dato.
 */

/** Una fila de la nota 10.1: qué clase de autorización es. */
export interface ExemptionType {
	code: string;
	/** Cuatro de los doce solo valen en notas de crédito y de débito. */
	onlyInNotes: boolean;
	/** Los que obligan a decir el artículo de la ley. */
	needsArticle: boolean;
	/** Los que Hacienda cruza contra su registro de exenciones. */
	verifiedByHacienda: boolean;
}

const tipo = (
	code: string,
	onlyInNotes = false,
	needsArticle = false,
	verifiedByHacienda = false
): ExemptionType => ({ code, onlyInNotes, needsArticle, verifiedByHacienda });

/** La nota 10.1 completa, en su orden. */
export const EXEMPTION_TYPES: readonly ExemptionType[] = [
	tipo('01', true),
	tipo('02', false, true),
	tipo('03', false, true),
	tipo('04', false, false, true),
	tipo('05', true),
	tipo('06', true, true),
	tipo('07', true, true),
	tipo('08', false, true),
	tipo('09'),
	tipo('10'),
	tipo('11', false, false, true),
	tipo('99')
];

/** Los que se le pueden poner a un cliente para facturarle. */
export const SELLABLE_EXEMPTION_TYPES = EXEMPTION_TYPES.filter((t) => !t.onlyInNotes);

/** La nota 23: quién emitió la exoneración. El `'99'` obliga a escribir cuál. */
export const EXEMPTION_INSTITUTIONS: readonly string[] = [
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
	'12',
	'99'
];

export const EXEMPTION_OTHER = '99';

/** La tarifa exonerada es `decimal 4,2`: cuatro dígitos con dos decimales. */
export const MAX_EXEMPTION_POINTS = 99.99;

/** Si ese tipo obliga a decir el artículo de la ley. */
export function exemptionNeedsArticle(code: string | null | undefined): boolean {
	return EXEMPTION_TYPES.find((t) => t.code === code)?.needsArticle ?? false;
}

/**
 * Si Hacienda va a cruzar ese documento contra su registro.
 *
 * Con los tipos `04` y `11` comprueba que exista, esté vigente y que los puntos
 * no excedan los autorizados. No se puede comprobar acá; lo que sí se puede es
 * avisar de que el rechazo llega después de emitir, con el cliente ya ido.
 */
export function exemptionVerifiedByHacienda(code: string | null | undefined): boolean {
	return EXEMPTION_TYPES.find((t) => t.code === code)?.verifiedByHacienda ?? false;
}
