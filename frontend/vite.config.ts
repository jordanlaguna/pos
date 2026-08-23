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
		 * `strategy: ['custom-session', 'cookie', 'baseLocale']`, y no la de fábrica
		 * (`['cookie', 'globalVariable', 'baseLocale']`):
		 *
		 * - **`custom-session`** es el idioma del token, que lo resolvió el backend
		 *   (T-809). Va primero porque es la única fuente que el cliente no puede
		 *   elegir. Se registra en `hooks.server.ts`.
		 * - **`cookie`** es el espejo para el navegador: después de hidratar no hay
		 *   token que leer del lado del cliente, porque la cookie de sesión es
		 *   httpOnly. La escribe el servidor en cada respuesta.
		 * - **`globalVariable` no está**, y es lo importante: guarda el idioma en
		 *   una variable de módulo, que en el servidor vive en el proceso de Node y
		 *   no en la petición. Con varias compañías atendidas por el mismo proceso,
		 *   la primera que cargue una página le presta su idioma a las demás. Es el
		 *   defecto 17 otra vez, el de la caché de configuración.
		 * - `url` tampoco: el idioma no es parte de la dirección de una pantalla
		 *   del POS, y meterlo obligaría a duplicar todas las rutas.
		 *
		 * En el servidor el idioma entra por `paraglideMiddleware`, que lo guarda
		 * en AsyncLocalStorage y por eso sí es por petición.
		 *
		 * **La misma lista está en el guion `i18n` de `package.json`** y tiene que
		 * estarlo: `svelte-check` no pasa por Vite, así que compila con lo que le
		 * diga la línea de comandos. Cuando divergían, la comprobación de tipos
		 * miraba un runtime con otras estrategias que el que se despliega.
		 */
		paraglideVitePlugin({
			project: './project.inlang',
			outdir: './src/lib/paraglide',
			strategy: ['custom-session', 'cookie', 'baseLocale']
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
