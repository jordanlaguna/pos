<script lang="ts">
	/**
	 * La boleta de pago (RF-58, T-1207): la cuarta plantilla de documento.
	 *
	 * Se imprime **de los rubros congelados** de la corrida (RN-66): recibe lo
	 * que guardó `payroll_run_items` y no recalcula nada, así que reimprimirla
	 * en diciembre da lo mismo que en julio aunque las tasas hayan cambiado.
	 *
	 * Habla el idioma del documento y no el de la pantalla (RN-29): el texto sale
	 * de `payslipLabels(docLocale)`, nunca de `m.*()`. Una hoja carta, sin color
	 * de marca: la boleta se firma y se archiva.
	 */
	import { formatMoney } from '$lib/domain/money';
	import { itemsByPayer, type Payslip, type PayslipItem } from '$lib/domain/payroll';
	import type { Settings } from '$lib/domain/settings';
	import { payslipLabels } from '$lib/ui/documents';
	import { formatDate } from '$lib/ui/format';

	let {
		payslip,
		settings,
		logoUrl,
		docLocale
	}: { payslip: Payslip; settings: Settings; logoUrl: string | null; docLocale: string } = $props();

	const t = $derived(payslipLabels(docLocale));
	const grupos = $derived(itemsByPayer(payslip.items));
	const empleado = $derived(payslip.employee);
	const nombre = $derived(
		[empleado.first_name, empleado.last_name_1, empleado.last_name_2].filter(Boolean).join(' ')
	);

	/** Horas, días, tasa y fechas de un rubro, en una línea chica. */
	function detalle(i: PayslipItem): string {
		const partes: string[] = [];
		if (i.quantity != null) {
			partes.push(
				i.concept === 'overtime' || i.concept === 'double_time' ? t.hours(i.quantity) : t.days(i.quantity)
			);
		}
		if (i.rate != null) partes.push(t.rate(Math.round(i.rate * 10000) / 100));
		if (i.applied_from && i.applied_to && i.applied_from !== i.applied_to) {
			partes.push(t.periodRange(formatDate(i.applied_from, docLocale), formatDate(i.applied_to, docLocale)));
		} else if (i.applied_from && i.action_id) {
			partes.push(formatDate(i.applied_from, docLocale));
		}
		if (i.action_memo) partes.push(i.action_memo);
		return partes.join(' · ');
	}

	const totalDeducciones = $derived(
		payslip.line.employee_deductions + payslip.line.income_tax + payslip.line.other_deductions
	);
</script>

<svelte:head>
	{@html `<style>@media print { @page { size: letter; margin: 15mm; } }</style>`}
</svelte:head>

<article class="print-sheet card mx-auto max-w-3xl p-6 sm:p-8" style="font-variant-numeric: tabular-nums" data-boleta>
	<header class="flex flex-wrap items-start justify-between gap-4 border-b border-[var(--border)] pb-4">
		<div class="flex items-center gap-3">
			{#if settings.document.showLogo && logoUrl}
				<img src={logoUrl} alt="" class="max-h-14 w-auto object-contain" />
			{/if}
			<div>
				<h1 class="text-lg font-bold text-[var(--text)]">{settings.business.name}</h1>
				{#if payslip.employer_number}
					<p class="text-xs text-[var(--text-muted)]">{t.employerNumber}: {payslip.employer_number}</p>
				{/if}
			</div>
		</div>
		<div class="text-right">
			<p class="text-base font-semibold text-[var(--text)]" data-boleta-titulo>{t.title(payslip.run.kind)}</p>
			<p class="text-xs text-[var(--text-muted)]">
				{t.period}: {t.periodRange(formatDate(payslip.run.period_from, docLocale), formatDate(payslip.run.period_to, docLocale))}
			</p>
			<p class="text-xs text-[var(--text-muted)]">{t.payDate}: {formatDate(payslip.run.pay_date, docLocale)}</p>
		</div>
	</header>

	{#if payslip.run.status !== 'paid'}
		<p class="mt-3 rounded-md border border-dashed border-[var(--border)] p-2 text-center text-xs text-[var(--text-muted)]">{t.draft}</p>
	{/if}
	{#if payslip.run.adjusts_run_id}
		<p class="mt-3 text-xs text-[var(--text-muted)]">
			{t.adjusts(formatDate(payslip.run.period_from, docLocale), formatDate(payslip.run.period_to, docLocale))}
		</p>
	{/if}

	<dl class="mt-4 grid grid-cols-2 gap-x-6 gap-y-1 text-sm sm:grid-cols-4">
		<dt class="text-[var(--text-subtle)]">{t.employee}</dt>
		<dd class="font-medium text-[var(--text)] sm:col-span-3" data-boleta-empleado>{nombre}</dd>
		<dt class="text-[var(--text-subtle)]">{t.identification}</dt>
		<dd class="font-mono">{empleado.identification}</dd>
		<dt class="text-[var(--text-subtle)]">{t.position}</dt>
		<dd>{empleado.position_name ?? ''}</dd>
		{#if empleado.period_salary != null && payslip.run.kind === 'regular'}
			<dt class="text-[var(--text-subtle)]">{t.salary}</dt>
			<dd>{formatMoney(empleado.period_salary)}</dd>
		{/if}
		{#if empleado.iban}
			<dt class="text-[var(--text-subtle)]">{t.account}</dt>
			<dd class="font-mono text-xs">{empleado.iban}</dd>
		{/if}
		{#if payslip.run.kind === 'settlement' && empleado.terminated_on}
			<dt class="text-[var(--text-subtle)]">{t.cause}</dt>
			<dd>{formatDate(empleado.terminated_on, docLocale)}</dd>
		{/if}
	</dl>

	{#snippet tabla(titulo: string, filas: PayslipItem[])}
		{#if filas.length}
			<table class="mt-4 w-full text-sm">
				<thead>
					<tr class="border-b border-[var(--border)] text-left text-xs text-[var(--text-subtle)]">
						<th class="py-1 font-semibold">{titulo}</th>
						<th class="py-1 font-normal">{t.colDetail}</th>
						<th class="py-1 text-right font-normal">{t.colAmount}</th>
					</tr>
				</thead>
				<tbody>
					{#each filas as i, n (n)}
						<tr class="border-b border-dashed border-[var(--border)]">
							<td class="py-1 text-[var(--text)]">{t.concept(i.concept)}</td>
							<td class="py-1 text-xs text-[var(--text-muted)]">{detalle(i)}</td>
							<td class="py-1 text-right">{formatMoney(i.amount)}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		{/if}
	{/snippet}

	{@render tabla(t.earnings, grupos.earnings)}
	{@render tabla(t.deductions, grupos.deductions)}

	<dl class="mt-4 ml-auto grid max-w-xs grid-cols-2 gap-y-1 text-sm">
		<dt class="text-[var(--text-muted)]">{t.gross}</dt>
		<dd class="text-right">{formatMoney(payslip.line.gross)}</dd>
		<dt class="text-[var(--text-muted)]">{t.totalDeductions}</dt>
		<dd class="text-right">{formatMoney(totalDeducciones)}</dd>
		<dt class="border-t border-[var(--border)] pt-1 font-semibold text-[var(--text)]">{t.net}</dt>
		<dd class="border-t border-[var(--border)] pt-1 text-right text-base font-bold text-[var(--text)]" data-boleta-neto>
			{formatMoney(payslip.line.net)}
		</dd>
	</dl>

	{#if grupos.employer.length}
		<details class="mt-4 text-xs text-[var(--text-muted)] print:hidden">
			<summary class="cursor-pointer">{t.employerCharges}: {formatMoney(payslip.line.employer_charges)}</summary>
			<ul class="mt-1 grid gap-x-6 sm:grid-cols-2">
				{#each grupos.employer as i, n (n)}
					<li class="flex justify-between"><span>{t.concept(i.concept)}</span><span>{formatMoney(i.amount)}</span></li>
				{/each}
			</ul>
		</details>
	{/if}

	<footer class="mt-10 grid grid-cols-2 gap-8 text-center text-xs text-[var(--text-muted)]">
		<p class="border-t border-[var(--border)] pt-2">{settings.business.name}</p>
		<p class="border-t border-[var(--border)] pt-2">{t.received} · {nombre}</p>
	</footer>
</article>
