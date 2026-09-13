<script lang="ts">
	import EmptyState from '$lib/ui/components/EmptyState.svelte';
	import Icon from '$lib/ui/components/Icon.svelte';
	import { formatMoney } from '$lib/domain/money';
	import { formatDate } from '$lib/ui/format';
	import { m } from '$lib/paraglide/messages.js';
	import { entryTitle, kindLabel } from '$lib/ui/accounting';
	import type {
		BalanceSheet,
		IncomeStatement,
		Journal,
		LedgerReport,
		TrialBalance
	} from '$lib/domain/types';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	const opciones = $derived([
		{ id: 'trial-balance', label: m.accounting_report_trial_balance() },
		{ id: 'income', label: m.accounting_report_income() },
		{ id: 'balance', label: m.accounting_report_balance() },
		{ id: 'journal', label: m.accounting_report_journal() },
		{ id: 'ledger', label: m.accounting_report_ledger() }
	]);

	const consulta = $derived(
		`report=${data.reporte}&year=${data.year}${data.month ? `&month=${data.month}` : ''}`
	);

	// Los cinco vienen del mismo `load`, así que el tipo se afina acá para que el
	// marcado no tenga que preguntarlo campo por campo.
	const comprobacion = $derived(
		data.reporte === 'trial-balance' ? (data.datos as TrialBalance | null) : null
	);
	const resultados = $derived(
		data.reporte === 'income' ? (data.datos as IncomeStatement | null) : null
	);
	const general = $derived(
		data.reporte === 'balance' ? (data.datos as BalanceSheet | null) : null
	);
	const diario = $derived(data.reporte === 'journal' ? (data.datos as Journal | null) : null);
	const mayor = $derived(data.reporte === 'ledger' ? (data.datos as LedgerReport | null) : null);
</script>

<div class="mb-3 flex flex-wrap items-end justify-between gap-3">
	<form method="GET" class="flex flex-wrap items-end gap-2">
		<label class="text-xs text-[var(--text-subtle)]">
			{m.accounting_tab_reports()}
			<select name="report" class="input mt-1" value={data.reporte}>
				{#each opciones as opcion (opcion.id)}
					<option value={opcion.id}>{opcion.label}</option>
				{/each}
			</select>
		</label>
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

	<a href="/contabilidad/reportes/reporte.csv?{consulta}" class="btn btn-ghost" download>
		<Icon name="download" size={15} />
		{m.accounting_report_download()}
	</a>
</div>

{#if !data.datos}
	<EmptyState icon="book" title={m.accounting_report_empty()} />
{:else if comprobacion}
	<p class="mb-2 text-xs {comprobacion.is_balanced ? 'text-[var(--text-subtle)]' : 'text-[var(--danger)]'}">
		{comprobacion.is_balanced
			? m.accounting_report_balanced({ debits: formatMoney(comprobacion.debits) })
			: m.accounting_report_not_balanced({
					debits: formatMoney(comprobacion.debits),
					credits: formatMoney(comprobacion.credits)
				})}
	</p>
	<div class="card overflow-x-auto">
		<table class="w-full min-w-[34rem] text-sm">
			<thead>
				<tr class="border-b border-[var(--border)] text-left text-xs text-[var(--text-subtle)] uppercase">
					<th class="px-3 py-2 font-semibold">{m.accounting_account_code()}</th>
					<th class="px-3 py-2 font-semibold">{m.accounting_account_name()}</th>
					<th class="px-3 py-2 text-right font-semibold">{m.accounting_entry_debit()}</th>
					<th class="px-3 py-2 text-right font-semibold">{m.accounting_entry_credit()}</th>
				</tr>
			</thead>
			<tbody class="divide-y divide-[var(--border)]">
				{#each comprobacion.rows as fila (fila.account_id)}
					<tr>
						<td class="px-3 py-2 font-mono text-xs">{fila.code}</td>
						<td class="px-3 py-2">{fila.name}</td>
						<td class="px-3 py-2 text-right tabular-nums">{formatMoney(fila.debits)}</td>
						<td class="px-3 py-2 text-right tabular-nums">{formatMoney(fila.credits)}</td>
					</tr>
				{/each}
			</tbody>
			<tfoot>
				<tr class="border-t border-[var(--border)] font-semibold">
					<td class="px-3 py-2" colspan="2">{m.accounting_entry_total()}</td>
					<td class="px-3 py-2 text-right tabular-nums">{formatMoney(comprobacion.debits)}</td>
					<td class="px-3 py-2 text-right tabular-nums">{formatMoney(comprobacion.credits)}</td>
				</tr>
			</tfoot>
		</table>
	</div>
{:else if resultados}
	<div class="mb-4 grid gap-3 sm:grid-cols-4">
		{#each [{ label: m.accounting_income(), value: resultados.income }, { label: m.accounting_cost(), value: resultados.cost }, { label: m.accounting_gross_profit(), value: resultados.gross_profit }, { label: m.accounting_result(), value: resultados.result }] as cifra (cifra.label)}
			<div class="card p-3">
				<p class="text-xs font-semibold tracking-wide text-[var(--text-subtle)] uppercase">
					{cifra.label}
				</p>
				<p class="mt-1 text-lg font-semibold tabular-nums">{formatMoney(cifra.value)}</p>
			</div>
		{/each}
	</div>
	<div class="card overflow-x-auto">
		<table class="w-full min-w-[30rem] text-sm">
			<tbody class="divide-y divide-[var(--border)]">
				{#each resultados.rows as fila (fila.account_id)}
					<tr>
						<td class="px-3 py-2 font-mono text-xs">{fila.code}</td>
						<td class="px-3 py-2">{fila.name}</td>
						<td class="px-3 py-2 text-[var(--text-subtle)]">{kindLabel(fila.kind)}</td>
						<td class="px-3 py-2 text-right tabular-nums">{formatMoney(fila.balance)}</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
{:else if general}
	<p class="mb-2 text-xs {general.is_balanced ? 'text-[var(--text-subtle)]' : 'text-[var(--danger)]'}">
		{general.is_balanced ? m.accounting_equation_ok() : m.accounting_equation_broken()}
	</p>
	<div class="mb-4 grid gap-3 sm:grid-cols-4">
		{#each [{ label: m.accounting_assets(), value: general.assets }, { label: m.accounting_liabilities(), value: general.liabilities }, { label: m.accounting_equity(), value: general.equity }, { label: m.accounting_result(), value: general.result }] as cifra (cifra.label)}
			<div class="card p-3">
				<p class="text-xs font-semibold tracking-wide text-[var(--text-subtle)] uppercase">
					{cifra.label}
				</p>
				<p class="mt-1 text-lg font-semibold tabular-nums">{formatMoney(cifra.value)}</p>
			</div>
		{/each}
	</div>
	<div class="card overflow-x-auto">
		<table class="w-full min-w-[30rem] text-sm">
			<tbody class="divide-y divide-[var(--border)]">
				{#each general.rows as fila (fila.account_id)}
					<tr>
						<td class="px-3 py-2 font-mono text-xs">{fila.code}</td>
						<td class="px-3 py-2">{fila.name}</td>
						<td class="px-3 py-2 text-[var(--text-subtle)]">{kindLabel(fila.kind)}</td>
						<td class="px-3 py-2 text-right tabular-nums">{formatMoney(fila.balance)}</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
{:else if diario}
	{#if !diario.entries.length}
		<EmptyState icon="book" title={m.accounting_report_empty()} />
	{:else}
		<div class="grid gap-3">
			{#each diario.entries as asiento (asiento.id)}
				<div class="card p-3">
					<p class="text-sm font-medium">
						#{asiento.entry_number} · {formatDate(asiento.entry_date)} · {entryTitle(asiento)}
					</p>
					<table class="mt-2 w-full text-sm">
						<tbody>
							{#each asiento.lines ?? [] as linea (linea.account_id + '-' + linea.debit + '-' + linea.credit + '-' + (linea.memo ?? ''))}
								<tr>
									<td class="py-1">
										<span class="font-mono text-xs">{linea.account_code}</span>
										{linea.account_name}
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
					</table>
				</div>
			{/each}
		</div>
	{/if}
{:else if mayor}
	{#if !mayor.accounts.length}
		<EmptyState icon="book" title={m.accounting_report_empty()} />
	{:else}
		<div class="grid gap-3">
			{#each mayor.accounts as cuenta (cuenta.account_id)}
				<div class="card p-3">
					<div class="flex flex-wrap items-baseline justify-between gap-2">
						<p class="text-sm font-medium">
							<span class="font-mono text-xs">{cuenta.code}</span>
							{cuenta.name}
						</p>
						<p class="text-xs text-[var(--text-subtle)]">
							{m.accounting_ledger_opening()}: {formatMoney(cuenta.opening)} ·
							{m.accounting_ledger_closing()}: {formatMoney(cuenta.closing)}
						</p>
					</div>
					<table class="mt-2 w-full text-sm">
						<tbody>
							{#each cuenta.movements as movimiento (movimiento.entry_id + '-' + movimiento.debit + '-' + movimiento.credit)}
								<tr>
									<td class="py-1 whitespace-nowrap">{formatDate(movimiento.entry_date)}</td>
									<td class="py-1">#{movimiento.entry_number}</td>
									<td class="py-1 text-right tabular-nums">
										{movimiento.debit ? formatMoney(movimiento.debit) : ''}
									</td>
									<td class="py-1 text-right tabular-nums">
										{movimiento.credit ? formatMoney(movimiento.credit) : ''}
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			{/each}
		</div>
	{/if}
{/if}
