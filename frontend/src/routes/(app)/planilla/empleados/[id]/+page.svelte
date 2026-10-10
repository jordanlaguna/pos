<script lang="ts">
	import { enhance } from '$app/forms';
	import { submit } from '$lib/ui/forms';
	import Icon from '$lib/ui/components/Icon.svelte';
	import Modal from '$lib/ui/components/Modal.svelte';
	import Field from '$lib/ui/components/Field.svelte';
	import { formatMoney } from '$lib/domain/money';
	import { TERMINATION_CAUSES, employeeName, type PersonnelAction } from '$lib/domain/payroll';
	import { formatDate } from '$lib/ui/format';
	import { m } from '$lib/paraglide/messages.js';
	import type { PageData } from './$types';
	import Select from '$lib/ui/components/Select.svelte';

	let { data }: { data: PageData } = $props();

	const e = $derived(data.employee);
	const jornadas = $derived(new Map(data.schedules.map((s) => [s.id, s])));
	const puestos = $derived(new Map(data.positions.map((p) => [p.id, p.name])));
	const polizas = $derived(new Map(data.policies.map((p) => [p.id, p.number])));
	const vigente = $derived(data.contracts.find((c) => c.valid_to === null) ?? data.contracts.at(-1) ?? null);

	let contratando = $state(false);
	let dandoDeBaja = $state(false);
	let anulando = $state<PersonnelAction | null>(null);
	let suspendiendo = $state<PersonnelAction | null>(null);

	/** Horas, días o plata: lo que la acción trae. */
	function detalle(a: PersonnelAction): string {
		const partes: string[] = [];
		if (a.hours != null) partes.push(m.payroll_hours_short({ hours: a.hours }));
		if (a.days != null) partes.push(m.payroll_days_short({ days: a.days }));
		if (a.amount != null) partes.push(formatMoney(a.amount));
		if (a.new_salary != null) partes.push(formatMoney(a.new_salary));
		if (a.total_amount != null) partes.push(`/ ${formatMoney(a.total_amount)}`);
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
	<title>{employeeName(e)} · {m.payroll_employees_title()}</title>
</svelte:head>

<div class="mb-4 flex flex-wrap items-start justify-between gap-3">
	<div>
		<a href="/planilla/empleados" class="inline-flex items-center gap-1.5 text-sm text-[var(--text-muted)] hover:text-[var(--text)]">
			<Icon name="back" size={15} />
			{m.payroll_employees_title()}
		</a>
		<h2 class="mt-1 text-lg font-bold text-[var(--text)]">{employeeName(e)}</h2>
		<p class="text-sm text-[var(--text-muted)]">
			{m.payroll_id_type({ type: e.identification_type })} <span class="font-mono">{e.identification}</span>
			· {m.payroll_employees_f_hired_on()}: {formatDate(e.hired_on)}
			{#if e.terminated_on}
				· <span class="text-[var(--negative)]">{m.payroll_employees_terminated_on({ date: formatDate(e.terminated_on) })} ({m.payroll_cause({ cause: e.termination_cause ?? '' })})</span>
			{/if}
		</p>
	</div>
	<div class="flex flex-wrap gap-2">
		<a href="/planilla/empleados?editar={e.id}" class="btn btn-ghost">
			<Icon name="edit" size={15} />
			{m.payroll_edit()}
		</a>
		{#if e.is_active}
			<a href="/planilla/acciones?empleado={e.id}" class="btn btn-ghost">
				<Icon name="plus" size={15} />
				{m.payroll_employee_register_action()}
			</a>
			<button type="button" class="btn btn-ghost text-[var(--negative)]" onclick={() => (dandoDeBaja = true)} disabled={!data.payrollEnabled}>
				<Icon name="logout" size={15} />
				{m.payroll_employee_terminate()}
			</button>
		{/if}
	</div>
</div>

<div class="grid gap-4 lg:grid-cols-3">
	<!-- ------------------------------------------------------------ contrato -->
	<section class="card p-4 lg:col-span-2" data-seccion-contrato>
		<div class="mb-3 flex items-center justify-between gap-2">
			<h3 class="font-semibold text-[var(--text)]">{m.payroll_employee_section_contract()}</h3>
			{#if e.is_active}
				<button type="button" class="btn btn-ghost py-1.5 text-xs" onclick={() => (contratando = true)} disabled={!data.payrollEnabled}>
					<Icon name="plus" size={14} />
					{m.payroll_employee_contract_new()}
				</button>
			{/if}
		</div>
		{#if !vigente}
			<p class="text-sm text-[var(--warning)]">{m.payroll_employee_contract_none()}</p>
		{:else}
			<dl class="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
				<dt class="text-[var(--text-subtle)]">{m.payroll_employee_f_schedule()}</dt>
				<dd>{jornadas.get(vigente.schedule_id)?.name ?? vigente.schedule_id}</dd>
				<dt class="text-[var(--text-subtle)]">{m.payroll_employee_f_position()}</dt>
				<dd>{puestos.get(vigente.position_id) ?? vigente.position_id}</dd>
				<dt class="text-[var(--text-subtle)]">{m.payroll_employee_f_period_salary()}</dt>
				<dd class="tabular-nums" data-salario>{formatMoney(vigente.period_salary)}</dd>
				<dt class="text-[var(--text-subtle)]">{m.payroll_employee_f_policy()}</dt>
				<dd>{vigente.ins_policy_id ? polizas.get(vigente.ins_policy_id) : m.payroll_employee_f_policy_default()}</dd>
			</dl>
			{#if data.contracts.length > 1}
				<details class="mt-3 text-sm">
					<summary class="cursor-pointer text-[var(--text-muted)]">{m.payroll_employee_contracts()} ({data.contracts.length})</summary>
					<table class="data-table mt-2">
						<thead>
							<tr>
								<th scope="col">{m.payroll_employee_col_from()}</th>
								<th scope="col">{m.payroll_employee_col_to()}</th>
								<th scope="col">{m.payroll_employee_f_position()}</th>
								<th scope="col" class="num">{m.payroll_employee_f_period_salary()}</th>
							</tr>
						</thead>
						<tbody>
							{#each data.contracts as c (c.id)}
								<tr>
									<td>{formatDate(c.valid_from)}</td>
									<td>{c.valid_to ? formatDate(c.valid_to) : m.payroll_employee_col_open()}</td>
									<td>{puestos.get(c.position_id) ?? c.position_id}</td>
									<td class="num tabular-nums">{formatMoney(c.period_salary)}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</details>
			{/if}
		{/if}
	</section>

	<!-- ---------------------------------------------------------- vacaciones -->
	<section class="card p-4" data-seccion-vacaciones>
		<h3 class="mb-2 font-semibold text-[var(--text)]">{m.payroll_employee_section_vacations()}</h3>
		<p class="text-2xl font-bold tabular-nums text-[var(--text)]" data-saldo-vacaciones>
			{m.payroll_employee_vacation_balance({ days: data.vacations?.balance ?? 0 })}
		</p>
		<a href="/planilla/vacaciones?empleado={e.id}" class="text-sm text-[var(--accent)] hover:underline">{m.payroll_tab_vacations()}</a>
	</section>

	<!-- ------------------------------------------------------------ historial -->
	<section class="card p-4 lg:col-span-3" data-seccion-historial>
		<h3 class="mb-3 font-semibold text-[var(--text)]">{m.payroll_employee_section_history()}</h3>
		{#if data.history.length === 0}
			<p class="text-sm text-[var(--text-muted)]">{m.payroll_employee_history_empty()}</p>
		{:else}
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
									{#if a.cancels_action_id}
										<span class="block text-xs text-[var(--text-subtle)]">{m.payroll_actions_cancels({ id: a.cancels_action_id })}</span>
									{/if}
									{#if a.cancelled_by}
										<span class="block text-xs text-[var(--negative)]">{m.payroll_actions_cancelled()}</span>
									{/if}
									{#if a.suspended_at}
										<span class="block text-xs text-[var(--warning)]">{m.payroll_actions_suspended_on({ date: formatDate(a.suspended_at) })}</span>
									{/if}
									{#if a.source === 'import'}
										<span class="block text-xs text-[var(--text-subtle)]">{m.payroll_actions_source_import()}</span>
									{:else if a.source === 'system'}
										<span class="block text-xs text-[var(--text-subtle)]">{m.payroll_actions_source_system()}</span>
									{/if}
								</td>
								<td class="text-xs">{fechas(a)}</td>
								<td class="text-xs">
									{detalle(a)}
									{#if a.memo}<span class="block text-[var(--text-subtle)]">{a.memo}</span>{/if}
								</td>
								<td class="num text-xs tabular-nums">
									{#if a.applied.length}
										{formatMoney(a.applied_total)}
										<span class="block text-[var(--text-subtle)]">{m.payroll_actions_applied_in({ count: new Set(a.applied.map((x) => x.run_id)).size })}</span>
									{:else}
										<span class="text-[var(--text-subtle)]">{m.payroll_actions_not_applied()}</span>
									{/if}
								</td>
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

<!-- ------------------------------------------------------- modal contrato -->
<Modal open={contratando} title={m.payroll_employee_contract_new()} description={m.payroll_employee_contract_hint()} size="lg" onclose={() => (contratando = false)}>
	<form id="form-contrato" method="POST" action="?/contrato" use:enhance={submit({ onSuccess: () => (contratando = false) })} class="grid gap-4 sm:grid-cols-2">
		<div>
			<label class="label" for="contrato-jornada">{m.payroll_employee_f_schedule()}</label>
			<Select id="contrato-jornada" name="schedule_id" required>
				{#each data.schedules.filter((s) => s.is_active) as s (s.id)}
					<option value={s.id} selected={vigente?.schedule_id === s.id}>{s.name} · {m.payroll_frequency({ frequency: s.frequency })}</option>
				{/each}
			</Select>
		</div>
		<div>
			<label class="label" for="contrato-puesto">{m.payroll_employee_f_position()}</label>
			<Select id="contrato-puesto" name="position_id" required>
				{#each data.positions.filter((p) => p.is_active) as p (p.id)}
					<option value={p.id} selected={vigente?.position_id === p.id}>{p.name}</option>
				{/each}
			</Select>
		</div>
		<div>
			<label class="label" for="contrato-poliza">{m.payroll_employee_f_policy()}</label>
			<Select id="contrato-poliza" name="ins_policy_id">
				<option value="">{m.payroll_employee_f_policy_default()}</option>
				{#each data.policies as p (p.id)}
					<option value={p.id}>{p.number}</option>
				{/each}
			</Select>
		</div>
		<Field label={m.payroll_employee_f_valid_from()} name="valid_from" type="date" value={vigente ? '' : e.hired_on} required />
		<Field label={m.payroll_employee_f_period_salary()} name="period_salary" value={vigente ? String(vigente.period_salary) : ''} inputmode="decimal" required hint={m.payroll_employee_f_period_salary_hint()} />
		<Field label={m.payroll_employee_f_solidarista_rate()} name="solidarista_rate" value={vigente?.solidarista_rate ? String(Math.round(vigente.solidarista_rate * 10000) / 100) : ''} inputmode="decimal" />
	</form>
	{#snippet footer()}
		<button type="button" class="btn btn-ghost" onclick={() => (contratando = false)}>{m.payroll_cancel()}</button>
		<button type="submit" form="form-contrato" class="btn btn-primary">{m.payroll_save()}</button>
	{/snippet}
</Modal>

<!-- ----------------------------------------------------------- modal baja -->
<Modal open={dandoDeBaja} title={m.payroll_employee_terminate_title({ name: employeeName(e) })} description={m.payroll_employee_terminate_hint()} onclose={() => (dandoDeBaja = false)}>
	<form
		id="form-baja"
		method="POST"
		action="?/baja"
		use:enhance={submit({ onRedirect: () => (dandoDeBaja = false) })}
		class="grid gap-4"
	>
		<Field label={m.payroll_employee_f_terminated_on()} name="terminated_on" type="date" required />
		<div>
			<label class="label" for="baja-causa">{m.payroll_employee_f_cause()}</label>
			<Select id="baja-causa" name="cause">
				{#each TERMINATION_CAUSES as c (c)}
					<option value={c}>{m.payroll_cause({ cause: c })}</option>
				{/each}
			</Select>
		</div>
	</form>
	{#snippet footer()}
		<button type="button" class="btn btn-ghost" onclick={() => (dandoDeBaja = false)}>{m.payroll_cancel()}</button>
		<button type="submit" form="form-baja" class="btn btn-primary">{m.payroll_employee_terminate()}</button>
	{/snippet}
</Modal>

<!-- ---------------------------------------------------------- modal anular -->
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

<!-- ------------------------------------------------------- modal suspender -->
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
