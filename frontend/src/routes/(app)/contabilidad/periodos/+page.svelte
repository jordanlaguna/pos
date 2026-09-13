<script lang="ts">
	import { enhance } from '$app/forms';
	import { submit } from '$lib/ui/forms';
	import Modal from '$lib/ui/components/Modal.svelte';
	import EmptyState from '$lib/ui/components/EmptyState.svelte';
	import { formatDate } from '$lib/ui/format';
	import { m } from '$lib/paraglide/messages.js';
	import { periodLabel } from '$lib/ui/accounting';
	import type { AccountingPeriod } from '$lib/domain/types';
	import type { ActionData, PageData } from './$types';

	let { data, form }: { data: PageData; form: ActionData } = $props();

	/** El mes que se está por cerrar. Cerrar no se deshace: se confirma. */
	let cerrando = $state<AccountingPeriod | null>(null);
</script>

{#if form?.success}
	<p class="mb-4 rounded-lg bg-[var(--success-soft)] px-3 py-2 text-sm">{form.success}</p>
{/if}
{#if form?.errors?.form}
	<p class="mb-4 rounded-lg bg-[var(--danger-soft)] px-3 py-2 text-sm">{form.errors.form}</p>
{/if}

{#if !data.periodos.length}
	<EmptyState icon="book" title={m.accounting_periods_empty()} />
{:else}
	<div class="card overflow-x-auto">
		<table class="w-full min-w-[28rem] text-sm">
			<thead>
				<tr
					class="border-b border-[var(--border)] text-left text-xs text-[var(--text-subtle)] uppercase"
				>
					<th class="px-3 py-2 font-semibold">{m.accounting_period()}</th>
					<th class="px-3 py-2 font-semibold">{m.accounting_status()}</th>
					<th class="px-3 py-2"></th>
				</tr>
			</thead>
			<tbody class="divide-y divide-[var(--border)]">
				{#each data.periodos as periodo (periodo.id)}
					<tr>
						<td class="px-3 py-2 font-medium">{periodLabel(periodo.year, periodo.month)}</td>
						<td class="px-3 py-2">
							{#if periodo.status === 'closed'}
								<span class="text-[var(--text-subtle)]">
									{m.accounting_period_closed()}
									{#if periodo.closed_at}
										· {m.accounting_period_closed_by({ date: formatDate(periodo.closed_at) })}
									{/if}
								</span>
							{:else}
								<span class="font-medium text-[var(--success)]">{m.accounting_period_open()}</span>
							{/if}
						</td>
						<td class="px-3 py-2 text-right">
							{#if periodo.status === 'open'}
								<button
									type="button"
									class="btn btn-ghost btn-sm"
									onclick={() => (cerrando = periodo)}
								>
									{m.accounting_close_period()}
								</button>
							{/if}
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
{/if}

<Modal open={cerrando !== null} title={m.accounting_close_period()} onclose={() => (cerrando = null)}>
	{#if cerrando}
		<form
			method="POST"
			action="?/cerrar"
			use:enhance={submit({ onSuccess: () => (cerrando = null) })}
			class="grid gap-3"
		>
			<input type="hidden" name="year" value={cerrando.year} />
			<input type="hidden" name="month" value={cerrando.month} />
			<p class="text-sm">
				{m.accounting_close_confirm({
					period: periodLabel(cerrando.year, cerrando.month)
				})}
			</p>
			<div class="flex justify-end gap-2">
				<button type="button" class="btn btn-ghost" onclick={() => (cerrando = null)}>
					{m.common_cancel()}
				</button>
				<button type="submit" class="btn btn-danger">{m.accounting_close_period()}</button>
			</div>
		</form>
	{/if}
</Modal>
