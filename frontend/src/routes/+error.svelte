<script lang="ts">
	import { page } from '$app/state';
	import Icon from '$lib/ui/components/Icon.svelte';
	import { m } from '$lib/paraglide/messages.js';

	const isForbidden = $derived(page.status === 403);
	const isNotFound = $derived(page.status === 404);

	/*
	 * La frase se arma acá y no donde se lanzó el error (RN-30): `requireAdmin`
	 * vive en `$lib/server`, que no sabe en qué idioma está la pantalla, así que
	 * manda un código. Una ruta —que sí es interfaz— puede mandar el `message` ya
	 * resuelto del catálogo, y entonces se usa ese.
	 *
	 * Los códigos son los mismos que usa el backend para lo mismo, así que se
	 * reusan sus claves: `api_support_only` dice exactamente lo que hay que decir
	 * cuando un administrador de compañía toca el panel, y tenerlo dos veces
	 * sería tenerlo distinto.
	 */
	const detalle = $derived.by(() => {
		switch (page.error?.code) {
			case 'admin_only':
				return m.error_admin_only();
			case 'support_only':
				return m.api_support_only();
			case 'no_company_in_token':
				return m.api_no_company_in_token();
			case 'impersonation_read_only':
				return m.api_impersonation_read_only();
			case 'subscription_read_only':
				return m.api_subscription_read_only({ state: page.error?.state ?? '' });
			case 'company_not_found':
				return m.api_company_not_found();
			default:
				return page.error?.message ?? m.error_unexpected();
		}
	});

	/*
	 * A dónde mandar a quien chocó con el error.
	 *
	 * «Ir a ventas» era el único botón, y con F3 dejó de servir en tres casos:
	 * soporte no puede entrar a ventas, un cliente con la suscripción vencida
	 * tampoco, y quien está de visita en una compañía va a volver al panel. Un
	 * botón que devuelve al mismo 403 es peor que no tener botón.
	 */
	const destino = $derived.by(() => {
		switch (page.error?.code) {
			case 'no_company_in_token':
				return { href: '/admin', label: m.error_go_to_panel(), icon: 'bolt' as const };
			case 'subscription_read_only':
			case 'impersonation_read_only':
				return { href: '/dashboard', label: m.error_go_to_dashboard(), icon: 'chart' as const };
			default:
				return { href: '/ventas', label: m.error_go_to_sales(), icon: 'cart' as const };
		}
	});
</script>

<svelte:head><title>{m.error_tab_title({ status: page.status })} · VentaSys</title></svelte:head>

<main class="flex min-h-full items-center justify-center p-6">
	<div class="w-full max-w-md text-center">
		<span
			class="mx-auto grid h-14 w-14 place-items-center rounded-full bg-[var(--surface-sunken)] {isForbidden
				? 'text-[var(--warning)]'
				: 'text-[var(--negative)]'}"
		>
			<Icon name={isForbidden ? 'lock' : 'alert'} size={24} />
		</span>

		<p class="mt-4 text-5xl font-bold tracking-tight text-[var(--text)]">{page.status}</p>
		<h1 class="mt-2 text-lg font-semibold text-[var(--text)]">
			{#if isForbidden}
				{m.error_forbidden_title()}
			{:else if isNotFound}
				{m.error_not_found_title()}
			{:else}
				{m.error_generic_title()}
			{/if}
		</h1>

		<p class="mt-2 text-sm text-[var(--text-muted)]">
			{detalle}
		</p>

		<div class="mt-6 flex justify-center gap-2">
			<a href={destino.href} class="btn btn-primary">
				<Icon name={destino.icon} size={15} />
				{destino.label}
			</a>
			{#if isForbidden}
				<form method="POST" action="/logout">
					<button type="submit" class="btn btn-ghost">
						<Icon name="logout" size={15} />
						{m.error_switch_user()}
					</button>
				</form>
			{/if}
		</div>
	</div>
</main>
