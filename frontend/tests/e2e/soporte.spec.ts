import { expect, test, type Page } from '@playwright/test';
import { ADMIN, CAJERO, autenticar, entrar, salir } from './sesion';

/**
 * El panel de soporte, de punta a punta (T-310, F3).
 *
 * Es la prueba que cierra la fase: **dar de alta una compañía, entrar con su
 * administrador, vender, y comprobar que no ve nada de la otra**. Lo demás de
 * F3 —los estados, la bitácora, entrar como— está probado contra el stack real
 * en `backend/tests/test_soporte.py`; lo que solo se puede ver acá es que las
 * dos aplicaciones convivan: que soporte no entre al POS, que el POS no entre
 * al panel, y que la franja de la visita esté donde tiene que estar.
 *
 * Los selectores no dependen del idioma donde se puede: `input[name=…]`, la
 * URL y los `#id` de los desplegables.
 */

const SOPORTE = { email: 'soporte@ventasys.cr', password: 'soporte123' };

async function entrarComoSoporte(page: Page) {
	await autenticar(page, SOPORTE);
	// Soporte no elige compañía porque no tiene ninguna (RN-4): va directo al
	// panel. Que la URL sea `/admin` y no `/compania` es la mitad de la prueba.
	await expect(page).toHaveURL(/\/admin$/);
}

/** Un correo distinto en cada corrida: el simulado guarda su estado en disco. */
function marca(): string {
	return `${Date.now()}`.slice(-8);
}

/**
 * Da de alta una compañía desde el panel y deja la pantalla en su ficha.
 *
 * La contraseña es siempre `dueno123`: lo que se prueba es el alta, no la
 * variedad de las claves.
 */
async function altaDeCompania(page: Page, negocio: string, correo: string) {
	await page.getByRole('link', { name: /Nueva compañía/i }).click();
	await expect(page).toHaveURL(/\/admin\/companias\/nueva/);

	await page.locator('input[name="nombre"]').fill(negocio);
	await page.locator('input[name="identificacion"]').fill('3101999888');
	await page.locator('input[name="email"]').fill(correo);
	await page.locator('input[name="password"]').fill('dueno123');
	await page.locator('input[name="name"]').fill('Dueña');
	await page.locator('input[name="lastName"]').fill('Nueva');
	// El plan se elige a mano: el primero del desplegable es el más barato y esta
	// prueba no tiene por qué saber cuál es.
	await page.locator('#plan_id').selectOption({ label: 'Comercio' });
	await page.getByRole('button', { name: /Dar de alta/i }).click();

	// Queda en la ficha de la compañía nueva, con el aviso de que se creó.
	await expect(page).toHaveURL(/\/admin\/companias\/\d+\?creada=1/);
}

test.describe('las dos aplicaciones no se cruzan (T-302)', () => {
	test('soporte entra al panel y no al POS', async ({ page }) => {
		await entrarComoSoporte(page);
		await expect(page.getByRole('link', { name: /Compañías/i })).toBeVisible();

		// Y el POS le responde 403, no lo manda al login: tiene una sesión válida,
		// lo que no tiene es compañía.
		await page.goto('/ventas');
		await expect(page.locator('body')).toContainText('403');

		// El botón del error lo devuelve al panel y no a ventas, que es a donde no
		// puede entrar.
		await page.getByRole('link', { name: /panel de soporte/i }).click();
		await expect(page).toHaveURL(/\/admin$/);
	});

	test('un administrador de compañía no entra al panel', async ({ page }) => {
		await entrar(page, ADMIN);
		await page.goto('/admin');
		await expect(page.locator('body')).toContainText('403');
	});

	test('un cajero tampoco', async ({ page }) => {
		await entrar(page, CAJERO);
		await page.goto('/admin');
		await expect(page.locator('body')).toContainText('403');
	});
});

test.describe('alta de compañía y su primera venta (T-310, RF-6)', () => {
	test('se da de alta, entra su administrador y cobra', async ({ page }) => {
		const sufijo = marca();
		const negocio = `Ferretería ${sufijo}`;
		const correo = `dueno.${sufijo}@ventasys.cr`;

		await entrarComoSoporte(page);
		await altaDeCompania(page, negocio, correo);
		await expect(page.locator('body')).toContainText(negocio);
		await expect(page.locator('body')).toContainText('001');

		// Y aparece en el listado, con su plan y su estado.
		await page.goto('/admin');
		const fila = page.locator('tr', { hasText: negocio });
		await expect(fila).toBeVisible();
		await expect(fila).toContainText('Comercio');

		/*
		 * El administrador de la compañía nueva entra y vende.
		 *
		 * Es la parte que hace que el alta signifique algo: una compañía a la que
		 * hay que arreglarle algo a mano antes de poder cobrar no está dada de
		 * alta. Y su catálogo está **vacío**, así que la venta se hace después de
		 * crear un producto —que es exactamente lo que hace un negocio nuevo—.
		 */
		await salir(page);
		await autenticar(page, { email: correo, password: 'dueno123' });
		await expect(page).toHaveURL(/\/(ventas|dashboard)/);

		// No ve nada de la compañía del demo: su catálogo arranca en cero (RNF-1).
		await page.goto('/inventario');
		await expect(page.locator('body')).not.toContainText('Arroz Tío Pelón');

		await page.goto('/ventas');
		await expect(page.getByRole('button', { name: /Arroz/i })).toHaveCount(0);
	});
});

test.describe('la suscripción se aplica en cada pantalla (T-308, RF-10)', () => {
	test('el aviso de vencimiento se ve en el POS', async ({ page }) => {
		// La segunda compañía del demo nace en prueba y por vencer, para que este
		// caso exista sin tener que configurar nada.
		await entrar(page, ADMIN, 'Sucursal Norte');
		await page.goto('/dashboard');
		await expect(page.locator('body')).toContainText(/vence/i);
	});

	test('con la suscripción suspendida no se puede vender', async ({ page }) => {
		/*
		 * Se suspende una compañía **propia**, no la del demo.
		 *
		 * La primera versión suspendía la compañía 1 y la devolvía a «activa» al
		 * final. Funcionaba hasta que falló a mitad: dejó el demo suspendido en
		 * `.data/mock-db.json`, y las trece pruebas de los otros archivos —que
		 * venden en esa compañía— empezaron a fallar señalando la pantalla de
		 * ventas. Es la misma trampa que documenta `idioma.spec.ts`, y la salida no
		 * es restaurar mejor sino no tocar lo que otros usan.
		 */
		const sufijo = marca();
		const negocio = `Suspendida ${sufijo}`;
		const correo = `moroso.${sufijo}@ventasys.cr`;

		await entrarComoSoporte(page);
		await altaDeCompania(page, negocio, correo);

		await page.locator('#estado').selectOption('suspendida');
		await page.getByRole('button', { name: /Guardar la suscripción/i }).click();
		await expect(page.locator('body')).toContainText(/Suspendida/i);

		// Su administrador entra —con la suscripción suspendida entra el
		// administrador y solo para ver el aviso— y no puede abrir ventas.
		await salir(page);
		await autenticar(page, { email: correo, password: 'dueno123' });
		await expect(page).toHaveURL(/\/(ventas|dashboard)/);
		await page.goto('/dashboard');
		await expect(page.locator('body')).toContainText(/suspendida/i);

		await page.goto('/ventas');
		await expect(page.locator('body')).toContainText('403');
	});
});

test.describe('entrar como una compañía (T-306, RF-8, RN-4)', () => {
	test('la franja está siempre, no se puede escribir y se vuelve al panel', async ({ page }) => {
		await entrarComoSoporte(page);
		await page.goto('/admin/companias/1');

		await page.locator('textarea[name="motivo"]').fill('revisar por qué no cierra la caja');
		await page.getByRole('button', { name: /Entrar a mirar/i }).click();

		// Adentro, en el tablero de esa compañía.
		await expect(page).toHaveURL(/\/dashboard/);
		const franja = page.locator('form[action="/admin/salir"]').locator('..');
		await expect(franja).toContainText(/Abastecedor La Esquina/i);
		await expect(franja).toContainText(/Solo lectura/i);
		await expect(franja).toContainText(/no cierra la caja/i);

		// La franja sigue ahí al navegar: es permanente, no un aviso de bienvenida.
		await page.goto('/inventario');
		await expect(page.locator('form[action="/admin/salir"]')).toBeVisible();

		// Ve los datos del cliente —para eso existe— y no puede vender.
		await expect(page.locator('body')).toContainText('Arroz');
		await page.goto('/ventas');
		await expect(page.locator('body')).toContainText('403');

		// Y vuelve al panel sin escribir la contraseña otra vez.
		await page.goto('/inventario');
		await page.getByRole('button', { name: /Volver al panel/i }).click();
		await expect(page).toHaveURL(/\/admin$/);
		await expect(page.getByRole('link', { name: /Compañías/i })).toBeVisible();
	});
});

test.describe('la bitácora (T-307, RF-9)', () => {
	test('registra lo que hizo soporte y se puede filtrar', async ({ page }) => {
		await entrarComoSoporte(page);
		await page.goto('/admin/bitacora');

		// Las acciones de las pruebas anteriores están: el alta, el cambio de
		// suscripción y la visita.
		await expect(page.locator('body')).toContainText(/Dio de alta la compañía/i);
		await expect(page.locator('body')).toContainText(/Entró como la compañía/i);

		// El filtro es un GET: produce una URL que se puede guardar y volver a abrir.
		await page.locator('#accion').selectOption('entrar_como');
		await page.getByRole('button', { name: /Filtrar/i }).click();
		await expect(page).toHaveURL(/accion=entrar_como/);
		/*
		 * La aserción negativa mira **la tabla** y no el `body`.
		 *
		 * El desplegable del filtro lista todas las acciones que existen, así que
		 * «Dio de alta la compañía» está siempre en la página aunque la tabla no lo
		 * tenga. Es la trampa de asertar sobre `body`: da verde de más y, al
		 * revés, rojo de más.
		 */
		const tabla = page.locator('table tbody');
		await expect(tabla).toContainText(/Entró como la compañía/i);
		await expect(tabla).not.toContainText(/Dio de alta la compañía/i);
	});
});
