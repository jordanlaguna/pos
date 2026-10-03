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

	test('una distribuidora que apaga el tiquete no cobra sin cliente', async ({ page }) => {
		await crearCliente(page);
		await activarFacturacion(page);

		// La NC no se apaga y la ND todavía no tiene flujo: se ven, no se mueven.
		await pestana(page, /Factura electrónica/i, '[data-comprobantes]');
		await expect(casilla(page, '03')).toBeDisabled();
		await expect(casilla(page, '03')).toBeChecked();
		await expect(casilla(page, '02')).toBeDisabled();
		await expect(casilla(page, '09')).toBeDisabled();

		await comprobantes(page, { '04': false });
		// Queda la factura sola, y es la última de venta: ya no se puede apagar. Y
		// guardar no apagó la NC ni la ND, que estaban bloqueadas.
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
