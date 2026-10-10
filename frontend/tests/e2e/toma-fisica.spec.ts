import { expect, test } from '@playwright/test';
import { clicHasta, entrar } from './sesion';

/**
 * La toma física de punta a punta (T-1503, F15).
 *
 * Un producto propio con 10, una toma de toda la sucursal, contar 8, aplicar, y
 * el kárdex con el ajuste de −2. La toma se cierra al final: una abierta de
 * toda la sucursal bloquearía cualquier otra, y no se deja nada abierto que
 * otra prueba pudiera encontrar (lección de T-310).
 */

function marca(): string {
	return `${Date.now()}`.slice(-8);
}

test.describe('Toma física', () => {
	test('contar 8 donde el sistema dice 10 deja un ajuste de −2', async ({ page }) => {
		await entrar(page);
		const sello = marca();
		const nombre = `Contado ${sello}`;

		// --- 1. Un producto propio con 10 unidades.
		await page.goto('/inventario');
		await clicHasta(page.getByRole('button', { name: /Nuevo producto/i }).first(), () =>
			expect(page.locator('#product-form input[name="name"]')).toBeVisible({ timeout: 1000 })
		);
		await page.locator('#product-form input[name="name"]').fill(nombre);
		await page.locator('#product-form input[name="description"]').fill(nombre);
		await page.locator('#product-form input[name="price"]').fill('1000');
		await page.locator('#product-form input[name="stock"]').fill('10');
		await page.locator('#product-form input[name="barcode"]').fill(`T${sello}`);
		await page.getByRole('button', { name: /Agregar producto/i }).click();
		await expect(page.getByText(nombre, { exact: true }).first()).toBeVisible();

		// --- 2. Abrir una toma de toda la sucursal.
		await page.goto('/inventario/toma-fisica');
		await clicHasta(page.getByRole('button', { name: /Abrir toma/i }).first(), () =>
			expect(page.locator('#alcance')).toBeVisible({ timeout: 1000 })
		);
		await page.getByRole('button', { name: /^Abrir$/ }).click();
		await expect(page).toHaveURL(/\/inventario\/toma-fisica\/\d+/);
		await expect(page.locator('[data-testid="count-status"]')).toHaveAttribute('data-status', 'open');

		// --- 3. Contar 8.
		const buscar = page.locator('input[type="search"]');
		await expect(async () => {
			await buscar.fill(nombre);
			await expect(page.getByRole('button', { name: nombre }).first()).toBeVisible({ timeout: 1000 });
		}).toPass({ timeout: 10_000 });
		await page.getByRole('button', { name: nombre }).first().click();
		await page.locator('#contado').fill('8');
		await page.getByRole('button', { name: /^Anotar$/ }).click();
		const linea = page.locator('[data-testid="count-line"]').filter({ hasText: nombre });
		await expect(linea).toHaveAttribute('data-difference', '-2');
		await expect(linea).toContainText('10');

		// --- 4. Aplicar: la toma queda cerrada.
		await clicHasta(page.getByRole('button', { name: /^Aplicar$/ }), () =>
			expect(page.getByRole('button', { name: /Aplicar toma/ })).toBeVisible({ timeout: 1000 })
		);
		await page.getByRole('button', { name: /Aplicar toma/ }).click();
		await expect(page.locator('[data-testid="count-status"]')).toHaveAttribute('data-status', 'applied');

		// --- 5. El kárdex: un ajuste de −2 y quedan 8.
		await page.goto('/inventario');
		await page.getByRole('link', { name: `Kárdex de ${nombre}` }).click();
		await expect(page.locator('[data-testid="kardex-stock"]')).toHaveText('8');
		await expect(page.locator('[data-testid="kardex-row"]').first()).toHaveAttribute('data-kind', 'count');
	});
});
