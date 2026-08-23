import { expect, test } from '@playwright/test';

/**
 * El idioma de la sesión llega hasta la pantalla (T-809).
 *
 * Es la única prueba que recorre la cadena completa: el backend resuelve el
 * idioma y lo pone en el token, `hooks.server.ts` lo saca de ahí con la
 * estrategia `custom-session`, `paraglideMiddleware` lo guarda por petición, el
 * render lo usa, y la cookie espejo lo deja disponible para el navegador. Cada
 * pieza por separado se prueba más abajo —`test_locale.py`, `test_idioma.py`,
 * `catalogs.test.ts`—; que las cinco encajen solo se ve acá.
 *
 * En el demo, Carlos es el único con el POS en inglés (`users[3].locale`). Los
 * otros dos siguen en español, así que esta prueba no depende de ninguna
 * decisión de las demás y las demás no dependen de esta.
 */

const correo = 'input[name="email"]';
const clave = 'input[name="password"]';

const CARLOS = { email: 'carlos@ventasys.cr', password: 'cajero123' };
const CAJERO_ES = { email: 'cajero@ventasys.cr', password: 'cajero123' };

async function entrar(page: import('@playwright/test').Page, quien: typeof CARLOS) {
	await page.goto('/login');
	await page.locator(correo).fill(quien.email);
	await page.locator(clave).fill(quien.password);
	// El botón dice «Entrar» o «Sign in» según el idioma de la pantalla de login,
	// que antes de entrar sale en el idioma base: acá siempre es el español.
	await page.getByRole('button', { name: /^entrar$/i }).click();
	await expect(page).toHaveURL(/\/(ventas|dashboard)/);
}

/** Deja el idioma de Carlos en inglés, venga como venga. */
async function asegurarIngles(page: import('@playwright/test').Page) {
	await entrar(page, CARLOS);
	if ((await page.locator('#nav-idioma').inputValue()) !== 'en') {
		await page.locator('#nav-idioma').selectOption('en');
		await page.getByRole('button', { name: /cambiar el idioma|change the language/i }).click();
		await expect(page.locator('#nav-idioma')).toHaveValue('en');
	}
}

/*
 * El estado del simulado se guarda en disco y sobrevive a la corrida, así que
 * esta prueba **no da por hecho el seed**: lo pone como lo necesita.
 *
 * No es celo de más. La primera versión daba por hecho que Carlos venía en
 * inglés; una corrida que falló a mitad lo dejó en español, y las tres pruebas
 * siguientes empezaron a fallar señalando la pantalla —el clásico de culpar al
 * último cambio cuando lo que está sucio es el estado—.
 */
test.beforeAll(async ({ browser }) => {
	const page = await browser.newPage();
	await asegurarIngles(page);
	await page.close();
});

test.describe('el idioma sale del token', () => {
	test('quien lo tiene en inglés ve el POS en inglés', async ({ page }) => {
		await entrar(page, CARLOS);

		// El menú: es lo que aparece en toda pantalla y sale del catálogo `nav`.
		await expect(page.getByRole('link', { name: 'Sales' })).toBeVisible();
		await expect(page.getByRole('link', { name: 'Cash register' })).toBeVisible();
		await expect(page.getByRole('link', { name: 'Invoices' })).toBeVisible();

		// Y nada en español, que es la otra mitad: si el catálogo inglés tuviera
		// huecos, la pantalla saldría mezclada y esto lo vería.
		await expect(page.getByRole('link', { name: 'Ventas' })).toHaveCount(0);
		await expect(page.getByRole('link', { name: 'Facturas' })).toHaveCount(0);
	});

	test('el documento declara el idioma que se está usando', async ({ page }) => {
		// De `<html lang>` salen la pronunciación de un lector de pantalla y el
		// guionado del navegador; si miente, miente para quien más lo necesita.
		await entrar(page, CARLOS);
		await expect(page.locator('html')).toHaveAttribute('lang', 'en');
	});

	test('el idioma sobrevive a navegar del lado del cliente', async ({ page }) => {
		// Después de hidratar no hay token que leer —la cookie de sesión es
		// httpOnly—, así que el navegador resuelve el idioma con la cookie espejo.
		// Sin ella, la primera navegación sin recargar volvería al español.
		await entrar(page, CARLOS);
		await page.getByRole('link', { name: 'Cash register' }).click();
		await expect(page).toHaveURL(/\/caja/);
		await expect(page.getByRole('link', { name: 'Sales' })).toBeVisible();
		await expect(page.getByRole('link', { name: 'Ventas' })).toHaveCount(0);
	});

	test('a quien no lo tiene no le cambia nada', async ({ page }) => {
		// La otra dirección, que es la que evita que esto se convierta en «el POS
		// quedó en inglés para todos».
		await entrar(page, CAJERO_ES);
		await expect(page.getByRole('link', { name: 'Ventas' })).toBeVisible();
		await expect(page.locator('html')).toHaveAttribute('lang', 'es');
	});
});

test.describe('el selector del menú', () => {
	/*
	 * Cambia estado del simulado y lo devuelve al final. Es seguro porque
	 * `playwright.config.ts` corre en un solo worker y sin paralelismo: nada más
	 * está mirando a Carlos mientras esto pasa. Si la prueba se cayera a mitad,
	 * Carlos quedaría en español y las pruebas de arriba fallarían en la corrida
	 * siguiente —ruidoso, que es lo que uno quiere: un estado sucio que no se
	 * nota es peor—.
	 */
	test('elegir «el de la compañía» y volver al inglés', async ({ page }) => {
		await entrar(page, CARLOS);

		// De inglés a heredar el de la compañía, que es español.
		await page.locator('#nav-idioma').selectOption('auto');
		await page.getByRole('button', { name: /cambiar el idioma|change the language/i }).click();
		await expect(page.getByRole('link', { name: 'Ventas' })).toBeVisible();
		await expect(page.locator('html')).toHaveAttribute('lang', 'es');

		// Y de vuelta. El selector muestra lo que eligió la persona, no lo
		// efectivo: después de «auto» tiene que estar en «auto».
		await expect(page.locator('#nav-idioma')).toHaveValue('auto');
		await page.locator('#nav-idioma').selectOption('en');
		await page.getByRole('button', { name: /cambiar el idioma|change the language/i }).click();
		await expect(page.getByRole('link', { name: 'Sales' })).toBeVisible();
		await expect(page.locator('#nav-idioma')).toHaveValue('en');
	});
});
