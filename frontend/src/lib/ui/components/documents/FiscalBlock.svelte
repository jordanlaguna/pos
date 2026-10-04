<script lang="ts">
	/**
	 * Lo que Hacienda pide imprimir, en las tres plantillas (RN-86, T-724).
	 *
	 * **Es un solo componente a propósito.** El dueño elige la plantilla por cómo
	 * se ve, no por lo que lleva, así que lo fiscal no puede depender de cuál
	 * eligió. Tres copias de este bloque serían tres documentos que terminan
	 * diciendo cosas distintas, y el que se entrega es justo el que nadie revisó.
	 * `documents.test.ts` lee las plantillas y falla si alguna deja de incluirlo,
	 * arriba y al pie.
	 *
	 * Va en dos partes, como en la factura de referencia del usuario (T-731):
	 *
	 * - **Arriba** (`part="head"`), junto al tipo y al número de la cabecera: la
	 *   clave, que con ellos forma lo que la Nota 1 del anexo pide agrupado; la
	 *   referencia de una nota al original; y la leyenda cuando el comprobante
	 *   **todavía no vale** —pendiente de emisión o emitido en pruebas—, que no
	 *   puede ir escondida al pie (RN-17).
	 * - **Al pie** (`part="foot"`): el **QR de la clave** en cuanto la hay, como
	 *   el de la factura aceptada por Hacienda (T-705); y la resolución que lo
	 *   autoriza y dónde se verifica, solo cuando está autorizado.
	 *
	 * El consecutivo no se repite acá: es el número de la cabecera
	 * (`documentNumber`). Dos números en la misma hoja obligan a adivinar.
	 *
	 * Una venta sin tipo no imprime nada: es el documento de siempre y su leyenda
	 * es la que escribió el dueño.
	 *
	 * El texto llega resuelto en `t`, en el idioma del documento (RN-29): este
	 * componente, como las plantillas, no importa el catálogo.
	 */
	import {
		EINVOICE_RESOLUTION,
		EINVOICE_VERIFY_URL,
		claveGroups,
		documentKind,
		fiscalBlock
	} from '$lib/domain/documents';
	import type { DocumentReference, EmittedDocument } from '$lib/domain/types';
	import type { DocumentLabels } from '$lib/ui/documents';
	import { formatDate } from '$lib/ui/format';
	import QrCode from './QrCode.svelte';

	let {
		sale,
		t,
		locale,
		variant = 'sheet',
		part = 'head'
	}: {
		sale: {
			document_type?: string | null;
			einvoice?: EmittedDocument | null;
			reference?: DocumentReference | null;
		};
		t: DocumentLabels;
		/** El idioma del documento, para la fecha del comprobante referenciado. */
		locale: string;
		/** El tiquete térmico no imprime color; la hoja sí. */
		variant?: 'receipt' | 'sheet';
		part?: 'head' | 'foot';
	} = $props();

	const bloque = $derived(fiscalBlock(sale));

	/**
	 * La referencia de una nota al comprobante que modifica (RN-89): va siempre,
	 * también mientras la nota está pendiente, porque sin ella la nota no dice
	 * qué corrige.
	 */
	const referencia = $derived.by(() => {
		const r = bloque?.reference;
		if (!r) return null;
		const fecha = r.date ? formatDate(r.date, locale) : '—';
		return {
			original: t.referenceTo(documentKind({ document_type: r.document_type }), r.number, fecha),
			motivo: t.referenceReason(r.code)
		};
	});

	/** Lo que se dice arriba mientras el comprobante no vale; autorizado, nada. */
	const aviso = $derived.by(() => {
		switch (bloque?.state) {
			case 'pending':
				return t.fiscalPending;
			case 'sandbox':
				return t.fiscalSandbox;
			default:
				return null;
		}
	});

	const hoja = $derived(variant === 'sheet');

	/** Arriba hay algo que imprimir: la clave, la referencia o el aviso. */
	const conCabeza = $derived(Boolean(bloque?.emitted || referencia || aviso));
	/**
	 * Al pie, el QR en cuanto hay clave —también en pruebas: el aviso de arriba ya
	 * dice que no tiene efecto fiscal— y la resolución solo si está autorizado.
	 */
	const autorizado = $derived(bloque?.state === 'authorized');
	const conPie = $derived(Boolean(bloque?.emitted));

	/*
	 * La leyenda de pruebas va marcada: entregar sin distintivo un comprobante sin
	 * efecto fiscal es entregar un papel que parece una factura y no lo es
	 * (RN-17). En el tiquete, sin color, la marca es el peso de la letra.
	 */
	const claseAviso = $derived(
		[
			bloque?.emitted || referencia ? 'mt-1' : '',
			bloque?.state === 'sandbox'
				? hoja
					? 'font-bold text-amber-800'
					: 'font-bold text-[var(--text)] uppercase'
				: hoja
					? 'text-slate-600'
					: 'text-[var(--text-muted)]'
		].join(' ')
	);
</script>

{#if bloque && part === 'head' && conCabeza}
	<section
		class={hoja
			? 'mb-6 rounded border border-slate-300 px-4 py-3 text-xs'
			: 'border-b border-dashed border-[var(--border)] py-3 text-center text-[11px]'}
		data-fiscal={bloque.state}
	>
		{#if bloque.emitted}
			<dl class={hoja ? 'flex gap-2' : 'text-[var(--text)]'}>
				<dt class={hoja ? 'w-16 shrink-0 font-semibold' : 'text-[var(--text-subtle)]'}>
					{t.fiscalKey}
				</dt>
				<!--
					En tramos, como la factura de referencia: se lee mejor y en un rollo
					de 58 mm se parte en los espacios, no a mitad de la cédula.
				-->
				<dd class="font-mono" data-clave={bloque.emitted.clave}>
					{claveGroups(bloque.emitted.clave).join(' ')}
				</dd>
			</dl>
		{/if}

		{#if referencia}
			<p class={hoja ? 'mt-1 text-slate-700' : 'mt-1 text-[var(--text)]'} data-referencia>
				<span class="font-semibold">{t.fiscalReference}:</span>
				{referencia.original} · {referencia.motivo}
			</p>
		{/if}

		{#if aviso}
			<p class={claseAviso}>{aviso}</p>
		{/if}
	</section>
{:else if bloque?.emitted && part === 'foot' && conPie}
	<!--
		Como la factura de referencia: el texto a la izquierda y el QR a la derecha
		en la hoja; en el rollo, el QR centrado y el texto debajo.
	-->
	<section
		class={hoja
			? 'mt-6 flex items-end justify-between gap-4 text-[11px] leading-relaxed text-slate-600'
			: 'border-t border-dashed border-[var(--border)] pt-3 text-center text-[10px] text-[var(--text-muted)]'}
		data-fiscal-pie
	>
		{#if !hoja}
			<QrCode text={bloque.emitted.clave} label={t.fiscalQr} class="mx-auto mb-2 w-28" />
		{/if}
		{#if autorizado}
			<div data-fiscal-autorizado>
				<p class="italic">{t.fiscalResolution(EINVOICE_RESOLUTION)}</p>
				<p class="break-words">{t.fiscalVerify(EINVOICE_VERIFY_URL)}</p>
			</div>
		{/if}
		{#if hoja}
			<QrCode text={bloque.emitted.clave} label={t.fiscalQr} class="ml-auto w-24 shrink-0" />
		{/if}
	</section>
{/if}
