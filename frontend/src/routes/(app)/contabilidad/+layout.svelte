<script lang="ts">
	import { page } from '$app/state';
	import PageHeader from '$lib/ui/components/PageHeader.svelte';
	import { m } from '$lib/paraglide/messages.js';
	import type { LayoutData } from './$types';

	let { data, children }: { data: LayoutData; children: import('svelte').Snippet } = $props();

	/**
	 * Las pestañas, en el orden en que se usan: primero mirar, después ajustar.
	 *
	 * Solo aparecen con la contabilidad activa. Antes de activar no hay nada que
	 * mirar y las siete llevarían a pantallas vacías.
	 */
	const pestañas = $derived([
		{ href: '/contabilidad', label: m.accounting_tab_summary() },
		{ href: '/contabilidad/asientos', label: m.accounting_tab_entries() },
		{ href: '/contabilidad/reportes', label: m.accounting_tab_reports() },
		{ href: '/contabilidad/iva', label: m.accounting_tab_vat() },
		{ href: '/contabilidad/periodos', label: m.accounting_tab_periods() },
		{ href: '/contabilidad/cuentas', label: m.accounting_tab_accounts() },
		{ href: '/contabilidad/mapeo', label: m.accounting_tab_mappings() }
	]);

	/** La pestaña activa. El resumen solo cuando la ruta es exactamente la suya. */
	function activa(href: string): boolean {
		return href === '/contabilidad'
			? page.url.pathname === '/contabilidad'
			: page.url.pathname.startsWith(href);
	}
</script>

<PageHeader title={m.accounting_title()} description={m.accounting_description()} />

{#if data.status.active}
	<nav class="mb-4 flex flex-wrap gap-1 border-b border-[var(--border)]" aria-label={m.accounting_title()}>
		{#each pestañas as pestaña (pestaña.href)}
			<a
				href={pestaña.href}
				class="-mb-px border-b-2 px-3 py-2 text-sm transition-colors {activa(pestaña.href)
					? 'border-[var(--accent)] font-semibold text-[var(--accent)]'
					: 'border-transparent text-[var(--text-subtle)] hover:text-[var(--text)]'}"
				aria-current={activa(pestaña.href) ? 'page' : undefined}
			>
				{pestaña.label}
			</a>
		{/each}
	</nav>
{/if}

{@render children()}
