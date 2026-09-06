import { describe, expect, it } from 'vitest';
import {
	MAX_TICKETS,
	canAdd,
	canSetQuantity,
	newLine,
	nextActiveId,
	quickCash,
	reservedElsewhere,
	saleNumber,
	unitCount,
	type Decision
} from './cart';
import type { CartLine, Product } from './types';

/*
 * Desde T-804 el dominio devuelve código y datos, no frases. Estas pruebas
 * afirman **qué código sale de qué situación**, que es la regla; que la frase
 * esté bien escrita es cosa del catálogo. Antes comparaban la cadena, y con eso
 * cualquier cambio de redacción rompía una prueba de lógica.
 */

/** Estrecha la unión al caso «sí». Falla nombrando el código si salió que no. */
function aceptado(d: Decision) {
	if (!d.ok) return expect.fail(`se esperaba que sí, y salió «${d.reason.code}»`);
	return d;
}

/** Estrecha la unión al caso «no» y devuelve el motivo. */
function rechazo(d: Decision) {
	if (d.ok) return expect.fail('se esperaba un rechazo y salió que sí');
	return d.reason;
}

function producto(stock: number, nombre = 'Arroz 1 kg'): Product {
	return {
		id_product: 1,
		name: nombre,
		description: '',
		price: 1450,
		stock,
		barcode: '7441029001057',
		created_at: '2026-01-01T00:00:00',
		category_id: 1
	};
}

function linea(cantidad: number, stock = 10, id = 1): CartLine {
	return {
		id_product: id,
		barcode: '7441029001057',
		name: 'Arroz 1 kg',
		price: 1450,
		quantity: cantidad,
		stock
	};
}

describe('reservedElsewhere', () => {
	const ventas = [
		{ id: 1, lines: [linea(2)] },
		{ id: 2, lines: [linea(3)] },
		{ id: 3, lines: [] }
	];

	it('suma lo apartado en las otras ventas', () => {
		expect(reservedElsewhere(ventas, 1, 1)).toBe(3);
		expect(reservedElsewhere(ventas, 2, 1)).toBe(2);
		expect(reservedElsewhere(ventas, 3, 1)).toBe(5);
	});

	it('no cuenta la venta activa', () => {
		expect(reservedElsewhere([{ id: 1, lines: [linea(4)] }], 1, 1)).toBe(0);
	});

	it('un producto que no está en ninguna no aparta nada', () => {
		expect(reservedElsewhere(ventas, 1, 99)).toBe(0);
	});
});

describe('unitCount', () => {
	it('suma las unidades, no las líneas', () => {
		expect(unitCount([linea(2), linea(3, 10, 2)])).toBe(5);
		expect(unitCount([])).toBe(0);
	});
});

describe('canAdd', () => {
	it('acepta lo que cabe', () => {
		expect(aceptado(canAdd(producto(10), 3, undefined, 0)).quantity).toBe(3);
	});

	it('acumula sobre lo que ya lleva la línea', () => {
		// Igual que `AddProductToSaleTable` del original, pero validando el stock
		// contra el total resultante y no solo contra lo nuevo.
		expect(aceptado(canAdd(producto(10), 2, linea(3), 0)).quantity).toBe(5);
	});

	it('rechaza cantidades que no tienen sentido', () => {
		for (const q of [0, -1]) {
			expect(rechazo(canAdd(producto(10), q, undefined, 0))).toEqual({
				code: 'cart_quantity_not_positive'
			});
		}
	});

	it('rechaza un producto sin existencias', () => {
		expect(rechazo(canAdd(producto(0), 1, undefined, 0))).toEqual({
			code: 'cart_out_of_stock',
			product: 'Arroz 1 kg'
		});
	});

	it('rechaza pasarse del stock', () => {
		expect(rechazo(canAdd(producto(3), 5, undefined, 0))).toEqual({
			code: 'cart_only_units',
			stock: 3,
			product: 'Arroz 1 kg'
		});
	});

	it('y lo dice contando lo que ya llevaba', () => {
		expect(rechazo(canAdd(producto(3), 2, linea(2), 0))).toEqual({
			code: 'cart_only_units_with_current',
			stock: 3,
			product: 'Arroz 1 kg',
			current: 2
		});
	});

	it('descuenta lo apartado en otras ventas', () => {
		/*
		 * La regla que importa. Si quedan 3 y la venta en espera tiene 2, acá solo
		 * entra 1: si no, al cobrar la segunda el backend la rechaza y el cajero se
		 * entera con el cliente enfrente.
		 */
		expect(canAdd(producto(3), 1, undefined, 2).ok).toBe(true);

		expect(rechazo(canAdd(producto(3), 2, undefined, 2))).toEqual({
			code: 'cart_reserved_elsewhere',
			free: 1,
			product: 'Arroz 1 kg',
			reserved: 2
		});
	});

	it('cuando lo apartado supera el stock, lo libre es cero y no negativo', () => {
		expect(rechazo(canAdd(producto(3), 1, undefined, 5))).toEqual({
			code: 'cart_reserved_elsewhere',
			free: 0,
			product: 'Arroz 1 kg',
			reserved: 5
		});
	});

	it('llenar el stock exacto sí se puede', () => {
		expect(canAdd(producto(3), 3, undefined, 0).ok).toBe(true);
		expect(canAdd(producto(3), 1, undefined, 2).ok).toBe(true);
	});
});

describe('canSetQuantity', () => {
	it('fija la cantidad exacta', () => {
		expect(aceptado(canSetQuantity(linea(2), 5, 0)).quantity).toBe(5);
	});

	it('trunca los decimales', () => {
		expect(aceptado(canSetQuantity(linea(2), 3.9, 0)).quantity).toBe(3);
	});

	it('cero o menos significa quitar la línea', () => {
		for (const q of [0, -3]) {
			expect(aceptado(canSetQuantity(linea(2), q, 0)).quantity).toBe(0);
		}
	});

	it('rechaza pasarse del stock', () => {
		expect(rechazo(canSetQuantity(linea(2, 10), 11, 0))).toEqual({
			code: 'cart_only_free_units',
			free: 10,
			product: 'Arroz 1 kg'
		});
	});

	it('descuenta lo apartado en otras ventas', () => {
		expect(rechazo(canSetQuantity(linea(2, 10), 9, 3))).toEqual({
			code: 'cart_only_free_units',
			free: 7,
			product: 'Arroz 1 kg'
		});
	});

	it('llegar justo al tope se puede', () => {
		expect(canSetQuantity(linea(2, 10), 7, 3).ok).toBe(true);
	});
});

describe('newLine', () => {
	it('copia del catálogo lo que la venta necesita', () => {
		const l = newLine(producto(10), 3);
		expect(l).toEqual({
			id_product: 1,
			barcode: '7441029001057',
			name: 'Arroz 1 kg',
			price: 1450,
			quantity: 3,
			stock: 10,
			// Sin clasificar: la venta le aplicará la tasa configurada (RN-9).
			taxRate: null
		});
	});

	it('copia la tarifa del producto, como copia el precio (F5, RN-9)', () => {
		// Sin esto el carrito le aplicaba a todo la configurada, y una venta con
		// tarifas mezcladas llegaba al servidor con un impuesto que no cuadraba:
		// el servidor recalcula por línea y la rechazaba con `totals_mismatch`.
		expect(newLine({ ...producto(10), tax_rate: 0.02 }, 1).taxRate).toBe(0.02);
	});

	it('el 0 % se copia y no se confunde con «sin clasificar»', () => {
		// Un libro infantil paga 0 % de verdad. Si `0` cayera a la configurada,
		// el único producto exonerado sería el que pagaría el 13 %.
		expect(newLine({ ...producto(10), tax_rate: 0 }, 1).taxRate).toBe(0);
	});
});

describe('nextActiveId', () => {
	const ventas = [{ id: 1, lines: [] }, { id: 2, lines: [] }, { id: 3, lines: [] }];

	it('pasa a la de la izquierda', () => {
		expect(nextActiveId(ventas, 2)).toBe(2);
	});

	it('o a la primera si se cerró la primera', () => {
		expect(nextActiveId(ventas, 0)).toBe(2);
	});

	it('null si no queda ninguna', () => {
		expect(nextActiveId([{ id: 1, lines: [] }], 0)).toBeNull();
	});
});

describe('MAX_TICKETS', () => {
	it('son ocho: más que eso se pierde el hilo', () => {
		expect(MAX_TICKETS).toBe(8);
	});
});

describe('saleNumber', () => {
	it('es yyyyMMddHHmmss, como generaba Bills.cs', () => {
		expect(saleNumber(new Date(2026, 7, 16, 21, 43, 5))).toBe('20260816214305');
	});

	it('rellena con ceros a la izquierda', () => {
		expect(saleNumber(new Date(2026, 0, 2, 3, 4, 5))).toBe('20260102030405');
	});

	it('tiene siempre 14 dígitos, que es lo que valida la acción', () => {
		const n = saleNumber(new Date(2026, 11, 31, 23, 59, 59));
		expect(n).toMatch(/^\d{14}$/);
	});
});

describe('quickCash', () => {
	it('ofrece el exacto y los redondeos al alza', () => {
		// Los pasos son los billetes que circulan en Costa Rica.
		expect(quickCash(4915.5)).toEqual([4915.5, 5000, 10000, 20000]);
	});

	it('no repite cuando el total ya es redondo', () => {
		expect(quickCash(5000)).toEqual([5000, 10000, 20000]);
	});

	it('nunca ofrece menos que el total', () => {
		for (const total of [1, 999, 4915.5, 23400]) {
			for (const m of quickCash(total)) expect(m).toBeGreaterThanOrEqual(total);
		}
	});

	it('como mucho cinco opciones: más no caben en la pantalla', () => {
		expect(quickCash(1).length).toBeLessThanOrEqual(5);
	});

	it('sin total no hay nada que sugerir', () => {
		expect(quickCash(0)).toEqual([]);
		expect(quickCash(-100)).toEqual([]);
	});
});
