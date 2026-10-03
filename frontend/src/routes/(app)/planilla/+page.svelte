<script lang="ts">
	import Icon from '$lib/ui/components/Icon.svelte';
	import { formatMoney } from '$lib/domain/money';
	import { employeeName } from '$lib/domain/payroll';
	import { formatDate } from '$lib/ui/format';
	import { m } from '$lib/paraglide/messages.js';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	const faltaAlgo = $derived(
		data.faltantes.employerNumber ||
			data.faltantes.policy ||
			data.faltantes.sinContrato.length > 0 ||
			data.faltantes.sinAsegurado.length > 0
	);
</script>

<svelte:head>
	<title>{m.payroll_summary_title()}</title>
</svelte:head>

<div class="grid gap-4 lg:grid-cols-2">
	<section class="card p-4" data-resumen-corridas>
		<div class="mb-3 flex items-center justify-between gap-2">
			<h2 class="font-semibold text-[var(--text)]">{m.payroll_summary_open_runs()}</h2>
			<a href="/planilla/corridas" class="text-sm text-[var(--accent)] hover:underline">
				{m.payroll_summary_see_runs()}
			</a>
		</div>
		{#if data.enCurso.length === 0}
			<p class="text-sm text-[var(--text-muted)]">{m.payroll_summary_no_open_runs()}</p>
		{:else}
			<ul class="divide-y divide-[var(--border)] text-sm">
				{#each data.enCurso as corrida (corrida.id)}
					<li class="flex items-center justify-between gap-3 py-2">
						<a href="/planilla/corridas/{corrida.id}" class="font-medium text-[var(--accent)] hover:underline">
							{m.payroll_run_kind({ kind: corrida.kind })}
							· {m.payroll_period_range({ from: formatDate(corrida.period_from), to: formatDate(corrida.period_to) })}
						</a>
						<span class="badge bg-[var(--surface-sunken)] text-[var(--text-muted)]">
							{m.payroll_run_status({ status: corrida.status })}
						</span>
						<span class="tabular-nums text-[var(--text)]">{formatMoney(corrida.net)}</span>
					</li>
				{/each}
			</ul>
		{/if}
		{#if data.sinEmpleados}
			<p class="mt-3 text-sm text-[var(--text-muted)]">{m.payroll_summary_first_steps()}</p>
		{/if}
	</section>

	<section class="card p-4" data-resumen-faltantes>
		<div class="mb-3 flex items-center justify-between gap-2">
			<h2 class="font-semibold text-[var(--text)]">{m.payroll_summary_missing_title()}</h2>
			<a href="/planilla/empleados" class="text-sm text-[var(--accent)] hover:underline">
				{m.payroll_summary_active_employees({ count: data.activos })}
			</a>
		</div>
		{#if !faltaAlgo}
			<p class="flex items-center gap-2 text-sm text-[var(--positive)]">
				<Icon name="check" size={15} />
				{m.payroll_summary_missing_none()}
			</p>
		{:else}
			<ul class="space-y-1 text-sm text-[var(--text)]">
				{#if data.faltantes.employerNumber}
					<li><a href="/planilla/configuracion" class="hover:underline">{m.payroll_summary_missing_employer()}</a></li>
				{/if}
				{#if data.faltantes.policy}
					<li><a href="/planilla/configuracion" class="hover:underline">{m.payroll_summary_missing_policy()}</a></li>
				{/if}
				{#each data.faltantes.sinContrato as e (e.id)}
					<li>
						<a href="/planilla/empleados/{e.id}" class="hover:underline">
							{m.payroll_summary_missing_contract({ name: employeeName(e) })}
						</a>
					</li>
				{/each}
				{#each data.faltantes.sinAsegurado as e (e.id)}
					<li>
						<a href="/planilla/empleados/{e.id}" class="hover:underline">
							{m.payroll_summary_missing_insured({ name: employeeName(e) })}
						</a>
					</li>
				{/each}
			</ul>
		{/if}
	</section>

	<section class="card p-4 lg:col-span-2" data-resumen-avisos>
		<ul class="space-y-2 text-sm">
			{#if data.tasas}
				<li class="flex items-center gap-2 {data.tasas.stale ? 'text-[var(--warning)]' : 'text-[var(--text-muted)]'}">
					<Icon name={data.tasas.stale ? 'alert' : 'check'} size={15} />
					{#if data.tasas.stale}
						{m.payroll_summary_rates_stale()}
					{:else}
						{m.payroll_summary_rates_ok({ verified_at: formatDate(data.tasas.verifiedAt) })}
					{/if}
					<a href="/planilla/tasas" class="text-[var(--accent)] hover:underline">{m.payroll_tab_rates()}</a>
				</li>
			{/if}
			{#if data.aguinaldoPendiente}
				<li class="flex items-center gap-2 text-[var(--warning)]">
					<Icon name="calendar" size={15} />
					{m.payroll_summary_aguinaldo_due({ year: data.aguinaldoPendiente })}
					<a href="/planilla/corridas" class="text-[var(--accent)] hover:underline">{m.payroll_runs_new_aguinaldo()}</a>
				</li>
			{/if}
		</ul>
	</section>
</div>
