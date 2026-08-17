import { expect, test, type Page } from '@playwright/test';

import { entrar } from './sesion';

/**
 * Cada encabezado tiene que estar sobre su columna.
 *
 * Es la comprobación del defecto 12: `.num` alineaba a la derecha, pero en un
 * `<th>` perdía contra `.data-table thead th`, que tiene más especificidad. El
 * marcado estaba bien en las nueve pantallas; era una sola regla de CSS. Por
 * eso se comprueba con una prueba que recorre todas y no con una por pantalla.
 */

const PANTALLAS = [
	'/facturas',
	'/inventario',
	'/inventario/entradas',
	'/caja',
	'/clientes',
	'/usuarios',
	'/devoluciones',
	'/dashboard'
];

/** Columnas visibles de cada tabla, con la alineación de su título y su celda. */
async function columnas(page: Page) {
	return page.evaluate(() => {
		// `start`/`end` son lo mismo que `left`/`right` en un idioma que se lee
		// de izquierda a derecha; el navegador devuelve una u otra según el caso.
		const norm = (a: string) => (a === 'start' ? 'left' : a === 'end' ? 'right' : a);
		const salida: { columna: string; th: string; td: string; desfase: number }[] = [];

		for (const tabla of document.querySelectorAll('table.data-table')) {
			const ths = [...tabla.querySelectorAll('thead th')];
			const fila = tabla.querySelector('tbody tr');
			// Una tabla vacía muestra una sola celda con el estado vacío.
			if (!fila || fila.children.length !== ths.length) continue;

			ths.forEach((th, i) => {
				const td = fila.children[i] as HTMLElement;
				// Cabecera invisible (`sr-only`, como la de Acciones): no hay
				// nada que alinear con nada.
				if (!th.textContent?.trim() || th.querySelector('.sr-only')) return;

				const aTh = norm(getComputedStyle(th).textAlign);
				const aTd = norm(getComputedStyle(td).textAlign);
				const rTh = th.getBoundingClientRect();
				const rTd = td.getBoundingClientRect();

				salida.push({
					columna: th.textContent.trim(),
					th: aTh,
					td: aTd,
					// Distancia entre el borde por el que se alinea cada uno.
					desfase: Math.abs(
						(aTh === 'right' ? rTh.right : rTh.left) -
							(aTd === 'right' ? rTd.right : rTd.left)
					)
				});
			});
		}
		return salida;
	});
}

test.describe('alineación de las tablas', () => {
	test('ningún encabezado se alinea distinto que su columna', async ({ page }) => {
		await entrar(page);
		let revisadas = 0;

		for (const ruta of PANTALLAS) {
			await page.goto(ruta);
			await page.waitForSelector('table.data-table, [data-empty]', { timeout: 10_000 }).catch(() => {});

			for (const c of await columnas(page)) {
				expect(
					c.th,
					`${ruta} · columna «${c.columna}»: el título va a la ${c.th} y los valores a la ${c.td}`
				).toBe(c.td);
				// El borde por el que se alinean tiene que ser el mismo, no uno
				// parecido: si difieren, el relleno de `th` y `td` se separó.
				expect(c.desfase, `${ruta} · columna «${c.columna}»`).toBeLessThanOrEqual(1);
				revisadas++;
			}
		}

		// Si un cambio deja las tablas sin filas, la prueba pasaría sin mirar
		// nada. Esto lo impide.
		expect(revisadas, 'no se revisó ninguna columna: ¿las tablas quedaron vacías?').toBeGreaterThan(20);
	});

	test('las columnas de plata van a la derecha', async ({ page }) => {
		await entrar(page);
		await page.goto('/facturas');

		for (const titulo of ['Subtotal', 'IVA', 'Total']) {
			const th = page.locator('table.data-table thead th', { hasText: new RegExp(`^${titulo}$`) });
			await expect(th).toHaveCSS('text-align', 'right');
		}
	});
});
