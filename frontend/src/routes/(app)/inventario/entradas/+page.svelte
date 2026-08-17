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
	import type { StockEntry } from '$lib/domain/types';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	let detalle = $state<StockEntry | null>(null);
	let anular = $state<StockEntry | null>(null);

	const ORIGEN: Record<string, { texto: string; icono: 'edit' | 'grid' | 'receipt' }> = {
		manual: { texto: 'Manual', icono: 'edit' },
		excel: { texto: 'Excel', icono: 'grid' },
		xml: { texto: 'XML Hacienda', icono: 'receipt' }
	};

	// El alta termina en redirect, así que el aviso no puede salir de enhance.
	let avisada = $state<string | null>(null);
	$effect(() => {
		const creada = page.url.searchParams.get('creada');
		if (creada && creada !== avisada) {
			avisada = creada;
			toasts.success('Entrada registrada', 'El stock ya está actualizado.');
		}
	});
</script>

<PageHeader
	title="Entradas de inventario"
	description="Historial de mercadería recibida. Cada carga deja constancia de quién, cuándo y de dónde."
>
	{#snippet actions()}
		<a href="/inventario" class="btn btn-ghost">
			<Icon name="box" size={15} />
			Catálogo
		</a>
		<a href="/inventario/entradas/nueva" class="btn btn-primary">
			<Icon name="plus" size={15} />
			Nueva entrada
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
			<strong>El módulo de entradas no está disponible.</strong> El backend no expone
			<code>/inventory/*</code>. Actualizá el FastAPI de <code>backend/</code> y corré la
			migración.
		</p>
	</div>
{/if}

<div class="card overflow-hidden">
	<div class="table-wrap">
		<table class="data-table">
			<thead>
				<tr>
					<th scope="col">Fecha</th>
					<th scope="col">Proveedor</th>
					<th scope="col">Documento</th>
					<th scope="col">Origen</th>
					<th scope="col">Cargó</th>
					<th scope="col" class="num">Unidades</th>
					<th scope="col" class="num">Costo</th>
					<th scope="col">Estado</th>
					<th scope="col"><span class="sr-only">Acciones</span></th>
				</tr>
			</thead>
			<tbody>
				{#each data.entries as entry (entry.id)}
					{@const origen = ORIGEN[entry.source] ?? ORIGEN.manual}
					<tr class:opacity-60={entry.status === 'anulada'}>
						<td class="whitespace-nowrap text-xs">{formatDateTime(entry.created_at)}</td>
						<td class="max-w-[14rem] truncate">{entry.supplier ?? '—'}</td>
						<td class="font-mono text-xs">{entry.document_number ?? '—'}</td>
						<td>
							<span class="badge bg-[var(--surface-sunken)] text-[var(--text-muted)]">
								<Icon name={origen.icono} size={11} />
								{origen.texto}
							</span>
						</td>
						<td class="text-xs">{entry.user_name ?? `#${entry.user_id}`}</td>
						<td class="num tabular-nums">{formatInt(entry.items_count)}</td>
						<td class="num tabular-nums">{formatMoney(entry.total_cost)}</td>
						<td>
							{#if entry.status === 'anulada'}
								<span class="badge bg-[var(--negative-bg)] text-[var(--negative)]">
									<Icon name="close" size={11} />
									Anulada
								</span>
							{:else}
								<span class="badge bg-[var(--positive-bg)] text-[var(--positive)]">
									<Icon name="check" size={11} />
									Aplicada
								</span>
							{/if}
						</td>
						<td>
							<div class="flex justify-end gap-1">
								<button
									type="button"
									class="rounded-lg p-1.5 text-[var(--text-subtle)] hover:bg-[var(--surface-sunken)] hover:text-[var(--accent)]"
									onclick={() => (detalle = entry)}
									aria-label="Ver detalle de la entrada {entry.id}"
								>
									<Icon name="eye" size={15} />
								</button>
								{#if entry.status === 'aplicada'}
									<button
										type="button"
										class="rounded-lg p-1.5 text-[var(--text-subtle)] hover:bg-[var(--negative-bg)] hover:text-[var(--negative)]"
										onclick={() => (anular = entry)}
										aria-label="Anular la entrada {entry.id}"
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
								title="Todavía no hay entradas"
								description="Cargá la primera factura de proveedor para empezar a llevar el historial."
							>
								<a href="/inventario/entradas/nueva" class="btn btn-primary">
									<Icon name="plus" size={15} />
									Nueva entrada
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
	title="Entrada #{detalle?.id ?? ''}"
	description={detalle
		? `${detalle.supplier ?? 'Sin proveedor'} · ${formatDateTime(detalle.created_at)}`
		: undefined}
	size="lg"
	onclose={() => (detalle = null)}
>
	{#if detalle}
		<dl class="mb-4 grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-4">
			<dt class="text-[var(--text-subtle)]">Documento</dt>
			<dd class="text-[var(--text)]">{detalle.document_number ?? '—'}</dd>
			<dt class="text-[var(--text-subtle)]">Cargó</dt>
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
						<th scope="col">Producto</th>
						<th scope="col" class="num">Cantidad</th>
						<th scope="col" class="num">Costo unit.</th>
						<th scope="col" class="num">Subtotal</th>
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
						<td colspan="3" class="text-right font-semibold">Total</td>
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
	title="Anular entrada"
	size="sm"
	onclose={() => (anular = null)}
>
	<p class="text-sm text-[var(--text-muted)]">
		Se van a restar <strong class="text-[var(--text)]">{anular?.items_count ?? 0}</strong>
		unidades del inventario, dejándolo como estaba antes de esta carga.
	</p>
	<p class="mt-2 text-xs text-[var(--text-subtle)]">
		Si parte de esa mercadería ya se vendió, el backend no va a permitir la anulación: el stock
		quedaría en negativo. En ese caso hay que ajustarlo a mano.
	</p>

	{#snippet footer()}
		<button type="button" class="btn btn-ghost" onclick={() => (anular = null)}>Cancelar</button>
		<form
			method="POST"
			action="?/anular"
			use:enhance={submit({
				errorTitle: 'No se pudo anular',
				onSuccess: () => (anular = null)
			})}
		>
			<input type="hidden" name="id_entry" value={anular?.id ?? ''} />
			<button type="submit" class="btn btn-danger">
				<Icon name="undo" size={15} />
				Anular entrada
			</button>
		</form>
	{/snippet}
</Modal>
