import { expect, type Page } from '@playwright/test';

/**
 * Entrar al POS, en un solo lugar.
 *
 * Estaba copiado en cada archivo de pruebas, y cuando el login pasó a tener dos
 * pasos (F2) hubo que arreglar la misma función tres veces. Acá vive una sola.
 *
 * El modo simulado tiene dos compañías y el administrador pertenece a las dos,
 * así que su login devuelve un token de tránsito y cae en la pantalla de
 * selección (RF-27). Los cajeros pertenecen a una sola y entran directo
 * (RN-25). Las dos cosas son el comportamiento correcto y las dos se prueban.
 */

export const ADMIN = { email: 'admin@ventasys.cr', password: 'admin123' };
export const CAJERO = { email: 'cajero@ventasys.cr', password: 'cajero123' };

/** La compañía con catálogo y ventas del demo. */
export const CON_DATOS = 'Abastecedor La Esquina';
/** La segunda, recién dada de alta y por lo tanto vacía. */
export const VACIA = 'Sucursal Norte';

export async function autenticar(page: Page, quien = ADMIN) {
	await page.goto('/login');
	await page.locator('input[name="email"]').fill(quien.email);
	await page.locator('input[name="password"]').fill(quien.password);
	await page.getByRole('button', { name: /^entrar$/i }).click();
}

/** Elige una compañía de la pantalla de selección, por parte de su nombre. */
export async function elegirCompania(page: Page, nombre = CON_DATOS) {
	await expect(page).toHaveURL(/\/compania/);
	await page.getByRole('button', { name: new RegExp(nombre, 'i') }).click();
	await expect(page).toHaveURL(/\/(ventas|dashboard)/);
}

/** Entra hasta el POS, pasando por la selección si aparece. */
export async function entrar(page: Page, quien = ADMIN, compania = CON_DATOS) {
	await autenticar(page, quien);
	await expect(page).toHaveURL(/\/(compania|ventas|dashboard)/);
	if (page.url().includes('/compania')) await elegirCompania(page, compania);
	await expect(page).toHaveURL(/\/(ventas|dashboard)/);
}

/** Entra y deja la pantalla de ventas lista, con el catálogo a la vista. */
export async function entrarAVentas(page: Page, quien = ADMIN, compania = CON_DATOS) {
	await entrar(page, quien, compania);
	await page.goto('/ventas');
	await expect(page.getByRole('button', { name: /Arroz/i }).first()).toBeVisible();
}
