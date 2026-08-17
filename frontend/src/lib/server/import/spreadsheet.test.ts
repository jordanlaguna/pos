import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { TEMPLATE_CSV, parseSpreadsheet } from './spreadsheet';

/**
 * Caracterización del lector de hojas de cálculo (T-104b).
 *
 * Los números vienen de `.specify/progress.json` →
 * `invariantes_verificados.entrada_csv`: columnas desordenadas, con tildes,
 * punto y coma, una fila vacía y una cantidad en cero. Entran 3 de 4 líneas,
 * 70 unidades y ₡69 080.
 *
 * El archivo de prueba está en `tests/fixtures/` a propósito: un CSV escrito
 * como lo manda un proveedor de verdad, no como conviene al lector.
 *
 * **De dónde salen las cifras.** El CSV original de aquella comprobación vivía
 * en un directorio temporal y se perdió; lo que quedó anotado son los números.
 * Este archivo se armó para reproducirlos exactos —24 × 1 100 + 12 × 780 +
 * 34 × 980 = 69 080 en 70 unidades— conservando todo lo que hacía difícil el
 * caso: separador de punto y coma, encabezados con otro nombre y otro orden,
 * un monto escrito `1.100,00`, una fila vacía en medio y una cantidad en cero.
 */

const CSV = readFileSync(
	fileURLToPath(new URL('../../../../tests/fixtures/entrada-proveedor.csv', import.meta.url))
);

async function leer(contenido: Buffer | string, nombre = 'entrada.csv') {
	return parseSpreadsheet(
		Buffer.isBuffer(contenido) ? contenido : Buffer.from(contenido, 'utf-8'),
		nombre
	);
}

describe('el invariante de progress.json', () => {
	it('entran 3 de 4 líneas, 70 unidades y ₡69 080', async () => {
		const r = await leer(CSV);
		const utiles = r.lines.filter((l) => !l.issue);

		expect(r.lines).toHaveLength(4);
		expect(utiles).toHaveLength(3);
		expect(utiles.reduce((acc, l) => acc + l.quantity, 0)).toBe(70);
		expect(utiles.reduce((acc, l) => acc + l.unit_cost * l.quantity, 0)).toBe(69080);
	});

	it('el origen queda marcado como hoja de cálculo', async () => {
		expect((await leer(CSV)).source).toBe('excel');
	});
});

describe('lo que el lector tiene que tolerar', () => {
	it('columnas en cualquier orden y con cualquier nombre razonable', async () => {
		// El archivo de prueba trae «Descripcion; Cant; Costo unitario; Codigo»:
		// ni el orden ni los nombres de la plantilla.
		const r = await leer(CSV);
		const arroz = r.lines[0];
		expect(arroz.description).toContain('Arroz');
		expect(arroz.code).toBe('7441000100015');
		expect(arroz.quantity).toBe(24);
	});

	it('montos escritos a la costarricense', async () => {
		// `1.100,00` es mil cien, no uno coma uno.
		const r = await leer(CSV);
		expect(r.lines[0].unit_cost).toBe(1100);
	});

	it('tildes en las descripciones', async () => {
		const r = await leer(CSV);
		expect(r.lines[0].description).toBe('Arroz Tío Pelón 1kg');
	});

	it('filas vacías en medio', async () => {
		// Se descartan sin contarse como línea.
		const r = await leer(CSV);
		expect(r.lines.every((l) => l.description.trim() !== '')).toBe(true);
	});

	it('una cantidad en cero se marca en vez de colarse', async () => {
		const r = await leer(CSV);
		const bolsa = r.lines.find((l) => l.description.includes('Bolsa'))!;
		expect(bolsa.quantity).toBe(0);
		expect(bolsa.issue).toBeTruthy();
	});

	it('separador por comas además de punto y coma', async () => {
		const r = await leer('Codigo,Descripcion,Cantidad,Costo\n111,Algo,2,500\n');
		expect(r.lines).toHaveLength(1);
		expect(r.lines[0].quantity).toBe(2);
		expect(r.lines[0].unit_cost).toBe(500);
	});

	it('la plantilla que descarga el usuario se lee sola', async () => {
		// Si la plantilla que ofrece el sistema no pasara su propio lector, sería
		// lo primero con lo que tropieza quien la usa.
		const r = await leer(TEMPLATE_CSV);
		expect(r.lines).toHaveLength(3);
		expect(r.lines.reduce((acc, l) => acc + l.quantity, 0)).toBe(72);
	});
});

describe('archivos que no sirven', () => {
	it('uno vacío', async () => {
		await expect(leer('')).rejects.toThrow(/vacío|encabezados/i);
	});

	it('uno con solo encabezados', async () => {
		await expect(leer('Codigo;Descripcion;Cantidad;Costo\n')).rejects.toThrow(
			/vacío|encabezados/i
		);
	});

	it('uno sin columna de cantidad', async () => {
		await expect(leer('Codigo;Descripcion;Costo\n111;Algo;500\n')).rejects.toThrow(
			/cantidad/i
		);
	});
});
