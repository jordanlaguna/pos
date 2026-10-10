import { expect, test, type Page } from '@playwright/test';
import { autenticar, clicHasta, entrar, salir } from './sesion';

/**
 * La sesión elige su caja (T-1505, RN-102).
 *
 * Una compañía propia nace con una caja y su dueña entra directo. Con una
 * segunda caja, el login pregunta en cuál se abre —en el mismo paso que la
 * compañía— y el menú ofrece cambiar de caja, que es abrir sesión de nuevo.
 *
 * **La compañía es propia y se da de alta al empezar**, como en
 * `sucursales.spec.ts`: una segunda caja en el demo haría que todas las demás
 * pruebas pasaran por la pregunta.
 */

const SOPORTE = { email: 'soporte@ventasys.cr', password: 'soporte123' };

function marca(): string {
	return `${Date.now()}`.slice(-8);
}

/** Da de alta una compañía con plan «Cadena» —admite varias cajas— y devuelve con qué entrar. */
async function companiaPropia(page: Page, quien: string) {
	const sufijo = marca();
	const correo = `caja.${quien}.${sufijo}@pruebas.ventasys.cr`;
	const negocio = `Ferretería ${quien} ${sufijo}`;

	await autenticar(page, SOPORTE);
	await expect(page).toHaveURL(/\/admin$/);

	await page.getByRole('link', { name: /Nueva compañía/i }).click();
	await page.locator('input[name="nombre"]').fill(negocio);
	await page.locator('input[name="identificacion"]').fill('3101555444');
	await page.locator('input[name="email"]').fill(correo);
	await page.locator('input[name="password"]').fill('dueno123');
	await page.locator('input[name="name"]').fill('Dueña');
	await page.locator('input[name="lastName"]').fill('DeCaja');
	await page.locator('#plan_id').selectOption({ label: 'Cadena' });
	await page.getByRole('button', { name: /Dar de alta/i }).click();
	await expect(page).toHaveURL(/\/admin\/companias\/\d+\?creada=1/);

	await salir(page);
	return { email: correo, password: 'dueno123', negocio };
}

function cajaDeLaSesion(page: Page) {
	return page.locator('[data-testid="session-terminal"]').locator('visible=true').first();
}

function cambiarDeCaja(page: Page) {
	return page.getByRole('link', { name: /Cambiar de caja/i }).locator('visible=true').first();
}

test.describe('la sesión elige su caja', () => {
	test('con dos cajas el login pregunta en cuál, y el menú deja cambiar', async ({ page }) => {
		const dueno = await companiaPropia(page, 'elige');

		// --- 1. Con una sola caja entra directo y no se ofrece cambiar.
		await entrar(page, dueno);
		await expect(cajaDeLaSesion(page)).toContainText('00001');
		await expect(cambiarDeCaja(page)).toHaveCount(0);

		// --- 2. Una segunda caja en la casa matriz.
		await page.goto('/configuracion');
		await clicHasta(page.getByRole('button', { name: /Sucursales y cajas/i }), async () => {
			await expect(page.getByRole('heading', { name: /Sucursales y cajas/i })).toBeVisible();
		});
		await page.locator('[data-sucursal="001"]').getByRole('button', { name: /Agregar caja/i }).click();
		const ficha = page.locator('form#form-caja');
		await ficha.locator('input[name="codigo"]').fill('2');
		await ficha.locator('input[name="nombre"]').fill('Caja dos');
		await page.locator('button[type="submit"][form="form-caja"]').click();
		await expect(page.locator('[data-sucursal="001"] [data-caja="00002"]')).toBeVisible();

		// El menú lo ve en el siguiente clic: la sesión se relee en cada petición.
		await page.goto('/ventas');
		await expect(cambiarDeCaja(page)).toBeVisible();

		// --- 3. Salir y volver: ya no entra directo, pregunta la caja.
		await salir(page);
		await autenticar(page, dueno);
		await expect(page).toHaveURL(/\/compania/);
		await expect(page.locator('[data-testid="company-terminals"]')).toBeVisible();
		await page.getByRole('button', { name: `${dueno.negocio} · Caja dos` }).click();
		await expect(page).toHaveURL(/\/(ventas|dashboard)/);
		await expect(cajaDeLaSesion(page)).toContainText('00002');

		// --- 4. Cambiar de caja desde el menú: abre sesión de nuevo en la otra.
		await cambiarDeCaja(page).click();
		await expect(page).toHaveURL(/\/compania\?caja=1/);
		await page.getByRole('button', { name: `${dueno.negocio} · Caja 1` }).click();
		await expect(page).toHaveURL(/\/(ventas|dashboard)/);
		await expect(cajaDeLaSesion(page)).toContainText('00001');
	});
});
