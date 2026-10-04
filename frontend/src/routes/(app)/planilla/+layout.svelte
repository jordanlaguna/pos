<script lang="ts">
	import { page } from '$app/state';
	import Icon from '$lib/ui/components/Icon.svelte';
	import PageHeader from '$lib/ui/components/PageHeader.svelte';
	import { m } from '$lib/paraglide/messages.js';
	import type { LayoutData } from './$types';

	let { data, children }: { data: LayoutData; children: import('svelte').Snippet } = $props();

	/** Las pestañas, en el orden del trabajo: mirar, la gente, lo que pasó, pagar. */
	const pestañas = $derived([
		{ href: '/planilla', label: m.payroll_tab_summary() },
		{ href: '/planilla/empleados', label: m.payroll_tab_employees() },
		{ href: '/planilla/acciones', label: m.payroll_tab_actions() },
		{ href: '/planilla/corridas', label: m.payroll_tab_runs() },
		{ href: '/planilla/vacaciones', label: m.payroll_tab_vacations() },
		{ href: '/planilla/archivos', label: m.payroll_tab_files() },
		{ href: '/planilla/configuracion', label: m.payroll_tab_settings() },
		{ href: '/planilla/importar', label: m.payroll_tab_import() },
		{ href: '/planilla/tasas', label: m.payroll_tab_rates() }
	]);

	function activa(href: string): boolean {
		return href === '/planilla'
			? page.url.pathname === '/planilla'
			: page.url.pathname.startsWith(href);
	}

	/** La boleta se imprime sola: sin cabecera ni pestañas. */
	const imprimible = $derived(/\/boleta\//.test(page.url.pathname));
</script>

{#if !imprimible}
	<PageHeader title={m.payroll_title()} description={m.payroll_description()} />

	{#if !data.payrollEnabled}
		<div
			class="mb-4 flex items-start gap-3 rounded-lg border border-[var(--warning)] bg-[var(--warning-bg)] p-3 text-sm"
			role="status"
			data-planilla-bloqueada
		>
			<Icon name="lock" size={16} class="mt-0.5 shrink-0 text-[var(--warning)]" />
			<div>
				<p class="font-semibold text-[var(--text)]">{m.payroll_locked_title()}</p>
				<p class="text-[var(--text-muted)]">{m.payroll_locked_text()}</p>
			</div>
		</div>
	{/if}

	<nav class="mb-4 flex flex-wrap gap-1 border-b border-[var(--border)]" aria-label={m.payroll_title()}>
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
