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

	const PRESETS = [
		{ label: 'Hoy', days: 1 },
		{ label: '7 días', days: 7 },
		{ label: '30 días', days: 30 },
		{ label: '90 días', days: 90 }
	];

	/** Marca el preset activo comparando contra el rango que devolvió el servidor. */
	function isPreset(days: number): boolean {
		const to = new Date();
		const from = new Date();
		from.setDate(from.getDate() - (days - 1));
		return data.range.from === toDateInput(from) && data.range.to === toDateInput(to);
	}

	const paymentTotal = $derived(data.byPaymentMethod.reduce((acc, m) => acc + m.total, 0));

	const topItems = $derived<BarItem[]>(
		data.topProducts.map((p) => ({
			key: p.id_product,
			label: p.name,
			value: p.total,
			secondary: `${formatInt(p.quantity)} u vendidas`
		}))
	);

	const paymentItems = $derived<BarItem[]>(
		data.byPaymentMethod.map((m) => ({
			key: m.payment_method,
			label: m.payment_method,
			value: m.total,
			secondary: `${formatInt(m.count)} ventas · ${
				paymentTotal ? ((m.total / paymentTotal) * 100).toFixed(0) : 0
			} % del total`
		}))
	);

	const rangeLabel = $derived(
		data.range.from === data.range.to
			? formatDate(data.range.from)
			: `${formatDate(data.range.from)} – ${formatDate(data.range.to)}`
	);
</script>

<PageHeader title="Reportes" description="Rendimiento del negocio en el periodo seleccionado." />

{#if !data.reportsAvailable}
	<div
		class="mb-4 flex items-start gap-2 rounded-lg border border-[var(--warning)] bg-[var(--warning-bg)] p-3 text-sm text-[var(--warning)]"
		role="alert"
	>
		<Icon name="alert" size={16} class="mt-0.5 shrink-0" />
		<p>
			<strong>Los reportes no están disponibles.</strong> El backend no expone
			<code>/reports/*</code>. Actualizá el FastAPI de <code>backend/</code> y reinicialo.
		</p>
	</div>
{/if}

<!-- Una sola fila de filtros, arriba de todo lo que condiciona. -->
<div class="card mb-4 flex flex-wrap items-end gap-3 p-3">
	<div class="flex flex-wrap gap-1.5">
		{#each PRESETS as p (p.days)}
			<button
				type="button"
				class="badge border {isPreset(p.days)
					? 'border-transparent bg-[var(--accent)] text-[var(--accent-text)]'
					: 'border-[var(--border)] text-[var(--text-muted)] hover:bg-[var(--surface-sunken)]'}"
				onclick={() => preset(p.days)}
			>
				{#if isPreset(p.days)}<Icon name="check" size={12} />{/if}
				{p.label}
			</button>
		{/each}
		<button
			type="button"
			class="badge border border-[var(--border)] text-[var(--text-muted)] hover:bg-[var(--surface-sunken)]"
			onclick={monthToDate}
		>
			Mes actual
		</button>
	</div>

	<div class="ml-auto flex flex-wrap items-end gap-2">
		<div>
			<label class="label" for="rango-desde">Desde</label>
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
			<label class="label" for="rango-hasta">Hasta</label>
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
			label="Ventas netas"
			value={formatMoney(s.net_total)}
			icon="wallet"
			delta={formatDelta(s.net_total, s.previous_net_total)}
		/>
		<StatCard
			label="Facturas emitidas"
			value={formatInt(s.sales_count)}
			icon="receipt"
			hint={rangeLabel}
		/>
		<StatCard
			label="Ticket promedio"
			value={formatMoney(s.average_ticket)}
			icon="trending"
			hint="{formatInt(s.items_sold)} unidades vendidas"
		/>
		<StatCard
			label="Devoluciones"
			value={formatMoney(s.returns_total)}
			icon="undo"
			tone={s.returns_total > 0 ? 'negative' : 'neutral'}
			deltaIsGood={false}
			hint={s.returns_total > 0 ? 'Descontadas de las ventas netas' : 'Sin devoluciones'}
		/>
	</div>
{/if}

<div class="grid gap-4">
	<SalesTrendChart
		data={data.salesByDay}
		title="Ventas por día"
		subtitle={rangeLabel}
		{loading}
	/>

	<div class="grid gap-4 lg:grid-cols-2">
		<BarListChart
			items={topItems}
			title="Productos más vendidos"
			subtitle="Por monto facturado en el periodo"
			valueHeader="Facturado"
			secondaryHeader="Unidades"
			emptyMessage="No hubo ventas en el periodo seleccionado."
			{loading}
		/>

		<BarListChart
			items={paymentItems}
			title="Ventas por método de pago"
			subtitle="Total cobrado por cada medio"
			valueHeader="Total"
			secondaryHeader="Detalle"
			emptyMessage="No hubo ventas en el periodo seleccionado."
			{loading}
		/>
	</div>

	<!-- Alertas de stock: estado, con icono y etiqueta, nunca solo color. -->
	<section class="card p-4">
		<header class="mb-3 flex items-center justify-between gap-3">
			<div>
				<h2 class="text-sm font-bold text-[var(--text)]">Alertas de inventario</h2>
				<p class="mt-0.5 text-xs text-[var(--text-subtle)]">
					Productos con {data.lowStockThreshold} unidades o menos
				</p>
			</div>
			<a
				href="/inventario"
				class="text-xs font-semibold text-[var(--accent)] hover:underline"
			>
				Ir a inventario
			</a>
		</header>

		{#if data.lowStock.length}
			<div class="table-wrap max-h-80 overflow-y-auto">
				<table class="data-table">
					<thead>
						<tr>
							<th scope="col">Producto</th>
							<th scope="col">Código</th>
							<th scope="col" class="num">Stock</th>
							<th scope="col">Estado</th>
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
											Agotado
										</span>
									{:else}
										<span class="badge bg-[var(--warning-bg)] text-[var(--warning)]">
											<Icon name="alert" size={11} />
											Stock bajo
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
				title="Todo el inventario está en orden"
				description="Ningún producto está por debajo del umbral."
				compact
			/>
		{/if}
	</section>
</div>
