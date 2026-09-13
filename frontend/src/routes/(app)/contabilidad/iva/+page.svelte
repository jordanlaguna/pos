<script lang="ts">
	import EmptyState from '$lib/ui/components/EmptyState.svelte';
	import { formatMoney } from '$lib/domain/money';
	import { m } from '$lib/paraglide/messages.js';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	/** La tarifa viene entre 0 y 1; en pantalla se lee en porcentaje. */
	function porcentaje(tarifa: number): string {
		return `${Math.round(tarifa * 10000) / 100} %`;
	}
</script>

<div class="mb-3">
	<h2 class="text-sm font-semibold">{m.accounting_vat_title()}</h2>
	<p class="mt-1 max-w-3xl text-xs text-[var(--text-subtle)]">
		{m.accounting_vat_description()}
	</p>
</div>

<form method="GET" class="mb-3 flex flex-wrap items-end gap-2">
	<label class="text-xs text-[var(--text-subtle)]">
		{m.accounting_report_year()}
		<input name="year" type="number" class="input mt-1 w-24" value={data.year} />
	</label>
	<label class="text-xs text-[var(--text-subtle)]">
		{m.accounting_report_month()}
		<select name="month" class="input mt-1 w-32" value={data.month}>
			{#each [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12] as mes (mes)}
				<option value={mes}>{mes}</option>
			{/each}
		</select>
	</label>
	<button type="submit" class="btn btn-ghost">{m.accounting_filter()}</button>
</form>

{#if !data.borrador || !data.borrador.lines.length}
	<EmptyState icon="book" title={m.accounting_vat_empty()} />
{:else}
	<div class="mb-4 grid gap-3 sm:grid-cols-3">
		<div class="card p-3">
			<p class="text-xs font-semibold tracking-wide text-[var(--text-subtle)] uppercase">
				{m.accounting_vat_debit()}
			</p>
			<p class="mt-1 text-lg font-semibold tabular-nums">{formatMoney(data.borrador.debit)}</p>
			<p class="text-xs text-[var(--text-subtle)]">{m.accounting_vat_net_hint()}</p>
		</div>
		<div class="card p-3">
			<p class="text-xs font-semibold tracking-wide text-[var(--text-subtle)] uppercase">
				{m.accounting_vat_credit()}
			</p>
			<p class="mt-1 text-lg font-semibold tabular-nums">{formatMoney(data.borrador.credit)}</p>
		</div>
		<div class="card p-3">
			<p class="text-xs font-semibold tracking-wide text-[var(--text-subtle)] uppercase">
				{data.borrador.in_favor ? m.accounting_vat_in_favor() : m.accounting_vat_to_pay()}
			</p>
			<p
				class="mt-1 text-lg font-semibold tabular-nums {data.borrador.in_favor
					? 'text-[var(--success)]'
					: ''}"
			>
				{formatMoney(Math.abs(data.borrador.balance))}
			</p>
		</div>
	</div>

	<div class="card overflow-x-auto">
		<table class="w-full min-w-[40rem] text-sm">
			<thead>
				<tr
					class="border-b border-[var(--border)] text-left text-xs text-[var(--text-subtle)] uppercase"
				>
					<th class="px-3 py-2 font-semibold">{m.accounting_vat_rate()}</th>
					<th class="px-3 py-2 text-right font-semibold">{m.accounting_vat_sales_base()}</th>
					<th class="px-3 py-2 text-right font-semibold">{m.accounting_vat_debit()}</th>
					<th class="px-3 py-2 text-right font-semibold">{m.accounting_vat_returns()}</th>
					<th class="px-3 py-2 text-right font-semibold">{m.accounting_vat_purchases_base()}</th>
					<th class="px-3 py-2 text-right font-semibold">{m.accounting_vat_credit()}</th>
				</tr>
			</thead>
			<tbody class="divide-y divide-[var(--border)]">
				{#each data.borrador.lines as fila (fila.tax_rate)}
					<tr>
						<td class="px-3 py-2">{porcentaje(fila.tax_rate)}</td>
						<td class="px-3 py-2 text-right tabular-nums">{formatMoney(fila.sales_base)}</td>
						<td class="px-3 py-2 text-right tabular-nums">{formatMoney(fila.debit)}</td>
						<td class="px-3 py-2 text-right tabular-nums">{formatMoney(fila.returns_tax)}</td>
						<td class="px-3 py-2 text-right tabular-nums">{formatMoney(fila.purchases_base)}</td>
						<td class="px-3 py-2 text-right tabular-nums">{formatMoney(fila.credit)}</td>
					</tr>
				{/each}
			</tbody>
			<tfoot>
				<tr class="border-t border-[var(--border)] font-semibold">
					<td class="px-3 py-2" colspan="2">{m.accounting_entry_total()}</td>
					<td class="px-3 py-2 text-right tabular-nums">{formatMoney(data.borrador.debit)}</td>
					<td class="px-3 py-2"></td>
					<td class="px-3 py-2"></td>
					<td class="px-3 py-2 text-right tabular-nums">{formatMoney(data.borrador.credit)}</td>
				</tr>
			</tfoot>
		</table>
	</div>
{/if}
