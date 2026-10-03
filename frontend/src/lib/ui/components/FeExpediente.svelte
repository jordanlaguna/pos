<script lang="ts">
	/**
	 * El expediente de un comprobante ante Hacienda (T-721, RF-33, RF-36): en
	 * qué estado va, por qué se detuvo si se detuvo, lo que dijo Hacienda, el
	 * próximo intento, y cada paso con su hora.
	 *
	 * Lo usan la factura, la devolución y la nota. El botón de reintentar envía
	 * a la acción `reintentar` de la pantalla que lo muestra: la regla de quién
	 * puede está en el servidor, acá solo se esconde a quien no.
	 */
	import { enhance } from '$app/forms';
	import { submit } from '$lib/ui/forms';
	import Icon from '$lib/ui/components/Icon.svelte';
	import { formatDateTime } from '$lib/ui/format';
	import { knownState, needsPerson } from '$lib/domain/transmission';
	import { m } from '$lib/paraglide/messages.js';
	import type { DocumentFile, EmittedDocument } from '$lib/domain/types';

	let {
		document,
		file,
		canRetry = false
	}: {
		document: EmittedDocument | null | undefined;
		file: DocumentFile | null | undefined;
		canRetry?: boolean;
	} = $props();

	const estado = $derived(knownState(document?.status));
	const detenido = $derived(needsPerson(estado));
	const eventos = $derived(file?.events ?? []);
	let reintentando = $state(false);

	function clase(state: string): string {
		if (state === 'accepted') return 'bg-[var(--positive-bg)] text-[var(--positive)]';
		if (state === 'rejected' || state === 'stopped')
			return 'bg-[var(--negative-bg)] text-[var(--negative)]';
		if (state === 'retrying') return 'bg-[var(--warning-bg)] text-[var(--warning)]';
		return 'bg-[var(--surface-sunken)] text-[var(--text-muted)]';
	}
</script>

{#if document?.id}
	<section class="card no-print mb-4 p-4" data-expediente data-estado={estado}>
		<div class="flex flex-wrap items-start justify-between gap-3">
			<div>
				<h2 class="text-sm font-bold text-[var(--text)]">{m.invoice_file_title()}</h2>
				<p class="mt-0.5 text-xs text-[var(--text-subtle)]">{m.invoice_file_hint()}</p>
			</div>
			<span class="badge {clase(estado)}" data-estado-hacienda>{m.invoice_state({ state: estado })}</span>
		</div>

		{#if detenido && document.stop_reason}
			<div
				class="mt-3 flex gap-2 rounded-lg border border-[var(--negative)] bg-[var(--negative-bg)] p-3 text-xs text-[var(--negative)]"
				role="status"
			>
				<Icon name="alert" size={15} class="mt-px shrink-0" />
				<div class="min-w-0 space-y-1">
					<p class="font-semibold">{m.invoice_stop_reason({ reason: document.stop_reason })}</p>
					{#if document.stop_detail}
						<p class="break-words font-mono text-[11px] opacity-90">{document.stop_detail}</p>
					{/if}
					<p class="opacity-90">{m.invoice_retry_hint()}</p>
				</div>
			</div>
		{:else if estado === 'rejected' && document.stop_detail}
			<div class="mt-3 rounded-lg border border-[var(--negative)] bg-[var(--negative-bg)] p-3 text-xs text-[var(--negative)]">
				<p class="font-semibold">{m.invoice_hacienda_detail()}</p>
				<p class="mt-1 break-words">{document.stop_detail}</p>
			</div>
		{:else if estado === 'accepted' && document.stop_detail}
			<p class="mt-3 text-xs text-[var(--text-muted)]">
				<span class="font-semibold">{m.invoice_hacienda_detail()}:</span>
				{document.stop_detail}
			</p>
		{/if}

		<div class="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-[var(--text-subtle)]">
			{#if document.last_attempt_at}
				<span>{m.invoice_last_attempt({ when: formatDateTime(document.last_attempt_at) })}</span>
			{/if}
			{#if document.next_attempt_at && !detenido}
				<span>{m.invoice_next_attempt({ when: formatDateTime(document.next_attempt_at) })}</span>
			{/if}
			{#if canRetry && detenido}
				<form
					method="POST"
					action="?/reintentar"
					use:enhance={submit({ setBusy: (b) => (reintentando = b) })}
					class="ml-auto"
				>
					<input type="hidden" name="document_id" value={document.id} />
					<button type="submit" class="btn btn-primary py-1 text-xs" disabled={reintentando} data-reintentar>
						<Icon name="refresh" size={13} />
						{m.invoice_retry()}
					</button>
				</form>
			{/if}
		</div>

		<h3 class="mt-4 text-xs font-bold uppercase tracking-wide text-[var(--text-subtle)]">
			{m.invoice_events_title()}
		</h3>
		{#if eventos.length}
			<ol class="mt-2 space-y-1.5 text-xs" data-eventos>
				{#each eventos as evento, i (i)}
					<li class="flex flex-wrap gap-x-3 gap-y-0.5">
						<span class="w-32 shrink-0 font-mono text-[var(--text-subtle)]">{formatDateTime(evento.at)}</span>
						<span class="font-semibold text-[var(--text)]">{m.invoice_event({ event: evento.event })}</span>
						{#if evento.detail}
							<span class="min-w-0 break-words text-[var(--text-muted)]">{evento.detail}</span>
						{/if}
					</li>
				{/each}
			</ol>
		{:else}
			<p class="mt-2 text-xs text-[var(--text-muted)]">{m.invoice_events_none()}</p>
		{/if}
	</section>
{/if}
