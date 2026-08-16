<script lang="ts">
	import { enhance } from '$app/forms';
	import Field from '$lib/components/Field.svelte';
	import Icon from '$lib/components/Icon.svelte';
	import Spinner from '$lib/components/Spinner.svelte';
	import type { ActionData } from './$types';

	let { form }: { form: ActionData } = $props();

	const v = $derived(form?.values);
	let submitting = $state(false);
</script>

<svelte:head><title>Crear cuenta · VentaSys</title></svelte:head>

<main class="flex min-h-full items-center justify-center p-6">
	<div class="w-full max-w-2xl">
		<a
			href="/login"
			class="mb-6 inline-flex items-center gap-1.5 text-sm font-semibold text-[var(--text-muted)] hover:text-[var(--text)]"
		>
			<Icon name="back" size={15} />
			Volver al inicio de sesión
		</a>

		<div class="card p-6 sm:p-8">
			<div class="mb-6 flex items-center gap-3">
				<span
					class="grid h-11 w-11 place-items-center rounded-xl bg-[var(--accent)] text-[var(--accent-text)]"
				>
					<Icon name="user" size={20} />
				</span>
				<div>
					<h1 class="text-xl font-bold tracking-tight text-[var(--text)]">Crear cuenta</h1>
					<p class="text-sm text-[var(--text-muted)]">
						Se registra la persona y su usuario de acceso.
					</p>
				</div>
			</div>

			{#if form?.errors?.form}
				<div
					class="mb-4 flex items-start gap-2 rounded-lg border border-[var(--negative)] bg-[var(--negative-bg)] p-3 text-sm text-[var(--negative)]"
					role="alert"
				>
					<Icon name="alert" size={16} class="mt-0.5 shrink-0" />
					<span>{form.errors.form}</span>
				</div>
			{/if}

			<form
				method="POST"
				use:enhance={() => {
					submitting = true;
					return async ({ update }) => {
						await update({ reset: false });
						submitting = false;
					};
				}}
				class="grid gap-4 sm:grid-cols-2"
			>
				<Field
					label="Nombre"
					name="name"
					value={v?.name ?? ''}
					icon="user"
					required
					error={form?.errors?.name}
				/>
				<Field
					label="Cédula"
					name="identification"
					value={v?.identification ?? ''}
					icon="idcard"
					inputmode="numeric"
					required
					error={form?.errors?.identification}
				/>
				<Field
					label="Primer apellido"
					name="lastName"
					value={v?.lastName ?? ''}
					required
					error={form?.errors?.lastName}
				/>
				<Field
					label="Segundo apellido"
					name="secondName"
					value={v?.secondName ?? ''}
					required
					error={form?.errors?.secondName}
				/>
				<Field
					label="Teléfono"
					name="telephone"
					value={v?.telephone ?? ''}
					icon="phone"
					inputmode="tel"
					required
					error={form?.errors?.telephone}
				/>
				<Field
					label="Fecha de nacimiento"
					name="birth_date"
					type="date"
					value={v?.birth_date ?? ''}
					required
					error={form?.errors?.birth_date}
				/>

				<Field
					label="Correo electrónico"
					name="email"
					type="email"
					value={v?.email ?? ''}
					icon="mail"
					autocomplete="username"
					required
					error={form?.errors?.email}
					class="sm:col-span-2"
				/>

				<Field
					label="Contraseña"
					name="password"
					type="password"
					icon="lock"
					autocomplete="new-password"
					required
					hint="Mínimo 6 caracteres."
					error={form?.errors?.password}
				/>
				<Field
					label="Confirmar contraseña"
					name="confirm"
					type="password"
					icon="lock"
					autocomplete="new-password"
					required
					error={form?.errors?.confirm}
				/>

				<div class="flex justify-end gap-2 sm:col-span-2">
					<a href="/login" class="btn btn-ghost">Cancelar</a>
					<button type="submit" class="btn btn-primary" disabled={submitting}>
						{#if submitting}
							<Spinner size={15} />
							Creando…
						{:else}
							<Icon name="check" size={15} />
							Crear cuenta
						{/if}
					</button>
				</div>
			</form>
		</div>
	</div>
</main>
