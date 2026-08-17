<script lang="ts">
	import type { Snippet } from 'svelte';
	import Icon from '../Icon.svelte';

	interface Props {
		title: string;
		subtitle?: string;
		/** Atenúa el gráfico mientras llegan datos nuevos, sin desmontarlo. */
		loading?: boolean;
		chart: Snippet;
		table: Snippet;
	}

	let { title, subtitle, loading = false, chart, table }: Props = $props();

	// Toda visualización tiene su gemela en tabla: el color nunca es el único canal.
	let showTable = $state(false);
</script>

<section class="card flex flex-col p-4">
	<header class="mb-3 flex items-start justify-between gap-3">
		<div class="min-w-0">
			<h2 class="text-sm font-bold text-[var(--text)]">{title}</h2>
			{#if subtitle}
				<p class="mt-0.5 text-xs text-[var(--text-subtle)]">{subtitle}</p>
			{/if}
		</div>

		<button
			type="button"
			class="no-print flex shrink-0 items-center gap-1.5 rounded-lg border border-[var(--border)] px-2 py-1 text-xs font-semibold text-[var(--text-muted)] hover:bg-[var(--surface-sunken)] hover:text-[var(--text)]"
			onclick={() => (showTable = !showTable)}
			aria-pressed={showTable}
		>
			<Icon name={showTable ? 'chart' : 'grid'} size={13} />
			{showTable ? 'Gráfico' : 'Tabla'}
		</button>
	</header>

	<!-- Al recargar se mantiene el marco: sin esqueletos ni saltos de layout. -->
	<div class="min-w-0 flex-1 transition-opacity duration-200" class:opacity-40={loading}>
		{#if showTable}
			<div class="table-wrap max-h-72 overflow-y-auto">
				{@render table()}
			</div>
		{:else}
			{@render chart()}
		{/if}
	</div>
</section>
