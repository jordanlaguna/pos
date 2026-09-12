<script lang="ts">
	import { enhance } from '$app/forms';
	import Icon from '$lib/ui/components/Icon.svelte';
	import PageHeader from '$lib/ui/components/PageHeader.svelte';
	import Spinner from '$lib/ui/components/Spinner.svelte';
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
		</section>
	{/each}
</div>
