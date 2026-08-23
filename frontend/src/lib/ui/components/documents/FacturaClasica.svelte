<script lang="ts">
	/**
	 * Factura clásica, página completa.
	 *
	 * Estructura sobria: franja de color con el nombre del negocio, número y
	 * fechas arriba a la derecha, emisor y receptor enfrentados, tabla de líneas
	 * con separadores punteados y bloque de totales cerrado por una banda de
	 * color. Es la forma en que están hechas las facturas comerciales que sirvieron
	 * de referencia, y la que mejor aguanta ser leída en una hoja impresa.
	 *
	 * La hoja se pinta blanca siempre, también en tema oscuro: es papel, no
	 * interfaz. Verla clara en pantalla es la única manera de saber cómo va a
	 * salir de la impresora.
	 */
	import { formatMoney, taxLabel } from '$lib/domain/money';
	import { formatDate, formatDateTime, fullName } from '$lib/ui/format';
	import {
		brandTones,
		issuerLines,
		returnedTotal,
		type DocumentProps
	} from '$lib/domain/documents';
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
	const marca = $derived(brandTones(doc.color));
	const emisor = $derived(issuerText(issuerLines(settings), t));
	const devuelto = $derived(returnedTotal(returns));
</script>

<svelte:head>
	{@html `<style>@media print { @page { size: auto; margin: 12mm; } }</style>`}
</svelte:head>

<article
	class="print-sheet mx-auto w-full max-w-3xl overflow-hidden rounded-xl border border-[var(--border)] shadow-sm"
	style="background:#ffffff; color:#0f172a; font-variant-numeric: tabular-nums"
>
	<!-- Franja del encabezado -->
	<header
		class="ink-exact flex items-center justify-between gap-4 px-8 py-6"
		style="background:{marca.base}; color:{marca.ink}"
	>
		<div class="min-w-0">
			<h1 class="truncate text-2xl font-bold tracking-tight uppercase">
				{settings.business.name}
			</h1>
			{#if settings.business.legalName && settings.business.legalName !== settings.business.name}
				<p class="truncate text-sm opacity-80">{settings.business.legalName}</p>
			{/if}
		</div>
		{#if doc.showLogo && logoUrl}
			<img src={logoUrl} alt="" class="max-h-14 w-auto shrink-0 object-contain" />
		{/if}
	</header>

	<div class="px-8 py-6">
		<!-- Número y fechas, con la línea punteada de las facturas de referencia -->
		<div class="mb-6 flex justify-end">
			<dl class="w-full max-w-xs space-y-1 text-sm">
				<div class="flex items-baseline justify-between gap-4 border-b border-dashed border-slate-300 pb-1">
					<dt class="font-semibold">{t.title(settings)} N.º</dt>
					<dd class="font-mono">{sale.sale_number}</dd>
				</div>
				<div class="flex items-baseline justify-between gap-4 border-b border-dashed border-slate-300 pb-1">
					<dt class="font-semibold">{t.date}</dt>
					<dd>{formatDate(sale.created_at, docLocale)}</dd>
				</div>
				<div class="flex items-baseline justify-between gap-4 border-b border-dashed border-slate-300 pb-1">
					<dt class="font-semibold">{t.paymentMethod}</dt>
					<dd>{t.paymentName(sale.payment_method)}</dd>
				</div>
			</dl>
		</div>

		<!-- Emisor y receptor -->
		<div class="mb-7 grid gap-6 sm:grid-cols-2">
			<section>
				<h2
					class="mb-1.5 text-xs font-bold tracking-widest uppercase"
					style="color:{marca.base}"
				>
					{t.issuer}
				</h2>
				<p class="text-sm font-bold">{settings.business.name}</p>
				{#each emisor as line (line)}
					<p class="text-xs leading-relaxed text-slate-600">{line}</p>
				{:else}
					<p class="text-xs text-slate-400">{t.issuerIncomplete}</p>
				{/each}
			</section>

			<section>
				<h2
					class="mb-1.5 text-xs font-bold tracking-widest uppercase"
					style="color:{marca.base}"
				>
					{t.client}
				</h2>
				{#if client}
					<p class="text-sm font-bold">{fullName(client)}</p>
					{#if client.identification}
						<p class="text-xs text-slate-600">{t.taxId(client.identification)}</p>
					{/if}
					{#if client.address}<p class="text-xs text-slate-600">{client.address}</p>{/if}
					{#if client.telephone}<p class="text-xs text-slate-600">{t.phone(client.telephone)}</p>{/if}
					{#if client.email}<p class="text-xs text-slate-600">{client.email}</p>{/if}
				{:else}
					<p class="text-sm font-bold">{t.walkIn}</p>
					<p class="text-xs text-slate-600">{t.walkInHint}</p>
				{/if}
			</section>
		</div>

		<!-- Detalle -->
		{#if sale.items.length}
			<table class="w-full text-sm">
				<thead>
					<tr class="border-b-2" style="border-color:{marca.base}">
						<th scope="col" class="py-2 text-left text-xs font-bold tracking-wider uppercase">
							{t.colDescription}
						</th>
						<th scope="col" class="py-2 text-right text-xs font-bold tracking-wider uppercase">
							{t.colQuantity}
						</th>
						<th scope="col" class="py-2 text-right text-xs font-bold tracking-wider uppercase">
							{t.colUnitPriceLong}
						</th>
						<th scope="col" class="py-2 text-right text-xs font-bold tracking-wider uppercase">
							{t.colTotal}
						</th>
					</tr>
				</thead>
				<tbody>
					{#each sale.items as item (item.id_product)}
						<tr class="border-b border-dashed border-slate-200">
							<td class="py-2.5 pr-3 font-medium">
								{item.name}
								{#if doc.showBarcode && barcodes[item.id_product]}
									<span class="block font-mono text-[11px] font-normal text-slate-500">
										{barcodes[item.id_product]}
									</span>
								{/if}
							</td>
							<td class="py-2.5 text-right text-slate-600">{item.quantity}</td>
							<td class="py-2.5 text-right text-slate-600">{formatMoney(item.price)}</td>
							<td class="py-2.5 text-right font-semibold">{formatMoney(item.subtotal)}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		{:else}
			<p class="border-y border-dashed border-slate-200 py-6 text-center text-sm text-slate-500">
				{t.noDetail}
			</p>
		{/if}

		<!-- Totales -->
		<div class="mt-5 flex justify-end">
			<div class="w-full max-w-xs">
				<dl class="space-y-1.5 text-sm">
					<div class="flex justify-between">
						<dt class="font-semibold">{t.subtotal}</dt>
						<dd>{formatMoney(sale.subtotal)}</dd>
					</div>
					<div class="flex justify-between">
						<dt class="font-semibold">{taxLabel()}</dt>
						<dd>{formatMoney(sale.tax)}</dd>
					</div>
					{#if sale.payment_method === 'Efectivo' && sale.cash_received > 0}
						<div class="flex justify-between text-slate-600">
							<dt>{t.cashReceived}</dt>
							<dd>{formatMoney(sale.cash_received)}</dd>
						</div>
						<div class="flex justify-between text-slate-600">
							<dt>{t.change}</dt>
							<dd>{formatMoney(sale.change_given)}</dd>
						</div>
					{/if}
				</dl>

				<div
					class="ink-exact mt-2 flex items-baseline justify-between rounded px-4 py-3"
					style="background:{marca.base}; color:{marca.ink}"
				>
					<span class="text-sm font-bold tracking-wider uppercase">{t.total}</span>
					<span class="text-xl font-bold">{formatMoney(sale.total)}</span>
				</div>

				{#if devuelto > 0}
					<p class="mt-2 text-right text-sm font-semibold text-red-700">
						{t.returned}: −{formatMoney(devuelto)}
					</p>
				{/if}
			</div>
		</div>

		{#if returns.length}
			<section class="mt-6 rounded border border-red-200 bg-red-50 px-4 py-3">
				<h2 class="text-xs font-bold tracking-wider text-red-700 uppercase">
					{t.returnsApplied}
				</h2>
				<ul class="mt-1 space-y-0.5 text-xs text-red-700">
					{#each returns as devolucion (devolucion.id)}
						<li>
							{formatDateTime(devolucion.created_at, docLocale)} — {formatMoney(devolucion.total)} ·
							{devolucion.reason}
						</li>
					{/each}
				</ul>
			</section>
		{/if}

		<!-- Pie: atención y notas -->
		<div class="mt-8 grid gap-6 text-xs sm:grid-cols-2">
			<section>
				<h2 class="mb-1 font-bold" style="color:{marca.base}">{t.servedBy}</h2>
				<p class="text-slate-600">{sale.user_name ?? '—'}</p>
				<p class="text-slate-600">{formatDateTime(sale.created_at, docLocale)}</p>
			</section>
			{#if doc.notes}
				<section>
					<h2 class="mb-1 font-bold" style="color:{marca.base}">{t.notesAndTerms}</h2>
					<p class="leading-relaxed whitespace-pre-line text-slate-600">{doc.notes}</p>
				</section>
			{/if}
		</div>
	</div>

	<footer
		class="ink-exact px-8 py-4 text-center text-xs"
		style="background:{marca.deep}; color:#ffffff"
	>
		{#if doc.thanksMessage}<p class="font-semibold">{doc.thanksMessage}</p>{/if}
		{#if doc.legalNotice}<p class="mt-0.5 opacity-80">{doc.legalNotice}</p>{/if}
	</footer>
</article>
