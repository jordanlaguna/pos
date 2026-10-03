/**
 * La numeración que propone el alta de una compañía (QA-04).
 *
 * La identidad de un cliente es el par (afiliado, compañía) y la compañía se
 * cuenta **dentro** de su afiliado: «afiliado 1 · compañía 2» es otra cédula
 * del mismo dueño, y un afiliado nuevo empieza en la compañía 1 (spec, «La
 * identidad de un cliente»). El alta propone los dos para que soporte no tenga
 * que ir a mirar la lista; la unicidad la sigue cuidando la base.
 */

export interface CompanyPair {
	afiliado: number;
	compania: number;
}

/** El siguiente afiliado libre: uno más que el mayor, o 1 si no hay ninguno. */
export function nextAffiliate(pairs: readonly CompanyPair[]): number {
	return pairs.reduce((mayor, par) => Math.max(mayor, par.afiliado), 0) + 1;
}

/** La siguiente compañía de un afiliado: uno más que la mayor suya, o 1. */
export function nextCompanyOf(pairs: readonly CompanyPair[], afiliado: number): number {
	return (
		pairs
			.filter((par) => par.afiliado === afiliado)
			.reduce((mayor, par) => Math.max(mayor, par.compania), 0) + 1
	);
}
