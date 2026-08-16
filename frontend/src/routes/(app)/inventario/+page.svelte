<script lang="ts">
	import { enhance } from '$app/forms';
	import { submit } from '$lib/forms';
	import Icon from '$lib/components/Icon.svelte';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import Modal from '$lib/components/Modal.svelte';
	import Field from '$lib/components/Field.svelte';
	import EmptyState from '$lib/components/EmptyState.svelte';
	import Spinner from '$lib/components/Spinner.svelte';
	import { toasts } from '$lib/stores/toast.svelte';
	import { formatMoney } from '$lib/money';
	import { formatInt } from '$lib/format';
	import type { Product } from '$lib/types';
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
		toasts.error('No se pudo generar un código libre. Escribilo a mano.');
	}

</script>

<PageHeader title="Inventario" description="Productos, existencias y categorías.">
	{#snippet actions()}
		<a href="/inventario/entradas" class="btn btn-ghost">
			<Icon name="download" size={15} />
			Entradas
		</a>
		<button type="button" class="btn btn-ghost" onclick={() => (categoryModal = true)}>
			<Icon name="tag" size={15} />
			Nueva categoría
		</button>
		<button
			type="button"
			class="btn btn-primary"
			onclick={openCreate}
			disabled={data.categories.length === 0}
			title={data.categories.length === 0 ? 'Creá una categoría primero' : undefined}
		>
			<Icon name="plus" size={15} />
			Nuevo producto
		</button>
	{/snippet}
</PageHeader>

<div class="mb-4 grid gap-3 sm:grid-cols-3">
	<div class="card p-3">
		<p class="text-xs font-semibold tracking-wide text-[var(--text-subtle)] uppercase">
			Productos
		</p>
		<p class="mt-1 text-xl font-bold text-[var(--text)]">{formatInt(data.products.length)}</p>
	</div>
	<div class="card p-3">
		<p class="text-xs font-semibold tracking-wide text-[var(--text-subtle)] uppercase">
			Valor del inventario
		</p>
		<p class="mt-1 text-xl font-bold text-[var(--text)]">{formatMoney(inventoryValue)}</p>
	</div>
	<div class="card p-3">
		<p class="text-xs font-semibold tracking-wide text-[var(--text-subtle)] uppercase">
			Stock bajo
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
		<label class="label" for="inv-buscar">Buscar</label>
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
				placeholder="Nombre, código o descripción…"
				class="input pl-9"
			/>
		</div>
	</div>

	<div>
		<label class="label" for="inv-categoria">Categoría</label>
		<select id="inv-categoria" bind:value={categoryFilter} class="input w-44">
			<option value="todas">Todas</option>
			{#each data.categories as category (category.id)}
				<option value={category.id}>{category.name}</option>
			{/each}
		</select>
	</div>

	<label class="flex cursor-pointer items-center gap-2 pb-2 text-sm text-[var(--text-muted)]">
		<input type="checkbox" bind:checked={onlyLowStock} class="h-4 w-4 accent-[var(--accent)]" />
		Solo stock bajo
	</label>
</div>

<div class="card overflow-hidden">
	<div class="table-wrap">
		<table class="data-table">
			<thead>
				<tr>
					<th scope="col">Producto</th>
					<th scope="col">Código</th>
					<th scope="col">Categoría</th>
					<th scope="col" class="num">Precio</th>
					<th scope="col" class="num">Stock</th>
					<th scope="col"><span class="sr-only">Acciones</span></th>
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
									aria-label="Editar {product.name}"
								>
									<Icon name="edit" size={15} />
								</button>
								<button
									type="button"
									class="rounded-lg p-1.5 text-[var(--text-subtle)] hover:bg-[var(--negative-bg)] hover:text-[var(--negative)]"
									onclick={() => (deleteTarget = product)}
									aria-label="Eliminar {product.name}"
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
								title="Sin productos"
								description={search || categoryFilter !== 'todas' || onlyLowStock
									? 'Ningún producto coincide con los filtros.'
									: 'Agregá tu primer producto para empezar a vender.'}
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
	title={editing ? 'Editar producto' : 'Nuevo producto'}
	description={editing ? editing.name : 'Los campos marcados son obligatorios.'}
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
			label="Nombre"
			name="name"
			bind:value={fName}
			required
			error={form?.errors?.name}
			class="sm:col-span-2"
		/>
		<Field
			label="Descripción"
			name="description"
			bind:value={fDescription}
			required
			error={form?.errors?.description}
			class="sm:col-span-2"
		/>

		<Field
			label="Precio"
			name="price"
			bind:value={fPrice}
			inputmode="decimal"
			required
			error={form?.errors?.price}
		/>
		<Field
			label="Stock"
			name="stock"
			bind:value={fStock}
			inputmode="numeric"
			required
			error={form?.errors?.stock}
		/>

		<div class="sm:col-span-2">
			<Field
				label="Código de barras"
				name="barcode"
				bind:value={fBarcode}
				icon="barcode"
				required
				error={form?.errors?.barcode}
				hint="Escaneá el código real o generá uno interno."
			>
				<button
					type="button"
					class="rounded p-1.5 text-[var(--text-subtle)] hover:text-[var(--accent)]"
					onclick={generateBarcode}
					title="Generar código interno"
					aria-label="Generar código de barras interno"
				>
					<Icon name="refresh" size={15} />
				</button>
			</Field>
		</div>

		<div class="sm:col-span-2">
			<label class="label" for="product-category">Categoría *</label>
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
			Cancelar
		</button>
		<button type="submit" form="product-form" class="btn btn-primary" disabled={submitting}>
			{#if submitting}
				<Spinner size={15} />
				Guardando…
			{:else}
				<Icon name="check" size={15} />
				{editing ? 'Guardar cambios' : 'Agregar producto'}
			{/if}
		</button>
	{/snippet}
</Modal>

<!-- ------------------------------------------------------- categoría -->
<Modal
	open={categoryModal}
	title="Nueva categoría"
	size="sm"
	onclose={() => (categoryModal = false)}
>
	<form id="category-form" method="POST" action="?/crearCategoria" use:enhance={submit({ onSuccess: () => (categoryModal = false) })}>
		<Field
			label="Nombre"
			name="name"
			required
			placeholder="Ej.: Congelados"
			error={form?.errors?.name}
		/>
	</form>

	{#snippet footer()}
		<button type="button" class="btn btn-ghost" onclick={() => (categoryModal = false)}>
			Cancelar
		</button>
		<button type="submit" form="category-form" class="btn btn-primary">
			<Icon name="check" size={15} />
			Crear
		</button>
	{/snippet}
</Modal>

<!-- ---------------------------------------------------------- borrar -->
<Modal
	open={deleteTarget !== null}
	title="Eliminar producto"
	size="sm"
	onclose={() => (deleteTarget = null)}
>
	<p class="text-sm text-[var(--text-muted)]">
		¿Seguro que querés eliminar
		<strong class="text-[var(--text)]">{deleteTarget?.name}</strong>? Esta acción no se puede
		deshacer.
	</p>
	<p class="mt-2 text-xs text-[var(--text-subtle)]">
		Si el producto ya tiene ventas registradas, el backend no permitirá borrarlo para no
		romper el histórico de facturas.
	</p>

	{#snippet footer()}
		<button type="button" class="btn btn-ghost" onclick={() => (deleteTarget = null)}>
			Cancelar
		</button>
		<form method="POST" action="?/eliminar" use:enhance={submit({ onSuccess: () => (deleteTarget = null) })}>
			<input type="hidden" name="id_product" value={deleteTarget?.id_product ?? ''} />
			<button type="submit" class="btn btn-danger">
				<Icon name="trash" size={15} />
				Eliminar
			</button>
		</form>
	{/snippet}
</Modal>
