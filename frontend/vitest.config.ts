import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vitest/config';

/**
 * Pruebas de unidad del POS.
 *
 * No usa el plugin de SvelteKit a propósito: lo que se prueba acá es código
 * puro —aritmética de plata, color, fusión de configuración—, y arrastrar el
 * compilador de Svelte solo agregaría tiempo de arranque y una dependencia que
 * estas pruebas no tienen. Los componentes y los flujos se prueban con
 * Playwright, que sí levanta la aplicación de verdad.
 */
export default defineConfig({
	resolve: {
		alias: {
			$lib: fileURLToPath(new URL('./src/lib', import.meta.url))
		}
	},
	test: {
		include: ['src/**/*.test.ts'],
		environment: 'node',
		coverage: {
			provider: 'v8',
			reporter: ['text', 'json-summary'],
			/*
			 * El umbral del 100 % es regla del proyecto (RNF-6) y aplica a dominio y
			 * casos de uso. Desde T-111 esas dos carpetas existen y recogen todo lo
			 * puro: plata, color, configuración, documentos, carrito y validación.
			 */
			include: ['src/lib/domain/**/*.ts', 'src/lib/application/**/*.ts'],
			thresholds: {
				statements: 100,
				branches: 100,
				functions: 100,
				lines: 100
			}
		}
	}
});
