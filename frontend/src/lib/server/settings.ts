import { api } from './api';
import {
	DEFAULT_SETTINGS,
	mergeSettings,
	type LogoSettings,
	type Settings,
	type StoredSettings
} from '$lib/settings';

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
 */

const TTL_MS = 30_000;

let cache: { value: StoredSettings; at: number } | null = null;

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

export async function loadSettings(token: string | null | undefined): Promise<StoredSettings> {
	if (cache && Date.now() - cache.at < TTL_MS) return cache.value;

	try {
		const payload = await api<SettingsPayload>('/settings/', { token });
		const value: StoredSettings = {
			settings: mergeSettings(payload.data),
			logo: payload.logo ?? null,
			updated_at: payload.updated_at ?? null,
			logo_version: logoVersion(payload)
		};
		cache = { value, at: Date.now() };
		return value;
	} catch {
		/*
		 * Que la configuración no cargue no puede tumbar el POS. Se devuelven los
		 * valores de fábrica y se cachean un momento para no reintentar contra un
		 * backend caído en cada navegación.
		 */
		cache = { value: FALLBACK, at: Date.now() };
		return FALLBACK;
	}
}

/** Descarta la caché. Se llama después de guardar. */
export function invalidateSettings(): void {
	cache = null;
}

/**
 * Guarda y deja la caché lista con lo que respondió el backend.
 * `logo === undefined` conserva el que había; `null` lo borra.
 */
export async function saveSettings(
	token: string | null | undefined,
	settings: Settings,
	logo: LogoSettings | null | undefined
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
	cache = { value, at: Date.now() };
	return value;
}
