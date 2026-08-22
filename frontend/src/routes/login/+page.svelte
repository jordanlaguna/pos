<script lang="ts">
	import { enhance } from '$app/forms';
	import { page } from '$app/state';
	import Field from '$lib/ui/components/Field.svelte';
	import Icon from '$lib/ui/components/Icon.svelte';
	import Spinner from '$lib/ui/components/Spinner.svelte';
	import { theme } from '$lib/ui/stores/theme.svelte';
	import { m } from '$lib/paraglide/messages.js';
	import type { ActionData, PageData } from './$types';

	let { data, form }: { data: PageData; form: ActionData } = $props();

	// Valor inicial a propósito: tras un intento fallido el campo conserva lo que
	// el usuario escribió, y a partir de ahí manda el binding, no la acción.
	// svelte-ignore state_referenced_locally
	let email = $state(form?.email ?? '');
	let password = $state('');
	let showPassword = $state(false);
	let submitting = $state(false);

	function fillDemo(user: string) {
		email = user;
		password = user.startsWith('admin') ? 'admin123' : 'cajero123';
	}
</script>

<svelte:head><title>{m.auth_sign_in()} · VentaSys</title></svelte:head>

<main class="grid min-h-full place-items-center p-4 sm:p-8">
	<!--
		Tarjeta centrada, no dos mitades a sangre. El POS se usa en pantallas muy
		distintas —una caja de 1366 y un monitor de 27"—, y a pantalla completa el
		formulario quedaba solo, empujado contra el borde derecho. Acá la pieza
		mantiene su tamaño y el navegador solo decide cuánto aire le deja alrededor.
	-->
	<div
		class="relative grid w-full max-w-[68rem] overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface-raised)] shadow-xl lg:min-h-[36rem] lg:grid-cols-[1.1fr_1fr]"
	>
		<!--
			Marca y tema van anclados a las esquinas de la tarjeta, no dentro del
			bloque del formulario: ese bloque va centrado vertical, y arrastrar el
			botón de tema con él lo dejaba flotando a media altura, sin relación con
			nada. En pantalla grande la marca ya vive en el panel de la izquierda.
		-->
		<div class="absolute top-5 left-5 z-10 flex items-center gap-2.5 lg:hidden">
			<span
				class="grid h-9 w-9 place-items-center rounded-lg bg-[var(--accent)] text-[var(--accent-text)]"
			>
				<Icon name="cart" size={18} />
			</span>
			<span class="text-lg font-bold text-[var(--text)]">VentaSys</span>
		</div>

		<button
			type="button"
			class="absolute top-5 right-5 z-10 rounded-lg border border-[var(--border)] bg-[var(--surface-raised)] p-2 text-[var(--text-muted)] hover:bg-[var(--surface-sunken)]"
			onclick={() => theme.toggle()}
			aria-label={m.nav_toggle_theme()}
		>
			<Icon name={theme.current === 'dark' ? 'sun' : 'moon'} size={16} />
		</button>

		<!-- Panel de marca. Se oculta en pantallas de caja pequeñas. -->
		<aside class="relative hidden flex-col overflow-hidden p-12 text-white lg:flex">
			<div
				class="pointer-events-none absolute -top-24 -right-24 h-96 w-96 rounded-full bg-white/10 blur-3xl"
			></div>

			<div class="relative flex items-center gap-3">
				<span class="grid h-11 w-11 place-items-center rounded-xl bg-white/15">
					<Icon name="cart" size={22} />
				</span>
				<div>
					<p class="text-lg font-bold">VentaSys</p>
					<p class="text-xs text-white/70">{m.auth_tagline()}</p>
				</div>
			</div>

			<div class="relative my-auto max-w-md pt-10">
				<h2 class="text-4xl font-bold tracking-tight">
					{m.auth_pitch_1()}<br />{m.auth_pitch_2()}
				</h2>
				<p class="mt-4 text-[0.95rem] leading-relaxed text-white/80">
					{m.auth_pitch_body()}
				</p>

				<ul class="mt-8 space-y-3 text-sm text-white/80">
					{#each [m.auth_feature_scanner(), m.auth_feature_z(), m.auth_feature_returns(), m.auth_feature_reports()] as feature}
						<li class="flex items-start gap-2.5">
							<Icon
								name="check"
								size={16}
								class="mt-0.5 shrink-0 text-[var(--brand-check)]"
							/>
							<span>{feature}</span>
						</li>
					{/each}
				</ul>
			</div>
		</aside>

		<!-- Formulario -->
		<div class="flex items-center justify-center px-6 pt-24 pb-12 sm:px-10 lg:px-12 lg:py-16">
			<div class="w-full max-w-sm">
				<h1 class="text-3xl font-bold tracking-tight text-[var(--text)]">{m.auth_sign_in()}</h1>
				<p class="mt-1.5 mb-7 text-sm text-[var(--text-muted)]">
					{m.auth_sign_in_hint()}
				</p>

				{#if page.url.searchParams.has('registrado') && !form?.errors?.form}
					<div
						class="mb-4 flex items-start gap-2 rounded-lg border border-[var(--positive)] bg-[var(--positive-bg)] p-3 text-sm text-[var(--positive)]"
						role="status"
					>
						<Icon name="check" size={16} class="mt-0.5 shrink-0" />
						<span>{m.auth_account_created()}</span>
					</div>
				{/if}

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
							password = '';
						};
					}}
					class="space-y-4"
				>
					<Field
						label={m.auth_email()}
						name="email"
						type="email"
						bind:value={email}
						icon="mail"
						placeholder={m.auth_email_placeholder()}
						autocomplete="username"
						required
						error={form?.errors?.email}
					/>

					<Field
						label={m.auth_password()}
						name="password"
						type={showPassword ? 'text' : 'password'}
						bind:value={password}
						icon="lock"
						placeholder="••••••••"
						autocomplete="current-password"
						required
						error={form?.errors?.password}
					>
						<button
							type="button"
							class="rounded p-1.5 text-[var(--text-subtle)] hover:text-[var(--text)]"
							onclick={() => (showPassword = !showPassword)}
							aria-label={showPassword ? m.auth_hide_password() : m.auth_show_password()}
						>
							<Icon name={showPassword ? 'eyeoff' : 'eye'} size={15} />
						</button>
					</Field>

					<button type="submit" class="btn btn-primary w-full" disabled={submitting}>
						{#if submitting}
							<Spinner size={15} />
							{m.auth_entering()}
						{:else}
							<Icon name="logout" size={15} />
							{m.auth_enter()}
						{/if}
					</button>
				</form>

				{#if data.demo}
					<div class="mt-6 rounded-lg border border-dashed border-[var(--border)] p-3">
						<p class="mb-2 text-xs font-semibold text-[var(--text-subtle)]">
							{m.auth_demo_mode()}
						</p>
						<div class="flex flex-wrap gap-2">
							<button
								type="button"
								class="btn btn-ghost px-2.5 py-1 text-xs"
								onclick={() => fillDemo('admin@ventasys.cr')}
							>
								{m.role_admin()}
							</button>
							<button
								type="button"
								class="btn btn-ghost px-2.5 py-1 text-xs"
								onclick={() => fillDemo('cajero@ventasys.cr')}
							>
								{m.role_cashier()}
							</button>
						</div>
					</div>
				{/if}

				<p class="mt-6 text-center text-sm text-[var(--text-muted)]">
					{m.auth_no_account()}
					<a href="/registro" class="font-semibold text-[var(--accent)] hover:underline">
						{m.auth_register_link()}
					</a>
				</p>
			</div>
		</div>
	</div>
</main>

<style>
	aside {
		background: linear-gradient(150deg, #0e7490, #083344);
		--brand-check: #67e8f9;
	}
</style>
