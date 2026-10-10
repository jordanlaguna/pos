<script lang="ts">
	import { enhance } from '$app/forms';
	import { submit } from '$lib/ui/forms';
	import Icon from '$lib/ui/components/Icon.svelte';
	import PageHeader from '$lib/ui/components/PageHeader.svelte';
	import Modal from '$lib/ui/components/Modal.svelte';
	import EmptyState from '$lib/ui/components/EmptyState.svelte';
	import { formatDateTime, formatInt } from '$lib/ui/format';
	import { m } from '$lib/paraglide/messages.js';
	import type { Category, StockCount, StockCountStatus } from '$lib/domain/types';
	import type { ActionData, PageData } from './$types';
	import Select from '$lib/ui/components/Select.svelte';

	let { data, form }: { data: PageData; form: ActionData } = $props();

	let abriendo = $state(false);
	let submitting = $state(false);

	/** Las categorías para elegir, con la raíz delante de cada hija: «Bebidas › Cervezas». */
	const opciones = $derived.by(() => {
		const porId = new Map(data.categories.map((c: Category) => [c.id, c]));
		return data.categories
			.map((c: Category) => {
				const madre = c.parent_id != null ? porId.get(c.parent_id) : null;
				return { id: c.id, label: madre ? `${madre.name} › ${c.name}` : c.name };
			})
			.sort((a, b) => a.label.localeCompare(b.label));
	});

	function estadoRotulo(status: StockCountStatus): string {
		switch (status) {
			case 'applied':
				return m.counts_status_applied();
			case 'discarded':
				return m.counts_status_discarded();
			default:
				return m.counts_status_open();
		}
	}

	function claseEstado(status: StockCountStatus): string {
		if (status === 'applied') return 'bg-[var(--positive-bg)] text-[var(--positive)]';
		if (status === 'discarded') return 'bg-[var(--negative-bg)] text-[var(--negative)]';
		return 'bg-[var(--warning-bg)] text-[var(--warning)]';
	}

	function alcance(toma: StockCount): string {
		return toma.category_name ?? m.counts_scope_all();
	}
</script>

<PageHeader title={m.counts_title()} description={m.counts_description()}>
	{#snippet actions()}
		<a href="/inventario" class="btn btn-ghost">
			<Icon name="box" size={15} />
			{m.counts_catalog()}
		</a>
		<button type="button" class="btn btn-primary" onclick={() => (abriendo = true)}>
			<Icon name="plus" size={15} />
			{m.counts_new()}
		</button>
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
			{m.entries_module_missing_hint({ endpoint: '/inventory/counts', folder: 'backend/' })}
		</p>
	</div>
{/if}

<div class="card overflow-hidden">
	<div class="table-wrap">
		<table class="data-table">
			<thead>
				<tr>
					<th scope="col">{m.counts_col_date()}</th>
					<th scope="col">{m.counts_col_scope()}</th>
					<th scope="col">{m.counts_col_user()}</th>
					<th scope="col" class="num">{m.counts_col_lines()}</th>
					<th scope="col">{m.counts_col_status()}</th>
					<th scope="col"><span class="sr-only">{m.common_actions()}</span></th>
				</tr>
			</thead>
			<tbody>
				{#each data.counts as toma (toma.id)}
					<tr data-testid="count-row" data-status={toma.status}>
						<td class="whitespace-nowrap text-xs">{formatDateTime(toma.opened_at)}</td>
						<td>{alcance(toma)}</td>
						<td class="text-xs">#{toma.opened_by}</td>
						<td class="num tabular-nums">{formatInt(toma.lines_count)}</td>
						<td>
							<span class="badge {claseEstado(toma.status)}">{estadoRotulo(toma.status)}</span>
						</td>
						<td>
							<div class="flex justify-end">
								<a
									href="/inventario/toma-fisica/{toma.id}"
									class="rounded-lg p-1.5 text-[var(--text-subtle)] hover:bg-[var(--surface-sunken)] hover:text-[var(--accent)]"
									aria-label={m.counts_view({ count: toma.id })}
								>
									<Icon name="eye" size={15} />
								</a>
							</div>
						</td>
					</tr>
				{:else}
					<tr>
						<td colspan="6">
							<EmptyState icon="grid" title={m.counts_none()} description={m.counts_none_hint()}>
								<button type="button" class="btn btn-primary" onclick={() => (abriendo = true)}>
									<Icon name="plus" size={15} />
									{m.counts_new()}
								</button>
							</EmptyState>
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
</div>

<!-- -------------------------------------------------------------- abrir -->
<Modal
	open={abriendo}
	title={m.counts_open_title()}
	description={m.counts_scope_hint()}
	size="sm"
	busy={submitting}
	onclose={() => (abriendo = false)}
>
	<form
		id="form-abrir"
		method="POST"
		action="?/abrir"
		class="space-y-3"
		use:enhance={submit({ setBusy: (v) => (submitting = v), errorTitle: m.count_failed() })}
	>
		<label class="block" for="alcance">
			<span class="label">{m.counts_scope_label()}</span>
			<!-- Sin `bind:value`: lo elegido antes de hidratar se perdería; la
			     primera opción va marcada con `selected` (trampa conocida). -->
			<Select id="alcance" name="category_id">
				<option value="" selected>{m.counts_scope_all()}</option>
				{#each opciones as opcion (opcion.id)}
					<option value={String(opcion.id)}>{opcion.label}</option>
				{/each}
			</Select>
		</label>
		<label class="block" for="notas">
			<span class="label">{m.counts_notes_label()}</span>
			<input id="notas" name="notes" type="text" class="input" maxlength="255" placeholder={m.counts_notes_placeholder()} />
		</label>
		{#if form?.errors?.form}
			<p class="rounded-lg bg-[var(--negative-bg)] p-2 text-sm text-[var(--negative)]" role="alert">
				{form.errors.form}
			</p>
		{/if}
	</form>
	{#snippet footer()}
		<button type="button" class="btn btn-ghost" onclick={() => (abriendo = false)}>{m.common_cancel()}</button>
		<button type="submit" form="form-abrir" class="btn btn-primary" disabled={submitting}>
			<Icon name="check" size={15} />
			{m.counts_open_confirm()}
		</button>
	{/snippet}
</Modal>
