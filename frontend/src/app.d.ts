import type { PendingSession, SessionUser } from '$lib/domain/types';

declare global {
	namespace App {
		interface Error {
			message: string;
			code?: string;
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
		}
		interface PageData {
			user?: SessionUser | null;
		}
	}
}

export {};
