import { requireUser } from '$lib/server/auth';
import { USE_MOCK } from '$lib/server/config';
import { loadSettings } from '$lib/server/settings';
import type { LayoutServerLoad } from './$types';

/** Todo lo que cuelga de (app) exige sesión iniciada. */
export const load: LayoutServerLoad = async ({ locals, url }) => {
	const user = requireUser(locals, url.pathname);
	const stored = await loadSettings(locals.token, user.company_id);

	return {
		user,
		demo: USE_MOCK,
		settings: stored.settings,
		/*
		 * El logo NO viaja acá. Son cientos de kilobytes que se repetirían en la
		 * carga de cada pantalla; se sirve por `/marca/logo`, que el navegador sí
		 * puede cachear. Lo único que viaja es el sello de versión, que cambia
		 * cuando cambia la imagen y sirve para invalidar esa caché.
		 */
		logoVersion: stored.logo ? stored.logo_version : null
	};
};
