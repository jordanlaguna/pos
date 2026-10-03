<script lang="ts">
	import { enhance } from '$app/forms';
	import Icon from '$lib/ui/components/Icon.svelte';
	import PageHeader from '$lib/ui/components/PageHeader.svelte';
	import Field from '$lib/ui/components/Field.svelte';
	import Select from '$lib/ui/components/Select.svelte';
	import Spinner from '$lib/ui/components/Spinner.svelte';
	import IssuerLocationFields from '$lib/ui/components/IssuerLocationFields.svelte';
	import { submit } from '$lib/ui/forms';
	import { untrack } from 'svelte';
	import { nextAffiliate, nextCompanyOf } from '$lib/domain/affiliates';
	import { companyStateLabel, moduleLabel } from '$lib/ui/messages';
	import { MODULES } from '$lib/domain/types';
	import { ID_TYPES } from '$lib/domain/settings';
	import { EMPTY_LOCATION } from '$lib/domain/location';
	import { m } from '$lib/paraglide/messages.js';
	import type { ActionData, PageData } from './$types';

	let { data, form }: { data: PageData; form: ActionData } = $props();

	let enviando = $state(false);

	/*
	 * Lo que había escrito, cuando el alta falla.
	 *
	 * Doce campos que se vacían porque el correo estaba repetido son doce campos
	 * que se llenan dos veces. La contraseña no vuelve, a propósito: el servidor
	 * no la manda de regreso.
	 */
	const previo = $derived(form?.valores ?? {});
	const errores = $derived(form?.errors ?? {});

	/*
	 * La ubicación del emisor (RF-73, T-722). Opcional al dar de alta —la compañía
	 * que no emite no la necesita, y el dueño la completa en Configuración—, pero
	 * si soporte la tiene a mano, que quede desde el primer día.
	 */
	let ubicacion = $state({ ...EMPTY_LOCATION });

	/*
	 * La numeración que se propone (QA-04): el siguiente afiliado libre y, para
	 * el afiliado que esté escrito, su siguiente compañía. Si soporte escribe un
	 * afiliado que ya existe, la compañía lo sigue; si cambió la compañía a mano,
	 * se respeta. Si el alta falló, vuelve lo que había escrito.
	 */
	const inicial = untrack(() => ({
		afiliado: String(previo.afiliado ?? nextAffiliate(data.pares)),
		compania: previo.compania == null ? null : String(previo.compania)
	}));
	let afiliado = $state<string | number>(inicial.afiliado);
	let sugerida = untrack(() => String(nextCompanyOf(data.pares, Number(inicial.afiliado))));
	let compania = $state<string | number>(inicial.compania ?? sugerida);

	/*
	 * El plan elegido: el que volvió si el alta falló, si no el primero.
	 *
	 * Las listas de esta ficha van **sin controlar** —`selected` en la opción y
	 * no `value`—, como el idioma del menú: con `value`, Svelte las reinicia al
	 * hidratar y se come lo que se eligió antes. La de plan se enlaza igual,
	 * para mostrar lo que trae, pero nace en `undefined`: así `Select` toma la
	 * opción marcada en vez de imponer la suya.
	 */
	const planInicial = untrack(() => String(previo.plan_id ?? data.plans[0]?.id ?? ''));
	let planElegido = $state<string | undefined>(undefined);
	const planActual = $derived(
		data.plans.find((plan) => String(plan.id) === String(planElegido ?? planInicial))
	);

	$effect(() => {
		const nueva = String(nextCompanyOf(data.pares, Number(afiliado)));
		untrack(() => {
			// `String`: con `type="number"` el campo puede devolver un número.
			if (String(compania) === sugerida) compania = nueva;
			sugerida = nueva;
		});
	});

	const IDIOMAS = $derived(
		data.locales.map((codigo) => ({
			value: codigo,
			label:
				codigo === 'es' ? m.language_es() : codigo === 'en' ? m.language_en() : m.language_pt()
		}))
	);
</script>

<PageHeader title={m.admin_new_title()} description={m.admin_new_intro()}>
	{#snippet actions()}
		<a href="/admin" class="btn btn-ghost">
			<Icon name="back" size={15} />
			{m.admin_back()}
		</a>
	{/snippet}
</PageHeader>

{#if errores.form}
	<p
		class="mb-4 flex items-start gap-2 rounded-lg border border-[var(--negative)] bg-[var(--negative-bg)] p-3 text-sm text-[var(--negative)]"
	>
		<Icon name="alert" size={15} class="mt-0.5 shrink-0" />
		{errores.form}
	</p>
{/if}

<form
	method="POST"
	class="grid gap-4 lg:grid-cols-2"
	use:enhance={submit({ setBusy: (ocupado) => (enviando = ocupado) })}
>
	<section class="card p-4">
		<h2 class="mb-3 text-sm font-bold text-[var(--text)]">{m.admin_section_business()}</h2>

		<div class="grid gap-3">
			<Field
				label={m.admin_label_company_name()}
				name="nombre"
				value={previo.nombre ?? ''}
				error={errores.nombre}
				required
			/>
			<Field
				label={m.admin_label_identification()}
				name="identificacion"
				value={previo.identificacion ?? ''}
				error={errores.identificacion}
				hint={m.admin_issuer_hint()}
			/>
			<div>
				<Select
					id="alta-tipo-identificacion"
					name="tipo_identificacion"
					label={m.settings_id_type()}
				>
					<option value="" selected={!previo.tipo_identificacion}>{m.admin_issuer_type_auto()}</option>
					{#each ID_TYPES as tipo (tipo.code)}
						<option value={tipo.code} selected={tipo.code === previo.tipo_identificacion}>{tipo.label}</option>
					{/each}
				</Select>
			</div>

			<fieldset data-ubicacion-alta>
				<legend class="mb-1 text-xs font-bold text-[var(--text)] uppercase">
					{m.settings_location_title()}
				</legend>
				<p class="mb-3 text-xs text-[var(--text-subtle)]">{m.settings_location_hint()}</p>
				<IssuerLocationFields bind:location={ubicacion} errors={errores} />
			</fieldset>

			<div class="grid grid-cols-2 gap-3">
				<Field
					label={m.admin_label_affiliate()}
					name="afiliado"
					type="number"
					min="1"
					bind:value={afiliado}
					error={errores.afiliado}
				/>
				<Field
					label={m.admin_label_company_number()}
					name="compania"
					type="number"
					min="1"
					bind:value={compania}
					error={errores.compania}
				/>
			</div>
			<p class="text-[11px] text-[var(--text-subtle)]">{m.admin_label_pair_hint()}</p>

			<div class="grid gap-3 sm:grid-cols-2">
				<Select id="locale" name="locale" label={m.admin_label_locale()}>
					{#each IDIOMAS as idioma (idioma.value)}
						<option value={idioma.value} selected={(previo.locale ?? 'es') === idioma.value}>{idioma.label}</option>
					{/each}
				</Select>
				<Select
					id="document_locale"
					name="document_locale"
					label={m.admin_label_document_locale()}
				>
					{#each IDIOMAS as idioma (idioma.value)}
						<option value={idioma.value} selected={(previo.document_locale ?? 'es') === idioma.value}>
							{idioma.label}
						</option>
					{/each}
				</Select>
			</div>
			<p class="text-[11px] text-[var(--text-subtle)]">{m.admin_label_document_locale_hint()}</p>
		</div>
	</section>

	<section class="card p-4">
		<h2 class="mb-3 text-sm font-bold text-[var(--text)]">{m.admin_section_subscription()}</h2>

		<div class="grid gap-3">
			<Select
				id="plan_id"
				name="plan_id"
				label={m.admin_label_plan()}
				error={errores.plan_id}
				bind:value={planElegido}
			>
				{#each data.plans as plan (plan.id)}
					<option value={String(plan.id)} selected={String(plan.id) === planInicial}>{plan.nombre}</option>
				{/each}
			</Select>

			<!--
				Lo que trae el paquete elegido (QA-01). El plan decide los módulos
				(RN-49): para cambiarlos se elige otro plan, no se marcan acá.
			-->
			{#if planActual}
				<div data-modulos-del-plan>
					<p class="label">{m.admin_new_plan_modules()}</p>
					<ul class="flex flex-wrap gap-1.5">
						{#each MODULES as nombre (nombre)}
							<li
								class="badge {planActual[nombre]
									? 'bg-[var(--accent-soft)] text-[var(--text)]'
									: 'bg-[var(--surface-sunken)] text-[var(--text-subtle)] line-through'}"
								data-modulo={nombre}
								data-incluido={planActual[nombre] ? 'si' : 'no'}
							>
								{moduleLabel(nombre)}
							</li>
						{/each}
					</ul>
					<p class="mt-1 text-[11px] text-[var(--text-subtle)]">{m.admin_new_plan_modules_hint()}</p>
				</div>
			{/if}

			<div class="grid grid-cols-2 gap-3">
				<Select id="estado" name="estado" label={m.admin_label_state()}>
					{#each data.estados as estado (estado)}
						<option value={estado} selected={(previo.estado ?? 'prueba') === estado}>{companyStateLabel(estado)}</option>
					{/each}
				</Select>
				<Field
					label={m.admin_label_expires()}
					name="vence_el"
					type="date"
					value={previo.vence_el ?? data.vencePropuesto}
					error={errores.vence_el}
				/>
			</div>
			<p class="text-[11px] text-[var(--text-subtle)]">{m.admin_label_expires_hint()}</p>
		</div>
	</section>

	<section class="card p-4 lg:col-span-2">
		<h2 class="mb-3 text-sm font-bold text-[var(--text)]">{m.admin_section_admin()}</h2>

		<div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
			<Field
				label={m.admin_label_email()}
				name="email"
				type="email"
				value={previo.email ?? ''}
				error={errores.email}
				icon="mail"
				required
			/>
			<Field
				label={m.admin_label_password()}
				name="password"
				type="password"
				error={errores.password}
				icon="lock"
				required
			/>
			<Field
				label={m.admin_label_name()}
				name="name"
				value={previo.name ?? ''}
				error={errores.name}
				required
			/>
			<Field
				label={m.admin_label_last_name()}
				name="lastName"
				value={previo.lastName ?? ''}
				error={errores.lastName}
			/>
			<Field
				label={m.admin_label_second_last_name()}
				name="secondName"
				value={previo.secondName ?? ''}
				error={errores.secondName}
			/>
			<Field
				label={m.admin_label_person_identification()}
				name="identification_person"
				value={previo.identification_person ?? ''}
				error={errores.identification_person}
				icon="idcard"
			/>
			<Field
				label={m.admin_label_telephone()}
				name="telephone"
				type="tel"
				value={previo.telephone ?? ''}
				error={errores.telephone}
				icon="phone"
			/>
		</div>

		<div class="mt-4 flex justify-end gap-2">
			<a href="/admin" class="btn btn-ghost">{m.admin_cancel()}</a>
			<button type="submit" class="btn btn-primary" disabled={enviando}>
				{#if enviando}
					<Spinner size={14} />
				{:else}
					<Icon name="check" size={15} />
				{/if}
				{m.admin_create()}
			</button>
		</div>
	</section>
</form>
