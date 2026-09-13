import { apiSafe } from '$lib/server/api';
import { requireAdmin } from '$lib/server/auth';
import type { VatDraft } from '$lib/domain/types';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ locals, url }) => {
	requireAdmin(locals, url.pathname);

	const hoy = new Date();
	const year = Number(url.searchParams.get('year')) || hoy.getFullYear();
	const month = Number(url.searchParams.get('month')) || hoy.getMonth() + 1;

	const borrador = await apiSafe<VatDraft | null>(
		`/accounting/vat?year=${year}&month=${month}`,
		null,
		{ token: locals.token }
	);

	return { year, month, borrador };
};
