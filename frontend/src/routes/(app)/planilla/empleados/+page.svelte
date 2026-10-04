<script lang="ts">
	import { enhance } from '$app/forms';
	import { submit } from '$lib/ui/forms';
	import Icon from '$lib/ui/components/Icon.svelte';
	import Modal from '$lib/ui/components/Modal.svelte';
	import Field from '$lib/ui/components/Field.svelte';
	import EmptyState from '$lib/ui/components/EmptyState.svelte';
	import { formatMoney } from '$lib/domain/money';
	import {
		GENDERS,
		IDENTIFICATION_TYPES,
		MARITAL_STATUSES,
		employeeName,
		type Employee
	} from '$lib/domain/payroll';
	import { formatDate } from '$lib/ui/format';
	import { m } from '$lib/paraglide/messages.js';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	function vacio(): Employee {
		return {
			id: 0,
			user_id: null,
			identification_type: 'national',
			identification: '',
			first_name: '',
			last_name_1: '',
			last_name_2: null,
			insured_number: null,
			birth_date: '',
			gender: 'F',
			marital_status: 'single',
			nationality: 'CR',
			phone: null,
			email: null,
			is_pensioner: false,
			iban: null,
			hired_on: '',
			terminated_on: null,
			termination_cause: null,
			dependent_children: 0,
			spouse_credit: false,
			is_active: true,
			contract: null
		};
	}

	/** `null` es el diálogo cerrado; viene abierto si la URL trae `?editar=`. */
	// svelte-ignore state_referenced_locally
	let editando = $state<Employee | null>(
		data.editar ? (data.employees.find((e) => e.id === data.editar) ?? null) : null
	);

	const visibles = $derived(data.inactivos ? data.employees : data.employees.filter((e) => e.is_active));
	const jornadas = $derived(new Map(data.schedules.map((s) => [s.id, s.name])));
	const puestos = $derived(new Map(data.positions.map((p) => [p.id, p.name])));

	/*
	 * El contrato del alta (RF-55). Sin una jornada y un puesto activos no hay
	 * con qué armarlo, y la ficha lo dice en vez de ofrecer listas vacías.
	 */
	const jornadasActivas = $derived(data.schedules.filter((s) => s.is_active));
	const puestosActivos = $derived(data.positions.filter((p) => p.is_active));
	let conContrato = $state(true);

	function nuevo() {
		conContrato = true;
		editando = vacio();
	}
</script>

<svelte:head>
	<title>{m.payroll_employees_title()}</title>
</svelte:head>

<div class="mb-3 flex flex-wrap items-center justify-between gap-3">
	<div>
		<p class="text-sm text-[var(--text-muted)]">{m.payroll_employees_description()}</p>
		<a
			href={data.inactivos ? '/planilla/empleados' : '/planilla/empleados?inactivos=1'}
			class="text-sm text-[var(--accent)] hover:underline"
		>
			{m.payroll_employees_show_terminated()}
		</a>
	</div>
	<button type="button" class="btn btn-primary" onclick={nuevo} disabled={!data.payrollEnabled}>
		<Icon name="plus" size={15} />
		{m.payroll_employees_new()}
	</button>
</div>

<div class="card overflow-hidden">
	<div class="table-wrap">
		<table class="data-table">
			<thead>
				<tr>
					<th scope="col">{m.payroll_employees_col_name()}</th>
					<th scope="col">{m.payroll_employees_col_identification()}</th>
					<th scope="col">{m.payroll_employees_col_contract()}</th>
					<th scope="col" class="num">{m.payroll_employees_col_salary()}</th>
					<th scope="col">{m.payroll_employees_col_status()}</th>
				</tr>
			</thead>
			<tbody>
				{#each visibles as e (e.id)}
					<tr class:opacity-60={!e.is_active}>
						<td class="font-medium">
							<a href="/planilla/empleados/{e.id}" class="text-[var(--accent)] hover:underline">{employeeName(e)}</a>
						</td>
						<td class="text-xs">
							<span class="font-mono">{e.identification}</span>
							<span class="block text-[var(--text-subtle)]">{m.payroll_id_type({ type: e.identification_type })}</span>
						</td>
						<td class="text-xs text-[var(--text-muted)]">
							{#if e.contract}
								{puestos.get(e.contract.position_id) ?? ''} · {jornadas.get(e.contract.schedule_id) ?? ''}
							{:else}
								<span class="text-[var(--warning)]">{m.payroll_employees_no_contract()}</span>
							{/if}
						</td>
						<td class="num tabular-nums">{e.contract ? formatMoney(e.contract.period_salary) : m.payroll_none()}</td>
						<td class="text-xs">
							{#if e.is_active}
								<span class="badge bg-[var(--positive-bg)] text-[var(--positive)]">{m.payroll_employees_active()}</span>
							{:else}
								<span class="badge bg-[var(--surface-sunken)] text-[var(--text-muted)]">
									{m.payroll_employees_terminated_on({ date: formatDate(e.terminated_on) })}
								</span>
							{/if}
						</td>
					</tr>
				{:else}
					<tr>
						<td colspan="5">
							<EmptyState icon="idcard" title={m.payroll_employees_empty()} description={m.payroll_summary_first_steps()}>
								<button type="button" class="btn btn-primary" onclick={nuevo} disabled={!data.payrollEnabled}>
									<Icon name="plus" size={15} />
									{m.payroll_employees_new()}
								</button>
							</EmptyState>
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
</div>

<Modal
	open={editando !== null}
	title={editando?.id ? m.payroll_employees_form_edit() : m.payroll_employees_form_new()}
	size="lg"
	onclose={() => (editando = null)}
>
	{#if editando}
		<form
			id="form-empleado"
			method="POST"
			action="?/guardar"
			use:enhance={submit({ onSuccess: () => (editando = null) })}
			class="grid gap-4 sm:grid-cols-2"
		>
			<input type="hidden" name="id" value={editando.id || ''} />
			<div>
				<label class="label" for="emp-tipo">{m.payroll_employees_f_identification_type()}</label>
				<select id="emp-tipo" name="identification_type" class="input" bind:value={editando.identification_type}>
					{#each IDENTIFICATION_TYPES as t (t)}
						<option value={t}>{m.payroll_id_type({ type: t })}</option>
					{/each}
				</select>
			</div>
			<Field label={m.payroll_employees_f_identification()} name="identification" bind:value={editando.identification} required icon="idcard" />
			<Field label={m.payroll_employees_f_first_name()} name="first_name" bind:value={editando.first_name} required />
			<Field label={m.payroll_employees_f_last_name_1()} name="last_name_1" bind:value={editando.last_name_1} required />
			<Field label={m.payroll_employees_f_last_name_2()} name="last_name_2" value={editando.last_name_2 ?? ''} />
			<Field label={m.payroll_employees_f_insured_number()} name="insured_number" value={editando.insured_number ?? ''} hint={m.payroll_employees_f_insured_hint()} />
			<Field label={m.payroll_employees_f_birth_date()} name="birth_date" type="date" bind:value={editando.birth_date} required />
			<Field label={m.payroll_employees_f_hired_on()} name="hired_on" type="date" bind:value={editando.hired_on} required />
			<div>
				<label class="label" for="emp-genero">{m.payroll_employees_f_gender()}</label>
				<select id="emp-genero" name="gender" class="input" bind:value={editando.gender}>
					{#each GENDERS as g (g)}
						<option value={g}>{m.payroll_gender({ gender: g })}</option>
					{/each}
				</select>
			</div>
			<div>
				<label class="label" for="emp-civil">{m.payroll_employees_f_marital_status()}</label>
				<select id="emp-civil" name="marital_status" class="input" bind:value={editando.marital_status}>
					{#each MARITAL_STATUSES as s (s)}
						<option value={s}>{m.payroll_marital({ status: s })}</option>
					{/each}
				</select>
			</div>
			<Field label={m.payroll_employees_f_nationality()} name="nationality" bind:value={editando.nationality} required />
			<Field label={m.payroll_employees_f_phone()} name="phone" value={editando.phone ?? ''} icon="phone" />
			<Field label={m.payroll_employees_f_email()} name="email" value={editando.email ?? ''} icon="mail" />
			<Field label={m.payroll_employees_f_iban()} name="iban" value={editando.iban ?? ''} />
			<Field label={m.payroll_employees_f_dependent_children()} name="dependent_children" value={String(editando.dependent_children)} inputmode="numeric" />
			<div class="flex flex-col justify-end gap-2">
				<label class="flex cursor-pointer items-center gap-2 text-sm text-[var(--text)]">
					<input type="checkbox" name="spouse_credit" checked={editando.spouse_credit} />
					{m.payroll_employees_f_spouse_credit()}
				</label>
				<label class="flex cursor-pointer items-center gap-2 text-sm text-[var(--text)]">
					<input type="checkbox" name="is_pensioner" checked={editando.is_pensioner} />
					{m.payroll_employees_f_is_pensioner()}
				</label>
			</div>

			{#if !editando.id}
				<!--
					El contrato, en el alta (RF-55). Solo al crear: los que siguen —un
					aumento, otro puesto— se registran desde la ficha del empleado, que
					cierra el anterior. Con la casilla apagada los campos se desmontan y
					no viajan, y el alta entra sin contrato como antes.
				-->
				<div class="grid gap-4 border-t border-[var(--border)] pt-4 sm:col-span-2 sm:grid-cols-2" data-contrato-alta>
					<h3 class="font-semibold text-[var(--text)] sm:col-span-2">{m.payroll_employee_section_contract()}</h3>
					{#if jornadasActivas.length && puestosActivos.length}
						<label class="flex cursor-pointer items-center gap-2 text-sm text-[var(--text)] sm:col-span-2">
							<input type="checkbox" name="con_contrato" bind:checked={conContrato} />
							{m.payroll_employees_f_with_contract()}
						</label>
						{#if conContrato}
							<div>
								<label class="label" for="alta-jornada">{m.payroll_employee_f_schedule()}</label>
								<select id="alta-jornada" name="schedule_id" class="input" required>
									{#each jornadasActivas as s (s.id)}
										<option value={s.id}>{s.name} · {m.payroll_frequency({ frequency: s.frequency })}</option>
									{/each}
								</select>
							</div>
							<div>
								<label class="label" for="alta-puesto">{m.payroll_employee_f_position()}</label>
								<select id="alta-puesto" name="position_id" class="input" required>
									{#each puestosActivos as p (p.id)}
										<option value={p.id}>{p.name}</option>
									{/each}
								</select>
							</div>
							<div>
								<label class="label" for="alta-poliza">{m.payroll_employee_f_policy()}</label>
								<select id="alta-poliza" name="ins_policy_id" class="input">
									<option value="">{m.payroll_employee_f_policy_default()}</option>
									{#each data.policies as p (p.id)}
										<option value={p.id}>{p.number}</option>
									{/each}
								</select>
							</div>
							<Field label={m.payroll_employee_f_period_salary()} name="period_salary" inputmode="decimal" required hint={m.payroll_employee_f_period_salary_hint()} />
							<Field label={m.payroll_employee_f_solidarista_rate()} name="solidarista_rate" inputmode="decimal" />
							<p class="self-end text-xs text-[var(--text-subtle)]">{m.payroll_employees_contract_from_hire()}</p>
						{/if}
					{:else}
						<p class="text-sm text-[var(--text-muted)] sm:col-span-2">{m.payroll_employees_contract_needs_catalog()}</p>
					{/if}
				</div>
			{/if}
		</form>
	{/if}
	{#snippet footer()}
		<button type="button" class="btn btn-ghost" onclick={() => (editando = null)}>{m.payroll_cancel()}</button>
		<button type="submit" form="form-empleado" class="btn btn-primary">{m.payroll_save()}</button>
	{/snippet}
</Modal>
