<script lang="ts">
	import { enhance } from '$app/forms';
	import Icon from '$lib/ui/components/Icon.svelte';
	import PageHeader from '$lib/ui/components/PageHeader.svelte';
	import Spinner from '$lib/ui/components/Spinner.svelte';
	import Select from '$lib/ui/components/Select.svelte';
	import { submit } from '$lib/ui/forms';
	import { MODULES } from '$lib/domain/types';
	import { moduleLabel } from '$lib/ui/messages';
	import { m } from '$lib/paraglide/messages.js';
	import type { ActionData, PageData } from './$types';

	let { data, form }: { data: PageData; form: ActionData } = $props();

	/**
	 * Cuál plan se está guardando, no un booleano.
	 *
	 * Con un `guardando` compartido, los tres formularios de la pantalla
	 * mostrarían la rueda a la vez y se deshabilitarían juntos al tocar uno solo.
	 */
	let guardandoPlan = $state<number | null>(null);

	/** Qué compañía se está moviendo, por lo mismo: una sola rueda a la vez. */
	let moviendo = $state<number | null>(null);

	const companiasDe = (planId: number) => data.companias.filter((c) => c.plan_id === planId);
</script>

<PageHeader title={m.admin_plans_title()} description={m.admin_plans_intro()} />

{#if form?.errors?.form}
	<p class="mb-3 text-sm text-[var(--negative)]">{form.errors.form}</p>
{/if}
{#if form?.success}
	<p class="mb-3 text-sm text-[var(--positive)]">{form.success}</p>
{/if}

<p class="mb-4 text-xs text-[var(--text-muted)]">{m.admin_plans_warning()}</p>

<div class="grid gap-3">
	{#each data.plans as plan (plan.id)}
		{@const suyas = companiasDe(plan.id)}
		<section class="card p-4">
			<div class="mb-3">
				<h2 class="text-sm font-bold text-[var(--text)]">{plan.nombre}</h2>
				<p class="text-xs text-[var(--text-muted)]">
					{m.admin_plan_limits({
						sucursales: plan.max_sucursales,
						terminales: plan.max_terminales,
						usuarios: plan.max_usuarios
					})}
				</p>
			</div>

			<form
				method="POST"
				action="?/modulos"
				class="flex flex-wrap items-center gap-4"
				use:enhance={submit({
					setBusy: (ocupado) => (guardandoPlan = ocupado ? plan.id : null)
				})}
			>
				<input type="hidden" name="plan_id" value={plan.id} />

				{#each MODULES as nombre (nombre)}
					<label class="flex items-center gap-2 text-sm text-[var(--text)]">
						<input type="checkbox" name={nombre} checked={plan[nombre]} class="accent-[var(--accent)]" />
						{moduleLabel(nombre)}
					</label>
				{/each}

				<button
					type="submit"
					class="btn btn-primary ml-auto"
					disabled={guardandoPlan === plan.id}
				>
					{#if guardandoPlan === plan.id}
						<Spinner size={14} />
					{:else}
						<Icon name="check" size={15} />
					{/if}
					{m.admin_plan_modules_save()}
				</button>
			</form>

			<!--
				Las compañías de este plan (QA-03), con su cambio a mano: el plan de un
				cliente cambia con el tiempo y esta es la pantalla desde donde se mira
				quién tiene qué.
			-->
			<div class="mt-4 border-t border-[var(--border)] pt-3" data-companias-plan={plan.id}>
				<h3 class="mb-2 text-xs font-bold text-[var(--text-subtle)] uppercase">
					{m.admin_plans_companies({ count: suyas.length })}
				</h3>
				{#if suyas.length === 0}
					<p class="text-sm text-[var(--text-muted)]">{m.admin_plans_no_companies()}</p>
				{:else}
					<ul class="divide-y divide-[var(--border)]">
						{#each suyas as compania (compania.id)}
							<li class="flex flex-wrap items-center gap-3 py-2" data-compania={compania.id}>
								<a
									href="/admin/companias/{compania.id}"
									class="min-w-0 flex-1 truncate text-sm font-medium text-[var(--text)] hover:text-[var(--accent)]"
								>
									<span class="font-mono text-xs text-[var(--text-subtle)]">
										{compania.afiliado}·{compania.compania}
									</span>
									{compania.nombre}
								</a>
								<form
									method="POST"
									action="?/cambiarPlan"
									class="flex items-center gap-2"
									use:enhance={submit({
										setBusy: (ocupado) => (moviendo = ocupado ? compania.id : null)
									})}
								>
									<input type="hidden" name="company_id" value={compania.id} />
									<Select
										id="plan-de-{compania.id}"
										name="plan_id"
										class="w-44"
										selectClass="h-8 py-0 text-xs"
										aria-label={m.admin_plans_move_label({ nombre: compania.nombre })}
									>
										<!--
											Sin `value`, con `selected`: la lista queda sin controlar, como la
											del idioma del menú. Con `value`, Svelte la reinicia al hidratar y
											se come la elección de quien la tocó antes —se mandaba el plan de
											siempre y la compañía no se movía—.
										-->
										{#each data.plans as opcion (opcion.id)}
											<option value={String(opcion.id)} selected={opcion.id === plan.id}>
												{opcion.nombre}
											</option>
										{/each}
									</Select>
									<button type="submit" class="btn btn-ghost h-8 px-3 text-xs" disabled={moviendo === compania.id}>
										{#if moviendo === compania.id}
											<Spinner size={13} />
										{:else}
											<Icon name="refresh" size={13} />
										{/if}
										{m.admin_plans_move()}
									</button>
								</form>
							</li>
						{/each}
					</ul>
				{/if}
			</div>
		</section>
	{/each}
</div>
