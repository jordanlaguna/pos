import { error } from '@sveltejs/kit';
import { requireAdmin } from '$lib/server/auth';
import { HOJAS, plantillaCsv, type Hoja } from '$lib/server/import/payroll';
import type { RequestHandler } from './$types';

/** La plantilla de una hoja (RF-86), con los encabezados que la lectura reconoce. */
export const GET: RequestHandler = async ({ locals, url, params }) => {
	requireAdmin(locals, url.pathname);
	if (!(HOJAS as string[]).includes(params.hoja)) error(404, { code: 'not_found' });
	const hoja = params.hoja as Hoja;
	// El BOM hace que Excel abra el archivo en UTF-8 y no rompa las tildes.
	return new Response('﻿' + plantillaCsv(hoja), {
		headers: {
			'content-type': 'text/csv; charset=utf-8',
			'content-disposition': `attachment; filename="plantilla-planilla-${hoja}.csv"`
		}
	});
};
