import { expect, test, type Page } from '@playwright/test';
import { autenticar, clicHasta, entrar, salir } from './sesion';

/**
 * Las credenciales de Hacienda, de punta a punta (F6, T-611, T-612, T-615).
 *
 * Lo que solo se puede ver acá es el recorrido completo: subir el certificado,
 * guardar las credenciales, probar la conexión con sus **tres** desenlaces y
 * pasar a producción con su confirmación. Las reglas están probadas contra el
 * stack real en `backend/tests/` —el orden entre Vault y la base, la traducción
 * de cada respuesta del IdP— y acá se comprueba que las dos mitades hablen.
 *
 * **La compañía es propia y se da de alta al empezar.** Es la lección de T-310
 * y de T-409: el simulado guarda su estado en `.data/mock-db.json`, así que una
 * prueba que le pone certificado al demo —o peor, que lo pasa a producción— se
 * lo cambia a las otras cincuenta y seis. La salida no es limpiar mejor, que una
 * prueba que falla a mitad no limpia nada, sino no tocar lo que otros usan.
 */

const SOPORTE = { email: 'soporte@ventasys.cr', password: 'soporte123' };

/** Un correo distinto en cada corrida: el simulado sobrevive entre ellas. */
function marca(): string {
	return `${Date.now()}`.slice(-8);
}

/**
 * Un `.p12` de mentira que el simulado sabe leer.
 *
 * El primer byte es `0x30` porque es lo único que el backend de verdad deduce
 * mirando los bytes: en DER, un PKCS#12 siempre empieza por una SEQUENCE. El
 * resto son las instrucciones que el simulado interpreta —a nombre de quién y
 * cuántos días le quedan— para poder pintar los estados sin generar
 * criptografía real en el navegador.
 */
function p12(sujeto: string, dias = 365): Buffer {
	return Buffer.concat([
		Buffer.from([0x30]),
		Buffer.from(`|SUJETO=${sujeto}|DIAS=${dias}`, 'utf-8')
	]);
}

/** Da de alta una compañía desde el panel y devuelve con qué entrar. */
async function companiaPropia(page: Page, quien: string) {
	const sufijo = marca();
	const correo = `fe.${quien}.${sufijo}@pruebas.ventasys.cr`;
	const negocio = `Ferretería FE ${sufijo}`;

	await autenticar(page, SOPORTE);
	await expect(page).toHaveURL(/\/admin$/);

	await page.getByRole('link', { name: /Nueva compañía/i }).click();
	await page.locator('input[name="nombre"]').fill(negocio);
	await page.locator('input[name="identificacion"]').fill('3101777666');
	await page.locator('input[name="email"]').fill(correo);
	await page.locator('input[name="password"]').fill('dueno123');
	await page.locator('input[name="name"]').fill('Dueña');
	await page.locator('input[name="lastName"]').fill('DeFE');
	await page.locator('#plan_id').selectOption({ label: 'Comercio' });
	await page.getByRole('button', { name: /Dar de alta/i }).click();
	await expect(page).toHaveURL(/\/admin\/companias\/\d+\?creada=1/);

	await salir(page);
	return { email: correo, password: 'dueno123', negocio };
}

/** Entra con el administrador de la compañía y abre la pestaña de FE. */
async function abrirFacturaElectronica(page: Page, quien: { email: string; password: string }) {
	// `entrar` y no `autenticar`: el segundo no espera a que la sesión quede
	// hecha, así que el `goto` de la línea siguiente corría contra el login y
	// todo lo demás fallaba señalando la pestaña, que es donde no está el
	// problema. Su administradora pertenece a una sola compañía, así que no pasa
	// por la pantalla de selección.
	await entrar(page, quien);
	await page.goto('/configuracion');
	// La pestaña no funciona hasta que Svelte hidrata: el HTML ya está pintado,
	// así que Playwright ve un botón listo y lo usa demasiado pronto.
	await clicHasta(page.getByRole('button', { name: /Factura electrónica/i }), async () => {
		await expect(page.getByText(/Ambiente en uso/i)).toBeVisible();
	});
}

/** La tarjeta de un ambiente. Se localiza por el atributo, no por el rótulo. */
function tarjeta(page: Page, ambiente: 'sandbox' | 'production') {
	return page.locator(`[data-ambiente="${ambiente}"]`);
}

async function subirCertificado(
	page: Page,
	ambiente: 'sandbox' | 'production',
	archivo: Buffer,
	pin = '1234'
) {
	const card = tarjeta(page, ambiente);
	await card
		.locator('input[type="file"]')
		.setInputFiles({ name: 'llave.p12', mimeType: 'application/x-pkcs12', buffer: archivo });
	await card.locator('input[name="pin"]').fill(pin);
	await card.getByRole('button', { name: /Subir certificado/i }).click();
}

async function guardarAtv(page: Page, ambiente: 'sandbox' | 'production', clave: string) {
	const card = tarjeta(page, ambiente);
	await card.locator('input[name="atv_usuario"]').fill('cpf-01-1234-5678@pruebas.cr');
	await card.locator('input[name="atv_clave"]').fill(clave);
	await card.getByRole('button', { name: /Guardar credenciales/i }).click();
}

test.describe('el recorrido completo (T-619)', () => {
	test('de un ambiente vacío a uno listo para emitir', async ({ page }) => {
		const dueno = await companiaPropia(page, 'recorrido');
		await abrirFacturaElectronica(page, dueno);

		// 1. Nace sin nada, y los dos ambientes lo dicen.
		await expect(page.getByText(/Ambiente en uso: pruebas/i)).toBeVisible();
		for (const ambiente of ['sandbox', 'production'] as const) {
			await expect(tarjeta(page, ambiente).getByText(/Incompleto/)).toBeVisible();
			await expect(
				tarjeta(page, ambiente).getByText(/Todavía no hay certificado/i)
			).toBeVisible();
		}

		// 2. El certificado. El nombre sale del certificado, no del archivo.
		await subirCertificado(page, 'sandbox', p12('FERRETERÍA DE PRUEBA S.A.'));
		await expect(tarjeta(page, 'sandbox').getByText('FERRETERÍA DE PRUEBA S.A.')).toBeVisible();
		// Con certificado y sin credenciales todavía **no** está listo: firmar y
		// transmitir son dos cosas, y con una sola no se emite.
		await expect(tarjeta(page, 'sandbox').getByText(/Incompleto/)).toBeVisible();
		// Y no tocó el otro ambiente.
		await expect(
			tarjeta(page, 'production').getByText(/Todavía no hay certificado/i)
		).toBeVisible();

		// 3. Las credenciales. Quedan guardadas pero sin comprobar.
		await guardarAtv(page, 'sandbox', 'la-buena');
		await expect(tarjeta(page, 'sandbox').getByText(/sin comprobar/i)).toBeVisible();
		await expect(tarjeta(page, 'sandbox').getByText(/Listo para emitir/)).toBeVisible();

		// 4. Probar la conexión, que no emite nada.
		await tarjeta(page, 'sandbox')
			.getByRole('button', { name: /Probar la conexión/i })
			.click();
		await expect(tarjeta(page, 'sandbox').getByText(/Comprobadas el/i)).toBeVisible();
	});

	test('el usuario de ATV se ve y la contraseña no vuelve nunca', async ({ page }) => {
		// RN-16: el usuario es un identificador y sin verlo nadie puede comprobar
		// que escribió el que era. La contraseña no tiene por dónde volver.
		const dueno = await companiaPropia(page, 'secretos');
		await abrirFacturaElectronica(page, dueno);

		await guardarAtv(page, 'sandbox', 'la-secreta-de-verdad');

		const card = tarjeta(page, 'sandbox');
		await expect(card.locator('input[name="atv_usuario"]')).toHaveValue(
			'cpf-01-1234-5678@pruebas.cr'
		);
		// El campo de la contraseña vuelve vacío, y el valor no aparece en ninguna
		// parte del documento — ni en un atributo, ni en un dato embebido.
		await expect(card.locator('input[name="atv_clave"]')).toHaveValue('');
		expect(await page.content()).not.toContain('la-secreta-de-verdad');
	});

	test('el PIN tampoco sobrevive a la petición que lo trajo', async ({ page }) => {
		const dueno = await companiaPropia(page, 'pin');
		await abrirFacturaElectronica(page, dueno);

		await subirCertificado(page, 'sandbox', p12('CON PIN'), 'el-pin-secreto');
		await expect(tarjeta(page, 'sandbox').getByText('CON PIN')).toBeVisible();
		expect(await page.content()).not.toContain('el-pin-secreto');
	});
});

test.describe('los tres desenlaces de probar la conexión (RF-31)', () => {
	test('cuando Hacienda dice que no, lo dice claro', async ({ page }) => {
		const dueno = await companiaPropia(page, 'rechazo');
		await abrirFacturaElectronica(page, dueno);

		await guardarAtv(page, 'sandbox', 'mal-escrita');
		await tarjeta(page, 'sandbox')
			.getByRole('button', { name: /Probar la conexión/i })
			.click();

		// Sale dos veces a propósito —el aviso que se desvanece y la banda que se
		// queda— así que se pide la primera en vez de discutir cuál.
		await expect(page.getByText(/rechazó el usuario o la contraseña/i).first()).toBeVisible();
	});

	test('cuando no se pudo comprobar, NO culpa a las credenciales', async ({ page }) => {
		/*
		 * El desenlace que RF-31 separa a propósito, y la razón por la que esta
		 * prueba existe: quien lea «no sirven» va a rotar su contraseña en ATV, y
		 * hacerlo el día que Hacienda está en mantenimiento es trabajo perdido
		 * sobre una credencial buena.
		 */
		const dueno = await companiaPropia(page, 'caido');
		await abrirFacturaElectronica(page, dueno);

		await guardarAtv(page, 'sandbox', 'caido-hoy');
		await tarjeta(page, 'sandbox')
			.getByRole('button', { name: /Probar la conexión/i })
			.click();

		await expect(page.getByText(/no respondió/i).first()).toBeVisible();
		await expect(page.getByText(/pueden estar bien/i).first()).toBeVisible();
		// Y la marca de «comprobadas» que hubiera antes no se tira: no se aprendió
		// nada nuevo sobre las credenciales.
		await expect(page.getByText(/rechazó/i)).toHaveCount(0);
	});

	test('sin credenciales el botón no se puede usar', async ({ page }) => {
		const dueno = await companiaPropia(page, 'sincred');
		await abrirFacturaElectronica(page, dueno);

		await expect(
			tarjeta(page, 'sandbox').getByRole('button', { name: /Probar la conexión/i })
		).toBeDisabled();
	});
});

test.describe('pasar a producción (RN-35, RN-46)', () => {
	test('se confirma, avisa de la certificación y queda en bitácora', async ({ page }) => {
		const dueno = await companiaPropia(page, 'produccion');
		await abrirFacturaElectronica(page, dueno);

		await clicHasta(page.getByRole('button', { name: /Pasar a producción/i }), async () => {
			await expect(page.getByRole('dialog')).toBeVisible();
		});

		// RN-46: avisa de lo que Hacienda exige y **no lo impide**.
		await expect(page.getByText(/una factura, un tiquete y una nota de crédito/i)).toBeVisible();

		await page.getByRole('button', { name: /Sí, pasar a producción/i }).click();
		await expect(page.getByText(/Ambiente en uso: producción/i)).toBeVisible();
		await expect(page.getByText(/tiene efecto fiscal/i)).toBeVisible();

		// La bitácora, con el antes y el después: «cambió el ambiente» no sirve
		// para nada dentro de seis meses.
		await salir(page);
		await autenticar(page, SOPORTE);
		// `autenticar` no espera a que la sesión quede hecha: sin esto, el `goto`
		// corre contra el login y la bitácora sale vacía por la razón equivocada.
		await expect(page).toHaveURL(/\/admin$/);
		await page.goto('/admin/bitacora?accion=fe_ambiente');
		await expect(page.getByText('sandbox → production').first()).toBeVisible();
	});

	test('volver a pruebas no pide confirmación', async ({ page }) => {
		const dueno = await companiaPropia(page, 'volver');
		await abrirFacturaElectronica(page, dueno);

		await clicHasta(page.getByRole('button', { name: /Pasar a producción/i }), async () => {
			await expect(page.getByRole('dialog')).toBeVisible();
		});
		await page.getByRole('button', { name: /Sí, pasar a producción/i }).click();
		await expect(page.getByText(/Ambiente en uso: producción/i)).toBeVisible();

		// Un solo clic, sin diálogo: exigir confirmación para deshacer convierte la
		// salida de un error en un segundo trámite.
		await page.getByRole('button', { name: /Volver a pruebas/i }).click();
		await expect(page.getByText(/Ambiente en uso: pruebas/i)).toBeVisible();
	});

	test('guardar la configuración no mueve el ambiente', async ({ page }) => {
		/*
		 * La puerta lateral (T-611). Sin cerrarla, la confirmación y la bitácora de
		 * RN-35 serían decoración: bastaría con guardar la pantalla de
		 * Configuración para pasar a producción sin que quedara rastro.
		 */
		const dueno = await companiaPropia(page, 'lateral');
		await abrirFacturaElectronica(page, dueno);

		await clicHasta(page.getByRole('button', { name: /Pasar a producción/i }), async () => {
			await expect(page.getByRole('dialog')).toBeVisible();
		});
		await page.getByRole('button', { name: /Sí, pasar a producción/i }).click();
		await expect(page.getByText(/Ambiente en uso: producción/i)).toBeVisible();

		// Se guarda la pantalla entera, como quien cambia el teléfono del negocio.
		// Esperando la respuesta y no solo `networkidle`, que se cumple antes de que
		// salga el POST: el `goto` de abajo cortaba el guardado a medias (ERR_ABORTED),
		// como ya documenta `guardarConfiguracion` en tipo-de-comprobante.spec.ts.
		const guardado = page.waitForResponse(
			(r) => r.url().includes('/configuracion') && r.request().method() === 'POST'
		);
		await page.getByRole('button', { name: /Guardar cambios/i }).click();
		expect((await guardado).ok(), 'no se pudo guardar la configuración').toBe(true);
		await page.waitForLoadState('networkidle');

		await page.goto('/configuracion');
		await clicHasta(page.getByRole('button', { name: /Factura electrónica/i }), async () => {
			await expect(page.getByText(/Ambiente en uso/i)).toBeVisible();
		});
		await expect(page.getByText(/Ambiente en uso: producción/i)).toBeVisible();
	});
});

test.describe('quitar el certificado (RF-24)', () => {
	test('no borra las credenciales de transmisión', async ({ page }) => {
		const dueno = await companiaPropia(page, 'quitar');
		await abrirFacturaElectronica(page, dueno);

		await subirCertificado(page, 'sandbox', p12('PARA QUITAR'));
		await guardarAtv(page, 'sandbox', 'la-buena');
		await expect(tarjeta(page, 'sandbox').getByText(/Listo para emitir/)).toBeVisible();

		await tarjeta(page, 'sandbox')
			.getByRole('button', { name: /Quitar/i })
			.click();

		await expect(tarjeta(page, 'sandbox').getByText(/Todavía no hay certificado/i)).toBeVisible();
		// Son dos cosas con vidas distintas: quien quita una no pidió nada de la
		// otra, y borrarlas juntas obligaría a volver a escribir una contraseña
		// que nadie dijo que estuviera mal.
		await expect(tarjeta(page, 'sandbox').locator('input[name="atv_usuario"]')).toHaveValue(
			'cpf-01-1234-5678@pruebas.cr'
		);
	});
});

test.describe('el vencimiento (T-606)', () => {
	test('un certificado por vencer avisa, y uno vencido no está listo', async ({ page }) => {
		const dueno = await companiaPropia(page, 'vence');
		await abrirFacturaElectronica(page, dueno);

		// Dentro de los 30 días de aviso.
		await subirCertificado(page, 'sandbox', p12('POR VENCER', 12));
		await guardarAtv(page, 'sandbox', 'la-buena');
		await expect(tarjeta(page, 'sandbox').getByText(/vence en 1[12] día/i)).toBeVisible();
		// Todavía sirve: avisar no es bloquear.
		await expect(tarjeta(page, 'sandbox').getByText(/Listo para emitir/)).toBeVisible();

		// Uno ya vencido está configurado y **no** sirve. Es la tercera condición
		// de «listo», que es la que se olvida.
		await subirCertificado(page, 'production', p12('YA VENCIDO', -5));
		await guardarAtv(page, 'production', 'la-buena');
		await expect(tarjeta(page, 'production').getByText(/certificado venció/i)).toBeVisible();
		await expect(tarjeta(page, 'production').getByText(/Incompleto/)).toBeVisible();
	});
});
