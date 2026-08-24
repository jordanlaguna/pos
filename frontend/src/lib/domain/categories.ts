/**
 * El árbol del catálogo, del lado del POS (F4).
 *
 * Dos niveles: raíces y subcategorías. Acá está solo el armado del árbol y las
 * preguntas que le hacen las tres pantallas —la grilla de ventas, el filtro del
 * inventario y la ficha del producto—. Sin Svelte, sin `fetch` y sin catálogo de
 * textos: los nombres los pone el servidor y los rótulos, la interfaz.
 *
 * El backend manda la lista plana, ya ordenada, con activas e inactivas. Quién
 * esconde a las inactivas es cada pantalla, y no es lo mismo en todas: la grilla
 * de ventas no las muestra nunca, y el inventario tiene que poder nombrar la
 * categoría de un producto viejo y volver a activarla.
 */

import type { Category } from './types';

/** Una raíz con sus hijas, que es como se navega en las dos pantallas. */
export interface CategoryBranch {
	root: Category;
	children: Category[];
}

const byOrder = (a: Category, b: Category) =>
	a.sort_order - b.sort_order || a.id - b.id;

/**
 * La lista plana convertida en ramas.
 *
 * `onlyActive` esconde las inactivas —y con ellas su rama entera: desactivar una
 * raíz esconde sus hijas sin tocarlas, que es lo que permite volver a activarla
 * y encontrarla como estaba—.
 */
export function buildTree(
	categories: Category[],
	{ onlyActive = false }: { onlyActive?: boolean } = {}
): CategoryBranch[] {
	const visible = onlyActive ? categories.filter((c) => c.is_active) : categories;
	const roots = visible.filter((c) => c.parent_id === null).sort(byOrder);
	return roots.map((root) => ({
		root,
		children: visible.filter((c) => c.parent_id === root.id).sort(byOrder)
	}));
}

/** Las hijas de una categoría, en su orden. */
export function childrenOf(categories: Category[], parentId: number): Category[] {
	return categories.filter((c) => c.parent_id === parentId).sort(byOrder);
}

/**
 * La categoría y sus hijas, por id.
 *
 * Es lo que necesita filtrar por una raíz: los productos de «Bebidas» son los
 * suyos **más** los de «Cervezas» y «Gaseosas». Filtrar solo por el id de la
 * raíz mostraría una pestaña casi vacía en cuanto alguien reparte su catálogo
 * en subcategorías.
 */
export function withDescendants(categories: Category[], categoryId: number): number[] {
	return [categoryId, ...childrenOf(categories, categoryId).map((c) => c.id)];
}

/**
 * Dónde se puede colgar un producto (RN-6): las hojas.
 *
 * Una raíz sin hijas es una hoja y admite productos; en cuanto tiene hijas, los
 * productos van en ellas. Solo las activas: colgar un producto de una categoría
 * que el dueño sacó de circulación lo esconde (el backend lo rechaza igual).
 */
export function leafOptions(categories: Category[]): Category[] {
	return buildTree(categories, { onlyActive: true }).flatMap(({ root, children }) =>
		children.length === 0 ? [root] : children
	);
}

/**
 * Los nombres desde la raíz hasta la categoría, para mostrarla.
 *
 * Devuelve nombres y no una frase con separador: cómo se une —una flecha, dos
 * puntos, un salto de línea— es decisión de la pantalla, y el dominio no
 * escribe texto para nadie (RN-30).
 */
export function categoryPath(categories: Category[], categoryId: number): string[] {
	const category = categories.find((c) => c.id === categoryId);
	if (!category) return [];
	if (category.parent_id === null) return [category.name];
	const parent = categories.find((c) => c.id === category.parent_id);
	return parent ? [parent.name, category.name] : [category.name];
}

/**
 * Sube o baja una categoría un lugar entre sus hermanas.
 *
 * Devuelve la lista completa en el orden nuevo, que es lo que el API espera.
 * Reordenar es un botón y no arrastrar: así funciona sin JavaScript como el
 * resto del POS, y en una pantalla táctil de caja arrastrar es peor.
 *
 * En el borde no pasa nada: la primera no sube. Devolver la lista igual en vez
 * de rechazar deja que la pantalla muestre el botón siempre —deshabilitarlo en
 * el borde es cosa de la vista— sin arriesgar un reordenamiento a medias.
 */
export function moveInOrder(ids: number[], id: number, direction: 'up' | 'down'): number[] {
	const desde = ids.indexOf(id);
	if (desde === -1) return [...ids];
	const hasta = direction === 'up' ? desde - 1 : desde + 1;
	if (hasta < 0 || hasta >= ids.length) return [...ids];
	const nuevo = [...ids];
	[nuevo[desde], nuevo[hasta]] = [nuevo[hasta], nuevo[desde]];
	return nuevo;
}

/**
 * ¿Esta categoría admite productos?
 *
 * La misma pregunta que hace el backend antes de aceptar el alta, para poder
 * avisar en la pantalla en vez de esperar el «no» del servidor.
 *
 * Cuenta las hijas **activas**, igual que el servidor: una raíz a la que le
 * desactivaron su única subcategoría vuelve a ser una hoja. Contando las
 * desactivadas, esa rama se quedaría sin ningún sitio donde poner un producto.
 */
export function canHoldProducts(categories: Category[], categoryId: number): boolean {
	const category = categories.find((c) => c.id === categoryId);
	if (!category || !category.is_active) return false;
	return childrenOf(categories, categoryId).filter((c) => c.is_active).length === 0;
}
