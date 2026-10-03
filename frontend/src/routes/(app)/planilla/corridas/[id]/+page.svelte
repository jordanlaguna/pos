<script lang="ts">
	import { enhance } from '$app/forms';
	import { submit } from '$lib/ui/forms';
	import Icon from '$lib/ui/components/Icon.svelte';
	import { formatMoney } from '$lib/domain/money';
	import { itemsByPayer, type PayrollItem } from '$lib/domain/payroll';
	import { formatDate } from '$lib/ui/format';
	import { m } from '$lib/paraglide/messages.js';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	const r = $derived(data.run);
	let abierta = $state<number | null>(null);
	let ocupado = $state(false);

	function cantidad(i: PayrollItem): string {
		if (i.quantity == null) return '';
		return i.concept === 'overtime' || i.concept === 'double_time'
			? m.payroll_hours_short({ hours: i.quantity })
			: m.payroll_days_short({ days: i.quantity });
	}

	function fechas(i: PayrollItem): string {
		if (!i.applied_from) return '';
		return i.applied_to && i.applied_to !== i.applied_from
			? m.payroll_period_range({ from: formatDate(i.applied_from), to: formatDate(i.applied_to) })
			: formatDate(i.applied_from);
	}

	function tasa(i: PayrollItem): string {
		return i.rate == null ? '' : m.payroll_percent({ value: Math.round(i.rate * 10000) / 100 });
	}

	const totales = $derived({
		gross: r.lines.reduce((t, l) => t + l.gross, 0),
		ccss: r.lines.reduce((t, l) => t + l.employee_deductions, 0),
		tax: r.lines.reduce((t, l) => t + l.income_tax, 0),
		other: r.lines.reduce((t, l) => t + l.other_deductions, 0),
		net: r.lines.reduce((t, l) => t + l.net, 0),
		employer: r.lines.reduce((t, l) => t + l.employer_charges, 0)
	});
</script>

<svelte:head>
	<title>{m.payroll_run_title({ id: r.id })}</title>
</svelte:head>

<div class="mb-4 flex flex-wrap items-start justify-between gap-3">
	<div>
		<a href="/planilla/corridas" class="inline-flex items-center gap-1.5 text-sm text-[var(--text-muted)] hover:text-[var(--text)]">
			<Icon name="back" size={15} />
			{m.payroll_run_back()}
		</a>
		<h2 class="mt-1 text-lg font-bold text-[var(--text)]" data-titulo-corrida>
			{m.payroll_run_kind({ kind: r.kind })} · {m.payroll_period_range({ from: formatDate(r.period_from), to: formatDate(r.period_to) })}
		</h2>
		<p class="text-sm text-[var(--text-muted)]">
			{#if r.schedule_name}{r.schedule_name} · {/if}
			{m.payroll_run_pay_date({ date: formatDate(r.pay_date) })}
			· <span class="font-semibold" data-estado-corrida>{m.payroll_run_status({ status: r.status })}</span>
			{#if r.adjusts_run_id}
				· <a href="/planilla/corridas/{r.adjusts_run_id}" class="text-[var(--accent)] hover:underline">{m.payroll_run_adjusts({ run: r.adjusts_run_id })}</a>
			{/if}
			{#if r.journal_entry_id}
				· <a href="/contabilidad/asientos" class="text-[var(--accent)] hover:underline">{m.payroll_run_journal({ id: r.journal_entry_id })}</a>
			{/if}
		</p>
		<p class="mt-1 text-xs text-[var(--text-subtle)]">
			{#if r.status === 'draft'}{m.payroll_run_draft_hint()}{:else if r.status === 'approved'}{m.payroll_run_approved_hint()}{:else}{m.payroll_run_paid_hint({ date: formatDate(r.paid_at) })}{/if}
		</p>
	</div>

	<div class="flex flex-wrap gap-2" data-acciones-corrida>
		{#if r.status === 'draft'}
			<form method="POST" action="?/calcular" use:enhance={submit({ setBusy: (b) => (ocupado = b) })}>
				<button type="submit" class="btn btn-primary" disabled={!data.payrollEnabled || ocupado}>
					<Icon name="refresh" size={15} />
					{r.lines.length ? m.payroll_run_recalculate() : m.payroll_run_calculate()}
				</button>
			</form>
			{#if r.lines.length}
				<form method="POST" action="?/aprobar" use:enhance={submit({ setBusy: (b) => (ocupado = b) })}>
					<button type="submit" class="btn btn-ghost" disabled={!data.payrollEnabled || ocupado}>
						<Icon name="check" size={15} />
						{m.payroll_run_approve()}
					</button>
				</form>
			{/if}
		{:else if r.status === 'approved'}
			<form method="POST" action="?/pagar" use:enhance={submit({ setBusy: (b) => (ocupado = b) })}>
				<button type="submit" class="btn btn-primary" disabled={!data.payrollEnabled || ocupado}>
					<Icon name="wallet" size={15} />
					{m.payroll_run_pay()}
				</button>
			</form>
		{:else if r.kind === 'regular'}
			<form method="POST" action="?/ajustar" use:enhance={submit({ setBusy: (b) => (ocupado = b) })}>
				<button type="submit" class="btn btn-ghost" disabled={!data.payrollEnabled || ocupado}>
					<Icon name="edit" size={15} />
					{m.payroll_run_adjust()}
				</button>
			</form>
		{/if}
	</div>
</div>

{#if r.lines.length === 0}
	<div class="card p-6 text-center text-sm text-[var(--text-muted)]">{m.payroll_run_no_lines()}</div>
{:else}
	<div class="card overflow-hidden">
		<div class="table-wrap">
			<table class="data-table" data-lineas>
				<thead>
					<tr>
						<th scope="col">{m.payroll_run_col_employee()}</th>
						<th scope="col" class="num">{m.payroll_run_col_gross()}</th>
						<th scope="col" class="num">{m.payroll_run_col_ccss()}</th>
						<th scope="col" class="num">{m.payroll_run_col_tax()}</th>
						<th scope="col" class="num">{m.payroll_run_col_other()}</th>
						<th scope="col" class="num">{m.payroll_run_col_net()}</th>
						<th scope="col" class="num">{m.payroll_run_col_employer()}</th>
						<th scope="col"><span class="sr-only">{m.payroll_run_items()}</span></th>
					</tr>
				</thead>
				<tbody>
					{#each r.lines as l (l.id)}
						<tr>
							<td class="font-medium text-[var(--text)]">{l.employee_name}</td>
							<td class="num tabular-nums">{formatMoney(l.gross)}</td>
							<td class="num tabular-nums">{formatMoney(l.employee_deductions)}</td>
							<td class="num tabular-nums">{formatMoney(l.income_tax)}</td>
							<td class="num tabular-nums">{formatMoney(l.other_deductions)}</td>
							<td class="num font-semibold tabular-nums" data-neto>{formatMoney(l.net)}</td>
							<td class="num tabular-nums">{formatMoney(l.employer_charges)}</td>
							<td class="text-right whitespace-nowrap">
								<button type="button" class="btn btn-ghost py-1 text-xs" onclick={() => (abierta = abierta === l.id ? null : l.id)}>
									<Icon name={abierta === l.id ? 'up' : 'down'} size={13} />
									{m.payroll_run_items()}
								</button>
								<a href="/planilla/corridas/{r.id}/boleta/{l.employee_id}" class="btn btn-ghost py-1 text-xs">
									<Icon name="printer" size={13} />
									{m.payroll_run_payslip()}
								</a>
							</td>
						</tr>
						{#if abierta === l.id}
							{@const grupos = itemsByPayer(l.items)}
							<tr>
								<td colspan="8" class="bg-[var(--surface-sunken)]">
									<table class="data-table text-xs">
										<thead>
											<tr>
												<th scope="col">{m.payroll_run_item_col_concept()}</th>
												<th scope="col" class="num">{m.payroll_run_item_col_base()}</th>
												<th scope="col" class="num">{m.payroll_run_item_col_rate()}</th>
												<th scope="col" class="num">{m.payroll_run_item_col_quantity()}</th>
												<th scope="col">{m.payroll_run_item_col_dates()}</th>
												<th scope="col" class="num">{m.payroll_run_item_col_amount()}</th>
											</tr>
										</thead>
										<tbody>
											{#each [...grupos.earnings, ...grupos.deductions, ...grupos.employer] as i, n (n)}
												<tr>
													<td>
														{m.payroll_concept({ concept: i.concept })}
														<span class="ml-1 text-[var(--text-subtle)]">· {m.payroll_payer({ payer: i.payer })}</span>
													</td>
													<td class="num tabular-nums">{formatMoney(i.base)}</td>
													<td class="num tabular-nums">{tasa(i)}</td>
													<td class="num tabular-nums">{cantidad(i)}</td>
													<td>{fechas(i)}</td>
													<td class="num tabular-nums">{formatMoney(i.amount)}</td>
												</tr>
											{/each}
										</tbody>
									</table>
								</td>
							</tr>
						{/if}
					{/each}
				</tbody>
				<tfoot>
					<tr class="font-semibold">
						<td>{m.payroll_run_totals()}</td>
						<td class="num tabular-nums">{formatMoney(totales.gross)}</td>
						<td class="num tabular-nums">{formatMoney(totales.ccss)}</td>
						<td class="num tabular-nums">{formatMoney(totales.tax)}</td>
						<td class="num tabular-nums">{formatMoney(totales.other)}</td>
						<td class="num tabular-nums">{formatMoney(totales.net)}</td>
						<td class="num tabular-nums">{formatMoney(totales.employer)}</td>
						<td></td>
					</tr>
				</tfoot>
			</table>
		</div>
	</div>

	{#if r.status === 'paid' && r.kind !== 'adjustment'}
		<section class="card mt-4 p-4" data-ibans>
			<h3 class="font-semibold text-[var(--text)]">{m.payroll_run_ibans_title()}</h3>
			<p class="mb-2 text-xs text-[var(--text-muted)]">{m.payroll_run_ibans_hint()}</p>
			<ul class="divide-y divide-[var(--border)] text-sm">
				{#each r.lines as l (l.id)}
					<li class="flex items-center justify-between gap-3 py-1.5">
						<span>{l.employee_name}</span>
						<span class="font-mono text-xs text-[var(--text-muted)]">{data.ibans[l.employee_id] ?? m.payroll_run_no_iban()}</span>
						<span class="tabular-nums">{formatMoney(l.net)}</span>
					</li>
				{/each}
			</ul>
		</section>
	{/if}
{/if}
