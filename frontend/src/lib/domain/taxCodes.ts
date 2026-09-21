/**
 * El código de tarifa del IVA, del lado del POS (T-715, RN-76).
 *
 * Espejo de `backend/app/domain/fe_tax_codes.py`, y a propósito: el servidor
 * sigue siendo el que manda —recalcula la tarifa desde el código en cada
 * guardado—, pero sin esta tabla acá el formulario no podría enseñar qué
 * porcentaje va a quedar hasta después de guardar.
 *
 * **Once códigos para nueve porcentajes.** El catálogo no es una lista de tasas
 * sino de situaciones: el 0 % del artículo 32 del reglamento —ventas a la CCSS,
 * a una municipalidad— da derecho a crédito pleno y el 0 % del código `11` no da
 * ninguno. Por eso de un código sale siempre una tarifa y de una tarifa no
 * siempre sale un código.
 */

/** Una fila de la nota 8.1 del anexo v4.4. */
export interface TaxCodeEntry {
	code: string;
	/** Entre 0 y 1: el 13 % es `0.13`. */
	rate: number;
	/** Los transitorios solo valen en notas de crédito y de débito. */
	onlyInNotes: boolean;
}

/** La nota 8.1 completa, en su orden. */
export const TAX_CODES: readonly TaxCodeEntry[] = [
	{ code: '01', rate: 0, onlyInNotes: false },
	{ code: '02', rate: 0.01, onlyInNotes: false },
	{ code: '03', rate: 0.02, onlyInNotes: false },
	{ code: '04', rate: 0.04, onlyInNotes: false },
	{ code: '05', rate: 0, onlyInNotes: true },
	{ code: '06', rate: 0.04, onlyInNotes: true },
	{ code: '07', rate: 0.08, onlyInNotes: true },
	{ code: '08', rate: 0.13, onlyInNotes: false },
	{ code: '09', rate: 0.005, onlyInNotes: false },
	{ code: '10', rate: 0, onlyInNotes: false },
	{ code: '11', rate: 0, onlyInNotes: false }
];

/** La general, del 13 %. */
export const TAX_CODE_GENERAL = '08';

/**
 * Los que se le pueden poner a un producto.
 *
 * Los transitorios quedan fuera: existen solo para corregir con una nota de
 * crédito una factura de cuando esas tarifas regían, así que ofrecerlos en la
 * ficha de un producto es ofrecer un rechazo.
 */
export const SELLABLE_TAX_CODES = TAX_CODES.filter((t) => !t.onlyInNotes);

/** La tarifa de ese código, o `null` si el código no existe. */
export function rateForTaxCode(code: string | null | undefined): number | null {
	const fila = TAX_CODES.find((t) => t.code === (code ?? '').trim());
	return fila ? fila.rate : null;
}

/**
 * El código que le toca a una tarifa, o `null` si hay más de uno.
 *
 * `null` es «hay que preguntar», y es la respuesta correcta en el 0 %: entre el
 * `01`, el `10` y el `11` no decide la aritmética sino qué se vende y a quién.
 * Proponer uno sería elegirle a quien factura el derecho a crédito de su
 * cliente.
 */
export function suggestedTaxCode(rate: number | null | undefined): string | null {
	if (rate == null) return null;
	const posibles = SELLABLE_TAX_CODES.filter((t) => t.rate === rate);
	return posibles.length === 1 ? posibles[0].code : null;
}
