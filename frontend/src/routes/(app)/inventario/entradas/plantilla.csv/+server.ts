import { error } from '@sveltejs/kit';
import { TEMPLATE_CSV } from '$lib/server/import/spreadsheet';
import type { RequestHandler } from './$types';

/** Plantilla de ejemplo para la carga por planilla. */
export const GET: RequestHandler = async ({ locals }) => {
	if (!locals.user) error(401, { message: 'Sesión requerida.' });

	// El BOM hace que Excel abra el archivo en UTF-8 y no rompa las tildes.
	return new Response('﻿' + TEMPLATE_CSV, {
		headers: {
			'content-type': 'text/csv; charset=utf-8',
			'content-disposition': 'attachment; filename="plantilla-entrada-inventario.csv"'
		}
	});
};
