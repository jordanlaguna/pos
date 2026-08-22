import { readFileSync, readdirSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { parse } from 'svelte/compiler';
import ts from 'typescript';

/**
 * Ningún texto que vea una persona se escribe dentro de un componente (T-812).
 *
 * Es la red que impide que los catálogos se queden atrás. Sin ella, la próxima
 * pantalla se escribe con la cadena adentro —cuesta lo mismo en el momento— y
 * nadie se entera hasta que alguien pide el POS en portugués. Cada pantalla así
 * es una pantalla que hay que volver a abrir.
 *
 * **Lee el árbol de sintaxis, no las líneas.** Un rastreador por líneas da
 * falsos positivos con lo que más abunda en este código —comentarios de varias
 * líneas y ternarios de clases de Tailwind— y una prueba que grita en falso se
 * termina desactivando. En el árbol la diferencia es exacta: un comentario es un
 * `Comment`, un `class={a ? 'x' : 'y'}` es un `ExpressionTag`, y el texto de
 * verdad es un `Text`.
 *
 * Importar `svelte/compiler` es la única excepción a la nota de
 * `vitest.config.ts`: acá no se compila ningún componente, se lee su árbol como
 * dato.
 */

const AQUI = dirname(fileURLToPath(import.meta.url));
const SRC = resolve(AQUI, '../..');

/** Donde vive la interfaz. */
const CARPETAS = ['routes', 'lib/ui'];

/**
 * Atributos que son rótulo: lo que llevan lo lee una persona.
 *
 * No están todos los atributos a propósito: `type`, `name`, `id`, `action` y
 * compañía llevan valores del contrato, no texto.
 */
const ROTULOS = new Set([
	'label',
	'title',
	'placeholder',
	'hint',
	'alt',
	'aria-label',
	'aria-description',
	'description',
	'subtitle',
	'errorTitle',
	'emptyMessage',
	'valueHeader',
	'secondaryHeader',
	'successMessage'
]);

/**
 * Etiquetas cuyo contenido es código por definición: una ruta, una clave, un
 * nombre de archivo. No se traduce y no tiene por qué salir del catálogo.
 */
const TECNICAS = new Set(['code', 'pre', 'kbd', 'samp', 'var', 'style', 'script']);

/**
 * Lo que puede quedar literal, con su razón.
 *
 * Una lista de excepciones sin razones se convierte en el lugar donde se esconde
 * lo que molesta, así que cada entrada lleva la suya. Y solo entra lo que de
 * verdad aparece: las teclas (`F1`, `Esc`) no están porque no hacen falta —viven
 * dentro de expresiones, no como texto del marcado— y una excepción que no se
 * usa es la que después justifica la siguiente.
 */
const PERMITIDO = new Map<string, string>([
	// Los seis `<title>` de las pantallas sin sesión: «{m.x()} · VentaSys».
	['VentaSys', 'la marca no se traduce']
]);

/** Tres letras seguidas: menos que eso es un signo, un símbolo o una unidad. */
const PALABRA = /[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{3}/;

interface Hallazgo {
	archivo: string;
	linea: number;
	tipo: 'texto suelto' | 'rótulo literal';
	texto: string;
}

function archivosSvelte(carpeta: string): string[] {
	const encontrados: string[] = [];
	for (const entrada of readdirSync(carpeta, { withFileTypes: true })) {
		const ruta = join(carpeta, entrada.name);
		if (entrada.isDirectory()) encontrados.push(...archivosSvelte(ruta));
		else if (entrada.name.endsWith('.svelte')) encontrados.push(ruta);
	}
	return encontrados;
}

/** Número de línea de una posición, para que el fallo diga dónde mirar. */
function lineaDe(fuente: string, posicion: number): number {
	let linea = 1;
	for (let i = 0; i < posicion && i < fuente.length; i++) {
		if (fuente[i] === '\n') linea++;
	}
	return linea;
}

function esPermitido(texto: string): boolean {
	if (PERMITIDO.has(texto)) return true;
	// Un texto hecho solo de palabras permitidas y signos tampoco es traducible:
	// «VentaSys · POS».
	const palabras = texto.split(/[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9]+/).filter(Boolean);
	return palabras.length > 0 && palabras.every((p) => PERMITIDO.has(p));
}

/* eslint-disable @typescript-eslint/no-explicit-any */
function revisar(archivo: string, fuente: string): Hallazgo[] {
	const hallazgos: Hallazgo[] = [];
	const nodos = (parse(fuente, { modern: true }) as any).fragment;

	function recorrer(nodo: any, dentroDeTecnica: boolean) {
		if (!nodo || typeof nodo !== 'object') return;

		if (nodo.type === 'Text') {
			const texto = String(nodo.data ?? '').trim();
			if (!dentroDeTecnica && PALABRA.test(texto) && !esPermitido(texto)) {
				hallazgos.push({
					archivo,
					linea: lineaDe(fuente, nodo.start),
					tipo: 'texto suelto',
					texto
				});
			}
			return;
		}

		// Un comentario no lo lee nadie más que quien programa.
		if (nodo.type === 'Comment') return;

		const nombre = typeof nodo.name === 'string' ? nodo.name.toLowerCase() : '';
		const tecnica = dentroDeTecnica || TECNICAS.has(nombre);

		for (const atributo of nodo.attributes ?? []) {
			if (atributo.type !== 'Attribute' || !ROTULOS.has(atributo.name)) continue;
			// Un valor que es expresión ya pasó por el catálogo o por una variable.
			if (!Array.isArray(atributo.value)) continue;
			const literal = atributo.value
				.filter((v: any) => v.type === 'Text')
				.map((v: any) => String(v.data ?? ''))
				.join('')
				.trim();
			if (!PALABRA.test(literal) || esPermitido(literal)) continue;
			hallazgos.push({
				archivo,
				linea: lineaDe(fuente, atributo.start),
				tipo: 'rótulo literal',
				texto: `${atributo.name}="${literal}"`
			});
		}

		for (const clave of ['fragment', 'nodes', 'body', 'consequent', 'alternate', 'children']) {
			const hijo = nodo[clave];
			if (Array.isArray(hijo)) for (const n of hijo) recorrer(n, tecnica);
			else if (hijo) recorrer(hijo, tecnica);
		}
	}

	recorrer(nodos, false);
	return hallazgos;
}
/* eslint-enable @typescript-eslint/no-explicit-any */

// ------------------------------------------------ el otro lado: las acciones

/**
 * Los sumideros de texto de un `.ts`.
 *
 * Una acción de formulario produce tantos mensajes como la pantalla, y ahí no
 * hay marcado que recorrer. Se miran las llamadas que **terminan en los ojos de
 * alguien**, y solo esas: `formError('…')`, `toasts.error('…')`,
 * `v.add(campo, '…')`. Un literal en cualquier otro lugar de un `.ts` puede ser
 * una clave, una clase o una ruta, y perseguirlos todos convertiría la prueba en
 * ruido.
 */
const SUMIDEROS = new Map<string, number[]>([
	// nombre de la llamada → en qué posiciones va texto para una persona
	['formError', [0]],
	['v.add', [1]],
	['toasts.success', [0, 1]],
	['toasts.error', [0, 1]],
	['toasts.warning', [0, 1]],
	['toasts.info', [0, 1]]
]);

/** Una frase: tres letras seguidas y un espacio. Un identificador no lo tiene. */
const FRASE = /[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{3}[^]*\s/;

function archivosTs(carpeta: string): string[] {
	const encontrados: string[] = [];
	for (const entrada of readdirSync(carpeta, { withFileTypes: true })) {
		const ruta = join(carpeta, entrada.name);
		if (entrada.isDirectory()) encontrados.push(...archivosTs(ruta));
		else if (entrada.name.endsWith('.ts') && !entrada.name.endsWith('.test.ts')) {
			encontrados.push(ruta);
		}
	}
	return encontrados;
}

function revisarTs(archivo: string, fuente: string): Hallazgo[] {
	const hallazgos: Hallazgo[] = [];
	const sf = ts.createSourceFile(archivo, fuente, ts.ScriptTarget.Latest, true);

	function recorrer(nodo: ts.Node) {
		if (ts.isCallExpression(nodo)) {
			const nombre = nodo.expression.getText(sf);
			const posiciones = SUMIDEROS.get(nombre);
			if (posiciones) {
				for (const i of posiciones) {
					const arg = nodo.arguments[i];
					if (!arg) continue;
					const literal =
						ts.isStringLiteral(arg) || ts.isNoSubstitutionTemplateLiteral(arg)
							? arg.text
							: ts.isTemplateExpression(arg)
								? arg.head.text
								: null;
					if (literal === null || !FRASE.test(literal)) continue;
					hallazgos.push({
						archivo,
						linea: sf.getLineAndCharacterOfPosition(arg.getStart(sf)).line + 1,
						tipo: 'rótulo literal',
						texto: `${nombre}(… "${literal}" …)`
					});
				}
			}
		}
		ts.forEachChild(nodo, recorrer);
	}

	recorrer(sf);
	return hallazgos;
}

describe('ningún texto para una persona vive dentro de un componente', () => {
	const archivos = CARPETAS.flatMap((c) => archivosSvelte(join(SRC, c)));

	it('hay componentes que revisar', () => {
		// Si el recorrido se rompe y no encuentra archivos, todo lo demás pasaría
		// por vacío: es el modo en que una prueba de este tipo miente.
		expect(archivos.length).toBeGreaterThan(20);
	});

	it('ni como texto suelto ni como rótulo literal', () => {
		const hallazgos = archivos.flatMap((archivo) =>
			revisar(relative(SRC, archivo).replace(/\\/g, '/'), readFileSync(archivo, 'utf-8'))
		);

		const informe = hallazgos
			.map((h) => `  ${h.archivo}:${h.linea}  ${h.tipo}: ${JSON.stringify(h.texto)}`)
			.join('\n');

		expect(
			hallazgos,
			`Estos textos los ve una persona y no salen del catálogo:\n${informe}\n\n` +
				'Agréguelos a messages/es/<pantalla>.json y úselos con m.<clave>(). ' +
				'Si de verdad no es texto traducible —una marca, un nombre de tecla—, ' +
				'va a PERMITIDO en esta prueba, con su razón.'
		).toEqual([]);
	});
});

describe('ni en las acciones, que producen tantos mensajes como la pantalla', () => {
	const archivos = [
		...archivosTs(join(SRC, 'routes')),
		...archivosTs(join(SRC, 'lib/ui')),
		// Los adaptadores del servidor: el lector de planillas escribía sus frases
		// hasta T-804 y es el sitio donde volvería a pasar.
		...archivosTs(join(SRC, 'lib/server'))
	];

	it('hay archivos que revisar', () => {
		expect(archivos.length).toBeGreaterThan(20);
	});

	it('ningún sumidero de texto recibe una frase escrita a mano', () => {
		const hallazgos = archivos.flatMap((archivo) =>
			revisarTs(relative(SRC, archivo).replace(/\\/g, '/'), readFileSync(archivo, 'utf-8'))
		);

		const informe = hallazgos
			.map((h) => `  ${h.archivo}:${h.linea}  ${h.texto}`)
			.join('\n');

		expect(
			hallazgos,
			`Estas frases se escribieron a mano en una acción:\n${informe}\n\n` +
				'Van al catálogo igual que las de la pantalla.'
		).toEqual([]);
	});
});
