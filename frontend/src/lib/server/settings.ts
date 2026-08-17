import { api } from './api';
import {
	DEFAULT_SETTINGS,
	mergeSettings,
	type LogoSettings,
	type Settings,
	type StoredSettings
} from '$lib/domain/settings';

/**
 * Configuración del negocio, del lado del servidor.
 *
 * La necesita cada carga de página: sin ella no se sabe con qué símbolo mostrar
 * un monto. Pedirla al backend en cada navegación sería una llamada de red por
 * pantalla para leer una fila que cambia una vez al mes, así que se guarda en
 * memoria por un rato.
 *
 * La caché tiene dos formas de vencer. Una es el tiempo, que cubre el caso de
 * varias cajas contra el mismo backend: si el dueño cambia la moneda desde una,
 * las demás se enteran en menos de un minuto. La otra es explícita, al guardar
 * desde esta misma instancia, para que quien acaba de tocar el botón vea el
 * cambio de inmediato y no dude de si se guardó.
 *
 * **Es una caché por compañía** (T-224). Era una variable de módulo, y esa
 * variable vive en el proceso de Node, no en la petición: con una compañía era
 * correcto y ahorraba una llamada por pantalla, pero con varias, la primera que
 * cargara una página le prestaba su nombre, su logo, su moneda y su color de
 * acento a todas las demás durante treinta segundos. `invalidateSettings` tenía
 * el mismo problema al revés: quien guardaba le borraba la caché a todos.
 *
 * Es el mismo defecto que el `WHERE company_id` olvidado, solo que del otro lado
 * del BFF, y por eso se arregla en la misma fase.
 */

const TTL_MS = 30_000;

interface Entrada {
	value: StoredSettings;
	at: number;
}

const cache = new Map<number, Entrada>();

/**
 * Compañía de una sesión sin compañía.
 *
 * Solo la usan las pantallas anteriores a elegir —el login lee la marca para
 * pintar el logo— y su configuración es la de fábrica. No se mezcla con ninguna
 * compañía real porque ninguna tiene el id 0.
 */
const SIN_COMPANIA = 0;

/** El POS sigue funcionando contra un backend sin el patch: sin fila, hay omisiones. */
const FALLBACK: StoredSettings = {
	settings: DEFAULT_SETTINGS,
	logo: null,
	updated_at: null,
	logo_version: '0'
};

interface SettingsPayload {
	data?: unknown;
	logo?: LogoSettings | null;
	updated_at?: string | null;
}

/**
 * Sello de versión del logo.
 *
 * Cambia cuando se guarda la configuración, que es cuando puede haber cambiado
 * la imagen. Se usa en `/marca/logo?v=…` para poder cachearla un año en el
 * navegador sin que quede pegada la vieja.
 */
function logoVersion(payload: SettingsPayload): string {
	if (!payload.logo?.data) return '0';
	const stamp = payload.updated_at ?? '';
	return `${stamp.replace(/\D/g, '').slice(0, 14) || '0'}-${payload.logo.data.length}`;
}

export async function loadSettings(
	token: string | null | undefined,
	companyId: number | null | undefined = SIN_COMPANIA
): Promise<StoredSettings> {
	const clave = companyId ?? SIN_COMPANIA;
	const guardada = cache.get(clave);
	if (guardada && Date.now() - guardada.at < TTL_MS) return guardada.value;

	try {
		const payload = await api<SettingsPayload>('/settings/', { token });
		const value: StoredSettings = {
			settings: mergeSettings(payload.data),
			logo: payload.logo ?? null,
			updated_at: payload.updated_at ?? null,
			logo_version: logoVersion(payload)
		};
		cache.set(clave, { value, at: Date.now() });
		return value;
	} catch {
		/*
		 * Que la configuración no cargue no puede tumbar el POS. Se devuelven los
		 * valores de fábrica y se cachean un momento para no reintentar contra un
		 * backend caído en cada navegación.
		 */
		cache.set(clave, { value: FALLBACK, at: Date.now() });
		return FALLBACK;
	}
}

/**
 * Descarta la caché de UNA compañía. Se llama después de guardar.
 *
 * Recibe cuál a propósito: sin el parámetro, guardar la configuración de un
 * negocio obligaba a todos los demás a volver a pedirla al backend, y en un
 * despliegue con muchas compañías eso convierte cada guardado ajeno en una
 * ráfaga de llamadas.
 */
export function invalidateSettings(companyId: number | null | undefined): void {
	cache.delete(companyId ?? SIN_COMPANIA);
}

/**
 * Guarda y deja la caché lista con lo que respondió el backend.
 * `logo === undefined` conserva el que había; `null` lo borra.
 */
export async function saveSettings(
	token: string | null | undefined,
	settings: Settings,
	logo: LogoSettings | null | undefined,
	companyId: number | null | undefined = SIN_COMPANIA
): Promise<StoredSettings> {
	const payload = await api<SettingsPayload>('/settings/', {
		method: 'PUT',
		token,
		body: {
			data: settings,
			logo: logo ?? null,
			keep_logo: logo === undefined
		}
	});

	const value: StoredSettings = {
		settings: mergeSettings(payload.data),
		logo: payload.logo ?? null,
		updated_at: payload.updated_at ?? null,
		logo_version: logoVersion(payload)
	};
	cache.set(companyId ?? SIN_COMPANIA, { value, at: Date.now() });
	return value;
}
