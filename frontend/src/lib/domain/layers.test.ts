import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

/**
 * La regla de dependencias del POS, comprobada (T-114).
 *
 * ```
 * domain/        puro: plata, color, configuración, documentos, carrito, tipos
 * application/   validación de formularios (corre en las acciones)
 * server/        infraestructura
 * ui/            componentes, almacenes reactivos, formato
 * ```
 *
 * `server/` no se llama `infrastructure/` a propósito. SvelteKit trata
 * `$lib/server` como especial e **impide compilar** si el código del cliente la
 * importa: es la misma frontera que se busca, pero verificada por el compilador
 * en vez de por esta prueba. Renombrarla sería cambiar una garantía por una
 * convención.
 *
 * Va como prueba y no como guion suelto por lo mismo que en el backend: un
 * guion que hay que acordarse de correr no protege nada.
 */

const LIB = fileURLToPath(new URL('..', import.meta.url));

/** Prohibido en el dominio: si algo de esto aparece, deja de ser puro. */
const FUERA_DEL_DOMINIO = [
	'svelte',
	'$app/',
	'$env/',
	'$lib/ui/',
	'$lib/server/',
	'$lib/application/'
];

function archivos(carpeta: string, ext = ['.ts']): string[] {
	const base = join(LIB, carpeta);
	const salida: string[] = [];
	const recorrer = (dir: string) => {
		for (const nombre of readdirSync(dir)) {
			const ruta = join(dir, nombre);
			if (statSync(ruta).isDirectory()) recorrer(ruta);
			else if (ext.some((e) => nombre.endsWith(e)) && !nombre.endsWith('.test.ts'))
				salida.push(ruta);
		}
	};
	recorrer(base);
	return salida;
}

/**
 * El código sin comentarios.
 *
 * Hace falta: la primera versión de esta prueba marcaba `domain/cart.ts` porque
 * su propia cabecera dice «sin `$state`». Una comprobación que se dispara con
 * el comentario que documenta la regla no comprueba la regla.
 */
function sinComentarios(fuente: string): string {
	return fuente.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
}

/** Cada módulo importado, con su línea. */
function imports(ruta: string): { modulo: string; linea: number }[] {
	const salida: { modulo: string; linea: number }[] = [];
	readFileSync(ruta, 'utf-8')
		.split('\n')
		.forEach((texto, i) => {
			const m = texto.match(/^\s*(?:import|export)\b[^'"]*from\s+['"]([^'"]+)['"]/);
			if (m) salida.push({ modulo: m[1], linea: i + 1 });
		});
	return salida;
}

describe('el dominio es puro', () => {
	const modulos = archivos('domain');

	it('hay dominio que comprobar', () => {
		// Si alguien borra la carpeta, las pruebas de abajo pasarían por vacías.
		expect(modulos.length).toBeGreaterThan(3);
	});

	it.each(modulos.map((m) => [relative(LIB, m), m]))(
		'%s no importa nada de fuera',
		(nombre, ruta) => {
			for (const { modulo, linea } of imports(ruta as string)) {
				for (const prohibido of FUERA_DEL_DOMINIO) {
					expect(
						modulo.startsWith(prohibido),
						`${nombre}:${linea} importa «${modulo}». El dominio no puede depender de Svelte, ` +
							`del entorno ni de otra capa: si para probar una regla hace falta un componente, ` +
							`la regla está en el sitio equivocado.`
					).toBe(false);
				}
			}
		}
	);

	it.each(modulos.map((m) => [relative(LIB, m), m]))(
		'%s no usa fetch ni almacenamiento del navegador',
		(nombre, ruta) => {
			const fuente = sinComentarios(readFileSync(ruta as string, 'utf-8'));
			/*
			 * Se busca el global, no cualquier aparición del nombre. `document.` a
			 * secas es el DOM; `d.document.color` es una propiedad de la
			 * configuración por omisión y no tiene nada que ver. El lookbehind es
			 * lo que separa una cosa de la otra: sin él, la comprobación marcaba
			 * `domain/settings.ts` por leer sus propios valores de fábrica.
			 */
			const globales: [string, RegExp][] = [
				['document', /(?<![\w.])document\s*\./],
				['window', /(?<![\w.])window\s*\./],
				['localStorage', /(?<![\w.])localStorage\b/],
				['sessionStorage', /(?<![\w.])sessionStorage\b/],
				['fetch', /(?<![\w.])fetch\s*\(/]
			];
			for (const [etiqueta, patron] of globales) {
				expect(patron.test(fuente), `${nombre} usa ${etiqueta}`).toBe(false);
			}
		}
	);

	it.each(modulos.map((m) => [relative(LIB, m), m]))('%s no usa runas', (nombre, ruta) => {
		const fuente = sinComentarios(readFileSync(ruta as string, 'utf-8'));
		for (const runa of ['$state', '$derived', '$effect', '$props']) {
			expect(fuente.includes(runa), `${nombre} usa ${runa}`).toBe(false);
		}
	});
});

describe('la aplicación no conoce la interfaz', () => {
	const modulos = archivos('application');

	it.each(modulos.map((m) => [relative(LIB, m), m]))(
		'%s solo importa el dominio y a sí misma',
		(nombre, ruta) => {
			for (const { modulo, linea } of imports(ruta as string)) {
				if (modulo.startsWith('.')) continue;
				if (modulo.startsWith('$lib/domain') || modulo.startsWith('$lib/application')) continue;
				if (!modulo.startsWith('$')) continue; // paquete de node
				expect.fail(
					`${nombre}:${linea} importa «${modulo}». La aplicación solo puede apoyarse en el dominio.`
				);
			}
		}
	);
});

describe('la interfaz no se salta la capa de servidor', () => {
	it('ningún componente ni almacén importa $lib/server', () => {
		/*
		 * SvelteKit ya rompe la compilación si esto pasa, así que la prueba es un
		 * cinturón sobre los tirantes. Vale la pena porque el mensaje del
		 * compilador es genérico y este dice exactamente qué archivo fue.
		 */
		for (const ruta of archivos('ui', ['.ts', '.svelte'])) {
			for (const { modulo, linea } of imports(ruta)) {
				expect(
					modulo.startsWith('$lib/server'),
					`${relative(LIB, ruta)}:${linea} importa «${modulo}» desde la interfaz.`
				).toBe(false);
			}
		}
	});
});
