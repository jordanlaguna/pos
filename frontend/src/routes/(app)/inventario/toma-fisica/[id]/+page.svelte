<script lang="ts">
	import { enhance } from '$app/forms';
	import { submit } from '$lib/ui/forms';
	import Icon from '$lib/ui/components/Icon.svelte';
	import PageHeader from '$lib/ui/components/PageHeader.svelte';
	import Modal from '$lib/ui/components/Modal.svelte';
	import { formatDateTime, formatInt } from '$lib/ui/format';
	import { m } from '$lib/paraglide/messages.js';
	import type { Product } from '$lib/domain/types';
	import type { ActionData, PageData } from './$types';

	let { data, form }: { data: PageData; form: ActionData } = $props();

	const abierta = $derived(data.count.status === 'open');
	let submitting = $state(false);
	let aplicando = $state(false);
	let descartando = $state(false);

	// ---------------------------------------------------------------- contar

	let busqueda = $state('');
	let elegido = $state<Product | null>(null);
	let contado = $state('');

	const coincidencias = $derived.by(() => {
		const t = busqueda.trim().toLowerCase();
		if (!t) return [];
		return data.products
			.filter((p) => p.name.toLowerCase().includes(t) || p.barcode.includes(t))
			.slice(0, 6);
	});

	function elegir(product: Product) {
		elegido = product;
		contado = '';
		busqueda = '';
	}

	function estadoRotulo(): string {
		if (data.count.status === 'applied') return m.counts_status_applied();
		if (data.count.status === 'discarded') return m.counts_status_discarded();
		return m.counts_status_open();
	}

	function claseDiferencia(diferencia: number): string {
		if (diferencia < 0) return 'bg-[var(--negative-bg)] text-[var(--negative)]';
		if (diferencia > 0) return 'bg-[var(--positive-bg)] text-[var(--positive)]';
		return 'bg-[var(--surface-sunken)] text-[var(--text-muted)]';
	}
</script>

<PageHeader
	title={m.count_title({ count: data.count.id })}
	description={abierta ? m.count_description_open() : m.count_description_closed()}
>
	{#snippet actions()}
		<a href="/inventario/toma-fisica" class="btn btn-ghost">
			<Icon name="back" size={15} />
			{m.count_back()}
		</a>
		{#if abierta && data.isAdmin}
			<button type="button" class="btn btn-ghost" onclick={() => (descartando = true)}>
				<Icon name="trash" size={15} />
				{m.count_discard()}
			</button>
			<button
				type="button"
				class="btn btn-primary"
				disabled={data.count.lines.length === 0}
				onclick={() => (aplicando = true)}
			>
				<Icon name="check" size={15} />
				{m.count_apply()}
			</button>
		{/if}
	{/snippet}
</PageHeader>

<div class="mb-4 flex flex-wrap items-center gap-3 text-sm">
	<span class="badge {abierta ? 'bg-[var(--warning-bg)] text-[var(--warning)]' : 'bg-[var(--surface-sunken)] text-[var(--text-muted)]'}" data-testid="count-status" data-status={data.count.status}>
		{estadoRotulo()}
	</span>
	<span class="text-[var(--text-muted)]">
		{m.count_scope()}: {data.count.category_name ?? m.counts_scope_all()}
	</span>
	{#if data.count.closed_at}
		<span class="text-[var(--text-subtle)]">
			{m.count_closed_on({ date: formatDateTime(data.count.closed_at), user: data.count.closed_by ?? '' })}
		</span>
	{/if}
	{#if data.count.notes}
		<span class="text-[var(--text-subtle)]">· {data.count.notes}</span>
	{/if}
</div>

<div class="grid gap-4 {abierta ? 'lg:grid-cols-[1fr_2fr]' : ''}">
	{#if abierta}
		<!-- ------------------------------------------------------- contar -->
		<div class="card h-fit space-y-3 p-4">
			<div class="relative">
				<span class="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-[var(--text-subtle)]">
					<Icon name="search" size={15} />
				</span>
				<input
					bind:value={busqueda}
					type="search"
					placeholder={m.count_search_placeholder()}
					aria-label={m.count_search_label()}
					class="input pl-9"
				/>
				{#if coincidencias.length}
					<ul
						class="absolute inset-x-0 top-[calc(100%+0.25rem)] z-20 max-h-72 overflow-y-auto rounded-lg border border-[var(--border)] bg-[var(--surface-raised)] p-1 shadow-xl"
					>
						{#each coincidencias as product (product.id_product)}
							<li>
								<button
									type="button"
									class="flex w-full items-center gap-3 rounded-md px-3 py-2 text-left hover:bg-[var(--surface-sunken)]"
									onclick={() => elegir(product)}
								>
									<span class="min-w-0 flex-1">
										<span class="block truncate text-sm text-[var(--text)]">{product.name}</span>
										<span class="block text-xs text-[var(--text-subtle)]">{product.barcode}</span>
									</span>
								</button>
							</li>
						{/each}
					</ul>
				{/if}
			</div>

			{#if elegido}
				<form
					method="POST"
					action="?/contar"
					class="space-y-3 rounded-lg bg-[var(--surface-sunken)] p-3"
					use:enhance={submit({
						setBusy: (v) => (submitting = v),
						errorTitle: m.count_failed(),
						onSuccess: () => {
							elegido = null;
							contado = '';
						}
					})}
				>
					<p class="text-xs font-semibold tracking-wide text-[var(--text-subtle)] uppercase">
						{m.count_counting()}
					</p>
					<p class="text-sm font-semibold text-[var(--text)]">{elegido.name}</p>
					<input type="hidden" name="id_product" value={elegido.id_product} />
					<label class="block" for="contado">
						<span class="label">{m.count_counted_label()}</span>
						<input
							id="contado"
							name="counted_qty"
							type="number"
							min="0"
							step="1"
							class="input"
							required
							bind:value={contado}
							aria-label={m.count_counted_of({ product: elegido.name })}
						/>
					</label>
					{#if form?.action === 'contar' && form?.errors?.form}
						<p class="rounded-lg bg-[var(--negative-bg)] p-2 text-sm text-[var(--negative)]" role="alert">
							{form.errors.form}
						</p>
					{/if}
					<div class="flex gap-2">
						<button type="submit" class="btn btn-primary" disabled={submitting || contado === ''}>
							<Icon name="check" size={15} />
							{m.count_record()}
						</button>
						<button type="button" class="btn btn-ghost" onclick={() => (elegido = null)}>
							{m.count_cancel_line()}
						</button>
					</div>
				</form>
			{:else}
				<p class="text-sm text-[var(--text-subtle)]">{m.count_pending_hint()}</p>
			{/if}
		</div>
	{/if}

	<!-- --------------------------------------------------------- líneas -->
	<div class="card overflow-hidden">
		<div class="table-wrap">
			<table class="data-table">
				<thead>
					<tr>
						<th scope="col">{m.count_col_product()}</th>
						<th scope="col" class="num">{m.count_col_system()}</th>
						<th scope="col" class="num">{m.count_col_counted()}</th>
						<th scope="col" class="num">{m.count_col_difference()}</th>
						<th scope="col">{m.count_col_user()}</th>
					</tr>
				</thead>
				<tbody>
					{#each data.count.lines as linea (`${linea.id_product}-${linea.lot_id ?? 0}`)}
						<tr data-testid="count-line" data-difference={linea.difference}>
							<td>{linea.name}</td>
							<td class="num tabular-nums text-[var(--text-muted)]">{formatInt(linea.system_qty)}</td>
							<td class="num tabular-nums">{formatInt(linea.counted_qty)}</td>
							<td class="num">
								<span class="badge tabular-nums {claseDiferencia(linea.difference)}">
									{linea.difference > 0 ? `+${formatInt(linea.difference)}` : formatInt(linea.difference)}
								</span>
							</td>
							<td class="text-xs">#{linea.counted_by}</td>
						</tr>
					{:else}
						<tr>
							<td colspan="5" class="p-6 text-center text-sm text-[var(--text-subtle)]">
								{m.count_no_lines()}
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	</div>
</div>

<!-- -------------------------------------------------------------- aplicar -->
<Modal open={aplicando} title={m.count_apply_title()} size="sm" busy={submitting} onclose={() => (aplicando = false)}>
	<p class="text-sm text-[var(--text-muted)]">{m.count_apply_note()}</p>
	{#if form?.action === 'aplicar' && form?.errors?.form}
		<p class="mt-3 rounded-lg bg-[var(--negative-bg)] p-2 text-sm text-[var(--negative)]" role="alert">
			{form.errors.form}
		</p>
	{/if}
	{#snippet footer()}
		<button type="button" class="btn btn-ghost" onclick={() => (aplicando = false)}>{m.common_cancel()}</button>
		<form
			method="POST"
			action="?/aplicar"
			use:enhance={submit({ setBusy: (v) => (submitting = v), onSuccess: () => (aplicando = false) })}
		>
			<button type="submit" class="btn btn-primary" disabled={submitting}>
				<Icon name="check" size={15} />
				{m.count_apply_confirm()}
			</button>
		</form>
	{/snippet}
</Modal>

<!-- ------------------------------------------------------------ descartar -->
<Modal open={descartando} title={m.count_discard_title()} size="sm" busy={submitting} onclose={() => (descartando = false)}>
	<p class="text-sm text-[var(--text-muted)]">{m.count_discard_note()}</p>
	{#snippet footer()}
		<button type="button" class="btn btn-ghost" onclick={() => (descartando = false)}>{m.common_cancel()}</button>
		<form
			method="POST"
			action="?/descartar"
			use:enhance={submit({ setBusy: (v) => (submitting = v), onSuccess: () => (descartando = false) })}
		>
			<button type="submit" class="btn btn-danger" disabled={submitting}>
				<Icon name="trash" size={15} />
				{m.count_discard_confirm()}
			</button>
		</form>
	{/snippet}
</Modal>
