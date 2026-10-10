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
	import type { StockExit } from '$lib/domain/types';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	let detalle = $state<StockExit | null>(null);
	let anular = $state<StockExit | null>(null);
	let motivo = $state('');

	// El motivo es de cada anulación: dejarlo puesto haría que la siguiente
	// heredara el porqué de la anterior.
	$effect(() => {
		if (anular === null) motivo = '';
	});

	// El alta termina en redirect, así que el aviso no puede salir de enhance.
	let avisada = $state<string | null>(null);
	$effect(() => {
		const creada = page.url.searchParams.get('creada');
		if (creada && creada !== avisada) {
			avisada = creada;
			toasts.success(m.exits_created_toast(), m.exits_created_detail());
		}
	});
</script>

<PageHeader title={m.exits_title()} description={m.exits_description()}>
	{#snippet actions()}
		<a href="/inventario" class="btn btn-ghost">
			<Icon name="box" size={15} />
			{m.exits_catalog()}
		</a>
		<a href="/inventario/motivos" class="btn btn-ghost">
			<Icon name="tag" size={15} />
			{m.exits_reasons()}
		</a>
		<a href="/inventario/salidas/nueva" class="btn btn-primary">
			<Icon name="plus" size={15} />
			{m.exits_new()}
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
			{m.entries_module_missing_hint({ endpoint: '/inventory/exits', folder: 'backend/' })}
		</p>
	</div>
{/if}

<div class="card overflow-hidden">
	<div class="table-wrap">
		<table class="data-table">
			<thead>
				<tr>
					<th scope="col">{m.exits_col_date()}</th>
					<th scope="col">{m.exits_col_reason()}</th>
					<th scope="col">{m.exits_col_user()}</th>
					<th scope="col" class="num">{m.exits_col_units()}</th>
					<th scope="col" class="num">{m.exits_col_cost()}</th>
					<th scope="col">{m.exits_col_status()}</th>
					<th scope="col"><span class="sr-only">{m.common_actions()}</span></th>
				</tr>
			</thead>
			<tbody>
				{#each data.exits as salida (salida.id)}
					<tr class:opacity-60={salida.status === 'voided'} data-testid="exit-row" data-status={salida.status}>
						<td class="whitespace-nowrap text-xs">{formatDateTime(salida.created_at)}</td>
						<td>
							<span class="badge bg-[var(--surface-sunken)] text-[var(--text-muted)]">
								<Icon name="tag" size={11} />
								{salida.reason_name}
							</span>
						</td>
						<td class="text-xs">{salida.user_name ?? `#${salida.user_id}`}</td>
						<td class="num tabular-nums">{formatInt(salida.items_count)}</td>
						<td class="num tabular-nums">{formatMoney(salida.total_cost)}</td>
						<td>
							{#if salida.status === 'voided'}
								<span class="badge bg-[var(--negative-bg)] text-[var(--negative)]">
									<Icon name="close" size={11} />
									{m.exits_status_voided()}
								</span>
							{:else}
								<span class="badge bg-[var(--positive-bg)] text-[var(--positive)]">
									<Icon name="check" size={11} />
									{m.exits_status_applied()}
								</span>
							{/if}
						</td>
						<td>
							<div class="flex justify-end gap-1">
								<button
									type="button"
									class="rounded-lg p-1.5 text-[var(--text-subtle)] hover:bg-[var(--surface-sunken)] hover:text-[var(--accent)]"
									onclick={() => (detalle = salida)}
									aria-label={m.exits_view_detail({ exit: salida.id })}
								>
									<Icon name="eye" size={15} />
								</button>
								{#if salida.status === 'applied'}
									<button
										type="button"
										class="rounded-lg p-1.5 text-[var(--text-subtle)] hover:bg-[var(--negative-bg)] hover:text-[var(--negative)]"
										onclick={() => (anular = salida)}
										aria-label={m.exits_cancel_exit({ exit: salida.id })}
									>
										<Icon name="undo" size={15} />
									</button>
								{/if}
							</div>
						</td>
					</tr>
				{:else}
					<tr>
						<td colspan="7">
							<EmptyState icon="box" title={m.exits_none()} description={m.exits_none_hint()}>
								<a href="/inventario/salidas/nueva" class="btn btn-primary">
									<Icon name="plus" size={15} />
									{m.exits_new()}
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
	title={m.exits_detail_title({ exit: detalle?.id ?? '' })}
	description={detalle
		? m.exits_detail_subtitle({
				reason: detalle.reason_name,
				date: formatDateTime(detalle.created_at)
			})
		: undefined}
	size="lg"
	onclose={() => (detalle = null)}
>
	{#if detalle}
		<dl class="mb-4 grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-4">
			<dt class="text-[var(--text-subtle)]">{m.exits_col_user()}</dt>
			<dd class="text-[var(--text)]">{detalle.user_name ?? `#${detalle.user_id}`}</dd>
			{#if detalle.status === 'voided'}
				<dt class="text-[var(--text-subtle)]">{m.exits_void_reason()}</dt>
				<dd class="text-[var(--text)]">
					{detalle.void_reason ?? '—'}
					<span class="block text-xs text-[var(--text-subtle)]">
						{m.exits_voided_on({ date: formatDateTime(detalle.voided_at) })}
					</span>
				</dd>
			{/if}
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
						<th scope="col">{m.exits_line_product()}</th>
						<th scope="col" class="num">{m.exits_line_quantity()}</th>
						<th scope="col" class="num">{m.exits_line_unit_cost()}</th>
						<th scope="col" class="num">{m.exits_line_subtotal()}</th>
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
						<td colspan="3" class="text-right font-semibold">{m.exits_total()}</td>
						<td class="num font-bold tabular-nums">{formatMoney(detalle.total_cost)}</td>
					</tr>
				</tfoot>
			</table>
		</div>
	{/if}
</Modal>

<!-- ------------------------------------------------------------- anular -->
<Modal open={anular !== null} title={m.exits_cancel_title()} size="sm" onclose={() => (anular = null)}>
	<p class="text-sm text-[var(--text-muted)]">
		{m.exits_cancel_units({ units: anular?.items_count ?? 0 })}
	</p>

	<label class="mt-4 block" for="motivo-anular">
		<span class="label">{m.exits_cancel_reason_label()}</span>
		<input
			id="motivo-anular"
			form="form-anular"
			name="reason"
			type="text"
			class="input"
			maxlength="255"
			required
			bind:value={motivo}
			placeholder={m.exits_cancel_reason_placeholder()}
		/>
	</label>

	{#snippet footer()}
		<button type="button" class="btn btn-ghost" onclick={() => (anular = null)}>{m.common_cancel()}</button>
		<form
			id="form-anular"
			method="POST"
			action="?/anular"
			use:enhance={submit({
				errorTitle: m.exits_cancel_failed(),
				onSuccess: () => (anular = null)
			})}
		>
			<input type="hidden" name="id_exit" value={anular?.id ?? ''} />
			<button type="submit" class="btn btn-danger">
				<Icon name="undo" size={15} />
				{m.exits_cancel_confirm()}
			</button>
		</form>
	{/snippet}
</Modal>
