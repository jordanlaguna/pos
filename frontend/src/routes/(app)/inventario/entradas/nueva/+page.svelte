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
	import { m } from '$lib/paraglide/messages.js';
	import { importMessage } from '$lib/ui/messages';
	import type { ParsedLine, ParsedSupplier, Product } from '$lib/domain/types';
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

	// ------------------------------------------------------------ compra (F10)
	//
	// Con proveedor esto es una compra: genera cuenta por pagar y crédito fiscal
	// (RN-52). Sin él sigue siendo la entrada de siempre, y por eso todo lo de
	// abajo arranca vacío y la pantalla no cambia hasta que se elija uno.
	let supplierId = $state('');
	let documentKey = $state('');
	let documentDate = $state('');
	let paymentTerms = $state<'cash' | 'credit'>('cash');
	let creditDays = $state('');
	let paymentMethod = $state('');
	/** El proveedor del XML que todavía no existe. Se da de alta al confirmar. */
	let proveedorNuevo = $state<ParsedSupplier | null>(null);

	const esCompra = $derived(supplierId !== '' || proveedorNuevo !== null);
	const proveedorElegido = $derived(
		data.suppliers.find((p) => String(p.id) === supplierId) ?? null
	);

	/**
	 * El motivo del movimiento de caja de una compra de contado pagada en
	 * efectivo (RN-30: el backend no escribe texto para personas).
	 *
	 * Se arma acá, en la interfaz, que es la única capa que sabe en qué idioma
	 * está la pantalla. Si no, un cajero brasileño vería medio arqueo en español.
	 */
	const motivoDelPago = $derived(
		m.entry_payment_reason({
			supplier: proveedorElegido?.name ?? proveedorNuevo?.name ?? supplier ?? '',
			document: documentNumber || '—'
		})
	);

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
			// El del documento del proveedor (RN-53). En cero cuando la línea se
			// agregó a mano o vino de una hoja de cálculo.
			tax_rate: base.tax_rate ?? 0,
			tax_amount: base.tax_amount ?? 0,
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

		// Lo que el XML sabe de la compra (RF-42).
		documentKey = parsed.document_key ?? '';
		documentDate = (parsed.issued_at ?? '').slice(0, 10);
		paymentTerms = parsed.payment_terms ?? 'cash';
		creditDays = parsed.credit_days ? String(parsed.credit_days) : '';
		reconocerProveedor(parsed.supplier_details ?? null);

		for (const aviso of parsed.warnings) toasts.warning(importMessage(aviso));
	});

	/**
	 * A quién le compramos, según lo que dice el documento.
	 *
	 * La identificación manda sobre el nombre: **la misma identificación es el
	 * mismo proveedor**, y el nombre cambia —razón social, nombre comercial,
	 * cómo lo escribió el emisor ese día— sin que cambie con quién se está
	 * tratando. Emparejar por nombre crearía una ficha nueva cada vez que el
	 * proveedor edite su factura, y el saldo quedaría repartido entre las dos.
	 */
	function reconocerProveedor(details: ParsedSupplier | null) {
		supplierId = '';
		proveedorNuevo = null;
		if (!details) return;

		const cedula = details.identification?.trim();
		const conocido = cedula
			? data.suppliers.find((p) => p.identification?.trim() === cedula)
			: undefined;

		if (conocido) {
			supplierId = String(conocido.id);
			// El plazo habitual del proveedor solo se propone si el documento no
			// trajo el suyo: lo que manda es lo que diga esta factura.
			if (paymentTerms === 'credit' && !creditDays && conocido.payment_terms_days) {
				creditDays = String(conocido.payment_terms_days);
			}
		} else {
			proveedorNuevo = details;
		}
	}

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
						price: Number(product.price),
						// Las dos de F10: la tarifa para poder avisar si la del
						// documento difiere (RF-43) y el costo para verlo al lado.
						tax_rate: product.tax_rate ?? null,
						cost: Number(product.cost ?? 0)
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
		incluidas.map((l) => {
			// El impuesto va **tal como lo dice el documento** (RN-53): es el
			// crédito fiscal, y lo que se acredita es lo que se pagó. No se
			// recalcula desde la tarifa del producto ni aunque no coincidan.
			const impuesto = {
				quantity: Number(l.quantity),
				unit_cost: Number(l.unit_cost) || 0,
				tax_rate: Number(l.tax_rate) || 0,
				tax_amount: Number(l.tax_amount) || 0
			};
			return l.matched
				? { id_product: l.matched.id_product, ...impuesto }
				: {
						new_product: {
							name: l.description,
							description: l.description,
							barcode: l.nuevoBarcode.trim(),
							price: Number(l.nuevoPrecio),
							category_id: Number(l.nuevaCategoria)
						},
						...impuesto
					};
		})
	);

	const totalImpuesto = $derived(
		round2(incluidas.reduce((a, l) => a + (Number(l.tax_amount) || 0), 0))
	);

	/**
	 * Líneas donde la tarifa del documento no es la del producto (RF-43).
	 *
	 * No se corrige ninguna de las dos: se avisa. Puede ser que el proveedor
	 * clasificara distinto —y entonces lo que vale es su documento— o que el
	 * CABYS del producto esté mal, y eso lo decide una persona mirando las dos.
	 * Solo se comparan las emparejadas y con tarifa propia: `null` es «la tasa
	 * configurada del negocio», que no es un desacuerdo sino una ausencia.
	 */
	const discrepan = $derived(
		incluidas.filter((l) => {
			const suya = l.matched?.tax_rate;
			if (l.matched == null || suya == null) return false;
			return round2(suya * 100) !== round2(Number(l.tax_rate) || 0);
		})
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
		supplierId = '';
		proveedorNuevo = null;
		documentKey = '';
		documentDate = '';
		paymentTerms = 'cash';
		creditDays = '';
		paymentMethod = '';
	}
</script>

<PageHeader
	title={m.entry_new_title()}
	description={m.entry_new_description()}
>
	{#snippet actions()}
		<a href="/inventario/entradas" class="btn btn-ghost">
			<Icon name="back" size={15} />
			{m.entry_new_see_entries()}
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
			{m.entry_method_manual()}
		</button>
		<button
			type="button"
			class="btn {metodo === 'archivo' ? 'btn-primary' : 'btn-ghost'}"
			onclick={() => (metodo = 'archivo')}
		>
			<Icon name="download" size={15} />
			{m.entry_method_file()}
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
				placeholder={m.entry_search_placeholder()}
				aria-label={m.entry_search_label()}
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
									{m.entry_search_stock({ stock: product.stock })}
								</span>
							</button>
						</li>
					{/each}
				</ul>
			{/if}
		</div>
		<p class="mt-2 text-xs text-[var(--text-subtle)]">
			{m.entry_search_hint()}
		</p>
	{:else}
		<form
			method="POST"
			action="?/analizar"
			enctype="multipart/form-data"
			use:enhance={submit({
				errorTitle: m.entry_file_read_failed(),
				setBusy: (v) => (analizando = v)
			})}
			class="flex flex-wrap items-end gap-3"
		>
			<div class="min-w-[16rem] flex-1">
				<label class="label" for="archivo">{m.entry_file_label()}</label>
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
					{m.entry_file_reading()}
				{:else}
					<Icon name="search" size={15} />
					{m.entry_file_analyze()}
				{/if}
			</button>
		</form>

		<div class="mt-3 grid gap-2 text-xs text-[var(--text-subtle)] sm:grid-cols-2">
			<p class="flex items-start gap-1.5">
				<Icon name="info" size={13} class="mt-0.5 shrink-0" />
				<span>
					<strong class="text-[var(--text-muted)]">{m.entry_file_xml()}</strong> —
					{m.entry_file_xml_hint()}
				</span>
			</p>
			<p class="flex items-start gap-1.5">
				<Icon name="info" size={13} class="mt-0.5 shrink-0" />
				<span>
					<strong class="text-[var(--text-muted)]">{m.entry_file_sheet()}</strong> —
					{m.entry_file_sheet_hint({
						code: m.entry_column_code(),
						description: m.entry_column_description(),
						quantity: m.entry_column_quantity(),
						cost: m.entry_column_cost()
					})}
					<a href="/inventario/entradas/plantilla.csv" class="text-[var(--accent)] hover:underline">
						{m.entry_file_template()}
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
			title={m.entry_preview_none()}
			description={metodo === 'manual'
				? m.entry_preview_none_manual()
				: m.entry_preview_none_file()}
		/>
	</div>
{:else}
	<div class="mb-4 grid gap-3 sm:grid-cols-4">
		<div class="card p-3">
			<p class="text-xs font-semibold tracking-wide text-[var(--text-subtle)] uppercase">
				{m.entry_stat_lines()}
			</p>
			<p class="mt-1 text-xl font-bold text-[var(--text)]">
				{incluidas.length}<span class="text-sm text-[var(--text-subtle)]">/{lineas.length}</span>
			</p>
		</div>
		<div class="card p-3">
			<p class="text-xs font-semibold tracking-wide text-[var(--text-subtle)] uppercase">
				{m.entry_stat_units()}
			</p>
			<p class="mt-1 text-xl font-bold text-[var(--text)]">{totalUnidades}</p>
		</div>
		<div class="card p-3">
			<p class="text-xs font-semibold tracking-wide text-[var(--text-subtle)] uppercase">
				{m.entry_stat_cost()}
			</p>
			<p class="mt-1 text-xl font-bold text-[var(--text)]">{formatMoney(totalCosto)}</p>
		</div>
		<div class="card p-3 {sinCoincidencia.length ? 'border-[var(--warning)]' : ''}">
			<p class="text-xs font-semibold tracking-wide text-[var(--text-subtle)] uppercase">
				{m.entry_stat_unmatched()}
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
				{m.entry_orphans({ count: huerfanas.length })}
				{m.entry_orphans_hint({ create: m.entry_create_word() })}
			</p>
		</div>
	{/if}

	<div class="card mb-4 overflow-hidden">
		<div class="table-wrap">
			<table class="data-table">
				<thead>
					<tr>
						<th scope="col" class="w-10">
							<span class="sr-only">{m.entry_col_include()}</span>
						</th>
						<th scope="col">{m.entries_line_product()}</th>
						<th scope="col">{m.entry_col_status()}</th>
						<th scope="col" class="num">{m.entries_line_quantity()}</th>
						<th scope="col" class="num">{m.entries_line_unit_cost()}</th>
						{#if esCompra}
							<th scope="col" class="num">{m.entry_col_tax_rate()}</th>
						{/if}
						<th scope="col" class="num">{m.entries_line_subtotal()}</th>
						<th scope="col" class="num">{m.entry_col_stock()}</th>
						<th scope="col"><span class="sr-only">{m.entry_col_remove()}</span></th>
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
									aria-label={m.entry_include_line({ product: linea.description })}
								/>
							</td>

							<td>
								<p class="font-medium text-[var(--text)]">
									{linea.matched?.name ?? linea.description}
								</p>
								<p class="text-xs text-[var(--text-subtle)]">
									{linea.code || m.entry_no_code()}
									{#if linea.issue}
										· <span class="text-[var(--warning)]">{importMessage(linea.issue)}</span>
									{/if}
								</p>
							</td>

							<td>
								{#if linea.matched}
									<span class="badge bg-[var(--positive-bg)] text-[var(--positive)]">
										<Icon name="check" size={11} />
										{linea.matched_by === 'barcode' ? m.entry_matched_barcode() : m.entry_matched_name()}
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
										{m.entry_create_product()}
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
									aria-label={m.entry_quantity_of({ product: linea.description })}
								/>
							</td>

							<td class="num">
								<input
									type="number"
									bind:value={linea.unit_cost}
									min="0"
									step="0.01"
									class="input h-8 w-24 text-right tabular-nums"
									aria-label={m.entry_unit_cost_of({ product: linea.description })}
								/>
							</td>

							{#if esCompra}
								{@const suya = linea.matched?.tax_rate}
								{@const difiere =
									linea.matched != null &&
									suya != null &&
									round2(suya * 100) !== round2(Number(linea.tax_rate) || 0)}
								<td class="num">
									<!-- Editable porque la factura manda y a veces hay que
									     corregirla al teclearla. El monto se recalcula con la
									     tarifa que quede: si el documento trae uno propio que no
									     cuadra, se respeta mientras nadie toque la tarifa. -->
									<input
										type="number"
										bind:value={linea.tax_rate}
										oninput={() =>
											(linea.tax_amount = round2(
												((Number(linea.unit_cost) || 0) *
													(Number(linea.quantity) || 0) *
													(Number(linea.tax_rate) || 0)) /
													100
											))}
										min="0"
										max="100"
										step="0.01"
										class="input h-8 w-20 text-right tabular-nums"
										class:border-[var(--warning)]={difiere}
										aria-label={m.entry_tax_rate_of({ product: linea.description })}
									/>
									{#if difiere}
										<!-- RF-43: no se corrige ninguna de las dos, se avisa.
										     O el proveedor clasificó distinto —y vale su
										     documento— o el CABYS del producto está mal. -->
										<span class="mt-0.5 block text-[10px] leading-tight text-[var(--warning)]">
											{m.entry_tax_differs({ rate: round2((suya ?? 0) * 100) })}
										</span>
									{/if}
								</td>
							{/if}

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
									aria-label={m.entry_remove_line({ product: linea.description })}
								>
									<Icon name="close" size={14} />
								</button>
							</td>
						</tr>

						<!-- Datos que hacen falta solo si se va a dar de alta -->
						{#if !linea.matched && linea.crear}
							<tr>
								<td></td>
								<td colspan={esCompra ? 8 : 7} class="bg-[var(--surface-sunken)]">
									<div class="grid gap-3 py-1 sm:grid-cols-3">
										<Field
											label={m.entry_label_barcode()}
											name="bc-{linea.key}"
											bind:value={linea.nuevoBarcode}
											icon="barcode"
											required
											error={linea.nuevoBarcode.trim() ? undefined : m.entry_required_short()}
										/>
										<Field
											label={m.entry_label_sale_price()}
											name="pv-{linea.key}"
											bind:value={linea.nuevoPrecio}
											inputmode="decimal"
											required
											hint={m.entry_price_hint()}
											error={Number(linea.nuevoPrecio) > 0 ? undefined : m.entry_required_short()}
										/>
										<div>
											<label class="label" for="cat-{linea.key}">{m.entry_label_category()}</label>
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
			errorTitle: m.entry_submit_failed(),
			setBusy: (v) => (guardando = v)
		})}
		class="card p-4"
	>
		<input type="hidden" name="lines" value={JSON.stringify(payload)} />
		<input type="hidden" name="source" value={origen} />
		<input type="hidden" name="document_key" value={documentKey} />
		<input type="hidden" name="supplier_id" value={supplierId} />
		<input
			type="hidden"
			name="new_supplier"
			value={proveedorNuevo ? JSON.stringify(proveedorNuevo) : ''}
		/>

		<h2 class="mb-3 text-sm font-bold text-[var(--text)]">{m.entry_document_data()}</h2>

		<div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
			<div>
				<label class="label" for="proveedor">{m.entry_label_supplier_account()}</label>
				<select id="proveedor" bind:value={supplierId} class="input" disabled={proveedorNuevo !== null}>
					<!-- Sin proveedor esto es una entrada y no una compra (RN-52), y
					     por eso la opción vacía existe y es la primera: recibir
					     mercadería sin factura sigue siendo lo normal. -->
					<option value="">{m.entry_supplier_none()}</option>
					{#each data.suppliers.filter((p) => p.is_active) as proveedor (proveedor.id)}
						<option value={String(proveedor.id)}>{proveedor.name}</option>
					{/each}
				</select>
				{#if proveedorNuevo}
					<p class="mt-1 text-xs text-[var(--warning)]">
						{m.entry_supplier_new({ name: proveedorNuevo.name })}
					</p>
				{/if}
			</div>
			<Field
				label={m.entry_label_supplier()}
				name="supplier"
				bind:value={supplier}
				placeholder={m.entry_supplier_placeholder()}
				hint={esCompra ? m.entry_supplier_text_hint() : undefined}
			/>
			<Field
				label={m.entry_label_document_number()}
				name="document_number"
				bind:value={documentNumber}
				hint={m.entry_document_hint()}
			/>
			<Field
				label={m.entry_label_notes()}
				name="notes"
				bind:value={notes}
				placeholder={m.entry_notes_placeholder()}
			/>
		</div>

		{#if esCompra}
			<!-- ------------------------------------------------ condición de pago -->
			<div class="mt-4 grid gap-4 sm:grid-cols-3">
				<div>
					<label class="label" for="fecha-doc">{m.entry_label_document_date()}</label>
					<input
						id="fecha-doc"
						name="document_date"
						type="date"
						class="input"
						bind:value={documentDate}
					/>
					<!-- No es la de carga, y de ahí se cuenta el vencimiento: una
					     factura del 28 digitada el 3 vence a los 30 días del 28. -->
					<p class="mt-1 text-xs text-[var(--text-subtle)]">{m.entry_document_date_hint()}</p>
				</div>

				<div>
					<label class="label" for="condicion">{m.entry_label_terms()}</label>
					<select id="condicion" name="payment_terms" bind:value={paymentTerms} class="input">
						<option value="cash">{m.entry_terms_cash()}</option>
						<option value="credit">{m.entry_terms_credit()}</option>
					</select>
				</div>

				{#if paymentTerms === 'credit'}
					<div>
						<label class="label" for="plazo">{m.entry_label_credit_days()}</label>
						<input
							id="plazo"
							name="payment_terms_days"
							type="number"
							min="0"
							step="1"
							class="input"
							bind:value={creditDays}
							placeholder={String(proveedorElegido?.payment_terms_days ?? 0)}
						/>
						<p class="mt-1 text-xs text-[var(--text-subtle)]">{m.entry_credit_days_hint()}</p>
					</div>
				{:else}
					<div>
						<label class="label" for="metodo">{m.entry_label_payment_method()}</label>
						<select id="metodo" name="payment_method" bind:value={paymentMethod} class="input">
							<!-- Sin método la compra nace con saldo y se abona desde
							     cuentas por pagar. No se adivina: «efectivo» descuadra un
							     arqueo y «transferencia» inventa un movimiento bancario. -->
							<option value="">{m.entry_payment_later()}</option>
							<option value="cash">{m.entry_payment_cash()}</option>
							<option value="transfer">{m.entry_payment_transfer()}</option>
							<option value="other">{m.entry_payment_other()}</option>
						</select>
						{#if paymentMethod === 'cash'}
							<!-- RN-56: el efectivo sale de la caja abierta o no sale, y
							     acá la compra entera rebota. Vale avisarlo antes. -->
							<p class="mt-1 text-xs text-[var(--warning)]">{m.entry_payment_cash_warning()}</p>
						{/if}
					</div>
				{/if}
			</div>

			<input type="hidden" name="payment_reason" value={motivoDelPago} />

			{#if discrepan.length}
				<div
					class="mt-4 flex items-start gap-2 rounded-lg border border-[var(--warning)] bg-[var(--warning-bg)] p-3 text-sm text-[var(--warning)]"
					role="alert"
				>
					<Icon name="alert" size={16} class="mt-0.5 shrink-0" />
					<p>{m.entry_tax_mismatch({ count: discrepan.length })}</p>
				</div>
			{/if}
		{/if}

		<div class="mt-4 flex flex-wrap items-center justify-between gap-3">
			<p class="text-sm text-[var(--text-muted)]">
				{m.entry_summary_units({ units: totalUnidades })}
				{#if aCrear.length}
					{m.entry_summary_creating({ count: aCrear.length })}
				{/if}
				{m.entry_summary_cost({ cost: formatMoney(totalCosto) })}
				{#if esCompra && totalImpuesto > 0}
					<!-- El impuesto aparte: es el crédito fiscal, y el total que se le
					     paga al proveedor es la suma de los dos. -->
					{m.entry_summary_tax({
						tax: formatMoney(totalImpuesto),
						total: formatMoney(round2(totalCosto + totalImpuesto))
					})}
				{/if}
			</p>

			<div class="flex gap-2">
				<button type="button" class="btn btn-ghost" onclick={limpiar} disabled={guardando}>
					{m.entry_discard()}
				</button>
				<button type="submit" class="btn btn-primary" disabled={!listo || guardando}>
					{#if guardando}
						<Spinner size={15} />
						{m.entry_saving()}
					{:else}
						<Icon name="check" size={15} />
						{m.entry_submit()}
					{/if}
				</button>
			</div>
		</div>
	</form>
{/if}
