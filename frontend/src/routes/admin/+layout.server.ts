import { requireSoporte } from '$lib/server/auth';
import { USE_MOCK } from '$lib/server/config';
import type { LayoutServerLoad } from './$types';

/**
 * Todo lo que cuelga de `/admin` exige sesión de **soporte** (T-302).
 *
 * Es el espejo de `(app)/+layout.server.ts`, y las dos puertas se cierran en los
 * dos sentidos: un usuario de compañía recibe 403 acá y soporte recibe 403 en las
 * pantallas del POS. No es simetría por gusto —son dos productos distintos
 * corriendo en el mismo despliegue, y lo único que los separa es esta línea—.
 *
 * `/admin` y no un grupo `(admin)`: el prefijo tiene que verse en la barra de
 * direcciones. Quien atiende soporte trabaja con las dos aplicaciones abiertas y
 * necesita saber en cuál está sin mirar el contenido.
 */
export const load: LayoutServerLoad = async ({ locals, url }) => {
	const support = requireSoporte(locals, url.pathname);
	return { support, demo: USE_MOCK };
};
