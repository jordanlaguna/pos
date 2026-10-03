<script lang="ts">
	import { enhance } from '$app/forms';
	import { submit } from '$lib/ui/forms';
	import Icon from '$lib/ui/components/Icon.svelte';
	import Field from '$lib/ui/components/Field.svelte';
	import type { ImportResult, ImportRowError } from '$lib/domain/payroll';
	import { apiMessage } from '$lib/ui/messages';
	import { m } from '$lib/paraglide/messages.js';
	import type { ActionData, PageData } from './$types';

	let { data, form }: { data: PageData; form: ActionData } = $props();

	const preview = $derived((form?.preview ?? null) as ImportResult | null);
	const payload = $derived((form?.payload ?? '') as string);
	const hecho = $derived((form?.done ?? null) as ImportResult | null);
	let ocupado = $state(false);

	/** La misma frase que daría el formulario para ese «no». */
	function problema(e: ImportRowError): string {
		return apiMessage({ status: 400, code: e.code, data: { field: e.field, reason: e.reason } });
	}

	const rotulos = {
		positions: m.payroll_import_sheet_positions(),
		employees: m.payroll_import_sheet_employees(),
		earnings: m.payroll_import_sheet_earnings(),
		deductions: m.payroll_import_sheet_deductions()
	} as const;
</script>

<svelte:head>
	<title>{m.payroll_import_title()}</title>
</svelte:head>

<p class="mb-4 text-sm text-[var(--text-muted)]">{m.payroll_import_description()}</p>

<div class="grid gap-4 lg:grid-cols-2">
	<section class="card p-4" data-import-archivos>
		<form method="POST" action="?/revisar" enctype="multipart/form-data" use:enhance={submit({ setBusy: (b) => (ocupado = b), quiet: true })} class="grid gap-4">
			<Field label={m.payroll_import_f_as_of()} name="as_of" type="date" required />
			{#each data.hojas as hoja (hoja)}
				<div>
					<div class="flex items-center justify-between gap-2">
						<label class="label" for="archivo-{hoja}">{rotulos[hoja]}</label>
						<a href="/planilla/importar/plantilla/{hoja}.csv" class="text-xs text-[var(--accent)] hover:underline">
							{m.payroll_import_template()}
						</a>
					</div>
					<input id="archivo-{hoja}" name={hoja} type="file" accept=".xlsx,.csv" class="input" required={hoja === 'employees'} />
				</div>
			{/each}
			<p class="text-xs text-[var(--text-subtle)]">{m.payroll_import_file_hint()}</p>
			<button type="submit" class="btn btn-primary" disabled={!data.payrollEnabled || ocupado}>
				<Icon name="search" size={15} />
				{m.payroll_import_preview()}
			</button>
		</form>
	</section>

	<section class="card p-4" data-import-resultado>
		{#if hecho}
			<p class="flex items-center gap-2 text-sm font-semibold text-[var(--positive)]">
				<Icon name="check" size={16} />
				{m.payroll_import_done({ employees: hecho.employees })}
			</p>
			<a href="/planilla/empleados" class="btn btn-ghost mt-3">{m.payroll_summary_see_employees()}</a>
		{:else if preview}
			{#if preview.ok}
				<p class="flex items-start gap-2 text-sm text-[var(--positive)]" data-import-ok>
					<Icon name="check" size={16} class="mt-0.5 shrink-0" />
					{m.payroll_import_ok({ employees: preview.employees, positions: preview.positions, earnings: preview.earnings, deductions: preview.deductions })}
				</p>
				<form method="POST" action="?/confirmar" use:enhance={submit({ setBusy: (b) => (ocupado = b) })} class="mt-3">
					<input type="hidden" name="payload" value={payload} />
					<button type="submit" class="btn btn-primary" disabled={!data.payrollEnabled || ocupado}>
						<Icon name="check" size={15} />
						{m.payroll_import_confirm()}
					</button>
				</form>
			{:else}
				<p class="flex items-start gap-2 text-sm text-[var(--negative)]" data-import-errores>
					<Icon name="alert" size={16} class="mt-0.5 shrink-0" />
					{m.payroll_import_errors({ count: preview.errors.length })}
				</p>
				<div class="table-wrap mt-3">
					<table class="data-table text-xs">
						<thead>
							<tr>
								<th scope="col">{m.payroll_import_col_sheet()}</th>
								<th scope="col" class="num">{m.payroll_import_col_row()}</th>
								<th scope="col">{m.payroll_import_col_problem()}</th>
							</tr>
						</thead>
						<tbody>
							{#each preview.errors as e, n (n)}
								<tr>
									<td>{m.payroll_sheet({ sheet: e.sheet })}</td>
									<td class="num tabular-nums">{e.row}</td>
									<td>{problema(e)}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			{/if}
		{:else}
			<p class="text-sm text-[var(--text-muted)]">{m.payroll_import_file_hint()}</p>
		{/if}
	</section>
</div>
