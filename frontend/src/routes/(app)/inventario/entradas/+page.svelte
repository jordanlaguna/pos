<script lang="ts">
	import { enhance } from '$app/forms';
	import { page } from '$app/state';
	import { submit } from '$lib/ui/forms';
	import Icon from '$lib/ui/components/Icon.svelte';
	import PageHeader from '$lib/ui/components/PageHeader.svelte';
	import Modal from '$lib/ui/components/Modal.svelte';
	import EmptyState from '$lib/ui/components/EmptyState.svelte';
	import { toasts } from '$lib/ui/stores/toast.svelte';
	import { formatMoney } from '$lib/domain/money';
	import { formatDateTime, formatInt } from '$lib/ui/format';
	import { m } from '$lib/paraglide/messages.js';
	import type { StockEntry } from '$lib/domain/types';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	let detalle = $state<StockEntry | null>(null);
	let anular = $state<StockEntry | null>(null);

	/**
	 * El rótulo y el icono de cada origen.
	 *
	 * Las claves son los valores que guarda `stock_entries.source`: no se
	 * traducen nunca —el backend valida contra ellos— y lo que se traduce es cómo
	 * se muestran. El rótulo se pide al catálogo dentro de una función y no en una
	 * constante de módulo: una constante se evaluaría una vez por proceso y todas
	 * las peticiones verían el idioma de la primera (defecto 17).
	 */
	const ICONO: Record<string, 'edit' | 'grid' | 'receipt'> = {
		manual: 'edit',
		excel: 'grid',
		xml: 'receipt'
	};

	function origenRotulo(source: string): string {
		switch (source) {
			case 'excel':
				return m.entries_source_excel();
			case 'xml':
				return m.entries_source_xml();
			default:
				return m.entries_source_manual();
		}
	}

	// El alta termina en redirect, así que el aviso no puede salir de enhance.
	let avisada = $state<string | null>(null);
	$effect(() => {
		const creada = page.url.searchParams.get('creada');
		if (creada && creada !== avisada) {
			avisada = creada;
			toasts.success(m.entries_created_toast(), m.entries_created_detail());
		}
	});
</script>

<PageHeader
	title={m.entries_title()}
	description={m.entries_description()}
>
	{#snippet actions()}
		<a href="/inventario" class="btn btn-ghost">
			<Icon name="box" size={15} />
			{m.entries_catalog()}
		</a>
		<a href="/inventario/entradas/nueva" class="btn btn-primary">
			<Icon name="plus" size={15} />
			{m.entries_new()}
		</a>
	{/snippet}
</PageHeader>

{#if !data.available}
	<div
		class="mb-4 flex items-start gap-2 rounded-lg border border-[var(--warning)] bg-[var(--warning-bg)] p-3 text-sm text-[var(--warning)]"
		role="alert"
	>
		<Icon name="alert" size={16} class="mt-0.5 shrink-0" />
		<p>
			<strong>{m.entries_module_missing()}</strong>
			{m.entries_module_missing_hint({ endpoint: '/inventory/*', folder: 'backend/' })}
		</p>
	</div>
{/if}

<div class="card overflow-hidden">
	<div class="table-wrap">
		<table class="data-table">
			<thead>
				<tr>
					<th scope="col">{m.entries_col_date()}</th>
					<th scope="col">{m.entries_col_supplier()}</th>
					<th scope="col">{m.entries_col_document()}</th>
					<th scope="col">{m.entries_col_source()}</th>
					<th scope="col">{m.entries_col_loaded_by()}</th>
					<th scope="col" class="num">{m.entries_col_units()}</th>
					<th scope="col" class="num">{m.entries_col_cost()}</th>
					<th scope="col">{m.entries_col_status()}</th>
					<th scope="col"><span class="sr-only">{m.common_actions()}</span></th>
				</tr>
			</thead>
			<tbody>
				{#each data.entries as entry (entry.id)}
					{@const icono = ICONO[entry.source] ?? 'edit'}
					<tr class:opacity-60={entry.status === 'anulada'}>
						<td class="whitespace-nowrap text-xs">{formatDateTime(entry.created_at)}</td>
						<td class="max-w-[14rem] truncate">{entry.supplier ?? '—'}</td>
						<td class="font-mono text-xs">{entry.document_number ?? '—'}</td>
						<td>
							<span class="badge bg-[var(--surface-sunken)] text-[var(--text-muted)]">
								<Icon name={icono} size={11} />
								{origenRotulo(entry.source)}
							</span>
						</td>
						<td class="text-xs">{entry.user_name ?? `#${entry.user_id}`}</td>
						<td class="num tabular-nums">{formatInt(entry.items_count)}</td>
						<td class="num tabular-nums">{formatMoney(entry.total_cost)}</td>
						<td>
							{#if entry.status === 'anulada'}
								<span class="badge bg-[var(--negative-bg)] text-[var(--negative)]">
									<Icon name="close" size={11} />
									{m.entries_status_cancelled()}
								</span>
							{:else}
								<span class="badge bg-[var(--positive-bg)] text-[var(--positive)]">
									<Icon name="check" size={11} />
									{m.entries_status_applied()}
								</span>
							{/if}
						</td>
						<td>
							<div class="flex justify-end gap-1">
								<button
									type="button"
									class="rounded-lg p-1.5 text-[var(--text-subtle)] hover:bg-[var(--surface-sunken)] hover:text-[var(--accent)]"
									onclick={() => (detalle = entry)}
									aria-label={m.entries_view_detail({ entry: entry.id })}
								>
									<Icon name="eye" size={15} />
								</button>
								{#if entry.status === 'aplicada'}
									<button
										type="button"
										class="rounded-lg p-1.5 text-[var(--text-subtle)] hover:bg-[var(--negative-bg)] hover:text-[var(--negative)]"
										onclick={() => (anular = entry)}
										aria-label={m.entries_cancel_entry({ entry: entry.id })}
									>
										<Icon name="undo" size={15} />
									</button>
								{/if}
							</div>
						</td>
					</tr>
				{:else}
					<tr>
						<td colspan="9">
							<EmptyState
								icon="box"
								title={m.entries_none()}
								description={m.entries_none_hint()}
							>
								<a href="/inventario/entradas/nueva" class="btn btn-primary">
									<Icon name="plus" size={15} />
									{m.entries_new()}
								</a>
							</EmptyState>
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
</div>

<!-- ------------------------------------------------------------ detalle -->
<Modal
	open={detalle !== null}
	title={m.entries_detail_title({ entry: detalle?.id ?? '' })}
	description={detalle
		? m.entries_detail_subtitle({
				supplier: detalle.supplier ?? m.entries_no_supplier(),
				date: formatDateTime(detalle.created_at)
			})
		: undefined}
	size="lg"
	onclose={() => (detalle = null)}
>
	{#if detalle}
		<dl class="mb-4 grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-4">
			<dt class="text-[var(--text-subtle)]">{m.entries_col_document()}</dt>
			<dd class="text-[var(--text)]">{detalle.document_number ?? '—'}</dd>
			<dt class="text-[var(--text-subtle)]">{m.entries_col_loaded_by()}</dt>
			<dd class="text-[var(--text)]">{detalle.user_name ?? `#${detalle.user_id}`}</dd>
		</dl>

		{#if detalle.notes}
			<p class="mb-4 rounded-lg bg-[var(--surface-sunken)] p-3 text-sm text-[var(--text-muted)]">
				{detalle.notes}
			</p>
		{/if}

		<div class="table-wrap">
			<table class="data-table">
				<thead>
					<tr>
						<th scope="col">{m.entries_line_product()}</th>
						<th scope="col" class="num">{m.entries_line_quantity()}</th>
						<th scope="col" class="num">{m.entries_line_unit_cost()}</th>
						<th scope="col" class="num">{m.entries_line_subtotal()}</th>
					</tr>
				</thead>
				<tbody>
					{#each detalle.lines as line (line.id_product)}
						<tr>
							<td>{line.name}</td>
							<td class="num tabular-nums">{line.quantity}</td>
							<td class="num tabular-nums">{formatMoney(line.unit_cost)}</td>
							<td class="num font-semibold tabular-nums">{formatMoney(line.subtotal)}</td>
						</tr>
					{/each}
				</tbody>
				<tfoot>
					<tr>
						<td colspan="3" class="text-right font-semibold">{m.entries_total()}</td>
						<td class="num font-bold tabular-nums">{formatMoney(detalle.total_cost)}</td>
					</tr>
				</tfoot>
			</table>
		</div>
	{/if}
</Modal>

<!-- ------------------------------------------------------------- anular -->
<Modal
	open={anular !== null}
	title={m.entries_cancel_title()}
	size="sm"
	onclose={() => (anular = null)}
>
	<p class="text-sm text-[var(--text-muted)]">
		{m.entries_cancel_units({ units: anular?.items_count ?? 0 })}
	</p>
	<p class="mt-2 text-xs text-[var(--text-subtle)]">
		{m.entries_cancel_sold_note()}
	</p>

	{#snippet footer()}
		<button type="button" class="btn btn-ghost" onclick={() => (anular = null)}>{m.common_cancel()}</button>
		<form
			method="POST"
			action="?/anular"
			use:enhance={submit({
				errorTitle: m.entries_cancel_failed(),
				onSuccess: () => (anular = null)
			})}
		>
			<input type="hidden" name="id_entry" value={anular?.id ?? ''} />
			<button type="submit" class="btn btn-danger">
				<Icon name="undo" size={15} />
				{m.entries_cancel_confirm()}
			</button>
		</form>
	{/snippet}
</Modal>
