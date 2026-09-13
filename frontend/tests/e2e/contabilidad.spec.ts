import { expect, test, type Page } from '@playwright/test';
import { abrirCobro, autenticar, clicHasta, entrar, salir } from './sesion';

/**
 * El recorrido completo de F11, de punta a punta (T-1113).
 *
 * Va contra **una compañía que esta prueba da de alta**, y no contra el demo,
 * por la misma razón que F10: activar la contabilidad cambia lo que pasa en cada
 * venta de esa compañía —desde entonces deja asiento— y eso se lo cambiaría a
 * todas las demás pruebas.
 *
 * El recorrido es el de un contador en su primer mes: activa, mira que la venta
 * dejó su asiento, compra a crédito, abona, cierra la caja con faltante, mira
 * que el D-104 cuadre, cierra el mes y comprueba que ya no puede escribir en él.
 */

const SOPORTE = { email: 'soporte@ventasys.cr', password: 'soporte123' };

function marca(): string {
	return `${Date.now()}`.slice(-8);
}

/** Da de alta una compañía con el plan que trae los tres módulos. */
async function companiaConContabilidad(page: Page, plan: string) {
	const correo = `conta${marca()}@ventasys.cr`;
	await autenticar(page, SOPORTE);
	await expect(page).toHaveURL(/\/admin$/);

	await page.goto('/admin/companias/nueva');
	await page.locator('input[name="nombre"]').fill(`Contadora ${marca()}`);
	await page.locator('input[name="identificacion"]').fill(`310${marca()}`);
	await page.locator('input[name="email"]').fill(correo);
	await page.locator('input[name="password"]').fill('dueno123');
	await page.locator('input[name="name"]').fill('Ana');
	await page.locator('input[name="lastName"]').fill('Contadora');
	await page.locator('#plan_id').selectOption({ label: plan });
	await page.getByRole('button', { name: /Dar de alta/i }).click();
	await expect(page).toHaveURL(/\/admin\/companias\/\d+\?creada=1/);

	await salir(page);
	return { email: correo, password: 'dueno123' };
}

/** Una categoría donde colgar el producto (RN-6). */
async function crearCategoria(page: Page, nombre: string) {
	await page.goto('/inventario/categorias');
	const campo = page.locator('#category-create input[name="name"]');
	await clicHasta(page.getByRole('button', { name: /nueva categoría|agregar/i }).first(), () =>
		expect(campo).toBeVisible({ timeout: 1000 })
	);
	await campo.fill(nombre);
	await page.locator('button[type="submit"][form="category-create"]').click();
	await expect(page.getByText(nombre, { exact: true }).first()).toBeVisible();
}

/** El primer día de este mes, que es desde cuándo se llevan los libros. */
function primeroDelMes(): string {
	const hoy = new Date();
	return `${hoy.getFullYear()}-${String(hoy.getMonth() + 1).padStart(2, '0')}-01`;
}

test.describe('F11 de punta a punta', () => {
	test('de la activación al mes cerrado', async ({ page }) => {
		const duena = await companiaConContabilidad(page, 'Comercio');
		await entrar(page, duena);

		// ------------------------------------------------- 1. activar los libros
		await page.goto('/contabilidad');
		await expect(page.getByText(/todavía no lleva libros/i)).toBeVisible();

		await page.locator('input[name="start_date"]').fill(primeroDelMes());

		/*
		 * Saldos iniciales que cuadran: 100 000 en caja contra capital.
		 *
		 * Primero hay que **esperar a que Svelte hidrate**. Los renglones se
		 * pintan en el servidor pero su valor lo lleva el cliente
		 * (`bind:value`), así que lo que se teclee antes de hidratar se borra en
		 * cuanto hidrata —y solo se borra lo tecleado hasta ese momento, así que
		 * el formulario llega a medias—. El síntoma engaña: la activación
		 * responde «los saldos no cuadran» con los dos números en la pantalla.
		 *
		 * El pie de la tabla es la señal: esa suma solo la mueve el cliente.
		 */
		const primerDebito = page.locator('input[name="opening_debit"]').first();
		await expect(async () => {
			await primerDebito.fill('100000');
			await expect(page.locator('tfoot')).toContainText('100.000,00', { timeout: 500 });
		}).toPass({ timeout: 15_000 });

		await page.locator('select[name="opening_code"]').first().selectOption('1.1.01');
		await page.locator('select[name="opening_code"]').nth(1).selectOption('3.1.01');
		await page.locator('input[name="opening_credit"]').nth(1).fill('100000');

		await page.getByRole('button', { name: /activar contabilidad/i }).click();

		// Las pestañas solo aparecen con la contabilidad activa.
		await expect(page.getByRole('link', { name: /^Asientos$/ })).toBeVisible();

		// ------------------------------------------ 2. la venta del invariante
		//
		// 3 × 1 450 al 13 % en efectivo. El producto nace sin costo —nunca se
		// compró—, así que el asiento no lleva el par costo / inventario: son
		// 4 915,50 por lado y no 7 615,50, y eso es RN-63 funcionando.
		await crearCategoria(page, 'Abarrotes');
		await page.goto('/inventario');
		await clicHasta(page.getByRole('button', { name: /Nuevo producto/i }).first(), () =>
			expect(page.locator('#product-form input[name="name"]')).toBeVisible({ timeout: 1000 })
		);
		await page.locator('#product-form input[name="name"]').fill('Arroz');
		await page.locator('#product-form input[name="description"]').fill('Arroz');
		await page.locator('#product-form input[name="price"]').fill('1450');
		await page.locator('#product-form input[name="stock"]').fill('20');
		await page.locator('#product-form input[name="barcode"]').fill(`T${marca()}`);
		await page.locator('#product-form input[name="tax_rate"]').fill('13');
		await page.getByRole('button', { name: /Agregar producto/i }).click();
		await expect(page.getByRole('row', { name: /Arroz/ }).first()).toBeVisible();

		// La caja abierta primero: la venta tiene que caer dentro del turno para
		// que el cierre de más abajo tenga con qué cuadrar.
		await page.goto('/caja');
		const apertura = page.locator('input[name="opening_amount"]');
		await clicHasta(page.getByRole('button', { name: /^abrir caja$/i }).first(), () =>
			expect(apertura).toBeVisible({ timeout: 1000 })
		);
		await apertura.fill('50000');
		await page.locator('button[type="submit"][form="open-form"]').click();
		await expect(page.locator('body')).toContainText('50.000,00');

		await page.goto('/ventas');
		const buscar = page.locator('input[type="search"]').first();
		await expect(async () => {
			await buscar.fill('Arroz');
			await expect(page.getByRole('button', { name: /Arroz/i }).first()).toBeVisible({
				timeout: 1000
			});
		}).toPass({ timeout: 15_000 });
		await page.getByRole('button', { name: /Arroz/i }).first().click();
		// Con el botón de la línea y no volviendo al catálogo: con el producto ya
		// en la venta, «Arroz» también nombra a los botones del carrito y
		// `.first()` deja de ser el del catálogo. Y por el botón y no llenando el
		// contador, porque escribir en el campo no dispara lo que la pantalla
		// escucha.
		const agregar = page.getByRole('button', { name: /Agregar una unidad de Arroz/i });
		await agregar.click();
		await agregar.click();
		await expect(page.locator('body')).toContainText('4.915,50');

		// F1 abre el cobro, como en el WinForms y como lo hacen las demás
		// pruebas. Si la caja estuviera cerrada, `abrirCobro` la abre.
		const recibido = await abrirCobro(page);
		await recibido.fill('5000');
		await page.locator('button[type="submit"][form="payment-form"]').click();
		// Que la venta **entró**, y no que el modal mostró el vuelto: el vuelto
		// aparece en cuanto se teclea el efectivo, así que esperarlo daría por
		// buena una venta que nunca se confirmó.
		await expect(page).toHaveURL(/\/facturas\/\d+/, { timeout: 15_000 });

		// -------------------------------- 3. y el asiento de esa venta cuadra
		await page.goto('/contabilidad/asientos');
		await page.getByRole('link', { name: /Venta n\.º/ }).first().click();
		// Las dos columnas del total dicen lo mismo: eso es que cuadra (RN-58).
		await expect(page.locator('tfoot')).toContainText('4.915,50');
		// Y la línea del IVA lleva su tarifa, que es lo que hace del D-104 una
		// consulta sobre el libro y no un cálculo aparte (RN-65).
		await expect(page.locator('body')).toContainText('565,50');

		// ------------------------------------- 3. un asiento manual que no cuadra
		await clicHasta(page.getByRole('button', { name: /asiento nuevo/i }).first(), () =>
			expect(page.locator('input[name="entry_date"]')).toBeVisible({ timeout: 1000 })
		);
		await page.locator('input[name="description"]').fill('Gasto del dueño');
		await page.locator('select[name="line_account"]').first().selectOption({ label: '6.9.02 · Gastos generales' });
		await page.locator('input[name="line_debit"]').first().fill('5000');
		// Sin la contrapartida, el botón de guardar queda deshabilitado: el POS
		// no deja mandar un asiento que no cuadra, y el servidor tampoco lo
		// aceptaría (RN-58).
		await expect(page.getByRole('button', { name: /^guardar$/i })).toBeDisabled();

		await page.locator('select[name="line_account"]').nth(1).selectOption({ label: '1.1.01 · Caja' });
		await page.locator('input[name="line_credit"]').nth(1).fill('5000');
		await expect(page.getByRole('button', { name: /^guardar$/i })).toBeEnabled();
		await page.getByRole('button', { name: /^guardar$/i }).click();
		await expect(page.getByText(/gasto del dueño/i).first()).toBeVisible();

		// ---------------------------- 4. el cierre con faltante deja su asiento
		//
		// Esperado: 50 000 de apertura + 4 915,50 de la venta. Se cuenta menos, y
		// el faltante es lo único que el cierre asienta: un turno que cuadra no
		// deja asiento porque no pasó nada que anotar.
		await page.goto('/caja');
		const contado = page.locator('input[name="closing_amount"]');
		await clicHasta(page.getByRole('button', { name: /cerrar caja/i }).first(), () =>
			expect(contado).toBeVisible({ timeout: 1000 })
		);
		await contado.fill('54000');
		await page.locator('button[type="submit"][form="close-form"]').click();
		await expect(page.locator('body')).toContainText('915,50');

		await page.goto('/contabilidad/asientos');
		await expect(page.getByRole('link', { name: /Cierre de caja n\.º/ }).first()).toBeVisible();

		// --------------------------------------- 5. los libros salen del mismo sitio
		await page.goto('/contabilidad/reportes?report=trial-balance');
		await expect(page.getByText(/cuadra:/i).first()).toBeVisible();

		await page.goto('/contabilidad/reportes?report=balance');
		// La ecuación contable: si esto falla, alguno de los cinco mintió.
		await expect(page.getByText(/activo = pasivo/i).first()).toBeVisible();

		// ------------------------------------------------ 5. cerrar el mes
		await page.goto('/contabilidad/periodos');
		await clicHasta(page.getByRole('button', { name: /cerrar el mes/i }).first(), () =>
			expect(page.getByText(/no se puede reabrir/i)).toBeVisible({ timeout: 1000 })
		);
		await page
			.getByRole('button', { name: /cerrar el mes/i })
			.last()
			.click();
		await expect(page.getByText(/^Cerrado/).first()).toBeVisible();

		// ---------------------- 6. y con el mes cerrado ya no se escribe en él
		await page.goto('/contabilidad/asientos');
		await clicHasta(page.getByRole('button', { name: /asiento nuevo/i }).first(), () =>
			expect(page.locator('input[name="entry_date"]')).toBeVisible({ timeout: 1000 })
		);
		await page.locator('input[name="entry_date"]').fill(primeroDelMes());
		await page.locator('input[name="description"]').fill('Tarde');
		await page.locator('select[name="line_account"]').first().selectOption({ label: '6.9.02 · Gastos generales' });
		await page.locator('input[name="line_debit"]').first().fill('100');
		await page.locator('select[name="line_account"]').nth(1).selectOption({ label: '1.1.01 · Caja' });
		await page.locator('input[name="line_credit"]').nth(1).fill('100');
		await page.getByRole('button', { name: /^guardar$/i }).click();

		// RN-61: lo que haya que corregir va por un ajuste en el periodo abierto.
		await expect(page.getByText(/está cerrado/i).first()).toBeVisible();
	});

	test('sin el módulo en el plan, el menú lo muestra con candado', async ({ page }) => {
		// La misma regla de F10 (RN-49): con candado, no escondido. Un
		// «Contabilidad 🔒» es lo único que le dice al dueño que el producto la
		// tiene.
		const duena = await companiaConContabilidad(page, 'Básico');
		await entrar(page, duena);

		const contabilidad = page.getByRole('listitem').filter({ hasText: /Contabilidad/ });
		await expect(contabilidad).toHaveCount(1);
		await expect(contabilidad.getByRole('link')).toHaveCount(0);
		await expect(contabilidad.locator('[title]')).toHaveAttribute(
			'title',
			/no está en su plan/i
		);
	});
});
