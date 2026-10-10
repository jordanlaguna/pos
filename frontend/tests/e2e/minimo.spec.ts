import { expect, test } from '@playwright/test';
import { clicHasta, entrar } from './sesion';

/**
 * El mínimo por producto (T-1504, RN-101).
 *
 * Un producto con 3 unidades y mínimo propio 2 no avisa aunque el general sea
 * 10; subirle el mínimo a 5 lo pone en las alertas del panel y en el contador
 * de la lista. Lo que se crea queda con nombre propio y no se borra: no estorba
 * a nadie.
 */

function marca(): string {
	return `${Date.now()}`.slice(-8);
}

test.describe('Mínimo por producto', () => {
	test('el propio manda sobre el general', async ({ page }) => {
		await entrar(page);
		const sello = marca();
		const nombre = `Mínimo ${sello}`;

		// --- 1. Un producto con 3 y mínimo propio 2.
		await page.goto('/inventario');
		await clicHasta(page.getByRole('button', { name: /Nuevo producto/i }).first(), () =>
			expect(page.locator('#product-form input[name="name"]')).toBeVisible({ timeout: 1000 })
		);
		await page.locator('#product-form input[name="name"]').fill(nombre);
		await page.locator('#product-form input[name="description"]').fill(nombre);
		await page.locator('#product-form input[name="price"]').fill('1000');
		await page.locator('#product-form input[name="stock"]').fill('3');
		await page.locator('#product-form input[name="min_stock"]').fill('2');
		await page.locator('#product-form input[name="barcode"]').fill(`M${sello}`);
		await page.getByRole('button', { name: /Agregar producto/i }).click();
		const fila = page.locator('tr', { hasText: nombre }).first();
		await expect(fila).toBeVisible();
		await expect(fila.locator('[data-testid="stock-badge"]')).toHaveAttribute('data-low', 'false');

		// --- 2. No está en las alertas del panel: su mínimo es 2, no el general.
		await page.goto('/dashboard');
		await expect(page.getByRole('heading', { name: /Alertas de inventario/i })).toBeVisible();
		await expect(page.getByText(nombre, { exact: true })).toHaveCount(0);

		// --- 3. Con mínimo 5 sí avisa, en la lista y en el panel.
		await page.goto('/inventario');
		await clicHasta(
			page.locator('tr', { hasText: nombre }).first().getByRole('button', { name: /Editar/i }),
			() => expect(page.locator('#product-form input[name="min_stock"]')).toBeVisible({ timeout: 1000 })
		);
		await page.locator('#product-form input[name="min_stock"]').fill('5');
		await page.getByRole('button', { name: /Guardar cambios/i }).click();
		await expect(
			page.locator('tr', { hasText: nombre }).first().locator('[data-testid="stock-badge"]')
		).toHaveAttribute('data-low', 'true');

		await page.goto('/dashboard');
		const alerta = page.locator('tr', { hasText: nombre }).first();
		await expect(alerta).toBeVisible();
		await expect(alerta).toContainText('5');
	});
});
