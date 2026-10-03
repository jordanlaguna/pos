<script lang="ts">
	import { enhance } from '$app/forms';
	import Icon from '$lib/ui/components/Icon.svelte';
	import PageHeader from '$lib/ui/components/PageHeader.svelte';
	import Field from '$lib/ui/components/Field.svelte';
	import Spinner from '$lib/ui/components/Spinner.svelte';
	import IssuerLocationFields from '$lib/ui/components/IssuerLocationFields.svelte';
	import { submit } from '$lib/ui/forms';
	import { companyStateLabel } from '$lib/ui/messages';
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
				<label class="label" for="alta-tipo-identificacion">{m.settings_id_type()}</label>
				<select
					id="alta-tipo-identificacion"
					name="tipo_identificacion"
					class="input"
					value={previo.tipo_identificacion ?? ''}
				>
					<option value="">{m.admin_issuer_type_auto()}</option>
					{#each ID_TYPES as tipo (tipo.code)}
						<option value={tipo.code}>{tipo.label}</option>
					{/each}
				</select>
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
					value={previo.afiliado ?? ''}
					error={errores.afiliado}
				/>
				<Field
					label={m.admin_label_company_number()}
					name="compania"
					type="number"
					min="1"
					value={previo.compania ?? ''}
					error={errores.compania}
				/>
			</div>
			<p class="text-[11px] text-[var(--text-subtle)]">{m.admin_label_pair_hint()}</p>

			<div class="grid gap-3 sm:grid-cols-2">
				<div>
					<label class="label" for="locale">{m.admin_label_locale()}</label>
					<select id="locale" name="locale" class="input">
						{#each IDIOMAS as idioma (idioma.value)}
							<option value={idioma.value} selected={(previo.locale ?? 'es') === idioma.value}>
								{idioma.label}
							</option>
						{/each}
					</select>
				</div>
				<div>
					<label class="label" for="document_locale">{m.admin_label_document_locale()}</label>
					<select id="document_locale" name="document_locale" class="input">
						{#each IDIOMAS as idioma (idioma.value)}
							<option
								value={idioma.value}
								selected={(previo.document_locale ?? 'es') === idioma.value}
							>
								{idioma.label}
							</option>
						{/each}
					</select>
				</div>
			</div>
			<p class="text-[11px] text-[var(--text-subtle)]">{m.admin_label_document_locale_hint()}</p>
		</div>
	</section>

	<section class="card p-4">
		<h2 class="mb-3 text-sm font-bold text-[var(--text)]">{m.admin_section_subscription()}</h2>

		<div class="grid gap-3">
			<div>
				<label class="label" for="plan_id">{m.admin_label_plan()}</label>
				<select id="plan_id" name="plan_id" class="input" aria-invalid={errores.plan_id ? 'true' : undefined}>
					{#each data.plans as plan (plan.id)}
						<option value={plan.id} selected={String(previo.plan_id ?? '') === String(plan.id)}>
							{plan.nombre}
						</option>
					{/each}
				</select>
				{#if errores.plan_id}
					<p class="mt-1 text-xs text-[var(--negative)]">{errores.plan_id}</p>
				{/if}
			</div>

			<div class="grid grid-cols-2 gap-3">
				<div>
					<label class="label" for="estado">{m.admin_label_state()}</label>
					<select id="estado" name="estado" class="input">
						{#each data.estados as estado (estado)}
							<option value={estado} selected={(previo.estado ?? 'prueba') === estado}>
								{companyStateLabel(estado)}
							</option>
						{/each}
					</select>
				</div>
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
