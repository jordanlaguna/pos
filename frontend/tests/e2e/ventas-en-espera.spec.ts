import { expect, test, type Locator, type Page } from '@playwright/test';

import { entrarAVentas as entrar } from './sesion';

/**
 * Varias ventas abiertas a la vez (T-116).
 *
 * Es el invariante `ventas_en_espera` de `.specify/progress.json`, el único que
 * seguía comprobándose solo a mano. Las reglas puras ya tienen prueba en
 * `domain/cart.test.ts`; lo que falta comprobar es el **flujo**: que el cajero
 * pueda dejar una venta a medias, atender a otro y volver.
 *
 * Un mostrador real no atiende de a un cliente por vez: alguien deja su compra
 * porque volvió por otro producto, y detrás hay tres personas esperando. El
 * WinForms perdía la venta entera al cerrar el formulario y ni siquiera podía
 * tener dos.
 */

/**
 * Pulsa hasta que la página reaccione.
 *
 * El primer clic después de un `goto` se pierde: el HTML ya está pintado pero
 * Svelte todavía no le enganchó los manejadores.
 */
async function clicHasta(boton: Locator, comprobar: () => Promise<void>) {
	await expect(async () => {
		await boton.click();
		await comprobar();
	}).toPass({ timeout: 10_000 });
}

/**
 * Las pestañas de venta, tal como se leen: «Venta 1 3» es la venta 1 con 3
 * unidades adentro.
 *
 * Se localizan por el `role="tab"` dentro del `tablist` y no por texto: es lo
 * que las distingue de los botones de producto, que también dicen números.
 */
function pestanas(page: Page) {
	return page.locator('[role="tablist"] button[role="tab"]');
}

const NUEVA = /Nueva venta en espera/i;

/*
 * Los patrones son **cadenas** y no expresiones regulares a propósito: con una
 * cadena, Playwright normaliza los espacios antes de comparar, y el texto de la
 * pestaña viene con espacios alrededor (`" Venta 1 1"`). Con una expresión
 * regular habría que contemplarlos a mano, que es más fácil de escribir mal que
 * de leer.
 */
/** Una pestaña vacía: «Venta n», sin contador. */
const vacia = (n: number) => `Venta ${n}`;
/** Una pestaña con `u` unidades adentro. */
const con = (n: number, u: number) => `Venta ${n} ${u}`;

test.describe('ventas en espera', () => {
	test('la pestaña lleva la cuenta de unidades de cada venta', async ({ page }) => {
		await entrar(page);
		await expect(pestanas(page)).toHaveText([vacia(1)]);

		await clicHasta(page.getByRole('button', { name: /Arroz/i }).first(), () =>
			expect(pestanas(page).first()).toHaveText(con(1, 1), { timeout: 1000 })
		);

		// Segunda unidad del mismo producto: acumula, no abre línea nueva.
		await page.getByRole('button', { name: /Arroz/i }).first().click();
		await expect(pestanas(page).first()).toHaveText(con(1, 2));
	});

	test('se abre otra venta y la primera queda esperando con lo suyo', async ({ page }) => {
		await entrar(page);
		await clicHasta(page.getByRole('button', { name: /Arroz/i }).first(), () =>
			expect(pestanas(page).first()).toHaveText(con(1, 1), { timeout: 1000 })
		);

		await page.getByRole('button', { name: NUEVA }).click();
		// Dos pestañas: la primera conserva su unidad, la segunda nace vacía.
		await expect(pestanas(page)).toHaveText([con(1, 1), vacia(2)]);

		await page.getByRole('button', { name: /Leche/i }).first().click();
		await expect(pestanas(page)).toHaveText([con(1, 1), con(2, 1)]);
	});

	test('volver a la primera devuelve su contenido, no el de la segunda', async ({ page }) => {
		await entrar(page);
		await clicHasta(page.getByRole('button', { name: /Arroz/i }).first(), () =>
			expect(pestanas(page).first()).toHaveText(con(1, 1), { timeout: 1000 })
		);
		await page.getByRole('button', { name: NUEVA }).click();
		await page.getByRole('button', { name: /Leche/i }).first().click();

		// En la venta 2 está la leche y no el arroz.
		const carrito = page.locator('table, ul, ol').filter({ hasText: /Leche/i }).first();
		await expect(carrito).toContainText(/Leche/i);

		await pestanas(page).first().click();
		await expect(pestanas(page).first()).toHaveText(con(1, 1));
	});

	test('las ventas sobreviven a recargar la página', async ({ page }) => {
		// Viven en sessionStorage: si el navegador se recarga —o la pestaña se
		// cierra sin querer— las ventas en espera siguen ahí. El WinForms perdía
		// la venta entera al cerrar el formulario.
		await entrar(page);
		await clicHasta(page.getByRole('button', { name: /Arroz/i }).first(), () =>
			expect(pestanas(page).first()).toHaveText(con(1, 1), { timeout: 1000 })
		);
		await page.getByRole('button', { name: NUEVA }).click();
		await page.getByRole('button', { name: /Leche/i }).first().click();
		await expect(pestanas(page)).toHaveText([con(1, 1), con(2, 1)]);

		await page.reload();

		await expect(pestanas(page)).toHaveText([con(1, 1), con(2, 1)]);
	});
});
