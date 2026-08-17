import { beforeEach, describe, expect, it, vi } from 'vitest';

/**
 * La caché de configuración es de cada compañía (T-224).
 *
 * Esta prueba existe por un defecto concreto: la configuración se guardaba en una
 * variable de módulo, y esa variable vive en el **proceso de Node**, no en la
 * petición. Con una compañía era correcto y ahorraba una llamada por pantalla.
 * Con varias, la primera que cargara una página le prestaba su nombre, su logo,
 * su moneda y su color de acento a todas las demás durante treinta segundos.
 *
 * Es el mismo defecto que el `WHERE company_id` olvidado, solo que del otro lado
 * del BFF, y por eso se comprueba igual de en serio: dos sesiones de compañías
 * distintas contra el mismo proceso, cada una con su marca.
 *
 * Se sustituye el cliente HTTP y no el backend: lo que se prueba es la caché, y
 * meter red o Docker en el medio solo agregaría formas de fallar que no son la
 * que interesa. Contar las llamadas es además la única manera de distinguir «me
 * devolvió lo correcto» de «me devolvió lo correcto **porque** volvió a
 * preguntar», que es justo lo que la caché no debe hacer.
 */

const api = vi.hoisted(() => vi.fn());
vi.mock('./api', () => ({ api }));

const { invalidateSettings, loadSettings, saveSettings } = await import('./settings');

/** Respuesta del backend para una compañía, con su nombre de negocio propio. */
function respuestaDe(nombre: string, moneda = 'CRC') {
	return {
		data: { business: { name: nombre }, currency: { code: moneda } },
		logo: null,
		updated_at: '2026-08-16T10:00:00'
	};
}

beforeEach(() => {
	api.mockReset();
	// Cada prueba arranca con la caché de las dos compañías descartada. La caché
	// es estado de módulo —es exactamente lo que se está probando— y sin esto una
	// prueba le dejaría a la siguiente el valor de la anterior.
	invalidateSettings(1);
	invalidateSettings(2);
	invalidateSettings(0);
});

describe('caché de configuración por compañía', () => {
	it('cada compañía recibe la suya contra el mismo proceso', async () => {
		api.mockImplementation(async (_ruta: string, opciones: { token?: string }) =>
			opciones.token === 'token-a' ? respuestaDe('Negocio A') : respuestaDe('Negocio B')
		);

		const a = await loadSettings('token-a', 1);
		const b = await loadSettings('token-b', 2);

		expect(a.settings.business.name).toBe('Negocio A');
		expect(b.settings.business.name).toBe('Negocio B');
	});

	it('la compañía que cargó primero no le presta su marca a la segunda', async () => {
		// El defecto exacto: con una sola variable de módulo, la segunda llamada
		// devolvía lo de la primera sin siquiera preguntarle al backend.
		api.mockImplementation(async (_ruta: string, opciones: { token?: string }) =>
			opciones.token === 'token-a' ? respuestaDe('Negocio A', 'CRC') : respuestaDe('Negocio B', 'USD')
		);

		await loadSettings('token-a', 1);
		const b = await loadSettings('token-b', 2);

		expect(b.settings.business.name).not.toBe('Negocio A');
		expect(b.settings.currency.code).toBe('USD');
		expect(api).toHaveBeenCalledTimes(2);
	});

	it('dentro de la misma compañía sí cachea: la segunda lectura no pregunta', async () => {
		api.mockResolvedValue(respuestaDe('Negocio A'));

		await loadSettings('token-a', 1);
		await loadSettings('token-a', 1);

		expect(api).toHaveBeenCalledTimes(1);
	});

	it('invalidar una compañía no le borra la caché a la otra', async () => {
		api.mockImplementation(async (_ruta: string, opciones: { token?: string }) =>
			opciones.token === 'token-a' ? respuestaDe('Negocio A') : respuestaDe('Negocio B')
		);

		await loadSettings('token-a', 1);
		await loadSettings('token-b', 2);
		expect(api).toHaveBeenCalledTimes(2);

		invalidateSettings(1);

		// La 1 vuelve a preguntar…
		await loadSettings('token-a', 1);
		expect(api).toHaveBeenCalledTimes(3);
		// …y la 2 no, porque nadie tocó la suya.
		await loadSettings('token-b', 2);
		expect(api).toHaveBeenCalledTimes(3);
	});

	it('guardar deja lista la caché de esa compañía y solo de esa', async () => {
		api.mockImplementation(async (_ruta: string, opciones: { token?: string }) =>
			opciones.token === 'token-a' ? respuestaDe('Negocio A') : respuestaDe('Negocio B')
		);
		await loadSettings('token-b', 2);
		api.mockClear();

		api.mockResolvedValue(respuestaDe('Negocio A renombrado'));
		const guardado = await saveSettings('token-a', {} as never, undefined, 1);
		expect(guardado.settings.business.name).toBe('Negocio A renombrado');

		// La lectura siguiente de la 1 sale de la caché que dejó el guardado.
		const a = await loadSettings('token-a', 1);
		expect(a.settings.business.name).toBe('Negocio A renombrado');
		expect(api).toHaveBeenCalledTimes(1); // solo el PUT

		// Y la 2 sigue con la suya, sin haber vuelto a preguntar.
		const b = await loadSettings('token-b', 2);
		expect(b.settings.business.name).toBe('Negocio B');
		expect(api).toHaveBeenCalledTimes(1);
	});

	it('si el backend falla, cada compañía cae en los valores de fábrica por su cuenta', async () => {
		api.mockRejectedValue(new Error('backend caído'));

		const a = await loadSettings('token-a', 1);
		expect(a.settings.currency.code).toBeTruthy();

		// Que la 1 haya fallado no puede dejar a la 2 con la caché de fábrica de
		// la 1: se le pregunta al backend por ella también.
		api.mockResolvedValue(respuestaDe('Negocio B'));
		invalidateSettings(2);
		const b = await loadSettings('token-b', 2);
		expect(b.settings.business.name).toBe('Negocio B');
	});
});
