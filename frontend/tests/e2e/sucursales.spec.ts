import { expect, test, type Page } from '@playwright/test';
import { autenticar, clicHasta, entrar, salir } from './sesion';

/**
 * Sucursales y cajas, de punta a punta (F6, T-608, RF-26).
 *
 * Lo que solo se puede ver acá es el recorrido: abrir un local, ponerle una
 * caja, cerrarlo y borrarlo. Las reglas están probadas contra el stack real en
 * `backend/tests/test_sucursales.py` —el relleno del código, los cupos del plan,
 * las dos puertas de lo que no se puede dejar apagado— y acá se comprueba que
 * las dos mitades hablen: que el «no» del backend llegue como frase y que el
 * estado completo que devuelve cada escritura se vea en la pantalla.
 *
 * **La compañía es propia y se da de alta al empezar**, por lo mismo que en
 * `factura-electronica.spec.ts`: el simulado guarda su estado en
 * `.data/mock-db.json`, y una prueba que le desactiva la sucursal al demo deja a
 * las otras cincuenta y seis sin poder vender.
 */

const SOPORTE = { email: 'soporte@ventasys.cr', password: 'soporte123' };

/** Un correo distinto en cada corrida: el simulado sobrevive entre ellas. */
function marca(): string {
	return `${Date.now()}`.slice(-8);
}

/**
 * Da de alta una compañía desde el panel y devuelve con qué entrar.
 *
 * El plan importa y por eso es parámetro: «Cadena» admite cinco sucursales y
 * quince cajas —hace falta para poder abrir la segunda— y «Básico» admite una de
 * cada, que es justo lo que se necesita para ver el techo.
 */
async function companiaPropia(page: Page, quien: string, plan: 'Cadena' | 'Básico') {
	const sufijo = marca();
	const correo = `suc.${quien}.${sufijo}@pruebas.ventasys.cr`;
	const negocio = `Panadería ${quien} ${sufijo}`;

	await autenticar(page, SOPORTE);
	await expect(page).toHaveURL(/\/admin$/);

	await page.getByRole('link', { name: /Nueva compañía/i }).click();
	await page.locator('input[name="nombre"]').fill(negocio);
	await page.locator('input[name="identificacion"]').fill('3101555444');
	await page.locator('input[name="email"]').fill(correo);
	await page.locator('input[name="password"]').fill('dueno123');
	await page.locator('input[name="name"]').fill('Dueño');
	await page.locator('input[name="lastName"]').fill('DeLocal');
	await page.locator('#plan_id').selectOption({ label: plan });
	await page.getByRole('button', { name: /Dar de alta/i }).click();
	await expect(page).toHaveURL(/\/admin\/companias\/\d+\?creada=1/);

	await salir(page);
	return { email: correo, password: 'dueno123', negocio };
}

/** Entra con el administrador de la compañía y abre la pestaña. */
async function abrirSucursales(page: Page, quien: { email: string; password: string }) {
	// `entrar` y no `autenticar`: el segundo no espera a que la sesión quede
	// hecha, así que el `goto` de la línea siguiente correría contra el login.
	await entrar(page, quien);
	await page.goto('/configuracion');
	// La pestaña no funciona hasta que Svelte hidrata: el HTML ya está pintado,
	// así que Playwright ve un botón listo y lo usa demasiado pronto.
	await clicHasta(page.getByRole('button', { name: /Sucursales y cajas/i }), async () => {
		await expect(page.getByRole('heading', { name: /Sucursales y cajas/i })).toBeVisible();
	});
}

/** La tarjeta de una sucursal. Se localiza por el atributo, no por el rótulo. */
function tarjeta(page: Page, codigo: string) {
	return page.locator(`[data-sucursal="${codigo}"]`);
}

/** Llena y envía la ficha que esté abierta. */
async function llenarFicha(page: Page, formulario: string, codigo: string | null, nombre: string) {
	const ficha = page.locator(`form#${formulario}`);
	if (codigo !== null) await ficha.locator('input[name="codigo"]').fill(codigo);
	await ficha.locator('input[name="nombre"]').fill(nombre);
	await page.locator(`button[type="submit"][form="${formulario}"]`).click();
}

test.describe('el recorrido de un local nuevo', () => {
	test('se abre, se le pone caja, se cierra y se borra', async ({ page }) => {
		const dueno = await companiaPropia(page, 'recorrido', 'Cadena');
		await abrirSucursales(page, dueno);

		// Nace con una de cada, como las que crea `dar_de_alta`: sin ellas no se
		// puede vender, así que no son un paso que alguien tenga que acordarse de
		// dar.
		await expect(tarjeta(page, '001')).toBeVisible();
		await expect(tarjeta(page, '001').locator('[data-caja="00001"]')).toBeVisible();

		// ---------------------------------------------- abrir la segunda
		// Se escribe «7» y se guarda «007»: quien da de alta un local escribe el
		// número que tiene en la cabeza (RN-15).
		await page.getByRole('button', { name: /Nueva sucursal/i }).click();
		await llenarFicha(page, 'form-sucursal', '7', 'Sucursal Sur');
		await expect(tarjeta(page, '007')).toBeVisible();
		await expect(tarjeta(page, '007')).toContainText('Sucursal Sur');
		await expect(tarjeta(page, '007')).toContainText(/no tiene cajas/i);

		// ------------------------------------------------ ponerle una caja
		await tarjeta(page, '007')
			.getByRole('button', { name: /Agregar caja/i })
			.click();
		await llenarFicha(page, 'form-caja', '3', 'Caja del Sur');
		const caja = tarjeta(page, '007').locator('[data-caja="00003"]');
		await expect(caja).toBeVisible();
		await expect(caja).toContainText('Caja del Sur');

		// Y el «00001» de la casa matriz sigue siendo suyo: el código es único
		// **por sucursal**, así que dos locales pueden tener los dos su caja 1.
		await tarjeta(page, '007')
			.getByRole('button', { name: /Agregar caja/i })
			.click();
		await llenarFicha(page, 'form-caja', '1', 'La otra caja 1');
		await expect(tarjeta(page, '007').locator('[data-caja="00001"]')).toBeVisible();
		await expect(tarjeta(page, '001').locator('[data-caja="00001"]')).toContainText('Caja 1');

		// ------------------------------------------------------- cerrarlo
		// Desactivar la sucursal apaga sus cajas: si no, el POS las ofrecería y el
		// consecutivo saldría de un local cerrado.
		await tarjeta(page, '007')
			.getByRole('button', { name: /Editar la sucursal/i })
			.click();
		await page.locator('form#form-sucursal input[name="activa"]').uncheck();
		await page.locator('button[type="submit"][form="form-sucursal"]').click();
		await expect(tarjeta(page, '007')).toContainText(/Inactiva/);
		await expect(tarjeta(page, '007').locator('[data-caja="00003"]')).toContainText(/Inactiva/);

		// -------------------------------------------------------- borrarlo
		// Con cajas colgando no se borra, y el «no» dice **las dos cuentas**:
		// quien lo lee necesita saber qué mover primero.
		await tarjeta(page, '007')
			.getByRole('button', { name: /Eliminar la sucursal/i })
			.click();
		await page.getByRole('button', { name: /Sí, eliminar/i }).click();
		await expect(page.getByText(/tiene 0 movimiento\(s\) y 2 caja\(s\)/i).first()).toBeVisible();
		// El diálogo sigue abierto —el borrado no ocurrió— y su fondo intercepta
		// todo lo de atrás.
		await page.getByRole('button', { name: /Cancelar/i }).click();

		// Las cajas primero. Están apagadas —las apagó el cierre de la sucursal— y
		// se borran igual: una que ya no está encendida no deja a nadie sin caja.
		for (const codigo of ['00001', '00003']) {
			await tarjeta(page, '007')
				.locator(`[data-caja="${codigo}"]`)
				.getByRole('button', { name: /Eliminar la caja/i })
				.click();
			await page.getByRole('button', { name: /Sí, eliminar/i }).click();
			await expect(tarjeta(page, '007').locator(`[data-caja="${codigo}"]`)).toHaveCount(0);
		}

		await tarjeta(page, '007')
			.getByRole('button', { name: /Eliminar la sucursal/i })
			.click();
		await page.getByRole('button', { name: /Sí, eliminar/i }).click();
		await expect(tarjeta(page, '007')).toHaveCount(0);
		await expect(tarjeta(page, '001')).toBeVisible();
	});
});

test.describe('lo que el código no deja hacer (RN-15)', () => {
	test('repetido, con letras, y demasiado largo', async ({ page }) => {
		const dueno = await companiaPropia(page, 'codigos', 'Cadena');
		await abrirSucursales(page, dueno);

		// El relleno es lo que caza el repetido: «1» normalizado es «001», que ya
		// existe. Sin normalizar serían dos filas con el mismo número en el
		// comprobante.
		await page.getByRole('button', { name: /Nueva sucursal/i }).click();
		await llenarFicha(page, 'form-sucursal', '1', 'La misma de siempre');
		await expect(page.getByText(/Ya hay una sucursal con el código 001/i).first()).toBeVisible();

		// Lo que no son dígitos no entra.
		await llenarFicha(page, 'form-sucursal', '1a', 'Con letra');
		await expect(page.getByText(/El código son solo dígitos/i).first()).toBeVisible();

		// Y lo que no cabe **no se recorta**: recortar en silencio sería cambiarle
		// el número a alguien.
		await llenarFicha(page, 'form-sucursal', '1234', 'Demasiado');
		await expect(page.getByText(/no puede pasar de 3 dígitos/i).first()).toBeVisible();
	});

	test('y no se puede cambiar después de creada', async ({ page }) => {
		const dueno = await companiaPropia(page, 'inmutable', 'Cadena');
		await abrirSucursales(page, dueno);

		await tarjeta(page, '001')
			.getByRole('button', { name: /Editar la sucursal/i })
			.click();
		// No hay campo: cambiarlo movería el número de todos los comprobantes ya
		// emitidos desde esta sucursal.
		await expect(page.locator('form#form-sucursal input[name="codigo"]')).toHaveCount(0);
		await expect(page.locator('form#form-sucursal')).toContainText(/no se cambia/i);

		await page.locator('form#form-sucursal input[name="nombre"]').fill('Casa matriz');
		await page.locator('button[type="submit"][form="form-sucursal"]').click();
		await expect(tarjeta(page, '001')).toContainText('Casa matriz');
	});
});

test.describe('las dos puertas que no se pueden cerrar', () => {
	test('no se apaga la última sucursal ni la última caja', async ({ page }) => {
		const dueno = await companiaPropia(page, 'puertas', 'Cadena');
		await abrirSucursales(page, dueno);

		// Una compañía sin sucursal activa no puede vender, y lo descubriría con
		// un cliente enfrente en vez de con alguien configurando.
		await tarjeta(page, '001')
			.getByRole('button', { name: /Editar la sucursal/i })
			.click();
		await page.locator('form#form-sucursal input[name="activa"]').uncheck();
		await page.locator('button[type="submit"][form="form-sucursal"]').click();
		await expect(page.getByText(/al menos una sucursal activa/i).first()).toBeVisible();
		await page.getByRole('button', { name: /Cancelar/i }).click();

		await tarjeta(page, '001')
			.locator('[data-caja="00001"]')
			.getByRole('button', { name: /Editar la caja/i })
			.click();
		await page.locator('form#form-caja input[name="activa"]').uncheck();
		await page.locator('button[type="submit"][form="form-caja"]').click();
		await expect(page.getByText(/al menos una caja activa/i).first()).toBeVisible();
	});
});

test.describe('el techo del plan (RF-12)', () => {
	test('se dice antes de abrir el formulario, no al chocar', async ({ page }) => {
		// «Básico» admite una sucursal y una caja, que es justo lo que ya trae.
		const dueno = await companiaPropia(page, 'techo', 'Básico');
		await abrirSucursales(page, dueno);

		await expect(page.getByText(/1 de 1 sucursales/i)).toBeVisible();
		await expect(page.getByText(/1 de 1 cajas/i)).toBeVisible();

		// Enterarse del techo después de llenar el formulario es el mismo error de
		// diseño que un botón que promete algo que no pasa.
		await expect(page.getByRole('button', { name: /Nueva sucursal/i })).toBeDisabled();
		await expect(page.getByText(/no admite otra sucursal activa/i)).toBeVisible();
		await expect(page.getByRole('button', { name: /Agregar caja/i })).toBeDisabled();
	});
});
