<script lang="ts">
	import { enhance } from '$app/forms';
	import { submit } from '$lib/forms';
	import Icon from '$lib/components/Icon.svelte';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import Modal from '$lib/components/Modal.svelte';
	import Field from '$lib/components/Field.svelte';
	import EmptyState from '$lib/components/EmptyState.svelte';
	import Spinner from '$lib/components/Spinner.svelte';
	import { toasts } from '$lib/stores/toast.svelte';
	import { formatDate, fullName, toDateInput } from '$lib/format';
	import type { Client } from '$lib/types';
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

<PageHeader title="Clientes" description="Registro de clientes del negocio.">
	{#snippet actions()}
		<button type="button" class="btn btn-primary" onclick={openCreate}>
			<Icon name="plus" size={15} />
			Nuevo cliente
		</button>
	{/snippet}
</PageHeader>

<div class="card mb-4 p-3">
	<label class="label" for="cliente-buscar">Buscar</label>
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
			placeholder="Nombre, cédula, correo o teléfono…"
			class="input pl-9"
		/>
	</div>
</div>

<div class="card overflow-hidden">
	<div class="table-wrap">
		<table class="data-table">
			<thead>
				<tr>
					<th scope="col">Cliente</th>
					<th scope="col">Cédula</th>
					<th scope="col">Contacto</th>
					<th scope="col">Dirección</th>
					<th scope="col">Registro</th>
					<th scope="col"><span class="sr-only">Acciones</span></th>
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
								aria-label="Editar {fullName(client)}"
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
								title="Sin clientes"
								description={search
									? 'Ningún cliente coincide con la búsqueda.'
									: 'Registrá clientes para asociarlos a las facturas.'}
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
	title={editing ? 'Editar cliente' : 'Nuevo cliente'}
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
			label="Cédula"
			name="identification"
			bind:value={f.identification}
			icon="idcard"
			inputmode="numeric"
			required
			error={form?.errors?.identification}
		/>
		<Field
			label="Nombre"
			name="name"
			bind:value={f.name}
			icon="user"
			required
			error={form?.errors?.name}
		/>
		<Field
			label="Primer apellido"
			name="last_name"
			bind:value={f.last_name}
			required
			error={form?.errors?.last_name}
		/>
		<Field
			label="Segundo apellido"
			name="second_name"
			bind:value={f.second_name}
			required
			error={form?.errors?.second_name}
		/>
		<Field
			label="Correo electrónico"
			name="email"
			type="email"
			bind:value={f.email}
			icon="mail"
			required
			error={form?.errors?.email}
		/>
		<Field
			label="Teléfono"
			name="telephone"
			bind:value={f.telephone}
			icon="phone"
			inputmode="tel"
			required
			error={form?.errors?.telephone}
		/>
		<Field
			label="Dirección"
			name="address"
			bind:value={f.address}
			required
			error={form?.errors?.address}
			class="sm:col-span-2"
		/>
		<Field
			label="Fecha de registro"
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
			Cancelar
		</button>
		<button type="submit" form="client-form" class="btn btn-primary" disabled={submitting}>
			{#if submitting}
				<Spinner size={15} />
				Guardando…
			{:else}
				<Icon name="check" size={15} />
				{editing ? 'Guardar cambios' : 'Registrar cliente'}
			{/if}
		</button>
	{/snippet}
</Modal>
