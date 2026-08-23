<script lang="ts">
	import Icon from '$lib/ui/components/Icon.svelte';
	import PageHeader from '$lib/ui/components/PageHeader.svelte';
	import EmptyState from '$lib/ui/components/EmptyState.svelte';
	import { formatDateTime } from '$lib/ui/format';
	import { auditActionLabel } from '$lib/ui/messages';
	import { m } from '$lib/paraglide/messages.js';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();
</script>

<PageHeader title={m.admin_audit_title()} description={m.admin_audit_intro()} />

<!--
	El filtro es un GET, no un formulario con acción: lo que produce es una URL
	que se puede guardar, pegar en un correo y volver a abrir mañana. Y funciona
	sin JavaScript.
-->
<form method="GET" class="card mb-4 flex flex-wrap items-end gap-3 p-3">
	<div class="min-w-40 flex-1">
		<label class="label" for="company_id">{m.admin_audit_company()}</label>
		<select id="company_id" name="company_id" class="input">
			<option value="" selected={data.filtro.companyId === ''}>{m.admin_audit_all()}</option>
			{#each data.companies as c (c.id)}
				<option value={c.id} selected={String(c.id) === data.filtro.companyId}>
					{c.nombre}
				</option>
			{/each}
		</select>
	</div>

	<div class="min-w-40 flex-1">
		<label class="label" for="accion">{m.admin_audit_action()}</label>
		<select id="accion" name="accion" class="input">
			<option value="" selected={data.filtro.accion === ''}>{m.admin_audit_all()}</option>
			{#each data.acciones as accion (accion)}
				<option value={accion} selected={accion === data.filtro.accion}>
					{auditActionLabel(accion)}
				</option>
			{/each}
		</select>
	</div>

	<button type="submit" class="btn btn-ghost">
		<Icon name="filter" size={15} />
		{m.admin_audit_apply()}
	</button>
</form>

{#if data.lineas.length === 0}
	<div class="card">
		<EmptyState icon="clock" title={m.admin_audit_title()} description={m.admin_audit_empty()} />
	</div>
{:else}
	<div class="card table-wrap">
		<table class="data-table">
			<thead>
				<tr>
					<th>{m.admin_col_when()}</th>
					<th>{m.admin_col_who()}</th>
					<th>{m.admin_col_what()}</th>
					<th>{m.admin_col_where()}</th>
					<th>{m.admin_col_detail()}</th>
					<th>{m.admin_col_ip()}</th>
				</tr>
			</thead>
			<tbody>
				{#each data.lineas as linea (linea.id)}
					<tr>
						<td class="text-xs whitespace-nowrap">{formatDateTime(linea.creado_el)}</td>
						<td class="text-xs">
							<p class="text-[var(--text)]">
								{linea.nombre ?? linea.email ?? m.admin_audit_unknown_user({ id: linea.user_id })}
							</p>
							{#if linea.nombre && linea.email}
								<p class="text-[11px] text-[var(--text-subtle)]">{linea.email}</p>
							{/if}
						</td>
						<td class="text-xs">{auditActionLabel(linea.accion)}</td>
						<td class="text-xs text-[var(--text-muted)]">
							{#if linea.company_id}
								<a href="/admin/companias/{linea.company_id}" class="hover:underline">
									{linea.company_nombre ?? linea.company_id}
								</a>
							{:else}
								{m.admin_audit_no_company()}
							{/if}
						</td>
						<td class="text-xs text-[var(--text-muted)]">{linea.detalle ?? ''}</td>
						<td class="font-mono text-[11px] text-[var(--text-subtle)]">{linea.ip ?? ''}</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
{/if}
