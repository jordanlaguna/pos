import { env } from '$env/dynamic/private';

/**
 * Configuración del servidor. Todo se lee de variables de entorno en tiempo de
 * ejecución (no de build), así que apuntar el POS a otra VM es cambiar el .env
 * y reiniciar — no recompilar.
 */

/** URL base del FastAPI. La del WinForms original era http://localhost:8000. */
export const API_BASE_URL = (env.API_BASE_URL ?? 'http://localhost:8000').replace(/\/+$/, '');

/**
 * Modo mock. Con `POS_MOCK=1` el POS no toca la red: sirve un backend en memoria
 * con datos de ejemplo. Sirve para desarrollar la interfaz sin la VM levantada y
 * para que cualquiera pueda probar el sistema recién clonado.
 */
export const USE_MOCK = env.POS_MOCK === '1' || env.POS_MOCK === 'true';

/** Timeout por petición. Un backend colgado no debe congelar la caja. */
export const API_TIMEOUT_MS = Number(env.API_TIMEOUT_MS ?? 8000);

/** Nombre de la cookie donde vive el JWT. */
export const SESSION_COOKIE = 'ventasys_session';

/** Umbral de stock bajo para las alertas del dashboard. */
export const LOW_STOCK_THRESHOLD = Number(env.LOW_STOCK_THRESHOLD ?? 10);
