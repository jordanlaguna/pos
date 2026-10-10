import { readFileSync, readdirSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

/**
 * Ningún `<select>` suelto fuera de `Select.svelte` (T-933).
 *
 * Los combos se ven iguales porque todos pasan por el mismo componente: el
 * desplegable de una lista nativa lo pinta el sistema operativo y no hay forma
 * de que se parezca a nada. Un `<select>` escrito a mano en una pantalla se ve
 * distinto a los demás sin que nada lo avise, así que esto lo tumba.
 *
 * Se exime `multiple`: una lista de varias filas no es un desplegable y el
 * componente no la reemplaza. Lo que está en un comentario no cuenta.
 */

const AQUI = dirname(fileURLToPath(import.meta.url));
const SRC = resolve(AQUI, '../..');
const COMPONENTE = join('lib', 'ui', 'components', 'Select.svelte');

function svelteFiles(dir: string): string[] {
	return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
		const ruta = join(dir, entry.name);
		if (entry.isDirectory()) return entry.name === 'paraglide' ? [] : svelteFiles(ruta);
		return entry.name.endsWith('.svelte') ? [ruta] : [];
	});
}

/** El marcado sin comentarios HTML ni líneas de comentario del script. */
function sinComentarios(texto: string): string {
	return texto.replace(/<!--[\s\S]*?-->/g, '').replace(/^\s*(\/\/|\*|\/\*).*$/gm, '');
}

describe('los <select> sueltos', () => {
	const sueltos = svelteFiles(SRC).flatMap((archivo) => {
		const ruta = relative(SRC, archivo);
		if (ruta === COMPONENTE) return [];
		const texto = sinComentarios(readFileSync(archivo, 'utf-8'));
		return [...texto.matchAll(/<select\b([^>]*)>/g)]
			.filter((m) => !/\bmultiple\b/.test(m[1]))
			.map(() => ruta);
	});

	it('no hay ninguno fuera de Select.svelte', () => {
		expect(sueltos).toEqual([]);
	});

	it('y el componente sí tiene el suyo, que es el que viaja en el formulario', () => {
		const texto = readFileSync(join(SRC, COMPONENTE), 'utf-8');
		expect(texto).toMatch(/<select\b/);
		expect(texto).toMatch(/sr-only/);
	});
});
