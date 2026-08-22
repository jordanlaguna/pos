<script lang="ts">
	import { enhance } from '$app/forms';
	import { submit } from '$lib/ui/forms';
	import Icon from '$lib/ui/components/Icon.svelte';
	import PageHeader from '$lib/ui/components/PageHeader.svelte';
	import Modal from '$lib/ui/components/Modal.svelte';
	import Field from '$lib/ui/components/Field.svelte';
	import EmptyState from '$lib/ui/components/EmptyState.svelte';
	import Spinner from '$lib/ui/components/Spinner.svelte';
	import { toasts } from '$lib/ui/stores/toast.svelte';
	import { formatMoney } from '$lib/domain/money';
	import { formatInt } from '$lib/ui/format';
	import { m } from '$lib/paraglide/messages.js';
	import type { Product } from '$lib/domain/types';
	import type { ActionData, PageData } from './$types';

	let { data, form }: { data: PageData; form: ActionData } = $props();

	const LOW_STOCK = 10;

	let search = $state('');
	let categoryFilter = $state<number | 'todas'>('todas');
	let onlyLowStock = $state(false);

	let productModal = $state(false);
	let categoryModal = $state(false);
	let deleteTarget = $state<Product | null>(null);
	let editing = $state<Product | null>(null);
	let submitting = $state(false);

	// Campos del formulario de producto.
	let fName = $state('');
	let fDescription = $state('');
	let fPrice = $state('');
	let fStock = $state('');
	let fBarcode = $state('');
	let fCategory = $state('');

	const categoryName = $derived((id: number) =>
		data.categories.find((c) => c.id === id)?.name ?? '—'
	);

	const filtered = $derived.by(() => {
		const term = search.trim().toLowerCase();
		return data.products.filter((p) => {
			if (categoryFilter !== 'todas' && p.category_id !== categoryFilter) return false;
			if (onlyLowStock && p.stock > LOW_STOCK) return false;
			if (!term) return true;
			return (
				p.name.toLowerCase().includes(term) ||
				p.barcode.toLowerCase().includes(term) ||
				p.description.toLowerCase().includes(term)
			);
		});
	});

	const inventoryValue = $derived(
		data.products.reduce((acc, p) => acc + Number(p.price) * p.stock, 0)
	);
	const lowStockCount = $derived(data.products.filter((p) => p.stock <= LOW_STOCK).length);

	function openCreate() {
		editing = null;
		fName = '';
		fDescription = '';
		fPrice = '';
		fStock = '';
		fBarcode = '';
		fCategory = String(data.categories[0]?.id ?? '');
		productModal = true;
	}

	function openEdit(product: Product) {
		editing = product;
		fName = product.name;
		fDescription = product.description;
		fPrice = String(product.price);
		fStock = String(product.stock);
		fBarcode = product.barcode;
		fCategory = String(product.category_id);
		productModal = true;
	}

	/**
	 * Genera un código de barras libre. El original completaba con 6 dígitos al
	 * azar en cuanto se escribían 3 caracteres, lo que pisaba lo que el usuario
	 * seguía tecleando; aquí es un botón explícito y comprueba que no exista.
	 */
	function generateBarcode() {
		for (let attempt = 0; attempt < 50; attempt++) {
			const candidate = `750${Math.floor(100000000 + Math.random() * 899999999)}`;
			if (!data.products.some((p) => p.barcode === candidate)) {
				fBarcode = candidate;
				return;
			}
		}
		toasts.error(m.inventory_barcode_failed());
	}

</script>

<PageHeader title={m.inventory_title()} description={m.inventory_description()}>
	{#snippet actions()}
		<a href="/inventario/entradas" class="btn btn-ghost">
			<Icon name="download" size={15} />
			{m.inventory_entries()}
		</a>
		<button type="button" class="btn btn-ghost" onclick={() => (categoryModal = true)}>
			<Icon name="tag" size={15} />
			{m.inventory_new_category()}
		</button>
		<button
			type="button"
			class="btn btn-primary"
			onclick={openCreate}
			disabled={data.categories.length === 0}
			title={data.categories.length === 0 ? m.inventory_category_first() : undefined}
		>
			<Icon name="plus" size={15} />
			{m.inventory_new_product()}
		</button>
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
			{m.inventory_value()}
		</p>
		<p class="mt-1 text-xl font-bold text-[var(--text)]">{formatMoney(inventoryValue)}</p>
	</div>
	<div class="card p-3">
		<p class="text-xs font-semibold tracking-wide text-[var(--text-subtle)] uppercase">
			{m.inventory_low_stock()}
		</p>
		<p
			class="mt-1 text-xl font-bold {lowStockCount
				? 'text-[var(--warning)]'
				: 'text-[var(--text)]'}"
		>
			{formatInt(lowStockCount)}
		</p>
	</div>
</div>

<div class="card mb-4 flex flex-wrap items-end gap-3 p-3">
	<div class="min-w-[12rem] flex-1">
		<label class="label" for="inv-buscar">{m.common_search()}</label>
		<div class="relative">
			<span
				class="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-[var(--text-subtle)]"
			>
				<Icon name="search" size={15} />
			</span>
			<input
				id="inv-buscar"
				bind:value={search}
				type="search"
				placeholder={m.inventory_search_placeholder()}
				class="input pl-9"
			/>
		</div>
	</div>

	<div>
		<label class="label" for="inv-categoria">{m.inventory_category()}</label>
		<select id="inv-categoria" bind:value={categoryFilter} class="input w-44">
			<option value="todas">{m.common_all_f()}</option>
			{#each data.categories as category (category.id)}
				<option value={category.id}>{category.name}</option>
			{/each}
		</select>
	</div>

	<label class="flex cursor-pointer items-center gap-2 pb-2 text-sm text-[var(--text-muted)]">
		<input type="checkbox" bind:checked={onlyLowStock} class="h-4 w-4 accent-[var(--accent)]" />
		{m.inventory_only_low_stock()}
	</label>
</div>

<div class="card overflow-hidden">
	<div class="table-wrap">
		<table class="data-table">
			<thead>
				<tr>
					<th scope="col">{m.inventory_col_product()}</th>
					<th scope="col">{m.inventory_col_barcode()}</th>
					<th scope="col">{m.inventory_col_category()}</th>
					<th scope="col" class="num">{m.inventory_col_price()}</th>
					<th scope="col" class="num">{m.inventory_col_stock()}</th>
					<th scope="col"><span class="sr-only">{m.common_actions()}</span></th>
				</tr>
			</thead>
			<tbody>
				{#each filtered as product (product.id_product)}
					<tr>
						<td>
							<p class="font-medium text-[var(--text)]">{product.name}</p>
							<p class="max-w-xs truncate text-xs text-[var(--text-subtle)]">
								{product.description}
							</p>
						</td>
						<td class="font-mono text-xs">{product.barcode}</td>
						<td>{categoryName(product.category_id)}</td>
						<td class="num tabular-nums">{formatMoney(product.price)}</td>
						<td class="num">
							<span
								class="badge tabular-nums {product.stock <= 0
									? 'bg-[var(--negative-bg)] text-[var(--negative)]'
									: product.stock <= LOW_STOCK
										? 'bg-[var(--warning-bg)] text-[var(--warning)]'
										: 'bg-[var(--surface-sunken)] text-[var(--text-muted)]'}"
							>
								{#if product.stock <= LOW_STOCK}
									<Icon name="alert" size={11} />
								{/if}
								{product.stock}
							</span>
						</td>
						<td>
							<div class="flex justify-end gap-1">
								<button
									type="button"
									class="rounded-lg p-1.5 text-[var(--text-subtle)] hover:bg-[var(--surface-sunken)] hover:text-[var(--accent)]"
									onclick={() => openEdit(product)}
									aria-label={m.inventory_edit_product({ product: product.name })}
								>
									<Icon name="edit" size={15} />
								</button>
								<button
									type="button"
									class="rounded-lg p-1.5 text-[var(--text-subtle)] hover:bg-[var(--negative-bg)] hover:text-[var(--negative)]"
									onclick={() => (deleteTarget = product)}
									aria-label={m.inventory_delete_product({ product: product.name })}
								>
									<Icon name="trash" size={15} />
								</button>
							</div>
						</td>
					</tr>
				{:else}
					<tr>
						<td colspan="6">
							<EmptyState
								icon="box"
								title={m.inventory_no_products()}
								description={search || categoryFilter !== 'todas' || onlyLowStock
									? m.inventory_no_match()
									: m.inventory_add_first()}
								compact
							/>
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
</div>

<!-- --------------------------------------------------- alta / edición -->
<Modal
	open={productModal}
	title={editing ? m.inventory_edit_title() : m.inventory_new_product()}
	description={editing ? editing.name : m.common_required_fields()}
	busy={submitting}
	onclose={() => (productModal = false)}
>
	<form
		id="product-form"
		method="POST"
		action={editing ? '?/actualizar' : '?/crear'}
		use:enhance={submit({
			onSuccess: () => (productModal = false),
			setBusy: (v) => (submitting = v)
		})}
		class="grid gap-4 sm:grid-cols-2"
	>
		{#if editing}
			<input type="hidden" name="id_product" value={editing.id_product} />
		{/if}

		<Field
			label={m.inventory_label_name()}
			name="name"
			bind:value={fName}
			required
			error={form?.errors?.name}
			class="sm:col-span-2"
		/>
		<Field
			label={m.inventory_label_description()}
			name="description"
			bind:value={fDescription}
			required
			error={form?.errors?.description}
			class="sm:col-span-2"
		/>

		<Field
			label={m.inventory_label_price()}
			name="price"
			bind:value={fPrice}
			inputmode="decimal"
			required
			error={form?.errors?.price}
		/>
		<Field
			label={m.inventory_label_stock()}
			name="stock"
			bind:value={fStock}
			inputmode="numeric"
			required
			error={form?.errors?.stock}
		/>

		<div class="sm:col-span-2">
			<Field
				label={m.inventory_label_barcode()}
				name="barcode"
				bind:value={fBarcode}
				icon="barcode"
				required
				error={form?.errors?.barcode}
				hint={m.inventory_barcode_hint()}
			>
				<button
					type="button"
					class="rounded p-1.5 text-[var(--text-subtle)] hover:text-[var(--accent)]"
					onclick={generateBarcode}
					title={m.inventory_generate_barcode()}
					aria-label={m.inventory_generate_barcode_label()}
				>
					<Icon name="refresh" size={15} />
				</button>
			</Field>
		</div>

		<div class="sm:col-span-2">
			<label class="label" for="product-category">{m.inventory_label_category_required()}</label>
			<select
				id="product-category"
				name="category_id"
				bind:value={fCategory}
				class="input"
				required
				aria-invalid={form?.errors?.category_id ? 'true' : undefined}
			>
				{#each data.categories as category (category.id)}
					<option value={String(category.id)}>{category.name}</option>
				{/each}
			</select>
			{#if form?.errors?.category_id}
				<p class="mt-1 text-xs text-[var(--negative)]">{form.errors.category_id}</p>
			{/if}
		</div>
	</form>

	{#snippet footer()}
		<button
			type="button"
			class="btn btn-ghost"
			onclick={() => (productModal = false)}
			disabled={submitting}
		>
			{m.common_cancel()}
		</button>
		<button type="submit" form="product-form" class="btn btn-primary" disabled={submitting}>
			{#if submitting}
				<Spinner size={15} />
				{m.common_saving()}
			{:else}
				<Icon name="check" size={15} />
				{editing ? m.common_save_changes() : m.inventory_add_product()}
			{/if}
		</button>
	{/snippet}
</Modal>

<!-- ------------------------------------------------------- categoría -->
<Modal
	open={categoryModal}
	title={m.inventory_new_category()}
	size="sm"
	onclose={() => (categoryModal = false)}
>
	<form id="category-form" method="POST" action="?/crearCategoria" use:enhance={submit({ onSuccess: () => (categoryModal = false) })}>
		<Field
			label={m.inventory_label_name()}
			name="name"
			required
			placeholder={m.inventory_category_placeholder()}
			error={form?.errors?.name}
		/>
	</form>

	{#snippet footer()}
		<button type="button" class="btn btn-ghost" onclick={() => (categoryModal = false)}>
			{m.common_cancel()}
		</button>
		<button type="submit" form="category-form" class="btn btn-primary">
			<Icon name="check" size={15} />
			{m.common_create()}
		</button>
	{/snippet}
</Modal>

<!-- ---------------------------------------------------------- borrar -->
<Modal
	open={deleteTarget !== null}
	title={m.inventory_delete_title()}
	size="sm"
	onclose={() => (deleteTarget = null)}
>
	<p class="text-sm text-[var(--text-muted)]">
		{m.inventory_delete_confirm()}
		<strong class="text-[var(--text)]">{deleteTarget?.name}</strong>?
		{m.common_cannot_be_undone()}
	</p>
	<p class="mt-2 text-xs text-[var(--text-subtle)]">
		{m.inventory_delete_history_note()}
	</p>

	{#snippet footer()}
		<button type="button" class="btn btn-ghost" onclick={() => (deleteTarget = null)}>
			{m.common_cancel()}
		</button>
		<form method="POST" action="?/eliminar" use:enhance={submit({ onSuccess: () => (deleteTarget = null) })}>
			<input type="hidden" name="id_product" value={deleteTarget?.id_product ?? ''} />
			<button type="submit" class="btn btn-danger">
				<Icon name="trash" size={15} />
				{m.common_delete()}
			</button>
		</form>
	{/snippet}
</Modal>
