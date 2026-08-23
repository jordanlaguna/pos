import { expect, test, type Page } from '@playwright/test';

/**
 * El flujo completo en los tres idiomas (T-814).
 *
 * Entrar, cobrar y ver la factura. Es la prueba que cierra F8: los catálogos
 * cuadran (`catalogs.test.ts`), el idioma llega del token (`idioma.spec.ts`) y
 * las fechas y el documento se resuelven aparte (`format.test.ts`,
 * `documents.test.ts`), pero que las cuatro cosas se sostengan **durante una
 * venta de verdad** solo se ve acá.
 *
 * **Los selectores no dependen del idioma**, a propósito: `input[name=…]`, el
 * `form` del modal y la tecla F1. Una prueba multi-idioma que busca botones por
 * su texto solo prueba el idioma en que se escribió.
 */

const CARLOS = { email: 'carlos@ventasys.cr', password: 'cajero123' };
const ADMIN = { email: 'admin@ventasys.cr', password: 'admin123' };

const IDIOMAS = [
	{ code: 'es', menu: 'Ventas', cantidad: 'Cant.', contado: 'Cliente de contado' },
	{ code: 'en', menu: 'Sales', cantidad: 'Qty', contado: 'Walk-in customer' },
	{ code: 'pt', menu: 'Vendas', cantidad: 'Qtd.', contado: 'Cliente avulso' }
];

async function entrar(page: Page, quien: typeof CARLOS) {
	await page.goto('/login');
	await page.locator('input[name="email"]').fill(quien.email);
	await page.locator('input[name="password"]').fill(quien.password);
	await page.locator('form button[type="submit"]').click();
	await expect(page).toHaveURL(/\/(compania|ventas|dashboard)/);
}

/** Deja la pantalla de esta persona en el idioma pedido. */
async function ponerIdioma(page: Page, locale: string) {
	await page.goto('/ventas');
	if ((await page.locator('#nav-idioma').inputValue()) !== locale) {
		await page.locator('#nav-idioma').selectOption(locale);
		await page.locator('form[action="/idioma"] button[type="submit"]').click();
		await expect(page.locator('#nav-idioma')).toHaveValue(locale);
	}
}

/**
 * Vende una unidad del primer producto y cobra en efectivo.
 *
 * Abre la caja si está cerrada: sin turno abierto, el botón de cobrar abre el
 * modal de apertura en vez del de pago (`openPayment`), y eso hacía fallar la
 * primera versión de esta prueba señalando el campo de efectivo —que no existía
 * porque el modal era el otro—.
 */
async function cobrarUnaVenta(page: Page) {
	await page.goto('/ventas');
	await page.getByRole('button', { name: /Arroz/i }).first().click();

	// F1 abre el cobro. Es el atajo del WinForms y no depende del idioma.
	await page.keyboard.press('F1');

	const apertura = page.locator('input[name="opening_amount"]');
	if (await apertura.isVisible()) {
		await apertura.fill('50000');
		await page.locator('button[type="submit"][form="open-cash-form"]').click();
		await expect(apertura).toBeHidden();
		await page.keyboard.press('F1');
	}

	const recibido = page.locator('input[name="cash_received"]');
	await expect(recibido).toBeVisible();
	await recibido.fill('50000');
	await page.locator('button[type="submit"][form="payment-form"]').click();

	await expect(page).toHaveURL(/\/facturas\/\d+/, { timeout: 15_000 });
}

test.describe('entrar, cobrar y ver la factura', () => {
	for (const idioma of IDIOMAS) {
		test(`en ${idioma.code}`, async ({ page }) => {
			await entrar(page, CARLOS);
			await ponerIdioma(page, idioma.code);

			// La pantalla, en su idioma.
			await expect(page.getByRole('link', { name: idioma.menu })).toBeVisible();
			await expect(page.locator('html')).toHaveAttribute('lang', idioma.code);

			await cobrarUnaVenta(page);

			// La factura salió y se puede leer: la venta llegó al backend, el
			// documento se armó y la pantalla siguió en su idioma.
			await expect(page.getByRole('link', { name: idioma.menu })).toBeVisible();
		});
	}

	test.afterAll(async ({ browser }) => {
		// Carlos vuelve al inglés, que es como lo dejó el seed y como lo esperan
		// las pruebas de `idioma.spec.ts`.
		const page = await browser.newPage();
		await entrar(page, CARLOS);
		await ponerIdioma(page, 'en');
		await page.close();
	});
});

test.describe('el documento no habla el idioma de la pantalla (RN-29)', () => {
	test('la pantalla en portugués y la factura en español', async ({ page }) => {
		await entrar(page, CARLOS);
		await ponerIdioma(page, 'pt');
		await cobrarUnaVenta(page);

		// El menú, en portugués.
		await expect(page.getByRole('link', { name: 'Vendas' })).toBeVisible();

		// Y el documento, en español: es la factura del cliente y de Hacienda, y
		// la compañía del demo emite en español (`document_locale`).
		const documento = page.locator('article.print-sheet');
		await expect(documento).toContainText('Cant.');
		await expect(documento).not.toContainText('Qtd.');

		await ponerIdioma(page, 'en');
	});

	test('el administrador cambia el idioma del documento y la pantalla no se mueve', async ({
		page
	}) => {
		await entrar(page, ADMIN);
		if (page.url().includes('/compania')) {
			await page.getByRole('button', { name: /Abastecedor La Esquina/i }).click();
		}
		await page.goto('/configuracion');

		/*
		 * El selector del documento vive en la pestaña de Documentos, que no es la
		 * que abre por omisión. Se reintenta el clic porque las pestañas son
		 * client-only (`onclick`): el primero, si cae antes de que Svelte hidrate,
		 * marca el botón como activo y no cambia nada. Es la misma trampa que
		 * documenta `clicHasta` en login.spec.ts, y cuesta lo mismo reintentar que
		 * esperar un tiempo fijo que en otra máquina no alcanza.
		 */
		await expect(async () => {
			await page.getByRole('button', { name: /^(documentos|documents)$/i }).click();
			await expect(page.locator('#idioma-documento')).toBeVisible({ timeout: 1000 });
		}).toPass({ timeout: 15_000 });

		const idiomaDePantalla = await page.locator('html').getAttribute('lang');

		// No hace falta restaurar nada: esta prueba **no guarda**, así que el
		// cambio vive solo en el borrador de la pantalla. Un `finally` que
		// «restaura» lo que nunca se escribió solo sirve para tapar el error de
		// verdad cuando algo falla antes.
		await page.locator('#idioma-documento').selectOption('pt');
		await expect(page.locator('article.print-sheet')).toContainText('Qtd.');

		// Y la pantalla no se movió: son dos ajustes distintos (RN-29).
		await expect(page.locator('html')).toHaveAttribute('lang', idiomaDePantalla ?? 'es');
	});
});
