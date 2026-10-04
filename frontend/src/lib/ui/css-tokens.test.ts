import { readFileSync, readdirSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

/**
 * Lo que una pantalla pide a `app.css` existe en `app.css` (QA-06).
 *
 * El navegador ignora sin avisar una clase que no existe y una `var(--x)` sin
 * definir, así que estos errores no los ve `npm run check` ni ninguna prueba:
 * se ven probando la pantalla. Cuando se escribió esto había tres:
 *
 * - `btn-secondary` en los botones del certificado y de las credenciales, que
 *   salían con el `.btn` pelado, sin fondo ni borde;
 * - `btn-sm` en contabilidad;
 * - `--danger`, `--success` y sus fondos en diez pantallas, que pintaban de
 *   color normal un asiento descuadrado o un error, y `--accent-soft`, que dejaba
 *   el ícono de cada compañía, en la pantalla de elegirla, sin fondo y casi
 *   invisible.
 */

const AQUI = dirname(fileURLToPath(import.meta.url));
const SRC = resolve(AQUI, '../..');
const CSS = readFileSync(join(SRC, 'app.css'), 'utf-8');

function svelteFiles(dir: string): string[] {
	return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
		const ruta = join(dir, entry.name);
		if (entry.isDirectory()) return entry.name === 'paraglide' ? [] : svelteFiles(ruta);
		return entry.name.endsWith('.svelte') ? [ruta] : [];
	});
}

const PANTALLAS = svelteFiles(SRC).map((archivo) => ({
	archivo: relative(SRC, archivo),
	texto: readFileSync(archivo, 'utf-8')
}));

describe('las clases de botón', () => {
	const definidas = new Set([...CSS.matchAll(/\.(btn(?:-[a-z]+)?)\b/g)].map((m) => m[1]));

	it('app.css define las de siempre', () => {
		expect([...definidas]).toEqual(expect.arrayContaining(['btn', 'btn-primary', 'btn-ghost']));
	});

	it('ninguna pantalla usa una que no existe', () => {
		const faltan = PANTALLAS.flatMap(({ archivo, texto }) =>
			[...texto.matchAll(/[\s"'`{](btn-[a-z]+)(?=[\s"'`}])/g)]
				.map((m) => m[1])
				.filter((clase) => !definidas.has(clase))
				.map((clase) => `${archivo}: ${clase}`)
		);
		expect(faltan).toEqual([]);
	});
});

describe('las variables de color', () => {
	const globales = new Set([...CSS.matchAll(/(--[a-z0-9-]+)\s*:/g)].map((m) => m[1]));

	it('app.css define los tokens de siempre', () => {
		expect([...globales]).toEqual(
			expect.arrayContaining(['--negative', '--positive', '--accent', '--accent-soft', '--surface-sunken'])
		);
	});

	it('ninguna pantalla usa una que no está definida', () => {
		const faltan = PANTALLAS.flatMap(({ archivo, texto }) => {
			// Las que el archivo define en su propio `<style>` también valen.
			const locales = new Set([...texto.matchAll(/(--[a-z0-9-]+)\s*:/g)].map((m) => m[1]));
			return [...texto.matchAll(/var\((--[a-z0-9-]+)/g)]
				.map((m) => m[1])
				.filter((v) => !globales.has(v) && !locales.has(v))
				.map((v) => `${archivo}: ${v}`);
		});
		expect(faltan).toEqual([]);
	});
});
