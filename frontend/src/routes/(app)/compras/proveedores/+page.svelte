<script lang="ts">
	import { enhance } from '$app/forms';
	import { submit } from '$lib/ui/forms';
	import Icon from '$lib/ui/components/Icon.svelte';
	import PageHeader from '$lib/ui/components/PageHeader.svelte';
	import Modal from '$lib/ui/components/Modal.svelte';
	import Field from '$lib/ui/components/Field.svelte';
	import EmptyState from '$lib/ui/components/EmptyState.svelte';
	import { m } from '$lib/paraglide/messages.js';
	import type { Supplier } from '$lib/domain/types';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	/** `null` es el diálogo cerrado; un proveedor vacío, el alta. */
	let editando = $state<Supplier | null>(null);

	function vacio(): Supplier {
		return {
			id: 0,
			identification_type: null,
			identification: null,
			name: '',
			email: null,
			phone: null,
			payment_terms_days: 0,
			is_active: true
		};
	}

	/** Los cuatro de Hacienda. El valor va sin traducir: lo valida el backend. */
	function tipoRotulo(tipo: string | null | undefined): string {
		switch (tipo) {
			case '01':
				return m.suppliers_id_type_01();
			case '02':
				return m.suppliers_id_type_02();
			case '03':
				return m.suppliers_id_type_03();
			case '04':
				return m.suppliers_id_type_04();
			default:
				return m.suppliers_id_type_none();
		}
	}
</script>

<PageHeader title={m.suppliers_title()} description={m.suppliers_description()}>
	{#snippet actions()}
		<a href="/compras/cuentas-por-pagar" class="btn btn-ghost">
			<Icon name="wallet" size={15} />
			{m.purchases_tab_payables()}
		</a>
		<button type="button" class="btn btn-primary" onclick={() => (editando = vacio())}>
			<Icon name="plus" size={15} />
			{m.suppliers_new()}
		</button>
	{/snippet}
</PageHeader>

<div class="mb-3">
	<!-- Un enlace y no una casilla: así el estado vive en la URL y la vuelta
	     atrás del navegador funciona. -->
	<a
		href={data.inactivos ? '/compras/proveedores' : '/compras/proveedores?inactivos=1'}
		class="text-sm text-[var(--accent)] hover:underline"
	>
		{m.suppliers_show_inactive()}
	</a>
</div>

<div class="card overflow-hidden">
	<div class="table-wrap">
		<table class="data-table">
			<thead>
				<tr>
					<th scope="col">{m.suppliers_col_name()}</th>
					<th scope="col">{m.suppliers_col_identification()}</th>
					<th scope="col">{m.suppliers_col_contact()}</th>
					<th scope="col" class="num">{m.suppliers_col_terms()}</th>
					<th scope="col">{m.suppliers_col_status()}</th>
					<th scope="col"><span class="sr-only">{m.common_actions()}</span></th>
				</tr>
			</thead>
			<tbody>
				{#each data.suppliers as proveedor (proveedor.id)}
					<tr class:opacity-60={!proveedor.is_active}>
						<td class="font-medium text-[var(--text)]">{proveedor.name}</td>
						<td class="text-xs">
							{#if proveedor.identification}
								<span class="font-mono">{proveedor.identification}</span>
								<span class="block text-[var(--text-subtle)]">
									{tipoRotulo(proveedor.identification_type)}
								</span>
							{:else}
								<span class="text-[var(--text-subtle)]">—</span>
							{/if}
						</td>
						<td class="text-xs text-[var(--text-muted)]">
							{proveedor.email ?? ''}
							{#if proveedor.phone}
								<span class="block">{proveedor.phone}</span>
							{/if}
						</td>
						<td class="num tabular-nums">
							{proveedor.payment_terms_days > 0
								? m.suppliers_terms_days({ days: proveedor.payment_terms_days })
								: m.suppliers_terms_cash()}
						</td>
						<td>
							{#if proveedor.is_active}
								<span class="badge bg-[var(--positive-bg)] text-[var(--positive)]">
									<Icon name="check" size={11} />
									{m.suppliers_active()}
								</span>
							{:else}
								<span class="badge bg-[var(--surface-sunken)] text-[var(--text-muted)]">
									<Icon name="close" size={11} />
									{m.suppliers_inactive()}
								</span>
							{/if}
						</td>
						<td class="text-right">
							<button
								type="button"
								class="rounded-lg p-1.5 text-[var(--text-subtle)] hover:bg-[var(--surface-sunken)] hover:text-[var(--accent)]"
								onclick={() => (editando = { ...proveedor })}
								aria-label={m.suppliers_edit_action({ name: proveedor.name })}
							>
								<Icon name="edit" size={15} />
							</button>
						</td>
					</tr>
				{:else}
					<tr>
						<td colspan="6">
							<EmptyState
								icon="truck"
								title={m.suppliers_none()}
								description={m.suppliers_none_hint()}
							>
								<button type="button" class="btn btn-primary" onclick={() => (editando = vacio())}>
									<Icon name="plus" size={15} />
									{m.suppliers_new()}
								</button>
							</EmptyState>
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
</div>

<!-- ------------------------------------------------------------- ficha -->
<Modal
	open={editando !== null}
	title={editando?.id ? m.suppliers_form_edit() : m.suppliers_form_new()}
	size="lg"
	onclose={() => (editando = null)}
>
	{#if editando}
		<form
			id="form-proveedor"
			method="POST"
			action="?/guardar"
			use:enhance={submit({
				errorTitle: m.suppliers_save_failed(),
				onSuccess: () => (editando = null)
			})}
			class="grid gap-4 sm:grid-cols-2"
		>
			<input type="hidden" name="id" value={editando.id || ''} />

			<div class="sm:col-span-2">
				<Field label={m.suppliers_label_name()} name="name" bind:value={editando.name} required />
			</div>

			<div>
				<label class="label" for="tipo-id">{m.suppliers_label_id_type()}</label>
				<select
					id="tipo-id"
					name="identification_type"
					class="input"
					value={editando.identification_type ?? ''}
				>
					<!-- Sin identificación es un proveedor informal, no un error: el
					     que trae la fruta el martes no tiene cédula, y obligarlo haría
					     que alguien la invente. -->
					<option value="">{m.suppliers_id_type_none()}</option>
					<option value="01">{m.suppliers_id_type_01()}</option>
					<option value="02">{m.suppliers_id_type_02()}</option>
					<option value="03">{m.suppliers_id_type_03()}</option>
					<option value="04">{m.suppliers_id_type_04()}</option>
				</select>
			</div>
			<Field
				label={m.suppliers_label_identification()}
				name="identification"
				value={editando.identification ?? ''}
				icon="idcard"
			/>

			<Field
				label={m.suppliers_label_email()}
				name="email"
				value={editando.email ?? ''}
				icon="mail"
			/>
			<Field
				label={m.suppliers_label_phone()}
				name="phone"
				value={editando.phone ?? ''}
				icon="phone"
			/>

			<Field
				label={m.suppliers_label_terms()}
				name="payment_terms_days"
				value={String(editando.payment_terms_days)}
				inputmode="numeric"
				hint={m.suppliers_terms_hint()}
			/>

			{#if editando.id}
				<!-- Solo al editar: uno nuevo nace activo y una casilla desmarcable
				     en el alta solo sirve para dar de alta algo apagado. -->
				<div>
					<label class="flex cursor-pointer items-center gap-2 text-sm text-[var(--text)]">
						<input
							type="checkbox"
							name="is_active"
							class="h-4 w-4 accent-[var(--accent)]"
							checked={editando.is_active}
						/>
						{m.suppliers_label_active()}
					</label>
					<p class="mt-1 text-xs text-[var(--text-subtle)]">{m.suppliers_active_hint()}</p>
				</div>
			{/if}
		</form>
	{/if}

	{#snippet footer()}
		<button type="button" class="btn btn-ghost" onclick={() => (editando = null)}>
			{m.common_cancel()}
		</button>
		<button type="submit" form="form-proveedor" class="btn btn-primary">
			<Icon name="check" size={15} />
			{m.common_save()}
		</button>
	{/snippet}
</Modal>
