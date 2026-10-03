import { apiSafe } from '$lib/server/api';
import { requireUser } from '$lib/server/auth';
import { USE_MOCK } from '$lib/server/config';
import type { FeQueue } from '$lib/domain/types';
import { loadSettings } from '$lib/server/settings';
import type { LayoutServerLoad } from './$types';

/** Todo lo que cuelga de (app) exige sesión iniciada. */
export const load: LayoutServerLoad = async ({ locals, url }) => {
	const user = requireUser(locals, url.pathname);
	const stored = await loadSettings(locals.token, user.company_id);

	// T-711: la alarma de antigüedad de la cola ante Hacienda es lo único que
	// avisa antes de que se acabe el plazo de contingencia, así que va en el
	// marco y no escondida en una pestaña. Solo para quien puede arreglarlo, y
	// con `apiSafe`: un backend anterior a F7 no tiene la ruta.
	const feQueue =
		user.role === 'admin' && stored.settings.eInvoicing.enabled
			? await apiSafe<FeQueue | null>('/fe/queue', null, { token: locals.token })
			: null;

	return {
		user,
		feQueue,
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
