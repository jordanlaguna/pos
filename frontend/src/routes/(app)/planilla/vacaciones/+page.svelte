<script lang="ts">
	import { goto } from '$app/navigation';
	import { employeeName } from '$lib/domain/payroll';
	import { formatDate } from '$lib/ui/format';
	import { m } from '$lib/paraglide/messages.js';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	const elegido = $derived(data.employees.find((e) => e.id === data.empleado) ?? null);
</script>

<svelte:head>
	<title>{m.payroll_vacations_title()}</title>
</svelte:head>

<p class="mb-3 text-sm text-[var(--text-muted)]">{m.payroll_vacations_description()}</p>

<div class="mb-4 flex flex-wrap items-center gap-3">
	<select
		class="input w-auto"
		aria-label={m.payroll_actions_f_employee()}
		value={data.empleado ?? ''}
		onchange={(ev) => goto(`/planilla/vacaciones?empleado=${(ev.currentTarget as HTMLSelectElement).value}`)}
	>
		<option value="">{m.payroll_vacations_choose()}</option>
		{#each data.employees as e (e.id)}
			<option value={e.id}>{employeeName(e)}</option>
		{/each}
	</select>
	{#if elegido}
		<a href="/planilla/acciones?empleado={elegido.id}" class="btn btn-ghost">{m.payroll_vacations_register()}</a>
	{/if}
</div>

{#if elegido && data.vacations}
	<div class="card p-4" data-vacaciones>
		<p class="mb-3 text-lg font-bold tabular-nums text-[var(--text)]" data-saldo>
			{m.payroll_vacations_balance({ name: employeeName(elegido), days: data.vacations.balance })}
		</p>
		{#if data.vacations.movements.length === 0}
			<p class="text-sm text-[var(--text-muted)]">{m.payroll_vacations_empty()}</p>
		{:else}
			<div class="table-wrap">
				<table class="data-table">
					<thead>
						<tr>
							<th scope="col">{m.payroll_vacations_col_date()}</th>
							<th scope="col">{m.payroll_vacations_col_kind()}</th>
							<th scope="col" class="num">{m.payroll_vacations_col_days()}</th>
							<th scope="col">{m.payroll_vacations_col_origin()}</th>
						</tr>
					</thead>
					<tbody>
						{#each data.vacations.movements as mov (mov.id)}
							<tr>
								<td>{formatDate(mov.on_date)}</td>
								<td>{m.payroll_vacation_kind({ kind: mov.kind })}</td>
								<td class="num tabular-nums">{mov.days}</td>
								<td class="text-xs text-[var(--text-muted)]">
									{#if mov.run_id}
										<a href="/planilla/corridas/{mov.run_id}" class="text-[var(--accent)] hover:underline">{m.payroll_vacations_origin_run({ id: mov.run_id })}</a>
									{:else if mov.action_id}
										{m.payroll_vacations_origin_action({ id: mov.action_id })}
									{/if}
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		{/if}
	</div>
{/if}
