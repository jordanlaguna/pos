import { expect, test, type Page } from '@playwright/test';

import { autenticar, entrar } from './sesion';

/**
 * La página entera no se desplaza: lo que se desplaza es el contenido.
 *
 * El marco del POS mide lo que mide la ventana, con el menú a la izquierda y
 * el contenido en un `main` que tiene su propia barra. Si el documento crece
 * más que la ventana, aparece una segunda barra a la derecha y al bajar se
 * lleva el menú por delante: queda cortado a media pantalla, con fondo vacío
 * debajo.
 *
 * Pasaba en el detalle de una venta con la plantilla del tiquete (2026-10-03).
 * La causa era un `sr-only` —el rótulo invisible del monto en letras—: es
 * `position: absolute`, y como `main` desplazaba sin estar posicionado, ese
 * rótulo no quedaba dentro de él sino del documento, y lo estiraba hasta su
 * altura. Cualquier pantalla larga con un rótulo así abajo hacía lo mismo; por
 * eso se recorren todas y no solo la del aviso.
 */

const POS = [
	'/ventas',
	'/caja',
	'/facturas',
	'/devoluciones',
	'/dashboard',
	'/inventario',
	'/inventario/categorias',
	'/inventario/clasificar',
	'/inventario/entradas',
	'/inventario/entradas/nueva',
	'/compras/proveedores',
	'/compras/cuentas-por-pagar',
	'/contabilidad',
	'/contabilidad/asientos',
	'/contabilidad/reportes',
	'/contabilidad/iva',
	'/contabilidad/periodos',
	'/contabilidad/cuentas',
	'/contabilidad/mapeo',
	'/planilla',
	'/planilla/empleados',
	'/planilla/acciones',
	'/planilla/corridas',
	'/planilla/vacaciones',
	'/planilla/archivos',
	'/planilla/configuracion',
	'/planilla/importar',
	'/planilla/tasas',
	'/clientes',
	'/usuarios',
	'/configuracion'
];

/*
 * Una ventana baja a propósito. El rótulo solo estira el documento si cae más
 * abajo que el borde de la ventana; con la de 720 de siempre, la venta corta
 * del simulado lo dejaba adentro y la prueba pasaba con el defecto puesto.
 */
test.use({ viewport: { width: 1280, height: 480 } });

const SOPORTE = { email: 'soporte@ventasys.cr', password: 'soporte123' };
const PANEL = ['/admin', '/admin/bitacora', '/admin/planes', '/admin/companias/nueva'];

/** Cuánto se pasa el documento de la ventana, en píxeles. */
async function sobrante(page: Page, ruta: string) {
	await page.goto(ruta);
	await expect(page.locator('main')).toBeVisible();
	return page.evaluate(
		() => document.documentElement.scrollHeight - document.documentElement.clientHeight
	);
}

/** Recorre las rutas y devuelve las que estiran el documento. */
async function rotas(page: Page, rutas: string[]) {
	const salida: string[] = [];
	for (const ruta of rutas) {
		const sobra = await sobrante(page, ruta);
		if (sobra > 1) salida.push(`${ruta} (+${sobra}px)`);
	}
	return salida;
}

/** El primer enlace de una lista hacia su detalle, para probar una pantalla con id. */
async function primerDetalle(page: Page, lista: string, prefijo: string) {
	await page.goto(lista);
	const hrefs = await page
		.locator(`main a[href^="${prefijo}"]`)
		.evaluateAll((as) => as.map((a) => a.getAttribute('href') ?? ''));
	// Con número: «nueva» también empieza igual y no es un detalle.
	return hrefs.find((h) => /\/\d+$/.test(h)) ?? null;
}

test('ninguna pantalla del POS desplaza la página entera', async ({ page }) => {
	await entrar(page);

	const rutas = [...POS];
	for (const [lista, prefijo] of [
		['/facturas', '/facturas/'],
		['/devoluciones', '/devoluciones/'],
		['/planilla/empleados', '/planilla/empleados/']
	]) {
		const detalle = await primerDetalle(page, lista, prefijo);
		if (detalle) rutas.push(detalle);
	}
	// La del aviso tiene que estar: es la que tiene el tiquete y su rótulo.
	expect(rutas.some((r) => /^\/facturas\/\d+/.test(r))).toBe(true);

	expect(await rotas(page, rutas)).toEqual([]);
});

test('ninguna pantalla del panel de soporte desplaza la página entera', async ({ page }) => {
	await autenticar(page, SOPORTE);
	await expect(page).toHaveURL(/\/admin/);

	const rutas = [...PANEL];
	const compania = await primerDetalle(page, '/admin', '/admin/companias/');
	if (compania) rutas.push(compania);

	expect(await rotas(page, rutas)).toEqual([]);
});
