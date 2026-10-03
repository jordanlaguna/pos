<script lang="ts">
	import Icon from '$lib/ui/components/Icon.svelte';
	import PageHeader from '$lib/ui/components/PageHeader.svelte';
	import EmptyState from '$lib/ui/components/EmptyState.svelte';
	import { formatMoney } from '$lib/domain/money';
	import { formatDateTime, formatInt, toDateInput } from '$lib/ui/format';
	import { PAYMENT_METHODS } from '$lib/domain/types';
	import { m } from '$lib/paraglide/messages.js';
	import { documentTypeLabel, paymentLabel } from '$lib/ui/messages';
	import { enhance } from '$app/forms';
	import { submit } from '$lib/ui/forms';
	import { knownState } from '$lib/domain/transmission';
	import type { EmittedDocument } from '$lib/domain/types';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	/*
	 * El comprobante de cada venta (RF-74). La columna aparece cuando hay algo
	 * que decir: con la facturación activa, o con ventas que ya lo tienen aunque
	 * después se haya apagado. En un negocio que nunca la usó sería una columna
	 * de rayas.
	 */
	const conComprobante = $derived(
		data.settings.eInvoicing.enabled || data.sales.some((s) => s.document_type)
	);

	/** El color del estado ante Hacienda (RN-39): lo que importa resalta. */
	function claseEstado(state: string | null | undefined): string {
		const s = knownState(state);
		if (s === 'accepted') return 'bg-[var(--positive-bg)] text-[var(--positive)]';
		if (s === 'rejected' || s === 'stopped') return 'bg-[var(--negative-bg)] text-[var(--negative)]';
		if (s === 'retrying') return 'bg-[var(--warning-bg)] text-[var(--warning)]';
		return 'bg-[var(--surface-sunken)] text-[var(--text-muted)]';
	}

	/** A qué pantalla pertenece un comprobante detenido: la venta, la devolución, la nota o la compra. */
	function pantallaDe(doc: EmittedDocument): string {
		if (doc.source_type === 'return') return `/devoluciones/${doc.source_id}`;
		if (doc.source_type === 'note') return `/notas/${doc.source_id}`;
		if (doc.source_type === 'purchase') return `/inventario/entradas?entrada=${doc.source_id}`;
		return `/facturas/${doc.source_id}`;
	}
	const esAdmin = $derived(data.user?.role === 'admin');

	let search = $state('');
	let method = $state('');
	let from = $state('');
	let until = $state('');
	let page = $state(1);

	const PER_PAGE = 25;

	function withinRange(value: string): boolean {
		const day = String(value).slice(0, 10);
		if (from && day < from) return false;
		if (until && day > until) return false;
		return true;
	}

	const filtered = $derived.by(() => {
		const term = search.trim().toLowerCase();
		return data.sales.filter((sale) => {
			if (method && sale.payment_method !== method) return false;
			if (!withinRange(sale.created_at)) return false;
			if (!term) return true;
			return (
				sale.sale_number.toLowerCase().includes(term) ||
				String(sale.total).includes(term)
			);
		});
	});

	// Cualquier cambio de filtro devuelve a la primera página.
	$effect(() => {
		search;
		method;
		from;
		until;
		page = 1;
	});

	const totalPages = $derived(Math.max(1, Math.ceil(filtered.length / PER_PAGE)));
	const visible = $derived(filtered.slice((page - 1) * PER_PAGE, page * PER_PAGE));
	const sumTotal = $derived(filtered.reduce((acc, s) => acc + Number(s.total), 0));

	function clearFilters() {
		search = '';
		method = '';
		from = '';
		until = '';
	}

	const hasFilters = $derived(Boolean(search || method || from || until));

	function setToday() {
		const today = toDateInput(new Date());
		from = today;
		until = today;
	}
</script>

<PageHeader
	title={m.invoices_title()}
	description={m.invoices_description()}
>
	{#snippet actions()}
		<a href="/ventas" class="btn btn-primary">
			<Icon name="cart" size={15} />
			{m.invoices_new_sale()}
		</a>
	{/snippet}
</PageHeader>

<!-- Una sola fila de filtros, arriba de todo lo que condicionan. -->
<div class="card mb-4 flex flex-wrap items-end gap-3 p-3">
	<div class="min-w-[12rem] flex-1">
		<label class="label" for="factura-buscar">{m.common_search()}</label>
		<div class="relative">
			<span
				class="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-[var(--text-subtle)]"
			>
				<Icon name="search" size={15} />
			</span>
			<input
				id="factura-buscar"
				bind:value={search}
				type="search"
				placeholder={m.invoices_search_placeholder()}
				class="input pl-9"
			/>
		</div>
	</div>

	<div>
		<label class="label" for="factura-metodo">{m.invoices_payment_method()}</label>
		<select id="factura-metodo" bind:value={method} class="input w-44">
			<option value="">{m.invoices_all_methods()}</option>
			{#each PAYMENT_METHODS as metodo}
				<option value={metodo}>{paymentLabel(metodo)}</option>
			{/each}
		</select>
	</div>

	<div>
		<label class="label" for="factura-desde">{m.invoices_from()}</label>
		<input id="factura-desde" bind:value={from} type="date" class="input w-40" />
	</div>

	<div>
		<label class="label" for="factura-hasta">{m.invoices_to()}</label>
		<input id="factura-hasta" bind:value={until} type="date" class="input w-40" />
	</div>

	<button type="button" class="btn btn-ghost" onclick={setToday}>{m.invoices_today()}</button>

	{#if hasFilters}
		<button type="button" class="btn btn-ghost" onclick={clearFilters}>
			<Icon name="close" size={14} />
			{m.invoices_clear()}
		</button>
	{/if}
</div>

{#if data.queue}
	{#if data.queue.alarm !== 'ok'}
		<!-- T-711: la antigüedad de la cola es lo único que avisa antes del plazo. -->
		<div
			class="mb-4 flex gap-2 rounded-lg border p-3 text-xs {data.queue.alarm === 'danger'
				? 'border-[var(--negative)] bg-[var(--negative-bg)] text-[var(--negative)]'
				: 'border-[var(--warning)] bg-[var(--warning-bg)] text-[var(--warning)]'}"
			role="status"
			data-alarma-cola={data.queue.alarm}
		>
			<Icon name="alert" size={15} class="mt-px shrink-0" />
			<p>
				{data.queue.alarm === 'danger'
					? m.invoices_queue_alarm_danger({
							count: data.queue.pending,
							since: formatDateTime(data.queue.oldest_pending_at ?? '')
						})
					: m.invoices_queue_alarm_warning({
							count: data.queue.pending,
							since: formatDateTime(data.queue.oldest_pending_at ?? '')
						})}
			</p>
		</div>
	{/if}
	{#if data.queue.contingency}
		<p
			class="mb-4 flex gap-2 rounded-lg border border-[var(--warning)] bg-[var(--warning-bg)] p-3 text-xs text-[var(--warning)]"
			role="status"
			data-contingencia
		>
			<Icon name="info" size={15} class="mt-px shrink-0" />
			{m.invoices_contingency()}
		</p>
	{/if}
	{#if data.queue.stopped.length}
		<!-- RF-35: lo detenido, con el motivo y el tiempo que lleva esperando. -->
		<section class="card mb-4 p-4" data-detenidos>
			<h2 class="text-sm font-bold text-[var(--negative)]">{m.invoices_stopped_title()}</h2>
			<p class="mt-0.5 text-xs text-[var(--text-subtle)]">{m.invoices_stopped_hint()}</p>
			<ul class="mt-3 divide-y divide-[var(--border)] text-xs">
				{#each data.queue.stopped as doc (doc.id)}
					<li class="flex flex-wrap items-center gap-x-4 gap-y-1 py-2" data-detenido={doc.id}>
						<a href={pantallaDe(doc)} class="font-mono font-semibold text-[var(--accent)] hover:underline">
							{doc.consecutive}
						</a>
						<span class="text-[var(--text-muted)]">{documentTypeLabel(doc.document_type) ?? ''}</span>
						<span class="min-w-0 flex-1 text-[var(--text)]">
							{doc.stop_reason ? m.invoice_stop_reason({ reason: doc.stop_reason }) : ''}
						</span>
						<span class="text-[var(--text-subtle)]">
							{m.invoices_stopped_waiting({ since: formatDateTime(doc.issued_at ?? '') })}
						</span>
						{#if esAdmin}
							<form method="POST" action="?/reintentar" use:enhance={submit()}>
								<input type="hidden" name="document_id" value={doc.id} />
								<button type="submit" class="btn btn-ghost py-1 text-xs">
									<Icon name="refresh" size={13} />
									{m.invoice_retry()}
								</button>
							</form>
						{/if}
					</li>
				{/each}
			</ul>
		</section>
	{/if}
{/if}

<div class="mb-3 flex flex-wrap items-center justify-between gap-2 text-sm">
	<p class="text-[var(--text-muted)]">
		{m.invoices_count({ count: filtered.length })}
		{#if data.queue?.pending}
			· {m.invoices_queue_pending({ count: data.queue.pending })}
		{/if}
	</p>
	<p class="text-[var(--text-muted)]">
		{m.invoices_sum({ total: formatMoney(sumTotal) })}
	</p>
</div>

<div class="card overflow-hidden">
	<div class="table-wrap">
		<table class="data-table">
			<thead>
				<tr>
					<th scope="col">{m.invoices_col_invoice()}</th>
					{#if conComprobante}
						<th scope="col">{m.invoices_col_document()}</th>
						<th scope="col">{m.invoices_col_hacienda()}</th>
					{/if}
					<th scope="col">{m.invoices_col_date()}</th>
					<th scope="col">{m.invoices_payment_method()}</th>
					<th scope="col" class="num">{m.invoices_col_subtotal()}</th>
					<th scope="col" class="num">{m.invoices_col_tax()}</th>
					<th scope="col" class="num">{m.invoices_col_total()}</th>
					<th scope="col"><span class="sr-only">{m.common_actions()}</span></th>
				</tr>
			</thead>
			<tbody>
				{#each visible as sale (sale.id)}
					<tr>
						<td class="font-mono text-xs font-semibold">{sale.sale_number}</td>
						{#if conComprobante}
							<td class="whitespace-nowrap" data-comprobante={sale.document_type ?? ''}>
								{documentTypeLabel(sale.document_type) ?? '—'}
							</td>
							<td class="whitespace-nowrap" data-hacienda={sale.einvoice_status ?? ''}>
								{#if sale.einvoice_status}
									<span class="badge {claseEstado(sale.einvoice_status)}">
										{m.invoice_state({ state: knownState(sale.einvoice_status) })}
									</span>
								{:else}
									—
								{/if}
							</td>
						{/if}
						<td class="whitespace-nowrap">{formatDateTime(sale.created_at)}</td>
						<td>{paymentLabel(sale.payment_method)}</td>
						<td class="num tabular-nums">
							{formatMoney(Number((sale as any).subtotal ?? 0))}
						</td>
						<td class="num tabular-nums">{formatMoney(Number((sale as any).tax ?? 0))}</td>
						<td class="num font-semibold tabular-nums">{formatMoney(Number(sale.total))}</td>
						<td class="text-right">
							<a
								href="/facturas/{sale.id}"
								class="inline-flex items-center gap-1 text-xs font-semibold text-[var(--accent)] hover:underline"
							>
								{m.invoices_view()}
								<Icon name="forward" size={12} />
							</a>
						</td>
					</tr>
				{:else}
					<tr>
						<td colspan={conComprobante ? 9 : 7}>
							<EmptyState
								icon="receipt"
								title={hasFilters ? m.invoices_no_results() : m.invoices_none()}
								description={hasFilters ? m.invoices_no_results_hint() : m.invoices_none_hint()}
								compact
							/>
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>

	{#if totalPages > 1}
		<div
			class="flex items-center justify-between gap-2 border-t border-[var(--border)] px-3 py-2"
		>
			<button
				type="button"
				class="btn btn-ghost px-2.5 py-1 text-xs"
				onclick={() => (page = Math.max(1, page - 1))}
				disabled={page === 1}
			>
				<Icon name="back" size={13} />
				{m.invoices_previous()}
			</button>
			<span class="text-xs text-[var(--text-muted)]">
				{m.invoices_page_of({ page, total: totalPages })}
			</span>
			<button
				type="button"
				class="btn btn-ghost px-2.5 py-1 text-xs"
				onclick={() => (page = Math.min(totalPages, page + 1))}
				disabled={page === totalPages}
			>
				{m.invoices_next()}
				<Icon name="forward" size={13} />
			</button>
		</div>
	{/if}
</div>
