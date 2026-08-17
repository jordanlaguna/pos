import { expect, test } from '@playwright/test';

import { CON_DATOS, VACIA, autenticar, elegirCompania, entrarAVentas } from './sesion';

/**
 * Elegir y cambiar de compañía (T-222, T-223, RF-27, RF-28, RN-27).
 *
 * Esto no se podía probar hasta que el modo simulado tuvo dos compañías
 * (T-228). Con una sola no hay pantalla de selección, no hay a dónde cambiar, y
 * la verificación que pedía T-223 —«con una venta a medias en A, cambiar a B
 * deja la pantalla de ventas vacía»— no tenía forma de ejecutarse.
 *
 * La segunda compañía del demo nace **vacía**, que es lo que de verdad pasa
 * cuando se da de alta una: sin catálogo, sin clientes, sin ventas. Eso hace
 * que el cambio se note de una forma que no se puede fingir.
 */

test.describe('elegir compañía', () => {
	test('las dos compañías se listan con su afiliado y su rol', async ({ page }) => {
		await autenticar(page);
		await expect(page).toHaveURL(/\/compania/);

		await expect(page.getByRole('button', { name: new RegExp(CON_DATOS, 'i') })).toBeVisible();
		await expect(page.getByRole('button', { name: new RegExp(VACIA, 'i') })).toBeVisible();
		await expect(page.getByText(/Afiliado 1 · Compañía 1/)).toBeVisible();
		await expect(page.getByText(/Afiliado 1 · Compañía 2/)).toBeVisible();
	});

	test('con el token de tránsito no se entra al POS', async ({ page }) => {
		// RN-26: autenticado pero sin compañía no autoriza nada. El POS devuelve
		// a la selección y no al login, porque la contraseña ya se escribió.
		await autenticar(page);
		await expect(page).toHaveURL(/\/compania/);

		await page.goto('/ventas');
		await expect(page).toHaveURL(/\/compania/);
	});

	test('cada compañía muestra la suya en el menú', async ({ page }) => {
		await autenticar(page);
		await elegirCompania(page, CON_DATOS);
		await expect(page.getByText(CON_DATOS).first()).toBeVisible();
		await expect(page.getByText(/Sucursal 001 · Caja 00001/)).toBeVisible();
	});
});

test.describe('cambiar de compañía', () => {
	test('la compañía nueva no ve el catálogo de la otra', async ({ page }) => {
		await entrarAVentas(page);
		await expect(page.getByRole('button', { name: /Arroz/i }).first()).toBeVisible();

		await page.getByRole('link', { name: /Cambiar de compañía/i }).click();
		await elegirCompania(page, VACIA);
		await page.goto('/ventas');

		await expect(page.getByRole('button', { name: /Arroz/i })).toHaveCount(0);
	});

	test('una venta a medias no se arrastra a la otra compañía', async ({ page }) => {
		/*
		 * La verificación que pedía T-223, y la razón por la que importa: las
		 * ventas en espera viven en `sessionStorage`, o sea en el navegador, donde
		 * el servidor no llega. Si nadie las limpia, al entrar a la otra compañía
		 * la pantalla de ventas aparece con artículos que no son de ese negocio
		 * —con sus precios y sus identificadores— y cobrarlos le carga a un
		 * negocio productos del otro.
		 */
		await entrarAVentas(page);

		// Una venta a medias: dos unidades adentro.
		const arroz = page.getByRole('button', { name: /Arroz/i }).first();
		await expect(async () => {
			await arroz.click();
			await expect(page.locator('[role="tablist"] button[role="tab"]').first()).toHaveText(
				'Venta 1 1',
				{ timeout: 1000 }
			);
		}).toPass({ timeout: 10_000 });
		await arroz.click();
		await expect(page.locator('[role="tablist"] button[role="tab"]').first()).toHaveText(
			'Venta 1 2'
		);

		await page.getByRole('link', { name: /Cambiar de compañía/i }).click();
		await elegirCompania(page, VACIA);
		await page.goto('/ventas');

		// La pestaña vuelve a estar vacía: sin contador, sin líneas.
		await expect(page.locator('[role="tablist"] button[role="tab"]')).toHaveText(['Venta 1']);
	});

	test('y al volver, la compañía original sigue con lo suyo', async ({ page }) => {
		// El carrito se limpia; el catálogo y las ventas de cada compañía, no.
		await entrarAVentas(page);

		await page.getByRole('link', { name: /Cambiar de compañía/i }).click();
		await elegirCompania(page, VACIA);
		await page.goto('/ventas');
		await expect(page.getByRole('button', { name: /Arroz/i })).toHaveCount(0);

		await page.getByRole('link', { name: /Cambiar de compañía/i }).click();
		await elegirCompania(page, CON_DATOS);
		await page.goto('/ventas');
		await expect(page.getByRole('button', { name: /Arroz/i }).first()).toBeVisible();
	});
});
