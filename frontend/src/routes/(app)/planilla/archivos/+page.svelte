<script lang="ts">
	import Icon from '$lib/ui/components/Icon.svelte';
	import { formatMoney } from '$lib/domain/money';
	import type { CcssMovement } from '$lib/domain/payroll';
	import { formatDate } from '$lib/ui/format';
	import { m } from '$lib/paraglide/messages.js';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	const MESES = Array.from({ length: 12 }, (_, i) => i + 1);
	const periodo = $derived(`year=${data.year}&month=${data.month}`);

	function movimiento(mov: CcssMovement): string {
		const fechas = mov.ends_on
			? m.payroll_period_range({ from: formatDate(mov.starts_on), to: formatDate(mov.ends_on) })
			: formatDate(mov.starts_on);
		const nombre = m.payroll_movement({ kind: mov.kind });
		return mov.detail ? `${nombre} ${fechas} (${mov.detail})` : `${nombre} ${fechas}`;
	}

	function campos(lista: string[]): string {
		return lista.map((campo) => m.api_payroll_field({ field: campo })).join(', ');
	}
</script>

<svelte:head>
	<title>{m.payroll_files_title()}</title>
</svelte:head>

<p class="mb-3 text-sm text-[var(--text-muted)]">{m.payroll_files_description()}</p>

<form method="GET" class="mb-4 flex flex-wrap items-end gap-3">
	<div>
		<label class="label" for="archivos-year">{m.payroll_files_f_year()}</label>
		<input id="archivos-year" name="year" type="number" class="input w-28" value={data.year} min="2000" max="2100" />
	</div>
	<div>
		<label class="label" for="archivos-month">{m.payroll_files_f_month()}</label>
		<select id="archivos-month" name="month" class="input w-28" value={String(data.month)}>
			{#each MESES as mes (mes)}
				<option value={String(mes)}>{mes}</option>
			{/each}
		</select>
	</div>
	<button type="submit" class="btn btn-ghost">{m.payroll_files_show()}</button>
</form>

<div class="grid gap-4">
	<!-- --------------------------------------------------------------- CCSS -->
	<section class="card p-4" data-ccss>
		<div class="mb-2 flex flex-wrap items-center justify-between gap-2">
			<h3 class="font-semibold text-[var(--text)]">{m.payroll_files_ccss_title()}</h3>
			{#if data.ccss && data.ccss.rows.length}
				<a href="/planilla/archivos/ccss.csv?{periodo}" class="btn btn-ghost py-1.5 text-xs">
					<Icon name="download" size={14} />
					{m.payroll_files_download_csv()}
				</a>
			{/if}
		</div>
		<p class="mb-3 text-xs text-[var(--text-muted)]">{m.payroll_files_ccss_hint()}</p>
		{#if data.ccssFaltantes}
			<div class="rounded-lg border border-[var(--warning)] bg-[var(--warning-bg)] p-3 text-sm" data-faltantes>
				<p class="font-semibold text-[var(--text)]">{m.payroll_files_missing_title()}</p>
				<ul class="mt-1 list-inside list-disc text-[var(--text-muted)]">
					{#if data.ccssFaltantes.company.length}
						<li>{m.payroll_files_missing_company({ fields: campos(data.ccssFaltantes.company) })}</li>
					{/if}
					{#each data.ccssFaltantes.missing as f (f.employee_id)}
						<li>{m.payroll_files_missing_employee({ name: data.nombres[f.employee_id] ?? f.employee_id, fields: campos(f.fields) })}</li>
					{/each}
				</ul>
			</div>
		{:else if !data.ccss || data.ccss.rows.length === 0}
			<p class="text-sm text-[var(--text-muted)]">{m.payroll_files_empty()}</p>
		{:else}
			<p class="mb-2 text-xs text-[var(--text-muted)]">{m.payroll_files_employer_number({ number: data.ccss.employer_number })}</p>
			<div class="table-wrap">
				<table class="data-table text-sm">
					<thead>
						<tr>
							<th scope="col">{m.payroll_files_col_identification()}</th>
							<th scope="col">{m.payroll_files_col_name()}</th>
							<th scope="col">{m.payroll_files_col_occupation()}</th>
							<th scope="col">{m.payroll_files_col_shift()}</th>
							<th scope="col" class="num">{m.payroll_files_col_salary()}</th>
							<th scope="col" class="num">{m.payroll_files_col_days()}</th>
							<th scope="col">{m.payroll_files_col_movements()}</th>
						</tr>
					</thead>
					<tbody>
						{#each data.ccss.rows as fila (fila.employee_id)}
							<tr>
								<td class="font-mono text-xs">{fila.identification}</td>
								<td>{fila.full_name}</td>
								<td class="font-mono text-xs">{fila.ccss_code}</td>
								<td>{m.payroll_ccss_shift({ shift: fila.shift })}</td>
								<td class="num tabular-nums">{formatMoney(fila.salary)}</td>
								<td class="num tabular-nums">{fila.days}</td>
								<td class="text-xs">
									{#each fila.movements as mov, n (n)}
										<span class="block">{movimiento(mov)}</span>
									{:else}
										{m.payroll_none()}
									{/each}
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
			<p class="mt-2 text-right text-sm font-semibold">{m.payroll_files_ccss_total({ amount: formatMoney(data.ccss.total_salary) })}</p>
		{/if}
	</section>

	<!-- ---------------------------------------------------------------- INS -->
	<section class="card p-4" data-ins>
		<h3 class="mb-1 font-semibold text-[var(--text)]">{m.payroll_files_ins_title()}</h3>
		<p class="mb-3 text-xs text-[var(--text-muted)]">{m.payroll_files_ins_hint()}</p>
		{#if data.policies.length === 0}
			<p class="text-sm text-[var(--text-muted)]">{m.payroll_files_ins_no_policies()}</p>
		{:else}
			<ul class="flex flex-wrap gap-2">
				{#each data.policies as p (p.id)}
					<li>
						<a href="/planilla/archivos/ins.txt?{periodo}&policy={p.id}" class="btn btn-ghost" data-ins-poliza={p.id}>
							<Icon name="download" size={15} />
							{m.payroll_files_ins_download({ number: p.number })}
						</a>
					</li>
				{/each}
			</ul>
		{/if}
	</section>

	<!-- -------------------------------------------------------------- renta -->
	<section class="card p-4" data-renta>
		<h3 class="mb-2 font-semibold text-[var(--text)]">{m.payroll_files_tax_title()}</h3>
		{#if !data.renta || data.renta.rows.length === 0}
			<p class="text-sm text-[var(--text-muted)]">{m.payroll_files_empty()}</p>
		{:else}
			<table class="data-table text-sm">
				<thead>
					<tr>
						<th scope="col">{m.payroll_files_col_name()}</th>
						<th scope="col" class="num">{m.payroll_files_col_taxable()}</th>
						<th scope="col" class="num">{m.payroll_files_col_withheld()}</th>
					</tr>
				</thead>
				<tbody>
					{#each data.renta.rows as fila (fila.employee_id)}
						<tr>
							<td>{fila.full_name}</td>
							<td class="num tabular-nums">{formatMoney(fila.taxable)}</td>
							<td class="num tabular-nums">{formatMoney(fila.withheld)}</td>
						</tr>
					{/each}
				</tbody>
			</table>
			<p class="mt-2 text-right text-sm font-semibold">
				{m.payroll_files_tax_total({ withheld: formatMoney(data.renta.total_withheld), taxable: formatMoney(data.renta.total_taxable) })}
			</p>
		{/if}
	</section>
</div>
