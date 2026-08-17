<script lang="ts">
	import type { SalesByDay } from '$lib/domain/types';
	import { formatCompact, formatMoney } from '$lib/domain/money';
	import { formatDayLabel, formatInt } from '$lib/ui/format';
	import ChartCard from './ChartCard.svelte';
	import EmptyState from '../EmptyState.svelte';

	interface Props {
		data: SalesByDay[];
		title?: string;
		subtitle?: string;
		loading?: boolean;
		height?: number;
	}

	let {
		data,
		title = 'Ventas por día',
		subtitle,
		loading = false,
		height = 240
	}: Props = $props();

	// Serie única: la tendencia es el sujeto, no hay identidades que distinguir,
	// así que un solo tono y sin leyenda — el título ya dice qué se grafica.
	const PAD = { top: 14, right: 20, bottom: 26, left: 56 };

	let width = $state(680);
	let activeIndex = $state<number | null>(null);

	const points = $derived(data ?? []);
	const innerW = $derived(Math.max(10, width - PAD.left - PAD.right));
	const innerH = $derived(Math.max(10, height - PAD.top - PAD.bottom));

	/** Techo redondo (1/2/2.5/5 × 10ⁿ) para que las marcas del eje sean legibles. */
	const maxValue = $derived.by(() => {
		const peak = Math.max(0, ...points.map((p) => p.total));
		if (peak <= 0) return 1000;
		const magnitude = 10 ** Math.floor(Math.log10(peak));
		for (const step of [1, 2, 2.5, 5, 10]) {
			if (peak <= step * magnitude) return step * magnitude;
		}
		return 10 * magnitude;
	});

	const xOf = $derived((i: number) =>
		points.length > 1
			? PAD.left + (innerW * i) / (points.length - 1)
			: PAD.left + innerW / 2
	);
	const yOf = $derived((v: number) => PAD.top + innerH - (v / maxValue) * innerH);

	const linePath = $derived(
		points.map((p, i) => `${i === 0 ? 'M' : 'L'}${xOf(i)},${yOf(p.total)}`).join(' ')
	);
	const areaPath = $derived(
		points.length
			? `${linePath} L${xOf(points.length - 1)},${PAD.top + innerH} L${xOf(0)},${PAD.top + innerH} Z`
			: ''
	);

	const yTicks = $derived([0, 0.25, 0.5, 0.75, 1].map((f) => maxValue * f));

	/** ~5 etiquetas repartidas: rotularlas todas sería ilegible. */
	const xTicks = $derived.by(() => {
		if (points.length <= 1) return points.map((_, i) => i);
		const wanted = Math.min(5, points.length);
		const stride = (points.length - 1) / (wanted - 1);
		return Array.from({ length: wanted }, (_, k) => Math.round(k * stride));
	});

	const active = $derived(activeIndex != null ? points[activeIndex] : null);

	function shortDay(day: string): string {
		const d = new Date(`${day}T00:00:00`);
		return new Intl.DateTimeFormat('es-CR', { day: 'numeric', month: 'short' }).format(d);
	}

	/** La mira busca la X: el lector apunta a una fecha, no a una línea de 2px. */
	function trackPointer(event: PointerEvent) {
		if (points.length === 0) return;
		const rect = (event.currentTarget as SVGRectElement).getBoundingClientRect();
		const relative = event.clientX - rect.left;
		const step = points.length > 1 ? innerW / (points.length - 1) : innerW;
		activeIndex = Math.max(0, Math.min(points.length - 1, Math.round(relative / step)));
	}

	function onKeydown(event: KeyboardEvent) {
		if (!points.length) return;
		const current = activeIndex ?? points.length - 1;
		if (event.key === 'ArrowRight') activeIndex = Math.min(points.length - 1, current + 1);
		else if (event.key === 'ArrowLeft') activeIndex = Math.max(0, current - 1);
		else if (event.key === 'Home') activeIndex = 0;
		else if (event.key === 'End') activeIndex = points.length - 1;
		else if (event.key === 'Escape') activeIndex = null;
		else return;
		event.preventDefault();
	}

	const last = $derived(points.length ? points[points.length - 1] : null);
	// La etiqueta directa del final se oculta si la mira ya está sobre ese punto.
	const showEndLabel = $derived(last != null && activeIndex !== points.length - 1);

	const tooltipLeft = $derived(
		activeIndex == null ? 0 : Math.min(Math.max(xOf(activeIndex), 70), width - 70)
	);
</script>

<ChartCard {title} {subtitle} {loading}>
	{#snippet chart()}
		{#if !points.length}
			<EmptyState
				icon="chart"
				title="Sin ventas en el periodo"
				description="Elegí otro rango de fechas para ver la tendencia."
				compact
			/>
		{:else}
			<div class="relative" bind:clientWidth={width}>
				<!--
					El recorrido con flechas es una mejora para quien navega con teclado y ve
					el gráfico. Para lectores de pantalla la vía accesible es la vista de
					tabla del encabezado, que expone los mismos valores como datos.
				-->
				<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
				<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
				<svg
					{width}
					{height}
					viewBox="0 0 {width} {height}"
					role="img"
					aria-label="Ventas por día. Use las flechas para recorrer los días."
					tabindex="0"
					class="block touch-none outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]"
					onkeydown={onKeydown}
					onblur={() => (activeIndex = null)}
				>
					<!-- Rejilla: hairline sólido, un paso fuera de la superficie. -->
					{#each yTicks as tick}
						<line
							x1={PAD.left}
							x2={PAD.left + innerW}
							y1={yOf(tick)}
							y2={yOf(tick)}
							stroke="var(--chart-grid)"
							stroke-width="1"
						/>
						<text
							x={PAD.left - 8}
							y={yOf(tick)}
							text-anchor="end"
							dominant-baseline="middle"
							class="fill-[var(--chart-ink)] text-[10px] tabular-nums"
						>
							{formatCompact(tick)}
						</text>
					{/each}

					{#each xTicks as index}
						<text
							x={xOf(index)}
							y={height - 8}
							text-anchor="middle"
							class="fill-[var(--chart-ink)] text-[10px]"
						>
							{shortDay(points[index].day)}
						</text>
					{/each}

					<!-- Relleno al 10%: un velo, nunca un bloque saturado. -->
					<path d={areaPath} fill="var(--chart-area)" />
					<path
						d={linePath}
						fill="none"
						stroke="var(--chart-accent)"
						stroke-width="2"
						stroke-linejoin="round"
						stroke-linecap="round"
					/>

					{#if last && showEndLabel}
						<circle
							cx={xOf(points.length - 1)}
							cy={yOf(last.total)}
							r="4"
							fill="var(--chart-accent)"
							stroke="var(--chart-surface)"
							stroke-width="2"
						/>
					{/if}

					{#if activeIndex != null && active}
						<line
							x1={xOf(activeIndex)}
							x2={xOf(activeIndex)}
							y1={PAD.top}
							y2={PAD.top + innerH}
							stroke="var(--chart-axis)"
							stroke-width="1"
						/>
						<circle
							cx={xOf(activeIndex)}
							cy={yOf(active.total)}
							r="5"
							fill="var(--chart-accent)"
							stroke="var(--chart-surface)"
							stroke-width="2"
						/>
					{/if}

					<!-- Capa de captura: el objetivo es toda la banda, no la línea. -->
					<!-- svelte-ignore a11y_no_static_element_interactions -->
					<rect
						aria-hidden="true"
						x={PAD.left}
						y={PAD.top}
						width={innerW}
						height={innerH}
						fill="transparent"
						onpointermove={trackPointer}
						onpointerleave={() => (activeIndex = null)}
					/>
				</svg>

				{#if last && showEndLabel}
					<!-- Etiqueta directa solo en el extremo, para no inundar el gráfico. -->
					<span
						class="pointer-events-none absolute text-[11px] font-semibold text-[var(--text-muted)]"
						style="left:{Math.min(xOf(points.length - 1) + 8, width - 64)}px; top:{yOf(
							last.total
						) - 20}px"
					>
						{formatCompact(last.total)}
					</span>
				{/if}

				{#if active}
					<div
						class="pointer-events-none absolute -translate-x-1/2 rounded-lg border border-[var(--border)] bg-[var(--surface-raised)] px-2.5 py-1.5 shadow-lg"
						style="left:{tooltipLeft}px; top:4px"
						role="status"
					>
						<!-- El valor manda; la etiqueta es secundaria. -->
						<p class="text-sm font-bold tabular-nums text-[var(--text)]">
							{formatMoney(active.total)}
						</p>
						<p class="text-[11px] whitespace-nowrap text-[var(--text-subtle)]">
							{formatDayLabel(active.day)} · {formatInt(active.sales_count)}
							{active.sales_count === 1 ? 'venta' : 'ventas'}
						</p>
					</div>
				{/if}
			</div>
		{/if}
	{/snippet}

	{#snippet table()}
		<table class="data-table">
			<thead>
				<tr>
					<th scope="col">Día</th>
					<th scope="col" class="num">Ventas</th>
					<th scope="col" class="num">Total</th>
				</tr>
			</thead>
			<tbody>
				{#each points as point (point.day)}
					<tr>
						<td>{formatDayLabel(point.day)}</td>
						<td class="num tabular-nums">{formatInt(point.sales_count)}</td>
						<td class="num tabular-nums">{formatMoney(point.total)}</td>
					</tr>
				{:else}
					<tr><td colspan="3" class="text-[var(--text-subtle)]">Sin datos.</td></tr>
				{/each}
			</tbody>
		</table>
	{/snippet}
</ChartCard>
