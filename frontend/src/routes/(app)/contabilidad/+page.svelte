<script lang="ts">
	import { enhance } from '$app/forms';
	import { submit } from '$lib/ui/forms';
	import Icon from '$lib/ui/components/Icon.svelte';
	import EmptyState from '$lib/ui/components/EmptyState.svelte';
	import { formatMoney } from '$lib/domain/money';
	import { formatDate } from '$lib/ui/format';
	import { m } from '$lib/paraglide/messages.js';
	import { entryTitle } from '$lib/ui/accounting';
	import type { ActionData, PageData } from './$types';

	let { data, form }: { data: PageData; form: ActionData } = $props();

	/** Cuántos renglones de saldos iniciales se ofrecen. */
	const RENGLONES = 6;

	let filas = $state(
		Array.from({ length: RENGLONES }, () => ({ code: '', debit: '', credit: '' }))
	);

	const debitos = $derived(filas.reduce((t, f) => t + (Number(f.debit) || 0), 0));
	const creditos = $derived(filas.reduce((t, f) => t + (Number(f.credit) || 0), 0));
	const diferencia = $derived(Math.round((debitos - creditos) * 100) / 100);

	const abierto = $derived(data.periodos.find((p) => p.status === 'open') ?? null);
	const hoy = new Date().toISOString().slice(0, 10);
</script>

{#if !data.status.active}
	<div class="card p-5">
		<h2 class="text-lg font-semibold">{m.accounting_inactive_title()}</h2>
		<p class="mt-1 max-w-3xl text-sm text-[var(--text-subtle)]">
			{m.accounting_inactive_body()}
		</p>

		<form method="POST" action="?/activar" use:enhance={submit()} class="mt-5 grid gap-4">
			<div class="grid gap-4 sm:grid-cols-2">
				<div>
	<label class="label" for="template">{m.accounting_template()}</label>
<select id="template" name="template" class="input">
						{#each data.status.templates as plantilla (plantilla)}
							<option value={plantilla}>{m.accounting_template_commerce()}</option>
						{/each}
					</select>
	{#if form?.errors?.template}
		<p class="mt-1 text-xs text-[var(--negative)]">{form?.errors?.template}</p>
	{/if}
</div>

				<div>
	<label class="label" for="start_date">{m.accounting_start_date()}</label>
<input
						id="start_date"
						name="start_date"
						type="date"
						class="input"
						value={hoy.slice(0, 8) + '01'}
						required
					/>
	{#if form?.errors?.start_date}
		<p class="mt-1 text-xs text-[var(--negative)]">{form?.errors?.start_date}</p>
	{/if}
	<p class="mt-1 text-xs text-[var(--text-subtle)]">{m.accounting_start_date_hint()}</p>
</div>
			</div>

			<div>
				<h3 class="text-sm font-semibold">{m.accounting_opening_title()}</h3>
				<p class="mt-1 max-w-3xl text-xs text-[var(--text-subtle)]">
					{m.accounting_opening_hint()}
				</p>

				<div class="mt-3 overflow-x-auto">
					<table class="w-full min-w-[34rem] text-sm">
						<thead>
							<tr class="text-left text-xs text-[var(--text-subtle)] uppercase">
								<th class="py-1 font-semibold">{m.accounting_account_name()}</th>
								<th class="py-1 text-right font-semibold">{m.accounting_entry_debit()}</th>
								<th class="py-1 text-right font-semibold">{m.accounting_entry_credit()}</th>
							</tr>
						</thead>
						<tbody>
							{#each filas as fila, i (i)}
								<tr>
									<td class="py-1 pr-2">
										<select name="opening_code" bind:value={fila.code} class="input">
											<option value=""></option>
											{#each data.status.chart as cuenta (cuenta.code)}
												<option value={cuenta.code}>{cuenta.code} · {cuenta.name}</option>
											{/each}
										</select>
									</td>
									<td class="py-1 pr-2">
										<input
											name="opening_debit"
											type="number"
											step="0.01"
											min="0"
											class="input text-right"
											bind:value={fila.debit}
										/>
									</td>
									<td class="py-1">
										<input
											name="opening_credit"
											type="number"
											step="0.01"
											min="0"
											class="input text-right"
											bind:value={fila.credit}
										/>
									</td>
								</tr>
							{/each}
						</tbody>
						<tfoot>
							<tr class="border-t border-[var(--border)] font-semibold">
								<td class="py-2">
									{#if diferencia === 0}
										<span class="text-[var(--text-subtle)]">{m.accounting_entry_balanced()}</span>
									{:else}
										<span class="text-[var(--danger)]">
											{m.accounting_entry_out_of_balance({
												amount: formatMoney(Math.abs(diferencia))
											})}
										</span>
									{/if}
								</td>
								<td class="py-2 text-right tabular-nums">{formatMoney(debitos)}</td>
								<td class="py-2 text-right tabular-nums">{formatMoney(creditos)}</td>
							</tr>
						</tfoot>
					</table>
				</div>
			</div>

			<div>
	<label class="label" for="description">{m.accounting_opening_description()}</label>
<input id="description" name="description" type="text" class="input" maxlength="255" />
	{#if form?.errors?.description}
		<p class="mt-1 text-xs text-[var(--negative)]">{form?.errors?.description}</p>
	{/if}
</div>

			{#if form?.errors?.form}
				<p class="text-sm text-[var(--danger)]">{form.errors.form}</p>
			{/if}

			<div>
				<button type="submit" class="btn btn-primary">
					<Icon name="book" size={15} />
					{m.accounting_activate()}
				</button>
			</div>
		</form>
	</div>
{:else}
	{#if form?.success}
		<p class="mb-4 rounded-lg bg-[var(--success-soft)] px-3 py-2 text-sm">{form.success}</p>
	{/if}

	<div class="mb-4 grid gap-3 sm:grid-cols-3">
		<div class="card p-3">
			<p class="text-xs font-semibold tracking-wide text-[var(--text-subtle)] uppercase">
				{m.accounting_open_period()}
			</p>
			<p class="mt-1 text-lg font-semibold">
				{abierto ? `${abierto.month}/${abierto.year}` : m.accounting_no_open_period()}
			</p>
			{#if data.status.start_date}
				<p class="text-xs text-[var(--text-subtle)]">
					{m.accounting_active_since({ date: formatDate(data.status.start_date) })}
				</p>
			{/if}
		</div>

		<div class="card p-3">
			<p class="text-xs font-semibold tracking-wide text-[var(--text-subtle)] uppercase">
				{m.accounting_unclassified()}
			</p>
			<p
				class="mt-1 text-lg font-semibold tabular-nums {data.porClasificar !== 0
					? 'text-[var(--danger)]'
					: ''}"
			>
				{formatMoney(data.porClasificar)}
			</p>
			<p class="text-xs text-[var(--text-subtle)]">
				{data.porClasificar === 0
					? m.accounting_unclassified_zero()
					: m.accounting_unclassified_hint()}
			</p>
		</div>

		<div class="card p-3">
			<p class="text-xs font-semibold tracking-wide text-[var(--text-subtle)] uppercase">
				{m.accounting_result_month()}
			</p>
			<p class="mt-1 text-lg font-semibold tabular-nums">{formatMoney(data.resultado)}</p>
		</div>
	</div>

	<div class="card p-4">
		<div class="mb-3 flex items-center justify-between">
			<h2 class="text-sm font-semibold">{m.accounting_latest_entries()}</h2>
			<a href="/contabilidad/asientos" class="text-sm text-[var(--accent)]">
				{m.accounting_see_all()}
			</a>
		</div>

		{#if !data.asientos.length}
			<EmptyState icon="book" title={m.accounting_entry_empty()} />
		{:else}
			<ul class="divide-y divide-[var(--border)] text-sm">
				{#each data.asientos as asiento (asiento.id)}
					<li class="flex items-center justify-between gap-3 py-2">
						<div class="min-w-0">
							<a
								href="/contabilidad/asientos?entry={asiento.id}"
								class="truncate font-medium hover:text-[var(--accent)]"
							>
								{entryTitle(asiento)}
							</a>
							<p class="text-xs text-[var(--text-subtle)]">
								#{asiento.entry_number} · {formatDate(asiento.entry_date)}
							</p>
						</div>
					</li>
				{/each}
			</ul>
		{/if}
	</div>
{/if}
