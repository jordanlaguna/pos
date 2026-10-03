<script lang="ts">
	import Icon from '$lib/ui/components/Icon.svelte';
	import DocumentSheet from '$lib/ui/components/documents/DocumentSheet.svelte';
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
	<title>{m.credit_note_tab_title({ number: data.nota.sale_number })} · {businessName(data.settings)}</title>
</svelte:head>

{#if data.isNew}
	<div
		class="no-print mb-4 flex flex-wrap items-center gap-3 rounded-lg border border-[var(--positive)] bg-[var(--positive-bg)] p-3"
		role="status"
	>
		<Icon name="check" size={18} class="shrink-0 text-[var(--positive)]" />
		<p class="flex-1 text-sm font-semibold text-[var(--positive)]">
			{data.devolucion.reference_code === '01' ? m.credit_note_annulled() : m.credit_note_registered()}
		</p>
		<button type="button" class="btn btn-ghost py-1.5 text-xs" onclick={print}>
			<Icon name="printer" size={14} />
			{m.invoice_print()}
		</button>
	</div>
{/if}

<div class="no-print mb-4 flex flex-wrap items-center justify-between gap-3">
	<a
		href="/devoluciones"
		class="inline-flex items-center gap-1.5 text-sm font-semibold text-[var(--text-muted)] hover:text-[var(--text)]"
	>
		<Icon name="back" size={15} />
		{m.credit_note_back()}
	</a>

	<div class="flex flex-wrap gap-2">
		<a href="/facturas/{data.devolucion.sale_id}" class="btn btn-ghost">
			<Icon name="receipt" size={15} />
			{m.credit_note_original()}
		</a>
		<button type="button" class="btn btn-primary" onclick={print} title={m.invoice_print_hint()}>
			<Icon name="printer" size={15} />
			{m.invoice_print()}
		</button>
	</div>
</div>

<!--
	La nota sale de la plantilla configurada, como la factura (RN-86), y en el
	idioma de la compañía (RN-29): es un documento para el cliente y para Hacienda.
-->
<DocumentSheet
	sale={data.nota}
	client={data.client}
	returns={[]}
	settings={data.settings}
	{logoUrl}
	docLocale={data.user?.document_locale ?? 'es'}
/>
