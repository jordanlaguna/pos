<script lang="ts">
	import Icon from '$lib/ui/components/Icon.svelte';
	import DocumentSheet from '$lib/ui/components/documents/DocumentSheet.svelte';
	import { DEBIT_NOTE } from '$lib/domain/documentType';
	import { businessName } from '$lib/domain/settings';
	import { m } from '$lib/paraglide/messages.js';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	const logoUrl = $derived(data.logoVersion ? `/marca/logo?v=${data.logoVersion}` : null);

	function print() {
		window.print();
	}
</script>

<svelte:head>
	<title>{m.amount_note_tab_title({ number: data.documento.sale_number })} · {businessName(data.settings)}</title>
</svelte:head>

{#if data.isNew}
	<!--
		Lo que queda por hacer en la mano: la nota ya movió la plata en el sistema,
		y el cajero tiene que cobrarla o entregarla de verdad.
	-->
	<div
		class="no-print mb-4 flex flex-wrap items-center gap-3 rounded-lg border border-[var(--positive)] bg-[var(--positive-bg)] p-3"
		role="status"
	>
		<Icon name="check" size={18} class="shrink-0 text-[var(--positive)]" />
		<p class="flex-1 text-sm font-semibold text-[var(--positive)]">
			{data.nota.document_type === DEBIT_NOTE
				? m.amount_note_registered_debit()
				: m.amount_note_registered_credit()}
		</p>
		<button type="button" class="btn btn-ghost py-1.5 text-xs" onclick={print}>
			<Icon name="printer" size={14} />
			{m.invoice_print()}
		</button>
	</div>
{/if}

<div class="no-print mb-4 flex flex-wrap items-center justify-between gap-3">
	<a
		href="/facturas/{data.nota.sale_id}"
		class="inline-flex items-center gap-1.5 text-sm font-semibold text-[var(--text-muted)] hover:text-[var(--text)]"
	>
		<Icon name="back" size={15} />
		{m.amount_note_back()}
	</a>

	<button type="button" class="btn btn-primary" onclick={print} title={m.invoice_print_hint()}>
		<Icon name="printer" size={15} />
		{m.invoice_print()}
	</button>
</div>

<!--
	La nota sale de la plantilla configurada, como la factura (RN-86), y en el
	idioma de la compañía (RN-29): es un documento para el cliente y para Hacienda.
-->
<DocumentSheet
	sale={data.documento}
	client={data.client}
	returns={[]}
	settings={data.settings}
	{logoUrl}
	docLocale={data.user?.document_locale ?? 'es'}
/>
