<script lang="ts">
	import Icon from '$lib/ui/components/Icon.svelte';
	import { formatMoney } from '$lib/domain/money';
	import { formatDate } from '$lib/ui/format';
	import { m } from '$lib/paraglide/messages.js';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	/** Una fracción se muestra en porcentaje; una regla, tal cual (días o un monto). */
	function valor(payer: string, concepto: string, v: number): string {
		if (payer !== 'rule') return m.payroll_percent({ value: Math.round(v * 10000) / 100 });
		return concepto.endsWith('_rate') ? m.payroll_percent({ value: Math.round(v * 10000) / 100 }) : v >= 1000 ? formatMoney(v) : String(v);
	}
</script>

<svelte:head>
	<title>{m.payroll_rates_title()}</title>
</svelte:head>

<p class="mb-3 text-sm text-[var(--text-muted)]">{m.payroll_rates_description()}</p>

<form method="GET" class="mb-4 flex flex-wrap items-end gap-3">
	<div>
		<label class="label" for="tasas-on">{m.payroll_rates_f_on()}</label>
		<input id="tasas-on" name="on" type="date" class="input" value={data.on} />
	</div>
	<button type="submit" class="btn btn-ghost">{m.payroll_files_show()}</button>
</form>

{#if data.rates}
	{#if data.rates.stale}
		<p class="mb-3 flex items-center gap-2 text-sm text-[var(--warning)]"><Icon name="alert" size={15} />{m.payroll_rates_stale()}</p>
	{/if}
	{#if data.rates.missing.length}
		<p class="mb-3 flex items-center gap-2 text-sm text-[var(--negative)]"><Icon name="alert" size={15} />{m.payroll_rates_missing({ missing: data.rates.missing.join(', ') })}</p>
	{/if}

	<div class="grid gap-4 lg:grid-cols-2">
		<section class="card overflow-hidden lg:col-span-2" data-tasas>
			<div class="table-wrap">
				<table class="data-table text-sm">
					<thead>
						<tr>
							<th scope="col">{m.payroll_rates_col_concept()}</th>
							<th scope="col">{m.payroll_rates_col_payer()}</th>
							<th scope="col" class="num">{m.payroll_rates_col_value()}</th>
							<th scope="col">{m.payroll_rates_col_valid_from()}</th>
							<th scope="col">{m.payroll_rates_col_verified()}</th>
							<th scope="col">{m.payroll_rates_col_source()}</th>
						</tr>
					</thead>
					<tbody>
						{#each data.rates.rates as t (`${t.payer}:${t.concept}`)}
							<tr class:text-[var(--warning)]={t.stale}>
								<td>{m.payroll_concept({ concept: t.concept })} <span class="font-mono text-xs text-[var(--text-subtle)]">{t.concept}</span></td>
								<td>{m.payroll_payer({ payer: t.payer })}</td>
								<td class="num tabular-nums">{valor(t.payer, t.concept, t.value)}</td>
								<td>{formatDate(t.valid_from)}</td>
								<td>{formatDate(t.verified_at)}</td>
								<td class="max-w-md text-xs text-[var(--text-muted)]">{t.source}</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		</section>

		<section class="card p-4" data-tramos>
			<h3 class="mb-2 font-semibold text-[var(--text)]">{m.payroll_rates_brackets_title()}</h3>
			<table class="data-table text-sm">
				<thead>
					<tr>
						<th scope="col" class="num">{m.payroll_rates_col_from()}</th>
						<th scope="col" class="num">{m.payroll_rates_col_to()}</th>
						<th scope="col" class="num">{m.payroll_rates_col_rate()}</th>
					</tr>
				</thead>
				<tbody>
					{#each data.rates.brackets as b (b.lower)}
						<tr>
							<td class="num tabular-nums">{formatMoney(b.lower)}</td>
							<td class="num tabular-nums">{b.upper == null ? m.payroll_rates_open_end() : formatMoney(b.upper)}</td>
							<td class="num tabular-nums">{m.payroll_percent({ value: Math.round(b.rate * 10000) / 100 })}</td>
						</tr>
					{/each}
				</tbody>
			</table>
			<h3 class="mt-4 mb-2 font-semibold text-[var(--text)]">{m.payroll_rates_credits_title()}</h3>
			<ul class="text-sm">
				{#each data.rates.credits as c (c.concept)}
					<li class="flex justify-between"><span>{c.concept === 'child' ? m.payroll_employees_f_dependent_children() : m.payroll_employees_f_spouse_credit()}</span><span class="tabular-nums">{formatMoney(c.amount)}</span></li>
				{/each}
			</ul>
		</section>

		<section class="card p-4" data-cesantia>
			<h3 class="mb-2 font-semibold text-[var(--text)]">{m.payroll_rates_severance_title()}</h3>
			<table class="data-table text-sm">
				<thead>
					<tr>
						<th scope="col" class="num">{m.payroll_rates_col_years()}</th>
						<th scope="col" class="num">{m.payroll_rates_col_days()}</th>
					</tr>
				</thead>
				<tbody>
					{#each data.rates.severance as s (s.years_from)}
						<tr>
							<td class="num tabular-nums">{s.years_from}{s.years_to == null ? '+' : ` – ${s.years_to}`}</td>
							<td class="num tabular-nums">{s.days}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</section>
	</div>
{/if}
