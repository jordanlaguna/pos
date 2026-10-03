import { expect, test } from '@playwright/test';

import { clicHasta, entrar } from './sesion';

/**
 * Guardar deja abierta la pestaña desde la que se guardó.
 *
 * Guardar recarga la pantalla entera, para que la moneda y el acento nuevos
 * lleguen a todo el POS. Con la pestaña solo en memoria, la recarga volvía
 * siempre a Negocio: quien acababa de cambiar la moneda tenía que ir a
 * buscarla para ver si se había guardado. Ahora viaja en la dirección.
 *
 * El nombre de la pestaña era «Moneda e impuesto» hasta QA-05.
 *
 * Se guarda sin cambiar nada: guardar dos veces lo mismo es inocuo, y así la
 * prueba no le mueve la configuración al resto de la suite.
 */
test('guardar no lo devuelve a la pestaña Negocio', async ({ page }) => {
	await entrar(page);
	await page.goto('/configuracion');

	const moneda = page.locator('#moneda-preset');
	const nombre = page.locator('input[name="negocio_nombre"]');
	await clicHasta(page.getByRole('button', { name: 'Moneda', exact: true }), async () => {
		await expect(moneda).toBeVisible();
	});
	await expect(page).toHaveURL(/[?&]seccion=moneda/);

	// QA-05: el impuesto ya no se escribe acá; la pestaña dice de dónde sale.
	await expect(page.locator('input[name="impuesto_tasa"]')).toHaveCount(0);
	await expect(page.locator('[data-impuesto-de-ley]')).toBeVisible();

	const recarga = page.waitForEvent('load');
	await page.getByRole('button', { name: /Guardar cambios/i }).click();
	await recarga;

	await expect(page).toHaveURL(/[?&]seccion=moneda/);
	await expect(moneda).toBeVisible();
	await expect(nombre).toBeHidden();
});

test('sin pestaña en la dirección abre Negocio, y una que no existe también', async ({ page }) => {
	await entrar(page);
	for (const ruta of ['/configuracion', '/configuracion?seccion=otra']) {
		await page.goto(ruta);
		await expect(page.locator('input[name="negocio_nombre"]')).toBeVisible();
	}
});
