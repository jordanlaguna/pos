import { expect, test, type Page } from '@playwright/test';
import { entrar } from './sesion';

/**
 * Registrar una compra y anularla, de punta a punta (T-1013, F10).
 *
 * Lo que se comprueba es lo que separa una **compra** de una entrada de
 * mercadería: proveedor, documento con su fecha, condición de pago y la tarifa
 * de cada línea. Y lo que arrastra: una compra no se anula sin decir por qué.
 *
 * Va contra el catálogo del demo y **solo agrega**: una compra sube existencias
 * y deja una fila más en la lista, que es lo que ninguna otra prueba mira. La
 * lección de T-310 sigue valiendo —quien cambia el estado del demo se lo cambia
 * a todas—, así que acá no se toca nada que ya estuviera.
 */

/** Un número distinto en cada corrida: el simulado guarda su estado en disco. */
function documento(): string {
	return `FC-${`${Date.now()}`.slice(-9)}`;
}

/** Deja una línea de arroz en la vista previa, con su cantidad y su costo. */
async function agregarArroz(page: Page, cantidad: string, costo: string) {
	const buscar = page.locator('input[type="search"]');
	await expect(async () => {
		await buscar.fill('Arroz');
		await expect(page.getByRole('button', { name: /Arroz/i }).first()).toBeVisible({
			timeout: 1000
		});
	}).toPass({ timeout: 10_000 });

	await page.getByRole('button', { name: /Arroz/i }).first().click();
	await page.locator('input[type="number"][aria-label*="antidad"]').first().fill(cantidad);
	await page.locator('input[type="number"][aria-label*="osto"]').first().fill(costo);
}

test.describe('Compras', () => {
	test('una compra a crédito lleva proveedor, fecha, condición y tarifa', async ({ page }) => {
		await entrar(page);
		await page.goto('/inventario/entradas/nueva');
		await agregarArroz(page, '10', '1000');

		// Sin proveedor esto es una entrada: los campos de compra no están.
		await expect(page.locator('#condicion')).toHaveCount(0);

		// Al elegir proveedor aparece todo lo de la compra (RN-52).
		await page.locator('#proveedor').selectOption({ label: 'Mayorista del Este' });
		await expect(page.locator('#condicion')).toBeVisible();

		const numero = documento();
		await page.locator('input[name="document_number"]').fill(numero);
		await page.locator('input[name="document_date"]').fill('2026-09-10');
		await page.locator('#condicion').selectOption('credit');
		await page.locator('input[name="payment_terms_days"]').fill('30');

		// La tarifa es por línea y la del documento manda (RN-53).
		await page.locator('input[aria-label*="Tarifa de impuesto"]').first().fill('13');

		await page.getByRole('button', { name: /ingresar|registrar/i }).last().click();
		await expect(page).toHaveURL(/\/inventario\/entradas\?creada=/);

		// En el detalle: la fecha del documento y el vencimiento a 30 días de
		// ella —no de hoy—, que es lo que el proveedor va a cobrar.
		await page.getByRole('row', { name: new RegExp(numero) }).getByRole('button').first().click();
		const modal = page.getByRole('dialog');
		await expect(modal).toContainText('Mayorista del Este');
		await expect(modal).toContainText('10/09/2026');
		await expect(modal).toContainText('10/10/2026');
	});

	test('una compra no se anula sin decir por qué', async ({ page }) => {
		await entrar(page);
		await page.goto('/inventario/entradas/nueva');
		await agregarArroz(page, '5', '900');
		await page.locator('#proveedor').selectOption({ label: 'Mayorista del Este' });

		const numero = documento();
		await page.locator('input[name="document_number"]').fill(numero);
		await page.getByRole('button', { name: /ingresar|registrar/i }).last().click();
		await expect(page).toHaveURL(/\/inventario\/entradas\?creada=/);

		const fila = page.getByRole('row', { name: new RegExp(numero) });
		await fila.getByRole('button').last().click();

		// El campo de motivo solo sale porque es compra, y el aviso del costo
		// promedio con él: quien anula espera que todo vuelva atrás, y no vuelve.
		const motivo = page.locator('#motivo-anular');
		await expect(motivo).toBeVisible();
		await expect(page.getByRole('dialog')).toContainText(/costo promedio/i);

		await motivo.fill('Llegó mercadería equivocada');
		await page.getByRole('button', { name: /anular/i }).last().click();

		await expect(fila).toContainText(/anulada/i);
	});

	test('el XML trae al proveedor, y si no existe lo marca como nuevo', async ({ page }) => {
		await entrar(page);
		await page.goto('/inventario/entradas/nueva');

		await page.getByRole('button', { name: /archivo/i }).first().click();
		await page
			.locator('input[type="file"]')
			.setInputFiles('tests/fixtures/factura-proveedor-v43.xml');
		await page.getByRole('button', { name: /analizar|leer/i }).click();

		// El emisor de la factura no está dado de alta: se crea al confirmar
		// (RF-42). Es el caso que importa, porque el otro no necesita decisión.
		await expect(page.getByText(/no está registrado/i)).toBeVisible();
		// Y el invariante de siempre: 42 unidades y ₡79 800 (T-1008). El
		// separador de miles es el punto en español, no un espacio.
		await expect(page.locator('body')).toContainText('79.800,00');
	});
});
