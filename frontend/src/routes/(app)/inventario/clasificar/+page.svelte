<script lang="ts">
	import { enhance } from '$app/forms';
	import { submit } from '$lib/ui/forms';
	import Icon from '$lib/ui/components/Icon.svelte';
	import PageHeader from '$lib/ui/components/PageHeader.svelte';
	import EmptyState from '$lib/ui/components/EmptyState.svelte';
	import Spinner from '$lib/ui/components/Spinner.svelte';
	import CabysSearch from '$lib/ui/components/CabysSearch.svelte';
	import { ratePercentText } from '$lib/domain/money';
	import { categoryPath } from '$lib/domain/categories';
	import { formatInt } from '$lib/ui/format';
	import { m } from '$lib/paraglide/messages.js';
	import { SvelteSet } from 'svelte/reactivity';
	import type { CabysEntry } from '$lib/domain/cabys';
	import type { ActionData, PageData } from './$types';

	let { data, form }: { data: PageData; form: ActionData } = $props();

	/**
	 * Asignación de CABYS en lote (RF-20).
	 *
	 * Es para los catálogos que ya estaban cargados cuando llegó F5: cientos de
	 * productos sin clasificar y un puñado de códigos que se repiten. Se elige un
	 * código una vez y se marca a quién le toca.
	 */
	let elegido = $state<CabysEntry | null>(null);
	let seleccion = $state<Set<number>>(new SvelteSet());
	let search = $state('');
	let onlyUnclassified = $state(true);
	let submitting = $state(false);

	const filtered = $derived.by(() => {
		const term = search.trim().toLowerCase();
		return data.products.filter((p) => {
			if (onlyUnclassified && p.cabys_code) return false;
			if (!term) return true;
			return (
				p.name.toLowerCase().includes(term) ||
				p.barcode.toLowerCase().includes(term) ||
				(p.cabys_code ?? '').includes(term)
			);
		});
	});

	const unclassified = $derived(data.products.filter((p) => !p.cabys_code).length);
	/** Los marcados que además están a la vista: es lo que se va a enviar. */
	const enviables = $derived(filtered.filter((p) => seleccion.has(p.id_product)));
	const todosMarcados = $derived(filtered.length > 0 && enviables.length === filtered.length);

	const categoryName = $derived((id: number) => {
		const camino = categoryPath(data.categories, id);
		return camino.length > 0 ? camino.join(' › ') : '—';
	});

	function alternar(id: number) {
		if (seleccion.has(id)) seleccion.delete(id);
		else seleccion.add(id);
	}

	/**
	 * Marca o desmarca **lo que está a la vista**, no el catálogo entero.
	 *
	 * Es la diferencia entre «todos los que estoy viendo» y «todos los que hay»,
	 * y con un filtro puesto la segunda lectura clasificaría cosas que quien
	 * marcó no llegó a ver.
	 */
	function alternarTodos() {
		if (todosMarcados) for (const p of filtered) seleccion.delete(p.id_product);
		else for (const p of filtered) seleccion.add(p.id_product);
	}
</script>

<PageHeader title={m.inventory_classify_title()} description={m.inventory_classify_description()}>
	{#snippet actions()}
		<a href="/inventario" class="btn btn-ghost">
			<Icon name="box" size={15} />
			{m.inventory_classify_back()}
		</a>
	{/snippet}
</PageHeader>

<div class="mb-4 grid gap-3 sm:grid-cols-3">
	<div class="card p-3">
		<p class="text-xs font-semibold tracking-wide text-[var(--text-subtle)] uppercase">
			{m.inventory_products()}
		</p>
		<p class="mt-1 text-xl font-bold text-[var(--text)]">{formatInt(data.products.length)}</p>
	</div>
	<div class="card p-3">
		<p class="text-xs font-semibold tracking-wide text-[var(--text-subtle)] uppercase">
			{m.inventory_classify_pending()}
		</p>
		<p
			class="mt-1 text-xl font-bold {unclassified
				? 'text-[var(--warning)]'
				: 'text-[var(--positive)]'}"
		>
			{formatInt(unclassified)}
		</p>
	</div>
	<div class="card p-3">
		<p class="text-xs font-semibold tracking-wide text-[var(--text-subtle)] uppercase">
			{m.inventory_classify_selected()}
		</p>
		<p class="mt-1 text-xl font-bold text-[var(--text)]">{formatInt(enviables.length)}</p>
	</div>
</div>

<form
	method="POST"
	action="?/asignar"
	use:enhance={submit({
		onSuccess: () => {
			seleccion = new SvelteSet();
			elegido = null;
		},
		setBusy: (v) => (submitting = v)
	})}
>
	<!-- ------------------------------------------------- 1. el código -->
	<div class="card mb-4 p-4">
		<h2 class="mb-3 text-sm font-semibold text-[var(--text)]">
			{m.inventory_classify_step_code()}
		</h2>

		{#if elegido}
			<input type="hidden" name="cabys_code" value={elegido.code} />
			<input type="hidden" name="tax_rate" value={ratePercentText(elegido.tax_rate)} />
			<div
				class="mb-3 flex items-center gap-2 rounded-lg bg-[var(--surface-sunken)] p-2 text-[var(--text)]"
			>
				<Icon name="check" size={15} />
				<span class="font-mono text-xs">{elegido.code}</span>
				<span class="flex-1 truncate text-sm">{elegido.description}</span>
				<span class="badge bg-[var(--surface)] text-[var(--text-muted)]">
					{ratePercentText(elegido.tax_rate)} %
				</span>
				<button
					type="button"
					class="rounded p-1 text-[var(--text-subtle)] hover:text-[var(--negative)]"
					onclick={() => (elegido = null)}
					aria-label={m.inventory_cabys_clear()}
				>
					<Icon name="close" size={15} />
				</button>
			</div>
		{/if}

		<CabysSearch onpick={(entry) => (elegido = entry)} selected={elegido?.code ?? null} />
	</div>

	<!-- --------------------------------------------- 2. los productos -->
	<div class="card overflow-hidden">
		<div class="flex flex-wrap items-end gap-3 border-b border-[var(--border)] p-3">
			<h2 class="w-full text-sm font-semibold text-[var(--text)]">
				{m.inventory_classify_step_products()}
			</h2>

			<div class="min-w-[12rem] flex-1">
				<label class="label" for="clasificar-buscar">{m.common_search()}</label>
				<input
					id="clasificar-buscar"
					bind:value={search}
					type="search"
					placeholder={m.inventory_search_placeholder()}
					class="input"
				/>
			</div>

			<label class="flex cursor-pointer items-center gap-2 pb-2 text-sm text-[var(--text-muted)]">
				<input
					type="checkbox"
					bind:checked={onlyUnclassified}
					class="h-4 w-4 accent-[var(--accent)]"
				/>
				{m.inventory_classify_only_pending()}
			</label>
		</div>

		<div class="table-wrap">
			<table class="data-table">
				<thead>
					<tr>
						<th scope="col" class="w-10">
							<input
								type="checkbox"
								class="h-4 w-4 accent-[var(--accent)]"
								checked={todosMarcados}
								onchange={alternarTodos}
								aria-label={m.inventory_classify_select_all()}
							/>
						</th>
						<th scope="col">{m.inventory_col_product()}</th>
						<th scope="col">{m.inventory_col_category()}</th>
						<th scope="col">{m.inventory_col_cabys()}</th>
						<th scope="col" class="num">{m.inventory_col_tax()}</th>
					</tr>
				</thead>
				<tbody>
					{#each filtered as product (product.id_product)}
						<tr>
							<td>
								<input
									type="checkbox"
									name="ids"
									value={product.id_product}
									class="h-4 w-4 accent-[var(--accent)]"
									checked={seleccion.has(product.id_product)}
									onchange={() => alternar(product.id_product)}
									aria-label={m.inventory_classify_select({ product: product.name })}
								/>
							</td>
							<td>
								<p class="font-medium text-[var(--text)]">{product.name}</p>
								<p class="font-mono text-xs text-[var(--text-subtle)]">{product.barcode}</p>
							</td>
							<td>{categoryName(product.category_id)}</td>
							<td class="font-mono text-xs">
								{#if product.cabys_code}
									{product.cabys_code}
								{:else}
									<span class="text-[var(--text-subtle)]">{m.inventory_unclassified()}</span>
								{/if}
							</td>
							<td class="num tabular-nums">
								{#if product.tax_rate == null}
									<span class="text-xs text-[var(--text-subtle)]">
										{ratePercentText(data.defaultTaxRate)} %
									</span>
								{:else}
									{ratePercentText(product.tax_rate)} %
								{/if}
							</td>
						</tr>
					{:else}
						<tr>
							<td colspan="5">
								<EmptyState
									icon="box"
									title={m.inventory_no_products()}
									description={onlyUnclassified && unclassified === 0
										? m.inventory_classify_all_done()
										: m.inventory_no_match()}
									compact
								/>
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>

		<div
			class="flex flex-wrap items-center justify-between gap-3 border-t border-[var(--border)] p-3"
		>
			{#if form?.errors?.form}
				<p class="text-sm text-[var(--negative)]">{form.errors.form}</p>
			{:else if form?.errors?.cabys_code}
				<p class="text-sm text-[var(--negative)]">{form.errors.cabys_code}</p>
			{:else}
				<p class="text-sm text-[var(--text-muted)]">
					{#if elegido && enviables.length > 0}
						{m.inventory_classify_ready({
							count: enviables.length,
							rate: ratePercentText(elegido.tax_rate)
						})}
					{:else if !elegido}
						{m.inventory_classify_pick_code()}
					{:else}
						{m.inventory_classify_pick_products()}
					{/if}
				</p>
			{/if}

			<button
				type="submit"
				class="btn btn-primary"
				disabled={submitting || !elegido || enviables.length === 0}
			>
				{#if submitting}
					<Spinner size={15} />
					{m.common_saving()}
				{:else}
					<Icon name="check" size={15} />
					{m.inventory_classify_apply({ count: enviables.length })}
				{/if}
			</button>
		</div>
	</div>
</form>
