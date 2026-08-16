import { error } from '@sveltejs/kit';
import { loadSettings } from '$lib/server/settings';
import type { RequestHandler } from './$types';

/**
 * Logo del negocio.
 *
 * Se sirve como archivo y no embebido en la página porque aparece en el menú, en
 * la factura y en la vista previa: incrustarlo como data URI significaría mandar
 * la misma imagen tres veces por navegación. Acá se manda una, y el navegador la
 * guarda.
 *
 * `immutable` es seguro porque la URL lleva `?v=<sello>`: al cambiar la imagen
 * cambia el sello, la URL es otra y la caché vieja deja de usarse.
 */
export const GET: RequestHandler = async ({ locals, setHeaders }) => {
	const stored = await loadSettings(locals.token);
	if (!stored.logo) error(404, { message: 'El negocio no tiene logo configurado.' });

	let bytes: Buffer;
	try {
		bytes = Buffer.from(stored.logo.data, 'base64');
	} catch {
		error(500, { message: 'El logo guardado no se pudo decodificar.' });
	}

	setHeaders({
		'Content-Type': stored.logo.mime,
		'Content-Length': String(bytes.byteLength),
		'Cache-Control': 'public, max-age=31536000, immutable'
	});

	return new Response(new Uint8Array(bytes));
};
