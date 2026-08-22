<script lang="ts">
	import { enhance } from '$app/forms';
	import { submit } from '$lib/ui/forms';
	import { page } from '$app/state';
	import Icon from '$lib/ui/components/Icon.svelte';
	import PageHeader from '$lib/ui/components/PageHeader.svelte';
	import EmptyState from '$lib/ui/components/EmptyState.svelte';
	import Spinner from '$lib/ui/components/Spinner.svelte';
	import { toasts } from '$lib/ui/stores/toast.svelte';
	import { formatMoney, round2, taxName, taxRate } from '$lib/domain/money';
	import { formatDateTime, formatInt } from '$lib/ui/format';
	import { m } from '$lib/paraglide/messages.js';
	import { paymentLabel } from '$lib/ui/messages';
	import type { ActionData, PageData } from './$types';

	let { data, form }: { data: PageData; form: ActionData } = $props();

	let saleSearch = $state('');
	let submitting = $state(false);

	// Cantidades a devolver, por id de producto.
	let quantities = $state<Record<number, number>>({});

	const selected = $derived(data.selected);

	/** Unidades que todavía se pueden devolver de cada línea. */
	const remaining = $derived((idProduct: number, sold: number) =>
		sold - (data.alreadyReturned[idProduct] ?? 0)
	);

	// Al cambiar de venta, las cantidades vuelven a cero.
	$effect(() => {
		selected;
		quantities = {};
	});

	const refundSubtotal = $derived.by(() => {
		if (!selected) return 0;
		return round2(
			selected.items.reduce(
				(acc, item) => acc + item.price * (quantities[item.id_product] ?? 0),
				0
			)
		);
	});
	/**
	 * Tasa con la que se cobró ESTA venta, deducida de su propio desglose.
	 *
	 * No es la tasa configurada hoy: si el negocio la cambió, lo que se devuelve
	 * es lo que se cobró. Es el mismo criterio que aplica el backend al registrar
	 * la devolución, y así lo que se ve acá coincide con lo que se reembolsa.
	 */
	const saleTaxRate = $derived(
		selected && selected.subtotal > 0 ? selected.tax / selected.subtotal : taxRate()
	);
	const refundTotal = $derived(round2(refundSubtotal * (1 + saleTaxRate)));
	const hasSelection = $derived(Object.values(quantities).some((q) => q > 0));

	const filteredSales = $derived.by(() => {
		const term = saleSearch.trim().toLowerCase();
		if (!term) return data.sales.slice(0, 8);
		return data.sales
			.filter((s) => s.sale_number.toLowerCase().includes(term))
			.slice(0, 8);
	});

	function returnAll() {
		if (!selected) return;
		const next: Record<number, number> = {};
		for (const item of selected.items) {
			next[item.id_product] = remaining(item.id_product, item.quantity);
		}
		quantities = next;
	}

	/*
	 * Este aviso no puede salir del callback de `use:enhance`: la acción termina
	 * en `redirect`, y ahí Kit navega sin pasar por el callback. Se dispara al
	 * detectar `?creada=`, con guarda para que no se repita si el efecto se
	 * reevalúa por cualquier otro motivo.
	 */
	let avisada = $state<string | null>(null);

	$effect(() => {
		const creada = page.url.searchParams.get('creada');
		if (creada && creada !== avisada) {
			avisada = creada;
			toasts.success(m.returns_registered(), m.returns_stock_back());
		}
	});

</script>

<PageHeader
	title={m.returns_title()}
	description={m.returns_description()}
/>

<div class="grid gap-4 lg:grid-cols-[minmax(0,1fr)_22rem]">
	<section class="min-w-0">
		{#if !selected}
			<div class="card p-4">
				<h2 class="mb-3 text-sm font-bold text-[var(--text)]">{m.returns_pick_sale()}</h2>

				<div class="relative mb-3">
					<span
						class="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-[var(--text-subtle)]"
					>
						<Icon name="search" size={15} />
					</span>
					<input
						bind:value={saleSearch}
						type="search"
						placeholder={m.returns_search_placeholder()}
						aria-label={m.returns_search_label()}
						class="input pl-9"
					/>
				</div>

				<ul class="divide-y divide-[var(--border)]">
					{#each filteredSales as sale (sale.id)}
						<li>
							<a
								href="/devoluciones?venta={sale.id}"
								class="flex items-center gap-3 py-2.5 hover:bg-[var(--surface-sunken)]"
							>
								<span class="min-w-0 flex-1">
									<span class="block font-mono text-xs font-semibold text-[var(--text)]">
										{sale.sale_number}
									</span>
									<span class="block text-xs text-[var(--text-subtle)]">
										{formatDateTime(sale.created_at)} · {paymentLabel(sale.payment_method)}
									</span>
								</span>
								<span class="shrink-0 text-sm font-semibold tabular-nums text-[var(--text)]">
									{formatMoney(sale.total)}
								</span>
								<Icon name="forward" size={14} class="shrink-0 text-[var(--text-subtle)]" />
							</a>
						</li>
					{:else}
						<li>
							<EmptyState
								icon="receipt"
								title={m.returns_no_sales()}
								description={saleSearch ? m.returns_no_match() : m.returns_all_returned()}
								compact
							/>
						</li>
					{/each}
				</ul>
			</div>
		{:else}
			<div class="card p-4">
				<div class="mb-4 flex flex-wrap items-start justify-between gap-3">
					<div>
						<h2 class="text-sm font-bold text-[var(--text)]">
							{m.returns_invoice({ number: selected.sale_number })}
						</h2>
						<p class="text-xs text-[var(--text-subtle)]">
							{formatDateTime(selected.created_at)} · {paymentLabel(selected.payment_method)} ·
							{formatMoney(selected.total)}
						</p>
					</div>
					<div class="flex gap-2">
						<button type="button" class="btn btn-ghost py-1.5 text-xs" onclick={returnAll}>
							{m.returns_return_all()}
						</button>
						<a href="/devoluciones" class="btn btn-ghost py-1.5 text-xs">
							<Icon name="close" size={13} />
							{m.returns_change_sale()}
						</a>
					</div>
				</div>

				{#if !selected.items.length}
					<EmptyState
						icon="alert"
						title={m.returns_no_detail()}
						description={m.returns_no_detail_hint()}
						compact
					/>
				{:else}
					<form
						id="return-form"
						method="POST"
						action="?/crear"
						use:enhance={submit({
							errorTitle: m.returns_could_not_register(),
							setBusy: (v) => (submitting = v)
						})}
					>
						<input type="hidden" name="sale_id" value={selected.id} />

						<div class="table-wrap">
							<table class="data-table">
								<thead>
									<tr>
										<th scope="col">{m.returns_col_product()}</th>
										<th scope="col" class="num">{m.returns_col_price()}</th>
										<th scope="col" class="num">{m.returns_col_sold()}</th>
										<th scope="col" class="num">{m.returns_col_returned()}</th>
										<th scope="col" class="num">{m.returns_col_available()}</th>
										<th scope="col" class="num">{m.returns_col_return()}</th>
									</tr>
								</thead>
								<tbody>
									{#each selected.items as item (item.id_product)}
										{@const left = remaining(item.id_product, item.quantity)}
										<tr class:opacity-50={left === 0}>
											<td class="font-medium text-[var(--text)]">{item.name}</td>
											<td class="num tabular-nums">{formatMoney(item.price)}</td>
											<td class="num tabular-nums">{item.quantity}</td>
											<td class="num tabular-nums">
												{data.alreadyReturned[item.id_product] ?? 0}
											</td>
											<td class="num tabular-nums font-semibold">{left}</td>
											<td class="num">
												<input
													type="number"
													name="cantidad_{item.id_product}"
													class="input h-8 w-20 text-right tabular-nums"
													min="0"
													max={left}
													step="1"
													disabled={left === 0}
													value={quantities[item.id_product] ?? 0}
													aria-label={m.returns_units_of({ product: item.name })}
													onchange={(e) => {
														const raw = Math.trunc(
															Number((e.currentTarget as HTMLInputElement).value)
														);
														const clamped = Math.max(0, Math.min(left, raw || 0));
														quantities = { ...quantities, [item.id_product]: clamped };
														(e.currentTarget as HTMLInputElement).value = String(clamped);
													}}
												/>
											</td>
										</tr>
									{/each}
								</tbody>
							</table>
						</div>

						<div class="mt-4">
							<label class="label" for="return-reason">{m.returns_reason_label()}</label>
							<textarea
								id="return-reason"
								name="reason"
								rows="2"
								required
								class="input resize-y"
								placeholder={m.returns_reason_placeholder()}
								aria-invalid={form?.errors?.reason ? 'true' : undefined}
							></textarea>
							{#if form?.errors?.reason}
								<p class="mt-1 text-xs text-[var(--negative)]">{form.errors.reason}</p>
							{/if}
						</div>
					</form>
				{/if}
			</div>
		{/if}

		<!-- Historial -->
		<section class="mt-6">
			<h2 class="mb-3 text-sm font-bold text-[var(--text)]">{m.returns_history()}</h2>
			<div class="card overflow-hidden">
				<div class="table-wrap">
					<table class="data-table">
						<thead>
							<tr>
								<th scope="col">{m.returns_col_date()}</th>
								<th scope="col">{m.returns_col_invoice()}</th>
								<th scope="col">{m.returns_col_reason()}</th>
								<th scope="col">{m.returns_col_type()}</th>
								<th scope="col" class="num">{m.returns_col_amount()}</th>
							</tr>
						</thead>
						<tbody>
							{#each data.returns as record (record.id)}
								<tr>
									<td class="whitespace-nowrap text-xs">
										{formatDateTime(record.created_at)}
									</td>
									<td>
										<a
											href="/facturas/{record.sale_id}"
											class="font-mono text-xs font-semibold text-[var(--accent)] hover:underline"
										>
											{record.sale_number}
										</a>
									</td>
									<td class="max-w-xs truncate text-xs text-[var(--text-muted)]">
										{record.reason}
									</td>
									<td>
										<span
											class="badge {record.is_full
												? 'bg-[var(--negative-bg)] text-[var(--negative)]'
												: 'bg-[var(--warning-bg)] text-[var(--warning)]'}"
										>
											{record.is_full ? m.returns_full() : m.returns_partial()}
										</span>
									</td>
									<td class="num font-semibold tabular-nums">
										{formatMoney(record.total)}
									</td>
								</tr>
							{:else}
								<tr>
									<td colspan="5">
										<EmptyState
											icon="undo"
											title={m.returns_none()}
											description={m.returns_none_hint()}
											compact
										/>
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			</div>
		</section>
	</section>

	<!-- Resumen del reembolso -->
	{#if selected && selected.items.length}
		<aside class="card h-fit p-4 lg:sticky lg:top-0">
			<h2 class="mb-3 text-sm font-bold text-[var(--text)]">{m.returns_summary()}</h2>

			{#if hasSelection}
				<ul class="mb-3 space-y-1.5 text-sm">
					{#each selected.items.filter((i) => (quantities[i.id_product] ?? 0) > 0) as item (item.id_product)}
						<li class="flex justify-between gap-2">
							<span class="min-w-0 truncate text-[var(--text-muted)]">
								{item.name}
								<span class="text-[var(--text-subtle)]">
									×{quantities[item.id_product]}
								</span>
							</span>
							<span class="shrink-0 tabular-nums text-[var(--text)]">
								{formatMoney(item.price * (quantities[item.id_product] ?? 0))}
							</span>
						</li>
					{/each}
				</ul>
			{:else}
				<p class="mb-3 text-sm text-[var(--text-subtle)]">
					{m.returns_indicate_units()}
				</p>
			{/if}

			<dl class="space-y-1.5 border-t border-[var(--border)] pt-3 text-sm">
				<div class="flex justify-between text-[var(--text-muted)]">
					<dt>{m.common_subtotal()}</dt>
					<dd class="tabular-nums">{formatMoney(refundSubtotal)}</dd>
				</div>
				<div class="flex justify-between text-[var(--text-muted)]">
					<!-- El porcentaje es el de la venta original, no el configurado hoy. -->
					<dt>
							{m.returns_tax_with_rate({
								tax: taxName(),
								rate: (saleTaxRate * 100).toFixed((saleTaxRate * 100) % 1 === 0 ? 0 : 1)
							})}
						</dt>
					<dd class="tabular-nums">{formatMoney(refundTotal - refundSubtotal)}</dd>
				</div>
				<div
					class="flex justify-between border-t border-[var(--border)] pt-2 text-lg font-bold text-[var(--text)]"
				>
					<dt>{m.returns_to_refund()}</dt>
					<dd class="tabular-nums">{formatMoney(refundTotal)}</dd>
				</div>
			</dl>

			<p class="mt-3 flex items-start gap-1.5 text-xs text-[var(--text-subtle)]">
				<Icon name="info" size={13} class="mt-0.5 shrink-0" />
				{m.returns_stock_note()}
			</p>

			<button
				type="submit"
				form="return-form"
				class="btn btn-danger mt-4 w-full"
				disabled={!hasSelection || submitting}
			>
				{#if submitting}
					<Spinner size={15} />
					{m.common_registering()}
				{:else}
					<Icon name="undo" size={15} />
					{m.returns_register()}
				{/if}
			</button>
		</aside>
	{/if}
</div>
