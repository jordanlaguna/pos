import type { PendingSession, SessionUser, SupportUser } from '$lib/domain/types';

declare global {
	namespace App {
		/**
		 * Un error de página: un código, y una frase solo si la escribió la
		 * interfaz.
		 *
		 * `message` es opcional desde T-816 porque `$lib/server` no puede escribir
		 * frases (RN-30): `requireAdmin` lanza `{ code: 'admin_only' }` y la frase
		 * la arma `+error.svelte`, que sí es interfaz. Las rutas —que también son
		 * interfaz— pueden seguir mandando `message` ya resuelto del catálogo.
		 */
		interface Error {
			message?: string;
			code?: string;
			/**
			 * Dato del código, cuando la frase lo necesita. Hoy lo usa
			 * `subscription_read_only`, que dice en qué estado quedó la suscripción
			 * ('vencida', 'suspendida', 'cancelada'): sin eso, el aviso no puede
			 * decirle al dueño qué tiene que arreglar.
			 */
			state?: string;
			/**
			 * El otro dato con dueño: cuál módulo pidió el plan y no tiene
			 * (`module_not_in_plan`, RN-49). Va aparte de `state` y no en un saco
			 * genérico porque son dos códigos distintos y cada frase necesita lo
			 * suyo; un `datos?: Record<string, unknown>` haría que agregar un
			 * código nuevo no obligue a pensar en qué acompaña a su frase.
			 */
			module?: string;
		}
		interface Locals {
			/** JWT emitido por FastAPI, leído de la cookie httpOnly. */
			token: string | null;
			/** Usuario autenticado **con compañía**, o null si la sesión no es válida. */
			user: SessionUser | null;
			/**
			 * Autenticado pero sin compañía elegida todavía.
			 *
			 * Existe desde F2 y es el único estado en que `user` es null sin que la
			 * persona sea un extraño: probó su contraseña y le falta decir dónde
			 * entra. Solo `/compania` lo acepta.
			 */
			pending: PendingSession | null;
			/**
			 * Sesión del panel de soporte, **sin compañía** (F3, RN-4).
			 *
			 * Es el tercer estado en que `user` es null sin que haya nada mal: alguien
			 * que administra la plataforma y no pertenece a ningún negocio. Solo
			 * `/admin` lo acepta; el POS le responde 403 (T-302).
			 */
			support: SupportUser | null;
			/**
			 * Idioma de esta petición, resuelto por el backend y traído en el token
			 * (T-809). Lo pone `paraglideMiddleware` en `hooks.server.ts`; acá está
			 * para que un `load` pueda publicarlo sin volver a leer el JWT.
			 */
			locale: string;
		}
		interface PageData {
			user?: SessionUser | null;
			support?: SupportUser | null;
			locale?: string;
		}
	}
}

export {};
