<script lang="ts">
	import Icon from '$lib/ui/components/Icon.svelte';
	import PageHeader from '$lib/ui/components/PageHeader.svelte';
	import EmptyState from '$lib/ui/components/EmptyState.svelte';
	import { formatMoney } from '$lib/domain/money';
	import { formatDateTime, formatInt, toDateInput } from '$lib/ui/format';
	import { PAYMENT_METHODS } from '$lib/domain/types';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	let search = $state('');
	let method = $state('');
	let from = $state('');
	let until = $state('');
	let page = $state(1);

	const PER_PAGE = 25;

	function withinRange(value: string): boolean {
		const day = String(value).slice(0, 10);
		if (from && day < from) return false;
		if (until && day > until) return false;
		return true;
	}

	const filtered = $derived.by(() => {
		const term = search.trim().toLowerCase();
		return data.sales.filter((sale) => {
			if (method && sale.payment_method !== method) return false;
			if (!withinRange(sale.created_at)) return false;
			if (!term) return true;
			return (
				sale.sale_number.toLowerCase().includes(term) ||
				String(sale.total).includes(term)
			);
		});
	});

	// Cualquier cambio de filtro devuelve a la primera página.
	$effect(() => {
		search;
		method;
		from;
		until;
		page = 1;
	});

	const totalPages = $derived(Math.max(1, Math.ceil(filtered.length / PER_PAGE)));
	const visible = $derived(filtered.slice((page - 1) * PER_PAGE, page * PER_PAGE));
	const sumTotal = $derived(filtered.reduce((acc, s) => acc + Number(s.total), 0));

	function clearFilters() {
		search = '';
		method = '';
		from = '';
		until = '';
	}

	const hasFilters = $derived(Boolean(search || method || from || until));

	function setToday() {
		const today = toDateInput(new Date());
		from = today;
		until = today;
	}
</script>

<PageHeader
	title="Facturas"
	description="Historial de ventas registradas en el sistema."
>
	{#snippet actions()}
		<a href="/ventas" class="btn btn-primary">
			<Icon name="cart" size={15} />
			Nueva venta
		</a>
	{/snippet}
</PageHeader>

<!-- Una sola fila de filtros, arriba de todo lo que condicionan. -->
<div class="card mb-4 flex flex-wrap items-end gap-3 p-3">
	<div class="min-w-[12rem] flex-1">
		<label class="label" for="factura-buscar">Buscar</label>
		<div class="relative">
			<span
				class="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-[var(--text-subtle)]"
			>
				<Icon name="search" size={15} />
			</span>
			<input
				id="factura-buscar"
				bind:value={search}
				type="search"
				placeholder="Número de factura o monto…"
				class="input pl-9"
			/>
		</div>
	</div>

	<div>
		<label class="label" for="factura-metodo">Método de pago</label>
		<select id="factura-metodo" bind:value={method} class="input w-44">
			<option value="">Todos</option>
			{#each PAYMENT_METHODS as m}
				<option value={m}>{m}</option>
			{/each}
		</select>
	</div>

	<div>
		<label class="label" for="factura-desde">Desde</label>
		<input id="factura-desde" bind:value={from} type="date" class="input w-40" />
	</div>

	<div>
		<label class="label" for="factura-hasta">Hasta</label>
		<input id="factura-hasta" bind:value={until} type="date" class="input w-40" />
	</div>

	<button type="button" class="btn btn-ghost" onclick={setToday}>Hoy</button>

	{#if hasFilters}
		<button type="button" class="btn btn-ghost" onclick={clearFilters}>
			<Icon name="close" size={14} />
			Limpiar
		</button>
	{/if}
</div>

<div class="mb-3 flex flex-wrap items-center justify-between gap-2 text-sm">
	<p class="text-[var(--text-muted)]">
		<strong class="text-[var(--text)]">{formatInt(filtered.length)}</strong>
		{filtered.length === 1 ? 'factura' : 'facturas'}
	</p>
	<p class="text-[var(--text-muted)]">
		Total: <strong class="tabular-nums text-[var(--text)]">{formatMoney(sumTotal)}</strong>
	</p>
</div>

<div class="card overflow-hidden">
	<div class="table-wrap">
		<table class="data-table">
			<thead>
				<tr>
					<th scope="col">Factura</th>
					<th scope="col">Fecha</th>
					<th scope="col">Método de pago</th>
					<th scope="col" class="num">Subtotal</th>
					<th scope="col" class="num">IVA</th>
					<th scope="col" class="num">Total</th>
					<th scope="col"><span class="sr-only">Acciones</span></th>
				</tr>
			</thead>
			<tbody>
				{#each visible as sale (sale.id)}
					<tr>
						<td class="font-mono text-xs font-semibold">{sale.sale_number}</td>
						<td class="whitespace-nowrap">{formatDateTime(sale.created_at)}</td>
						<td>{sale.payment_method}</td>
						<td class="num tabular-nums">
							{formatMoney(Number((sale as any).subtotal ?? 0))}
						</td>
						<td class="num tabular-nums">{formatMoney(Number((sale as any).tax ?? 0))}</td>
						<td class="num font-semibold tabular-nums">{formatMoney(Number(sale.total))}</td>
						<td class="text-right">
							<a
								href="/facturas/{sale.id}"
								class="inline-flex items-center gap-1 text-xs font-semibold text-[var(--accent)] hover:underline"
							>
								Ver
								<Icon name="forward" size={12} />
							</a>
						</td>
					</tr>
				{:else}
					<tr>
						<td colspan="7">
							<EmptyState
								icon="receipt"
								title={hasFilters ? 'Sin resultados' : 'Todavía no hay facturas'}
								description={hasFilters
									? 'Probá con otros filtros o limpialos para ver todo.'
									: 'Las ventas que cobres van a aparecer acá.'}
								compact
							/>
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>

	{#if totalPages > 1}
		<div
			class="flex items-center justify-between gap-2 border-t border-[var(--border)] px-3 py-2"
		>
			<button
				type="button"
				class="btn btn-ghost px-2.5 py-1 text-xs"
				onclick={() => (page = Math.max(1, page - 1))}
				disabled={page === 1}
			>
				<Icon name="back" size={13} />
				Anterior
			</button>
			<span class="text-xs text-[var(--text-muted)]">
				Página {page} de {totalPages}
			</span>
			<button
				type="button"
				class="btn btn-ghost px-2.5 py-1 text-xs"
				onclick={() => (page = Math.min(totalPages, page + 1))}
				disabled={page === totalPages}
			>
				Siguiente
				<Icon name="forward" size={13} />
			</button>
		</div>
	{/if}
</div>
