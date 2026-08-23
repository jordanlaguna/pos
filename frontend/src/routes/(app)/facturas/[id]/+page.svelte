<script lang="ts">
	import Icon from '$lib/ui/components/Icon.svelte';
	import DocumentSheet from '$lib/ui/components/documents/DocumentSheet.svelte';
	import { formatMoney } from '$lib/domain/money';
	import { formatDateTime } from '$lib/ui/format';
	import { businessName } from '$lib/domain/settings';
	import { m } from '$lib/paraglide/messages.js';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	const sale = $derived(data.sale);
	const isFullyReturned = $derived(data.saleReturns.some((r) => r.is_full));
	const logoUrl = $derived(data.logoVersion ? `/marca/logo?v=${data.logoVersion}` : null);

	function print() {
		window.print();
	}
</script>

<svelte:head>
	<title>{m.invoice_tab_title({ number: sale.sale_number })} · {businessName(data.settings)}</title>
</svelte:head>

{#if data.isNew}
	<div
		class="no-print mb-4 flex flex-wrap items-center gap-3 rounded-lg border border-[var(--positive)] bg-[var(--positive-bg)] p-3"
		role="status"
	>
		<Icon name="check" size={18} class="shrink-0 text-[var(--positive)]" />
		<p class="flex-1 text-sm font-semibold text-[var(--positive)]">
			{m.invoice_registered()}
		</p>
		<button type="button" class="btn btn-ghost py-1.5 text-xs" onclick={print}>
			<Icon name="printer" size={14} />
			{m.invoice_print()}
		</button>
		<a href="/ventas" class="btn btn-primary py-1.5 text-xs">
			<Icon name="cart" size={14} />
			{m.invoices_new_sale()}
		</a>
	</div>
{/if}

<div class="no-print mb-4 flex flex-wrap items-center justify-between gap-3">
	<a
		href="/facturas"
		class="inline-flex items-center gap-1.5 text-sm font-semibold text-[var(--text-muted)] hover:text-[var(--text)]"
	>
		<Icon name="back" size={15} />
		{m.invoice_back()}
	</a>

	<div class="flex flex-wrap gap-2">
		{#if !isFullyReturned}
			<a href="/devoluciones?venta={sale.id}" class="btn btn-ghost">
				<Icon name="undo" size={15} />
				{m.invoice_return()}
			</a>
		{/if}
		{#if data.canDownloadPdf}
			<a href="/facturas/{sale.id}/pdf" target="_blank" rel="noopener" class="btn btn-ghost">
				<Icon name="download" size={15} />
				{m.invoice_backend_pdf()}
			</a>
		{/if}
		<button type="button" class="btn btn-primary" onclick={print}>
			<Icon name="printer" size={15} />
			{m.invoice_print()}
		</button>
	</div>
</div>

{#if data.saleReturns.length}
	<div
		class="no-print mb-4 rounded-lg border border-[var(--warning)] bg-[var(--warning-bg)] p-3 text-sm text-[var(--warning)]"
	>
		<p class="flex items-center gap-2 font-semibold">
			<Icon name="undo" size={15} />
			{isFullyReturned ? m.invoice_fully_returned() : m.invoice_partially_returned()}
		</p>
		<ul class="mt-1.5 space-y-0.5 pl-6 text-xs">
			{#each data.saleReturns as saleReturn (saleReturn.id)}
				<li>
					{m.invoice_return_line({
						date: formatDateTime(saleReturn.created_at),
						total: formatMoney(saleReturn.total),
						reason: saleReturn.reason
					})}
				</li>
			{/each}
		</ul>
	</div>
{/if}

<!--
	El documento sale de la plantilla configurada en /configuracion: tiquete
	térmico para el mostrador, factura de página completa para mandar por correo.
-->
<!--
	`docLocale` es el idioma de la **compañía**, no el de la pantalla (RN-29): esta
	factura es la que se le da al cliente y la que va a Hacienda.
-->
<DocumentSheet
	{sale}
	client={data.client}
	returns={data.saleReturns}
	settings={data.settings}
	{logoUrl}
	barcodes={data.barcodes}
	docLocale={data.user?.document_locale ?? 'es'}
/>
