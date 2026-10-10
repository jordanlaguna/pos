<script lang="ts">
	import Icon from '$lib/ui/components/Icon.svelte';
	import PageHeader from '$lib/ui/components/PageHeader.svelte';
	import EmptyState from '$lib/ui/components/EmptyState.svelte';
	import { formatMoney } from '$lib/domain/money';
	import { formatDateTime, formatInt } from '$lib/ui/format';
	import { m } from '$lib/paraglide/messages.js';
	import type { StockMovement, StockMovementKind } from '$lib/domain/types';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	/**
	 * El rótulo de cada tipo de movimiento.
	 *
	 * Las claves son los once valores que guarda `stock_movements.kind` (RN-98):
	 * no se traducen nunca —el backend valida contra ellos— y lo que se traduce
	 * es cómo se muestran. Se pide al catálogo dentro de una función y no en una
	 * constante de módulo, por el defecto 17: una constante vería el idioma de la
	 * primera petición para siempre.
	 */
	function tipoRotulo(kind: StockMovementKind): string {
		switch (kind) {
			case 'opening':
				return m.kardex_kind_opening();
			case 'sale':
				return m.kardex_kind_sale();
			case 'sale_void':
				return m.kardex_kind_sale_void();
			case 'return':
				return m.kardex_kind_return();
			case 'entry':
				return m.kardex_kind_entry();
			case 'entry_void':
				return m.kardex_kind_entry_void();
			case 'exit':
				return m.kardex_kind_exit();
			case 'exit_void':
				return m.kardex_kind_exit_void();
			case 'count':
				return m.kardex_kind_count();
			case 'transfer_out':
				return m.kardex_kind_transfer_out();
			case 'transfer_in':
				return m.kardex_kind_transfer_in();
		}
	}

	/** De qué documento vino: «Venta #50», «Entrada #9», o la ficha si es la apertura. */
	function origenRotulo(mov: StockMovement): string {
		const id = mov.source_id;
		switch (mov.source_type) {
			case 'sale':
				return m.kardex_source_sale({ id });
			case 'return':
				return m.kardex_source_return({ id });
			case 'stock_entry':
				return m.kardex_source_stock_entry({ id });
			case 'stock_exit':
				return m.kardex_source_stock_exit({ id });
			case 'stock_count':
				return m.kardex_source_stock_count({ id });
			case 'stock_transfer':
				return m.kardex_source_stock_transfer({ id });
			default:
				return m.kardex_source_product();
		}
	}

	/** Lo que baja va en rojo y lo que sube en verde: se lee de un vistazo. */
	function claseCantidad(quantity: number): string {
		return quantity < 0
			? 'bg-[var(--negative-bg)] text-[var(--negative)]'
			: 'bg-[var(--positive-bg)] text-[var(--positive)]';
	}
</script>

<PageHeader
	title={m.kardex_product_title({ product: data.product.name })}
	description={m.kardex_description()}
>
	{#snippet actions()}
		<a href="/inventario" class="btn btn-ghost">
			<Icon name="back" size={15} />
			{m.kardex_back()}
		</a>
	{/snippet}
</PageHeader>

<div class="mb-4 grid gap-3 sm:grid-cols-3">
	<div class="card p-3">
		<p class="text-xs font-semibold tracking-wide text-[var(--text-subtle)] uppercase">
			{m.kardex_stock()}
		</p>
		<p class="mt-1 text-xl font-bold tabular-nums" data-testid="kardex-stock">
			{formatInt(data.product.stock)}
		</p>
		{#if data.levels.length > 1}
			<!-- El desglose solo cuando hay más de una sucursal (RN-102): con una,
			     la suma y la sucursal son el mismo número. -->
			<p class="mt-1 text-xs text-[var(--text-subtle)]">
				{#each data.levels as nivel (nivel.branch_id)}
					<span class="mr-2">
						{m.kardex_branch_stock({ branch: nivel.branch_id })}: {formatInt(nivel.quantity)}
					</span>
				{/each}
			</p>
		{/if}
	</div>
	<div class="card p-3">
		<p class="text-xs font-semibold tracking-wide text-[var(--text-subtle)] uppercase">
			{m.kardex_avg_cost()}
		</p>
		<p class="mt-1 text-xl font-bold tabular-nums">{formatMoney(data.product.cost ?? 0)}</p>
	</div>
	<div class="card p-3">
		<p class="text-xs font-semibold tracking-wide text-[var(--text-subtle)] uppercase">
			{m.inventory_col_barcode()}
		</p>
		<p class="mt-1 font-mono text-sm text-[var(--text)]">{data.product.barcode}</p>
	</div>
</div>

<div class="card overflow-hidden">
	<div class="table-wrap">
		<table class="data-table">
			<thead>
				<tr>
					<th scope="col">{m.kardex_col_date()}</th>
					<th scope="col">{m.kardex_col_kind()}</th>
					<th scope="col" class="num">{m.kardex_col_quantity()}</th>
					<th scope="col" class="num">{m.kardex_col_before()}</th>
					<th scope="col" class="num">{m.kardex_col_after()}</th>
					<th scope="col" class="num">{m.kardex_col_cost()}</th>
					<th scope="col" class="num">{m.kardex_col_avg()}</th>
					<th scope="col">{m.kardex_col_source()}</th>
					<th scope="col">{m.kardex_col_user()}</th>
				</tr>
			</thead>
			<tbody>
				{#each data.movements as mov (mov.id)}
					<tr data-testid="kardex-row" data-kind={mov.kind}>
						<td class="whitespace-nowrap text-xs">{formatDateTime(mov.moved_at)}</td>
						<td>
							<span class="badge {claseCantidad(mov.quantity)}">{tipoRotulo(mov.kind)}</span>
						</td>
						<td class="num font-semibold tabular-nums">
							{mov.quantity > 0 ? `+${formatInt(mov.quantity)}` : formatInt(mov.quantity)}
						</td>
						<td class="num tabular-nums text-[var(--text-muted)]">{formatInt(mov.before_qty)}</td>
						<td class="num tabular-nums">{formatInt(mov.after_qty)}</td>
						<td class="num tabular-nums">{formatMoney(mov.unit_cost)}</td>
						<td class="num tabular-nums text-[var(--text-muted)]">{formatMoney(mov.avg_cost_after)}</td>
						<td class="text-xs">
							{origenRotulo(mov)}
							{#if mov.source_line}
								<span class="text-[var(--text-subtle)]">· {m.kardex_line({ line: mov.source_line })}</span>
							{/if}
						</td>
						<td class="text-xs">#{mov.user_id}</td>
					</tr>
				{:else}
					<tr>
						<td colspan="9">
							<EmptyState icon="clock" title={m.kardex_none()} description={m.kardex_none_hint()} />
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
</div>
