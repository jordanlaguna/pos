import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

/**
 * Los tres catálogos dicen lo mismo (T-813).
 *
 * **Paraglide no avisa de nada de esto**, y se midió en vez de suponerlo:
 *
 * | Lo que se rompe | Qué dice `npm run check` | Qué se ve |
 * |---|---|---|
 * | Una clave falta en `en` | nada | la frase sale en español |
 * | Un parámetro falta en la traducción | nada | el dato desaparece de la frase |
 * | Una clave existe en `en` y no en `es` | nada | una función que nadie llama |
 *
 * El segundo es el peor y es el que no estaba previsto: si `es` dice «Solo
 * quedan {free} de {product}: hay {reserved} apartadas en otra venta» y la
 * traducción inglesa dice «Only {free} left of {product}», el cajero inglés no
 * se entera de que hay unidades apartadas. No es una frase sin traducir —que se
 * nota— sino una frase completa a la que le falta un dato.
 *
 * La comprobación de parámetros **no admite excepciones**, y la de claves tampoco
 * desde que los tres catálogos están completos (T-807, T-808). Hubo una lista de
 * catálogos «todavía sin traducir» mientras se llenaban, con un guardián que
 * obligaba a sacarlos al terminarlos; se borró al quedar vacía, porque una lista
 * de excepciones vacía es una prueba que no puede fallar y aun así tranquiliza.
 *
 * Exigir los mismos parámetros obliga a que una traducción sin género —el inglés
 * no lo tiene— conserve la declaración del selector. Se comprobó que eso compila
 * limpio: una variante con un solo `concord=*` en `en` da 0 errores.
 *
 * Y no la escribe el compilador porque no puede: para él, cada idioma es un
 * mensaje distinto y nada obliga a que dos mensajes distintos se parezcan.
 */

const RAIZ = fileURLToPath(new URL('../../../messages', import.meta.url));

/** El idioma que se escribe primero y del que salen las claves. */
const BASE = 'es';
const TRADUCIDOS = ['en', 'pt'];


/** Una variante del formato de inlang: selectores y un texto por caso. */
interface Variante {
	declarations?: string[];
	selectors?: string[];
	match?: Record<string, string>;
}

type Mensaje = string | Variante[];

function catalogos(locale: string): string[] {
	return readdirSync(join(RAIZ, locale))
		.filter((n) => n.endsWith('.json'))
		.sort();
}

function leer(locale: string, archivo: string): Record<string, Mensaje> {
	const crudo = JSON.parse(readFileSync(join(RAIZ, locale, archivo), 'utf-8')) as Record<
		string,
		Mensaje
	>;
	// Las claves que empiezan con `$` son del formato (`$schema`) o comentarios
	// del catálogo (`$comentario`), no mensajes.
	return Object.fromEntries(Object.entries(crudo).filter(([k]) => !k.startsWith('$')));
}

/** Los `{marcadores}` de un texto. */
function marcadores(texto: string): string[] {
	return [...texto.matchAll(/\{([^}]+)\}/g)].map((m) => m[1].trim());
}

/**
 * El nombre que declara una declaración del formato de inlang.
 *
 * Son de dos formas: `"input concord"` declara el parámetro `concord`, y
 * `"local remainingPlural = remaining: plural"` declara una variable calculada a
 * partir de otro parámetro. Se compara el **nombre** y no el texto para que dos
 * catálogos no difieran por un espacio de más en la declaración de un local.
 */
function nombreDeclarado(declaracion: string): string {
	const sinPrefijo = declaracion.replace(/^(input|local)\s+/, '');
	return sinPrefijo.split('=')[0].trim();
}

/**
 * Lo que hay que pasarle al mensaje para que se arme.
 *
 * En un texto suelto son sus marcadores. En una variante son las declaraciones
 * más lo que use cada caso: el selector se declara y no aparece entre llaves,
 * así que sin las declaraciones se perdería justo el parámetro que elige la
 * frase.
 */
function parametros(mensaje: Mensaje): Set<string> {
	if (typeof mensaje === 'string') return new Set(marcadores(mensaje));
	const salida = new Set<string>();
	for (const variante of mensaje) {
		for (const declaracion of variante.declarations ?? []) {
			salida.add(nombreDeclarado(declaracion));
		}
		for (const selector of variante.selectors ?? []) salida.add(selector.trim());
		for (const texto of Object.values(variante.match ?? {})) {
			for (const p of marcadores(texto)) salida.add(p);
		}
	}
	return salida;
}

const ordenado = (s: Iterable<string>) => [...s].sort();

describe('los catálogos de los tres idiomas', () => {
	const archivosBase = catalogos(BASE);

	it('hay catálogos y claves que revisar', () => {
		// Si el recorrido se rompe, todo lo demás pasaría por vacío: es la forma
		// en que una prueba que lee archivos miente.
		expect(archivosBase.length).toBeGreaterThan(15);
		const claves = archivosBase.flatMap((a) => Object.keys(leer(BASE, a)));
		expect(claves.length).toBeGreaterThan(800);
	});

	it.each(TRADUCIDOS)('%s tiene los mismos archivos que el español', (locale) => {
		expect(catalogos(locale)).toEqual(archivosBase);
	});

	it('todos los catálogos están declarados en el proyecto de inlang', () => {
		/*
		 * El agujero que no estaba tapado, y costó 144 errores encontrarlo.
		 *
		 * `project.inlang/settings.json` lista los catálogos **uno por uno**. Un
		 * archivo nuevo que no esté en esa lista existe, se traduce a los tres
		 * idiomas, pasa todas las pruebas de arriba —tiene las mismas claves y los
		 * mismos parámetros— y Paraglide no lo compila: `m.mi_clave()` no existe.
		 * Y el compilador tampoco se queja, porque para él ese archivo no es nada.
		 *
		 * El síntoma es un muro de «Property 'x' does not exist» en `npm run check`
		 * que señala las pantallas, que es el único sitio donde no está el problema.
		 */
		const declarados = new Set(
			(
				JSON.parse(readFileSync(join(RAIZ, '..', 'project.inlang', 'settings.json'), 'utf-8')) as {
					'plugin.inlang.messageFormat': { pathPattern: string[] };
				}
			)['plugin.inlang.messageFormat'].pathPattern.map((patron) =>
				patron.replace('./messages/{locale}/', '')
			)
		);

		const sinDeclarar = archivosBase.filter((archivo) => !declarados.has(archivo));
		expect(
			sinDeclarar,
			`Estos catálogos existen y Paraglide no los compila: ${sinDeclarar.join(', ')}

` +
				'Agregalos a `pathPattern` en project.inlang/settings.json. Sin eso, sus ' +
				'mensajes no existen y el error sale en la pantalla que los usa.'
		).toEqual([]);

		// Y al revés: un patrón que apunte a un archivo borrado.
		const fantasmas = [...declarados].filter((archivo) => !archivosBase.includes(archivo));
		expect(fantasmas, `Declarados y sin archivo: ${fantasmas.join(', ')}`).toEqual([]);
	});

	it.each(TRADUCIDOS)('%s no tiene ninguna clave que el español no tenga', (locale) => {
		const sobrantes: string[] = [];
		for (const archivo of archivosBase) {
			const base = leer(BASE, archivo);
			for (const clave of Object.keys(leer(locale, archivo))) {
				if (!(clave in base)) sobrantes.push(`${locale}/${archivo} → ${clave}`);
			}
		}
		expect(
			sobrantes,
			`Estas claves no existen en ${BASE}:\n  ${sobrantes.join('\n  ')}\n\n` +
				'Casi siempre es una clave que se renombró en el catálogo base y quedó ' +
				'huérfana en la traducción: nadie la llama y nadie se enteraría.'
		).toEqual([]);
	});

	it.each(TRADUCIDOS)('%s usa los mismos parámetros que el español', (locale) => {
		const diferencias: string[] = [];
		for (const archivo of archivosBase) {
			const base = leer(BASE, archivo);
			for (const [clave, mensaje] of Object.entries(leer(locale, archivo))) {
				if (!(clave in base)) continue; // ya lo dice la prueba de sobrantes
				const esperados = ordenado(parametros(base[clave]));
				const tiene = ordenado(parametros(mensaje));
				if (esperados.join(',') !== tiene.join(',')) {
					diferencias.push(
						`${locale}/${archivo} → ${clave}: ${BASE} usa [${esperados.join(', ')}] ` +
							`y ${locale} usa [${tiene.join(', ')}]`
					);
				}
			}
		}
		expect(
			diferencias,
			`Estos mensajes no reciben los mismos datos en los dos idiomas:\n  ` +
				`${diferencias.join('\n  ')}\n\n` +
				'Un parámetro de menos no rompe nada: la frase se arma igual y el dato ' +
				'desaparece. Si el idioma no necesita el selector —el inglés no tiene ' +
				'género—, la traducción va como variante con un solo caso `=*`, que ' +
				'conserva la declaración.'
		).toEqual([]);
	});

	it.each(TRADUCIDOS)('%s tiene todas las claves del español', (locale) => {
		const faltantes: string[] = [];
		for (const archivo of archivosBase) {
			const traducido = leer(locale, archivo);
			for (const clave of Object.keys(leer(BASE, archivo))) {
				if (!(clave in traducido)) faltantes.push(`${locale}/${archivo} → ${clave}`);
			}
		}
		const informe = faltantes.map((f) => `  ${f}`).join('\n');
		expect(
			faltantes,
			`Faltan ${faltantes.length} claves:\n${informe}\n\n` +
				'Una clave que falta no se ve: Paraglide devuelve la del idioma base, así ' +
				'que la pantalla sale a medias en español y nadie se entera.'
		).toEqual([]);
	});
});
