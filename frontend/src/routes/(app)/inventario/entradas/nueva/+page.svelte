<script lang="ts">
	import { enhance } from '$app/forms';
	import { submit } from '$lib/ui/forms';
	import Icon from '$lib/ui/components/Icon.svelte';
	import PageHeader from '$lib/ui/components/PageHeader.svelte';
	import Field from '$lib/ui/components/Field.svelte';
	import Spinner from '$lib/ui/components/Spinner.svelte';
	import EmptyState from '$lib/ui/components/EmptyState.svelte';
	import { toasts } from '$lib/ui/stores/toast.svelte';
	import { formatMoney, round2 } from '$lib/domain/money';
	import type { ParsedLine, Product } from '$lib/domain/types';
	import type { ActionData, PageData } from './$types';

	let { data, form }: { data: PageData; form: ActionData } = $props();

	type Metodo = 'manual' | 'archivo';
	let metodo = $state<Metodo>('manual');

	// Datos del documento
	let supplier = $state('');
	let documentNumber = $state('');
	let notes = $state('');
	let analizando = $state(false);
	let guardando = $state(false);

	/**
	 * Línea de la vista previa. Es lo que el usuario edita antes de confirmar:
	 * ninguna de estas decisiones toca el inventario hasta darle a ingresar.
	 */
	interface Linea extends ParsedLine {
		key: number;
		incluir: boolean;
		/** Solo para las que no coinciden: darlas de alta en el catálogo. */
		crear: boolean;
		nuevoPrecio: string;
		nuevaCategoria: string;
		nuevoBarcode: string;
	}

	let lineas = $state<Linea[]>([]);
	let secuencia = 0;

	/** Margen sugerido para el precio de venta de un producto nuevo. */
	const MARGEN = 1.3;

	function nuevaLinea(base: Partial<ParsedLine>): Linea {
		const costo = base.unit_cost ?? 0;
		return {
			code: base.code ?? '',
			description: base.description ?? '',
			quantity: base.quantity ?? 1,
			unit_cost: costo,
			matched: base.matched ?? null,
			matched_by: base.matched_by ?? null,
			issue: base.issue,
			key: ++secuencia,
			// Las líneas con problema entran desmarcadas para que se revisen.
			incluir: !base.issue,
			crear: false,
			nuevoPrecio: costo > 0 ? String(round2(costo * MARGEN)) : '',
			nuevaCategoria: String(data.categories[0]?.id ?? ''),
			nuevoBarcode: base.code ?? ''
		};
	}

	// El resultado del análisis llega por `form`; se pasa a estado editable.
	let analizado = $state<string | null>(null);
	$effect(() => {
		const parsed = form && 'parsed' in form ? form.parsed : null;
		const filename = form && 'filename' in form ? String(form.filename) : null;
		if (!parsed || filename === analizado) return;

		analizado = filename;
		lineas = parsed.lines.map((l) => nuevaLinea(l));
		if (parsed.supplier) supplier = parsed.supplier;
		if (parsed.document_number) documentNumber = parsed.document_number;
		for (const aviso of parsed.warnings) toasts.warning(aviso);
	});

	// ------------------------------------------------------------- carga manual

	let busqueda = $state('');
	const coincidencias = $derived.by(() => {
		const t = busqueda.trim().toLowerCase();
		if (!t) return [];
		return data.products
			.filter((p) => p.name.toLowerCase().includes(t) || p.barcode.includes(t))
			.slice(0, 6);
	});

	function agregarManual(product: Product) {
		const yaEsta = lineas.find((l) => l.matched?.id_product === product.id_product);
		if (yaEsta) {
			yaEsta.quantity += 1;
		} else {
			lineas.push(
				nuevaLinea({
					code: product.barcode,
					description: product.name,
					quantity: 1,
					unit_cost: 0,
					matched: {
						id_product: product.id_product,
						name: product.name,
						barcode: product.barcode,
						stock: product.stock,
						price: Number(product.price)
					},
					matched_by: 'barcode'
				})
			);
		}
		busqueda = '';
	}

	// ----------------------------------------------------------------- resumen

	const incluidas = $derived(lineas.filter((l) => l.incluir));
	const sinCoincidencia = $derived(lineas.filter((l) => !l.matched));
	const aCrear = $derived(lineas.filter((l) => l.incluir && !l.matched && l.crear));
	const totalUnidades = $derived(incluidas.reduce((a, l) => a + (Number(l.quantity) || 0), 0));
	const totalCosto = $derived(
		round2(incluidas.reduce((a, l) => a + (Number(l.unit_cost) || 0) * (Number(l.quantity) || 0), 0))
	);

	/** Líneas marcadas que no tienen a dónde ir: ni producto ni alta. */
	const huerfanas = $derived(lineas.filter((l) => l.incluir && !l.matched && !l.crear));

	const listo = $derived(
		incluidas.length > 0 &&
			huerfanas.length === 0 &&
			aCrear.every((l) => l.nuevoBarcode.trim() && Number(l.nuevoPrecio) > 0) &&
			incluidas.every((l) => Number.isInteger(Number(l.quantity)) && Number(l.quantity) > 0)
	);

	/** Carga útil para el backend: producto existente o producto a crear. */
	const payload = $derived(
		incluidas.map((l) =>
			l.matched
				? {
						id_product: l.matched.id_product,
						quantity: Number(l.quantity),
						unit_cost: Number(l.unit_cost) || 0
					}
				: {
						new_product: {
							name: l.description,
							description: l.description,
							barcode: l.nuevoBarcode.trim(),
							price: Number(l.nuevoPrecio),
							category_id: Number(l.nuevaCategoria)
						},
						quantity: Number(l.quantity),
						unit_cost: Number(l.unit_cost) || 0
					}
		)
	);

	const origen = $derived<'manual' | 'excel' | 'xml'>(
		metodo === 'manual'
			? 'manual'
			: analizado?.toLowerCase().endsWith('.xml')
				? 'xml'
				: 'excel'
	);

	function limpiar() {
		lineas = [];
		analizado = null;
		supplier = '';
		documentNumber = '';
		notes = '';
	}
</script>

<PageHeader
	title="Entrada de mercadería"
	description="Sumá stock desde una factura del proveedor o a mano. Nada entra hasta que lo confirmes."
>
	{#snippet actions()}
		<a href="/inventario/entradas" class="btn btn-ghost">
			<Icon name="back" size={15} />
			Ver entradas
		</a>
	{/snippet}
</PageHeader>

<!-- ------------------------------------------------------ cómo cargar -->
<div class="card mb-4 p-4">
	<div class="mb-4 flex flex-wrap gap-2">
		<button
			type="button"
			class="btn {metodo === 'manual' ? 'btn-primary' : 'btn-ghost'}"
			onclick={() => (metodo = 'manual')}
		>
			<Icon name="edit" size={15} />
			Manual
		</button>
		<button
			type="button"
			class="btn {metodo === 'archivo' ? 'btn-primary' : 'btn-ghost'}"
			onclick={() => (metodo = 'archivo')}
		>
			<Icon name="download" size={15} />
			Desde archivo
		</button>
	</div>

	{#if metodo === 'manual'}
		<div class="relative">
			<span
				class="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-[var(--text-subtle)]"
			>
				<Icon name="search" size={15} />
			</span>
			<input
				bind:value={busqueda}
				type="search"
				placeholder="Buscá el producto por nombre o código de barras…"
				aria-label="Buscar producto para agregar a la entrada"
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
								onclick={() => agregarManual(product)}
							>
								<span class="min-w-0 flex-1">
									<span class="block truncate text-sm text-[var(--text)]">{product.name}</span>
									<span class="block text-xs text-[var(--text-subtle)]">{product.barcode}</span>
								</span>
								<span class="shrink-0 text-xs tabular-nums text-[var(--text-subtle)]">
									stock {product.stock}
								</span>
							</button>
						</li>
					{/each}
				</ul>
			{/if}
		</div>
		<p class="mt-2 text-xs text-[var(--text-subtle)]">
			Buscá y tocá cada producto que llegó. Después ajustá cantidad y costo en la tabla.
		</p>
	{:else}
		<form
			method="POST"
			action="?/analizar"
			enctype="multipart/form-data"
			use:enhance={submit({
				errorTitle: 'No se pudo leer el archivo',
				setBusy: (v) => (analizando = v)
			})}
			class="flex flex-wrap items-end gap-3"
		>
			<div class="min-w-[16rem] flex-1">
				<label class="label" for="archivo">Factura del proveedor</label>
				<input
					id="archivo"
					name="archivo"
					type="file"
					accept=".xml,.xlsx,.csv"
					required
					class="input file:mr-3 file:rounded file:border-0 file:bg-[var(--surface-sunken)] file:px-3 file:py-1 file:text-xs file:font-semibold file:text-[var(--text-muted)]"
				/>
			</div>
			<button type="submit" class="btn btn-primary" disabled={analizando}>
				{#if analizando}
					<Spinner size={15} />
					Leyendo…
				{:else}
					<Icon name="search" size={15} />
					Analizar
				{/if}
			</button>
		</form>

		<div class="mt-3 grid gap-2 text-xs text-[var(--text-subtle)] sm:grid-cols-2">
			<p class="flex items-start gap-1.5">
				<Icon name="info" size={13} class="mt-0.5 shrink-0" />
				<span>
					<strong class="text-[var(--text-muted)]">XML</strong> — factura electrónica de Hacienda
					(v4.3 o 4.4), la que llega por correo. Se leen proveedor, consecutivo y líneas.
				</span>
			</p>
			<p class="flex items-start gap-1.5">
				<Icon name="info" size={13} class="mt-0.5 shrink-0" />
				<span>
					<strong class="text-[var(--text-muted)]">Excel o CSV</strong> — con columnas
					<em>Código</em>, <em>Descripción</em>, <em>Cantidad</em> y <em>Costo</em>. El orden no
					importa.
					<a href="/inventario/entradas/plantilla.csv" class="text-[var(--accent)] hover:underline">
						Descargar plantilla
					</a>
				</span>
			</p>
		</div>
	{/if}
</div>

<!-- ------------------------------------------------------ vista previa -->
{#if lineas.length === 0}
	<div class="card p-6">
		<EmptyState
			icon="box"
			title="Todavía no hay líneas"
			description={metodo === 'manual'
				? 'Buscá productos arriba para armar la entrada.'
				: 'Subí la factura del proveedor y revisá lo que se va a ingresar.'}
		/>
	</div>
{:else}
	<div class="mb-4 grid gap-3 sm:grid-cols-4">
		<div class="card p-3">
			<p class="text-xs font-semibold tracking-wide text-[var(--text-subtle)] uppercase">
				Líneas a ingresar
			</p>
			<p class="mt-1 text-xl font-bold text-[var(--text)]">
				{incluidas.length}<span class="text-sm text-[var(--text-subtle)]">/{lineas.length}</span>
			</p>
		</div>
		<div class="card p-3">
			<p class="text-xs font-semibold tracking-wide text-[var(--text-subtle)] uppercase">
				Unidades
			</p>
			<p class="mt-1 text-xl font-bold text-[var(--text)]">{totalUnidades}</p>
		</div>
		<div class="card p-3">
			<p class="text-xs font-semibold tracking-wide text-[var(--text-subtle)] uppercase">
				Costo total
			</p>
			<p class="mt-1 text-xl font-bold text-[var(--text)]">{formatMoney(totalCosto)}</p>
		</div>
		<div class="card p-3 {sinCoincidencia.length ? 'border-[var(--warning)]' : ''}">
			<p class="text-xs font-semibold tracking-wide text-[var(--text-subtle)] uppercase">
				Sin coincidencia
			</p>
			<p
				class="mt-1 text-xl font-bold {sinCoincidencia.length
					? 'text-[var(--warning)]'
					: 'text-[var(--text)]'}"
			>
				{sinCoincidencia.length}
			</p>
		</div>
	</div>

	{#if huerfanas.length}
		<div
			class="mb-4 flex items-start gap-2 rounded-lg border border-[var(--warning)] bg-[var(--warning-bg)] p-3 text-sm text-[var(--warning)]"
			role="alert"
		>
			<Icon name="alert" size={16} class="mt-0.5 shrink-0" />
			<p>
				{huerfanas.length}
				{huerfanas.length === 1 ? 'línea está marcada' : 'líneas están marcadas'} para ingresar
				pero no existen en el catálogo. Marcá <strong>Crear</strong> para darlas de alta, o
				desmarcalas para dejarlas fuera.
			</p>
		</div>
	{/if}

	<div class="card mb-4 overflow-hidden">
		<div class="table-wrap">
			<table class="data-table">
				<thead>
					<tr>
						<th scope="col" class="w-10">
							<span class="sr-only">Incluir</span>
						</th>
						<th scope="col">Producto</th>
						<th scope="col">Estado</th>
						<th scope="col" class="num">Cantidad</th>
						<th scope="col" class="num">Costo unit.</th>
						<th scope="col" class="num">Subtotal</th>
						<th scope="col" class="num">Stock</th>
						<th scope="col"><span class="sr-only">Quitar</span></th>
					</tr>
				</thead>
				<tbody>
					{#each lineas as linea (linea.key)}
						<tr class:opacity-50={!linea.incluir}>
							<td>
								<input
									type="checkbox"
									bind:checked={linea.incluir}
									class="h-4 w-4 accent-[var(--accent)]"
									aria-label="Incluir {linea.description}"
								/>
							</td>

							<td>
								<p class="font-medium text-[var(--text)]">
									{linea.matched?.name ?? linea.description}
								</p>
								<p class="text-xs text-[var(--text-subtle)]">
									{linea.code || 'sin código'}
									{#if linea.issue}
										· <span class="text-[var(--warning)]">{linea.issue}</span>
									{/if}
								</p>
							</td>

							<td>
								{#if linea.matched}
									<span class="badge bg-[var(--positive-bg)] text-[var(--positive)]">
										<Icon name="check" size={11} />
										{linea.matched_by === 'barcode' ? 'Por código' : 'Por nombre'}
									</span>
								{:else}
									<label
										class="flex cursor-pointer items-center gap-1.5 text-xs font-semibold text-[var(--warning)]"
									>
										<input
											type="checkbox"
											bind:checked={linea.crear}
											class="h-4 w-4 accent-[var(--accent)]"
										/>
										Crear producto
									</label>
								{/if}
							</td>

							<td class="num">
								<input
									type="number"
									bind:value={linea.quantity}
									min="1"
									step="1"
									class="input h-8 w-20 text-right tabular-nums"
									aria-label="Cantidad de {linea.description}"
								/>
							</td>

							<td class="num">
								<input
									type="number"
									bind:value={linea.unit_cost}
									min="0"
									step="0.01"
									class="input h-8 w-24 text-right tabular-nums"
									aria-label="Costo unitario de {linea.description}"
								/>
							</td>

							<td class="num font-semibold tabular-nums">
								{formatMoney((Number(linea.unit_cost) || 0) * (Number(linea.quantity) || 0))}
							</td>

							<td class="num text-xs tabular-nums">
								{#if linea.matched}
									<span class="text-[var(--text-subtle)]">{linea.matched.stock}</span>
									<Icon name="forward" size={10} class="inline text-[var(--text-subtle)]" />
									<strong class="text-[var(--positive)]">
										{linea.matched.stock + (Number(linea.quantity) || 0)}
									</strong>
								{:else}
									<span class="text-[var(--text-subtle)]">—</span>
								{/if}
							</td>

							<td class="text-right">
								<button
									type="button"
									class="rounded p-1 text-[var(--text-subtle)] hover:text-[var(--negative)]"
									onclick={() => (lineas = lineas.filter((l) => l.key !== linea.key))}
									aria-label="Quitar {linea.description}"
								>
									<Icon name="close" size={14} />
								</button>
							</td>
						</tr>

						<!-- Datos que hacen falta solo si se va a dar de alta -->
						{#if !linea.matched && linea.crear}
							<tr>
								<td></td>
								<td colspan="7" class="bg-[var(--surface-sunken)]">
									<div class="grid gap-3 py-1 sm:grid-cols-3">
										<Field
											label="Código de barras"
											name="bc-{linea.key}"
											bind:value={linea.nuevoBarcode}
											icon="barcode"
											required
											error={linea.nuevoBarcode.trim() ? undefined : 'Obligatorio'}
										/>
										<Field
											label="Precio de venta"
											name="pv-{linea.key}"
											bind:value={linea.nuevoPrecio}
											inputmode="decimal"
											required
											hint="Sugerido: costo + 30 %"
											error={Number(linea.nuevoPrecio) > 0 ? undefined : 'Obligatorio'}
										/>
										<div>
											<label class="label" for="cat-{linea.key}">Categoría</label>
											<select
												id="cat-{linea.key}"
												bind:value={linea.nuevaCategoria}
												class="input"
											>
												{#each data.categories as category (category.id)}
													<option value={String(category.id)}>{category.name}</option>
												{/each}
											</select>
										</div>
									</div>
								</td>
							</tr>
						{/if}
					{/each}
				</tbody>
			</table>
		</div>
	</div>

	<!-- ------------------------------------------------ confirmar -->
	<form
		method="POST"
		action="?/confirmar"
		use:enhance={submit({
			errorTitle: 'No se pudo registrar la entrada',
			setBusy: (v) => (guardando = v)
		})}
		class="card p-4"
	>
		<input type="hidden" name="lines" value={JSON.stringify(payload)} />
		<input type="hidden" name="source" value={origen} />

		<h2 class="mb-3 text-sm font-bold text-[var(--text)]">Datos del documento</h2>

		<div class="grid gap-4 sm:grid-cols-3">
			<Field
				label="Proveedor"
				name="supplier"
				bind:value={supplier}
				placeholder="Ej.: Distribuidora La Central"
			/>
			<Field
				label="N.º de factura"
				name="document_number"
				bind:value={documentNumber}
				hint="Evita cargar la misma factura dos veces."
			/>
			<Field label="Notas" name="notes" bind:value={notes} placeholder="Opcional" />
		</div>

		<div class="mt-4 flex flex-wrap items-center justify-between gap-3">
			<p class="text-sm text-[var(--text-muted)]">
				Van a entrar <strong class="text-[var(--text)]">{totalUnidades}</strong> unidades
				{#if aCrear.length}
					y se van a crear
					<strong class="text-[var(--text)]">{aCrear.length}</strong>
					{aCrear.length === 1 ? 'producto' : 'productos'}
				{/if}
				· costo {formatMoney(totalCosto)}
			</p>

			<div class="flex gap-2">
				<button type="button" class="btn btn-ghost" onclick={limpiar} disabled={guardando}>
					Descartar
				</button>
				<button type="submit" class="btn btn-primary" disabled={!listo || guardando}>
					{#if guardando}
						<Spinner size={15} />
						Ingresando…
					{:else}
						<Icon name="check" size={15} />
						Ingresar al inventario
					{/if}
				</button>
			</div>
		</div>
	</form>
{/if}
