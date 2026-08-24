import { describe, expect, it } from 'vitest';
import {
	buildTree,
	canHoldProducts,
	categoryPath,
	childrenOf,
	leafOptions,
	moveInOrder,
	withDescendants
} from './categories';
import type { Category } from './types';

/** Un catálogo de súper: dos raíces, una con rama y otra sin. */
const cat = (
	id: number,
	name: string,
	parent_id: number | null = null,
	sort_order = id,
	is_active = true
): Category => ({ id, name, parent_id, sort_order, is_active });

const CATALOGO: Category[] = [
	cat(1, 'Abarrotes', null, 1),
	cat(2, 'Bebidas', null, 2),
	cat(20, 'Gaseosas', 2, 2),
	cat(21, 'Cervezas', 2, 1),
	cat(3, 'Retirada', null, 3, false),
	cat(30, 'Hija de la retirada', 3, 1)
];

describe('buildTree', () => {
	it('arma una rama por raíz', () => {
		const arbol = buildTree(CATALOGO);
		expect(arbol.map((r) => r.root.name)).toEqual(['Abarrotes', 'Bebidas', 'Retirada']);
	});

	it('respeta el orden que eligió el dueño y no el alfabético', () => {
		// Cervezas está segunda en el catálogo y primera en el orden.
		const bebidas = buildTree(CATALOGO).find((r) => r.root.id === 2);
		expect(bebidas?.children.map((c) => c.name)).toEqual(['Cervezas', 'Gaseosas']);
	});

	it('una raíz sin hijas es una rama sin hijas, no una ausencia', () => {
		const abarrotes = buildTree(CATALOGO).find((r) => r.root.id === 1);
		expect(abarrotes?.children).toEqual([]);
	});

	it('con onlyActive esconde la raíz inactiva y su rama entera', () => {
		// Desactivar una raíz esconde sus hijas sin tocarlas: por eso la hija
		// sigue en la lista y aun así no aparece en ninguna rama.
		const arbol = buildTree(CATALOGO, { onlyActive: true });
		expect(arbol.map((r) => r.root.id)).toEqual([1, 2]);
		expect(arbol.flatMap((r) => r.children.map((c) => c.id))).not.toContain(30);
	});

	it('desempata por id cuando dos hermanas comparten orden', () => {
		const empatadas = [cat(9, 'B', null, 1), cat(8, 'A', null, 1)];
		expect(buildTree(empatadas).map((r) => r.root.id)).toEqual([8, 9]);
	});
});

describe('childrenOf', () => {
	it('devuelve las hijas en orden', () => {
		expect(childrenOf(CATALOGO, 2).map((c) => c.id)).toEqual([21, 20]);
	});

	it('una hoja no tiene hijas', () => {
		expect(childrenOf(CATALOGO, 1)).toEqual([]);
	});
});

describe('withDescendants', () => {
	it('la raíz incluye a sus hijas', () => {
		// Filtrar solo por el id de la raíz dejaría la pestaña «Bebidas» casi
		// vacía en cuanto alguien reparte su catálogo en subcategorías.
		expect(withDescendants(CATALOGO, 2)).toEqual([2, 21, 20]);
	});

	it('una hoja es ella misma', () => {
		expect(withDescendants(CATALOGO, 1)).toEqual([1]);
	});

	it('una subcategoría no arrastra a sus hermanas', () => {
		expect(withDescendants(CATALOGO, 21)).toEqual([21]);
	});
});

describe('leafOptions', () => {
	it('una raíz con hijas no es opción: lo son sus hijas (RN-6)', () => {
		expect(leafOptions(CATALOGO).map((c) => c.name)).toEqual([
			'Abarrotes',
			'Cervezas',
			'Gaseosas'
		]);
	});

	it('no ofrece las inactivas ni las hijas de una inactiva', () => {
		const ids = leafOptions(CATALOGO).map((c) => c.id);
		expect(ids).not.toContain(3);
		expect(ids).not.toContain(30);
	});
});

describe('categoryPath', () => {
	it('una raíz es un solo nombre', () => {
		expect(categoryPath(CATALOGO, 1)).toEqual(['Abarrotes']);
	});

	it('una subcategoría trae también su raíz', () => {
		expect(categoryPath(CATALOGO, 21)).toEqual(['Bebidas', 'Cervezas']);
	});

	it('una categoría que no está devuelve nada, no una fila rota', () => {
		expect(categoryPath(CATALOGO, 999)).toEqual([]);
	});

	it('si falta la raíz, al menos dice la hija', () => {
		// Puede pasar mientras una lista llega a medias; la pantalla muestra lo
		// que hay en vez de quedarse en blanco.
		expect(categoryPath([cat(5, 'Suelta', 99)], 5)).toEqual(['Suelta']);
	});
});

describe('moveInOrder', () => {
	it('sube una posición', () => {
		expect(moveInOrder([1, 2, 3], 2, 'up')).toEqual([2, 1, 3]);
	});

	it('baja una posición', () => {
		expect(moveInOrder([1, 2, 3], 2, 'down')).toEqual([1, 3, 2]);
	});

	it('la primera no sube y la última no baja', () => {
		expect(moveInOrder([1, 2, 3], 1, 'up')).toEqual([1, 2, 3]);
		expect(moveInOrder([1, 2, 3], 3, 'down')).toEqual([1, 2, 3]);
	});

	it('una que no está en la lista no mueve nada', () => {
		// Puede pasar si alguien deja la pantalla abierta y otra sesión borra la
		// categoría: mejor un reordenamiento que no hace nada que uno a medias.
		expect(moveInOrder([1, 2, 3], 99, 'up')).toEqual([1, 2, 3]);
	});

	it('no muta la lista que recibe', () => {
		const original = [1, 2, 3];
		moveInOrder(original, 2, 'up');
		expect(original).toEqual([1, 2, 3]);
	});
});

describe('canHoldProducts', () => {
	it('una hoja activa sí', () => {
		expect(canHoldProducts(CATALOGO, 1)).toBe(true);
		expect(canHoldProducts(CATALOGO, 21)).toBe(true);
	});

	it('una raíz con hijas no (RN-6)', () => {
		expect(canHoldProducts(CATALOGO, 2)).toBe(false);
	});

	it('una desactivada no', () => {
		expect(canHoldProducts(CATALOGO, 3)).toBe(false);
	});

	it('una que no existe no', () => {
		expect(canHoldProducts(CATALOGO, 999)).toBe(false);
	});

	it('una raíz cuya única hija está desactivada vuelve a ser hoja', () => {
		// La decisión: se cuentan las hijas activas. Contando las desactivadas,
		// esta rama no tendría dónde poner un producto —la raíz bloqueada por su
		// hija y la hija fuera de circulación— y habría que reactivar algo que el
		// dueño acaba de retirar. El servidor cuenta igual.
		const conHijaRetirada = [cat(1, 'Bebidas'), cat(10, 'Cervezas', 1, 1, false)];
		expect(canHoldProducts(conHijaRetirada, 1)).toBe(true);
	});
});
