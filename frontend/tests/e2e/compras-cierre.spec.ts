import { expect, test, type Page } from '@playwright/test';
import { autenticar, clicHasta, entrar, salir } from './sesion';

/**
 * El recorrido completo de F10, de punta a punta (T-1016).
 *
 * Va contra **una compañía que esta prueba da de alta**, y no contra el demo,
 * por la lección de T-310: quien cambia el estado del demo se lo cambia a las
 * demás. Acá hace falta además porque el catálogo tiene que estar vacío —así el
 * XML crea los productos, que es el caso de RF-42— y porque el reporte por
 * tarifa solo se puede comparar contra un absoluto si nadie más compró.
 *
 * El recorrido es el de un negocio de verdad en su primer día con el módulo:
 * llega la factura del proveedor por correo, se carga, se paga parte en
 * efectivo, y la segunda compra resulta estar mal y se anula.
 */

const SOPORTE = { email: 'soporte@ventasys.cr', password: 'soporte123' };

function marca(): string {
	return `${Date.now()}`.slice(-8);
}

/** Da de alta una compañía con el plan que trae los tres módulos. */
async function companiaConCompras(page: Page, plan: string) {
	const correo = `compras${marca()}@ventasys.cr`;
	await autenticar(page, SOPORTE);
	await expect(page).toHaveURL(/\/admin$/);

	await page.goto('/admin/companias/nueva');
	await page.locator('input[name="nombre"]').fill(`Abarrotes ${marca()}`);
	await page.locator('input[name="identificacion"]').fill(`310${marca()}`);
	await page.locator('input[name="email"]').fill(correo);
	await page.locator('input[name="password"]').fill('dueno123');
	await page.locator('input[name="name"]').fill('Marta');
	await page.locator('input[name="lastName"]').fill('Abarrotes');
	// «Comercio» trae los tres módulos; «Básico», ninguno.
	await page.locator('#plan_id').selectOption({ label: plan });
	await page.getByRole('button', { name: /Dar de alta/i }).click();
	await expect(page).toHaveURL(/\/admin\/companias\/\d+\?creada=1/);

	await salir(page);
	return { email: correo, password: 'dueno123' };
}

/** Una categoría donde colgar los productos que va a crear el XML (RN-6). */
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

test.describe('F10 de punta a punta', () => {
	test('del XML del proveedor al arqueo cuadrado', async ({ page }) => {
		const duena = await companiaConCompras(page, 'Comercio');
		await entrar(page, duena);
		await crearCategoria(page, 'Abarrotes');

		// ---------------------------------------------- 1. el XML del proveedor
		await page.goto('/inventario/entradas/nueva');
		// La pestaña solo vive en el cliente: hay que esperar a que hidrate.
		await clicHasta(page.getByRole('button', { name: /archivo/i }).first(), () =>
			expect(page.locator('input[type="file"]')).toBeVisible({ timeout: 1000 })
		);
		await page
			.locator('input[type="file"]')
			.setInputFiles('tests/fixtures/factura-proveedor-v43.xml');
		await page.getByRole('button', { name: /analizar|leer/i }).click();

		// El catálogo está vacío: las cuatro líneas vienen sin coincidencia y el
		// proveedor no existe, que es el caso que importa de RF-42.
		await expect(page.getByText(/no está registrado/i)).toBeVisible();

		// Se deja **una sola** línea, la del arroz, para que las cifras del
		// reporte sean comprobables: 24 × 1 200 = 28 800.
		const filas = page.locator('tbody tr');
		const incluir = page.locator('input[type="checkbox"][aria-label*="ncluir"]');
		const cuantas = await incluir.count();
		for (let i = 1; i < cuantas; i++) {
			if (await incluir.nth(i).isChecked()) await incluir.nth(i).uncheck();
		}
		await expect(filas.first()).toContainText(/Arroz/i);
		await incluir.first().check();
		await page.locator('input[type="checkbox"]:not([aria-label])').first().check(); // crear producto

		// ------------------------------------------- 2. la compra, a crédito
		await page.locator('input[name="document_date"]').fill('2026-04-20');
		await page.locator('#condicion').selectOption('credit');
		await page.locator('input[name="payment_terms_days"]').fill('30');
		// El XML de ejemplo no trae impuesto; se teclea el 13 %, que es lo que
		// hace una persona cuando el emisor lo omitió.
		await page.locator('input[aria-label*="Tarifa de impuesto"]').first().fill('13');

		await page.getByRole('button', { name: /ingresar|registrar/i }).last().click();
		await expect(page).toHaveURL(/\/inventario\/entradas\?creada=/);

		// ------------------------------ 3. el reporte por tarifa ve su IVA
		await page.goto('/dashboard?from=2026-04-01&to=2026-04-30');
		const reporte = page.locator('section').filter({ hasText: /compras del periodo/i });
		await expect(reporte).toContainText('13 %');
		await expect(reporte).toContainText('28.800,00');
		await expect(reporte).toContainText('3.744,00');

		// Y **no** en mayo: el periodo es el de la fecha del documento, no el de
		// la carga. Contarlo por la carga desplazaría dos declaraciones.
		await page.goto('/dashboard?from=2026-05-01&to=2026-05-31');
		await expect(page.locator('section').filter({ hasText: /compras del periodo/i })).toHaveCount(0);

		// --------------------------------- 4. abono en efectivo y arqueo
		await page.goto('/caja');
		const apertura = page.locator('input[name="opening_amount"]');
		await clicHasta(page.getByRole('button', { name: /^abrir caja$/i }).first(), () =>
			expect(apertura).toBeVisible({ timeout: 1000 })
		);
		await apertura.fill('50000');
		await page.locator('button[type="submit"][form="open-form"]').click();
		await expect(page.locator('body')).toContainText('50.000,00');

		await page.goto('/compras/cuentas-por-pagar');
		// 28 800 + 13 % = 32 544, que es lo que se le debe al proveedor.
		await expect(page.locator('body')).toContainText('32.544,00');
		await clicHasta(page.getByRole('button', { name: /abonar|pagar/i }).first(), () =>
			expect(page.locator('#metodo-abono')).toBeVisible()
		);
		await page.locator('input[name="amount"]').fill('20000');
		await page.locator('#metodo-abono').selectOption('cash');
		await page.getByRole('button', { name: /registrar abono/i }).click();
		await expect(page.locator('body')).toContainText('12.544,00');

		await page.goto('/caja');
		// 50 000 − 20 000: el arqueo cuadra porque la gaveta y el abono son la
		// misma plata (RN-56). Si no lo fueran, el turno cerraría con 20 000 de
		// sobrante y nadie sabría de dónde salieron.
		await expect(page.locator('body')).toContainText('30.000,00');

		// ------------------------------ 5. una segunda compra se anula
		await page.goto('/inventario/entradas/nueva');
		const buscar = page.locator('input[type="search"]');
		await expect(async () => {
			await buscar.fill('Arroz');
			await expect(page.getByRole('button', { name: /Arroz/i }).first()).toBeVisible({
				timeout: 1000
			});
		}).toPass({ timeout: 10_000 });
		await page.getByRole('button', { name: /Arroz/i }).first().click();
		await page.locator('input[type="number"][aria-label*="osto"]').first().fill('1500');
		await page.locator('#proveedor').selectOption({ index: 1 });
		const segunda = `FC-${marca()}`;
		await page.locator('input[name="document_number"]').fill(segunda);
		await page.getByRole('button', { name: /ingresar|registrar/i }).last().click();
		await expect(page).toHaveURL(/\/inventario\/entradas\?creada=/);

		const fila = page.getByRole('row', { name: new RegExp(segunda) });
		await fila.getByRole('button').last().click();
		await page.locator('#motivo-anular').fill('Se pidió de más');
		await page.getByRole('button', { name: /anular/i }).last().click();
		await expect(fila).toContainText(/anulada/i);

		// La primera sigue debiendo lo suyo: anular una no toca a la otra.
		await page.goto('/compras/cuentas-por-pagar');
		await expect(page.locator('body')).toContainText('12.544,00');
	});

	test('sin el módulo en el plan, el menú lo muestra con candado y el POST rebota', async ({
		page
	}) => {
		/*
		 * RN-49, corregida con el usuario el 2026-09-12: el módulo que el plan no
		 * incluye **se ve con candado, no desaparece**. Es la misma regla que ya
		 * regía para lo que un rol no puede abrir, y acá vale por una razón más:
		 * un «Compras 🔒» es lo único que le dice al dueño que el producto lo
		 * tiene. Lo que no se ve no se compra.
		 */
		const duena = await companiaConCompras(page, 'Básico');
		await entrar(page, duena);

		const compras = page.getByRole('listitem').filter({ hasText: /Compras/ });
		await expect(compras).toHaveCount(1);
		// Y no es un enlace: está bloqueado, así que no lleva a ningún lado.
		await expect(compras.getByRole('link')).toHaveCount(0);
		// El candado dice **por qué**, y a un administrador no le sirve que le
		// digan que pida un cambio de rol: lo que le falta es el plan.
		await expect(compras.locator('[title]')).toHaveAttribute('title', /no está en su plan/i);

		// La pantalla **abre igual**, y eso es RN-50: apagar un módulo no borra
		// nada, lo deja en solo lectura. Quien bajó de plan tiene que poder
		// seguir consultando a quién le compró.
		await page.goto('/compras/proveedores');
		await expect(page.getByRole('heading', { name: /proveedores/i }).first()).toBeVisible();

		// Lo que rebota es escribir, y lo decide el servidor (§8, regla 3): el
		// menú con candado no es control de acceso, y esta prueba entra por la
		// URL justamente para saltárselo.
		await clicHasta(page.getByRole('button', { name: /nuevo proveedor/i }).first(), () =>
			expect(page.locator('#form-proveedor input[name="name"]')).toBeVisible({ timeout: 1000 })
		);
		await page.locator('#form-proveedor input[name="name"]').fill('No debería entrar');
		await page.locator('button[type="submit"][form="form-proveedor"]').click();
		await expect(page.locator('body')).toContainText(/no incluye Compras/i);
	});
});
