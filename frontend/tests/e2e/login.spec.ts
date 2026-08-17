import { expect, test, type Locator } from '@playwright/test';

/**
 * Hace clic hasta que la página reaccione.
 *
 * El primer clic después de un `goto` se pierde. El HTML ya está pintado —lo
 * renderizó el servidor— pero Svelte todavía no le enganchó los manejadores, y
 * Playwright no tiene forma de saberlo: ve un botón visible y habilitado, y lo
 * pulsa. Para lo que pasa por formulario da igual, porque funciona sin
 * JavaScript; para un botón que solo vive en el cliente, no.
 *
 * Se reintenta en vez de esperar un tiempo fijo: un `waitForTimeout` sería más
 * lento en la máquina rápida y seguiría fallando en la lenta.
 */
async function clicHasta(boton: Locator, comprobar: () => Promise<void>) {
	await expect(async () => {
		await boton.click();
		await comprobar();
	}).toPass({ timeout: 10_000 });
}

/**
 * Entrar y salir. Es el flujo del que dependen todos los demás: si el cajero no
 * puede iniciar sesión a las 7 de la mañana, el resto del sistema da igual.
 *
 * Los campos se buscan por `name` y no por etiqueta: `getByLabel(/contraseña/i)`
 * casa también con el botón «Mostrar contraseña», y el `name` es además lo que
 * de verdad viaja en el formulario.
 */

const correo = 'input[name="email"]';
const clave = 'input[name="password"]';

test.describe('inicio de sesión', () => {
	test('la pantalla se ve completa y centrada', async ({ page }) => {
		await page.goto('/login');

		await expect(page.getByRole('heading', { name: 'Iniciar sesión' })).toBeVisible();
		await expect(page.locator(correo)).toBeVisible();
		await expect(page.locator(clave)).toBeVisible();
		await expect(page.getByRole('button', { name: /^entrar$/i })).toBeVisible();

		// La tarjeta queda centrada: el mismo aire a cada lado.
		const caja = await page.locator('main > div').first().boundingBox();
		expect(caja).not.toBeNull();
		const derecha = page.viewportSize()!.width - caja!.x - caja!.width;
		expect(Math.abs(caja!.x - derecha)).toBeLessThanOrEqual(1);
	});

	test('no queda rastro de la leyenda de la migración', async ({ page }) => {
		await page.goto('/login');
		await expect(page.getByText(/Migrado de WinForms/i)).toHaveCount(0);
	});

	test('el cajero, con una sola compañía, entra derecho al POS', async ({ page }) => {
		// RN-25: quien tiene una sola compañía disponible no se entera de que la
		// pantalla de selección existe. Es el caso de la mayoría de los negocios.
		await page.goto('/login');
		await page.locator(correo).fill('cajero@ventasys.cr');
		await page.locator(clave).fill('cajero123');
		await page.getByRole('button', { name: /^entrar$/i }).click();

		await expect(page).toHaveURL(/\/(ventas|dashboard)/);
	});

	test('quien tiene varias compañías pasa por la pantalla de selección', async ({ page }) => {
		// RF-27. El administrador del demo pertenece a las dos.
		await page.goto('/login');
		await page.locator(correo).fill('admin@ventasys.cr');
		await page.locator(clave).fill('admin123');
		await page.getByRole('button', { name: /^entrar$/i }).click();

		await expect(page).toHaveURL(/\/compania/);
		await expect(page.getByRole('button', { name: /Abastecedor La Esquina/i })).toBeVisible();
		await expect(page.getByRole('button', { name: /Sucursal Norte/i })).toBeVisible();

		await page.getByRole('button', { name: /Abastecedor La Esquina/i }).click();
		await expect(page).toHaveURL(/\/(ventas|dashboard)/);
	});

	test('con la contraseña mala no entra y lo dice', async ({ page }) => {
		await page.goto('/login');
		await page.locator(correo).fill('admin@ventasys.cr');
		await page.locator(clave).fill('la que no es');
		await page.getByRole('button', { name: /^entrar$/i }).click();

		await expect(page.getByRole('alert')).toBeVisible();
		await expect(page).toHaveURL(/\/login/);
		// El correo se conserva: volver a escribirlo cada vez es lo que hace
		// odiar un POS.
		await expect(page.locator(correo)).toHaveValue('admin@ventasys.cr');
	});

	test('la contraseña se puede mostrar y volver a esconder', async ({ page }) => {
		await page.goto('/login');
		await expect(page.locator(clave)).toHaveAttribute('type', 'password');

		await clicHasta(page.getByRole('button', { name: 'Mostrar contraseña' }), () =>
			expect(page.locator(clave)).toHaveAttribute('type', 'text', { timeout: 1000 })
		);

		await page.getByRole('button', { name: 'Ocultar contraseña' }).click();
		await expect(page.locator(clave)).toHaveAttribute('type', 'password');
	});

	test('una pantalla del POS sin sesión manda al login', async ({ page }) => {
		await page.goto('/ventas');
		await expect(page).toHaveURL(/\/login/);
	});

	test('el botón de tema cambia entre claro y oscuro', async ({ page }) => {
		await page.goto('/login');
		const raiz = page.locator('html');
		const boton = page.getByRole('button', { name: /cambiar entre tema/i });
		await expect(raiz).toHaveAttribute('data-theme', 'light');

		await clicHasta(boton, () =>
			expect(raiz).toHaveAttribute('data-theme', 'dark', { timeout: 1000 })
		);

		await boton.click();
		await expect(raiz).toHaveAttribute('data-theme', 'light');
	});
});
