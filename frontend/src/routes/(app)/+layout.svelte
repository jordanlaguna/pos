<script lang="ts">
	import { untrack } from 'svelte';
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import Icon from '$lib/components/Icon.svelte';
	import { theme } from '$lib/stores/theme.svelte';
	import { visibleGroups, titleFor } from '$lib/navigation';
	import { initials } from '$lib/format';
	import { configureMoney } from '$lib/money';
	import { accentTheme, hexToRgb } from '$lib/color';
	import { businessName } from '$lib/settings';
	import { DEFAULT_SETTINGS } from '$lib/settings';
	import type { LayoutData } from './$types';

	let { data, children }: { data: LayoutData; children: any } = $props();

	/*
	 * La moneda y el impuesto se fijan acá, en el script del layout, porque corre
	 * antes de que se renderice cualquier hijo —tanto en el servidor como al
	 * hidratar—, y de ahí en adelante `formatMoney` ya sabe con qué símbolo
	 * escribir. Ver la nota larga en $lib/money.ts.
	 *
	 * `untrack` porque acá SÍ se quiere el valor inicial y nada más: de mantenerlo
	 * al día se encarga el `$effect.pre` de abajo.
	 */
	untrack(() => configureMoney(data.settings));

	// Y de nuevo antes de cada actualización, por si la configuración cambió.
	// `$effect.pre` corre antes que el renderizado de los hijos; un `$effect`
	// normal correría después y el primer repintado saldría con la moneda vieja.
	$effect.pre(() => configureMoney(data.settings));

	const marca = $derived(businessName(data.settings));
	const logoUrl = $derived(data.logoVersion ? `/marca/logo?v=${data.logoVersion}` : null);

	/**
	 * Acento configurable.
	 *
	 * Solo se emiten variables cuando el color elegido no es el de fábrica; así
	 * el sistema de diseño de app.css sigue siendo la única fuente mientras nadie
	 * toque nada. El tono oscuro y el color del texto no los elige el usuario: se
	 * derivan para que el contraste no dependa del gusto (ver $lib/color.ts).
	 */
	const accent = $derived(
		data.settings.apariencia.color_acento !== DEFAULT_SETTINGS.apariencia.color_acento
			? accentTheme(data.settings.apariencia.color_acento)
			: null
	);

	function chartVars(hex: string | null): string {
		if (!hex) return '';
		const { r, g, b } = hexToRgb(hex);
		const rgb = `${Math.round(r * 255)} ${Math.round(g * 255)} ${Math.round(b * 255)}`;
		return `--chart-accent:${hex};--chart-area:rgb(${rgb} / 0.12);`;
	}

	// El menú del WinForms colapsaba a iconos; aquí se conserva ese gesto y la
	// preferencia se recuerda, porque un cajero fijo siempre lo quiere igual.
	let collapsed = $state(false);
	let mobileOpen = $state(false);

	$effect(() => {
		const stored = localStorage.getItem('ventasys-menu');
		if (stored) collapsed = stored === 'collapsed';
	});

	function toggleMenu() {
		collapsed = !collapsed;
		localStorage.setItem('ventasys-menu', collapsed ? 'collapsed' : 'expanded');
	}

	const groups = $derived(visibleGroups(data.user.role));
	const currentTitle = $derived(titleFor(page.url.pathname));

	function isActive(href: string): boolean {
		return page.url.pathname === href || page.url.pathname.startsWith(`${href}/`);
	}

	/**
	 * Atajos globales. F2 lleva a vender desde cualquier pantalla, como el F1 de
	 * cobro del WinForms. Se ignoran mientras el foco está en un campo de texto.
	 */
	function onKeydown(event: KeyboardEvent) {
		const target = event.target as HTMLElement | null;
		const typing =
			target?.tagName === 'INPUT' ||
			target?.tagName === 'TEXTAREA' ||
			target?.tagName === 'SELECT' ||
			target?.isContentEditable;

		if (event.key === 'F2' && !typing) {
			event.preventDefault();
			goto('/ventas');
		}
		if (event.key === 'Escape') mobileOpen = false;
	}
</script>

<svelte:head>
	<title>{currentTitle} · {marca}</title>
	{#if accent}
		<!-- eslint-disable-next-line svelte/no-at-html-tags -->
		{@html `<style>
			:root {
				--accent: ${accent.light};
				--accent-text: ${accent.inkLight};
				--ring: ${accent.light};
				${chartVars(accent.chart)}
			}
			:root[data-theme='dark'] {
				--accent: ${accent.dark};
				--accent-text: ${accent.inkDark};
				--ring: ${accent.dark};
				${chartVars(accent.chart)}
			}
		</style>`}
	{/if}
</svelte:head>
<svelte:window onkeydown={onKeydown} />

<div class="flex h-full">
	<!-- Fondo oscuro del menú en móvil -->
	{#if mobileOpen}
		<button
			type="button"
			class="fixed inset-0 z-30 bg-black/50 lg:hidden"
			onclick={() => (mobileOpen = false)}
			aria-label="Cerrar menú"
		></button>
	{/if}

	<nav
		class="no-print fixed inset-y-0 left-0 z-40 flex flex-col border-r border-[var(--border)] bg-[var(--surface-raised)] transition-[width,transform] duration-200 lg:static lg:translate-x-0
			{collapsed ? 'w-[4.5rem]' : 'w-60'}
			{mobileOpen ? 'translate-x-0' : '-translate-x-full'}"
		aria-label="Navegación principal"
	>
		<div class="flex h-14 shrink-0 items-center gap-2.5 border-b border-[var(--border)] px-3">
			{#if logoUrl}
				<!-- object-contain: el logo del negocio puede venir de cualquier proporción. -->
				<img
					src={logoUrl}
					alt=""
					class="h-9 w-9 shrink-0 rounded-lg object-contain"
					width="36"
					height="36"
				/>
			{:else}
				<span
					class="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-[var(--accent)] text-[var(--accent-text)]"
				>
					<Icon name="cart" size={18} />
				</span>
			{/if}
			{#if !collapsed}
				<div class="min-w-0 flex-1">
					<p class="truncate text-sm font-bold text-[var(--text)]">{marca}</p>
					<p class="truncate text-[10px] text-[var(--text-subtle)]">Punto de venta</p>
				</div>
			{/if}
			<button
				type="button"
				class="hidden shrink-0 rounded-lg p-1.5 text-[var(--text-subtle)] hover:bg-[var(--surface-sunken)] hover:text-[var(--text)] lg:block"
				onclick={toggleMenu}
				aria-label={collapsed ? 'Expandir menú' : 'Colapsar menú'}
			>
				<Icon name="menu" size={16} />
			</button>
		</div>

		<div class="flex-1 overflow-y-auto py-3">
			{#each groups as group (group.title)}
				<div class="mb-4">
					{#if !collapsed}
						<p
							class="mb-1 px-4 text-[10px] font-bold tracking-wider text-[var(--text-subtle)] uppercase"
						>
							{group.title}
						</p>
					{/if}
					<ul class="space-y-0.5 px-2">
						{#each group.items as item (item.href)}
							{@const active = isActive(item.href)}
							<li>
								{#if item.locked}
									<!--
										Se muestra pero no se abre. Un cajero necesita saber que la
										sección existe y que le falta permiso; si desaparece del menú,
										concluye que el sistema no la tiene.
									-->
									<div
										class="flex cursor-not-allowed items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-[var(--text-subtle)] opacity-60 {collapsed
											? 'justify-center px-0'
											: ''}"
										title="{item.label}: solo para administradores. Pedile a un administrador que te cambie el rol."
									>
										<Icon name={item.icon} size={18} class="shrink-0" />
										{#if !collapsed}
											<span class="flex-1 truncate">{item.label}</span>
											<Icon name="lock" size={12} class="shrink-0" />
										{/if}
									</div>
								{:else}
									<a
										href={item.href}
										onclick={() => (mobileOpen = false)}
										class="flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors
											{active
											? 'bg-[var(--accent)] text-[var(--accent-text)]'
											: 'text-[var(--text-muted)] hover:bg-[var(--surface-sunken)] hover:text-[var(--text)]'}
											{collapsed ? 'justify-center px-0' : ''}"
										aria-current={active ? 'page' : undefined}
										title={collapsed ? item.label : undefined}
									>
										<Icon name={item.icon} size={18} class="shrink-0" />
										{#if !collapsed}
											<span class="flex-1 truncate">{item.label}</span>
											{#if item.shortcut}
												<kbd
													class="rounded border px-1 text-[10px] font-semibold
														{active
														? 'border-white/30 text-[var(--accent-text)]/80'
														: 'border-[var(--border)] text-[var(--text-subtle)]'}"
												>
													{item.shortcut}
												</kbd>
											{/if}
										{/if}
									</a>
								{/if}
							</li>
						{/each}
					</ul>
				</div>
			{/each}
		</div>

		<div class="shrink-0 border-t border-[var(--border)] p-2">
			<div
				class="flex items-center gap-2.5 rounded-lg px-2 py-2 {collapsed ? 'justify-center' : ''}"
			>
				<span
					class="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-[var(--surface-sunken)] text-xs font-bold text-[var(--text-muted)]"
					title={data.user.name}
				>
					{initials(data.user.name)}
				</span>
				{#if !collapsed}
					<div class="min-w-0 flex-1">
						<p class="truncate text-xs font-semibold text-[var(--text)]">{data.user.name}</p>
						<p class="truncate text-[10px] text-[var(--text-subtle)] capitalize">
							{data.user.role}
						</p>
					</div>
					<form method="POST" action="/logout">
						<button
							type="submit"
							class="rounded-lg p-1.5 text-[var(--text-subtle)] hover:bg-[var(--negative-bg)] hover:text-[var(--negative)]"
							aria-label="Cerrar sesión"
						>
							<Icon name="logout" size={15} />
						</button>
					</form>
				{/if}
			</div>
		</div>
	</nav>

	<div class="flex min-w-0 flex-1 flex-col">
		<header
			class="no-print flex h-14 shrink-0 items-center gap-3 border-b border-[var(--border)] bg-[var(--surface-raised)] px-4"
		>
			<button
				type="button"
				class="rounded-lg p-2 text-[var(--text-muted)] hover:bg-[var(--surface-sunken)] lg:hidden"
				onclick={() => (mobileOpen = true)}
				aria-label="Abrir menú"
			>
				<Icon name="menu" size={18} />
			</button>

			<h1 class="flex-1 truncate text-sm font-bold text-[var(--text)]">{currentTitle}</h1>

			{#if data.demo}
				<span
					class="badge hidden bg-[var(--warning-bg)] text-[var(--warning)] sm:inline-flex"
					title="El backend real no está conectado; se están usando datos de ejemplo."
				>
					<Icon name="info" size={12} />
					Demo
				</span>
			{/if}

			<button
				type="button"
				class="rounded-lg p-2 text-[var(--text-muted)] hover:bg-[var(--surface-sunken)]"
				onclick={() => theme.toggle()}
				aria-label="Cambiar entre tema claro y oscuro"
			>
				<Icon name={theme.current === 'dark' ? 'sun' : 'moon'} size={16} />
			</button>
		</header>

		<main class="min-h-0 flex-1 overflow-y-auto p-4 sm:p-6">
			{@render children()}
		</main>
	</div>
</div>
