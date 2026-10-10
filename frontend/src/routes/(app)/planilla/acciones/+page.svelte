<script lang="ts">
	import { enhance } from '$app/forms';
	import { goto } from '$app/navigation';
	import { submit } from '$lib/ui/forms';
	import Modal from '$lib/ui/components/Modal.svelte';
	import Field from '$lib/ui/components/Field.svelte';
	import { formatMoney } from '$lib/domain/money';
	import {
		REGISTRABLE_KINDS,
		actionFields,
		employeeName,
		type PersonnelAction
	} from '$lib/domain/payroll';
	import { formatDate } from '$lib/ui/format';
	import { m } from '$lib/paraglide/messages.js';
	import type { PageData } from './$types';
	import Select from '$lib/ui/components/Select.svelte';

	let { data }: { data: PageData } = $props();

	let kind = $state('overtime');
	const campos = $derived(actionFields(kind));
	// svelte-ignore state_referenced_locally
	let seleccionados = $state<number[]>(data.empleado ? [data.empleado] : []);
	let anulando = $state<PersonnelAction | null>(null);
	let suspendiendo = $state<PersonnelAction | null>(null);

	const elegido = $derived(data.employees.find((e) => e.id === data.empleado) ?? null);

	function detalle(a: PersonnelAction): string {
		const partes: string[] = [];
		if (a.hours != null) partes.push(m.payroll_hours_short({ hours: a.hours }));
		if (a.days != null) partes.push(m.payroll_days_short({ days: a.days }));
		if (a.amount != null) partes.push(formatMoney(a.amount));
		if (a.new_salary != null) partes.push(formatMoney(a.new_salary));
		return partes.join(' ');
	}

	function fechas(a: PersonnelAction): string {
		return a.ends_on && a.ends_on !== a.starts_on
			? m.payroll_period_range({ from: formatDate(a.starts_on), to: formatDate(a.ends_on) })
			: formatDate(a.starts_on);
	}

	const puedeSuspender = (a: PersonnelAction) =>
		(a.kind === 'deduction' || a.kind === 'child_support') && a.is_recurring && !a.suspended_at && !a.cancelled_by;
	const puedeAnular = (a: PersonnelAction) =>
		!a.cancels_action_id && !a.cancelled_by && !['raise', 'position_change', 'termination'].includes(a.kind);
</script>

<svelte:head>
	<title>{m.payroll_actions_title()}</title>
</svelte:head>

<p class="mb-4 text-sm text-[var(--text-muted)]">{m.payroll_actions_description()}</p>

<div class="grid gap-4 lg:grid-cols-5">
	<section class="card p-4 lg:col-span-2" data-form-accion>
		<form method="POST" action="?/registrar" use:enhance={submit({ reset: false })} class="grid gap-4">
			<div>
				<label class="label" for="accion-empleados">{m.payroll_actions_f_employees()}</label>
				<select id="accion-empleados" name="employee_id" class="input" multiple size="5" bind:value={seleccionados} required>
					{#each data.employees as e (e.id)}
						<option value={e.id}>{employeeName(e)}</option>
					{/each}
				</select>
				<p class="mt-1 text-xs text-[var(--text-subtle)]">{m.payroll_actions_f_employees_hint()}</p>
			</div>
			<div>
				<label class="label" for="accion-tipo">{m.payroll_actions_f_kind()}</label>
				<Select id="accion-tipo" name="kind" bind:value={kind}>
					{#each REGISTRABLE_KINDS as k (k)}
						<option value={k}>{m.payroll_action_kind({ kind: k })}</option>
					{/each}
				</Select>
			</div>
			<div class="grid gap-4 sm:grid-cols-2">
				<Field label={m.payroll_actions_f_starts_on()} name="starts_on" type="date" required />
				{#if campos.endsOn}
					<Field label={m.payroll_actions_f_ends_on()} name="ends_on" type="date" required />
				{/if}
				{#if campos.hours}
					<Field label={m.payroll_actions_f_hours()} name="hours" inputmode="decimal" required />
				{/if}
				{#if campos.days}
					<Field label={m.payroll_actions_f_days()} name="days" inputmode="decimal" required />
				{/if}
				{#if campos.amount}
					<Field label={campos.totalAmount ? m.payroll_actions_f_quota() : m.payroll_actions_f_amount()} name="amount" inputmode="decimal" required={kind !== 'garnishment'} />
				{/if}
				{#if campos.totalAmount}
					<Field label={m.payroll_actions_f_total_amount()} name="total_amount" inputmode="decimal" hint={m.payroll_actions_f_total_hint()} required={kind === 'garnishment'} />
				{/if}
				{#if campos.newSalary}
					<Field label={m.payroll_actions_f_new_salary()} name="new_salary" inputmode="decimal" required />
				{/if}
				{#if campos.position}
					<div>
						<label class="label" for="accion-puesto">{m.payroll_actions_f_position()}</label>
						<Select id="accion-puesto" name="position_id" required>
							{#each data.positions as p (p.id)}
								<option value={p.id}>{p.name}</option>
							{/each}
						</Select>
					</div>
				{/if}
			</div>
			{#if campos.recurring}
				<label class="flex cursor-pointer items-start gap-2 text-sm text-[var(--text)]">
					<input type="checkbox" name="is_recurring" class="mt-0.5" checked />
					{m.payroll_actions_f_recurring()}
				</label>
			{/if}
			<Field label={m.payroll_actions_f_memo()} name="memo" />
			<button type="submit" class="btn btn-primary" disabled={!data.payrollEnabled}>{m.payroll_actions_register()}</button>
		</form>
	</section>

	<section class="card p-4 lg:col-span-3" data-historial-acciones>
		<div class="mb-3 flex flex-wrap items-center justify-between gap-2">
			<h3 class="font-semibold text-[var(--text)]">
				{elegido ? m.payroll_actions_history_of({ name: employeeName(elegido) }) : m.payroll_actions_choose_employee()}
			</h3>
			<Select
				class="w-auto"
				aria-label={m.payroll_actions_f_employee()}
				value={data.empleado ?? ''}
				onchange={(ev) => goto(`/planilla/acciones?empleado=${(ev.currentTarget as HTMLSelectElement).value}`)}
			>
				<option value="">{m.payroll_none()}</option>
				{#each data.employees as e (e.id)}
					<option value={e.id}>{employeeName(e)}</option>
				{/each}
			</Select>
		</div>
		{#if elegido && data.history.length === 0}
			<p class="text-sm text-[var(--text-muted)]">{m.payroll_employee_history_empty()}</p>
		{:else if data.history.length}
			<div class="table-wrap">
				<table class="data-table">
					<thead>
						<tr>
							<th scope="col">{m.payroll_actions_col_kind()}</th>
							<th scope="col">{m.payroll_actions_col_dates()}</th>
							<th scope="col">{m.payroll_actions_col_detail()}</th>
							<th scope="col" class="num">{m.payroll_actions_col_applied()}</th>
							<th scope="col" class="num">{m.payroll_actions_col_balance()}</th>
							<th scope="col"><span class="sr-only">{m.payroll_actions_col_kind()}</span></th>
						</tr>
					</thead>
					<tbody>
						{#each data.history as a (a.id)}
							<tr class:opacity-60={a.cancelled_by !== null}>
								<td>
									<span class="font-medium text-[var(--text)]">{m.payroll_action_kind({ kind: a.kind })}</span>
									{#if a.cancelled_by}<span class="block text-xs text-[var(--negative)]">{m.payroll_actions_cancelled()}</span>{/if}
									{#if a.suspended_at}<span class="block text-xs text-[var(--warning)]">{m.payroll_actions_suspended_on({ date: formatDate(a.suspended_at) })}</span>{/if}
								</td>
								<td class="text-xs">{fechas(a)}</td>
								<td class="text-xs">{detalle(a)}{#if a.memo}<span class="block text-[var(--text-subtle)]">{a.memo}</span>{/if}</td>
								<td class="num text-xs tabular-nums">{a.applied.length ? formatMoney(a.applied_total) : m.payroll_actions_not_applied()}</td>
								<td class="num text-xs tabular-nums">{a.balance != null ? formatMoney(a.balance) : m.payroll_none()}</td>
								<td class="text-right whitespace-nowrap">
									{#if puedeSuspender(a)}
										<button type="button" class="btn btn-ghost py-1 text-xs" onclick={() => (suspendiendo = a)} disabled={!data.payrollEnabled}>{m.payroll_actions_suspend()}</button>
									{/if}
									{#if puedeAnular(a)}
										<button type="button" class="btn btn-ghost py-1 text-xs text-[var(--negative)]" onclick={() => (anulando = a)} disabled={!data.payrollEnabled}>{m.payroll_actions_cancel()}</button>
									{/if}
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		{/if}
	</section>
</div>

<Modal open={anulando !== null} title={m.payroll_actions_cancel()} onclose={() => (anulando = null)}>
	{#if anulando}
		<form id="form-anular" method="POST" action="?/anular" use:enhance={submit({ onSuccess: () => (anulando = null) })} class="grid gap-4">
			<input type="hidden" name="action_id" value={anulando.id} />
			<p class="text-sm text-[var(--text-muted)]">{m.payroll_action_kind({ kind: anulando.kind })} · {fechas(anulando)}</p>
			<Field label={m.payroll_actions_f_memo()} name="memo" />
		</form>
	{/if}
	{#snippet footer()}
		<button type="button" class="btn btn-ghost" onclick={() => (anulando = null)}>{m.payroll_cancel()}</button>
		<button type="submit" form="form-anular" class="btn btn-primary">{m.payroll_actions_cancel()}</button>
	{/snippet}
</Modal>

<Modal open={suspendiendo !== null} title={m.payroll_actions_suspend()} onclose={() => (suspendiendo = null)}>
	{#if suspendiendo}
		<form id="form-suspender" method="POST" action="?/suspender" use:enhance={submit({ onSuccess: () => (suspendiendo = null) })} class="grid gap-4">
			<input type="hidden" name="action_id" value={suspendiendo.id} />
			<Field label={m.payroll_actions_suspend_reason()} name="reason" required />
		</form>
	{/if}
	{#snippet footer()}
		<button type="button" class="btn btn-ghost" onclick={() => (suspendiendo = null)}>{m.payroll_cancel()}</button>
		<button type="submit" form="form-suspender" class="btn btn-primary">{m.payroll_actions_suspend()}</button>
	{/snippet}
</Modal>
