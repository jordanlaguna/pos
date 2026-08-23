import type { LayoutServerLoad } from './$types';

/**
 * Publica el usuario y el idioma a toda la app vía `$page.data`.
 *
 * El idioma ya viene resuelto en `locals` —lo puso el middleware con lo que traía
 * el token (T-809)— y se publica para que el menú pueda mostrar cuál está activo
 * (T-810). Los mensajes **no** lo necesitan: `m.x()` lo toma del contexto de la
 * petición, no de los datos de la página.
 */
export const load: LayoutServerLoad = async ({ locals }) => {
	return { user: locals.user, locale: locals.locale };
};
