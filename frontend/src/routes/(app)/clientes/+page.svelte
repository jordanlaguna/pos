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
	import {
		EXEMPTION_INSTITUTIONS,
		EXEMPTION_OTHER,
		MAX_EXEMPTION_POINTS,
		SELLABLE_EXEMPTION_TYPES,
		exemptionNeedsArticle,
		exemptionVerifiedByHacienda
	} from '$lib/domain/exemptions';
	import { exemptionInstitutionLabel, exemptionTypeLabel } from '$lib/ui/exemptions';
	import type { Client } from '$lib/domain/types';
	import { m } from '$lib/paraglide/messages.js';
	import type { ActionData, PageData } from './$types';

	let { data, form }: { data: PageData; form: ActionData } = $props();

	let search = $state('');
	let modalOpen = $state(false);
	let editing = $state<Client | null>(null);
	let submitting = $state(false);

	/** Los ocho campos de la exoneración en blanco: «este cliente no tiene». */
	const SIN_EXONERACION = {
		exo_document_type: '',
		exo_document_number: '',
		exo_institution: '',
		exo_institution_other: '',
		exo_article: '',
		exo_subsection: '',
		exo_date: '',
		exo_points: ''
	};

	let f = $state({
		identification: '',
		name: '',
		last_name: '',
		second_name: '',
		email: '',
		telephone: '',
		address: '',
		register_date: '',
		// La exoneración (T-717, RN-78). Los ocho viajan siempre, aun vacíos:
		// es lo que permite quitársela a un cliente que la tenía.
		exo_document_type: '',
		exo_document_number: '',
		exo_institution: '',
		exo_institution_other: '',
		exo_article: '',
		exo_subsection: '',
		exo_date: '',
		exo_points: ''
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
			register_date: toDateInput(new Date()),
			...SIN_EXONERACION
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
			register_date: toDateInput(client.register_date),
			exo_document_type: client.exo_document_type ?? '',
			exo_document_number: client.exo_document_number ?? '',
			exo_institution: client.exo_institution ?? '',
			exo_institution_other: client.exo_institution_other ?? '',
			exo_article: client.exo_article == null ? '' : String(client.exo_article),
			exo_subsection: client.exo_subsection == null ? '' : String(client.exo_subsection),
			exo_date: client.exo_date ? toDateInput(client.exo_date) : '',
			exo_points: client.exo_points == null ? '' : String(client.exo_points)
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

		<!--
			La exoneración del cliente (T-717, RF-67, RN-78).

			**Se llena entera o se deja vacía**: los ocho campos viajan siempre, aun
			en blanco, y los ocho en blanco es cómo se le quita a un cliente que la
			tenía. El servidor los trata como uno solo.

			Los puntos son **puntos de tarifa**, no un porcentaje del precio: nueve
			sobre el 13 % dejan la línea pagando 4 %. No existe ninguna tarifa del
			9 %, así que guardar «4» sería guardar el resultado en vez del dato.
		-->
		<div class="sm:col-span-2 rounded-xl border border-[var(--border)] p-3">
			<p class="mb-1 text-sm font-medium text-[var(--text)]">{m.clients_exemption()}</p>
			<p class="mb-3 text-xs text-[var(--text-subtle)]">{m.clients_exemption_hint()}</p>

			<div class="grid gap-4 sm:grid-cols-2">
				<div>
					<label class="label" for="exo-type">{m.clients_label_exo_type()}</label>
					<select id="exo-type" name="exo_document_type" class="input" bind:value={f.exo_document_type}>
						<option value="">{m.clients_exemption_none()}</option>
						{#each SELLABLE_EXEMPTION_TYPES as tipo (tipo.code)}
							<option value={tipo.code}>{exemptionTypeLabel(tipo.code)}</option>
						{/each}
					</select>
				</div>

				{#if f.exo_document_type}
					<Field
						label={m.clients_label_exo_number()}
						name="exo_document_number"
						bind:value={f.exo_document_number}
						icon="receipt"
					/>

					<div>
						<label class="label" for="exo-inst">{m.clients_label_exo_institution()}</label>
						<select id="exo-inst" name="exo_institution" class="input" bind:value={f.exo_institution}>
							<option value=""></option>
							{#each EXEMPTION_INSTITUTIONS as institucion (institucion)}
								<option value={institucion}>{exemptionInstitutionLabel(institucion)}</option>
							{/each}
						</select>
					</div>

					{#if f.exo_institution === EXEMPTION_OTHER}
						<Field
							label={m.clients_label_exo_institution_other()}
							name="exo_institution_other"
							bind:value={f.exo_institution_other}
						/>
					{/if}

					{#if exemptionNeedsArticle(f.exo_document_type)}
						<Field
							label={m.clients_label_exo_article()}
							name="exo_article"
							bind:value={f.exo_article}
							inputmode="numeric"
						/>
						<Field
							label={m.clients_label_exo_subsection()}
							name="exo_subsection"
							bind:value={f.exo_subsection}
							inputmode="numeric"
						/>
					{/if}

					<Field
						label={m.clients_label_exo_date()}
						name="exo_date"
						type="date"
						bind:value={f.exo_date}
					/>
					<Field
						label={m.clients_label_exo_points()}
						name="exo_points"
						bind:value={f.exo_points}
						inputmode="decimal"
						hint={m.clients_exo_points_hint()}
						max={MAX_EXEMPTION_POINTS}
					/>
				{/if}
			</div>

			{#if exemptionVerifiedByHacienda(f.exo_document_type)}
				<p class="mt-3 flex items-start gap-1.5 text-xs text-[var(--warning)]">
					<Icon name="alert" size={13} />
					{m.clients_exo_verified()}
				</p>
			{/if}
		</div>
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
