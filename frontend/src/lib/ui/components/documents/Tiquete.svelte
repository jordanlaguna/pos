<script lang="ts">
	/**
	 * Tiquete térmico.
	 *
	 * El documento de un abarrotes: una columna, sin colores, ancho de rollo. No
	 * lleva franjas de marca a propósito —una impresora térmica no imprime color y
	 * un fondo oscuro sale como una mancha gris— y el logo va en blanco y negro
	 * por la misma razón.
	 *
	 * El ancho de la hoja lo pone `@page` desde acá, no una clase: `@page` es una
	 * regla global y cada plantilla necesita la suya.
	 */
	import { formatMoney, taxLabel } from '$lib/domain/money';
	import { formatDateTime, fullName } from '$lib/ui/format';
	import { issuerLines, returnedTotal, type DocumentProps } from '$lib/domain/documents';
	import { documentLabels, issuerText } from '$lib/ui/documents';

	let {
		sale,
		client,
		returns,
		settings,
		logoUrl,
		barcodes = {},
		docLocale
	}: DocumentProps = $props();

	/*
	 * El texto del documento sale de acá y no de `m.*()` (RN-29, T-811): se emite
	 * en el idioma de la compañía, no en el de la pantalla. La plantilla no importa
	 * el catálogo, así que no tiene forma de equivocarse.
	 */
	const t = $derived(documentLabels(docLocale));

	const doc = $derived(settings.document);
	const emisor = $derived(issuerText(issuerLines(settings), t));
	const devuelto = $derived(returnedTotal(returns));
</script>

<svelte:head>
	{@html `<style>@media print { @page { size: ${doc.receiptWidth}mm auto; margin: 3mm; } }</style>`}
</svelte:head>

<article
	class="print-sheet card mx-auto p-6 sm:p-8"
	style="max-width: 22rem; font-variant-numeric: tabular-nums"
>
	<header class="border-b border-dashed border-[var(--border)] pb-4 text-center">
		{#if doc.showLogo && logoUrl}
			<img
				src={logoUrl}
				alt=""
				class="mx-auto mb-2 max-h-14 w-auto object-contain"
				style="filter: grayscale(1)"
			/>
		{/if}
		<h1 class="text-lg font-bold tracking-tight text-[var(--text)]">
			{settings.business.name}
		</h1>
		{#each emisor as line (line)}
			<p class="text-[11px] leading-snug text-[var(--text-muted)]">{line}</p>
		{/each}

		<p class="mt-3 text-sm font-semibold text-[var(--text)]">
			{t.invoiceNumber(sale.sale_number)}
		</p>
		<p class="text-xs text-[var(--text-muted)]">{formatDateTime(sale.created_at, docLocale)}</p>
	</header>

	<dl
		class="grid grid-cols-2 gap-x-4 gap-y-1 border-b border-dashed border-[var(--border)] py-3 text-xs"
	>
		<dt class="text-[var(--text-subtle)]">{t.client}</dt>
		<dd class="text-right text-[var(--text)]">
			{client ? fullName(client) : t.walkIn}
		</dd>

		{#if client?.identification}
			<dt class="text-[var(--text-subtle)]">{t.clientId}</dt>
			<dd class="text-right text-[var(--text)]">{client.identification}</dd>
		{/if}

		<dt class="text-[var(--text-subtle)]">{t.servedBy}</dt>
		<dd class="text-right text-[var(--text)]">{sale.user_name ?? '—'}</dd>

		<dt class="text-[var(--text-subtle)]">{t.paymentMethod}</dt>
		<dd class="text-right text-[var(--text)]">{t.paymentName(sale.payment_method)}</dd>
	</dl>

	{#if sale.items.length}
		<table class="w-full border-b border-dashed border-[var(--border)] py-2 text-xs">
			<thead>
				<tr class="text-[var(--text-subtle)]">
					<th scope="col" class="py-2 text-left font-semibold">{t.colProduct}</th>
					<th scope="col" class="py-2 text-right font-semibold">{t.colQuantity}</th>
					<th scope="col" class="py-2 text-right font-semibold">{t.colUnitPrice}</th>
					<th scope="col" class="py-2 text-right font-semibold">{t.colTotal}</th>
				</tr>
			</thead>
			<tbody>
				{#each sale.items as item (item.id_product)}
					<tr class="align-top">
						<td class="py-1 pr-2 text-[var(--text)]">
							{item.name}
							{#if doc.showBarcode && barcodes[item.id_product]}
								<span class="block font-mono text-[10px] text-[var(--text-subtle)]">
									{barcodes[item.id_product]}
								</span>
							{/if}
						</td>
						<td class="py-1 text-right text-[var(--text-muted)]">{item.quantity}</td>
						<td class="py-1 text-right text-[var(--text-muted)]">{formatMoney(item.price)}</td>
						<td class="py-1 text-right font-medium text-[var(--text)]">
							{formatMoney(item.subtotal)}
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	{:else}
		<p
			class="border-b border-dashed border-[var(--border)] py-4 text-center text-xs text-[var(--text-subtle)]"
		>
			{t.noDetail}
			<span class="no-print block">
				{t.noDetailHint('GET /sales/sale/{id}')}
			</span>
		</p>
	{/if}

	<dl class="space-y-1 py-3 text-sm">
		<div class="flex justify-between text-[var(--text-muted)]">
			<dt>{t.subtotal}</dt>
			<dd>{formatMoney(sale.subtotal)}</dd>
		</div>
		<div class="flex justify-between text-[var(--text-muted)]">
			<dt>{taxLabel()}</dt>
			<dd>{formatMoney(sale.tax)}</dd>
		</div>
		<div
			class="flex justify-between border-t border-[var(--border)] pt-2 text-base font-bold text-[var(--text)]"
		>
			<dt>{t.total}</dt>
			<dd>{formatMoney(sale.total)}</dd>
		</div>

		{#if sale.payment_method === 'Efectivo'}
			<div class="flex justify-between pt-1 text-[var(--text-muted)]">
				<dt>{t.cashReceived}</dt>
				<dd>{formatMoney(sale.cash_received)}</dd>
			</div>
			<div class="flex justify-between text-[var(--text-muted)]">
				<dt>{t.change}</dt>
				<dd>{formatMoney(sale.change_given)}</dd>
			</div>
		{/if}

		{#if devuelto > 0}
			<div class="flex justify-between pt-1 font-semibold text-[var(--negative)]">
				<dt>{t.returned}</dt>
				<dd>−{formatMoney(devuelto)}</dd>
			</div>
		{/if}
	</dl>

	<footer class="border-t border-dashed border-[var(--border)] pt-4 text-center">
		{#if doc.thanksMessage}
			<p class="text-xs text-[var(--text-muted)]">{doc.thanksMessage}</p>
		{/if}
		{#if doc.legalNotice}
			<p class="mt-1 text-[10px] text-[var(--text-subtle)]">{doc.legalNotice}</p>
		{/if}
	</footer>
</article>
