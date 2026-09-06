import { expect, test, type Page } from '@playwright/test';
import { abrirCobro, autenticar, clicHasta, salir } from './sesion';

/**
 * Clasificar productos con CABYS, de punta a punta (T-504, T-505, T-506).
 *
 * Lo que estas pruebas comprueban es la **interfaz**: que se pueda buscar un
 * código, que asignarlo copie la tarifa, que cambiarla avise (RN-11) y que la
 * asignación en lote alcance a varios productos de una vez. La aritmética de
 * las tarifas mezcladas vive en `backend/tests/test_impuesto_por_producto.py`,
 * contra MySQL, que es donde tiene que estar.
 *
 * Va contra una **compañía propia**, dada de alta al empezar, por la lección de
 * T-310: una prueba que cambia el catálogo del demo se lo cambia a las otras
 * trece. Acá además es imprescindible, porque clasificar cambia las tarifas y
 * con ellas los totales que varias pruebas fijan.
 */

const SOPORTE = { email: 'soporte@ventasys.cr', password: 'soporte123' };

/**
 * Códigos del catálogo simulado, con la tarifa que les toca.
 *
 * Son **reales**, del CABYS de Hacienda. Los de antes estaban inventados, y un
 * código inventado en una prueba enseña a leer una tarifa que el catálogo de
 * verdad no confirma — que es la causa de rechazo «IVA incorrecto».
 */
// El texto que se busca tiene que dar **una** entrada: «tos» también está dentro
// de «bocadillos de maíz, tostados», que va al 13 %, y elegir el primero de la
// lista traía ese.
const JARABE = { buscar: 'supresores', codigo: '3563704030201', tarifa: '2' };
const LIBRO = { buscar: 'libro', codigo: '3229200000000', tarifa: '0' };

function marca(): string {
	return `${Date.now()}`.slice(-8);
}

/** Da de alta una compañía y devuelve las credenciales de su administrador. */
async function farmaciaNueva(page: Page) {
	const correo = `farmacia${marca()}@ventasys.cr`;
	await autenticar(page, SOPORTE);
	await expect(page).toHaveURL(/\/admin$/);

	await page.goto('/admin/companias/nueva');
	await page.locator('input[name="nombre"]').fill('Farmacia La Cruz');
	await page.locator('input[name="identificacion"]').fill('3101555444');
	await page.locator('input[name="email"]').fill(correo);
	await page.locator('input[name="password"]').fill('dueno123');
	await page.locator('input[name="name"]').fill('Fabiana');
	await page.locator('input[name="lastName"]').fill('Cruz');
	await page.locator('#plan_id').selectOption({ label: 'Comercio' });
	await page.getByRole('button', { name: /Dar de alta/i }).click();
	await expect(page).toHaveURL(/\/admin\/companias\/\d+\?creada=1/);

	await salir(page);
	return { email: correo, password: 'dueno123' };
}

/** Una categoría raíz donde colgar los productos. */
async function crearCategoria(page: Page, nombre: string) {
	await page.goto('/inventario/categorias');
	const campo = page.locator('#category-create input[name="name"]');
	await clicHasta(page.getByRole('button', { name: /Nueva categoría/i }).first(), () =>
		expect(campo).toBeVisible({ timeout: 1000 })
	);
	await campo.fill(nombre);
	// El botón vive FUERA del formulario y lo apunta con `form=`: dentro del
	// modal solo está el marcado del formulario.
	await page.locator('button[type="submit"][form="category-create"]').click();
	await expect(page.getByText(nombre, { exact: true }).first()).toBeVisible();
}

/** Abre la ficha de alta de producto y la llena, sin guardar. */
async function abrirFicha(page: Page, nombre: string, precio: string) {
	await clicHasta(page.getByRole('button', { name: /Nuevo producto/i }).first(), () =>
		expect(page.locator('#product-form input[name="name"]')).toBeVisible({ timeout: 1000 })
	);
	await page.locator('#product-form input[name="name"]').fill(nombre);
	await page.locator('#product-form input[name="description"]').fill(nombre);
	await page.locator('#product-form input[name="price"]').fill(precio);
	await page.locator('#product-form input[name="stock"]').fill('10');
	await page.locator('#product-form input[name="barcode"]').fill(`T${marca()}${nombre.length}`);
}

/** Busca en el catálogo desde la ficha abierta y elige el primer resultado. */
async function buscarYElegir(page: Page, texto: string) {
	await page.locator('#cabys-buscar').fill(texto);
	await page.getByRole('button', { name: /^Buscar$/ }).click();
	await page.locator('[data-testid="cabys-results"] button').first().click();
}

/** Guarda la ficha y espera a que la fila aparezca en la tabla. */
async function guardarFicha(page: Page, nombre: string) {
	await page.getByRole('button', { name: /Agregar producto/i }).click();
	// Por fila y no por celda: la celda del producto lleva nombre y descripción,
	// así que su nombre accesible es «Jarabe Jarabe» y nunca coincide exacto.
	await expect(fila(page, nombre)).toBeVisible();
}

/** La fila del producto en la tabla del inventario. */
function fila(page: Page, nombre: string) {
	return page.getByRole('row', { name: new RegExp(nombre) });
}

test.describe('clasificar con CABYS', () => {
	test.beforeEach(async ({ page }) => {
		const dueno = await farmaciaNueva(page);
		await autenticar(page, dueno);
		// Una sola compañía: se entra directo, sin pantalla de selección (RN-25).
		await expect(page).toHaveURL(/\/(ventas|dashboard)/);
		await crearCategoria(page, 'Salud');
		await page.goto('/inventario');
	});

	test('asignar un código copia su tarifa, y quitarlo devuelve a la configurada', async ({
		page
	}) => {
		await abrirFicha(page, 'Jarabe', '1000');

		// La tarifa nace en blanco: en blanco ES la configurada del negocio (RN-9).
		const tarifa = page.locator('#product-form input[name="tax_rate"]');
		await expect(tarifa).toHaveValue('');

		await clicHasta(page.getByRole('button', { name: /Buscar en el catálogo/i }), () =>
			expect(page.locator('#cabys-buscar')).toBeVisible({ timeout: 1000 })
		);
		await buscarYElegir(page, JARABE.buscar);

		// RN-11: asignar un CABYS ES copiar su tarifa.
		await expect(page.locator('#product-form input[name="cabys_code"]')).toHaveValue(
			JARABE.codigo
		);
		await expect(tarifa).toHaveValue(JARABE.tarifa);

		await guardarFicha(page, 'Jarabe');
		// La tabla lo muestra con SU tarifa, no con la del negocio.
		await expect(fila(page, 'Jarabe')).toContainText('2 %');

		/*
		 * Y la vuelta, que es la mitad que se rompía: clasificar tiene que poder
		 * deshacerse. Con la tarifa en blanco el producto vuelve a heredar la
		 * configurada (RN-9), y eso significa mandar un nulo que de verdad llegue
		 * a la base —el `PUT` parcial se saltaba los nulos, así que el campo era
		 * una puerta de una sola dirección—.
		 */
		await clicHasta(page.getByRole('button', { name: /Editar Jarabe/i }), () =>
			expect(page.locator('#product-form input[name="name"]')).toHaveValue('Jarabe', {
				timeout: 1000
			})
		);
		await page.getByRole('button', { name: /Quitar el código/i }).click();
		await page.locator('#product-form input[name="tax_rate"]').fill('');
		await page.getByRole('button', { name: /Guardar cambios/i }).click();

		await expect(fila(page, 'Jarabe')).toContainText('13 %');
	});

	test('cambiar la tarifa avisa que difiere de la del catálogo (RN-11)', async ({ page }) => {
		await abrirFicha(page, 'Aviso', '1000');
		await clicHasta(page.getByRole('button', { name: /Buscar en el catálogo/i }), () =>
			expect(page.locator('#cabys-buscar')).toBeVisible({ timeout: 1000 })
		);
		await buscarYElegir(page, JARABE.buscar);

		const aviso = page.getByText(/Difiere de la del catálogo/i);
		await expect(aviso).toBeHidden();

		// Se puede cambiar —hay exoneraciones— pero se avisa. El aviso no bloquea.
		await page.locator('#product-form input[name="tax_rate"]').fill('0');
		await expect(aviso).toBeVisible();
		await expect(aviso).toContainText('2 %');

		await guardarFicha(page, 'Aviso');
		await expect(fila(page, 'Aviso')).toContainText('0 %');
	});

	test('el aviso vuelve al reabrir un producto ya clasificado', async ({ page }) => {
		// Es lo que distingue un aviso útil de uno decorativo: si solo existiera
		// durante la sesión en que se asignó el código, al día siguiente —que es
		// cuando importa— no avisaría nada.
		await abrirFicha(page, 'Reabierto', '1000');
		await clicHasta(page.getByRole('button', { name: /Buscar en el catálogo/i }), () =>
			expect(page.locator('#cabys-buscar')).toBeVisible({ timeout: 1000 })
		);
		await buscarYElegir(page, JARABE.buscar);
		await page.locator('#product-form input[name="tax_rate"]').fill('0');
		await guardarFicha(page, 'Reabierto');

		await clicHasta(page.getByRole('button', { name: /Editar Reabierto/i }), () =>
			expect(page.locator('#product-form input[name="name"]')).toHaveValue('Reabierto', {
				timeout: 1000
			})
		);
		await expect(page.getByText(/Difiere de la del catálogo/i)).toBeVisible();
	});

	test('un código que no son trece dígitos se rechaza antes de guardar', async ({ page }) => {
		await abrirFicha(page, 'Codigo malo', '1000');
		await page.locator('#product-form input[name="cabys_code"]').fill('352100000010');
		// El texto exacto: la ayuda del campo también menciona los trece dígitos.
		await expect(page.getByText('El código CABYS son trece dígitos.')).toBeVisible();
	});

	test('la asignación en lote alcanza a varios de una vez (RF-20)', async ({ page }) => {
		for (const nombre of ['Lote uno', 'Lote dos']) {
			await abrirFicha(page, nombre, '1000');
			await guardarFicha(page, nombre);
		}

		await page.goto('/inventario/clasificar');
		// Los dos nacen sin clasificar y el filtro empieza mostrando justo esos.
		await expect(fila(page, 'Lote uno')).toBeVisible();
		await expect(fila(page, 'Lote dos')).toBeVisible();

		await clicHasta(page.locator('#cabys-buscar'), () =>
			expect(page.locator('#cabys-buscar')).toBeEditable({ timeout: 1000 })
		);
		await buscarYElegir(page, LIBRO.buscar);

		await page.getByRole('checkbox', { name: /Seleccionar Lote uno/i }).check();
		await page.getByRole('checkbox', { name: /Seleccionar Lote dos/i }).check();
		await page.getByRole('button', { name: /Asignar a 2/i }).click();

		// Ya no queda nada por clasificar, así que la lista filtrada queda vacía.
		await expect(page.getByText(/Todo el catálogo está clasificado/i)).toBeVisible();

		await page.goto('/inventario');
		for (const nombre of ['Lote uno', 'Lote dos']) {
			await expect(fila(page, nombre)).toContainText(`${LIBRO.tarifa} %`);
		}
	});

	/*
	 * El caso de aceptación de la fase, visto desde el mostrador (T-511).
	 *
	 * La aritmética ya está fijada contra MySQL en
	 * `backend/tests/test_impuesto_por_producto.py`; lo que falta comprobar es
	 * que las mismas cifras lleguen a la pantalla, porque entre el cálculo y la
	 * factura hay un carrito, un modal de cobro y tres plantillas.
	 */
	test('una venta con tres tarifas se cobra y se devuelve por su tarifa (T-511)', async ({
		page
	}) => {
		const canasta = [
			{ nombre: 'Jarabe', buscar: JARABE.buscar, tarifa: '2' },
			// «harina» a secas también encuentra «tortillas de harina de maíz», que
			// va al 1 %: el texto tiene que dar una sola entrada.
			{ nombre: 'Harina', buscar: 'harina de arroz', tarifa: '13' },
			{ nombre: 'Cuento', buscar: LIBRO.buscar, tarifa: '0' }
		];

		for (const item of canasta) {
			await abrirFicha(page, item.nombre, '1000');
			await clicHasta(page.getByRole('button', { name: /Buscar en el catálogo/i }), () =>
				expect(page.locator('#cabys-buscar')).toBeVisible({ timeout: 1000 })
			);
			await buscarYElegir(page, item.buscar);
			await expect(page.locator('#product-form input[name="tax_rate"]')).toHaveValue(item.tarifa);
			await guardarFicha(page, item.nombre);
		}

		/*
		 * Una unidad de cada: subtotal ₡3 000 e impuesto ₡150 —₡20 + ₡130 + ₡0—,
		 * total ₡3 150. Con una tasa única al 13 % el impuesto sería ₡390. Esa
		 * diferencia de ₡240 es toda la fase.
		 */
		await page.goto('/ventas');
		const primero = page.getByRole('button', { name: new RegExp(canasta[0].nombre) }).first();
		await clicHasta(primero, () =>
			expect(page.getByText('₡1.020,00').first()).toBeVisible({ timeout: 1000 })
		);
		for (const item of canasta.slice(1)) {
			await page.getByRole('button', { name: new RegExp(item.nombre) }).first().click();
		}
		await expect(page.getByText('₡3.150,00').first()).toBeVisible();

		const recibido = await abrirCobro(page);
		await recibido.fill('5000');
		await page.locator('button[type="submit"][form="payment-form"]').click();
		await expect(page).toHaveURL(/\/facturas\/\d+/, { timeout: 15_000 });

		// RF-21: el documento desglosa por tarifa cuando hay más de una.
		await expect(page.locator('body')).toContainText('IVA (0 %)');
		await expect(page.locator('body')).toContainText('IVA (2 %)');
		await expect(page.locator('body')).toContainText('IVA (13 %)');

		// Devolver SOLO el jarabe reembolsa ₡1 020, no el promedio de ₡1 050.
		await page.goto('/devoluciones');
		// Por el enlace de la lista y no armando la URL: el id se toma de donde
		// la pantalla lo publica, no de la barra de direcciones de la factura.
		await page.locator('a[href^="/devoluciones?venta="]').first().click();
		/*
		 * La cantidad se escribe hasta que el botón se habilite. El campo es un
		 * `<input type=number>` cuyo `onchange` es el que lleva la cuenta, y ese
		 * manejador solo existe **después de hidratar**: escribirlo antes deja el
		 * número en la pantalla y el estado en cero.
		 */
		const cantidad = page.getByRole('spinbutton', { name: /Unidades a devolver de Jarabe/i });
		const enviar = page.locator('button[type="submit"][form="return-form"]');
		await expect(async () => {
			await cantidad.fill('1');
			await page.locator('#return-reason').fill('Prueba de aceptación de F5');
			await expect(enviar).toBeEnabled({ timeout: 1000 });
		}).toPass({ timeout: 10_000 });
		await enviar.click();

		await expect(page.getByRole('row', { name: /Parcial/ }).first()).toContainText('₡1.020,00');
	});
});
