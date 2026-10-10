<script lang="ts">
	import { onMount } from 'svelte';
	import { enhance } from '$app/forms';
	import { submit } from '$lib/ui/forms';
	import Icon from '$lib/ui/components/Icon.svelte';
	import PageHeader from '$lib/ui/components/PageHeader.svelte';
	import { formatMoney, round2 } from '$lib/domain/money';
	import { formatInt } from '$lib/ui/format';
	import { m } from '$lib/paraglide/messages.js';
	import type { Product } from '$lib/domain/types';
	import type { ActionData, PageData } from './$types';
	import Select from '$lib/ui/components/Select.svelte';

	let { data, form }: { data: PageData; form: ActionData } = $props();

	interface Linea {
		product: Product;
		quantity: number;
	}

	// Sin `bind:value` a propósito (trampa conocida de CLAUDE.md): lo que la
	// persona eligió antes de que Svelte enganche la página se perdería al
	// hidratar. El valor se lee del DOM, al montar y en cada cambio.
	let reasonId = $state('');
	onMount(() => {
		// Por el `id` y no por `bind:this`: el `<select>` vive dentro de `Select`.
		const motivo = document.getElementById('motivo') as HTMLSelectElement | null;
		if (motivo) reasonId = motivo.value;
	});
	let notes = $state('');
	let lineas = $state<Linea[]>([]);
	let submitting = $state(false);

	// ---------------------------------------------------------------- buscar

	let busqueda = $state('');
	const coincidencias = $derived.by(() => {
		const t = busqueda.trim().toLowerCase();
		if (!t) return [];
		return data.products
			.filter((p) => p.name.toLowerCase().includes(t) || p.barcode.includes(t))
			.slice(0, 6);
	});

	function agregar(product: Product) {
		const yaEsta = lineas.find((l) => l.product.id_product === product.id_product);
		if (yaEsta) {
			yaEsta.quantity += 1;
		} else {
			lineas.push({ product, quantity: 1 });
		}
		busqueda = '';
	}

	function quitar(product: Product) {
		lineas = lineas.filter((l) => l.product.id_product !== product.id_product);
	}

	// --------------------------------------------------------------- resumen

	const totalUnidades = $derived(lineas.reduce((a, l) => a + (Number(l.quantity) || 0), 0));
	// Al promedio de hoy (RN-99). Es una vista previa: el que manda es el
	// servidor, que lo relee bajo el candado al confirmar.
	const totalCosto = $derived(
		round2(lineas.reduce((a, l) => a + Number(l.product.cost ?? 0) * (Number(l.quantity) || 0), 0))
	);
	const listo = $derived(
		reasonId !== '' && lineas.length > 0 && lineas.every((l) => Number(l.quantity) > 0)
	);
	const payload = $derived(
		JSON.stringify(
			lineas.map((l) => ({ id_product: l.product.id_product, quantity: Math.trunc(Number(l.quantity)) }))
		)
	);
</script>

<PageHeader title={m.exit_new_title()} description={m.exit_new_description()}>
	{#snippet actions()}
		<a href="/inventario/salidas" class="btn btn-ghost">
			<Icon name="back" size={15} />
			{m.exit_back()}
		</a>
	{/snippet}
</PageHeader>

<form
	method="POST"
	action="?/confirmar"
	class="grid gap-4 lg:grid-cols-[2fr_1fr]"
	use:enhance={submit({ setBusy: (v) => (submitting = v) })}
>
	<input type="hidden" name="lines" value={payload} />

	<div class="space-y-4">
		<div class="card grid gap-4 p-4 sm:grid-cols-2">
			<label class="block" for="motivo">
				<span class="label">{m.exit_reason_label()}</span>
				<Select
					id="motivo"
					name="reason_id"
					onchange={(e) => (reasonId = e.currentTarget.value)}
					required
				>
					<option value="">{m.exit_reason_placeholder()}</option>
					{#each data.reasons as motivo (motivo.id)}
						<option value={String(motivo.id)}>{motivo.name}</option>
					{/each}
				</Select>
				{#if form?.errors?.reason_id}
					<span class="mt-1 block text-xs text-[var(--negative)]">{form.errors.reason_id}</span>
				{/if}
			</label>
			<label class="block" for="notas">
				<span class="label">{m.exit_notes_label()}</span>
				<input
					id="notas"
					name="notes"
					type="text"
					class="input"
					maxlength="255"
					bind:value={notes}
					placeholder={m.exit_notes_placeholder()}
				/>
			</label>
		</div>

		<div class="card p-4">
			<div class="relative">
				<span class="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-[var(--text-subtle)]">
					<Icon name="search" size={15} />
				</span>
				<input
					bind:value={busqueda}
					type="search"
					placeholder={m.exit_search_placeholder()}
					aria-label={m.exit_search_label()}
					class="input pl-9"
				/>
				{#if coincidencias.length}
					<ul
						class="absolute inset-x-0 top-[calc(100%+0.25rem)] z-20 max-h-72 overflow-y-auto rounded-lg border border-[var(--border)] bg-[var(--surface-raised)] p-1 shadow-xl"
					>
						{#each coincidencias as product (product.id_product)}
							<li>
								<button
									type="button"
									class="flex w-full items-center gap-3 rounded-md px-3 py-2 text-left hover:bg-[var(--surface-sunken)]"
									onclick={() => agregar(product)}
								>
									<span class="min-w-0 flex-1">
										<span class="block truncate text-sm text-[var(--text)]">{product.name}</span>
										<span class="block text-xs text-[var(--text-subtle)]">{product.barcode}</span>
									</span>
									<span class="shrink-0 text-xs tabular-nums text-[var(--text-subtle)]">
										{m.exit_available({ stock: formatInt(product.stock) })}
									</span>
								</button>
							</li>
						{/each}
					</ul>
				{/if}
			</div>

			<h2 class="mt-4 mb-2 text-sm font-semibold text-[var(--text)]">{m.exit_lines_title()}</h2>
			{#if lineas.length === 0}
				<p class="text-sm text-[var(--text-subtle)]">{m.exit_no_lines()}</p>
			{:else}
				<div class="table-wrap">
					<table class="data-table">
						<thead>
							<tr>
								<th scope="col">{m.exits_line_product()}</th>
								<th scope="col" class="num">{m.exits_line_quantity()}</th>
								<th scope="col" class="num">{m.exits_line_unit_cost()}</th>
								<th scope="col" class="num">{m.exits_line_subtotal()}</th>
								<th scope="col"><span class="sr-only">{m.common_actions()}</span></th>
							</tr>
						</thead>
						<tbody>
							{#each lineas as linea (linea.product.id_product)}
								<tr>
									<td>
										{linea.product.name}
										<span class="block text-xs text-[var(--text-subtle)]">
											{m.exit_available({ stock: formatInt(linea.product.stock) })}
										</span>
									</td>
									<td class="num">
										<input
											type="number"
											min="1"
											step="1"
											class="input w-24 text-right"
											bind:value={linea.quantity}
											aria-label={m.exit_quantity_of({ product: linea.product.name })}
										/>
									</td>
									<td class="num tabular-nums">{formatMoney(linea.product.cost ?? 0)}</td>
									<td class="num font-semibold tabular-nums">
										{formatMoney(round2(Number(linea.product.cost ?? 0) * (Number(linea.quantity) || 0)))}
									</td>
									<td>
										<button
											type="button"
											class="rounded-lg p-1.5 text-[var(--text-subtle)] hover:bg-[var(--negative-bg)] hover:text-[var(--negative)]"
											onclick={() => quitar(linea.product)}
											aria-label={m.exit_remove_line({ product: linea.product.name })}
										>
											<Icon name="trash" size={15} />
										</button>
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			{/if}
		</div>
	</div>

	<aside class="card h-fit space-y-3 p-4">
		<dl class="space-y-2 text-sm">
			<div class="flex justify-between">
				<dt class="text-[var(--text-muted)]">{m.exit_preview_units()}</dt>
				<dd class="font-semibold tabular-nums">{formatInt(totalUnidades)}</dd>
			</div>
			<div class="flex justify-between">
				<dt class="text-[var(--text-muted)]">{m.exit_preview_cost()}</dt>
				<dd class="font-bold tabular-nums">{formatMoney(totalCosto)}</dd>
			</div>
		</dl>
		<p class="text-xs text-[var(--text-subtle)]">{m.exit_cost_note()}</p>
		{#if form?.errors?.form}
			<p class="rounded-lg bg-[var(--negative-bg)] p-2 text-sm text-[var(--negative)]" role="alert">
				{form.errors.form}
			</p>
		{/if}
		<button type="submit" class="btn btn-primary w-full" disabled={!listo || submitting}>
			<Icon name="check" size={15} />
			{submitting ? m.exit_confirming() : m.exit_confirm()}
		</button>
		{#if !listo}
			<p class="text-xs text-[var(--text-subtle)]">
				{reasonId === '' ? m.exit_pick_reason() : m.exit_add_line()}
			</p>
		{/if}
	</aside>
</form>
