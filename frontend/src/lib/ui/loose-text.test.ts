import { readFileSync, readdirSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { parse } from 'svelte/compiler';
import ts from 'typescript';

/**
 * Ningún texto que vea una persona se escribe fuera de la interfaz (T-812,
 * T-816).
 *
 * Es la red que impide que los catálogos se queden atrás. Sin ella, la próxima
 * pantalla se escribe con la cadena adentro —cuesta lo mismo en el momento— y
 * nadie se entera hasta que alguien pide el POS en portugués. Cada pantalla así
 * es una pantalla que hay que volver a abrir.
 *
 * Vigila **tres** sitios, que son los tres donde apareció el problema: el
 * marcado, los sumideros de texto de las acciones, y los literales del dominio y
 * la aplicación (RN-30). El tercero se agregó al reescribir RN-30: hasta
 * entonces la regla ahí la sostenía una decisión y no una prueba, y `layers.ts`
 * no la habría visto —una frase suelta no importa nada—.
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
	tipo: 'texto suelto' | 'rótulo literal' | 'frase en una capa de adentro';
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

		// `fallback` es el `{:else}` de un `{#each}`, y `pending`/`then`/`catch`
		// las tres ramas de un `{#await}`. Faltaban, así que todo lo que
		// estuviera dentro era invisible: ahí vivía el «Sin datos.» de
		// `SalesTrendChart`, mientras su gemelo `BarListChart` usaba la clave del
		// catálogo para lo mismo.
		for (const clave of [
			'fragment',
			'nodes',
			'body',
			'consequent',
			'alternate',
			'children',
			'fallback',
			'pending',
			'then',
			'catch'
		]) {
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

/**
 * Propiedades que llegan a los ojos de alguien **esté donde esté el objeto**.
 *
 * Antes esto se declaraba por llamada —`error(404, { message: '…' })`, posición
 * 1—, y por eso no veía la forma más usada de todas: `return { success: '…' }`
 * desde una acción, que no es una llamada a nada. `lib/ui/forms.ts` lee
 * `data.success` y `data.message` del resultado de la acción y los pasa a
 * `toasts.success()` y `toasts.error()`; ese es el canal, y no importa por qué
 * función pasó el objeto antes.
 *
 * Es la misma lección que ya estaba escrita acá y no se había aplicado del todo:
 * **un sumidero se declara por dónde entra el texto, no por cómo se llama la
 * función**. Declarado por propiedad, cubre de una vez `return { success }`,
 * `return { message }`, `fail(400, { message })` y `error(404, { message })`
 * —los cuatro caminos, incluidos los que nadie ha escrito todavía—.
 *
 * Dejó pasar los cuatro textos de T-411 y el `Movimiento de ${type} registrado`
 * de T-914.
 */
const PROPIEDADES_QUE_SE_VEN = ['success', 'message'];

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

/** El texto de un literal, si el nodo lo es. Una expresión no cuenta: ya pasó por el catálogo. */
function textoLiteral(nodo: ts.Node): string | null {
	if (ts.isStringLiteral(nodo) || ts.isNoSubstitutionTemplateLiteral(nodo)) return nodo.text;
	if (ts.isTemplateExpression(nodo)) return nodo.head.text;
	return null;
}

function revisarTs(archivo: string, fuente: string): Hallazgo[] {
	const hallazgos: Hallazgo[] = [];
	const sf = ts.createSourceFile(archivo, fuente, ts.ScriptTarget.Latest, true);

	const anotar = (nodo: ts.Node, comoSeLlamo: string) =>
		hallazgos.push({
			archivo,
			linea: sf.getLineAndCharacterOfPosition(nodo.getStart(sf)).line + 1,
			tipo: 'rótulo literal',
			texto: comoSeLlamo
		});

	function recorrer(nodo: ts.Node) {
		if (ts.isCallExpression(nodo)) {
			const nombre = nodo.expression.getText(sf);

			for (const i of SUMIDEROS.get(nombre) ?? []) {
				const arg = nodo.arguments[i];
				if (!arg) continue;
				const literal = textoLiteral(arg);
				if (literal === null || !FRASE.test(literal)) continue;
				anotar(arg, `${nombre}(… "${literal}" …)`);
			}

		}

		// Fuera del `if`: la propiedad se busca en **todo** objeto literal, no
		// solo en los que son argumento de una llamada. Es lo que hace que se
		// vea `return { success: '…' }`, que es por donde salen casi todos los
		// avisos de éxito del POS.
		if (ts.isObjectLiteralExpression(nodo)) {
			for (const prop of nodo.properties) {
				if (!ts.isPropertyAssignment(prop)) continue;
				const clave = prop.name.getText(sf).replace(/['"]/g, '');
				if (!PROPIEDADES_QUE_SE_VEN.includes(clave)) continue;
				const literal = textoLiteral(prop.initializer);
				if (literal === null || !FRASE.test(literal)) continue;
				anotar(prop, `{ ${clave}: "${literal}" }`);
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

// ----------------------------- el tercero: el dominio y la aplicación (RN-30)

/**
 * Las capas de adentro no escriben texto para una persona.
 *
 * Acá no hay sumidero que vigilar: `formError` y `toasts` viven en `ui/`, que el
 * dominio no puede importar, así que una prueba de llamadas no encontraría nada
 * nunca —y una prueba que no puede fallar es peor que ninguna, porque tranquiliza
 * igual—. Lo que hay que buscar es el literal mismo: una frase devuelta como
 * valor, que es la forma en que esto se cuela (`documentTitle()` devolvía
 * «Factura electrónica», `CURRENCIES[].label` decía «Colón costarricense», los
 * lectores de archivos lanzaban `new Error('No se pudo leer el CSV…')`).
 *
 * **Dos disparadores, y el segundo importa.** Una frase es tres letras y un
 * espacio; eso deja fuera los códigos (`cart_out_of_stock`) y las claves, que es
 * casi todo lo que hay legítimamente acá. Pero deja pasar la palabra sola:
 * «Efectivo» no tiene espacio. Por eso también dispara la tilde y los signos de
 * apertura —«Cédula», «Anulación», «¿…?»—, que en un identificador o una clave
 * no aparecen. Queda un hueco conocido: una palabra sola y sin tilde
 * («Pendiente») pasa. No se cierra con esta forma de prueba; se cierra con la
 * revisión del diff.
 */
const CAPAS_DE_ADENTRO = ['lib/domain', 'lib/application'];

/** Español visible: una tilde o un signo de apertura. Un código no los lleva. */
const ESPANOL = /[ÁÉÍÓÚÜÑáéíóúüñ¡¿]/;

/**
 * Literales que son **dato** y no texto para una persona, con su razón.
 *
 * Igual que `PERMITIDO`: cada entrada lleva la suya, porque una lista de
 * excepciones sin razones es donde se esconde lo que molesta. Las dos que había
 * y no eran dato —el agradecimiento del tiquete y la leyenda legal, que venían
 * de fábrica en español y se imprimían— no están acá: se vaciaron, y el idioma
 * lo pone quien da de alta la compañía (T-304).
 */
const DATOS = new Map<string, string>([
	[
		'Tarjeta de crédito',
		'valor que se guarda en sales.payment_method y se compara en los reportes y ' +
			'las tres plantillas; traducirlo haría que una venta cobrada en portugués ' +
			'dejara de contarse como tarjeta. paymentLabel() traduce cómo se muestra'
	],
	['Transferencia bancaria', 'ídem: valor de sales.payment_method'],
	['Pago móvil', 'ídem: valor de sales.payment_method'],
	[
		'Cédula física',
		'nombre legal del documento en Costa Rica: no se traduce a portugués, se ' +
			'cambia por la lista de otro país'
	],
	['Cédula jurídica', 'ídem: nombre legal del documento en Costa Rica']
]);

function revisarLiterales(archivo: string, fuente: string): Hallazgo[] {
	const hallazgos: Hallazgo[] = [];
	const sf = ts.createSourceFile(archivo, fuente, ts.ScriptTarget.Latest, true);

	function recorrer(nodo: ts.Node) {
		const literal = ts.isStringLiteral(nodo) || ts.isNoSubstitutionTemplateLiteral(nodo);
		const texto = literal
			? nodo.text
			: ts.isTemplateExpression(nodo)
				? nodo.head.text
				: null;

		if (texto !== null && (FRASE.test(texto) || ESPANOL.test(texto)) && !DATOS.has(texto)) {
			hallazgos.push({
				archivo,
				linea: sf.getLineAndCharacterOfPosition(nodo.getStart(sf)).line + 1,
				tipo: 'frase en una capa de adentro',
				texto
			});
		}

		ts.forEachChild(nodo, recorrer);
	}

	recorrer(sf);
	return hallazgos;
}

describe('ni en las plantillas de documento, que hablan otro idioma (RN-29)', () => {
	/*
	 * El documento se emite en el idioma de la **compañía** y no en el de la
	 * pantalla: la factura es para el cliente y para Hacienda. Las plantillas
	 * reciben el diccionario ya resuelto (`documentLabels`), así que si alguna
	 * importa el catálogo es porque escribió `m.doc_total()` —que compila, se ve
	 * bien en español, y sale en el idioma del cajero el día que haya dos—.
	 *
	 * Es una prueba de importaciones y no de texto porque el error no es escribir
	 * una cadena: es pedir el mensaje sin decir en qué idioma.
	 */
	const PLANTILLAS = ['Tiquete.svelte', 'FacturaClasica.svelte', 'FacturaModerna.svelte'];

	it.each(PLANTILLAS)('%s no importa $lib/paraglide', (nombre) => {
		const fuente = readFileSync(join(SRC, 'lib/ui/components/documents', nombre), 'utf-8');
		const importa = /from\s+['"]\$lib\/paraglide/.test(fuente);
		expect(
			importa,
			`${nombre} importa el catálogo. El texto del documento sale de ` +
				'`documentLabels(docLocale)`, que es lo único que sabe en qué idioma se ' +
				'emite (RN-29).'
		).toBe(false);
	});
});

describe('ni en el dominio ni en la aplicación, que no pueden traducir', () => {
	const archivos = CAPAS_DE_ADENTRO.flatMap((c) => archivosTs(join(SRC, c)));

	it('hay módulos que revisar', () => {
		expect(archivos.length).toBeGreaterThan(5);
	});

	it('ningún literal tiene forma de frase en español', () => {
		const hallazgos = archivos.flatMap((archivo) =>
			revisarLiterales(relative(SRC, archivo).replace(/\\/g, '/'), readFileSync(archivo, 'utf-8'))
		);

		const informe = hallazgos
			.map((h) => `  ${h.archivo}:${h.linea}  ${JSON.stringify(h.texto)}`)
			.join('\n');

		expect(
			hallazgos,
			`Estas frases están en una capa que no puede traducir (RN-30):\n${informe}\n\n` +
				'El dominio y la aplicación devuelven un código y los datos; la frase la ' +
				'arma la interfaz —$lib/ui/messages.ts para los «no», el catálogo para los ' +
				'rótulos—. Si de verdad es un dato que se guarda o se compara, va a DATOS ' +
				'en esta prueba, con su razón.'
		).toEqual([]);
	});
});
