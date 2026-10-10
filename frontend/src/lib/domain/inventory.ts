/**
 * El inventario a fondo (F15): lo que el POS decide solo, sin backend.
 *
 * Por ahora, el mínimo (RN-101). Es la misma regla que `below_minimum` en
 * `domain/inventory.py`: el reporte, el aviso del panel y la lista de
 * inventario tienen que decir lo mismo, y lo dicen por la misma función.
 */

/**
 * Si un producto está bajo mínimo (RN-101).
 *
 * Manda el mínimo propio; sin él, el general de la compañía; sin ninguno de
 * los dos, nunca. Se compara la existencia **total** —la suma de las
 * sucursales— y el mínimo cuenta: con 10 y mínimo 10 ya está bajo.
 *
 *     5 con mínimo 10            → sí
 *     10 con mínimo 10           → sí
 *     5 sin mínimo y general 3   → no
 *     5 sin mínimo y sin general → no
 */
export function belowMinimum(
	total: number,
	minStock: number | null | undefined,
	defaultMin: number | null
): boolean {
	const minimo = minStock ?? defaultMin;
	if (minimo === null) return false;
	return total <= minimo;
}

/** El mínimo que se aplica a un producto: el propio o el general, o ninguno. */
export function effectiveMinimum(
	minStock: number | null | undefined,
	defaultMin: number | null
): number | null {
	return minStock ?? defaultMin;
}
