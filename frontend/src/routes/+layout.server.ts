import type { LayoutServerLoad } from './$types';

/** Publica el usuario a toda la app vía `$page.data.user`. */
export const load: LayoutServerLoad = async ({ locals }) => {
	return { user: locals.user };
};
