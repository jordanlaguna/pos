<script lang="ts" module>
	export interface BarItem {
		key: string | number;
		label: string;
		value: number;
		/** Métrica de apoyo (unidades, número de ventas, porcentaje). */
		secondary?: string;
	}
</script>

<script lang="ts">
	import { formatMoney } from '$lib/domain/money';
	import ChartCard from './ChartCard.svelte';
	import EmptyState from '../EmptyState.svelte';

	interface Props {
		items: BarItem[];
		title: string;
		subtitle?: string;
		loading?: boolean;
		/** Encabezado de la columna de valores en la vista de tabla. */
		valueHeader?: string;
		secondaryHeader?: string;
		emptyMessage?: string;
	}

	let {
		items,
		title,
		subtitle,
		loading = false,
		valueHeader = 'Total',
		secondaryHeader = 'Detalle',
		emptyMessage = 'No hay datos en el periodo seleccionado.'
	}: Props = $props();

	// Categorías nominales (productos, métodos de pago): un solo tono para todas
	// las barras. Oscurecer según el valor duplicaría lo que ya dice la longitud.
	const max = $derived(Math.max(0, ...items.map((i) => i.value)));
	const pct = $derived((value: number) => (max > 0 ? (value / max) * 100 : 0));

	let activeKey = $state<string | number | null>(null);
</script>

<ChartCard {title} {subtitle} {loading}>
	{#snippet chart()}
		{#if !items.length}
			<EmptyState icon="chart" title="Sin datos" description={emptyMessage} compact />
		{:else}
			<ul class="flex flex-col gap-1.5">
				{#each items as item (item.key)}
					{@const percentage = pct(item.value)}
					<!-- El valor ya está rotulado en la punta; el hover solo añade la métrica
					     de apoyo, que la vista de tabla expone sin depender del puntero. -->
					<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
					<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
					<li
						class="group relative grid grid-cols-[minmax(6rem,11rem)_1fr] items-center gap-3 rounded-md px-1 py-1.5 outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]"
						class:bg-[var(--surface-sunken)]={activeKey === item.key}
						tabindex="0"
						onmouseenter={() => (activeKey = item.key)}
						onmouseleave={() => (activeKey = null)}
						onfocus={() => (activeKey = item.key)}
						onblur={() => (activeKey = null)}
					>
						<span class="truncate text-xs text-[var(--text-muted)]" title={item.label}>
							{item.label}
						</span>

						<div class="relative">
							<!-- El carril reserva la derecha para que la cifra nunca se recorte. -->
							<div class="relative w-[calc(100%-5.5rem)]">
								<div
									class="h-5 rounded-r-[4px] transition-[filter] duration-100 group-hover:brightness-110"
									style="width:{Math.max(percentage, 0.8)}%; background:var(--chart-accent)"
								></div>

								<!-- Etiqueta directa en la punta: el valor siempre es legible sin hover. -->
								<span
									class="absolute top-1/2 ml-2 -translate-y-1/2 text-xs font-semibold tabular-nums whitespace-nowrap text-[var(--text)]"
									style="left:{percentage}%"
								>
									{formatMoney(item.value)}
								</span>
							</div>

							{#if activeKey === item.key && item.secondary}
								<div
									class="pointer-events-none absolute -top-1 right-0 z-10 rounded-lg border border-[var(--border)] bg-[var(--surface-raised)] px-2.5 py-1.5 shadow-lg"
									role="status"
								>
									<p class="text-sm font-bold tabular-nums text-[var(--text)]">
										{formatMoney(item.value)}
									</p>
									<p class="text-[11px] whitespace-nowrap text-[var(--text-subtle)]">
										{item.label} · {item.secondary}
									</p>
								</div>
							{/if}
						</div>
					</li>
				{/each}
			</ul>
		{/if}
	{/snippet}

	{#snippet table()}
		<table class="data-table">
			<thead>
				<tr>
					<th scope="col">Concepto</th>
					<th scope="col" class="num">{valueHeader}</th>
					<th scope="col" class="num">{secondaryHeader}</th>
				</tr>
			</thead>
			<tbody>
				{#each items as item (item.key)}
					<tr>
						<td>{item.label}</td>
						<td class="num tabular-nums">{formatMoney(item.value)}</td>
						<td class="num tabular-nums">{item.secondary ?? '—'}</td>
					</tr>
				{:else}
					<tr><td colspan="3" class="text-[var(--text-subtle)]">{emptyMessage}</td></tr>
				{/each}
			</tbody>
		</table>
	{/snippet}
</ChartCard>
