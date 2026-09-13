<script lang="ts">
	import { enhance } from '$app/forms';
	import { submit } from '$lib/ui/forms';
	import Icon from '$lib/ui/components/Icon.svelte';
	import Modal from '$lib/ui/components/Modal.svelte';
	import EmptyState from '$lib/ui/components/EmptyState.svelte';
	import { formatMoney } from '$lib/domain/money';
	import { formatDate } from '$lib/ui/format';
	import { m } from '$lib/paraglide/messages.js';
	import { entryKindLabel, entryTitle } from '$lib/ui/accounting';
	import type { ActionData, PageData } from './$types';

	let { data, form }: { data: PageData; form: ActionData } = $props();

	const RENGLONES = 4;

	let creando = $state(false);
	let filas = $state(
		Array.from({ length: RENGLONES }, () => ({ account: '', debit: '', credit: '' }))
	);
	let reclasificando = $state(false);

	const debitos = $derived(filas.reduce((t, f) => t + (Number(f.debit) || 0), 0));
	const creditos = $derived(filas.reduce((t, f) => t + (Number(f.credit) || 0), 0));
	const diferencia = $derived(Math.round((debitos - creditos) * 100) / 100);

	const hoy = new Date().toISOString().slice(0, 10);

	/** El código de la cuenta donde cae lo que el mapeo no supo clasificar. */
	const POR_CLASIFICAR = '1.9.99';

	/** Si el asiento abierto tiene algo por clasificar, se ofrece resolverlo. */
	const tienePorClasificar = $derived(
		(data.detalle?.lines ?? []).some((linea) => linea.account_code === POR_CLASIFICAR)
	);
</script>

{#if form?.success}
	<p class="mb-4 rounded-lg bg-[var(--success-soft)] px-3 py-2 text-sm">{form.success}</p>
{/if}
{#if form?.errors?.form}
	<p class="mb-4 rounded-lg bg-[var(--danger-soft)] px-3 py-2 text-sm">{form.errors.form}</p>
{/if}

<div class="mb-3 flex flex-wrap items-end justify-between gap-3">
	<form method="GET" class="flex items-end gap-2">
		<label class="text-xs text-[var(--text-subtle)]">
			{m.accounting_report_year()}
			<input name="year" type="number" class="input mt-1 w-24" value={data.year} />
		</label>
		<label class="text-xs text-[var(--text-subtle)]">
			{m.accounting_report_month()}
			<select name="month" class="input mt-1 w-32" value={data.month ?? ''}>
				<option value="">{m.accounting_report_all_year()}</option>
				{#each [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12] as mes (mes)}
					<option value={mes}>{mes}</option>
				{/each}
			</select>
		</label>
		<button type="submit" class="btn btn-ghost">{m.accounting_filter()}</button>
	</form>

	<button type="button" class="btn btn-primary" onclick={() => (creando = true)}>
		<Icon name="plus" size={15} />
		{m.accounting_new_entry()}
	</button>
</div>

<div class="grid gap-4 lg:grid-cols-[1fr_1.2fr]">
	<div class="card overflow-x-auto">
		{#if !data.asientos.length}
			<EmptyState icon="book" title={m.accounting_entry_empty()} />
		{:else}
			<table class="w-full min-w-[22rem] text-sm">
				<thead>
					<tr
						class="border-b border-[var(--border)] text-left text-xs text-[var(--text-subtle)] uppercase"
					>
						<th class="px-3 py-2 font-semibold">{m.accounting_entry_number()}</th>
						<th class="px-3 py-2 font-semibold">{m.accounting_entry_date()}</th>
						<th class="px-3 py-2 font-semibold">{m.accounting_entry_description()}</th>
					</tr>
				</thead>
				<tbody class="divide-y divide-[var(--border)]">
					{#each data.asientos as asiento (asiento.id)}
						<tr class={data.detalle?.id === asiento.id ? 'bg-[var(--surface-sunken)]' : ''}>
							<td class="px-3 py-2 tabular-nums">{asiento.entry_number}</td>
							<td class="px-3 py-2 whitespace-nowrap">{formatDate(asiento.entry_date)}</td>
							<td class="px-3 py-2">
								<a
									href="?year={data.year}{data.month ? `&month=${data.month}` : ''}&entry={asiento.id}"
									class="hover:text-[var(--accent)]"
								>
									{entryTitle(asiento)}
								</a>
								<span class="ml-1 text-xs text-[var(--text-subtle)]">
									{entryKindLabel(asiento.kind)}
								</span>
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		{/if}
	</div>

	<div class="card p-4">
		{#if !data.detalle}
			<EmptyState icon="book" title={m.accounting_tab_entries()} />
		{:else}
			<div class="mb-3">
				<h2 class="text-sm font-semibold">{entryTitle(data.detalle)}</h2>
				<p class="text-xs text-[var(--text-subtle)]">
					#{data.detalle.entry_number} · {formatDate(data.detalle.entry_date)} ·
					{entryKindLabel(data.detalle.kind)}
					{#if data.detalle.adjusts_entry_id}
						· {m.accounting_entry_adjusts({ number: data.detalle.adjusts_entry_id })}
					{/if}
				</p>
			</div>

			<div class="overflow-x-auto">
				<table class="w-full min-w-[26rem] text-sm">
					<thead>
						<tr class="text-left text-xs text-[var(--text-subtle)] uppercase">
							<th class="py-1 font-semibold">{m.accounting_account_name()}</th>
							<th class="py-1 text-right font-semibold">{m.accounting_entry_debit()}</th>
							<th class="py-1 text-right font-semibold">{m.accounting_entry_credit()}</th>
						</tr>
					</thead>
					<tbody>
						{#each data.detalle.lines ?? [] as linea (linea.account_id + '-' + linea.debit + '-' + linea.credit + '-' + (linea.memo ?? ''))}
							<tr
								class={linea.account_code === POR_CLASIFICAR ? 'text-[var(--danger)]' : ''}
							>
								<td class="py-1">
									<span class="font-mono text-xs">{linea.account_code}</span>
									{linea.account_name}
									{#if linea.tax_rate !== null}
										<span class="text-xs text-[var(--text-subtle)]">· {linea.tax_rate} %</span>
									{/if}
								</td>
								<td class="py-1 text-right tabular-nums">
									{linea.debit ? formatMoney(linea.debit) : ''}
								</td>
								<td class="py-1 text-right tabular-nums">
									{linea.credit ? formatMoney(linea.credit) : ''}
								</td>
							</tr>
						{/each}
					</tbody>
					<tfoot>
						<tr class="border-t border-[var(--border)] font-semibold">
							<td class="py-2">{m.accounting_entry_total()}</td>
							<td class="py-2 text-right tabular-nums">{formatMoney(data.detalle.total ?? 0)}</td>
							<td class="py-2 text-right tabular-nums">{formatMoney(data.detalle.total ?? 0)}</td>
						</tr>
					</tfoot>
				</table>
			</div>

			{#if tienePorClasificar}
				<div class="mt-3">
					<button type="button" class="btn btn-ghost" onclick={() => (reclasificando = true)}>
						{m.accounting_reclassify()}
					</button>
				</div>
			{/if}
		{/if}
	</div>
</div>

<Modal open={creando} title={m.accounting_new_entry()} onclose={() => (creando = false)}>
	<form method="POST" action="?/crear" use:enhance={submit({ onSuccess: () => (creando = false) })} class="grid gap-3">
		<div class="grid gap-3 sm:grid-cols-2">
			<div>
	<label class="label" for="entry_date">{m.accounting_entry_date()}</label>
<input id="entry_date" name="entry_date" type="date" class="input" value={hoy} required />
	{#if form?.errors?.entry_date}
		<p class="mt-1 text-xs text-[var(--negative)]">{form?.errors?.entry_date}</p>
	{/if}
</div>
			<div>
	<label class="label" for="kind">{m.accounting_entry_kind_manual()}</label>
<select id="kind" name="kind" class="input">
					<option value="manual">{m.accounting_entry_kind_manual()}</option>
					<option value="adjustment">{m.accounting_entry_kind_adjustment()}</option>
				</select>
</div>
		</div>

		<div>
	<label class="label" for="description">{m.accounting_entry_description()}</label>
<input id="description" name="description" type="text" class="input" maxlength="255" required />
	{#if form?.errors?.description}
		<p class="mt-1 text-xs text-[var(--negative)]">{form?.errors?.description}</p>
	{/if}
</div>

		<div class="overflow-x-auto">
			<table class="w-full min-w-[28rem] text-sm">
				<thead>
					<tr class="text-left text-xs text-[var(--text-subtle)] uppercase">
						<th class="py-1 font-semibold">{m.accounting_account_name()}</th>
						<th class="py-1 text-right font-semibold">{m.accounting_entry_debit()}</th>
						<th class="py-1 text-right font-semibold">{m.accounting_entry_credit()}</th>
					</tr>
				</thead>
				<tbody>
					{#each filas as fila, i (i)}
						<tr>
							<td class="py-1 pr-2">
								<select name="line_account" bind:value={fila.account} class="input">
									<option value=""></option>
									{#each data.cuentas as cuenta (cuenta.id)}
										<option value={cuenta.id}>{cuenta.code} · {cuenta.name}</option>
									{/each}
								</select>
							</td>
							<td class="py-1 pr-2">
								<input
									name="line_debit"
									type="number"
									step="0.01"
									min="0"
									class="input text-right"
									bind:value={fila.debit}
								/>
							</td>
							<td class="py-1">
								<input
									name="line_credit"
									type="number"
									step="0.01"
									min="0"
									class="input text-right"
									bind:value={fila.credit}
								/>
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>

		<p class="text-xs {diferencia === 0 ? 'text-[var(--text-subtle)]' : 'text-[var(--danger)]'}">
			{diferencia === 0
				? m.accounting_entry_balance_hint()
				: m.accounting_entry_out_of_balance({ amount: formatMoney(Math.abs(diferencia)) })}
		</p>

		<div class="flex justify-end gap-2">
			<button type="button" class="btn btn-ghost" onclick={() => (creando = false)}>
				{m.common_cancel()}
			</button>
			<button type="submit" class="btn btn-primary" disabled={diferencia !== 0}>
				{m.common_save()}
			</button>
		</div>
	</form>
</Modal>

<Modal
	open={reclasificando}
	title={m.accounting_reclassify_title()}
	onclose={() => (reclasificando = false)}
>
	{#if data.detalle}
		<form
			method="POST"
			action="?/reclasificar"
			use:enhance={submit({ onSuccess: () => (reclasificando = false) })}
			class="grid gap-3"
		>
			<input type="hidden" name="entry_id" value={data.detalle.id} />
			<p class="text-xs text-[var(--text-subtle)]">{m.accounting_reclassify_hint()}</p>

			<div>
	<label class="label" for="account_id">{m.accounting_reclassify_account()}</label>
<select id="account_id" name="account_id" class="input" required>
					{#each data.cuentas.filter((c) => c.code !== POR_CLASIFICAR) as cuenta (cuenta.id)}
						<option value={cuenta.id}>{cuenta.code} · {cuenta.name}</option>
					{/each}
				</select>
</div>

			<div>
	<label class="label" for="description">{m.accounting_entry_description()}</label>
<input id="description" name="description" type="text" class="input" maxlength="255" />
</div>

			<div class="flex justify-end gap-2">
				<button type="button" class="btn btn-ghost" onclick={() => (reclasificando = false)}>
					{m.common_cancel()}
				</button>
				<button type="submit" class="btn btn-primary">{m.accounting_reclassify()}</button>
			</div>
		</form>
	{/if}
</Modal>
