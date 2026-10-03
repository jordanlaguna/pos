<script lang="ts">
	import { enhance } from '$app/forms';
	import { submit } from '$lib/ui/forms';
	import Icon from '$lib/ui/components/Icon.svelte';
	import Modal from '$lib/ui/components/Modal.svelte';
	import Field from '$lib/ui/components/Field.svelte';
	import EmptyState from '$lib/ui/components/EmptyState.svelte';
	import { formatMoney } from '$lib/domain/money';
	import { formatDate } from '$lib/ui/format';
	import { m } from '$lib/paraglide/messages.js';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	let creando = $state(false);
	let aguinaldo = $state(false);
	const anio = new Date().getFullYear();

	function estado(status: string): string {
		return status === 'paid'
			? 'bg-[var(--positive-bg)] text-[var(--positive)]'
			: status === 'approved'
				? 'bg-[var(--warning-bg)] text-[var(--warning)]'
				: 'bg-[var(--surface-sunken)] text-[var(--text-muted)]';
	}
</script>

<svelte:head>
	<title>{m.payroll_runs_title()}</title>
</svelte:head>

<div class="mb-3 flex flex-wrap items-center justify-between gap-3">
	<p class="text-sm text-[var(--text-muted)]">{m.payroll_runs_description()}</p>
	<div class="flex gap-2">
		<button type="button" class="btn btn-ghost" onclick={() => (aguinaldo = true)} disabled={!data.payrollEnabled}>
			<Icon name="calendar" size={15} />
			{m.payroll_runs_new_aguinaldo()}
		</button>
		<button type="button" class="btn btn-primary" onclick={() => (creando = true)} disabled={!data.payrollEnabled || data.schedules.length === 0}>
			<Icon name="plus" size={15} />
			{m.payroll_runs_new()}
		</button>
	</div>
</div>

<div class="card overflow-hidden">
	<div class="table-wrap">
		<table class="data-table">
			<thead>
				<tr>
					<th scope="col">{m.payroll_runs_col_period()}</th>
					<th scope="col">{m.payroll_runs_col_kind()}</th>
					<th scope="col">{m.payroll_runs_col_status()}</th>
					<th scope="col" class="num">{m.payroll_runs_col_employees()}</th>
					<th scope="col" class="num">{m.payroll_runs_col_gross()}</th>
					<th scope="col" class="num">{m.payroll_runs_col_net()}</th>
					<th scope="col" class="num">{m.payroll_runs_col_employer()}</th>
				</tr>
			</thead>
			<tbody>
				{#each data.runs as r (r.id)}
					<tr>
						<td>
							<a href="/planilla/corridas/{r.id}" class="font-medium text-[var(--accent)] hover:underline">
								{m.payroll_period_range({ from: formatDate(r.period_from), to: formatDate(r.period_to) })}
							</a>
							<span class="block text-xs text-[var(--text-subtle)]">{r.schedule_name ?? ''} · {m.payroll_run_pay_date({ date: formatDate(r.pay_date) })}</span>
						</td>
						<td>
							{m.payroll_run_kind({ kind: r.kind })}
							{#if r.adjusts_run_id}<span class="block text-xs text-[var(--text-subtle)]">{m.payroll_run_adjusts({ run: r.adjusts_run_id })}</span>{/if}
						</td>
						<td><span class="badge {estado(r.status)}">{m.payroll_run_status({ status: r.status })}</span></td>
						<td class="num tabular-nums">{r.employees}</td>
						<td class="num tabular-nums">{formatMoney(r.gross)}</td>
						<td class="num tabular-nums">{formatMoney(r.net)}</td>
						<td class="num tabular-nums">{formatMoney(r.employer_charges)}</td>
					</tr>
				{:else}
					<tr>
						<td colspan="7">
							<EmptyState icon="calendar" title={m.payroll_runs_empty()} description={m.payroll_runs_description()} />
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
</div>

<Modal open={creando} title={m.payroll_runs_new()} onclose={() => (creando = false)}>
	<form id="form-corrida" method="POST" action="?/crear" use:enhance={submit({ onRedirect: () => (creando = false) })} class="grid gap-4">
		<div>
			<label class="label" for="corrida-jornada">{m.payroll_runs_f_schedule()}</label>
			<select id="corrida-jornada" name="schedule_id" class="input" required>
				{#each data.schedules as s (s.id)}
					<option value={s.id}>{s.name} · {m.payroll_frequency({ frequency: s.frequency })}</option>
				{/each}
			</select>
		</div>
		<Field label={m.payroll_runs_f_cut_date()} name="cut_date" type="date" required hint={m.payroll_runs_f_cut_hint()} />
		<Field label={m.payroll_runs_f_pay_date()} name="pay_date" type="date" />
	</form>
	{#snippet footer()}
		<button type="button" class="btn btn-ghost" onclick={() => (creando = false)}>{m.payroll_cancel()}</button>
		<button type="submit" form="form-corrida" class="btn btn-primary">{m.payroll_runs_new()}</button>
	{/snippet}
</Modal>

<Modal open={aguinaldo} title={m.payroll_runs_new_aguinaldo()} description={m.payroll_runs_aguinaldo_hint()} onclose={() => (aguinaldo = false)}>
	<form id="form-aguinaldo" method="POST" action="?/aguinaldo" use:enhance={submit({ onRedirect: () => (aguinaldo = false) })} class="grid gap-4">
		<Field label={m.payroll_runs_f_year()} name="year" value={String(anio)} inputmode="numeric" required />
		<Field label={m.payroll_runs_f_pay_date()} name="pay_date" type="date" />
	</form>
	{#snippet footer()}
		<button type="button" class="btn btn-ghost" onclick={() => (aguinaldo = false)}>{m.payroll_cancel()}</button>
		<button type="submit" form="form-aguinaldo" class="btn btn-primary">{m.payroll_runs_new_aguinaldo()}</button>
	{/snippet}
</Modal>
