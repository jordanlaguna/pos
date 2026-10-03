<script lang="ts">
	import { enhance } from '$app/forms';
	import { submit } from '$lib/ui/forms';
	import Icon from '$lib/ui/components/Icon.svelte';
	import Modal from '$lib/ui/components/Modal.svelte';
	import Spinner from '$lib/ui/components/Spinner.svelte';
	import DocumentSheet from '$lib/ui/components/documents/DocumentSheet.svelte';
	import { formatMoney } from '$lib/domain/money';
	import { formatDateTime } from '$lib/ui/format';
	import { businessName } from '$lib/domain/settings';
	import { CREDIT_NOTE, DEBIT_NOTE } from '$lib/domain/documentType';
	import { PAYMENT_METHODS } from '$lib/domain/types';
	import { documentTypeLabel, paymentLabel } from '$lib/ui/messages';
	import { m } from '$lib/paraglide/messages.js';
	import type { ActionData, PageData } from './$types';

	let { data, form }: { data: PageData; form: ActionData } = $props();

	const sale = $derived(data.sale);
	const isFullyReturned = $derived(data.saleReturns.some((r) => r.is_full));
	const logoUrl = $derived(data.logoVersion ? `/marca/logo?v=${data.logoVersion}` : null);

	/*
	 * Anular (RN-89): solo un comprobante, y solo entero. Uno que ya tiene
	 * devoluciones no se anula —lo que queda se devuelve—, así que el botón no
	 * aparece; el servidor lo rechaza igual si alguien lo intenta.
	 */
	const puedeAnular = $derived(
		Boolean(sale.document_type) && data.saleReturns.length === 0 && data.saleNotes.length === 0
	);
	let anulando = $state(false);
	let enviando = $state(false);

	/*
	 * La nota por monto (RF-77, T-726): sobre un comprobante y solo para el
	 * administrador, como en el servidor. La ND solo se ofrece si la compañía la
	 * tiene encendida (RN-88); la NC no se apaga.
	 */
	const puedeNota = $derived(Boolean(sale.document_type) && data.user?.role === 'admin');
	const ndEncendida = $derived(data.settings.eInvoicing.documentTypes.includes(DEBIT_NOTE));
	let notando = $state(false);
	let tipoNota = $state<string>(CREDIT_NOTE);

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
		{#if puedeNota}
			<button type="button" class="btn btn-ghost" onclick={() => (notando = true)} data-nota-monto>
				<Icon name="edit" size={15} />
				{m.invoice_note()}
			</button>
		{/if}
		{#if puedeAnular}
			<button type="button" class="btn btn-ghost text-[var(--negative)]" onclick={() => (anulando = true)}>
				<Icon name="close" size={15} />
				{m.invoice_annul()}
			</button>
		{/if}
		<!--
			El PDF sale de acá y de ningún otro lado (RN-86, T-922): el diálogo de
			impresión del navegador lo guarda con la plantilla configurada, que es la
			que lleva el bloque fiscal. El que armaba el backend era un cuarto
			documento sin nada de eso.
		-->
		<button type="button" class="btn btn-primary" onclick={print} title={m.invoice_print_hint()}>
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
					{#if saleReturn.document_type}
						·
						<a href="/devoluciones/{saleReturn.id}" class="font-semibold underline">
							{saleReturn.reference_code === '01'
								? m.returns_view_annulment()
								: m.returns_view_credit_note()}
						</a>
					{/if}
				</li>
			{/each}
		</ul>
	</div>
{/if}

{#if data.saleNotes.length}
	<div class="no-print mb-4 rounded-lg border border-[var(--border)] bg-[var(--surface-2)] p-3 text-sm">
		<p class="flex items-center gap-2 font-semibold text-[var(--text)]">
			<Icon name="edit" size={15} />
			{m.invoice_notes_list()}
		</p>
		<ul class="mt-1.5 space-y-0.5 pl-6 text-xs text-[var(--text-muted)]">
			{#each data.saleNotes as nota (nota.id)}
				<li>
					{m.invoice_note_row({
						date: formatDateTime(nota.created_at),
						document: documentTypeLabel(nota.document_type) ?? nota.document_type,
						total: formatMoney(nota.total),
						reason: nota.reason
					})}
					·
					<a href="/notas/{nota.id}" class="font-semibold underline" data-nota-enlace>
						{m.invoice_note_view()}
					</a>
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

<!-- ------------------------------------------------------ anular (RN-89) -->
<Modal
	open={anulando}
	title={m.invoice_annul_title({ number: sale.sale_number })}
	description={m.invoice_annul_hint()}
	busy={enviando}
	onclose={() => (anulando = false)}
>
	<form
		id="annul-form"
		method="POST"
		action="?/anular"
		use:enhance={submit({
			errorTitle: m.invoice_annul_failed(),
			setBusy: (v) => (enviando = v)
		})}
	>
		<label class="label" for="annul-reason">{m.returns_reason_label()}</label>
		<textarea
			id="annul-reason"
			name="reason"
			rows="3"
			required
			maxlength="255"
			class="input resize-y"
			placeholder={m.invoice_annul_reason_placeholder()}
			aria-invalid={form?.errors?.reason ? 'true' : undefined}
		></textarea>
		{#if form?.errors?.reason}
			<p class="mt-1 text-xs text-[var(--negative)]">{form.errors.reason}</p>
		{/if}
	</form>

	{#snippet footer()}
		<button type="button" class="btn btn-ghost" onclick={() => (anulando = false)} disabled={enviando}>
			{m.common_cancel()}
		</button>
		<button type="submit" form="annul-form" class="btn btn-primary" disabled={enviando}>
			{#if enviando}
				<Spinner size={15} />
				{m.common_registering()}
			{:else}
				<Icon name="check" size={15} />
				{m.invoice_annul_confirm()}
			{/if}
		</button>
	{/snippet}
</Modal>

<!-- ---------------------------------------- nota por monto (RF-77, T-726) -->
<Modal
	open={notando}
	title={m.invoice_note_title({ number: sale.sale_number })}
	description={m.invoice_note_hint()}
	busy={enviando}
	onclose={() => (notando = false)}
>
	<form
		id="note-form"
		method="POST"
		action="?/nota"
		class="space-y-4"
		use:enhance={submit({
			errorTitle: m.invoice_note_failed(),
			setBusy: (v) => (enviando = v)
		})}
	>
		<fieldset>
			<legend class="label">{m.invoice_note_type()}</legend>
			<div class="space-y-1.5">
				<label class="flex items-center gap-2 text-sm">
					<input type="radio" name="document_type" value={CREDIT_NOTE} bind:group={tipoNota} />
					{m.invoice_note_credit()}
				</label>
				<label class="flex items-center gap-2 text-sm">
					<input
						type="radio"
						name="document_type"
						value={DEBIT_NOTE}
						bind:group={tipoNota}
						disabled={!ndEncendida}
					/>
					{m.invoice_note_debit()}
				</label>
				{#if !ndEncendida}
					<p class="pl-6 text-xs text-[var(--text-subtle)]">{m.invoice_note_debit_off()}</p>
				{/if}
			</div>
		</fieldset>

		<fieldset>
			<legend class="label">{m.invoice_note_lines()}</legend>
			<div class="space-y-2">
				{#each sale.items as item (item.id_product)}
					<div class="flex items-center justify-between gap-3">
						<label for="monto-{item.id_product}" class="min-w-0 flex-1 truncate text-sm">
							{m.invoice_note_line({ product: item.name, price: formatMoney(item.price) })}
						</label>
						<input
							id="monto-{item.id_product}"
							name="monto_{item.id_product}"
							type="text"
							inputmode="decimal"
							class="input w-32 text-right tabular-nums"
							autocomplete="off"
						/>
					</div>
				{/each}
			</div>
		</fieldset>

		{#if tipoNota === DEBIT_NOTE}
			<div>
				<label class="label" for="note-payment">{m.invoice_note_payment()}</label>
				<select id="note-payment" name="payment_method" class="input">
					{#each PAYMENT_METHODS as metodo (metodo)}
						<option value={metodo}>{paymentLabel(metodo)}</option>
					{/each}
				</select>
			</div>
		{/if}

		<div>
			<label class="label" for="note-reason">{m.returns_reason_label()}</label>
			<textarea
				id="note-reason"
				name="reason"
				rows="2"
				required
				maxlength="255"
				class="input resize-y"
				placeholder={m.invoice_note_reason_placeholder()}
			></textarea>
		</div>
	</form>

	{#snippet footer()}
		<button type="button" class="btn btn-ghost" onclick={() => (notando = false)} disabled={enviando}>
			{m.common_cancel()}
		</button>
		<button type="submit" form="note-form" class="btn btn-primary" disabled={enviando}>
			{#if enviando}
				<Spinner size={15} />
				{m.common_registering()}
			{:else}
				<Icon name="check" size={15} />
				{m.invoice_note_confirm()}
			{/if}
		</button>
	{/snippet}
</Modal>
