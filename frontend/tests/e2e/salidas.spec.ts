import { expect, test } from '@playwright/test';
import { clicHasta, entrar } from './sesion';

/**
 * Salidas con motivo, de punta a punta (T-1502, F15).
 *
 * Un motivo propio, un producto propio con existencia, una salida con los dos,
 * su fila en el kárdex y su anulación. Todo es de esta prueba: no se toca lo
 * que otras usan, que es la lección de T-310.
 */

/** Único por corrida: el simulado guarda su estado en disco. */
function marca(): string {
	return `${Date.now()}`.slice(-8);
}

test.describe('Salidas con motivo', () => {
	test('motivo nuevo, salida, kárdex y anulación', async ({ page }) => {
		await entrar(page);
		const sello = marca();
		const nombre = `Merma ${sello}`;

		// --- 1. Un producto propio con 10 unidades: nace con su apertura.
		await page.goto('/inventario');
		await clicHasta(page.getByRole('button', { name: /Nuevo producto/i }).first(), () =>
			expect(page.locator('#product-form input[name="name"]')).toBeVisible({ timeout: 1000 })
		);
		await page.locator('#product-form input[name="name"]').fill(nombre);
		await page.locator('#product-form input[name="description"]').fill(nombre);
		await page.locator('#product-form input[name="price"]').fill('1000');
		await page.locator('#product-form input[name="stock"]').fill('10');
		await page.locator('#product-form input[name="barcode"]').fill(`S${sello}`);
		await page.getByRole('button', { name: /Agregar producto/i }).click();
		await expect(page.getByText(nombre, { exact: true }).first()).toBeVisible();

		// --- 2. Un motivo propio.
		await page.goto('/inventario/motivos');
		await page.locator('input[name="code"]').fill(`rotura_${sello}`);
		await page.locator('input[name="name"]').fill(`Rotura ${sello}`);
		await page.getByRole('button', { name: /^Agregar$/ }).click();
		await expect(page.locator(`[data-code="rotura_${sello}"]`)).toBeVisible();

		// --- 3. La salida: 3 unidades con ese motivo.
		await page.goto('/inventario/salidas/nueva');
		await page.locator('select[name="reason_id"]').selectOption({ label: `Rotura ${sello}` });
		const buscar = page.locator('input[type="search"]');
		await expect(async () => {
			await buscar.fill(nombre);
			await expect(page.getByRole('button', { name: nombre }).first()).toBeVisible({ timeout: 1000 });
		}).toPass({ timeout: 10_000 });
		await page.getByRole('button', { name: nombre }).first().click();
		await page.locator('input[type="number"][aria-label*="antidad"]').first().fill('3');
		await page.getByRole('button', { name: /Confirmar salida/i }).click();
		await expect(page).toHaveURL(/\/inventario\/salidas\?creada=/);
		const fila = page.locator('[data-testid="exit-row"]').first();
		await expect(fila).toContainText(`Rotura ${sello}`);
		await expect(fila).toHaveAttribute('data-status', 'applied');

		// --- 4. El kárdex del producto: la salida y la apertura, y quedan 7.
		await page.goto('/inventario');
		await page.getByRole('link', { name: `Kárdex de ${nombre}` }).click();
		await expect(page.locator('[data-testid="kardex-stock"]')).toHaveText('7');
		const filas = page.locator('[data-testid="kardex-row"]');
		await expect(filas.first()).toHaveAttribute('data-kind', 'exit');
		await expect(filas.last()).toHaveAttribute('data-kind', 'opening');

		// --- 5. Anular con motivo: la existencia vuelve a 10.
		await page.goto('/inventario/salidas');
		await clicHasta(page.getByRole('button', { name: /Anular la salida/ }).first(), () =>
			expect(page.locator('#motivo-anular')).toBeVisible({ timeout: 1000 })
		);
		await page.locator('#motivo-anular').fill('se contó mal');
		await page.getByRole('button', { name: /^Anular salida$/ }).click();
		await expect(page.locator('[data-testid="exit-row"]').first()).toHaveAttribute(
			'data-status',
			'voided'
		);

		await page.goto('/inventario');
		await page.getByRole('link', { name: `Kárdex de ${nombre}` }).click();
		await expect(page.locator('[data-testid="kardex-stock"]')).toHaveText('10');
		await expect(page.locator('[data-testid="kardex-row"]').first()).toHaveAttribute(
			'data-kind',
			'exit_void'
		);
	});
});
