/**
 * El código CABYS, del lado del POS (T-504, T-505).
 *
 * Espejo de `backend/app/domain/cabys.py`, y a propósito: son las mismas tres
 * razones por las que un código puede estar mal, en el mismo orden. Que estén
 * las dos no es duplicación por descuido —el servidor sigue siendo el que
 * manda, y valida igual—, es lo que permite decirle a quien escribe que le
 * faltan dos dígitos sin gastar un viaje a internet.
 *
 * Acá no se habla con Hacienda ni se guarda nada: entran datos, salen reglas.
 */

/** Trece dígitos, ni uno más. Es la longitud del catálogo publicado. */
export const CABYS_CODE_LENGTH = 13;

/** Qué tiene de malo un código. Los mismos tres del backend. */
export type CabysCodeProblem = 'empty' | 'not_digits' | 'bad_length';

/** Una entrada del catálogo, tal como viaja: el código, qué es y cuánto paga. */
export interface CabysEntry {
	code: string;
	description: string;
	/** Entre 0 y 1: el 13 % es `0.13`. */
	tax_rate: number;
}

/** De dónde salió la respuesta. `cache` es «esto decía la última vez que hubo internet». */
export type CabysSource = 'hacienda' | 'cache';

export interface CabysAnswer {
	items: CabysEntry[];
	source: CabysSource;
	/** Cuándo se leyó de Hacienda lo que se devuelve. Solo viene con `cache`. */
	cached_at: string | null;
}

/**
 * Qué tiene de malo el código, o `null` si está bien.
 *
 * Se aceptan los espacios de alrededor —quien lo pega de una hoja de cálculo
 * los arrastra— y nada más. En particular **no** se rellena con ceros a la
 * izquierda: un código de doce dígitos no es uno de trece al que le falta algo,
 * es un código mal copiado, y adivinar cuál era es peor que rechazarlo.
 */
export function cabysCodeProblem(raw: string | null | undefined): CabysCodeProblem | null {
	const clean = (raw ?? '').trim();
	if (!clean) return 'empty';
	if (!/^\d+$/.test(clean)) return 'not_digits';
	if (clean.length !== CABYS_CODE_LENGTH) return 'bad_length';
	return null;
}

/** El código limpio, o `null` si no es uno. */
export function normalizeCabysCode(raw: string | null | undefined): string | null {
	const clean = (raw ?? '').trim();
	return cabysCodeProblem(clean) === null ? clean : null;
}

/**
 * Si la tarifa que puso el usuario no es la del catálogo (RN-11).
 *
 * Se puede cambiar —hay exoneraciones y casos especiales, y quien vende sabe de
 * su negocio más que una tabla— pero **se le avisa**. El aviso no es un
 * obstáculo: es lo que convierte un error de dedo en una decisión.
 *
 * Sin tarifa oficial no hay con qué comparar y no se avisa nada. Pasa cuando el
 * producto no está clasificado y cuando no hubo forma de leer el catálogo: un
 * aviso ahí sería inventarse una diferencia que nadie puede comprobar.
 */
export function differsFromOfficial(
	chosen: number | null | undefined,
	official: number | null | undefined
): boolean {
	if (chosen == null || official == null) return false;
	return chosen !== official;
}
