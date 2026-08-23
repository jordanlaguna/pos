<script lang="ts">
	import { enhance } from '$app/forms';
	import Icon from '$lib/ui/components/Icon.svelte';
	import PageHeader from '$lib/ui/components/PageHeader.svelte';
	import Field from '$lib/ui/components/Field.svelte';
	import Spinner from '$lib/ui/components/Spinner.svelte';
	import { submit } from '$lib/ui/forms';
	import { formatAmount } from '$lib/domain/money';
	import { formatDate, formatDateTime } from '$lib/ui/format';
	import { auditActionLabel, companyStateLabel, subscriptionNotice } from '$lib/ui/messages';
	import { m } from '$lib/paraglide/messages.js';
	import type { ActionData, PageData } from './$types';

	let { data, form }: { data: PageData; form: ActionData } = $props();

	let guardando = $state(false);
	let entrando = $state(false);

	const c = $derived(data.company);
	const s = $derived(data.company.suscripcion);
	const errores = $derived(form?.errors ?? {});

	const IDIOMAS: Record<string, () => string> = {
		es: () => m.language_es(),
		en: () => m.language_en(),
		pt: () => m.language_pt()
	};
	const idioma = (codigo: string) => (IDIOMAS[codigo] ?? (() => codigo))();

	/** El aviso que este cliente está viendo hoy en su POS. */
	const aviso = $derived(subscriptionNotice(s));
</script>

<PageHeader title={c.nombre} description={m.admin_pair({ afiliado: c.afiliado, compania: c.compania })}>
	{#snippet actions()}
		<a href="/admin" class="btn btn-ghost">
			<Icon name="back" size={15} />
			{m.admin_back()}
		</a>
	{/snippet}
</PageHeader>

{#if data.recienCreada}
	<p
		class="mb-4 flex items-start gap-2 rounded-lg border border-[var(--positive)] bg-[var(--positive-bg)] p-3 text-sm text-[var(--positive)]"
	>
		<Icon name="check" size={15} class="mt-0.5 shrink-0" />
		{m.admin_created({ nombre: c.nombre, sucursal: '001', caja: '00001' })}
	</p>
{/if}

{#if errores.form}
	<p
		class="mb-4 flex items-start gap-2 rounded-lg border border-[var(--negative)] bg-[var(--negative-bg)] p-3 text-sm text-[var(--negative)]"
	>
		<Icon name="alert" size={15} class="mt-0.5 shrink-0" />
		{errores.form}
	</p>
{/if}

<div class="grid gap-4 lg:grid-cols-3">
	<!-- Datos y uso -->
	<section class="card p-4">
		<h2 class="mb-3 text-sm font-bold text-[var(--text)]">{m.admin_section_business()}</h2>
		<dl class="grid gap-2 text-sm">
			<div>
				<dt class="text-[11px] text-[var(--text-subtle)] uppercase">{m.admin_col_client()}</dt>
				<dd class="font-mono text-xs text-[var(--text)]">
					{m.admin_pair({ afiliado: c.afiliado, compania: c.compania })}
				</dd>
			</div>
			<div>
				<dt class="text-[11px] text-[var(--text-subtle)] uppercase">
					{m.admin_label_identification()}
				</dt>
				<dd class="text-[var(--text)]">
					{c.identificacion ? m.admin_company_id({ identificacion: c.identificacion }) : m.admin_company_no_id()}
				</dd>
			</div>
			{#if c.creada_el}
				<div>
					<dt class="text-[11px] text-[var(--text-subtle)] uppercase">{m.admin_col_when()}</dt>
					<dd class="text-[var(--text)]">
						{m.admin_company_since({ fecha: formatDate(c.creada_el) })}
					</dd>
				</div>
			{/if}
			<div>
				<dt class="text-[11px] text-[var(--text-subtle)] uppercase">
					{m.admin_languages_title()}
				</dt>
				<dd class="text-[var(--text)]">
					{idioma(c.locale)} · {idioma(c.document_locale)}
				</dd>
			</div>
		</dl>

		<h3 class="mt-4 mb-2 text-xs font-bold text-[var(--text)] uppercase">{m.admin_admins()}</h3>
		{#if c.administradores.length === 0}
			<p class="text-xs text-[var(--warning)]">{m.admin_no_admins()}</p>
		{:else}
			<ul class="space-y-1 text-xs text-[var(--text-muted)]">
				{#each c.administradores as correo (correo)}
					<li class="flex items-center gap-1.5">
						<Icon name="mail" size={12} class="shrink-0" />
						<span class="truncate">{correo}</span>
					</li>
				{/each}
			</ul>
		{/if}

		<h3 class="mt-4 mb-2 text-xs font-bold text-[var(--text)] uppercase">{m.admin_usage_title()}</h3>
		<ul class="space-y-1 text-xs text-[var(--text-muted)]">
			<li>
				{c.uso.cupo_usuarios === null
					? m.admin_usage_users_unlimited({ used: c.uso.usuarios })
					: m.admin_usage_users({ used: c.uso.usuarios, max: c.plan?.max_usuarios ?? 0 })}
			</li>
			<li>
				{c.uso.cupo_terminales === null
					? m.admin_usage_terminals_unlimited({ used: c.uso.terminales })
					: m.admin_usage_terminals({ used: c.uso.terminales, max: c.plan?.max_terminales ?? 0 })}
			</li>
			<li>{m.admin_usage_products({ count: c.uso.productos })}</li>
			<li>
				{c.uso.ventas_del_mes === 0
					? m.admin_usage_no_sales()
					: m.admin_usage_sales({
							count: c.uso.ventas_del_mes,
							total: formatAmount(c.uso.total_del_mes)
						})}
			</li>
		</ul>
	</section>

	<!-- Suscripción -->
	<section class="card p-4">
		<h2 class="mb-3 text-sm font-bold text-[var(--text)]">{m.admin_subscription_title()}</h2>

		<div class="mb-3 grid gap-1 text-xs">
			<p class="text-[var(--text-muted)]">
				{m.admin_subscription_stored()}: <strong class="text-[var(--text)]">{companyStateLabel(s.guardado)}</strong>
			</p>
			<p class="text-[var(--text-muted)]">
				{m.admin_subscription_effective()}: <strong class="text-[var(--text)]">{companyStateLabel(s.estado)}</strong>
			</p>
			{#if s.estado !== s.guardado}
				<!--
					La fecha ya pasó y el sistema lo está tratando como vencido aunque la
					columna diga otra cosa. Se dice en pantalla porque si no, quien mira
					la ficha ve «activa» y no entiende la llamada del cliente.
				-->
				<p class="text-[var(--warning)]">
					{m.admin_subscription_derived({
						guardado: companyStateLabel(s.guardado),
						efectivo: companyStateLabel(s.estado)
					})}
				</p>
			{/if}
			{#if aviso}
				<p class="mt-1 rounded-lg bg-[var(--surface-sunken)] p-2 text-[var(--text-muted)]">
					{aviso}
				</p>
			{/if}
		</div>

		<form
			method="POST"
			action="?/suscripcion"
			class="grid gap-3"
			use:enhance={submit({ setBusy: (ocupado) => (guardando = ocupado) })}
		>
			<div>
				<label class="label" for="estado">{m.admin_label_state()}</label>
				<select id="estado" name="estado" class="input">
					{#each data.estados as estado (estado)}
						<option value={estado} selected={estado === s.guardado}>
							{companyStateLabel(estado)}
						</option>
					{/each}
				</select>
			</div>

			<Field
				label={m.admin_label_expires()}
				name="vence_el"
				type="date"
				value={s.vence_el ?? ''}
				error={errores.vence_el}
			/>

			<div>
				<label class="label" for="plan_id">{m.admin_label_plan()}</label>
				<select id="plan_id" name="plan_id" class="input">
					{#each data.plans as plan (plan.id)}
						<option value={plan.id} selected={plan.id === c.plan?.id}>{plan.nombre}</option>
					{/each}
				</select>
			</div>

			<button type="submit" class="btn btn-primary" disabled={guardando}>
				{#if guardando}
					<Spinner size={14} />
				{:else}
					<Icon name="check" size={15} />
				{/if}
				{m.admin_subscription_save()}
			</button>
		</form>
	</section>

	<!-- Entrar como -->
	<section class="card p-4">
		<h2 class="mb-1 text-sm font-bold text-[var(--text)]">{m.admin_enter_title()}</h2>
		<p class="mb-3 text-xs text-[var(--text-muted)]">
			{m.admin_enter_intro({ minutos: data.minutosDeVisita })}
		</p>

		<form
			method="POST"
			action="?/entrar"
			class="grid gap-3"
			use:enhance={submit({ setBusy: (ocupado) => (entrando = ocupado) })}
		>
			<div>
				<label class="label" for="motivo">{m.admin_enter_reason()}</label>
				<textarea
					id="motivo"
					name="motivo"
					class="input"
					rows="3"
					required
					aria-invalid={errores.motivo ? 'true' : undefined}
				></textarea>
				{#if errores.motivo}
					<p class="mt-1 text-xs text-[var(--negative)]">{errores.motivo}</p>
				{/if}
				<p class="mt-1 text-[11px] text-[var(--text-subtle)]">{m.admin_enter_reason_hint()}</p>
			</div>

			<button type="submit" class="btn btn-ghost" disabled={entrando}>
				{#if entrando}
					<Spinner size={14} />
				{:else}
					<Icon name="eye" size={15} />
				{/if}
				{m.admin_enter()}
			</button>
		</form>
	</section>
</div>

<!-- La bitácora de esta compañía -->
<section class="card mt-4 p-4">
	<div class="mb-3 flex items-center justify-between gap-3">
		<h2 class="text-sm font-bold text-[var(--text)]">{m.admin_audit_recent()}</h2>
		<a href="/admin/bitacora?company_id={c.id}" class="text-xs text-[var(--accent-text)] hover:underline">
			{m.admin_audit_see_all()}
		</a>
	</div>

	{#if data.lineas.length === 0}
		<p class="text-xs text-[var(--text-muted)]">{m.admin_audit_empty()}</p>
	{:else}
		<div class="table-wrap">
			<table class="data-table">
				<thead>
					<tr>
						<th>{m.admin_col_when()}</th>
						<th>{m.admin_col_who()}</th>
						<th>{m.admin_col_what()}</th>
						<th>{m.admin_col_detail()}</th>
					</tr>
				</thead>
				<tbody>
					{#each data.lineas as linea (linea.id)}
						<tr>
							<td class="text-xs whitespace-nowrap">{formatDateTime(linea.creado_el)}</td>
							<td class="text-xs">
								{linea.nombre ?? linea.email ?? m.admin_audit_unknown_user({ id: linea.user_id })}
							</td>
							<td class="text-xs">{auditActionLabel(linea.accion)}</td>
							<td class="text-xs text-[var(--text-muted)]">{linea.detalle ?? ''}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{/if}
</section>
