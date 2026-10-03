import { expect, test, type Page } from '@playwright/test';
import { abrirCobro, autenticar, clicHasta, entrar, salir } from './sesion';

/**
 * El tipo de comprobante y el bloque fiscal, de punta a punta (T-723, T-724).
 *
 * Salió de mirar la pantalla: con la facturación activa, **toda** venta se
 * imprimía «Factura electrónica» —incluida la del cliente de contado del
 * supermercado, que sin receptor no puede serlo—, y nada en la caja decía qué
 * se estaba emitiendo. Las reglas están probadas sin navegador en los dos lados
 * (`documentType.test.ts`, `test_fe_document_type.py`) y contra MySQL en
 * `test_tipo_de_comprobante.py`; acá se comprueba lo que ve el cajero y lo que
 * sale impreso en **las tres** plantillas.
 *
 * **La compañía es propia.** Activar la facturación cambia lo que se imprime en
 * cada venta, y hacerlo en el demo se lo cambiaría a todas las demás pruebas
 * (la lección de T-310).
 */

const SOPORTE = { email: 'soporte@ventasys.cr', password: 'soporte123' };

function marca(): string {
	return `${Date.now()}`.slice(-8);
}

/** Da de alta la compañía y devuelve con qué entrar. */
async function supermercadoNuevo(page: Page) {
	const correo = `super${marca()}@ventasys.cr`;
	await autenticar(page, SOPORTE);
	await expect(page).toHaveURL(/\/admin$/);

	await page.goto('/admin/companias/nueva');
	await page.locator('input[name="nombre"]').fill(`Súper ${marca()}`);
	await page.locator('input[name="identificacion"]').fill(`310${marca()}`);
	await page.locator('input[name="email"]').fill(correo);
	await page.locator('input[name="password"]').fill('dueno123');
	await page.locator('input[name="name"]').fill('Sara');
	await page.locator('input[name="lastName"]').fill('Mercado');
	await page.locator('#plan_id').selectOption({ label: 'Comercio' });
	await page.getByRole('button', { name: /Dar de alta/i }).click();
	await expect(page).toHaveURL(/\/admin\/companias\/\d+\?creada=1/);
	// La ficha del panel, para volver a ella como soporte.
	const ficha = new URL(page.url()).pathname;

	await salir(page);
	return { email: correo, password: 'dueno123', ficha };
}

async function crearProducto(page: Page) {
	await page.goto('/inventario/categorias');
	const campo = page.locator('#category-create input[name="name"]');
	await clicHasta(page.getByRole('button', { name: /Nueva categoría/i }).first(), () =>
		expect(campo).toBeVisible({ timeout: 1000 })
	);
	await campo.fill('Abarrotes');
	await page.locator('button[type="submit"][form="category-create"]').click();
	await expect(page.getByText('Abarrotes', { exact: true }).first()).toBeVisible();

	await page.goto('/inventario');
	await clicHasta(page.getByRole('button', { name: /Nuevo producto/i }).first(), () =>
		expect(page.locator('#product-form input[name="name"]')).toBeVisible({ timeout: 1000 })
	);
	await page.locator('#product-form input[name="name"]').fill('Arroz');
	await page.locator('#product-form input[name="description"]').fill('Arroz');
	await page.locator('#product-form input[name="price"]').fill('1000');
	await page.locator('#product-form input[name="stock"]').fill('50');
	await page.locator('#product-form input[name="barcode"]').fill(`T${marca()}`);
	// Con CABYS: el comprobante lo imprime por línea, congelado en la venta (T-731).
	await page.locator('#product-form input[name="cabys_code"]').fill('2316100000100');
	await page.getByRole('button', { name: /Agregar producto/i }).click();
	await expect(page.getByRole('row', { name: /Arroz/ }).first()).toBeVisible();
}

async function crearCliente(page: Page) {
	await page.goto('/clientes');
	const cedula = page.locator('#client-form input[name="identification"]');
	await clicHasta(page.getByRole('button', { name: /Nuevo cliente/i }).first(), () =>
		expect(cedula).toBeVisible({ timeout: 1000 })
	);
	await cedula.fill(`1${marca()}`);
	await page.locator('#client-form input[name="name"]').fill('Ana');
	await page.locator('#client-form input[name="last_name"]').fill('Receptora');
	await page.locator('#client-form input[name="second_name"]').fill('Pérez');
	await page.locator('#client-form input[name="email"]').fill(`ana${marca()}@correo.cr`);
	await page.locator('#client-form input[name="telephone"]').fill('88887777');
	await page.locator('#client-form input[name="address"]').fill('San José');
	await page.locator('#client-form input[name="register_date"]').fill('2026-09-01');
	await page.locator('button[type="submit"][form="client-form"]').click();
	await expect(page.getByRole('row', { name: /Receptora/ })).toBeVisible();
}

/** Abre una pestaña de Configuración, esperando a que la página hidrate. */
async function pestana(page: Page, nombre: RegExp, dentro: string) {
	await page.goto('/configuracion');
	await clicHasta(page.getByRole('button', { name: nombre }).first(), () =>
		expect(page.locator(dentro)).toBeVisible({ timeout: 1000 })
	);
}

/**
 * Guarda y **espera la respuesta**. `networkidle` a secas no alcanza: puede
 * cumplirse antes de que salga la petición, y entonces la navegación siguiente
 * corta el guardado a medias —la venta sale sin facturación, o el `goto` se
 * aborta—, y la prueba falla señalando la pantalla de ventas.
 */
async function guardarConfiguracion(page: Page) {
	const respuesta = page.waitForResponse(
		(r) => r.url().includes('/configuracion') && r.request().method() === 'POST'
	);
	await page.locator('button[type="submit"][form="config-form"]').click();
	expect((await respuesta).ok(), 'no se pudo guardar la configuración').toBe(true);
	await page.waitForLoadState('networkidle');
}

/**
 * La ubicación del emisor, la de la factura de referencia: San José, San José,
 * Zapote (T-722). Deja elegido cada nivel antes del siguiente, que es lo que
 * llena el desplegable de abajo.
 */
async function llenarUbicacion(page: Page) {
	// Elegir antes de que la página hidrate cambia el desplegable y no el estado:
	// el cantón se queda sin opciones. Se reintenta hasta que la elección llegue.
	await expect(async () => {
		await page.locator('#ubicacion-provincia').selectOption('1');
		await expect(page.locator('#ubicacion-canton')).toBeEnabled({ timeout: 1000 });
	}).toPass({ timeout: 15_000 });
	await page.locator('#ubicacion-canton').selectOption('01');
	await expect(page.locator('#ubicacion-distrito')).toBeEnabled();
	await page.locator('#ubicacion-distrito').selectOption('05');
	await page.locator('#ubicacion-senas').fill('600 m oeste de Plaza Cristal');
}

/**
 * Enciende la facturación con el emisor completo (T-722): sin correo ni
 * ubicación, Configuración no la deja encender. La cédula la puso soporte al
 * dar de alta.
 */
async function activarFacturacion(page: Page) {
	await pestana(page, /^Negocio$/, '#ubicacion-provincia');
	await page.locator('input[name="negocio_correo"]').fill('facturas@super.cr');
	await llenarUbicacion(page);
	await clicHasta(page.getByRole('button', { name: /Factura electrónica/i }).first(), () =>
		expect(page.locator('input[name="electronica_activa"]')).toBeVisible({ timeout: 1000 })
	);
	await page.locator('input[name="electronica_activa"]').check();
	await guardarConfiguracion(page);
}

async function elegirPlantilla(page: Page, id: 'tiquete' | 'clasica' | 'moderna') {
	const radio = `input[name="documento_plantilla"][value="${id}"]`;
	await pestana(page, /^Documentos$/, radio);
	await page.locator(radio).check();
	await guardarConfiguracion(page);
}

/** Deja el arroz en la venta activa, esperando a que la pantalla responda. */
async function llenarVenta(page: Page) {
	await page.goto('/ventas');
	const buscar = page.locator('input[type="search"]').first();
	await expect(async () => {
		await buscar.fill('Arroz');
		await expect(page.getByRole('button', { name: /Arroz/i }).first()).toBeVisible({
			timeout: 1000
		});
	}).toPass({ timeout: 15_000 });
	await clicHasta(page.getByRole('button', { name: /Arroz/i }).first(), () =>
		expect(page.locator('body')).toContainText('1.130,00', { timeout: 1000 })
	);
}

async function confirmarCobro(page: Page): Promise<string> {
	// Se guarda la respuesta de la acción: si el cobro no entra, el aviso ya se
	// desvaneció cuando la espera se rinde, y sin esto la prueba solo diría que
	// la página no cambió.
	const respuesta = page.waitForResponse(
		(r) => r.url().includes('/ventas') && r.request().method() === 'POST'
	);
	await page.locator('button[type="submit"][form="payment-form"]').click();
	const r = await respuesta;
	const cuerpo = `${await r.text()} ← ${r.request().postData() ?? ''}`;
	await expect(page, `el cobro no entró: ${cuerpo}`).toHaveURL(/\/facturas\/\d+/, {
		timeout: 15_000
	});
	return new URL(page.url()).pathname;
}

const TIQUETE = 'input[name="document_type"][value="04"]';
const FACTURA = 'input[name="document_type"][value="01"]';

test.describe('el tipo de comprobante (RN-85) y el bloque fiscal (RN-86)', () => {
	let dueno: { email: string; password: string };

	test.beforeEach(async ({ page }) => {
		dueno = await supermercadoNuevo(page);
		await entrar(page, dueno);
		await crearProducto(page);
	});

	test('sin facturación electrónica no hay nada que elegir ni que imprimir', async ({ page }) => {
		await llenarVenta(page);
		await expect(page.locator('[data-comprobante]')).toHaveCount(0);

		const recibido = await abrirCobro(page);
		await expect(page.locator(TIQUETE)).toHaveCount(0);
		await recibido.fill('2000');
		await confirmarCobro(page);

		// El documento de siempre: sin bloque fiscal y con el título de siempre.
		await expect(page.locator('[data-fiscal]')).toHaveCount(0);
		await expect(page.locator('.print-sheet')).toContainText('Factura');
		await expect(page.locator('.print-sheet')).not.toContainText('electrónic');
	});

	test('el cliente de contado recibe un tiquete, y lo sabe antes de cobrar', async ({ page }) => {
		await activarFacturacion(page);
		await llenarVenta(page);

		// Junto al botón de cobrar, antes de abrir nada.
		await expect(page.locator('[data-comprobante="04"]')).toContainText('Tiquete electrónico');

		const recibido = await abrirCobro(page);
		await expect(page.locator(TIQUETE)).toBeChecked();
		// La factura se ve apagada, no escondida: el cajero tiene que entender por
		// qué no está.
		await expect(page.locator(FACTURA)).toBeDisabled();
		await expect(page.getByText(/elija un cliente/i)).toBeVisible();

		await recibido.fill('2000');
		await confirmarCobro(page);

		const hoja = page.locator('.print-sheet');
		await expect(hoja).toContainText('Tiquete electrónico');
		// Numerado al vender (T-704, T-705): el ambiente es el de pruebas, y lo dice.
		await expect(page.locator('[data-fiscal="sandbox"]')).toContainText(/ambiente de pruebas/i);
		// El número de la cabecera es el consecutivo: oficina, caja, tiquete, uno.
		await expect(hoja.locator('[data-cabecera]')).toContainText('00100001040000000001');
		// La clave: 50 dígitos, con el día de hoy y la cédula que puso soporte.
		const clave = await page.locator('[data-clave]').getAttribute('data-clave');
		expect(clave).toMatch(/^506\d{47}$/);
		expect(clave!.slice(21, 41)).toBe('00100001040000000001');
		// Impresa en tramos, como la factura de referencia.
		await expect(page.locator('[data-clave]')).toContainText(`${clave!.slice(0, 3)} ${clave!.slice(3, 9)} `);
		// Y al pie, el QR con la clave sola, como el de la factura aceptada.
		await expect(page.locator('[data-fiscal-pie] [data-qr]')).toHaveAttribute('data-qr', clave!);
		// Y el emisor, con la ubicación de Hacienda (T-722).
		await expect(hoja.locator('[data-emisor]')).toContainText(
			'Provincia: San José / Cantón: San José / Distrito: Zapote'
		);
		await expect(hoja.locator('[data-emisor]')).toContainText('600 m oeste de Plaza Cristal');
	});

	test('con cliente sale factura en las tres plantillas, y se ve en el historial', async ({
		page
	}) => {
		await crearCliente(page);
		await activarFacturacion(page);
		await llenarVenta(page);

		const recibido = await abrirCobro(page);
		// El único cliente de la compañía, después de «Cliente de contado».
		await page.locator('#client-select').selectOption({ index: 1 });
		// Elegir un cliente sugiere la factura (RN-85).
		await expect(page.locator(FACTURA)).toBeChecked();
		await expect(page.locator('[data-comprobante="01"]')).toContainText('Factura electrónica');

		await recibido.fill('2000');
		const factura = await confirmarCobro(page);

		// El cliente llegó a la venta: el documento lo nombra. Antes de T-723 la
		// pestaña lo mostraba y la venta se guardaba de contado.
		await expect(page.locator('.print-sheet')).toContainText('Receptora');

		// RN-86: el bloque fiscal en las tres plantillas, no solo en la que estaba
		// elegida. El título sigue a la venta, no a la configuración.
		for (const plantilla of ['tiquete', 'clasica', 'moderna'] as const) {
			await elegirPlantilla(page, plantilla);
			await page.goto(factura);
			const hoja = page.locator('.print-sheet');
			await expect(hoja, `plantilla ${plantilla}`).toContainText('Factura electrónica');
			await expect(page.locator('[data-fiscal="sandbox"]'), `plantilla ${plantilla}`).toBeVisible();
			// La misma clave y la misma ubicación en las tres (RN-86).
			await expect(page.locator('[data-clave]'), `plantilla ${plantilla}`).toHaveAttribute(
				'data-clave',
				/^506\d{47}$/
			);
			// El QR al pie, con la misma clave que la cabecera (T-705).
			const laClave = await page.locator('[data-clave]').getAttribute('data-clave');
			await expect(page.locator('[data-fiscal-pie] [data-qr]'), `plantilla ${plantilla}`).toHaveAttribute(
				'data-qr',
				laClave!
			);
			await expect(hoja.locator('[data-emisor]'), `plantilla ${plantilla}`).toContainText(
				'Distrito: Zapote'
			);

			// T-731: lo que la factura de referencia lleva, en las tres.
			const en = `plantilla ${plantilla}`;
			await expect(hoja.locator('[data-condicion]'), en).toContainText('Contado');
			await expect(hoja.locator('[data-moneda]'), en).toContainText('CRC (TC 1.00)');
			await expect(hoja.locator('[data-cabys]').first(), en).toContainText('2316100000100');
			// La cédula de nueve dígitos se guardó como física sin que nadie la eligiera.
			await expect(hoja.locator('[data-receptor]'), en).toContainText('Cédula física');
			await expect(hoja.locator('[data-resumen]'), en).toContainText('Total venta neta');
			await expect(hoja, en).toContainText('Total comprobante');
			await expect(hoja.locator('[data-en-letras]'), en).toContainText('CON 00/100 COLONES');
		}

		await page.goto('/facturas');
		await expect(page.locator('td[data-comprobante="01"]').first()).toContainText(
			'Factura electrónica'
		);
	});

	test('el cajero puede dejar en tiquete a un cliente', async ({ page }) => {
		await crearCliente(page);
		await activarFacturacion(page);
		await llenarVenta(page);

		const recibido = await abrirCobro(page);
		await page.locator('#client-select').selectOption({ index: 1 });
		await expect(page.locator(FACTURA)).toBeChecked();

		// El radio está oculto detrás de su rótulo, que es lo que se pulsa.
		await page.locator('label').filter({ has: page.locator(TIQUETE) }).click();
		await expect(page.locator(TIQUETE)).toBeChecked();

		await recibido.fill('2000');
		await confirmarCobro(page);
		const hoja = page.locator('.print-sheet');
		await expect(hoja).toContainText('Tiquete electrónico');
		// Tiquete, pero con su cliente: bajar el comprobante no lo borra.
		await expect(hoja).toContainText('Receptora');
	});
});

/**
 * La casilla de un comprobante en Configuración. Por tipo y no solo por nombre:
 * la que está bloqueada y encendida viaja además en un campo oculto con el mismo
 * nombre y valor.
 */
function casilla(page: Page, codigo: string) {
	return page.locator(`input[type="checkbox"][name="electronica_comprobantes"][value="${codigo}"]`);
}

/** Enciende o apaga comprobantes en Configuración (RN-88) y guarda. */
async function comprobantes(page: Page, cambios: Record<string, boolean>) {
	await pestana(page, /Factura electrónica/i, '[data-comprobantes]');
	for (const [codigo, encendido] of Object.entries(cambios)) {
		await casilla(page, codigo).setChecked(encendido);
	}
	await guardarConfiguracion(page);
}

/** Un cliente del extranjero (identificación 05), con su dirección de afuera. */
async function crearClienteExtranjero(page: Page) {
	await page.goto('/clientes');
	const cedula = page.locator('#client-form input[name="identification"]');
	await clicHasta(page.getByRole('button', { name: /Nuevo cliente/i }).first(), () =>
		expect(cedula).toBeVisible({ timeout: 1000 })
	);
	await page.locator('#client-form select[name="identification_type"]').selectOption('05');
	await cedula.fill(`P${marca().slice(-7)}`);
	await page.locator('#client-form input[name="name"]').fill('Foreign');
	await page.locator('#client-form input[name="last_name"]').fill('Buyer');
	await page.locator('#client-form input[name="second_name"]').fill('Inc');
	await page.locator('#client-form input[name="email"]').fill(`buyer${marca()}@example.com`);
	await page.locator('#client-form input[name="telephone"]').fill('13055550100');
	await page.locator('#client-form input[name="foreign_address"]').fill('12 Main St, Miami, FL');
	await page.locator('#client-form input[name="register_date"]').fill('2026-09-01');
	await page.locator('button[type="submit"][form="client-form"]').click();
	await expect(page.getByRole('row', { name: /Buyer/ })).toBeVisible();
}

/** Una mercancía que se puede exportar: con CABYS y con partida arancelaria. */
async function crearProductoExportable(page: Page) {
	await page.goto('/inventario');
	await clicHasta(page.getByRole('button', { name: /Nuevo producto/i }).first(), () =>
		expect(page.locator('#product-form input[name="name"]')).toBeVisible({ timeout: 1000 })
	);
	await page.locator('#product-form input[name="name"]').fill('Café');
	await page.locator('#product-form input[name="description"]').fill('Café');
	await page.locator('#product-form input[name="price"]').fill('1000');
	await page.locator('#product-form input[name="stock"]').fill('50');
	await page.locator('#product-form input[name="barcode"]').fill(`C${marca()}`);
	await page.locator('#product-form input[name="cabys_code"]').fill('2316100000100');
	await page.locator('#product-form input[name="tariff_heading"]').fill('090111000000');
	await page.getByRole('button', { name: /Agregar producto/i }).click();
	await expect(page.getByRole('row', { name: /Café/ }).first()).toBeVisible();
}

/** Como `llenarVenta`, con el producto que se le diga. Los dos cuestan 1 000. */
async function llenarVentaDe(page: Page, nombre: RegExp) {
	await page.goto('/ventas');
	const buscar = page.locator('input[type="search"]').first();
	await expect(async () => {
		await buscar.fill(nombre.source);
		await expect(page.getByRole('button', { name: nombre }).first()).toBeVisible({ timeout: 1000 });
	}).toPass({ timeout: 15_000 });
	await clicHasta(page.getByRole('button', { name: nombre }).first(), () =>
		expect(page.locator('body')).toContainText('1.130,00', { timeout: 1000 })
	);
}

/** Un proveedor no contribuyente (identificación 06): a él se le emite la FEC. */
async function crearProveedorNoContribuyente(page: Page) {
	await page.goto('/compras/proveedores');
	await clicHasta(page.getByRole('button', { name: /nuevo proveedor/i }).first(), () =>
		expect(page.locator('#form-proveedor input[name="name"]')).toBeVisible({ timeout: 1000 })
	);
	await page.locator('#form-proveedor input[name="name"]').fill('Doña Flor');
	await page.locator('#form-proveedor select[name="identification_type"]').selectOption('06');
	await page.locator('#form-proveedor input[name="identification"]').fill(`1${marca()}`);
	await page.locator('button[type="submit"][form="form-proveedor"]').click();
	await expect(page.getByRole('row', { name: /Doña Flor/ })).toBeVisible();
}

/** Una compra de contado de una unidad de Arroz al primer proveedor de la lista. */
async function comprarArroz(page: Page): Promise<string> {
	await page.goto('/inventario/entradas/nueva');
	const buscar = page.locator('input[type="search"]');
	await expect(async () => {
		await buscar.fill('Arroz');
		await expect(page.getByRole('button', { name: /Arroz/i }).first()).toBeVisible({ timeout: 1000 });
	}).toPass({ timeout: 15_000 });
	await page.getByRole('button', { name: /Arroz/i }).first().click();
	await page.locator('input[type="number"][aria-label*="osto"]').first().fill('500');
	await page.locator('#proveedor').selectOption({ index: 1 });
	const documento = `REC-${marca()}`;
	await page.locator('input[name="document_number"]').fill(documento);
	await page.locator('#condicion').selectOption('cash');
	await page.getByRole('button', { name: /ingresar|registrar/i }).last().click();
	await expect(page).toHaveURL(/\/inventario\/entradas\?creada=/);
	return documento;
}

/** Devuelve una unidad de lo que se vendió, desde la pantalla de Devoluciones. */
async function devolverUna(page: Page, factura: string) {
	const venta = factura.split('/').pop();
	await page.goto(`/devoluciones?venta=${venta}`);
	const cantidad = page.getByRole('spinbutton', { name: /Unidades a devolver de Arroz/i });
	const enviar = page.locator('button[type="submit"][form="return-form"]');
	// El contador lo lleva el cliente: escribir antes de hidratar deja el número
	// en la pantalla y el estado en cero.
	await expect(async () => {
		await cantidad.fill('1');
		await page.locator('#return-reason').fill('No le quedó');
		await expect(enviar).toBeEnabled({ timeout: 1000 });
	}).toPass({ timeout: 10_000 });
	await enviar.click();
}

test.describe('los comprobantes de cada compañía (RN-88) y las notas (RN-89)', () => {
	test.beforeEach(async ({ page }) => {
		const dueno = await supermercadoNuevo(page);
		await entrar(page, dueno);
		await crearProducto(page);
	});

	test('al cliente del extranjero se le exporta, y la partida se exige antes de cobrar (T-727)', async ({
		page
	}) => {
		test.setTimeout(180_000);
		await activarFacturacion(page);
		await credencialesDePruebas(page);
		await comprobantes(page, { '09': true });
		await crearClienteExtranjero(page);
		await crearProductoExportable(page);

		// Con la partida, sale: la exportación se sugiere sola y la factura no se
		// ofrece (RN-87). El tiquete sigue ahí.
		await llenarVentaDe(page, /Café/);
		const recibido = await abrirCobro(page);
		await page.locator('#client-select').selectOption({ index: 1 });
		await expect(page.locator('input[name="document_type"][value="09"]')).toBeChecked();
		await expect(page.locator(FACTURA)).toHaveCount(0);
		await expect(page.locator(TIQUETE)).toBeEnabled();
		await expect(page.locator('[data-comprobante="09"]')).toBeVisible();
		await recibido.fill('2000');
		const exportacion = await confirmarCobro(page);
		await expect(page.getByText(/Factura electrónica de exportación/).first()).toBeVisible();
		// Y recorre la cola como las demás, hasta aceptada (RN-39).
		await esperarEstado(page, exportacion, 'accepted');

		// Sin la partida, no se cobra y se dice de cuál producto (RF-78).
		await llenarVenta(page);
		const recibido2 = await abrirCobro(page);
		await page.locator('#client-select').selectOption({ index: 1 });
		await recibido2.fill('2000');
		await page.locator('button[type="submit"][form="payment-form"]').click();
		await expect(page.getByText(/Arroz no tiene partida arancelaria/i).first()).toBeVisible({
			timeout: 15_000
		});
	});

	test('comprarle a un no contribuyente emite la factura de compra (T-728)', async ({ page }) => {
		test.setTimeout(180_000);
		await activarFacturacion(page);
		await credencialesDePruebas(page);
		await comprobantes(page, { '08': true });
		await crearProveedorNoContribuyente(page);

		const documento = await comprarArroz(page);
		const fila = page.getByRole('row', { name: new RegExp(documento) });
		await expect(fila).toContainText(/Factura electrónica de compra/);

		// Su expediente, desde la fila: recorre la cola hasta aceptada (RN-39).
		await expect(async () => {
			await page.reload();
			await page
				.getByRole('row', { name: new RegExp(documento) })
				.getByRole('button', { name: /Ver detalle/i })
				.click();
			await expect(page.locator('[data-expediente][data-estado="accepted"]')).toBeVisible({
				timeout: 2000
			});
		}).toPass({ timeout: 40_000 });
		await expect(page.locator('[data-xml-firmado]')).toBeVisible();
		await expect(page.locator('[data-respuesta-hacienda]')).toBeVisible();
	});

	test('una distribuidora que apaga el tiquete no cobra sin cliente', async ({ page }) => {
		await crearCliente(page);
		await activarFacturacion(page);

		// La NC no se apaga: se ve, no se mueve. La ND (T-726) y la exportación
		// (T-727) ya tienen flujo: sus casillas se mueven. El REP no.
		await pestana(page, /Factura electrónica/i, '[data-comprobantes]');
		await expect(casilla(page, '03')).toBeDisabled();
		await expect(casilla(page, '03')).toBeChecked();
		await expect(casilla(page, '02')).toBeEnabled();
		await expect(casilla(page, '09')).toBeEnabled();
		await expect(casilla(page, '10')).toBeDisabled();

		await comprobantes(page, { '04': false });
		// Queda la factura sola, y es la última de venta: ya no se puede apagar. Y
		// guardar no apagó la NC, que está bloqueada, ni la ND, que nadie tocó.
		await pestana(page, /Factura electrónica/i, '[data-comprobantes]');
		await expect(casilla(page, '01')).toBeDisabled();
		await expect(casilla(page, '04')).not.toBeChecked();
		await expect(casilla(page, '03')).toBeChecked();
		await expect(casilla(page, '02')).toBeChecked();

		await llenarVenta(page);
		await expect(page.locator('[data-comprobante=""]')).toContainText(/Elija un cliente/i);

		const recibido = await abrirCobro(page);
		await expect(page.locator(TIQUETE)).toHaveCount(0);
		await expect(page.getByText(/solo emite facturas electrónicas/i)).toBeVisible();
		await expect(page.locator('button[type="submit"][form="payment-form"]')).toBeDisabled();

		await page.locator('#client-select').selectOption({ index: 1 });
		await expect(page.locator(FACTURA)).toBeChecked();
		await recibido.fill('2000');
		await confirmarCobro(page);
		await expect(page.locator('.print-sheet')).toContainText('Factura electrónica');
	});

	test('devolver de un tiquete emite su nota de crédito, referenciada', async ({ page }) => {
		await activarFacturacion(page);
		await llenarVenta(page);
		const recibido = await abrirCobro(page);
		await recibido.fill('2000');
		const factura = await confirmarCobro(page);

		await devolverUna(page, factura);
		await expect(page).toHaveURL(/\/devoluciones\/\d+\?nueva=1/, { timeout: 15_000 });

		const hoja = page.locator('.print-sheet');
		await expect(hoja).toContainText('Nota de crédito electrónica');
		const referencia = page.locator('[data-referencia]');
		await expect(referencia).toContainText('Tiquete electrónico');
		await expect(referencia).toContainText(/Devolución de mercancía/i);
		// La nota repite con qué CABYS se vendió (T-731).
		await expect(hoja.locator('[data-cabys]').first()).toContainText('2316100000100');
		// Una nota no cobra: nada de efectivo recibido ni vuelto.
		await expect(hoja).not.toContainText('Efectivo recibido');
		// La NC en su serie, la 03, y referenciando la clave del tiquete (T-705).
		await expect(page.locator('[data-fiscal="sandbox"]')).toBeVisible();
		await expect(hoja.locator('[data-cabecera]')).toContainText('00100001030000000001');
		await expect(referencia).toContainText(/506\d{47}/);
		// La nota lleva su propio QR, con su clave y no la del tiquete.
		const claveDeLaNota = await page.locator('[data-clave]').getAttribute('data-clave');
		await expect(page.locator('[data-qr]')).toHaveAttribute('data-qr', claveDeLaNota!);

		// Y el historial la enlaza.
		await page.goto('/devoluciones');
		await expect(page.locator('a[data-nota="06"]').first()).toBeVisible();
	});

	test('anular una factura es una nota que la anula entera', async ({ page }) => {
		await crearCliente(page);
		await activarFacturacion(page);
		await llenarVenta(page);
		const recibido = await abrirCobro(page);
		await page.locator('#client-select').selectOption({ index: 1 });
		await recibido.fill('2000');
		const factura = await confirmarCobro(page);

		await clicHasta(page.getByRole('button', { name: /^Anular$/ }), () =>
			expect(page.locator('#annul-reason')).toBeVisible({ timeout: 1000 })
		);
		await page.locator('#annul-reason').fill('Cliente equivocado');
		await page.locator('button[type="submit"][form="annul-form"]').click();
		await expect(page).toHaveURL(/\/devoluciones\/\d+\?nueva=1/, { timeout: 15_000 });

		await expect(page.locator('[data-referencia]')).toContainText('Factura electrónica');
		await expect(page.locator('[data-referencia]')).toContainText(/Anula el comprobante/i);

		// Anulada, ya no se ofrece anular ni devolver.
		await page.goto(factura);
		await expect(page.getByRole('button', { name: /^Anular$/ })).toHaveCount(0);
		await expect(page.getByRole('link', { name: /Ver anulación/i })).toBeVisible();
	});

	test('la nota de débito por monto se cobra, se imprime y entra al arqueo (T-726)', async ({
		page
	}) => {
		await activarFacturacion(page);
		await llenarVenta(page);
		const recibido = await abrirCobro(page);
		await recibido.fill('2000');
		const factura = await confirmarCobro(page);

		// El dueño es administrador: ve el botón.
		await clicHasta(page.locator('button[data-nota-monto]'), () =>
			expect(page.locator('#note-form')).toBeVisible({ timeout: 1000 })
		);
		await page.locator('#note-form input[name="document_type"][value="02"]').check();
		await page.locator('#note-form input[name^="monto_"]').first().fill('113');
		await page.locator('#note-payment').selectOption('Efectivo');
		await page.locator('#note-reason').fill('Se cobró de menos');
		await page.locator('button[type="submit"][form="note-form"]').click();
		await expect(page).toHaveURL(/\/notas\/\d+\?nueva=1/, { timeout: 15_000 });

		const hoja = page.locator('.print-sheet');
		await expect(hoja).toContainText('Nota de débito electrónica');
		await expect(page.locator('[data-referencia]')).toContainText('Tiquete electrónico');
		await expect(page.locator('[data-referencia]')).toContainText(/Corrige monto/i);
		// La línea repite con qué CABYS se vendió.
		await expect(hoja.locator('[data-cabys]').first()).toContainText('2316100000100');

		// La plata entró a la gaveta del turno.
		await page.goto('/caja');
		await expect(page.locator('[data-arqueo-nd]')).toContainText('113,00');

		// La factura la enlaza, y con una nota encima ya no se anula.
		await page.goto(factura);
		await expect(page.locator('a[data-nota-enlace]')).toBeVisible();
		await expect(page.getByRole('button', { name: /^Anular$/ })).toHaveCount(0);
	});

	test('una nota de crédito por monto no pasa de lo cobrado (T-726)', async ({ page }) => {
		await activarFacturacion(page);
		await llenarVenta(page);
		const recibido = await abrirCobro(page);
		await recibido.fill('2000');
		await confirmarCobro(page);

		await clicHasta(page.locator('button[data-nota-monto]'), () =>
			expect(page.locator('#note-form')).toBeVisible({ timeout: 1000 })
		);
		// La NC viene elegida: es la que no se apaga. El arroz se cobró ₡1 130.
		await page.locator('#note-form input[name^="monto_"]').first().fill('5000');
		await page.locator('#note-reason').fill('Descuento que no se aplicó');
		await page.locator('button[type="submit"][form="note-form"]').click();
		await expect(page.getByText(/le quedan .*1130/i)).toBeVisible();
		await expect(page).not.toHaveURL(/\/notas\//);
	});
});

test.describe('el emisor: su ubicación (T-722) y su cédula (RN-45, T-621)', () => {
	let ficha: string;

	test.beforeEach(async ({ page }) => {
		const dueno = await supermercadoNuevo(page);
		ficha = dueno.ficha;
		await entrar(page, dueno);
	});

	test('la factura electrónica no se enciende sin correo ni ubicación', async ({ page }) => {
		await pestana(page, /Factura electrónica/i, 'input[name="electronica_activa"]');
		await page.locator('input[name="electronica_activa"]').check();
		await page.locator('button[type="submit"][form="config-form"]').click();

		// Se dice en el campo, en la pestaña Negocio, que es donde se arregla.
		await clicHasta(page.getByRole('button', { name: /^Negocio$/ }).first(), () =>
			expect(page.locator('#ubicacion-provincia')).toBeVisible({ timeout: 1000 })
		);
		await expect(page.locator('[data-ubicacion-emisor]')).toContainText(/Complete «Provincia»/);
		await expect(page.getByText(/el correo del negocio/i)).toBeVisible();
	});

	test('elegir otra provincia vacía el cantón y el distrito', async ({ page }) => {
		await pestana(page, /^Negocio$/, '#ubicacion-provincia');
		await llenarUbicacion(page);
		await page.locator('#ubicacion-provincia').selectOption('7');
		await expect(page.locator('#ubicacion-canton')).toHaveValue('');
		await expect(page.locator('#ubicacion-distrito')).toHaveValue('');
		await expect(page.locator('#ubicacion-distrito')).toBeDisabled();
		// Limón tiene seis cantones.
		await expect(page.locator('#ubicacion-canton option')).toHaveCount(7);
	});

	test('la cédula del emisor la fija soporte y el negocio la ve sin poder editarla', async ({
		page
	}) => {
		// El negocio la ve, y no hay campo para escribirla.
		await page.goto('/configuracion');
		await expect(page.locator('[data-cedula-emisor]')).toContainText('DIMEX');
		await expect(page.locator('input[name="negocio_identificacion"]')).toHaveCount(0);
		await salir(page);

		// Soporte la corrige: con guiones, y queda limpia.
		await autenticar(page, SOPORTE);
		await expect(page).toHaveURL(/\/admin$/);
		await page.goto(ficha);
		await expect(page.locator('[data-emisor-form]')).toBeVisible();
		await page.locator('[data-emisor-form] input[name="identificacion"]').fill('3-101-999999');
		await page.locator('[data-emisor-form] button').click();
		await expect(page.getByText('Cédula del emisor guardada.')).toBeVisible();
		await expect(page.locator('[data-emisor-form] input[name="identificacion"]')).toHaveValue(
			'3101999999'
		);
	});
});


// ------------------------------------------------- el recorrido ante Hacienda (F7)
//
// El simulado avanza cada comprobante por el tiempo transcurrido desde que se
// numeró —firmado a los 2 s, enviado a los 4, aceptado a los 7— con el
// certificado y las credenciales del ambiente cargados; sin ellos se detiene y
// dice qué falta. Es la misma máquina de estados del backend
// (`domain/fe_transmission.py`), así que lo que estas pruebas comprueban es que
// las pantallas la cuenten bien: la columna, el expediente, los dos XML, lo
// detenido y el reintento.

/** Un `.p12` de mentira que el simulado sabe leer (ver factura-electronica.spec). */
function p12DePrueba(): Buffer {
	return Buffer.concat([Buffer.from([0x30]), Buffer.from('|SUJETO=SUPER DE PRUEBA S.A.|DIAS=365', 'utf-8')]);
}

/** Deja el ambiente de pruebas listo para emitir: certificado y usuario de ATV. */
async function credencialesDePruebas(page: Page) {
	await pestana(page, /Factura electrónica/i, '[data-ambiente="sandbox"]');
	const card = page.locator('[data-ambiente="sandbox"]');
	await card
		.locator('input[type="file"]')
		.setInputFiles({ name: 'llave.p12', mimeType: 'application/x-pkcs12', buffer: p12DePrueba() });
	await card.locator('input[name="pin"]').fill('1234');
	await card.getByRole('button', { name: /Subir certificado/i }).click();
	await expect(card).toContainText(/SUPER DE PRUEBA/i);
	await card.locator('input[name="atv_usuario"]').fill('cpj-3101000000@pruebas.cr');
	await card.locator('input[name="atv_clave"]').fill('buena-clave');
	await card.getByRole('button', { name: /Guardar credenciales/i }).click();
	await expect(card.locator('input[name="atv_usuario"]')).toHaveValue('cpj-3101000000@pruebas.cr');
}

/** Recarga hasta que el expediente diga ese estado: la cola del simulado va por reloj. */
async function esperarEstado(page: Page, factura: string, estado: string) {
	await expect(async () => {
		await page.goto(factura);
		await expect(page.locator('[data-expediente]')).toHaveAttribute('data-estado', estado, { timeout: 1500 });
	}).toPass({ timeout: 30_000 });
}

test.describe('el recorrido ante Hacienda (F7, RN-39 a RN-42)', () => {
	test.beforeEach(async ({ page }) => {
		const dueno = await supermercadoNuevo(page);
		await entrar(page, dueno);
		await crearProducto(page);
		await activarFacturacion(page);
	});

	test('un tiquete llega a aceptado y sus dos XML se bajan, y con los tres aceptados se pasa a producción', async ({ page }) => {
		test.setTimeout(240_000);
		await credencialesDePruebas(page);
		await llenarVenta(page);
		await abrirCobro(page);
		const factura = await confirmarCobro(page);

		// Recién cobrado: el expediente existe y está en camino.
		await expect(page.locator('[data-expediente]')).toBeVisible();
		await esperarEstado(page, factura, 'accepted');
		await expect(page.locator('[data-estado-hacienda]')).toHaveText(/Aceptado/);
		await expect(page.locator('[data-eventos]')).toContainText(/Firmado/);
		await expect(page.locator('[data-eventos]')).toContainText(/Enviado a Hacienda/);
		await expect(page.locator('[data-eventos]')).toContainText(/Hacienda lo aceptó/);

		// Los dos XML del expediente (RF-34): el firmado y la respuesta de Hacienda.
		await expect(page.locator('[data-xml-firmado]')).toBeVisible();
		const xml = await page.request.get(`${factura}/xml`);
		expect(xml.status()).toBe(200);
		const textoXml = await xml.text();
		expect(textoXml).toContain('<ds:Signature');
		expect(xml.headers()['content-disposition']).toContain('.xml');
		const respuesta = await page.request.get(`${factura}/respuesta`);
		expect(respuesta.status()).toBe(200);
		expect(await respuesta.text()).toContain('<Mensaje>1</Mensaje>');

		// Y la lista lo dice en su columna (RF-33).
		await page.goto('/facturas');
		await expect(page.locator('[data-hacienda="accepted"]').first()).toBeVisible();

		// ---------------------------------- la puerta de producción (T-713, RN-46)
		//
		// Falta la factura y la nota de crédito. La factura, con cliente; la nota,
		// devolviendo el tiquete. Las dos recorren la cola igual.
		await crearCliente(page);
		await llenarVenta(page);
		const recibido = await abrirCobro(page);
		await page.locator('#client-select').selectOption({ index: 1 });
		await recibido.fill('2000');
		const facturaConCliente = await confirmarCobro(page);
		await devolverUna(page, factura);
		await expect(page).toHaveURL(/\/devoluciones\/\d+\?nueva=1/, { timeout: 15_000 });
		const notaDeCredito = new URL(page.url()).pathname;
		await esperarEstado(page, facturaConCliente, 'accepted');
		await esperarEstado(page, notaDeCredito, 'accepted');

		// Con los tres aceptados la puerta se abre y se pasa, confirmando (RN-35).
		await pestana(page, /Factura electrónica/i, '[data-ambiente="sandbox"]');
		await expect(page.locator('[data-puerta-produccion="abierta"]')).toBeVisible();
		await clicHasta(page.getByRole('button', { name: /Pasar a producción/i }), async () => {
			await expect(page.getByRole('dialog')).toBeVisible();
		});
		await page.getByRole('button', { name: /Sí, pasar a producción/i }).click();
		await expect(page.getByText(/Ambiente en uso: producción/i)).toBeVisible();
		// «Lo que se emita…», no el aviso del certificado, que también dice «efecto fiscal».
		await expect(page.getByText(/Lo que se emita tiene efecto fiscal/i)).toBeVisible();

		// La puerta lateral (T-611): guardar la pantalla entera no mueve el ambiente.
		const guardado = page.waitForResponse(
			(r) => r.url().includes('/configuracion') && r.request().method() === 'POST'
		);
		await page.getByRole('button', { name: /Guardar cambios/i }).click();
		expect((await guardado).ok(), 'no se pudo guardar la configuración').toBe(true);
		await page.waitForLoadState('networkidle');
		await pestana(page, /Factura electrónica/i, '[data-ambiente="sandbox"]');
		await expect(page.getByText(/Ambiente en uso: producción/i)).toBeVisible();

		// Volver a pruebas no pide confirmación (RN-35): un clic.
		await page.getByRole('button', { name: /Volver a pruebas/i }).click();
		await expect(page.getByText(/Ambiente en uso: pruebas/i)).toBeVisible();

		// Y la bitácora tiene el antes y el después.
		await salir(page);
		await autenticar(page, SOPORTE);
		await expect(page).toHaveURL(/\/admin$/);
		await page.goto('/admin/bitacora?accion=fe_ambiente');
		await expect(page.getByText('sandbox → production').first()).toBeVisible();
	});

	test('sin certificado se detiene, se ve en la lista y se reintenta a mano', async ({ page }) => {
		await llenarVenta(page);
		await abrirCobro(page);
		const factura = await confirmarCobro(page);

		// Se detiene en la firma y dice qué falta (RN-41, RF-35).
		await esperarEstado(page, factura, 'stopped');
		await expect(page.locator('[data-expediente]')).toContainText(/Falta el certificado/);
		await expect(page.locator('[data-xml-firmado]')).toHaveCount(0);

		await page.goto('/facturas');
		await expect(page.locator('[data-detenidos]')).toBeVisible();
		await expect(page.locator('[data-detenidos]')).toContainText(/Falta el certificado/);
		await expect(page.locator('[data-hacienda="stopped"]').first()).toBeVisible();

		// Se arregla la causa y se reintenta (RF-36): vuelve a la cola y llega.
		await credencialesDePruebas(page);
		await page.goto(factura);
		// Se mira el resultado y no el aviso: antes de hidratar el envío es nativo
		// y el aviso no sale, pero el reintento sí entra y el botón desaparece.
		await expect(async () => {
			const boton = page.locator('[data-reintentar]');
			if (await boton.count()) await boton.click();
			await expect(page.locator('[data-expediente]')).not.toHaveAttribute('data-estado', 'stopped', {
				timeout: 1500
			});
		}).toPass({ timeout: 15_000 });
		await esperarEstado(page, factura, 'accepted');
		await expect(page.locator('[data-eventos]')).toContainText(/Reintentado a mano/);
	});
});
