<script lang="ts">
	/**
	 * Tiquete térmico.
	 *
	 * El documento de un abarrotes: una columna, sin colores, ancho de rollo. No
	 * lleva franjas de marca a propósito —una impresora térmica no imprime color y
	 * un fondo oscuro sale como una mancha gris— y el logo va en blanco y negro
	 * por la misma razón.
	 *
	 * Lleva lo mismo que las dos de página (RN-86, T-731), acomodado al rollo: en
	 * 58 mm no caben nueve columnas, así que cada producto va en su renglón con el
	 * total a la derecha y, debajo, en chico, la cantidad con su unidad y su
	 * precio, el impuesto y el CABYS.
	 *
	 * El ancho de la hoja lo pone `@page` desde acá, no una clase: `@page` es una
	 * regla global y cada plantilla necesita la suya.
	 */
	import { formatMoney, ratePercentText } from '$lib/domain/money';
	import { formatDateTime, fullName } from '$lib/ui/format';
	import {
		SALE_CONDITION_CASH,
		documentKind,
		documentLines,
		documentNumber,
		documentSummary,
		exchangeRate,
		issuerActivity,
		issuerLines,
		returnedTotal,
		type DocumentProps
	} from '$lib/domain/documents';
	import { documentLabels, issuerText } from '$lib/ui/documents';
	import FiscalBlock from './FiscalBlock.svelte';

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
	/** Tiquete o factura: lo dice la venta, no la configuración de hoy (RN-85). */
	const kind = $derived(documentKind(sale));
	/** Un comprobante electrónico lleva lo que pide Hacienda (RN-86). */
	const fiscal = $derived(kind !== 'invoice');
	const emisor = $derived(
		issuerText(
			issuerLines(settings, fiscal ? { activity: issuerActivity(sale, settings) } : null),
			t
		)
	);
	const devuelto = $derived(returnedTotal(returns));
	const lineas = $derived(documentLines(sale));
	/**
	 * El resumen, con el desglose por tarifa (RF-21). Sale de lo que se GUARDÓ en
	 * cada línea, no de recalcular con la configuración de hoy.
	 */
	const resumen = $derived(documentSummary(sale));
	const moneda = $derived(
		t.currencyWithRate(settings.currency.code, exchangeRate(settings.currency.code))
	);
	const enLetras = $derived(
		t.amountInWords(sale.total, settings.currency.code, settings.currency.decimals)
	);
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
		<div data-emisor>
			{#each emisor as line (line)}
				<p class="text-[11px] leading-snug text-[var(--text-muted)]">{line}</p>
			{/each}
		</div>

		<p class="mt-3 text-sm font-semibold text-[var(--text)]" data-cabecera>
			{t.numbered(kind, documentNumber(sale))}
		</p>
		<p class="text-xs text-[var(--text-muted)]">
			{t.issueDate}: {formatDateTime(sale.created_at, docLocale)}
		</p>
	</header>

	<FiscalBlock {sale} {t} locale={docLocale} variant="receipt" />

	<dl
		class="grid grid-cols-2 gap-x-4 gap-y-1 border-b border-dashed border-[var(--border)] py-3 text-xs"
		data-receptor
	>
		<dt class="text-[var(--text-subtle)]">{t.client}</dt>
		<dd class="text-right text-[var(--text)]">
			{client ? fullName(client) : t.walkIn}
		</dd>

		{#if client?.identification}
			<!-- En dos columnas el tipo es el rótulo: «Cédula física · 119870654». -->
			<dt class="text-[var(--text-subtle)]">
				{fiscal ? t.idLabel(client.identification_type) : t.clientId}
			</dt>
			<dd class="text-right text-[var(--text)]">{client.identification}</dd>
		{/if}

		{#if fiscal && client?.email}
			<dt class="text-[var(--text-subtle)]">{t.email}</dt>
			<dd class="text-right break-all text-[var(--text)]">{client.email}</dd>
		{/if}

		<dt class="text-[var(--text-subtle)]">{t.servedBy}</dt>
		<dd class="text-right text-[var(--text)]">{sale.user_name ?? '—'}</dd>

		{#if fiscal}
			<dt class="text-[var(--text-subtle)]">{t.saleCondition}</dt>
			<dd class="text-right text-[var(--text)]" data-condicion>
				{t.saleConditionName(SALE_CONDITION_CASH)}
			</dd>
		{/if}

		<dt class="text-[var(--text-subtle)]">{t.paymentMethod}</dt>
		<dd class="text-right text-[var(--text)]">{t.paymentName(sale.payment_method)}</dd>

		{#if fiscal}
			<dt class="text-[var(--text-subtle)]">{t.currency}</dt>
			<dd class="text-right text-[var(--text)]" data-moneda>{moneda}</dd>
		{/if}
	</dl>

	{#if lineas.length}
		<div class="border-b border-dashed border-[var(--border)] py-2 text-xs" data-lineas>
			<div class="flex justify-between py-1 font-semibold text-[var(--text-subtle)]">
				<span>{t.colProduct}</span>
				<span>{t.colTotal}</span>
			</div>
			<ol>
				{#each lineas as linea (linea.id_product)}
					<li class="py-1">
						<div class="flex justify-between gap-2 text-[var(--text)]">
							<span>{linea.number}. {linea.name}</span>
							<span class="shrink-0 font-medium">{formatMoney(linea.total)}</span>
						</div>
						<p class="pl-3 text-[10px] text-[var(--text-muted)]">
							{t.colQuantity}
							{t.lineQuantity(linea.quantity, linea.unit ?? '', formatMoney(linea.unitPrice))}
							· {t.taxAtRate(settings.tax.name, ratePercentText(linea.rate))}
							{formatMoney(linea.tax)}
						</p>
						{#if fiscal && linea.cabys}
							<p class="pl-3 font-mono text-[10px] text-[var(--text-subtle)]" data-cabys>
								{t.lineCabys(linea.cabys)}
							</p>
						{/if}
						{#if doc.showBarcode && barcodes[linea.id_product]}
							<p class="pl-3 font-mono text-[10px] text-[var(--text-subtle)]">
								{barcodes[linea.id_product]}
							</p>
						{/if}
					</li>
				{/each}
			</ol>
		</div>
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

	<dl class="space-y-1 py-3 text-sm" data-resumen>
		{#if fiscal}
			<div class="flex justify-between text-[var(--text-muted)]">
				<dt>{t.totalSale}</dt>
				<dd>{formatMoney(resumen.gross)}</dd>
			</div>
			<div class="flex justify-between text-[var(--text-muted)]">
				<dt>{t.totalDiscounts}</dt>
				<dd>{formatMoney(resumen.discounts)}</dd>
			</div>
			<div class="flex justify-between text-[var(--text-muted)]">
				<dt>{t.totalNet}</dt>
				<dd>{formatMoney(resumen.net)}</dd>
			</div>
		{:else}
			<div class="flex justify-between text-[var(--text-muted)]">
				<dt>{t.subtotal}</dt>
				<dd>{formatMoney(resumen.gross)}</dd>
			</div>
		{/if}
		{#each resumen.taxes as fila (fila.rate)}
			<div class="flex justify-between text-[var(--text-muted)]">
				<dt>{t.taxAtRate(settings.tax.name, ratePercentText(fila.rate))}</dt>
				<dd>{formatMoney(fila.tax)}</dd>
			</div>
		{/each}
		{#if fiscal && resumen.taxes.length > 1}
			<div class="flex justify-between text-[var(--text-muted)]">
				<dt>{t.totalTax}</dt>
				<dd>{formatMoney(resumen.tax)}</dd>
			</div>
		{/if}
		<div
			class="flex justify-between border-t border-[var(--border)] pt-2 text-base font-bold text-[var(--text)]"
		>
			<dt>{fiscal ? t.totalDocument : t.total}</dt>
			<dd>{formatMoney(resumen.total)}</dd>
		</div>

		{#if enLetras}
			<div class="pt-1 text-[10px] text-[var(--text-muted)]" data-en-letras>
				<dt class="sr-only">{t.amountInWordsLabel}</dt>
				<dd>{enLetras}</dd>
			</div>
		{/if}

		<!--
			Con lo recibido mayor que cero, como en las facturas: una nota de crédito
			no cobra (RN-89) y sin esto imprimiría «Efectivo recibido ₡0,00».
		-->
		{#if sale.payment_method === 'Efectivo' && sale.cash_received > 0}
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

	<FiscalBlock {sale} {t} locale={docLocale} variant="receipt" part="foot" />

	<footer class="border-t border-dashed border-[var(--border)] pt-4 text-center">
		{#if doc.thanksMessage}
			<p class="text-xs text-[var(--text-muted)]">{doc.thanksMessage}</p>
		{/if}
		{#if doc.legalNotice}
			<p class="mt-1 text-[10px] text-[var(--text-subtle)]">{doc.legalNotice}</p>
		{/if}
	</footer>
</article>
