import { expect, test, type Page } from '@playwright/test';

import { autenticar, entrar, salir } from './sesion';

/**
 * La numeración que viene de otro sistema (T-616, RF-32, RN-36 a RN-38).
 *
 * Un negocio que ya facturaba con otro sistema dice el último consecutivo que
 * emitió de cada comprobante, y el siguiente sale con uno más. Solo sube, y
 * una serie con la que el sistema ya emitió no se toca; esa mitad, que pide una
 * emisión de verdad, está en `backend/tests/test_series_fe.py`.
 *
 * Va contra una compañía que la prueba da de alta: moverle la numeración a la
 * del demo le cambiaría los consecutivos a las demás pruebas.
 */

const SOPORTE = { email: 'soporte@ventasys.cr', password: 'soporte123' };

function marca(): string {
	return `${Date.now()}`.slice(-8);
}

async function companiaPropia(page: Page) {
	const sufijo = marca();
	const correo = `series.${sufijo}@pruebas.ventasys.cr`;
	await autenticar(page, SOPORTE);
	await expect(page).toHaveURL(/\/admin$/);
	await page.goto('/admin/companias/nueva');
	await page.locator('input[name="nombre"]').fill(`Series ${sufijo}`);
	await page.locator('input[name="identificacion"]').fill('3101555444');
	await page.locator('input[name="email"]').fill(correo);
	await page.locator('input[name="password"]').fill('dueno123');
	await page.locator('input[name="name"]').fill('Dueña');
	await page.locator('input[name="lastName"]').fill('Series');
	await page.locator('#plan_id').selectOption({ label: 'Comercio' });
	await page.getByRole('button', { name: /Dar de alta/i }).click();
	await expect(page).toHaveURL(/\/admin\/companias\/\d+\?creada=1/);
	await salir(page);
	return { email: correo, password: 'dueno123' };
}

test('el último consecutivo de otro sistema se indica y no baja', async ({ page }) => {
	const duena = await companiaPropia(page);
	await entrar(page, duena);
	await page.goto('/configuracion?seccion=electronica');

	const factura = page.locator('[data-series] tr[data-serie="01"]');
	const campo = factura.locator('input[name="last_number"]');
	await expect(campo).toHaveValue('0');

	// Con reintento: antes de hidratar, el clic manda el formulario sin
	// JavaScript, la página se recarga en la dirección de la acción y pierde la
	// pestaña. Guarda igual; lo que no hay es aviso. Volver a la pestaña y
	// guardar el mismo número otra vez es inofensivo.
	await expect(async () => {
		await page.goto('/configuracion?seccion=electronica');
		await campo.fill('500209');
		await factura.getByRole('button', { name: /Guardar/i }).click();
		await expect(page.getByText(/Numeración guardada/i)).toBeVisible({ timeout: 2000 });
	}).toPass({ timeout: 30_000 });
	await page.reload();
	await expect(campo).toHaveValue('500209');

	// Bajarla volvería a emitir números usados: el servidor lo rechaza y lo dice.
	await campo.fill('500100');
	await factura.getByRole('button', { name: /Guardar/i }).click();
	// Sale en el aviso y en el error del formulario: con uno alcanza.
	await expect(page.getByText(/no puede bajar a 500100/i).first()).toBeVisible();
	// `goto` y no `reload`: si ese envío salió sin JavaScript, recargar lo repite.
	await page.goto('/configuracion?seccion=electronica');
	await expect(campo).toHaveValue('500209');
});
