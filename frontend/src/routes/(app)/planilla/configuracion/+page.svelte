<script lang="ts">
	import { enhance } from '$app/forms';
	import { submit } from '$lib/ui/forms';
	import Icon from '$lib/ui/components/Icon.svelte';
	import Modal from '$lib/ui/components/Modal.svelte';
	import Field from '$lib/ui/components/Field.svelte';
	import { FREQUENCIES, SHIFTS, type InsPolicy, type Position, type WorkSchedule } from '$lib/domain/payroll';
	import { formatDate } from '$lib/ui/format';
	import { m } from '$lib/paraglide/messages.js';
	import type { PageData } from './$types';
	import Select from '$lib/ui/components/Select.svelte';

	let { data }: { data: PageData } = $props();

	let jornada = $state<WorkSchedule | null>(null);
	let puesto = $state<Position | null>(null);
	let poliza = $state<(InsPolicy & { porcentaje: string }) | null>(null);

	function jornadaVacia(): WorkSchedule {
		return {
			id: 0,
			name: '',
			frequency: 'semimonthly',
			shift: 'day',
			hours_per_day: 8,
			workdays_per_week: 6,
			rest_day_paid: true,
			first_cut_day: 15,
			cut_weekday: 4,
			series_start: null,
			is_active: true
		};
	}

	function puestoVacio(): Position {
		return { id: 0, name: '', ccss_code: '', ins_code: '', is_active: true };
	}

	function polizaVacia(): InsPolicy & { porcentaje: string } {
		return { id: 0, number: '', rt_rate: 0, is_default: data.policies.length === 0, porcentaje: '' };
	}

	function abrirPoliza(p: InsPolicy) {
		poliza = { ...p, porcentaje: String(Math.round(p.rt_rate * 10000) / 100) };
	}

	/** Cómo corta cada jornada, en una frase. */
	function corte(j: WorkSchedule): string {
		switch (j.frequency) {
			case 'monthly':
				return m.payroll_settings_cut_monthly();
			case 'semimonthly':
				return m.payroll_settings_cut_semimonthly({ day: j.first_cut_day ?? 15 });
			case 'biweekly':
				return m.payroll_settings_cut_biweekly({ date: formatDate(j.series_start) });
			default:
				return m.payroll_settings_cut_weekly({ weekday: m.payroll_weekday({ day: String(j.cut_weekday ?? 0) }) });
		}
	}

	const DIAS = ['0', '1', '2', '3', '4', '5', '6'];
</script>

<svelte:head>
	<title>{m.payroll_settings_title()}</title>
</svelte:head>

<p class="mb-4 text-sm text-[var(--text-muted)]">{m.payroll_settings_description()}</p>

<div class="grid gap-4 lg:grid-cols-2">
	<!-- ------------------------------------------------------ datos patronales -->
	<section class="card p-4" data-seccion-patronal>
		<h2 class="mb-3 font-semibold text-[var(--text)]">{m.payroll_settings_employer_title()}</h2>
		<form method="POST" action="?/patronales" use:enhance={submit()} class="space-y-3">
			<Field
				label={m.payroll_settings_f_employer_number()}
				name="employer_number"
				value={data.settings.employer_number ?? ''}
				hint={m.payroll_settings_f_employer_hint()}
				icon="idcard"
			/>
			<label class="flex cursor-pointer items-start gap-2 text-sm text-[var(--text)]">
				<input type="checkbox" name="ina_exempt" checked={data.settings.ina_exempt} class="mt-0.5" />
				{m.payroll_settings_f_ina_exempt()}
			</label>
			<button type="submit" class="btn btn-primary" disabled={!data.payrollEnabled}>
				{m.payroll_save()}
			</button>
		</form>
	</section>

	<!-- -------------------------------------------------------------- pólizas -->
	<section class="card p-4" data-seccion-polizas>
		<div class="mb-3 flex items-center justify-between gap-2">
			<h2 class="font-semibold text-[var(--text)]">{m.payroll_settings_policies_title()}</h2>
			<button type="button" class="btn btn-ghost py-1.5 text-xs" onclick={() => (poliza = polizaVacia())} disabled={!data.payrollEnabled}>
				<Icon name="plus" size={14} />
				{m.payroll_settings_policy_new()}
			</button>
		</div>
		<p class="mb-3 text-xs text-[var(--text-muted)]">{m.payroll_settings_policies_hint()}</p>
		<ul class="divide-y divide-[var(--border)] text-sm">
			{#each data.policies as p (p.id)}
				<li class="flex items-center justify-between gap-2 py-2">
					<span>
						<span class="font-mono text-[var(--text)]">{p.number}</span>
						<span class="ml-2 text-[var(--text-muted)]">{m.payroll_percent({ value: Math.round(p.rt_rate * 10000) / 100 })}</span>
						{#if p.is_default}
							<span class="badge ml-2 bg-[var(--positive-bg)] text-[var(--positive)]">{m.payroll_settings_default()}</span>
						{/if}
					</span>
					<button type="button" class="rounded-lg p-1.5 text-[var(--text-subtle)] hover:text-[var(--accent)]" onclick={() => abrirPoliza(p)} aria-label={m.payroll_edit()}>
						<Icon name="edit" size={15} />
					</button>
				</li>
			{:else}
				<li class="py-2 text-[var(--text-muted)]">{m.payroll_files_ins_no_policies()}</li>
			{/each}
		</ul>
	</section>

	<!-- ------------------------------------------------------------- jornadas -->
	<section class="card p-4" data-seccion-jornadas>
		<div class="mb-3 flex items-center justify-between gap-2">
			<h2 class="font-semibold text-[var(--text)]">{m.payroll_settings_schedules_title()}</h2>
			<button type="button" class="btn btn-ghost py-1.5 text-xs" onclick={() => (jornada = jornadaVacia())} disabled={!data.payrollEnabled}>
				<Icon name="plus" size={14} />
				{m.payroll_settings_schedule_new()}
			</button>
		</div>
		<p class="mb-3 text-xs text-[var(--text-muted)]">{m.payroll_settings_schedules_hint()}</p>
		<div class="table-wrap">
			<table class="data-table">
				<thead>
					<tr>
						<th scope="col">{m.payroll_settings_f_name()}</th>
						<th scope="col">{m.payroll_settings_f_frequency()}</th>
						<th scope="col">{m.payroll_settings_col_cut()}</th>
						<th scope="col"><span class="sr-only">{m.payroll_edit()}</span></th>
					</tr>
				</thead>
				<tbody>
					{#each data.schedules as j (j.id)}
						<tr class:opacity-60={!j.is_active}>
							<td class="font-medium text-[var(--text)]">
								{j.name}
								{#if !j.is_active}<span class="ml-1 text-xs text-[var(--text-subtle)]">({m.payroll_settings_inactive()})</span>{/if}
							</td>
							<td>{m.payroll_frequency({ frequency: j.frequency })} · {m.payroll_shift({ shift: j.shift })} · {m.payroll_hours_short({ hours: j.hours_per_day })}</td>
							<td class="text-xs text-[var(--text-muted)]">{corte(j)}</td>
							<td class="text-right">
								<button type="button" class="rounded-lg p-1.5 text-[var(--text-subtle)] hover:text-[var(--accent)]" onclick={() => (jornada = { ...j })} aria-label={m.payroll_edit()}>
									<Icon name="edit" size={15} />
								</button>
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	</section>

	<!-- -------------------------------------------------------------- puestos -->
	<section class="card p-4" data-seccion-puestos>
		<div class="mb-3 flex items-center justify-between gap-2">
			<h2 class="font-semibold text-[var(--text)]">{m.payroll_settings_positions_title()}</h2>
			<button type="button" class="btn btn-ghost py-1.5 text-xs" onclick={() => (puesto = puestoVacio())} disabled={!data.payrollEnabled}>
				<Icon name="plus" size={14} />
				{m.payroll_settings_position_new()}
			</button>
		</div>
		<p class="mb-3 text-xs text-[var(--text-muted)]">{m.payroll_settings_positions_hint()}</p>
		<div class="table-wrap">
			<table class="data-table">
				<thead>
					<tr>
						<th scope="col">{m.payroll_settings_f_name()}</th>
						<th scope="col">{m.payroll_settings_col_codes()}</th>
						<th scope="col"><span class="sr-only">{m.payroll_edit()}</span></th>
					</tr>
				</thead>
				<tbody>
					{#each data.positions as p (p.id)}
						<tr class:opacity-60={!p.is_active}>
							<td class="font-medium text-[var(--text)]">{p.name}</td>
							<td class="font-mono text-xs">{m.payroll_settings_codes_line({ ccss: p.ccss_code, ins: p.ins_code })}</td>
							<td class="text-right">
								<button type="button" class="rounded-lg p-1.5 text-[var(--text-subtle)] hover:text-[var(--accent)]" onclick={() => (puesto = { ...p })} aria-label={m.payroll_edit()}>
									<Icon name="edit" size={15} />
								</button>
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	</section>
</div>

<!-- --------------------------------------------------------- modal jornada -->
<Modal open={jornada !== null} title={m.payroll_settings_schedules_title()} size="lg" onclose={() => (jornada = null)}>
	{#if jornada}
		<form id="form-jornada" method="POST" action="?/jornada" use:enhance={submit({ onSuccess: () => (jornada = null) })} class="grid gap-4 sm:grid-cols-2">
			<input type="hidden" name="id" value={jornada.id || ''} />
			<div class="sm:col-span-2">
				<Field label={m.payroll_settings_f_name()} name="name" bind:value={jornada.name} required />
			</div>
			<div>
				<label class="label" for="jornada-frequency">{m.payroll_settings_f_frequency()}</label>
				<Select id="jornada-frequency" name="frequency" bind:value={jornada.frequency}>
					{#each FREQUENCIES as f (f)}
						<option value={f}>{m.payroll_frequency({ frequency: f })}</option>
					{/each}
				</Select>
			</div>
			<div>
				<label class="label" for="jornada-shift">{m.payroll_settings_f_shift()}</label>
				<Select id="jornada-shift" name="shift" bind:value={jornada.shift}>
					{#each SHIFTS as s (s)}
						<option value={s}>{m.payroll_shift({ shift: s })}</option>
					{/each}
				</Select>
			</div>
			<Field label={m.payroll_settings_f_hours_per_day()} name="hours_per_day" value={String(jornada.hours_per_day)} inputmode="decimal" hint={m.payroll_settings_f_hours_hint()} />
			<Field label={m.payroll_settings_f_workdays_per_week()} name="workdays_per_week" value={String(jornada.workdays_per_week)} inputmode="numeric" />
			{#if jornada.frequency === 'semimonthly'}
				<Field label={m.payroll_settings_f_first_cut_day()} name="first_cut_day" value={String(jornada.first_cut_day ?? 15)} inputmode="numeric" min="8" max="15" />
			{:else if jornada.frequency === 'weekly'}
				<div>
					<label class="label" for="jornada-weekday">{m.payroll_settings_f_cut_weekday()}</label>
					<Select id="jornada-weekday" name="cut_weekday" value={String(jornada.cut_weekday ?? 4)}>
						{#each DIAS as d (d)}
							<option value={d}>{m.payroll_weekday({ day: d })}</option>
						{/each}
					</Select>
				</div>
			{:else if jornada.frequency === 'biweekly'}
				<Field label={m.payroll_settings_f_series_start()} name="series_start" type="date" value={jornada.series_start ?? ''} />
			{/if}
			<div class="flex flex-col gap-2 sm:col-span-2">
				<label class="flex cursor-pointer items-center gap-2 text-sm text-[var(--text)]">
					<input type="checkbox" name="rest_day_paid" checked={jornada.rest_day_paid} />
					{m.payroll_settings_f_rest_day_paid()}
				</label>
				{#if jornada.id}
					<label class="flex cursor-pointer items-center gap-2 text-sm text-[var(--text)]">
						<input type="checkbox" name="is_active" checked={jornada.is_active} />
						{m.payroll_settings_f_is_active()}
					</label>
				{/if}
			</div>
		</form>
	{/if}
	{#snippet footer()}
		<button type="button" class="btn btn-ghost" onclick={() => (jornada = null)}>{m.payroll_cancel()}</button>
		<button type="submit" form="form-jornada" class="btn btn-primary">{m.payroll_save()}</button>
	{/snippet}
</Modal>

<!-- ---------------------------------------------------------- modal puesto -->
<Modal open={puesto !== null} title={m.payroll_settings_positions_title()} onclose={() => (puesto = null)}>
	{#if puesto}
		<form id="form-puesto" method="POST" action="?/puesto" use:enhance={submit({ onSuccess: () => (puesto = null) })} class="grid gap-4">
			<input type="hidden" name="id" value={puesto.id || ''} />
			<Field label={m.payroll_settings_f_name()} name="name" bind:value={puesto.name} required />
			<Field label={m.payroll_settings_f_ccss_code()} name="ccss_code" bind:value={puesto.ccss_code} inputmode="numeric" required />
			<Field label={m.payroll_settings_f_ins_code()} name="ins_code" bind:value={puesto.ins_code} required />
			{#if puesto.id}
				<label class="flex cursor-pointer items-center gap-2 text-sm text-[var(--text)]">
					<input type="checkbox" name="is_active" checked={puesto.is_active} />
					{m.payroll_settings_f_is_active()}
				</label>
			{/if}
		</form>
	{/if}
	{#snippet footer()}
		<button type="button" class="btn btn-ghost" onclick={() => (puesto = null)}>{m.payroll_cancel()}</button>
		<button type="submit" form="form-puesto" class="btn btn-primary">{m.payroll_save()}</button>
	{/snippet}
</Modal>

<!-- ---------------------------------------------------------- modal póliza -->
<Modal open={poliza !== null} title={m.payroll_settings_policies_title()} onclose={() => (poliza = null)}>
	{#if poliza}
		<form id="form-poliza" method="POST" action="?/poliza" use:enhance={submit({ onSuccess: () => (poliza = null) })} class="grid gap-4">
			<input type="hidden" name="id" value={poliza.id || ''} />
			<Field label={m.payroll_settings_f_policy_number()} name="number" bind:value={poliza.number} required readonly={Boolean(poliza.id)} />
			<Field label={m.payroll_settings_f_rt_rate()} name="rt_rate" bind:value={poliza.porcentaje} inputmode="decimal" required />
			<label class="flex cursor-pointer items-center gap-2 text-sm text-[var(--text)]">
				<input type="checkbox" name="is_default" checked={poliza.is_default} />
				{m.payroll_settings_f_is_default()}
			</label>
		</form>
	{/if}
	{#snippet footer()}
		<button type="button" class="btn btn-ghost" onclick={() => (poliza = null)}>{m.payroll_cancel()}</button>
		<button type="submit" form="form-poliza" class="btn btn-primary">{m.payroll_save()}</button>
	{/snippet}
</Modal>
