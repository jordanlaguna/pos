<script lang="ts">
	import { page } from '$app/state';
	import Icon from '$lib/ui/components/Icon.svelte';
	import { theme } from '$lib/ui/stores/theme.svelte';
	import { initials } from '$lib/ui/format';
	import { m } from '$lib/paraglide/messages.js';
	import type { LayoutData } from './$types';

	let { data, children }: { data: LayoutData; children: any } = $props();

	/*
	 * El armazón del panel, y a propósito **no** es el del POS.
	 *
	 * No hay moneda que configurar —soporte no vende—, no hay marca del negocio
	 * —no es de ningún negocio— y no hay compañía en el menú. Reusar el layout de
	 * `(app)` habría significado llenarlo de condicionales para apagar la mitad,
	 * y esa mitad es justamente la que RN-4 dice que no existe.
	 *
	 * Lo que sí se comparte es todo lo demás: los tokens de color, los iconos, el
	 * tema claro y oscuro y el catálogo.
	 */
	const SECCIONES = $derived([
		{ href: '/admin', label: m.admin_nav_companies(), icon: 'users' as const },
		{ href: '/admin/bitacora', label: m.admin_nav_audit(), icon: 'clock' as const }
	]);

	function isActive(href: string): boolean {
		// `/admin` es la raíz: solo está activa cuando la ruta es exactamente eso,
		// porque si no queda marcada también estando en la bitácora.
		return href === '/admin'
			? page.url.pathname === '/admin' || page.url.pathname.startsWith('/admin/companias')
			: page.url.pathname === href || page.url.pathname.startsWith(`${href}/`);
	}
</script>

<svelte:head>
	<title>{m.admin_title()}</title>
</svelte:head>

<div class="flex h-full">
	<nav
		class="hidden w-56 shrink-0 flex-col border-r border-[var(--border)] bg-[var(--surface-raised)] sm:flex"
		aria-label={m.admin_nav()}
	>
		<div class="flex h-14 items-center gap-2.5 border-b border-[var(--border)] px-3">
			<span
				class="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-[var(--text)] text-[var(--surface)]"
			>
				<Icon name="bolt" size={18} />
			</span>
			<div class="min-w-0">
				<p class="truncate text-sm font-bold text-[var(--text)]">{m.admin_title()}</p>
				<p class="truncate text-[10px] text-[var(--text-subtle)]">{m.admin_tagline()}</p>
			</div>
		</div>

		<ul class="flex-1 space-y-0.5 p-2">
			{#each SECCIONES as seccion (seccion.href)}
				{@const active = isActive(seccion.href)}
				<li>
					<a
						href={seccion.href}
						class="flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors
							{active
							? 'bg-[var(--accent)] text-[var(--accent-text)]'
							: 'text-[var(--text-muted)] hover:bg-[var(--surface-sunken)] hover:text-[var(--text)]'}"
						aria-current={active ? 'page' : undefined}
					>
						<Icon name={seccion.icon} size={18} class="shrink-0" />
						<span class="flex-1 truncate">{seccion.label}</span>
					</a>
				</li>
			{/each}
		</ul>

		<div class="flex items-center gap-2.5 border-t border-[var(--border)] p-3">
			<span
				class="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-[var(--surface-sunken)] text-xs font-bold text-[var(--text-muted)]"
				title={data.support.name}
			>
				{initials(data.support.name)}
			</span>
			<div class="min-w-0 flex-1">
				<p class="truncate text-xs font-semibold text-[var(--text)]">{data.support.name}</p>
				<p class="truncate text-[10px] text-[var(--text-subtle)]">{m.admin_role()}</p>
			</div>
			<form method="POST" action="/logout">
				<button
					type="submit"
					class="rounded-lg p-1.5 text-[var(--text-subtle)] hover:bg-[var(--negative-bg)] hover:text-[var(--negative)]"
					aria-label={m.admin_logout()}
				>
					<Icon name="logout" size={15} />
				</button>
			</form>
		</div>
	</nav>

	<div class="flex min-w-0 flex-1 flex-col">
		<header
			class="flex h-14 shrink-0 items-center gap-3 border-b border-[var(--border)] bg-[var(--surface-raised)] px-4"
		>
			<span class="grid h-8 w-8 place-items-center rounded-lg bg-[var(--text)] text-[var(--surface)] sm:hidden">
				<Icon name="bolt" size={16} />
			</span>
			<h1 class="flex-1 truncate text-sm font-bold text-[var(--text)]">{m.admin_title()}</h1>

			<!-- En móvil el menú lateral no está: las dos secciones van acá. -->
			<div class="flex items-center gap-1 sm:hidden">
				{#each SECCIONES as seccion (seccion.href)}
					<a
						href={seccion.href}
						class="rounded-lg p-2 {isActive(seccion.href)
							? 'text-[var(--accent-text)]'
							: 'text-[var(--text-muted)]'}"
						aria-label={seccion.label}
					>
						<Icon name={seccion.icon} size={16} />
					</a>
				{/each}
			</div>

			{#if data.demo}
				<span class="badge hidden bg-[var(--warning-bg)] text-[var(--warning)] sm:inline-flex">
					<Icon name="info" size={12} />
					{m.nav_demo()}
				</span>
			{/if}

			<button
				type="button"
				class="rounded-lg p-2 text-[var(--text-muted)] hover:bg-[var(--surface-sunken)]"
				onclick={() => theme.toggle()}
				aria-label={m.nav_toggle_theme()}
			>
				<Icon name={theme.current === 'dark' ? 'sun' : 'moon'} size={16} />
			</button>
		</header>

		<main class="min-h-0 flex-1 overflow-y-auto p-4 sm:p-6">
			{@render children()}
		</main>
	</div>
</div>
