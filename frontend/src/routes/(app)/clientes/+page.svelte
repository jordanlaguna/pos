<script lang="ts">
	import { enhance } from '$app/forms';
	import { submit } from '$lib/ui/forms';
	import Icon from '$lib/ui/components/Icon.svelte';
	import PageHeader from '$lib/ui/components/PageHeader.svelte';
	import Modal from '$lib/ui/components/Modal.svelte';
	import Field from '$lib/ui/components/Field.svelte';
	import EmptyState from '$lib/ui/components/EmptyState.svelte';
	import Spinner from '$lib/ui/components/Spinner.svelte';
	import { toasts } from '$lib/ui/stores/toast.svelte';
	import { formatDate, fullName, toDateInput } from '$lib/ui/format';
	import type { Client } from '$lib/domain/types';
	import { m } from '$lib/paraglide/messages.js';
	import type { ActionData, PageData } from './$types';

	let { data, form }: { data: PageData; form: ActionData } = $props();

	let search = $state('');
	let modalOpen = $state(false);
	let editing = $state<Client | null>(null);
	let submitting = $state(false);

	let f = $state({
		identification: '',
		name: '',
		last_name: '',
		second_name: '',
		email: '',
		telephone: '',
		address: '',
		register_date: ''
	});

	const filtered = $derived.by(() => {
		const term = search.trim().toLowerCase();
		if (!term) return data.clients;
		return data.clients.filter(
			(c) =>
				fullName(c).toLowerCase().includes(term) ||
				c.identification.toLowerCase().includes(term) ||
				c.email.toLowerCase().includes(term) ||
				String(c.telephone).includes(term)
		);
	});

	function openCreate() {
		editing = null;
		f = {
			identification: '',
			name: '',
			last_name: '',
			second_name: '',
			email: '',
			telephone: '',
			address: '',
			register_date: toDateInput(new Date())
		};
		modalOpen = true;
	}

	function openEdit(client: Client) {
		editing = client;
		f = {
			identification: client.identification,
			name: client.name,
			last_name: client.last_name,
			second_name: client.second_name,
			email: client.email,
			telephone: String(client.telephone ?? ''),
			address: client.address ?? '',
			register_date: toDateInput(client.register_date)
		};
		modalOpen = true;
	}

</script>

<PageHeader title={m.clients_title()} description={m.clients_description()}>
	{#snippet actions()}
		<button type="button" class="btn btn-primary" onclick={openCreate}>
			<Icon name="plus" size={15} />
			{m.clients_new_title()}
		</button>
	{/snippet}
</PageHeader>

<div class="card mb-4 p-3">
	<label class="label" for="cliente-buscar">{m.common_search()}</label>
	<div class="relative">
		<span
			class="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-[var(--text-subtle)]"
		>
			<Icon name="search" size={15} />
		</span>
		<input
			id="cliente-buscar"
			bind:value={search}
			type="search"
			placeholder={m.clients_search_placeholder()}
			class="input pl-9"
		/>
	</div>
</div>

<div class="card overflow-hidden">
	<div class="table-wrap">
		<table class="data-table">
			<thead>
				<tr>
					<th scope="col">{m.clients_col_client()}</th>
					<th scope="col">{m.people_label_identification()}</th>
					<th scope="col">{m.clients_col_contact()}</th>
					<th scope="col">{m.clients_col_address()}</th>
					<th scope="col">{m.clients_col_register()}</th>
					<th scope="col"><span class="sr-only">{m.common_actions()}</span></th>
				</tr>
			</thead>
			<tbody>
				{#each filtered as client (client.id_client)}
					<tr>
						<td class="font-medium text-[var(--text)]">{fullName(client)}</td>
						<td class="tabular-nums">{client.identification}</td>
						<td>
							<p class="text-xs text-[var(--text)]">{client.email}</p>
							<p class="text-xs tabular-nums text-[var(--text-subtle)]">
								{client.telephone}
							</p>
						</td>
						<td class="max-w-xs truncate text-xs text-[var(--text-muted)]">
							{client.address}
						</td>
						<td class="whitespace-nowrap text-xs">{formatDate(client.register_date)}</td>
						<td class="text-right">
							<button
								type="button"
								class="rounded-lg p-1.5 text-[var(--text-subtle)] hover:bg-[var(--surface-sunken)] hover:text-[var(--accent)]"
								onclick={() => openEdit(client)}
								aria-label={m.users_edit({ person: fullName(client) })}
							>
								<Icon name="edit" size={15} />
							</button>
						</td>
					</tr>
				{:else}
					<tr>
						<td colspan="6">
							<EmptyState
								icon="users"
								title={m.clients_none()}
								description={search ? m.clients_no_match() : m.clients_register_hint()}
								compact
							/>
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
</div>

<Modal
	open={modalOpen}
	title={editing ? m.clients_edit_title() : m.clients_new_title()}
	description={editing ? fullName(editing) : undefined}
	busy={submitting}
	onclose={() => (modalOpen = false)}
>
	<form
		id="client-form"
		method="POST"
		action={editing ? '?/actualizar' : '?/crear'}
		use:enhance={submit({
			onSuccess: () => (modalOpen = false),
			setBusy: (v) => (submitting = v)
		})}
		class="grid gap-4 sm:grid-cols-2"
	>
		{#if editing}
			<input type="hidden" name="id_client" value={editing.id_client} />
		{/if}

		<Field
			label={m.people_label_identification()}
			name="identification"
			bind:value={f.identification}
			icon="idcard"
			inputmode="numeric"
			required
			error={form?.errors?.identification}
		/>
		<Field
			label={m.people_label_name()}
			name="name"
			bind:value={f.name}
			icon="user"
			required
			error={form?.errors?.name}
		/>
		<Field
			label={m.people_label_first_last_name()}
			name="last_name"
			bind:value={f.last_name}
			required
			error={form?.errors?.last_name}
		/>
		<Field
			label={m.people_label_second_last_name()}
			name="second_name"
			bind:value={f.second_name}
			required
			error={form?.errors?.second_name}
		/>
		<Field
			label={m.people_label_email()}
			name="email"
			type="email"
			bind:value={f.email}
			icon="mail"
			required
			error={form?.errors?.email}
		/>
		<Field
			label={m.people_label_telephone()}
			name="telephone"
			bind:value={f.telephone}
			icon="phone"
			inputmode="tel"
			required
			error={form?.errors?.telephone}
		/>
		<Field
			label={m.people_label_address()}
			name="address"
			bind:value={f.address}
			required
			error={form?.errors?.address}
			class="sm:col-span-2"
		/>
		<Field
			label={m.people_label_register_date()}
			name="register_date"
			type="date"
			bind:value={f.register_date}
			required
			error={form?.errors?.register_date}
		/>
	</form>

	{#snippet footer()}
		<button
			type="button"
			class="btn btn-ghost"
			onclick={() => (modalOpen = false)}
			disabled={submitting}
		>
			{m.common_cancel()}
		</button>
		<button type="submit" form="client-form" class="btn btn-primary" disabled={submitting}>
			{#if submitting}
				<Spinner size={15} />
				{m.common_saving()}
			{:else}
				<Icon name="check" size={15} />
				{editing ? m.common_save_changes() : m.clients_register()}
			{/if}
		</button>
	{/snippet}
</Modal>
