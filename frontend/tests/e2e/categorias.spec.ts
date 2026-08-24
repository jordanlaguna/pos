import { expect, test, type Locator, type Page } from '@playwright/test';
import { ADMIN, autenticar, clicHasta, entrar, entrarAVentas, salir } from './sesion';

/**
 * Categorías de dos niveles, de punta a punta (T-409, F4).
 *
 * La tarea pide comprobarlo con **dos catálogos reales**, y son dos porque se
 * usan distinto:
 *
 * * **Un súper** —«Bebidas → Cervezas, Gaseosas»— es el caso de leer: la grilla
 *   de ventas navega los dos niveles y el inventario filtra por los dos. Va
 *   contra el catálogo del demo, que ya nace repartido, y **no escribe nada**.
 * * **Un repuestero** —«Yamaha → Llantas, Focos»— es el caso de construir: se
 *   arma desde cero, con sus reglas y sus «no». Va contra una **compañía
 *   propia**, dada de alta al empezar, por la lección de T-310: una prueba que
 *   cambia el catálogo del demo se lo cambia a las otras trece.
 *
 * Los selectores no dependen del idioma donde se puede: `input[name=…]`, los
 * `#id` de los desplegables y la URL.
 *
 * Dos cosas hay que reintentar y las dos son la misma: el desplegable del filtro
 * y los botones que abren un modal solo funcionan **después de hidratar**. El
 * HTML ya está pintado, así que Playwright ve un control listo y lo usa; hasta
 * que Svelte le engancha el manejador, no pasa nada. Lo que va por formulario
 * —guardar, reordenar, activar— no necesita ninguna espera.
 */

const SOPORTE = { email: 'soporte@ventasys.cr', password: 'soporte123' };

/** Un correo distinto en cada corrida: el simulado guarda su estado en disco. */
function marca(): string {
	return `${Date.now()}`.slice(-8);
}

/** Da de alta una compañía desde el panel y devuelve su administrador. */
async function repuesteroNuevo(page: Page) {
	const correo = `repuestos${marca()}@ventasys.cr`;
	await autenticar(page, SOPORTE);
	await expect(page).toHaveURL(/\/admin$/);

	await page.goto('/admin/companias/nueva');
	await page.locator('input[name="nombre"]').fill('Repuestos Yamaha');
	await page.locator('input[name="identificacion"]').fill('3101777666');
	await page.locator('input[name="email"]').fill(correo);
	await page.locator('input[name="password"]').fill('dueno123');
	await page.locator('input[name="name"]').fill('Rafa');
	await page.locator('input[name="lastName"]').fill('Repuestos');
	await page.locator('#plan_id').selectOption({ label: 'Comercio' });
	await page.getByRole('button', { name: /Dar de alta/i }).click();
	await expect(page).toHaveURL(/\/admin\/companias\/\d+\?creada=1/);

	await salir(page);
	return { email: correo, password: 'dueno123' };
}

/** Abre el modal de alta y guarda la categoría. */
async function crearCategoria(page: Page, abrir: RegExp, nombre: string) {
	const campo = page.locator('#category-create input[name="name"]');
	await clicHasta(page.getByRole('button', { name: abrir }).first(), () =>
		expect(campo).toBeVisible({ timeout: 1000 })
	);
	await campo.fill(nombre);
	await page.locator('button[type="submit"][form="category-create"]').click();
	await expect(page.getByText(nombre, { exact: true })).toBeVisible();
}

/** Elige en un desplegable hasta que la pantalla obedezca. Ver el encabezado. */
async function elegirHasta(select: Locator, label: string, comprobar: () => Promise<void>) {
	await expect(async () => {
		await select.selectOption({ label });
		await comprobar();
	}).toPass({ timeout: 10_000 });
}

// ---------------------------------------------------------------- el súper

test.describe('un súper: la grilla navega los dos niveles (RF-15)', () => {
	test('la raíz muestra su rama y la ficha muestra solo la suya', async ({ page }) => {
		await entrarAVentas(page);

		// Sin filtro se ve todo, de las dos ramas y de las raíces planas.
		await expect(page.getByRole('button', { name: /Cerveza Imperial/i })).toBeVisible();
		await expect(page.getByRole('button', { name: /Arroz/i }).first()).toBeVisible();

		// Al elegir «Bebidas» aparecen las fichas de sus subcategorías, y la
		// grilla sigue mostrando la rama entera: si mostrara solo los productos
		// colgados de la raíz, quedaría vacía.
		await clicHasta(page.getByRole('button', { name: /^Bebidas$/ }), () =>
			expect(page.getByRole('button', { name: /^Cervezas$/ })).toBeVisible({ timeout: 1000 })
		);
		await expect(page.getByRole('button', { name: /^Gaseosas$/ })).toBeVisible();
		await expect(page.getByRole('button', { name: /Cerveza Imperial/i })).toBeVisible();
		await expect(page.getByRole('button', { name: /Coca-Cola/i })).toBeVisible();
		await expect(page.getByRole('button', { name: /Arroz/i })).toHaveCount(0);

		// Y al elegir «Cervezas», solo lo de esa ficha.
		await page.getByRole('button', { name: /^Cervezas$/ }).click();
		await expect(page.getByRole('button', { name: /Cerveza Imperial/i })).toBeVisible();
		await expect(page.getByRole('button', { name: /Coca-Cola/i })).toHaveCount(0);

		// Volver a una raíz plana descarta la subcategoría: era de la otra rama.
		await page.getByRole('button', { name: /^Abarrotes$/ }).click();
		await expect(page.getByRole('button', { name: /Arroz/i }).first()).toBeVisible();
		await expect(page.getByRole('button', { name: /^Cervezas$/ })).toHaveCount(0);
	});

	test('el inventario filtra por los dos niveles (RF-16)', async ({ page }) => {
		await entrar(page, ADMIN);
		await page.goto('/inventario');

		const filtro = page.locator('#inv-categoria');
		const tabla = page.locator('table.data-table tbody');

		// La columna dice de dónde cuelga cada producto, y eso es lo que
		// distingue dos subcategorías con el mismo nombre en ramas distintas.
		await expect(tabla).toContainText('Bebidas › Cervezas');

		// La raíz arrastra su rama entera.
		await elegirHasta(filtro, 'Toda la categoría', () =>
			expect(tabla).not.toContainText('Arroz', { timeout: 1000 })
		);
		await expect(tabla).toContainText('Cerveza Imperial');
		await expect(tabla).toContainText('Coca-Cola');

		// La subcategoría, solo lo suyo.
		await filtro.selectOption({ label: 'Cervezas' });
		await expect(tabla).toContainText('Cerveza Imperial');
		await expect(tabla).not.toContainText('Coca-Cola');
	});
});

// ----------------------------------------------------------- el repuestero

test.describe('un repuestero: el catálogo se arma desde cero (RF-13, RF-14)', () => {
	test('dos niveles, sus reglas y sus productos', async ({ page }) => {
		const dueno = await repuesteroNuevo(page);
		await entrar(page, dueno);
		await page.goto('/inventario/categorias');

		// --- la raíz y sus dos subcategorías (RF-13)
		await crearCategoria(page, /^Nueva categoría$/, 'Yamaha');
		await crearCategoria(page, /^Nueva subcategoría$/, 'Llantas');
		await crearCategoria(page, /^Nueva subcategoría$/, 'Focos');

		// --- el tercer nivel no se puede ni intentar (RN-5)
		//
		// El botón de «nueva subcategoría» lo tienen las raíces y nadie más: hay
		// tres categorías en pantalla y un solo botón. La regla también está en el
		// servidor —`test_categorias.py` la prueba con el código de error— pero
		// que la pantalla no ofrezca lo que va a ser rechazado es parte de RF-13.
		await expect(page.getByRole('button', { name: /^Nueva subcategoría$/ })).toHaveCount(1);

		// --- dos hermanas no se llaman igual
		await clicHasta(page.getByRole('button', { name: /^Nueva subcategoría$/ }), () =>
			expect(page.locator('#category-create input[name="name"]')).toBeVisible({ timeout: 1000 })
		);
		await page.locator('#category-create input[name="name"]').fill('Llantas');
		await page.locator('button[type="submit"][form="category-create"]').click();
		await expect(page.locator('body')).toContainText(/Llantas/);
		await expect(page.getByText('Llantas', { exact: true })).toHaveCount(1);
		await page.keyboard.press('Escape');

		// --- el producto va en la hoja (RN-6)
		await page.goto('/inventario');
		await clicHasta(page.getByRole('button', { name: /^Nuevo producto$/ }), () =>
			expect(page.locator('#product-form input[name="name"]')).toBeVisible({ timeout: 1000 })
		);
		await page.locator('input[name="name"]').fill('Llanta 90/90-18');
		await page.locator('input[name="description"]').fill('Llanta trasera');
		await page.locator('input[name="price"]').fill('45000');
		await page.locator('input[name="stock"]').fill('4');
		await page.locator('input[name="barcode"]').fill(`Y${marca()}`);
		// Al elegir la raíz con rama, el segundo desplegable ofrece sus hijas y es
		// la hija la que viaja: la raíz con hijas no puede recibir productos.
		await page.locator('#product-category').selectOption({ label: 'Yamaha' });
		await page.locator('#product-subcategory').selectOption({ label: 'Llantas' });
		await page.locator('button[type="submit"][form="product-form"]').click();

		const tabla = page.locator('table.data-table tbody');
		await expect(tabla).toContainText('Llanta 90/90-18');
		await expect(tabla).toContainText('Yamaha › Llantas');

		// --- con productos no se borra: se desactiva (RN-7)
		await page.goto('/inventario/categorias');
		// El botón del diálogo dice «Eliminar» (`common_delete`) y el de la fila,
		// «Borrar {categoría}»: son dos claves distintas y conviene no confundirlas.
		await clicHasta(page.getByRole('button', { name: /Borrar Llantas/i }), () =>
			expect(page.getByRole('button', { name: /^Eliminar$/ })).toBeVisible({ timeout: 1000 })
		);
		await page.getByRole('button', { name: /^Eliminar$/ }).click();
		await expect(page.locator('body')).toContainText(/producto/i);
		await expect(page.getByText('Llantas', { exact: true })).toBeVisible();
		await page.keyboard.press('Escape');

		// --- mover una subcategoría de raíz no toca sus productos (RF-14)
		await crearCategoria(page, /^Nueva categoría$/, 'Suzuki');
		await clicHasta(page.getByRole('button', { name: /Mover Llantas/i }), () =>
			expect(page.locator('#category-parent')).toBeVisible({ timeout: 1000 })
		);
		await page.locator('#category-parent').selectOption({ label: 'Suzuki' });
		await page.locator('button[type="submit"][form="category-move"]').click();

		await page.goto('/inventario');
		// El producto sigue en «Llantas», que es la que se mudó: ahora su camino
		// dice Suzuki. Es exactamente lo que pide RF-14 —los productos no se
		// tocan— y la razón de que el producto apunte a la categoría y no a la rama.
		await expect(tabla).toContainText('Suzuki › Llantas');
		await expect(tabla).toContainText('Llanta 90/90-18');

		// --- desactivada, ya no recibe productos nuevos
		await page.goto('/inventario/categorias');
		await page.getByRole('button', { name: /Desactivar Llantas/i }).click();
		await expect(page.getByRole('button', { name: /Activar Llantas/i })).toBeVisible();

		await page.goto('/inventario');
		// El producto que ya estaba se queda: desactivar no mueve nada.
		await expect(tabla).toContainText('Llanta 90/90-18');
		await clicHasta(page.getByRole('button', { name: /^Nuevo producto$/ }), () =>
			expect(page.locator('#product-category')).toBeVisible({ timeout: 1000 })
		);
		await page.locator('#product-category').selectOption({ label: 'Suzuki' });
		await expect(page.locator('#product-subcategory')).toHaveCount(0);
	});

	test('reordenar cambia el orden de la grilla (RF-13)', async ({ page }) => {
		const dueno = await repuesteroNuevo(page);
		await entrar(page, dueno);
		await page.goto('/inventario/categorias');

		await crearCategoria(page, /^Nueva categoría$/, 'Yamaha');
		await crearCategoria(page, /^Nueva subcategoría$/, 'Llantas');
		await crearCategoria(page, /^Nueva subcategoría$/, 'Focos');

		const subcategorias = page.locator('section li p');
		await expect(subcategorias).toHaveText(['Llantas', 'Focos']);

		// Focos sube un lugar. El botón manda la categoría y la dirección; el
		// orden entero lo arma el servidor, y por eso funciona sin JavaScript.
		await page.getByRole('button', { name: /Subir Focos/i }).click();
		await expect(subcategorias).toHaveText(['Focos', 'Llantas']);

		// La primera ya no puede subir.
		await expect(page.getByRole('button', { name: /Subir Focos/i })).toBeDisabled();

		// Y el orden es el que ve el cajero en la grilla de ventas.
		await page.goto('/ventas');
		await clicHasta(page.getByRole('button', { name: /^Yamaha$/ }), () =>
			expect(page.getByRole('button', { name: /^Focos$/ })).toBeVisible({ timeout: 1000 })
		);
		await expect(page.locator('.badge').filter({ hasText: /^(Focos|Llantas)$/ })).toHaveText([
			'Focos',
			'Llantas'
		]);
	});
});
