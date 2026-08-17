<script lang="ts">
	import { enhance } from '$app/forms';
	import { page } from '$app/state';
	import Field from '$lib/ui/components/Field.svelte';
	import Icon from '$lib/ui/components/Icon.svelte';
	import Spinner from '$lib/ui/components/Spinner.svelte';
	import { theme } from '$lib/ui/stores/theme.svelte';
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

<svelte:head><title>Iniciar sesión · VentaSys</title></svelte:head>

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
			aria-label="Cambiar entre tema claro y oscuro"
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
					<p class="text-xs text-white/70">Sistema de punto de venta</p>
				</div>
			</div>

			<div class="relative my-auto max-w-md pt-10">
				<h2 class="text-4xl font-bold tracking-tight">
					Cobrá rápido.<br />Cuadrá sin sustos.
				</h2>
				<p class="mt-4 text-[0.95rem] leading-relaxed text-white/80">
					Ventas con escáner, control de inventario, arqueo de caja por turno, devoluciones
					con reposición de stock y reportes en vivo.
				</p>

				<ul class="mt-8 space-y-3 text-sm text-white/80">
					{#each ['Escáner de código de barras y atajos de teclado', 'Corte Z con diferencia de caja', 'Devoluciones que regresan el stock', 'Reportes de ventas y productos más vendidos'] as feature}
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
				<h1 class="text-3xl font-bold tracking-tight text-[var(--text)]">Iniciar sesión</h1>
				<p class="mt-1.5 mb-7 text-sm text-[var(--text-muted)]">
					Ingresá con tu correo para abrir la caja.
				</p>

				{#if page.url.searchParams.has('registrado') && !form?.errors?.form}
					<div
						class="mb-4 flex items-start gap-2 rounded-lg border border-[var(--positive)] bg-[var(--positive-bg)] p-3 text-sm text-[var(--positive)]"
						role="status"
					>
						<Icon name="check" size={16} class="mt-0.5 shrink-0" />
						<span>Cuenta creada. Ya podés iniciar sesión con tu correo.</span>
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
						label="Correo electrónico"
						name="email"
						type="email"
						bind:value={email}
						icon="mail"
						placeholder="usuario@ventasys.cr"
						autocomplete="username"
						required
						error={form?.errors?.email}
					/>

					<Field
						label="Contraseña"
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
							aria-label={showPassword ? 'Ocultar contraseña' : 'Mostrar contraseña'}
						>
							<Icon name={showPassword ? 'eyeoff' : 'eye'} size={15} />
						</button>
					</Field>

					<button type="submit" class="btn btn-primary w-full" disabled={submitting}>
						{#if submitting}
							<Spinner size={15} />
							Entrando…
						{:else}
							<Icon name="logout" size={15} />
							Entrar
						{/if}
					</button>
				</form>

				{#if data.demo}
					<div class="mt-6 rounded-lg border border-dashed border-[var(--border)] p-3">
						<p class="mb-2 text-xs font-semibold text-[var(--text-subtle)]">
							Modo demostración — datos de ejemplo
						</p>
						<div class="flex flex-wrap gap-2">
							<button
								type="button"
								class="btn btn-ghost px-2.5 py-1 text-xs"
								onclick={() => fillDemo('admin@ventasys.cr')}
							>
								Administrador
							</button>
							<button
								type="button"
								class="btn btn-ghost px-2.5 py-1 text-xs"
								onclick={() => fillDemo('cajero@ventasys.cr')}
							>
								Cajero
							</button>
						</div>
					</div>
				{/if}

				<p class="mt-6 text-center text-sm text-[var(--text-muted)]">
					¿No tenés cuenta?
					<a href="/registro" class="font-semibold text-[var(--accent)] hover:underline">
						Registrate
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
