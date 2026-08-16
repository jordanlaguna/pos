import type { SessionUser } from '$lib/types';

declare global {
	namespace App {
		interface Error {
			message: string;
			code?: string;
		}
		interface Locals {
			/** JWT emitido por FastAPI, leído de la cookie httpOnly. */
			token: string | null;
			/** Usuario autenticado, o null si la sesión no es válida. */
			user: SessionUser | null;
		}
		interface PageData {
			user?: SessionUser | null;
		}
	}
}

export {};
