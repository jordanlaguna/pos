<script lang="ts">
	import Icon from '$lib/ui/components/Icon.svelte';
	import PageHeader from '$lib/ui/components/PageHeader.svelte';
	import EmptyState from '$lib/ui/components/EmptyState.svelte';
	import { formatAmount } from '$lib/domain/money';
	import { formatDate } from '$lib/ui/format';
	import { companyStateLabel } from '$lib/ui/messages';
	import { m } from '$lib/paraglide/messages.js';
	import type { Subscription, SupportCompany } from '$lib/domain/types';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	/**
	 * El color del estado. Es lo único que se mira al abrir la pantalla, así que
	 * el que importa —vencida, suspendida, cancelada— tiene que salirse de la
	 * página.
	 */
	function tono(s: Subscription): string {
		if (s.estado === 'cancelada' || s.estado === 'suspendida') {
			return 'bg-[var(--negative-bg)] text-[var(--negative)]';
		}
		if (s.estado === 'vencida') {
			return s.puede_vender
				? 'bg-[var(--warning-bg)] text-[var(--warning)]'
				: 'bg-[var(--negative-bg)] text-[var(--negative)]';
		}
		if (s.estado === 'prueba') return 'bg-[var(--info-bg)] text-[var(--info)]';
		return 'bg-[var(--positive-bg)] text-[var(--positive)]';
	}

	function usuarios(c: SupportCompany): string {
		return c.uso.cupo_usuarios === null
			? m.admin_usage_users_unlimited({ used: c.uso.usuarios })
			: m.admin_usage_users({ used: c.uso.usuarios, max: c.plan?.max_usuarios ?? 0 });
	}

	function cajas(c: SupportCompany): string {
		return c.uso.cupo_terminales === null
			? m.admin_usage_terminals_unlimited({ used: c.uso.terminales })
			: m.admin_usage_terminals({ used: c.uso.terminales, max: c.plan?.max_terminales ?? 0 });
	}

	/*
	 * El monto del mes va **sin símbolo de moneda**, y no es un olvido: cada
	 * compañía tiene la suya configurada y el panel no lee la configuración de
	 * veinte negocios para pintar una tabla. Un símbolo puesto por omisión diría
	 * «₡» sobre las ventas de un cliente que cobra en dólares, que es peor que no
	 * decir nada. La cifra sirve igual para lo que se usa acá: ver de un vistazo
	 * quién está operando y quién no.
	 */
	function ventas(c: SupportCompany): string {
		if (c.uso.ventas_del_mes === 0) return m.admin_usage_no_sales();
		return m.admin_usage_sales({
			count: c.uso.ventas_del_mes,
			total: formatAmount(c.uso.total_del_mes)
		});
	}
</script>

<PageHeader
	title={m.admin_companies_title()}
	description={m.admin_companies_count({ count: data.companies.length })}
>
	{#snippet actions()}
		<a href="/admin/companias/nueva" class="btn btn-primary">
			<Icon name="plus" size={15} />
			{m.admin_new_company()}
		</a>
	{/snippet}
</PageHeader>

{#if data.companies.length === 0}
	<div class="card">
		<EmptyState
			icon="users"
			title={m.admin_companies_title()}
			description={m.admin_companies_empty()}
		/>
	</div>
{:else}
	<div class="card table-wrap">
		<table class="data-table">
			<thead>
				<tr>
					<th>{m.admin_col_client()}</th>
					<th>{m.admin_col_company()}</th>
					<th>{m.admin_col_plan()}</th>
					<th>{m.admin_col_state()}</th>
					<th>{m.admin_col_expires()}</th>
					<th>{m.admin_col_usage()}</th>
					<th>{m.admin_col_month()}</th>
					<th class="text-right">{m.admin_col_actions()}</th>
				</tr>
			</thead>
			<tbody>
				{#each data.companies as c (c.id)}
					<tr>
						<td class="font-mono text-xs whitespace-nowrap">
							{m.admin_pair({ afiliado: c.afiliado, compania: c.compania })}
						</td>
						<td>
							<p class="font-medium text-[var(--text)]">{c.nombre}</p>
							{#if c.administradores.length > 0}
								<p class="truncate text-[11px] text-[var(--text-subtle)]">
									{c.administradores[0]}
								</p>
							{/if}
						</td>
						<td class="text-xs text-[var(--text-muted)]">
							{c.plan ? c.plan.nombre : m.admin_no_plan()}
						</td>
						<td>
							<span class="badge {tono(c.suscripcion)}">
								{companyStateLabel(c.suscripcion.estado)}
							</span>
						</td>
						<td class="text-xs whitespace-nowrap text-[var(--text-muted)]">
							{c.suscripcion.vence_el ? formatDate(c.suscripcion.vence_el) : m.admin_no_expiry()}
						</td>
						<td class="text-xs text-[var(--text-muted)]">
							<p>{usuarios(c)}</p>
							<p>{cajas(c)}</p>
							<p>{m.admin_usage_products({ count: c.uso.productos })}</p>
						</td>
						<td class="text-xs whitespace-nowrap text-[var(--text-muted)]">{ventas(c)}</td>
						<td class="text-right">
							<a href="/admin/companias/{c.id}" class="btn btn-ghost px-2 py-1 text-xs">
								{m.admin_open()}
							</a>
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
{/if}
