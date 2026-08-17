<script lang="ts">
	import { page } from '$app/state';
	import Icon from '$lib/ui/components/Icon.svelte';

	const isForbidden = $derived(page.status === 403);
	const isNotFound = $derived(page.status === 404);
</script>

<svelte:head><title>Error {page.status} · VentaSys</title></svelte:head>

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
				Acceso restringido
			{:else if isNotFound}
				Página no encontrada
			{:else}
				Algo salió mal
			{/if}
		</h1>

		<p class="mt-2 text-sm text-[var(--text-muted)]">
			{page.error?.message ?? 'Ocurrió un error inesperado.'}
		</p>

		<div class="mt-6 flex justify-center gap-2">
			<a href="/ventas" class="btn btn-primary">
				<Icon name="cart" size={15} />
				Ir a ventas
			</a>
			{#if isForbidden}
				<form method="POST" action="/logout">
					<button type="submit" class="btn btn-ghost">
						<Icon name="logout" size={15} />
						Cambiar de usuario
					</button>
				</form>
			{/if}
		</div>
	</div>
</main>
