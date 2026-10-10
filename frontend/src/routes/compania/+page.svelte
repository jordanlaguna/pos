<script lang="ts">
	import { enhance } from '$app/forms';
	import Icon from '$lib/ui/components/Icon.svelte';
	import Spinner from '$lib/ui/components/Spinner.svelte';
	import { cart } from '$lib/ui/stores/cart.svelte';
	import { theme } from '$lib/ui/stores/theme.svelte';
	import { m } from '$lib/paraglide/messages.js';
	import { roleLabel, roleLabelLower } from '$lib/ui/messages';
	import type { CompanyOption } from '$lib/domain/types';
	import type { ActionData, PageData } from './$types';

	let { data, form }: { data: PageData; form: ActionData } = $props();

	let enviando = $state<number | null>(null);

	/**
	 * El motivo llega como código y la frase se arma acá (RN-30).
	 *
	 * El backend no escribe texto para personas: no sabe en qué idioma está la
	 * pantalla ni si quien lee es el dueño o un cajero. Cuando exista F8 esto se
	 * vuelve una llamada al catálogo de traducciones y la estructura no cambia.
	 */
	function motivo(c: CompanyOption): string {
		switch (c.motivo) {
			case 'invitacion_pendiente':
				return m.company_reason_pending_invite();
			case 'suspendida':
				return m.company_reason_suspended();
			case 'cancelada':
				return m.company_reason_cancelled();
			default:
				return m.company_reason_unavailable();
		}
	}

	/** El estado, dicho como se le dice a una persona. */
	function estado(c: CompanyOption): string {
		switch (c.estado) {
			case 'prueba':
				return m.company_status_trial();
			case 'activa':
				return m.company_status_current();
			case 'vencida':
				return m.company_status_overdue();
			case 'suspendida':
				return m.company_status_suspended();
			case 'cancelada':
				return m.company_status_cancelled();
		}
	}

	const disponibles = $derived(data.companies.filter((c) => c.puede_entrar));

	/** Las cajas que hay que ofrecer: más de una activa (RN-102); si no, ninguna. */
	function cajas(c: CompanyOption) {
		const lista = c.terminals ?? [];
		return lista.length > 1 ? lista : [];
	}

	function esLaActual(c: CompanyOption, terminalId: number): boolean {
		return c.id === data.actual && terminalId === data.actualTerminal;
	}
	const invitaciones = $derived(data.companies.filter((c) => c.pendiente));
	const bloqueadas = $derived(data.companies.filter((c) => !c.puede_entrar && !c.pendiente));
</script>

<svelte:head><title>{m.company_pick_tab()} · VentaSys</title></svelte:head>

<main class="grid min-h-full place-items-center p-4 sm:p-8">
	<div
		class="relative w-full max-w-2xl overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface-raised)] p-6 shadow-xl sm:p-10"
	>
		<button
			type="button"
			class="absolute top-4 right-4 rounded-lg p-2 text-[var(--text-muted)] hover:bg-[var(--surface-sunken)]"
			onclick={() => theme.toggle()}
			title={m.nav_toggle_theme()}
			aria-label={m.nav_toggle_theme_short()}
		>
			<Icon name={theme.current === 'dark' ? 'sun' : 'moon'} size={18} />
		</button>

		<h1 class="text-2xl font-semibold text-[var(--text)]">{m.company_pick_title()}</h1>
		<p class="mt-1 text-sm text-[var(--text-muted)]">
			{m.company_access_count({ count: data.companies.length })}
		</p>

		{#if form?.hecho}
			<p
				class="mt-4 rounded-lg border border-[var(--border)] bg-[var(--surface-sunken)] px-4 py-3 text-sm text-[var(--text)]"
				role="status"
			>
				{form.hecho}
			</p>
		{/if}

		{#if form?.message}
			<p
				class="mt-4 rounded-lg border border-[var(--negative)] bg-[var(--negative-bg)] px-4 py-3 text-sm text-[var(--negative)]"
				role="alert"
			>
				{form.message}
			</p>
		{/if}

		<div class="mt-6 grid gap-3">
			{#each disponibles as c (c.id)}
				{#if cajas(c).length}
					<!--
						Varias cajas (RN-102): se elige la compañía y la caja en el mismo
						paso. Cada caja es un envío aparte, con la compañía escondida, para
						que elegir siga siendo un clic.
					-->
					<div
						class="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-4 py-4"
						data-testid="company-terminals"
					>
						<div class="flex items-center gap-4">
							<span
								class="grid size-10 shrink-0 place-items-center rounded-lg bg-[var(--accent-soft)] text-[var(--accent-text)]"
							>
								<Icon name="home" size={20} />
							</span>
							<span class="min-w-0 flex-1">
								<span class="block truncate font-medium text-[var(--text)]">{c.nombre}</span>
								<span class="block text-xs text-[var(--text-muted)]">
									{m.company_row_detail({
										affiliate: c.afiliado,
										company: c.compania,
										status: estado(c),
										role: roleLabel(c.rol)
									})}
								</span>
							</span>
						</div>
						<p class="mt-3 text-xs font-medium text-[var(--text-muted)]">{m.company_terminal_pick()}</p>
						<div class="mt-2 grid gap-2 sm:grid-cols-2">
							{#each cajas(c) as t (t.id)}
								<form
									method="POST"
									action="?/elegir"
									use:enhance={() => {
										enviando = c.id;
										cart.reset();
										return async ({ update }) => {
											await update();
											enviando = null;
										};
									}}
								>
									<input type="hidden" name="company_id" value={c.id} />
									<input type="hidden" name="terminal_id" value={t.id} />
									<button
										type="submit"
										disabled={enviando !== null}
										aria-label={m.company_terminal_option({ company: c.nombre, terminal: t.nombre })}
										class="flex w-full items-center gap-3 rounded-lg border px-3 py-2.5 text-left transition hover:border-[var(--accent)] hover:bg-[var(--surface-sunken)] disabled:opacity-60 {esLaActual(c, t.id)
											? 'border-[var(--accent)]'
											: 'border-[var(--border)]'}"
										data-terminal={t.codigo}
									>
										<span class="min-w-0 flex-1">
											<span class="block truncate text-sm font-medium text-[var(--text)]">{t.nombre}</span>
											<span class="block text-xs text-[var(--text-muted)]">
												{m.company_terminal_row({ branch: t.branch_codigo, code: t.codigo, name: t.branch_nombre })}
											</span>
										</span>
										{#if esLaActual(c, t.id)}
											<span class="shrink-0 text-xs text-[var(--text-muted)]">{m.company_current()}</span>
										{/if}
										<Icon name="forward" size={16} />
									</button>
								</form>
							{/each}
						</div>
					</div>
				{:else}
				<form
					method="POST"
					action="?/elegir"
					use:enhance={() => {
						enviando = c.id;
						/*
						 * Se vacía el carrito ANTES de que el servidor responda
						 * (RN-27). Las ventas en espera viven en sessionStorage,
						 * que el servidor no puede tocar; si esto no ocurriera,
						 * al entrar a la otra compañía la pantalla de ventas
						 * aparecería con artículos que no son de ese negocio.
						 */
						cart.reset();
						return async ({ update }) => {
							await update();
							enviando = null;
						};
					}}
				>
					<input type="hidden" name="company_id" value={c.id} />
					<button
						type="submit"
						disabled={enviando !== null}
						class="flex w-full items-center gap-4 rounded-xl border border-[var(--border)] bg-[var(--surface)] px-4 py-4 text-left transition hover:border-[var(--accent)] hover:bg-[var(--surface-sunken)] disabled:opacity-60"
					>
						<span
							class="grid size-10 shrink-0 place-items-center rounded-lg bg-[var(--accent-soft)] text-[var(--accent-text)]"
						>
							<Icon name="home" size={20} />
						</span>
						<span class="min-w-0 flex-1">
							<span class="block truncate font-medium text-[var(--text)]">{c.nombre}</span>
							<span class="block text-xs text-[var(--text-muted)]">
								{m.company_row_detail({
									affiliate: c.afiliado,
									company: c.compania,
									status: estado(c),
									role: roleLabel(c.rol)
								})}
							</span>
						</span>
						{#if c.id === data.actual}
							<span class="shrink-0 text-xs text-[var(--text-muted)]">{m.company_current()}</span>
						{/if}
						{#if enviando === c.id}
							<Spinner size={16} />
						{:else}
							<Icon name="forward" size={18} />
						{/if}
					</button>
				</form>
				{/if}
			{/each}
		</div>

		{#if invitaciones.length}
			<!--
				Invitaciones pendientes (T-229). Un administrador puede sumar a su
				compañía a alguien que ya tiene cuenta —es la única forma de armar el
				caso del contador— pero no puede darle acceso a su nombre. Hasta que
				no se acepte, la membresía existe y no abre nada.
			-->
			<h2 class="mt-8 text-sm font-medium text-[var(--text-muted)]">
				{m.company_invited({ count: invitaciones.length })}
			</h2>
			<div class="mt-3 grid gap-3">
				{#each invitaciones as c (c.id)}
					<div
						class="flex flex-wrap items-center gap-4 rounded-xl border border-[var(--accent)] bg-[var(--accent-soft)] px-4 py-4"
					>
						<span class="min-w-0 flex-1">
							<span class="block truncate font-medium text-[var(--text)]">{c.nombre}</span>
							<span class="block text-xs text-[var(--text-muted)]">
								{m.company_invite_detail({
									affiliate: c.afiliado,
									company: c.compania,
									role: roleLabelLower(c.rol)
								})}
							</span>
						</span>
						<span class="flex shrink-0 gap-2">
							<form method="POST" action="?/invitacion" use:enhance>
								<input type="hidden" name="company_id" value={c.id} />
								<input type="hidden" name="accion" value="aceptar" />
								<button
									type="submit"
									class="rounded-lg bg-[var(--accent)] px-3 py-1.5 text-xs font-medium text-[var(--accent-text)] hover:opacity-90"
								>
									{m.company_accept()}
								</button>
							</form>
							<form method="POST" action="?/invitacion" use:enhance>
								<input type="hidden" name="company_id" value={c.id} />
								<input type="hidden" name="accion" value="rechazar" />
								<button
									type="submit"
									class="rounded-lg border border-[var(--border)] px-3 py-1.5 text-xs text-[var(--text-muted)] hover:bg-[var(--surface-sunken)]"
								>
									{m.company_reject()}
								</button>
							</form>
						</span>
					</div>
				{/each}
			</div>
		{/if}

		{#if bloqueadas.length}
			<!--
				Las bloqueadas se muestran, no se esconden (RF-27). Una compañía que
				simplemente desaparece de la lista se lee como «me borraron la
				cuenta», y quien no puede entrar tiene que saber por qué y qué hacer.
			-->
			<h2 class="mt-8 text-sm font-medium text-[var(--text-muted)]">{m.company_no_access()}</h2>
			<div class="mt-3 grid gap-3">
				{#each bloqueadas as c (c.id)}
					<div
						class="flex items-start gap-4 rounded-xl border border-dashed border-[var(--border)] px-4 py-4 opacity-80"
					>
						<span
							class="grid size-10 shrink-0 place-items-center rounded-lg bg-[var(--surface-sunken)] text-[var(--text-muted)]"
						>
							<Icon name="lock" size={18} />
						</span>
						<span class="min-w-0 flex-1">
							<span class="block truncate font-medium text-[var(--text)]">{c.nombre}</span>
							<span class="block text-xs text-[var(--text-muted)]">
								{m.company_identity({ affiliate: c.afiliado, company: c.compania })}
							</span>
							<span class="mt-1 block text-xs text-[var(--negative)]">{motivo(c)}</span>
						</span>
					</div>
				{/each}
			</div>
		{/if}

		{#if !disponibles.length && !invitaciones.length}
			<p class="mt-6 text-sm text-[var(--text-muted)]">
				{m.company_none_available()}
			</p>
		{/if}

		<a
			href="/logout"
			data-sveltekit-reload
			class="mt-8 inline-flex items-center gap-2 text-sm text-[var(--text-muted)] hover:text-[var(--text)]"
		>
			<Icon name="logout" size={16} />
			{m.nav_logout()}
		</a>
	</div>
</main>
