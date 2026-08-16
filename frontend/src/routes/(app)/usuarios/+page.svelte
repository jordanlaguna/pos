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
	import { formatDate, fullName, initials, toDateInput } from '$lib/format';
	import type { Person } from '$lib/types';
	import type { ActionData, PageData } from './$types';

	let { data, form }: { data: PageData; form: ActionData } = $props();

	let search = $state('');
	let modalOpen = $state(false);
	let editing = $state<Person | null>(null);
	let submitting = $state(false);

	let f = $state({
		name: '',
		lastName: '',
		secondName: '',
		identification: '',
		telephone: '',
		birth_date: '',
		email: ''
	});

	const filtered = $derived.by(() => {
		const term = search.trim().toLowerCase();
		if (!term) return data.persons;
		return data.persons.filter(
			(p) =>
				fullName(p).toLowerCase().includes(term) ||
				p.email.toLowerCase().includes(term) ||
				p.identification.toLowerCase().includes(term)
		);
	});

	function openEdit(person: Person) {
		editing = person;
		f = {
			name: person.name,
			lastName: person.lastName,
			secondName: person.secondName,
			identification: person.identification,
			telephone: person.telephone,
			birth_date: toDateInput(person.birth_date),
			email: person.email
		};
		modalOpen = true;
	}

</script>

<PageHeader
	title="Usuarios"
	description="Personas registradas y su nivel de acceso al sistema."
/>

<div
	class="mb-4 flex items-start gap-2 rounded-lg border border-[var(--border)] bg-[var(--surface-raised)] p-3 text-xs text-[var(--text-muted)]"
>
	<Icon name="info" size={14} class="mt-0.5 shrink-0 text-[var(--info)]" />
	<p>
		<strong class="text-[var(--text)]">Administrador</strong> gestiona inventario, usuarios y
		reportes. <strong class="text-[var(--text)]">Cajero</strong> solo vende, cobra y consulta
		facturas. Las cuentas nuevas se crean desde la pantalla de registro.
	</p>
</div>

<div class="card mb-4 p-3">
	<label class="label" for="usuario-buscar">Buscar</label>
	<div class="relative">
		<span
			class="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-[var(--text-subtle)]"
		>
			<Icon name="search" size={15} />
		</span>
		<input
			id="usuario-buscar"
			bind:value={search}
			type="search"
			placeholder="Nombre, correo o cédula…"
			class="input pl-9"
		/>
	</div>
</div>

<div class="card overflow-hidden">
	<div class="table-wrap">
		<table class="data-table">
			<thead>
				<tr>
					<th scope="col">Usuario</th>
					<th scope="col">Cédula</th>
					<th scope="col">Teléfono</th>
					<th scope="col">Nacimiento</th>
					<th scope="col">Rol</th>
					<th scope="col"><span class="sr-only">Acciones</span></th>
				</tr>
			</thead>
			<tbody>
				{#each filtered as person (person.id_person)}
					{@const role = person.role ?? 'cajero'}
					{@const isMe = person.id_user === data.user.id_user}
					<tr>
						<td>
							<div class="flex items-center gap-2.5">
								<span
									class="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-[var(--surface-sunken)] text-[10px] font-bold text-[var(--text-muted)]"
								>
									{initials(fullName(person))}
								</span>
								<div class="min-w-0">
									<p class="truncate font-medium text-[var(--text)]">
										{fullName(person)}
										{#if isMe}
											<span class="text-xs font-normal text-[var(--text-subtle)]">(vos)</span>
										{/if}
									</p>
									<p class="truncate text-xs text-[var(--text-subtle)]">{person.email}</p>
								</div>
							</div>
						</td>
						<td class="tabular-nums">{person.identification}</td>
						<td class="tabular-nums">{person.telephone}</td>
						<td class="whitespace-nowrap text-xs">{formatDate(person.birth_date)}</td>
						<td>
							<form method="POST" action="?/cambiarRol" use:enhance>
								<input type="hidden" name="id_user" value={person.id_user} />
								<select
									name="role"
									value={role}
									class="input w-32 py-1 text-xs"
									disabled={isMe}
									title={isMe ? 'No podés cambiar tu propio rol.' : 'Cambiar rol'}
									onchange={(e) => e.currentTarget.form?.requestSubmit()}
									aria-label="Rol de {fullName(person)}"
								>
									<option value="admin">Administrador</option>
									<option value="cajero">Cajero</option>
								</select>
							</form>
						</td>
						<td class="text-right">
							<button
								type="button"
								class="rounded-lg p-1.5 text-[var(--text-subtle)] hover:bg-[var(--surface-sunken)] hover:text-[var(--accent)]"
								onclick={() => openEdit(person)}
								aria-label="Editar {fullName(person)}"
							>
								<Icon name="edit" size={15} />
							</button>
						</td>
					</tr>
				{:else}
					<tr>
						<td colspan="6">
							<EmptyState
								icon="user"
								title="Sin usuarios"
								description={search ? 'Nadie coincide con la búsqueda.' : undefined}
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
	title="Editar usuario"
	description={editing ? fullName(editing) : undefined}
	busy={submitting}
	onclose={() => (modalOpen = false)}
>
	<form
		id="user-form"
		method="POST"
		action="?/actualizar"
		use:enhance={submit({
			onSuccess: () => (modalOpen = false),
			setBusy: (v) => (submitting = v)
		})}
		class="grid gap-4 sm:grid-cols-2"
	>
		<input type="hidden" name="id_person" value={editing?.id_person ?? ''} />

		<Field
			label="Nombre"
			name="name"
			bind:value={f.name}
			icon="user"
			required
			error={form?.errors?.name}
		/>
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
			label="Primer apellido"
			name="lastName"
			bind:value={f.lastName}
			required
			error={form?.errors?.lastName}
		/>
		<Field
			label="Segundo apellido"
			name="secondName"
			bind:value={f.secondName}
			required
			error={form?.errors?.secondName}
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
			label="Fecha de nacimiento"
			name="birth_date"
			type="date"
			bind:value={f.birth_date}
			required
			error={form?.errors?.birth_date}
		/>
		<Field
			label="Correo electrónico"
			name="email"
			type="email"
			bind:value={f.email}
			icon="mail"
			required
			hint="Es también el usuario con el que inicia sesión."
			error={form?.errors?.email}
			class="sm:col-span-2"
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
		<button type="submit" form="user-form" class="btn btn-primary" disabled={submitting}>
			{#if submitting}
				<Spinner size={15} />
				Guardando…
			{:else}
				<Icon name="check" size={15} />
				Guardar cambios
			{/if}
		</button>
	{/snippet}
</Modal>
