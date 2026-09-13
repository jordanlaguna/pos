<script lang="ts">
	import { enhance } from '$app/forms';
	import { submit } from '$lib/ui/forms';
	import Icon from '$lib/ui/components/Icon.svelte';
	import Modal from '$lib/ui/components/Modal.svelte';
	import { m } from '$lib/paraglide/messages.js';
	import { kindLabel } from '$lib/ui/accounting';
	import { ACCOUNT_KINDS, type Account } from '$lib/domain/types';
	import type { ActionData, PageData } from './$types';

	let { data, form }: { data: PageData; form: ActionData } = $props();

	let creando = $state(false);
	let editando = $state<Account | null>(null);
	let borrando = $state<Account | null>(null);
</script>

{#if form?.success}
	<p class="mb-4 rounded-lg bg-[var(--success-soft)] px-3 py-2 text-sm">{form.success}</p>
{/if}
{#if form?.errors?.form}
	<p class="mb-4 rounded-lg bg-[var(--danger-soft)] px-3 py-2 text-sm">{form.errors.form}</p>
{/if}

<div class="mb-3 flex items-center justify-between gap-3">
	<p class="text-xs text-[var(--text-subtle)]">{m.accounting_system_hint()}</p>
	<button type="button" class="btn btn-primary" onclick={() => (creando = true)}>
		<Icon name="plus" size={15} />
		{m.accounting_new_account()}
	</button>
</div>

<div class="card overflow-x-auto">
	<table class="w-full min-w-[36rem] text-sm">
		<thead>
			<tr class="border-b border-[var(--border)] text-left text-xs text-[var(--text-subtle)] uppercase">
				<th class="px-3 py-2 font-semibold">{m.accounting_account_code()}</th>
				<th class="px-3 py-2 font-semibold">{m.accounting_account_name()}</th>
				<th class="px-3 py-2 font-semibold">{m.accounting_account_kind()}</th>
				<th class="px-3 py-2"></th>
			</tr>
		</thead>
		<tbody class="divide-y divide-[var(--border)]">
			{#each data.cuentas as cuenta (cuenta.id)}
				<tr class={cuenta.is_active ? '' : 'opacity-60'}>
					<td class="px-3 py-2 font-mono text-xs">{cuenta.code}</td>
					<td class="px-3 py-2">
						{cuenta.name}
						{#if cuenta.is_system}
							<span class="ml-2 rounded bg-[var(--surface-sunken)] px-1.5 py-0.5 text-[11px]">
								{m.accounting_account_system()}
							</span>
						{/if}
						{#if !cuenta.is_active}
							<span class="ml-2 text-[11px] text-[var(--text-subtle)]">
								{m.accounting_account_inactive()}
							</span>
						{/if}
					</td>
					<td class="px-3 py-2 text-[var(--text-subtle)]">{kindLabel(cuenta.kind)}</td>
					<td class="px-3 py-2 text-right whitespace-nowrap">
						<button type="button" class="btn btn-ghost btn-sm" onclick={() => (editando = cuenta)}>
							{m.accounting_edit_account()}
						</button>
						{#if !cuenta.is_system}
							<button
								type="button"
								class="btn btn-ghost btn-sm text-[var(--danger)]"
								onclick={() => (borrando = cuenta)}
							>
								<Icon name="trash" size={14} />
							</button>
						{/if}
					</td>
				</tr>
			{/each}
		</tbody>
	</table>
</div>

<Modal open={creando} title={m.accounting_new_account()} onclose={() => (creando = false)}>
	<form method="POST" action="?/crear" use:enhance={submit({ onSuccess: () => (creando = false) })} class="grid gap-3">
		<div>
	<label class="label" for="code">{m.accounting_account_code()}</label>
<input id="code" name="code" type="text" class="input" maxlength="20" required />
	{#if form?.errors?.code}
		<p class="mt-1 text-xs text-[var(--negative)]">{form?.errors?.code}</p>
	{/if}
</div>
		<div>
	<label class="label" for="name">{m.accounting_account_name()}</label>
<input id="name" name="name" type="text" class="input" maxlength="120" required />
	{#if form?.errors?.name}
		<p class="mt-1 text-xs text-[var(--negative)]">{form?.errors?.name}</p>
	{/if}
</div>
		<div>
	<label class="label" for="kind">{m.accounting_account_kind()}</label>
<select id="kind" name="kind" class="input">
				{#each ACCOUNT_KINDS as tipo (tipo)}
					<option value={tipo}>{kindLabel(tipo)}</option>
				{/each}
			</select>
	{#if form?.errors?.kind}
		<p class="mt-1 text-xs text-[var(--negative)]">{form?.errors?.kind}</p>
	{/if}
</div>
		<div class="flex justify-end gap-2">
			<button type="button" class="btn btn-ghost" onclick={() => (creando = false)}>
				{m.common_cancel()}
			</button>
			<button type="submit" class="btn btn-primary">{m.common_save()}</button>
		</div>
	</form>
</Modal>

<Modal
	open={editando !== null}
	title={m.accounting_edit_account()}
	onclose={() => (editando = null)}
>
	{#if editando}
		<form
			method="POST"
			action="?/guardar"
			use:enhance={submit({ onSuccess: () => (editando = null) })}
			class="grid gap-3"
		>
			<input type="hidden" name="id" value={editando.id} />
			<div>
	<label class="label" for="name">{m.accounting_account_name()}</label>
<input
					id="name"
					name="name"
					type="text"
					class="input"
					maxlength="120"
					value={editando.name}
					required
				/>
	{#if form?.errors?.name}
		<p class="mt-1 text-xs text-[var(--negative)]">{form?.errors?.name}</p>
	{/if}
</div>

			{#if !editando.is_system}
				<label class="flex items-center gap-2 text-sm">
					<input
						type="checkbox"
						name="is_active"
						value="true"
						checked={editando.is_active}
						class="accent-[var(--accent)]"
					/>
					{m.accounting_activate_account()}
				</label>
			{/if}

			<div class="flex justify-end gap-2">
				<button type="button" class="btn btn-ghost" onclick={() => (editando = null)}>
					{m.common_cancel()}
				</button>
				<button type="submit" class="btn btn-primary">{m.common_save()}</button>
			</div>
		</form>
	{/if}
</Modal>

<Modal open={borrando !== null} title={m.accounting_account_deleted()} onclose={() => (borrando = null)}>
	{#if borrando}
		<form
			method="POST"
			action="?/borrar"
			use:enhance={submit({ onSuccess: () => (borrando = null) })}
			class="grid gap-3"
		>
			<input type="hidden" name="id" value={borrando.id} />
			<p class="text-sm">{m.accounting_delete_account_confirm({ code: borrando.code })}</p>
			<div class="flex justify-end gap-2">
				<button type="button" class="btn btn-ghost" onclick={() => (borrando = null)}>
					{m.common_cancel()}
				</button>
				<button type="submit" class="btn btn-danger">{m.common_delete()}</button>
			</div>
		</form>
	{/if}
</Modal>
