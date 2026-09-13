<script lang="ts">
	import { untrack } from 'svelte';
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import Icon from '$lib/ui/components/Icon.svelte';
	import { theme } from '$lib/ui/stores/theme.svelte';
	import { visibleGroups, titleFor } from '$lib/ui/navigation';
	import { initials } from '$lib/ui/format';
	import { configureMoney } from '$lib/domain/money';
	import { accentTheme, hexToRgb } from '$lib/domain/color';
	import { businessName } from '$lib/domain/settings';
	import { m } from '$lib/paraglide/messages.js';
	import { roleLabel, subscriptionNotice } from '$lib/ui/messages';
	import { DEFAULT_SETTINGS } from '$lib/domain/settings';
	import type { LayoutData } from './$types';

	let { data, children }: { data: LayoutData; children: any } = $props();

	/*
	 * La moneda y el impuesto se fijan acá, en el script del layout, porque corre
	 * antes de que se renderice cualquier hijo —tanto en el servidor como al
	 * hidratar—, y de ahí en adelante `formatMoney` ya sabe con qué símbolo
	 * escribir. Ver la nota larga en $lib/domain/money.ts.
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
	 * derivan para que el contraste no dependa del gusto (ver $lib/domain/color.ts).
	 */
	const accent = $derived(
		data.settings.appearance.accentColor !== DEFAULT_SETTINGS.appearance.accentColor
			? accentTheme(data.settings.appearance.accentColor)
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

	const groups = $derived(visibleGroups(data.user.role, data.user.modules));
	const currentTitle = $derived(titleFor(page.url.pathname));

	/*
	 * Los dos avisos que van arriba de todo (F3).
	 *
	 * El de la suscripción se muestra en **cada pantalla** y no solo en ventas
	 * (RF-10): el dueño puede entrar a mirar un reporte y ahí también tiene que
	 * enterarse de que su pago vence el jueves. Sale nulo cuando no hay nada que
	 * decir, porque un aviso permanente que no dice nada es un aviso que nadie
	 * lee.
	 *
	 * El de la suplantación se muestra mientras soporte esté mirando esta
	 * compañía, y por eso viaja en `/users/me` y no una sola vez al entrar: una
	 * franja que se pierde al navegar no es permanente, y lo peor que puede pasar
	 * en una visita de soporte es olvidar de quién son los datos que se están
	 * viendo.
	 */
	const aviso = $derived(subscriptionNotice(data.user.subscription));
	const enGracia = $derived(data.user.subscription?.aviso === 'en_gracia');
	const bloqueado = $derived(data.user.subscription?.puede_vender === false);
	const suplantacion = $derived(data.user.impersonated_by);

	/*
	 * Las opciones del selector de idioma (T-810).
	 *
	 * Son funciones y no una constante de módulo por lo de siempre: una constante
	 * se evaluaría al importar y congelaría el idioma de la primera petición para
	 * todas (defecto 17). `idiomaElegido` es lo que **eligió** la persona, no el
	 * efectivo: «el de la compañía» tiene que verse marcado cuando hereda.
	 */
	const IDIOMAS = $derived([
		{ value: 'auto', label: m.nav_language_auto() },
		{ value: 'es', label: m.language_es() },
		{ value: 'en', label: m.language_en() },
		{ value: 'pt', label: m.language_pt() }
	]);
	const idiomaElegido = $derived(data.user?.user_locale ?? 'auto');

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
			aria-label={m.nav_close_menu()}
		></button>
	{/if}

	<!--
		Compañía, sucursal y caja (T-211).

		Con una sola compañía es información de fondo; con varias es lo que evita
		cobrarle una venta al negocio equivocado.

		Se define una vez y se usa en dos sitios —la barra de arriba en pantalla
		ancha, el cajón del menú en pantalla chica— porque son el mismo dato y no
		dos. Dos copias del mismo bloque es como una se queda sin el arreglo que
		recibió la otra.
	-->
	{#snippet identidad(forma: 'inline' | 'block')}
		{#if data.user.company_name}
			<div class={forma === 'inline' ? 'flex items-center gap-2' : 'pb-2'}>
				<span class="text-[var(--text-subtle)]" aria-hidden="true">
					<Icon name="home" size={14} />
				</span>
				<div class="min-w-0">
					<p class="truncate text-xs font-medium text-[var(--text)]">
						{data.user.company_name}
					</p>
					{#if data.user.branch_code && data.user.terminal_code}
						<p class="truncate text-[10px] leading-tight text-[var(--text-subtle)]">
							{m.nav_branch_terminal({
								branch: data.user.branch_code,
								terminal: data.user.terminal_code
							})}
						</p>
					{/if}
				</div>
				{#if data.user.companies_available > 1}
					<!--
						Solo aparece cuando hay a dónde ir (RN-25). Ofrecerle «cambiar de
						compañía» a quien tiene una sola es prometer algo que no existe.
					-->
					<a
						href="/compania"
						class="shrink-0 rounded-lg p-1.5 text-[var(--text-subtle)] hover:bg-[var(--surface-sunken)] hover:text-[var(--accent)]"
						title={m.nav_switch_company()}
						aria-label={m.nav_switch_company()}
					>
						<Icon name="refresh" size={13} />
					</a>
				{/if}
			</div>
		{/if}
	{/snippet}

	<!--
		El idioma de esta persona (T-810, RN-28).

		Va en la barra y no en Configuración porque es de quien está sentado en la
		caja, no del negocio: un local costarricense puede contratar a una cajera
		nicaragüense que prefiera otra cosa, y no tiene por qué pedirle permiso al
		administrador para leer su pantalla.

		Es un formulario de verdad, con su botón: así funciona sin JavaScript,
		igual que el resto del POS. «El de la compañía» no es lo mismo que elegir
		español —hereda, y sigue al negocio si cambia—.
	-->
	{#snippet idioma(donde: 'header' | 'nav')}
		<form
			method="POST"
			action="/idioma"
			class={donde === 'header' ? 'flex items-center gap-1' : 'mt-2 flex items-center gap-1'}
		>
			<input type="hidden" name="redirectTo" value={page.url.pathname} />
			<label class="sr-only" for="nav-idioma-{donde}">{m.nav_language()}</label>
			<!--
				Sin `value` ni `bind:`, con `selected` en cada opción: el select queda
				**sin controlar** a propósito.

				Con `value={…}`, Svelte lo reinicia al hidratar, y eso se come la
				elección de quien alcanzó a tocarlo antes —que en una caja lenta es lo
				normal—. Se descubrió con la prueba de punta a punta: elegía «el de la
				compañía», el valor volvía a «inglés» solo, y el formulario mandaba el
				idioma que ya estaba puesto.
			-->
			<select
				id="nav-idioma-{donde}"
				name="locale"
				class="input h-8 min-w-0 py-0 text-xs {donde === 'header' ? 'w-36' : 'flex-1'}"
			>
				{#each IDIOMAS as opcion (opcion.value)}
					<option value={opcion.value} selected={opcion.value === idiomaElegido}>
						{opcion.label}
					</option>
				{/each}
			</select>
			<button type="submit" class="btn btn-ghost h-8 px-2" aria-label={m.nav_language_apply()}>
				<Icon name="check" size={14} />
			</button>
		</form>
	{/snippet}

	<nav
		class="no-print fixed inset-y-0 left-0 z-40 flex flex-col border-r border-[var(--border)] bg-[var(--surface-raised)] transition-[width,transform] duration-200 lg:relative lg:translate-x-0
			{collapsed ? 'w-[4.5rem]' : 'w-60'}
			{mobileOpen ? 'translate-x-0' : '-translate-x-full'}"
		aria-label={m.nav_main()}
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
					<p class="truncate text-[10px] text-[var(--text-subtle)]">{m.nav_tagline()}</p>
				</div>
			{/if}
		</div>

		<!--
			El tirador de plegar, **montado sobre el borde** y no dentro del
			encabezado.

			Queda en el mismo punto de la pantalla esté plegado o no —lo lleva el
			borde, que es lo único que se mueve—, así que el gesto de volver a
			abrirlo se hace sin buscar. Metido adentro, al plegarse se corría con el
			menú y había que ir a encontrarlo entre los iconos.

			`-right-3` lo deja a caballo del borde: mitad adentro, mitad afuera. Es
			lo que lo hace leerse como un asa del panel y no como un botón más de la
			lista.
		-->
		<button
			type="button"
			class="absolute top-11 -right-3.5 z-10 hidden h-7 w-7 place-items-center rounded-full border border-[var(--border)] bg-[var(--surface-raised)] text-[var(--text-subtle)] shadow-sm transition-colors hover:border-[var(--accent)] hover:text-[var(--accent)] lg:grid"
			onclick={toggleMenu}
			aria-label={collapsed ? m.nav_expand_menu() : m.nav_collapse_menu()}
			title={collapsed ? m.nav_expand_menu() : m.nav_collapse_menu()}
		>
			<Icon name={collapsed ? 'panelopen' : 'panelclose'} size={15} strokeWidth={1.6} />
		</button>

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
										title={item.lockedBy === 'module'
										? m.nav_locked_module({ section: item.label })
										: m.nav_locked({ section: item.label })}
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
			{#if !collapsed}
				<!-- En pantalla chica el cajón es el único sitio donde caben: arriba
				     la barra no da para más que el título y los dos botones. -->
				<div class="px-2 pb-2 md:hidden">
					{@render identidad('block')}
					{@render idioma('nav')}
				</div>
			{/if}

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
						<p class="truncate text-[10px] text-[var(--text-subtle)]">
							{roleLabel(data.user.role)}
						</p>
					</div>
					<form method="POST" action="/logout">
						<button
							type="submit"
							class="rounded-lg p-1.5 text-[var(--text-subtle)] hover:bg-[var(--negative-bg)] hover:text-[var(--negative)]"
							aria-label={m.nav_logout()}
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
				aria-label={m.nav_open_menu()}
			>
				<Icon name="menu" size={18} />
			</button>

			<h1 class="flex-1 truncate text-sm font-bold text-[var(--text)]">{currentTitle}</h1>

			<!--
				La identidad y el idioma viven acá y no al pie del menú (2026-09-12).

				Dos razones. La barra tenía el título y un botón de tema en todo lo
				ancho, y el pie del menú acumulaba compañía, caja, idioma y usuario
				uno encima de otro. Y la segunda, que es la que importa: **en qué
				compañía y en qué caja se está trabajando es lo que hay que ver sin
				buscar** (T-211), y al pie del menú desaparecía con el menú plegado.
				Acá está siempre.
			-->
			<div class="hidden items-center gap-3 md:flex">
				{@render identidad('inline')}
				{@render idioma('header')}
			</div>

			{#if data.demo}
				<span
					class="badge hidden bg-[var(--warning-bg)] text-[var(--warning)] sm:inline-flex"
					title={m.nav_demo_hint()}
				>
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

		{#if suplantacion}
			<!--
				La franja de la visita de soporte (RF-8). Va antes del contenido, ocupa
				el ancho completo y no se puede cerrar: es la única cosa en la pantalla
				que dice que estos datos son de otro.
			-->
			<div
				class="no-print flex flex-wrap items-center gap-2 border-b border-[var(--warning)] bg-[var(--warning-bg)] px-4 py-2 text-xs text-[var(--warning)]"
			>
				<Icon name="eye" size={14} class="shrink-0" />
				<strong>{m.impersonation_banner({ compania: data.user.company_name ?? '' })}</strong>
				<span class="badge bg-[var(--warning)] text-[var(--surface)]">
					{m.impersonation_read_only()}
				</span>
				{#if data.user.impersonation_reason}
					<span class="min-w-0 flex-1 truncate opacity-90">
						{m.impersonation_reason({ motivo: data.user.impersonation_reason })}
					</span>
				{/if}
				<form method="POST" action="/admin/salir" class="ml-auto">
					<button type="submit" class="btn btn-ghost px-2 py-1 text-xs">
						<Icon name="back" size={13} />
						{m.impersonation_leave()}
					</button>
				</form>
			</div>
		{/if}

		{#if aviso}
			<!--
				El estado de la suscripción (RF-11). Rojo cuando ya no se puede vender,
				ámbar mientras quede gracia o falten días: el color es lo primero que se
				mira y tiene que decir si hay que actuar hoy.
			-->
			<div
				class="no-print flex flex-wrap items-center gap-2 border-b px-4 py-2 text-xs
					{bloqueado
					? 'border-[var(--negative)] bg-[var(--negative-bg)] text-[var(--negative)]'
					: enGracia
						? 'border-[var(--warning)] bg-[var(--warning-bg)] text-[var(--warning)]'
						: 'border-[var(--border)] bg-[var(--surface-sunken)] text-[var(--text-muted)]'}"
			>
				<Icon name={bloqueado ? 'alert' : 'info'} size={14} class="shrink-0" />
				<span class="min-w-0 flex-1">{aviso}</span>
				{#if bloqueado || enGracia}
					<span class="opacity-90">{m.subscription_contact()}</span>
				{/if}
			</div>
		{/if}

		<main class="min-h-0 flex-1 overflow-y-auto p-4 sm:p-6">
			{@render children()}
		</main>
	</div>
</div>
