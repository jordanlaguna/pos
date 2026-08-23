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

/**
 * Dónde se guarda el token de soporte mientras dura un *entrar como* (RF-8).
 *
 * La cookie de sesión pasa a llevar el token de suplantación —es el que abre las
 * pantallas de la compañía— y el de soporte tiene que quedar en algún lado para
 * poder volver al panel. Sin esto, entrar a diagnosticar significaría perder la
 * sesión de soporte y volver a escribir la contraseña al salir.
 *
 * `httpOnly` igual que la de sesión: es un token completo y ningún script del
 * navegador tiene nada que hacer con él.
 */
export const SUPPORT_COOKIE = 'ventasys_support';

/** Umbral de stock bajo para las alertas del dashboard. */
export const LOW_STOCK_THRESHOLD = Number(env.LOW_STOCK_THRESHOLD ?? 10);
