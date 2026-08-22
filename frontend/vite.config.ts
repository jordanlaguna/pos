import { paraglideVitePlugin } from '@inlang/paraglide-js';
import adapter from '@sveltejs/adapter-node';
import { sveltekit } from '@sveltejs/kit/vite';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [
		/*
		 * Multi-idioma (F8, T-801). Los catálogos viven en `messages/*.json` y el
		 * compilador los convierte en funciones tipadas en `src/lib/paraglide/`,
		 * que no se versiona: la escribe la build.
		 *
		 * `strategy: ['baseLocale']` a propósito, y no la de fábrica
		 * (`['cookie', 'globalVariable', 'baseLocale']`):
		 *
		 * - `globalVariable` guarda el idioma en una variable de módulo, que en el
		 *   servidor vive en el proceso de Node y no en la petición. Con varias
		 *   compañías atendidas por el mismo proceso, la primera que cargue una
		 *   página le presta su idioma a las demás. Es el defecto 17 otra vez, el
		 *   de la caché de configuración.
		 * - `cookie` y `url` sobran: el idioma efectivo se resuelve en el servidor
		 *   —lo de la persona, si no lo de la compañía, si no `es`— y viaja en el
		 *   JWT (plan §8.4). No es algo que el navegador elija.
		 *
		 * Mientras T-809 no ponga el `locale` en el token, todo sale en español.
		 * Cuando lo haga, entra por `paraglideMiddleware`, que usa
		 * AsyncLocalStorage y por eso sí es por petición.
		 */
		paraglideVitePlugin({
			project: './project.inlang',
			outdir: './src/lib/paraglide',
			strategy: ['baseLocale']
		}),
		tailwindcss(),
		sveltekit({
			compilerOptions: {
				// Force runes mode for the project, except for libraries. Can be removed in svelte 6.
				runes: ({ filename }) =>
					filename.split(/[/\\]/).includes('node_modules') ? undefined : true
			},
			adapter: adapter()
		})
	]
});
