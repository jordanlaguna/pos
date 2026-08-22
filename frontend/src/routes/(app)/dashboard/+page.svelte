<script lang="ts">
	import { goto } from '$app/navigation';
	import { navigating } from '$app/state';
	import Icon from '$lib/ui/components/Icon.svelte';
	import PageHeader from '$lib/ui/components/PageHeader.svelte';
	import StatCard from '$lib/ui/components/StatCard.svelte';
	import EmptyState from '$lib/ui/components/EmptyState.svelte';
	import SalesTrendChart from '$lib/ui/components/charts/SalesTrendChart.svelte';
	import BarListChart from '$lib/ui/components/charts/BarListChart.svelte';
	import type { BarItem } from '$lib/ui/components/charts/BarListChart.svelte';
	import { formatMoney } from '$lib/domain/money';
	import { formatDate, formatDelta, formatInt, toDateInput } from '$lib/ui/format';
	import { m } from '$lib/paraglide/messages.js';
	import { paymentLabel } from '$lib/ui/messages';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	// Mientras llega el rango nuevo, los gráficos se atenúan sin desmontarse.
	const loading = $derived(navigating.to?.url.pathname === '/dashboard');

	function applyRange(from: string, to: string) {
		goto(`/dashboard?from=${from}&to=${to}`, { keepFocus: true, noScroll: true });
	}

	function preset(days: number) {
		const to = new Date();
		const from = new Date();
		from.setDate(from.getDate() - (days - 1));
		applyRange(toDateInput(from), toDateInput(to));
	}

	function monthToDate() {
		const now = new Date();
		applyRange(toDateInput(new Date(now.getFullYear(), now.getMonth(), 1)), toDateInput(now));
	}

	/**
	 * Los rangos rápidos. Solo los días: el rótulo se arma al pintar.
	 *
	 * Una constante de módulo con el texto adentro se evaluaría una vez por
	 * proceso y todas las peticiones verían el idioma de la primera —el defecto
	 * 17 otra vez—.
	 */
	const PRESETS = [1, 7, 30, 90];

	function presetLabel(days: number): string {
		return days === 1 ? m.reports_preset_today() : m.reports_preset_days({ days });
	}

	/** Marca el preset activo comparando contra el rango que devolvió el servidor. */
	function isPreset(days: number): boolean {
		const to = new Date();
		const from = new Date();
		from.setDate(from.getDate() - (days - 1));
		return data.range.from === toDateInput(from) && data.range.to === toDateInput(to);
	}

	// Las variables de estas funciones se llaman `metodo` y no `m`: `m` es ahora
	// el catálogo de mensajes, y un parámetro con ese nombre lo taparía justo
	// donde hace falta.
	const paymentTotal = $derived(
		data.byPaymentMethod.reduce((acc, metodo) => acc + metodo.total, 0)
	);

	const topItems = $derived<BarItem[]>(
		data.topProducts.map((p) => ({
			key: p.id_product,
			label: p.name,
			value: p.total,
			secondary: m.reports_units_short({ units: formatInt(p.quantity) })
		}))
	);

	const paymentItems = $derived<BarItem[]>(
		data.byPaymentMethod.map((metodo) => ({
			key: metodo.payment_method,
			// El valor se guarda en `sales.payment_method` y no se traduce nunca;
			// `paymentLabel` traduce cómo se muestra.
			label: paymentLabel(metodo.payment_method),
			value: metodo.total,
			secondary: m.reports_payment_share({
				count: formatInt(metodo.count),
				percent: paymentTotal ? ((metodo.total / paymentTotal) * 100).toFixed(0) : 0
			})
		}))
	);

	const rangeLabel = $derived(
		data.range.from === data.range.to
			? formatDate(data.range.from)
			: `${formatDate(data.range.from)} – ${formatDate(data.range.to)}`
	);
</script>

<PageHeader title={m.reports_title()} description={m.reports_description()} />

{#if !data.reportsAvailable}
	<div
		class="mb-4 flex items-start gap-2 rounded-lg border border-[var(--warning)] bg-[var(--warning-bg)] p-3 text-sm text-[var(--warning)]"
		role="alert"
	>
		<Icon name="alert" size={16} class="mt-0.5 shrink-0" />
		<p>
			<strong>{m.reports_module_missing()}</strong>
			{m.reports_module_missing_hint({ endpoint: '/reports/*', folder: 'backend/' })}
		</p>
	</div>
{/if}

<!-- Una sola fila de filtros, arriba de todo lo que condiciona. -->
<div class="card mb-4 flex flex-wrap items-end gap-3 p-3">
	<div class="flex flex-wrap gap-1.5">
		{#each PRESETS as days (days)}
			<button
				type="button"
				class="badge border {isPreset(days)
					? 'border-transparent bg-[var(--accent)] text-[var(--accent-text)]'
					: 'border-[var(--border)] text-[var(--text-muted)] hover:bg-[var(--surface-sunken)]'}"
				onclick={() => preset(days)}
			>
				{#if isPreset(days)}<Icon name="check" size={12} />{/if}
				{presetLabel(days)}
			</button>
		{/each}
		<button
			type="button"
			class="badge border border-[var(--border)] text-[var(--text-muted)] hover:bg-[var(--surface-sunken)]"
			onclick={monthToDate}
		>
			{m.reports_preset_month()}
		</button>
	</div>

	<div class="ml-auto flex flex-wrap items-end gap-2">
		<div>
			<label class="label" for="rango-desde">{m.reports_from()}</label>
			<input
				id="rango-desde"
				type="date"
				value={data.range.from}
				max={data.range.to}
				class="input w-40"
				onchange={(e) => applyRange(e.currentTarget.value, data.range.to)}
			/>
		</div>
		<div>
			<label class="label" for="rango-hasta">{m.reports_to()}</label>
			<input
				id="rango-hasta"
				type="date"
				value={data.range.to}
				min={data.range.from}
				class="input w-40"
				onchange={(e) => applyRange(data.range.from, e.currentTarget.value)}
			/>
		</div>
	</div>
</div>

{#if data.summary}
	{@const s = data.summary}
	<div class="mb-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
		<StatCard
			label={m.reports_net_sales()}
			value={formatMoney(s.net_total)}
			icon="wallet"
			delta={formatDelta(s.net_total, s.previous_net_total)}
		/>
		<StatCard
			label={m.reports_invoices_issued()}
			value={formatInt(s.sales_count)}
			icon="receipt"
			hint={rangeLabel}
		/>
		<StatCard
			label={m.reports_average_ticket()}
			value={formatMoney(s.average_ticket)}
			icon="trending"
			hint={m.reports_units_sold({ units: formatInt(s.items_sold) })}
		/>
		<StatCard
			label={m.reports_returns()}
			value={formatMoney(s.returns_total)}
			icon="undo"
			tone={s.returns_total > 0 ? 'negative' : 'neutral'}
			deltaIsGood={false}
			hint={s.returns_total > 0 ? m.reports_returns_deducted() : m.reports_no_returns()}
		/>
	</div>
{/if}

<div class="grid gap-4">
	<SalesTrendChart
		data={data.salesByDay}
		title={m.reports_sales_by_day()}
		subtitle={rangeLabel}
		{loading}
	/>

	<div class="grid gap-4 lg:grid-cols-2">
		<BarListChart
			items={topItems}
			title={m.reports_top_products()}
			subtitle={m.reports_top_products_hint()}
			valueHeader={m.reports_billed()}
			secondaryHeader={m.reports_units()}
			emptyMessage={m.reports_no_sales_in_range()}
			{loading}
		/>

		<BarListChart
			items={paymentItems}
			title={m.reports_by_payment()}
			subtitle={m.reports_by_payment_hint()}
			valueHeader={m.reports_total()}
			secondaryHeader={m.reports_breakdown()}
			emptyMessage={m.reports_no_sales_in_range()}
			{loading}
		/>
	</div>

	<!-- Alertas de stock: estado, con icono y etiqueta, nunca solo color. -->
	<section class="card p-4">
		<header class="mb-3 flex items-center justify-between gap-3">
			<div>
				<h2 class="text-sm font-bold text-[var(--text)]">{m.reports_stock_alerts()}</h2>
				<p class="mt-0.5 text-xs text-[var(--text-subtle)]">
					{m.reports_stock_threshold({ threshold: data.lowStockThreshold })}
				</p>
			</div>
			<a
				href="/inventario"
				class="text-xs font-semibold text-[var(--accent)] hover:underline"
			>
				{m.reports_go_to_inventory()}
			</a>
		</header>

		{#if data.lowStock.length}
			<div class="table-wrap max-h-80 overflow-y-auto">
				<table class="data-table">
					<thead>
						<tr>
							<th scope="col">{m.reports_col_product()}</th>
							<th scope="col">{m.reports_col_barcode()}</th>
							<th scope="col" class="num">{m.reports_col_stock()}</th>
							<th scope="col">{m.reports_col_status()}</th>
						</tr>
					</thead>
					<tbody>
						{#each data.lowStock as product (product.id_product)}
							<tr>
								<td class="font-medium text-[var(--text)]">{product.name}</td>
								<td class="font-mono text-xs">{product.barcode}</td>
								<td class="num tabular-nums">{product.stock}</td>
								<td>
									{#if product.stock <= 0}
										<span class="badge bg-[var(--negative-bg)] text-[var(--negative)]">
											<Icon name="alert" size={11} />
											{m.reports_out_of_stock()}
										</span>
									{:else}
										<span class="badge bg-[var(--warning-bg)] text-[var(--warning)]">
											<Icon name="alert" size={11} />
											{m.reports_low_stock()}
										</span>
									{/if}
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		{:else}
			<EmptyState
				icon="check"
				title={m.reports_inventory_ok()}
				description={m.reports_inventory_ok_hint()}
				compact
			/>
		{/if}
	</section>
</div>
