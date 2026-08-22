<script lang="ts">
	import { enhance } from '$app/forms';
	import { tick } from 'svelte';
	import { submit } from '$lib/ui/forms';
	import Icon from '$lib/ui/components/Icon.svelte';
	import Modal from '$lib/ui/components/Modal.svelte';
	import Field from '$lib/ui/components/Field.svelte';
	import Spinner from '$lib/ui/components/Spinner.svelte';
	import EmptyState from '$lib/ui/components/EmptyState.svelte';
	import { quickCash, saleNumber } from '$lib/domain/cart';
	import { cart } from '$lib/ui/stores/cart.svelte';
	import { toasts } from '$lib/ui/stores/toast.svelte';
	import { formatMoney, parseAmount, changeDue, taxLabel } from '$lib/domain/money';
	import { PAYMENT_METHODS, type Product } from '$lib/domain/types';
	import { m } from '$lib/paraglide/messages.js';
	import { cartMessage, paymentLabel } from '$lib/ui/messages';
	import type { ActionData, PageData } from './$types';

	let { data, form }: { data: PageData; form: ActionData } = $props();

	let searchTerm = $state('');
	let searchInput = $state<HTMLInputElement | null>(null);
	let highlighted = $state(0);
	let activeCategory = $state<number | 'todas'>('todas');

	let paymentOpen = $state(false);
	let cashOpen = $state(false);
	let submitting = $state(false);

	let paymentMethod = $state<string>(PAYMENT_METHODS[0]);
	let cashInput = $state('');
	let currentSaleNumber = $state('');

	const totals = $derived(cart.totals);
	const hasCashSession = $derived(data.cashSession != null);

	/** La pestaña muestra el nombre del cliente si lo tiene; si no, su número. */
	function ticketLabel(ticket: (typeof cart.tickets)[number]): string {
		if (ticket.clientId) {
			const client = data.clients.find((c) => String(c.id_client) === ticket.clientId);
			if (client) return `${client.name} ${client.last_name}`.trim();
		}
		return m.sales_ticket_label({ position: cart.positionOf(ticket.id) });
	}

	function nuevaVenta() {
		const result = cart.open();
		if (!result.ok) {
			toasts.warning(cartMessage(result.reason));
			return;
		}
		searchInput?.focus();
	}

	// --------------------------------------------------------------- búsqueda

	/**
	 * Filtra sobre el catálogo ya cargado. El escáner dispara un `input` por
	 * carácter y una consulta al servidor por tecla haría inservible la caja.
	 */
	const matches = $derived.by(() => {
		const term = searchTerm.trim().toLowerCase();
		if (term.length < 1) return [];
		return data.products
			.filter(
				(p) => p.name.toLowerCase().includes(term) || p.barcode.toLowerCase().includes(term)
			)
			.slice(0, 8);
	});

	const showDropdown = $derived(matches.length > 0 && searchTerm.trim().length > 0);

	const visibleProducts = $derived(
		activeCategory === 'todas'
			? data.products
			: data.products.filter((p) => p.category_id === activeCategory)
	);

	$effect(() => {
		// Al cambiar los resultados, la selección vuelve al primero.
		matches;
		highlighted = 0;
	});

	function addProduct(product: Product, quantity = 1) {
		const result = cart.add(product, quantity);
		if (!result.ok) {
			toasts.warning(cartMessage(result.reason));
			return;
		}
		searchTerm = '';
		searchInput?.focus();
	}

	/** Enter en el campo: código de barras exacto primero, si no el resaltado. */
	function onSearchKeydown(event: KeyboardEvent) {
		if (event.key === 'ArrowDown') {
			event.preventDefault();
			highlighted = Math.min(matches.length - 1, highlighted + 1);
			return;
		}
		if (event.key === 'ArrowUp') {
			event.preventDefault();
			highlighted = Math.max(0, highlighted - 1);
			return;
		}
		if (event.key === 'Escape') {
			searchTerm = '';
			return;
		}
		if (event.key !== 'Enter') return;

		event.preventDefault();
		const term = searchTerm.trim();
		if (!term) return;

		const exact = data.products.find((p) => p.barcode === term);
		const chosen = exact ?? matches[highlighted];
		if (chosen) addProduct(chosen);
		else toasts.error(m.sales_product_not_found(), m.sales_no_matches({ term }));
	}

	// ------------------------------------------------------------------ cobro

	async function openPayment() {
		if (cart.isEmpty) {
			toasts.warning(m.sales_cart_is_empty());
			return;
		}
		if (!hasCashSession) {
			cashOpen = true;
			return;
		}
		currentSaleNumber = saleNumber(new Date());
		paymentMethod = PAYMENT_METHODS[0];
		cashInput = String(totals.total.toFixed(2));
		paymentOpen = true;
		await tick();
	}

	const cashValue = $derived(parseAmount(cashInput) ?? 0);
	const isCash = $derived(paymentMethod === 'Efectivo');
	const change = $derived(isCash ? changeDue(cashValue, totals.total) : 0);
	const insufficient = $derived(isCash && cashValue < totals.total);

	function onGlobalKeydown(event: KeyboardEvent) {
		const target = event.target as HTMLElement | null;
		const typing =
			target?.tagName === 'TEXTAREA' ||
			(target?.tagName === 'INPUT' && (target as HTMLInputElement).type !== 'search');

		// F1 cobra, igual que en el WinForms original.
		if (event.key === 'F1') {
			event.preventDefault();
			if (!paymentOpen) openPayment();
			return;
		}
		if (paymentOpen) return;

		if (event.key === 'F2' && !typing) {
			event.preventDefault();
			searchInput?.focus();
			searchInput?.select();
			return;
		}
		// F3 deja la venta actual en espera y abre otra para el siguiente cliente.
		if (event.key === 'F3') {
			event.preventDefault();
			nuevaVenta();
			return;
		}
		// F4 rota entre las ventas abiertas.
		if (event.key === 'F4') {
			event.preventDefault();
			cart.next();
			searchInput?.focus();
		}
	}

</script>

<svelte:window onkeydown={onGlobalKeydown} />

<!--
	En pantallas grandes la caja ocupa el alto exacto de la ventana y no hay
	desplazamiento de página: solo se mueve la grilla de productos. Así el total y
	el botón de cobrar están siempre a la vista, que es lo que un cajero necesita.
-->
<div class="flex flex-col gap-4 lg:h-full">
	{#if !hasCashSession}
		<div
			class="flex shrink-0 flex-wrap items-center gap-3 rounded-lg border border-[var(--warning)] bg-[var(--warning-bg)] p-3"
			role="alert"
		>
		<Icon name="alert" size={18} class="shrink-0 text-[var(--warning)]" />
		<p class="flex-1 text-sm text-[var(--warning)]">
			<strong>{m.sales_register_closed()}</strong> {m.sales_register_closed_hint()}
		</p>
		<button type="button" class="btn btn-primary py-1.5 text-xs" onclick={() => (cashOpen = true)}>
			<Icon name="wallet" size={14} />
			{m.sales_open_register()}
		</button>
	</div>
{/if}

<div
	class="grid gap-4 lg:min-h-0 lg:flex-1 lg:grid-cols-[minmax(0,1fr)_23rem] xl:grid-cols-[minmax(0,1fr)_26rem]"
>
	<!-- ------------------------------------------------------ catálogo -->
	<section class="flex min-w-0 flex-col gap-3 lg:min-h-0">
		<!-- Buscador y categorías quedan fijos; el desplegable se superpone a la grilla. -->
		<div class="relative shrink-0">
			<span
				class="pointer-events-none absolute top-1/2 left-3.5 -translate-y-1/2 text-[var(--text-subtle)]"
			>
				<Icon name="barcode" size={18} />
			</span>
			<!-- svelte-ignore a11y_autofocus -->
			<input
				bind:this={searchInput}
				bind:value={searchTerm}
				onkeydown={onSearchKeydown}
				type="search"
				autofocus
				autocomplete="off"
				placeholder={m.sales_search_placeholder()}
				aria-label={m.sales_search_label()}
				class="input h-12 pr-16 pl-11 text-base"
			/>
			<!-- «F2» es el nombre de una tecla, no una palabra: no se traduce. -->
			<kbd
				class="pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 rounded border border-[var(--border)] px-1.5 py-0.5 text-[10px] font-semibold text-[var(--text-subtle)]"
			>
				F2
			</kbd>

			{#if showDropdown}
				<ul
					class="absolute inset-x-0 top-[calc(100%+0.25rem)] z-20 max-h-80 overflow-y-auto rounded-lg border border-[var(--border)] bg-[var(--surface-raised)] p-1 shadow-xl"
					role="listbox"
					aria-label={m.sales_search_results()}
				>
					{#each matches as product, index (product.id_product)}
						<li>
							<button
								type="button"
								class="flex w-full items-center gap-3 rounded-md px-3 py-2 text-left {index ===
								highlighted
									? 'bg-[var(--surface-sunken)]'
									: ''}"
								onmouseenter={() => (highlighted = index)}
								onclick={() => addProduct(product)}
								role="option"
								aria-selected={index === highlighted}
							>
								<span class="min-w-0 flex-1">
									<span class="block truncate text-sm font-medium text-[var(--text)]">
										{product.name}
									</span>
									<span class="block truncate text-xs text-[var(--text-subtle)]">
										{product.barcode}
									</span>
								</span>
								<span class="shrink-0 text-right">
									<span class="block text-sm font-semibold tabular-nums text-[var(--text)]">
										{formatMoney(product.price)}
									</span>
									<span
										class="block text-xs tabular-nums {product.stock > 0
											? 'text-[var(--text-subtle)]'
											: 'text-[var(--negative)]'}"
									>
										{m.sales_in_stock({ stock: product.stock })}
									</span>
								</span>
							</button>
						</li>
					{/each}
				</ul>
			{/if}
		</div>

		<!-- Filtro por categoría para la operación táctil -->
		<div class="flex shrink-0 flex-wrap gap-1.5">
			<button
				type="button"
				class="badge border {activeCategory === 'todas'
					? 'border-transparent bg-[var(--accent)] text-[var(--accent-text)]'
					: 'border-[var(--border)] text-[var(--text-muted)] hover:bg-[var(--surface-sunken)]'}"
				onclick={() => (activeCategory = 'todas')}
			>
				{m.sales_all_categories()}
			</button>
			{#each data.categories as category (category.id)}
				<button
					type="button"
					class="badge border {activeCategory === category.id
						? 'border-transparent bg-[var(--accent)] text-[var(--accent-text)]'
						: 'border-[var(--border)] text-[var(--text-muted)] hover:bg-[var(--surface-sunken)]'}"
					onclick={() => (activeCategory = category.id)}
				>
					{category.name}
				</button>
			{/each}
		</div>

		<div
			class="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-4 lg:min-h-0 lg:flex-1 lg:content-start lg:overflow-y-auto lg:pr-1"
		>
			{#each visibleProducts as product (product.id_product)}
				{@const out = product.stock <= 0}
				<button
					type="button"
					class="card flex min-h-24 flex-col justify-between p-3 text-left transition-colors enabled:hover:border-[var(--accent)] disabled:opacity-45"
					onclick={() => addProduct(product)}
					disabled={out}
					title={out ? m.sales_out_of_stock() : m.sales_add_product({ product: product.name })}
				>
					<span class="block">
						<span class="line-clamp-2 text-xs font-medium text-[var(--text)]">
							{product.name}
						</span>
						<!-- El código a la vista: sirve para cotejar contra la etiqueta física
						     cuando dos presentaciones del mismo producto se parecen. -->
						<span class="mt-0.5 block truncate font-mono text-[10px] text-[var(--text-subtle)]">
							{product.barcode}
						</span>
					</span>
					<span class="mt-2 flex items-end justify-between gap-2">
						<span class="text-sm font-bold tabular-nums text-[var(--text)]">
							{formatMoney(product.price)}
						</span>
						<span
							class="text-[10px] font-semibold tabular-nums {out
								? 'text-[var(--negative)]'
								: product.stock <= 10
									? 'text-[var(--warning)]'
									: 'text-[var(--text-subtle)]'}"
						>
							{out ? m.sales_sold_out() : m.sales_units_short({ stock: product.stock })}
						</span>
					</span>
				</button>
			{:else}
				<div class="col-span-full">
					<EmptyState
						icon="box"
						title={m.sales_no_products()}
						description={m.sales_no_products_hint()}
						compact
					/>
				</div>
			{/each}
		</div>
	</section>

	<!-- --------------------------------------------------------- carrito -->
	<!-- El carrito llena la columna; solo su lista de líneas se desplaza. -->
	<aside class="card flex flex-col lg:min-h-0">
		<!--
			Ventas en espera. Cuando un cliente vuelve por otro producto, su venta
			queda en una pestaña y el cajero atiende al siguiente sin perder nada.
		-->
		<div
			class="flex shrink-0 items-stretch gap-1 overflow-x-auto border-b border-[var(--border)] px-2 pt-2"
			role="tablist"
			aria-label={m.sales_pending_tickets()}
		>
			{#each cart.tickets as ticket (ticket.id)}
				{@const activa = ticket.id === cart.activeId}
				{@const unidades = cart.countOf(ticket)}
				<div class="group relative flex shrink-0 items-center">
					<button
						type="button"
						role="tab"
						aria-selected={activa}
						class="flex items-center gap-1.5 rounded-t-lg border-x border-t px-3 py-2 text-xs font-semibold whitespace-nowrap transition-colors
							{activa
							? 'border-[var(--border)] bg-[var(--surface-raised)] text-[var(--text)]'
							: 'border-transparent text-[var(--text-subtle)] hover:bg-[var(--surface-sunken)] hover:text-[var(--text-muted)]'}
							{cart.tickets.length > 1 ? 'pr-7' : ''}"
						onclick={() => {
							cart.switchTo(ticket.id);
							searchInput?.focus();
						}}
						title={unidades ? m.sales_units_in_ticket({ units: unidades }) : m.sales_ticket_empty()}
					>
						<Icon name="cart" size={13} />
						{ticketLabel(ticket)}
						{#if unidades}
							<span
								class="rounded-full px-1.5 text-[10px] tabular-nums
									{activa
									? 'bg-[var(--accent)] text-[var(--accent-text)]'
									: 'bg-[var(--surface-sunken)] text-[var(--text-muted)]'}"
							>
								{unidades}
							</span>
						{/if}
					</button>

					{#if cart.tickets.length > 1}
						<button
							type="button"
							class="absolute right-1.5 rounded p-0.5 text-[var(--text-subtle)] opacity-0 group-hover:opacity-100 hover:text-[var(--negative)] focus-visible:opacity-100"
							onclick={() => cart.close(ticket.id)}
							title={m.sales_ticket_discard()}
							aria-label={m.sales_ticket_discard_named({ ticket: ticketLabel(ticket) })}
						>
							<Icon name="close" size={12} />
						</button>
					{/if}
				</div>
			{/each}

			<button
				type="button"
				class="my-1 ml-1 shrink-0 rounded-lg px-2 text-[var(--text-subtle)] hover:bg-[var(--surface-sunken)] hover:text-[var(--accent)] disabled:opacity-40"
				onclick={nuevaVenta}
				disabled={!cart.canOpenMore}
				title={cart.canOpenMore ? m.sales_ticket_hold() : m.sales_ticket_max()}
				aria-label={m.sales_ticket_new()}
			>
				<Icon name="plus" size={15} />
			</button>
		</div>

		<header
			class="flex shrink-0 items-center justify-between gap-2 border-b border-[var(--border)] px-4 py-2.5"
		>
			<h2 class="flex items-center gap-2 text-sm font-bold text-[var(--text)]">
				{ticketLabel(cart.active)}
				{#if !cart.isEmpty}
					<span class="badge bg-[var(--surface-sunken)] text-[var(--text-muted)]">
						{cart.count}
					</span>
				{/if}
			</h2>
			{#if !cart.isEmpty}
				<button
					type="button"
					class="rounded-lg p-1.5 text-[var(--text-subtle)] hover:bg-[var(--negative-bg)] hover:text-[var(--negative)]"
					onclick={() => {
						cart.clear();
						searchInput?.focus();
					}}
					title={m.sales_ticket_clear()}
					aria-label={m.sales_ticket_clear()}
				>
					<Icon name="trash" size={15} />
				</button>
			{/if}
		</header>

		<div class="min-h-0 flex-1 overflow-y-auto">
			{#if cart.isEmpty}
				<EmptyState
					icon="barcode"
					title={m.sales_cart_empty()}
					description={cart.tickets.length > 1
						? m.sales_cart_empty_hint_switch()
						: m.sales_cart_empty_hint()}
					compact
				/>
			{:else}
				<ul class="divide-y divide-[var(--border)]">
					{#each cart.lines as line (line.id_product)}
						<li class="flex items-center gap-2 px-3 py-2.5">
							<div class="min-w-0 flex-1">
								<p class="truncate text-sm font-medium text-[var(--text)]" title={line.name}>
									{line.name}
								</p>
								<p class="text-xs tabular-nums text-[var(--text-subtle)]">
									{formatMoney(line.price)} {m.sales_each()}
								</p>
							</div>

							<div class="flex shrink-0 items-center gap-1">
								<button
									type="button"
									class="grid h-7 w-7 place-items-center rounded-md border border-[var(--border)] text-[var(--text-muted)] hover:bg-[var(--surface-sunken)]"
									onclick={() => cart.decrement(line.id_product)}
									aria-label={m.sales_remove_one({ product: line.name })}
								>
									<Icon name="minus" size={13} />
								</button>

								<input
									type="number"
									class="input h-7 w-12 px-1 text-center text-sm tabular-nums"
									value={line.quantity}
									min="1"
									max={line.stock}
									aria-label={m.sales_quantity_of({ product: line.name })}
									onchange={(e) => {
										const next = Number((e.currentTarget as HTMLInputElement).value);
										const result = cart.setQuantity(line.id_product, next);
										if (!result.ok) {
											toasts.warning(cartMessage(result.reason));
											(e.currentTarget as HTMLInputElement).value = String(line.quantity);
										}
									}}
								/>

								<button
									type="button"
									class="grid h-7 w-7 place-items-center rounded-md border border-[var(--border)] text-[var(--text-muted)] hover:bg-[var(--surface-sunken)] disabled:opacity-40"
									onclick={() => {
										const result = cart.increment(line.id_product);
										if (!result.ok) toasts.warning(cartMessage(result.reason));
									}}
									disabled={line.quantity >= line.stock}
									aria-label={m.sales_add_one({ product: line.name })}
								>
									<Icon name="plus" size={13} />
								</button>
							</div>

							<span
								class="w-20 shrink-0 text-right text-sm font-semibold tabular-nums text-[var(--text)]"
							>
								{formatMoney(cart.lineTotal(line))}
							</span>

							<button
								type="button"
								class="shrink-0 rounded p-1 text-[var(--text-subtle)] hover:text-[var(--negative)]"
								onclick={() => cart.remove(line.id_product)}
								aria-label={m.sales_remove_line({ product: line.name })}
							>
								<Icon name="close" size={14} />
							</button>
						</li>
					{/each}
				</ul>
			{/if}
		</div>

		<footer class="shrink-0 border-t border-[var(--border)] p-4">
			<dl class="space-y-1.5 text-sm">
				<div class="flex justify-between text-[var(--text-muted)]">
					<dt>{m.common_subtotal()}</dt>
					<dd class="tabular-nums">{formatMoney(totals.subtotal)}</dd>
				</div>
				<div class="flex justify-between text-[var(--text-muted)]">
					<!-- El nombre del impuesto lo configura el negocio, no el idioma. -->
					<dt>{taxLabel()}</dt>
					<dd class="tabular-nums">{formatMoney(totals.tax)}</dd>
				</div>
				<div
					class="flex justify-between border-t border-[var(--border)] pt-2 text-lg font-bold text-[var(--text)]"
				>
					<dt>{m.common_total()}</dt>
					<dd class="tabular-nums">{formatMoney(totals.total)}</dd>
				</div>
			</dl>

			<button
				type="button"
				class="btn btn-primary mt-3 h-12 w-full text-base"
				onclick={openPayment}
				disabled={cart.isEmpty}
			>
				<Icon name="wallet" size={18} />
				{m.sales_charge()}
				<kbd class="rounded border border-white/30 px-1 text-[10px]">F1</kbd>
			</button>
		</footer>
	</aside>
	</div>
</div>

<!-- ------------------------------------------------------------ cobro -->
<Modal
	open={paymentOpen}
	title={m.sales_charge_sale()}
	description={m.sales_invoice_number({ number: currentSaleNumber })}
	busy={submitting}
	onclose={() => (paymentOpen = false)}
>
	<form
		id="payment-form"
		method="POST"
		action="?/cobrar"
		use:enhance={submit({
			errorTitle: m.sales_charge_failed(),
			setBusy: (v) => (submitting = v),
			// La venta solo se cierra cuando el backend la confirmó. Si había otra
			// en espera, queda activa y el cajero sigue sin tocar nada.
			onRedirect: () => cart.completed(),
			onFailure: () => (paymentOpen = false)
		})}
		class="space-y-4"
	>
		<input type="hidden" name="sale_number" value={currentSaleNumber} />
		<input
			type="hidden"
			name="lines"
			value={JSON.stringify(
				cart.lines.map((l) => ({ id_product: l.id_product, quantity: l.quantity }))
			)}
		/>

		<div class="rounded-lg bg-[var(--surface-sunken)] p-4 text-center">
			<p class="text-xs font-semibold tracking-wide text-[var(--text-subtle)] uppercase">
				{m.sales_amount_due()}
			</p>
			<p class="mt-1 text-3xl font-bold text-[var(--text)]">{formatMoney(totals.total)}</p>
		</div>

		<div>
			<span class="label">{m.sales_payment_method()}</span>
			<div class="grid grid-cols-2 gap-2">
				{#each PAYMENT_METHODS as method}
					<label
						class="flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-2 text-sm transition-colors {paymentMethod ===
						method
							? 'border-[var(--accent)] bg-[var(--surface-sunken)] font-semibold text-[var(--text)]'
							: 'border-[var(--border)] text-[var(--text-muted)] hover:bg-[var(--surface-sunken)]'}"
					>
						<!--
							El `value` va sin traducir: es lo que se guarda en
							`sales.payment_method` y contra lo que comparan las plantillas y
							los reportes. Lo que se traduce es el rótulo.
						-->
						<input
							type="radio"
							name="payment_method"
							value={method}
							bind:group={paymentMethod}
							class="sr-only"
						/>
						<Icon name={method === 'Efectivo' ? 'wallet' : 'idcard'} size={15} />
						{paymentLabel(method)}
					</label>
				{/each}
			</div>
		</div>

		{#if isCash}
			<div>
				<Field
					label={m.sales_cash_received()}
					name="cash_received"
					bind:value={cashInput}
					inputmode="decimal"
					icon="wallet"
					required
					error={insufficient ? m.sales_cash_short() : undefined}
				/>
				<div class="mt-2 flex flex-wrap gap-1.5">
					{#each quickCash(totals.total) as amount}
						<button
							type="button"
							class="btn btn-ghost px-2.5 py-1 text-xs tabular-nums"
							onclick={() => (cashInput = amount.toFixed(2))}
						>
							{formatMoney(amount)}
						</button>
					{/each}
				</div>
			</div>

			<div
				class="flex items-center justify-between rounded-lg border border-[var(--border)] px-4 py-3"
			>
				<span class="text-sm font-semibold text-[var(--text-muted)]">{m.sales_change_due()}</span>
				<span
					class="text-xl font-bold tabular-nums {insufficient
						? 'text-[var(--negative)]'
						: 'text-[var(--positive)]'}"
				>
					{formatMoney(change)}
				</span>
			</div>
		{:else}
			<!-- Sin efectivo no hay vuelto: se cobra el importe exacto. -->
			<input type="hidden" name="cash_received" value={totals.total.toFixed(2)} />
		{/if}

		<div>
			<label class="label" for="client-select">{m.sales_client_optional()}</label>
			<select
				id="client-select"
				name="client_id"
				value={cart.clientId}
				onchange={(e) => cart.setClient(e.currentTarget.value)}
				class="input"
			>
				<option value="">{m.sales_client_walk_in()}</option>
				{#each data.clients as client (client.id_client)}
					<option value={client.id_client}>
						{client.name}
						{client.last_name} — {client.identification}
					</option>
				{/each}
			</select>
		</div>
	</form>

	{#snippet footer()}
		<button
			type="button"
			class="btn btn-ghost"
			onclick={() => (paymentOpen = false)}
			disabled={submitting}
		>
			{m.common_cancel()}
		</button>
		<button
			type="submit"
			form="payment-form"
			class="btn btn-primary"
			disabled={submitting || insufficient || cart.isEmpty}
		>
			{#if submitting}
				<Spinner size={15} />
				{m.common_registering()}
			{:else}
				<Icon name="check" size={15} />
				{m.sales_confirm_charge()}
			{/if}
		</button>
	{/snippet}
</Modal>

<!-- ------------------------------------------------------ abrir caja -->
<Modal
	open={cashOpen}
	title={m.sales_open_register()}
	description={m.sales_open_register_hint()}
	size="sm"
	onclose={() => (cashOpen = false)}
>
	<form
		id="open-cash-form"
		method="POST"
		action="?/abrirCaja"
		use:enhance={() => {
			return async ({ result, update }) => {
				if (result.type === 'success') {
					toasts.success(m.sales_register_opened(), m.sales_register_opened_hint());
					cashOpen = false;
				}
				await update();
			};
		}}
	>
		<Field
			label={m.sales_opening_amount()}
			name="opening_amount"
			value="0"
			inputmode="decimal"
			icon="wallet"
			required
			hint={m.sales_opening_amount_hint()}
		/>
	</form>

	{#snippet footer()}
		<button type="button" class="btn btn-ghost" onclick={() => (cashOpen = false)}>
			{m.common_cancel()}
		</button>
		<button type="submit" form="open-cash-form" class="btn btn-primary">
			<Icon name="check" size={15} />
			{m.sales_open_register()}
		</button>
	{/snippet}
</Modal>
