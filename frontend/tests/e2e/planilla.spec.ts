import { expect, test, type Locator, type Page } from '@playwright/test';
import { autenticar, clicHasta, entrar, salir } from './sesion';

/**
 * F12 de punta a punta (T-1215).
 *
 * Va contra **una compañía que esta prueba da de alta**: pagar una planilla
 * deja asientos y vacaciones acumuladas, y eso se lo cambiaría a todas las
 * demás pruebas. El recorrido es el de la persona que lleva la planilla en su
 * primer mes con VentaSys: configura, da de alta a dos personas —una quincenal
 * y una mensual—, registra una incapacidad que cruza la quincena y un préstamo
 * recurrente, paga, reimprime la boleta y comprueba que no cambió, paga la
 * siguiente y ve bajar el saldo del préstamo, corre el aguinaldo, da de baja
 * con su liquidación y arma los archivos del mes.
 *
 * Lo que no pasa por acá: la tasa nueva con vigencia futura, que carga soporte
 * por el API (`PUT /support/payroll/rates`) y se prueba contra el stack real en
 * `backend/tests/test_planilla.py`.
 */

const SOPORTE = { email: 'soporte@ventasys.cr', password: 'soporte123' };

function marca(): string {
	return `${Date.now()}`.slice(-8);
}

async function companiaConPlanilla(page: Page) {
	const correo = `planilla${marca()}@ventasys.cr`;
	await autenticar(page, SOPORTE);
	await expect(page).toHaveURL(/\/admin$/);
	await page.goto('/admin/companias/nueva');
	await page.locator('input[name="nombre"]').fill(`Planillera ${marca()}`);
	await page.locator('input[name="identificacion"]').fill(`310${marca()}`);
	await page.locator('input[name="email"]').fill(correo);
	await page.locator('input[name="password"]').fill('dueno123');
	await page.locator('input[name="name"]').fill('Rosa');
	await page.locator('input[name="lastName"]').fill('Planillera');
	await page.locator('#plan_id').selectOption({ label: 'Comercio' });
	await page.getByRole('button', { name: /Dar de alta/i }).click();
	await expect(page).toHaveURL(/\/admin\/companias\/\d+\?creada=1/);
	await salir(page);
	return { email: correo, password: 'dueno123' };
}

/** Activa los libros desde enero de 2026, con un saldo inicial que cuadra. */
async function activarContabilidad(page: Page) {
	await page.goto('/contabilidad');
	const primerDebito = page.locator('input[name="opening_debit"]').first();
	await expect(async () => {
		await primerDebito.fill('100000');
		await expect(page.locator('tfoot')).toContainText('100.000,00', { timeout: 500 });
	}).toPass({ timeout: 15_000 });
	// Después de hidratar, no antes: lo que se teclea antes se pierde al hidratar.
	await page.locator('input[name="start_date"]').fill('2026-01-01');
	await page.locator('select[name="opening_code"]').first().selectOption('1.1.01');
	await page.locator('select[name="opening_code"]').nth(1).selectOption('3.1.01');
	await page.locator('input[name="opening_credit"]').nth(1).fill('100000');
	// La fecha tiene que sobrevivir a los saldos (defecto corregido el 2026-10-02).
	await expect(page.locator('input[name="start_date"]')).toHaveValue('2026-01-01');
	await page.getByRole('button', { name: /activar contabilidad/i }).click();
	await expect(page.getByRole('link', { name: /^Asientos$/ })).toBeVisible();
}

/** Abre un modal con reintento y espera a que su formulario esté. */
async function abrir(page: Page, boton: RegExp, formulario: string) {
	await clicHasta(page.getByRole('button', { name: boton }).first(), () =>
		expect(page.locator(`${formulario}`)).toBeVisible({ timeout: 1000 })
	);
}

async function guardar(page: Page, formulario: string) {
	await page.locator(`button[type="submit"][form="${formulario.slice(1)}"]`).click();
	await expect(page.locator(formulario)).toBeHidden();
}

/**
 * Da de alta a una persona desde la lista y vuelve con el enlace a su ficha.
 *
 * Con `contrato`, se lo asigna en la misma ficha (RF-55); sin él, apaga la
 * casilla y el contrato se da después desde el detalle. El recorrido usa los
 * dos caminos, uno por persona.
 */
async function altaDeEmpleado(
	page: Page,
	datos: { cedula: string; nombre: string; apellido: string; nacimiento: string; ingreso: string },
	contrato?: { jornada: string; salario: string }
) {
	await page.goto('/planilla/empleados');
	await abrir(page, /Nuevo empleado/i, '#form-empleado');
	await page.locator('#form-empleado input[name="identification"]').fill(datos.cedula);
	await page.locator('#form-empleado input[name="first_name"]').fill(datos.nombre);
	await page.locator('#form-empleado input[name="last_name_1"]').fill(datos.apellido);
	await page.locator('#form-empleado input[name="birth_date"]').fill(datos.nacimiento);
	await page.locator('#form-empleado input[name="hired_on"]').fill(datos.ingreso);
	const casilla = page.locator('#form-empleado input[name="con_contrato"]');
	if (contrato) {
		await expect(casilla).toBeChecked();
		await elegir(page.locator('#form-empleado select[name="schedule_id"]'), contrato.jornada);
		await page.locator('#form-empleado input[name="period_salary"]').fill(contrato.salario);
	} else {
		await casilla.uncheck();
		await expect(page.locator('#form-empleado input[name="period_salary"]')).toHaveCount(0);
	}
	await guardar(page, '#form-empleado');
	const enlace = page.getByRole('link', { name: `${datos.nombre} ${datos.apellido}` });
	await expect(enlace).toBeVisible();
	return enlace;
}

/** Elige la opción cuyo texto contiene `texto`: las jornadas se rotulan «nombre · periodicidad». */
async function elegir(select: Locator, texto: string) {
	const valor = await select.locator('option', { hasText: texto }).first().getAttribute('value');
	await select.selectOption(valor ?? '');
}

async function contratar(page: Page, jornada: string, salario: string, desde: string) {
	await abrir(page, /Nuevo contrato/i, '#form-contrato');
	await elegir(page.locator('#form-contrato select[name="schedule_id"]'), jornada);
	await page.locator('#form-contrato input[name="valid_from"]').fill(desde);
	await page.locator('#form-contrato input[name="period_salary"]').fill(salario);
	await guardar(page, '#form-contrato');
	await expect(page.locator('[data-salario]')).toBeVisible();
}

/** Crea una corrida regular y la deja pagada; devuelve la URL de su detalle. */
async function pagarCorrida(page: Page, jornada: string, corte: string) {
	await page.goto('/planilla/corridas');
	await abrir(page, /^Nueva corrida$/i, '#form-corrida');
	await elegir(page.locator('#form-corrida select[name="schedule_id"]'), jornada);
	await page.locator('#form-corrida input[name="cut_date"]').fill(corte);
	await page.locator('button[type="submit"][form="form-corrida"]').click();
	await expect(page).toHaveURL(/\/planilla\/corridas\/\d+$/);
	await calcularAprobarPagar(page);
	return page.url();
}

async function calcularAprobarPagar(page: Page) {
	await page.getByRole('button', { name: /^Calcular$/ }).click();
	await expect(page.locator('[data-lineas] [data-neto]').first()).toBeVisible();
	await page.getByRole('button', { name: /^Aprobar$/ }).click();
	await expect(page.locator('[data-estado-corrida]')).toHaveText('Aprobada');
	await page.getByRole('button', { name: /^Pagar$/ }).click();
	await expect(page.locator('[data-estado-corrida]')).toHaveText('Pagada');
}

/**
 * Elige el tipo de acción y espera a ver un campo que solo ese tipo tiene. Con
 * reintento: antes de hidratar, cambiar el `select` no cambia el formulario.
 */
async function elegirTipo(page: Page, tipo: string, campo: string) {
	await expect(async () => {
		await page.locator('#accion-tipo').selectOption(tipo);
		await expect(page.locator(`[data-form-accion] input[name="${campo}"]`)).toBeVisible({ timeout: 500 });
	}).toPass({ timeout: 10_000 });
}

/** Despliega los rubros de la primera línea hasta ver el texto. El botón es de estado y antes de hidratar no hace nada. */
async function verRubros(page: Page, texto: string | RegExp) {
	await clicHasta(page.getByRole('button', { name: /Rubros/ }).first(), () =>
		expect(page.locator('[data-lineas]')).toContainText(texto, { timeout: 1000 })
	);
}

test.describe('F12 de punta a punta', () => {
	test('de la configuración a los archivos del mes', async ({ page }) => {
		test.setTimeout(240_000);
		const duena = await companiaConPlanilla(page);
		await entrar(page, duena);
		await activarContabilidad(page);

		// ------------------------------------------------- 1. la configuración
		await page.goto('/planilla');
		await expect(page.locator('[data-resumen-faltantes]')).toContainText(/número patronal/i);

		await page.goto('/planilla/configuracion');
		// Con reintento, y el campo se vuelve a llenar en cada intento: antes de
		// hidratar el envío es nativo y el aviso no sale, y al hidratar Svelte
		// repone el valor cargado. Guardar dos veces lo mismo es inocuo.
		await expect(async () => {
			await page.locator('input[name="employer_number"]').fill('2-03101000000-001-001');
			await page.locator('[data-seccion-patronal] button[type="submit"]').click();
			await expect(page.getByText(/configuración guardada/i).first()).toBeVisible({ timeout: 1500 });
		}).toPass({ timeout: 10_000 });

		await abrir(page, /Nueva póliza/i, '#form-poliza');
		await page.locator('#form-poliza input[name="number"]').fill('RT-1');
		await page.locator('#form-poliza input[name="rt_rate"]').fill('1.46');
		await guardar(page, '#form-poliza');
		await expect(page.locator('[data-seccion-polizas]')).toContainText('RT-1');

		await abrir(page, /Nueva jornada/i, '#form-jornada');
		await page.locator('#form-jornada input[name="name"]').fill('Quincenal');
		await page.locator('#form-jornada select[name="frequency"]').selectOption('semimonthly');
		await page.locator('#form-jornada input[name="first_cut_day"]').fill('15');
		await guardar(page, '#form-jornada');
		await abrir(page, /Nueva jornada/i, '#form-jornada');
		await page.locator('#form-jornada input[name="name"]').fill('Mensual');
		await page.locator('#form-jornada select[name="frequency"]').selectOption('monthly');
		await guardar(page, '#form-jornada');
		await expect(page.locator('[data-seccion-jornadas]')).toContainText('Mensual');

		await abrir(page, /Nuevo puesto/i, '#form-puesto');
		await page.locator('#form-puesto input[name="name"]').fill('Caja');
		await page.locator('#form-puesto input[name="ccss_code"]').fill('4211');
		await page.locator('#form-puesto input[name="ins_code"]').fill('52');
		await guardar(page, '#form-puesto');
		await expect(page.locator('[data-seccion-puestos]')).toContainText('4211');

		// --------------------------------------- 2. dos personas, dos jornadas
		const elena = await altaDeEmpleado(page, { cedula: '101230456', nombre: 'Elena', apellido: 'Rojas', nacimiento: '1990-05-20', ingreso: '2025-06-01' });
		await elena.click();
		await expect(page).toHaveURL(/\/planilla\/empleados\/\d+$/);
		const fichaElena = page.url();
		await contratar(page, 'Quincenal', '300000', '2025-06-01');

		// Mario entra con su contrato en el alta (RF-55): la lista ya lo muestra
		// con puesto y jornada, y su ficha con el salario desde el ingreso.
		const mario = await altaDeEmpleado(
			page,
			{ cedula: '201230456', nombre: 'Mario', apellido: 'Castro', nacimiento: '1988-07-01', ingreso: '2024-09-01' },
			{ jornada: 'Mensual', salario: '540000' }
		);
		await expect(page.locator('tr', { has: mario })).toContainText('Caja · Mensual');
		await mario.click();
		await expect(page).toHaveURL(/\/planilla\/empleados\/\d+$/);
		const fichaMario = page.url();
		await expect(page.locator('[data-salario]')).toBeVisible();

		// ------------------- 3. una incapacidad que cruza la quincena y un préstamo
		const idElena = fichaElena.split('/').at(-1);
		await page.goto(`/planilla/acciones?empleado=${idElena}`);
		await elegirTipo(page, 'sick_leave_ccss', 'ends_on');
		await page.locator('[data-form-accion] input[name="starts_on"]').fill('2026-01-10');
		await page.locator('[data-form-accion] input[name="ends_on"]').fill('2026-01-20');
		await page.locator('[data-form-accion] button[type="submit"]').click();
		await expect(page.locator('[data-historial-acciones]')).toContainText(/Incapacidad de la CCSS/);

		await elegirTipo(page, 'deduction', 'total_amount');
		await page.locator('[data-form-accion] input[name="starts_on"]').fill('2026-01-01');
		await page.locator('[data-form-accion] input[name="amount"]').fill('25000');
		await page.locator('[data-form-accion] input[name="total_amount"]').fill('300000');
		await page.locator('[data-form-accion] button[type="submit"]').click();
		await expect(page.locator('[data-historial-acciones]')).toContainText('300.000,00');

		// --------------------------------------- 4. la primera quincena, pagada
		const primera = await pagarCorrida(page, 'Quincenal', '2026-01-15');
		// Con contabilidad activa, el pago dejó su asiento (RN-75).
		await expect(page.getByRole('link', { name: /^Asiento \d+$/ })).toBeVisible();
		// La incapacidad entró con su tramo de la quincena: seis días del 10 al 15.
		await verRubros(page, '10/01/2026 a 15/01/2026');

		// ---------------------------------------- 5. la boleta, dos veces igual
		await page.getByRole('link', { name: /Boleta/ }).first().click();
		await expect(page.locator('[data-boleta-titulo]')).toHaveText('Boleta de pago');
		const neto = await page.locator('[data-boleta-neto]').textContent();
		expect(neto).toMatch(/\d/);
		await page.reload();
		await expect(page.locator('[data-boleta-neto]')).toHaveText(neto ?? '');

		// --------------------- 6. la siguiente: distinta, y el préstamo bajando
		await pagarCorrida(page, 'Quincenal', '2026-01-31');
		await verRubros(page, '16/01/2026 a 20/01/2026');
		await page.goto(fichaElena);
		// Dos cuotas de 25 000 sobre 300 000.
		await expect(page.locator('[data-seccion-historial]')).toContainText('250.000,00');
		// Y las dos quincenas acumularon vacaciones (RN-70).
		await expect(page.locator('[data-saldo-vacaciones]')).not.toContainText('Saldo: 0 ');

		// ------------------------------------------ 7. la mensual y el aguinaldo
		await pagarCorrida(page, 'Mensual', '2026-01-31');
		await page.goto('/planilla/corridas');
		await abrir(page, /Corrida de aguinaldo/i, '#form-aguinaldo');
		await page.locator('#form-aguinaldo input[name="year"]').fill('2026');
		await page.locator('button[type="submit"][form="form-aguinaldo"]').click();
		await expect(page).toHaveURL(/\/planilla\/corridas\/\d+$/);
		await expect(page.locator('[data-titulo-corrida]')).toContainText('Aguinaldo');
		await page.getByRole('button', { name: /^Calcular$/ }).click();
		await expect(page.locator('[data-lineas] [data-neto]')).toHaveCount(2);

		// --------------------------------------------- 8. la baja y su liquidación
		await page.goto(fichaMario);
		await abrir(page, /Dar de baja/i, '#form-baja');
		await page.locator('#form-baja input[name="terminated_on"]').fill('2026-02-10');
		await page.locator('#form-baja select[name="cause"]').selectOption('dismissal_without_cause');
		await page.locator('button[type="submit"][form="form-baja"]').click();
		await expect(page).toHaveURL(/\/planilla\/corridas\/\d+$/);
		await expect(page.locator('[data-titulo-corrida]')).toContainText('Liquidación');
		// Nace con la línea vacía de la persona, así que el botón ya dice «Recalcular».
		await page.getByRole('button', { name: /^(Re)?calcular$/ }).click();
		await expect(page.locator('[data-lineas] [data-neto]').first()).toBeVisible();
		await verRubros(page, 'Cesantía');

		// ------------------------------------------------ 9. los archivos del mes
		await page.goto('/planilla/archivos?year=2026&month=1');
		await expect(page.locator('[data-ccss] tbody tr')).toHaveCount(2);
		await expect(page.locator('[data-ccss]')).toContainText('Incapacidad SEM');
		await expect(page.locator('[data-renta] tbody tr')).toHaveCount(2);
		const enlaceIns = page.locator('[data-ins-poliza]').first();
		const archivo = await page.request.get((await enlaceIns.getAttribute('href')) ?? '');
		expect(archivo.status()).toBe(200);
		const texto = await archivo.text();
		expect(texto).toContain('V08D');
		expect(texto.split('\r\n').filter(Boolean)).toHaveLength(5);
		expect(archivo.headers()['content-disposition']).toContain('PL0000001M202601-V08D');

		const primeraCorrida = await page.request.get(primera);
		expect(primeraCorrida.status()).toBe(200);
	});
});
