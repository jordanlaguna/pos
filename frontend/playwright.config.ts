import { defineConfig, devices } from '@playwright/test';

/**
 * Flujos de punta a punta (RNF-6, capa de interfaz).
 *
 * Corren contra el **modo simulado** (`POS_MOCK=1`), no contra Docker. Es a
 * propósito: lo que estas pruebas verifican es la interfaz —que el cajero pueda
 * entrar, cobrar y que las cifras que ve sean las correctas—, y el modo
 * simulado tiene contrato idéntico al backend por regla del proyecto. Así se
 * pueden correr en una máquina recién clonada, sin levantar MySQL, y no dejan
 * ventas inventadas en ninguna base.
 *
 * Lo que sí necesita el backend de verdad son las pruebas de caracterización,
 * que viven en `backend/tests/` y hablan con FastAPI y MySQL.
 *
 * Playwright levanta y apaga el servidor solo. La primera vez hay que instalar
 * el navegador: `npx playwright install chromium`.
 */

const PORT = 4173;

export default defineConfig({
	testDir: 'tests/e2e',
	// En integración continua, una prueba que pasa al segundo intento es una
	// prueba que no sirve: se prohíbe el `.only` y no se reintenta.
	forbidOnly: !!process.env.CI,
	retries: 0,

	/*
	 * Un solo trabajador, en serie.
	 *
	 * No es prudencia: el modo simulado es **un** proceso con **una** base
	 * respaldada en un archivo, así que dos pruebas en paralelo escriben sobre lo
	 * mismo. Con tres trabajadores la suite fallaba una de cada varias corridas
	 * —siempre en un sitio distinto—, que es la peor clase de fallo: parece
	 * casualidad y esconde el problema de verdad.
	 *
	 * La suite entera tarda unos nueve segundos; no hay nada que ganar
	 * paralelizándola.
	 */
	fullyParallel: false,
	workers: 1,
	reporter: process.env.CI ? 'github' : 'list',

	use: {
		baseURL: `http://127.0.0.1:${PORT}`,
		// 127.0.0.1 y no «localhost»: en Windows, localhost resuelve primero a
		// ::1 y cada conexión paga el intento fallido antes de caer a IPv4.
		trace: 'on-first-retry',
		screenshot: 'only-on-failure'
	},

	projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],

	webServer: {
		// `--host 127.0.0.1` explícito: por omisión Vite escucha en «localhost»,
		// que en Windows se resuelve a ::1, y entonces el POS no responde en
		// 127.0.0.1 —que es donde lo busca `baseURL`—.
		command: `npm run dev -- --port ${PORT} --strictPort --host 127.0.0.1`,
		url: `http://127.0.0.1:${PORT}/login`,
		/*
		 * **Nunca se reutiliza un servidor que ya esté escuchando.**
		 *
		 * Antes esto decía `!process.env.CI`, para no pagar el arranque en cada
		 * corrida local. El precio apareció al cambiar el backend simulado: un
		 * `npm run dev` olvidado en este puerto —de horas antes— siguió sirviendo
		 * el código viejo, y la suite entera pasó en verde sin haber probado una
		 * sola línea de lo que se acababa de escribir. Una prueba que pasa contra
		 * el código de ayer es peor que no tenerla.
		 *
		 * Con esto, si el puerto está ocupado, Playwright falla y lo dice. Cuesta
		 * unos segundos por corrida y quita una forma silenciosa de mentir.
		 */
		reuseExistingServer: false,
		timeout: 120_000,
		env: {
			// Sin backend: datos de ejemplo en memoria.
			POS_MOCK: '1'
		}
	}
});
