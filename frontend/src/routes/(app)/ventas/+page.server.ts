import { fail, redirect } from '@sveltejs/kit';
import { api, apiSafe, toMessage } from '$lib/server/api';
import { requireUser } from '$lib/server/auth';
import { loadSettings } from '$lib/server/settings';
import { prepareSale } from '$lib/application/checkout';
import { Validator } from '$lib/application/validation';
import { PAYMENT_METHODS, type CashSession, type Category, type Client, type Product } from '$lib/domain/types';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ locals, url }) => {
	const user = requireUser(locals, url.pathname);
	const token = locals.token;

	// El catálogo entero viaja una vez y la búsqueda se resuelve en el navegador:
	// el escáner debe responder al instante, sin una ida al servidor por tecla.
	const [products, categories, clients, cashSession] = await Promise.all([
		api<Product[]>('/products/products_list', { token }),
		apiSafe<Category[]>('/categories/categories_list', [], { token }),
		apiSafe<Client[]>('/clients/clients_list', [], { token }),
		apiSafe<CashSession | null>('/cash/current', null, {
			token,
			query: { user_id: user.id_user }
		})
	]);

	return { products, categories, clients, cashSession };
};

export const actions: Actions = {
	/** Registra la venta. Recalcula los totales en el servidor: el navegador no decide precios. */
	cobrar: async ({ request, locals, url }) => {
		const user = requireUser(locals, url.pathname);
		const form = await request.formData();
		const v = new Validator(form);

		const paymentMethod = v.oneOf('payment_method', 'El método de pago', PAYMENT_METHODS);
		const cashReceived = v.decimal('cash_received', 'El monto recibido', { min: 0 });
		const clientRaw = String(form.get('client_id') ?? '').trim();
		const clientId = clientRaw ? Number(clientRaw) : null;

		let lines: { id_product: number; quantity: number }[];
		try {
			lines = JSON.parse(String(form.get('lines') ?? '[]'));
		} catch {
			return fail(400, { message: 'No se pudo leer el detalle de la venta.' });
		}
		if (!Array.isArray(lines) || lines.length === 0) {
			return fail(400, { message: 'Agregá al menos un producto antes de cobrar.' });
		}
		if (!v.ok) return fail(400, { message: Object.values(v.errors)[0], errors: v.errors });

		const token = locals.token;

		// Los precios se releen del backend: si el navegador manda otro, no importa.
		let catalog: Product[];
		try {
			catalog = await api<Product[]>('/products/products_list', { token });
		} catch (error) {
			return fail(502, { message: toMessage(error) });
		}

		/*
		 * La tasa se lee acá y no del estado del módulo de dinero: esto corre en una
		 * acción del servidor, donde no se ha renderizado ningún componente y por lo
		 * tanto nadie llamó a `configureMoney`. La plata se calcula con la tasa que
		 * el servidor acaba de leer, no con la que quedó de la última pantalla.
		 */
		const { settings } = await loadSettings(token, user.company_id);

		// La decisión entera vive en la capa de aplicación y es pura; acá solo se
		// transporta lo que devuelve (T-112).
		const preparada = prepareSale(
			{
				lines,
				paymentMethod,
				cashReceived,
				clientId,
				saleNumber: String(form.get('sale_number') ?? '').trim(),
				userId: user.id_user
			},
			catalog,
			settings.tax.rate,
			new Date()
		);

		if (!preparada.ok) {
			return fail(400, {
				message: preparada.message,
				...(preparada.field ? { errors: { [preparada.field]: 'Monto insuficiente.' } } : {})
			});
		}

		let saleId: number;
		try {
			const result = await api<{ message: string; id_sale: number }>('/sales/add_sale', {
				method: 'POST',
				token,
				body: preparada.payload
			});
			saleId = result.id_sale;
		} catch (error) {
			return fail(400, { message: toMessage(error) });
		}

		redirect(303, `/facturas/${saleId}?nueva=1`);
	},

	/** Abre la caja sin salir de la pantalla de ventas. */
	abrirCaja: async ({ request, locals, url }) => {
		const user = requireUser(locals, url.pathname);
		const form = await request.formData();
		const v = new Validator(form);
		const openingAmount = v.decimal('opening_amount', 'El monto de apertura', { min: 0 });
		if (!v.ok) return fail(400, { message: Object.values(v.errors)[0] });

		try {
			await api<CashSession>('/cash/open', {
				method: 'POST',
				token: locals.token,
				body: { user_id: user.id_user, opening_amount: openingAmount }
			});
		} catch (error) {
			return fail(400, { message: toMessage(error) });
		}

		return { opened: true };
	}
};
