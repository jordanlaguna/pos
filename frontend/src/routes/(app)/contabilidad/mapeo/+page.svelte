<script lang="ts">
	import { enhance } from '$app/forms';
	import { submit } from '$lib/ui/forms';
	import { m } from '$lib/paraglide/messages.js';
	import { eventLabel } from '$lib/ui/accounting';
	import type { ActionData, PageData } from './$types';

	let { data, form }: { data: PageData; form: ActionData } = $props();

	/** Agrupado por movimiento: es como se lee y como se corrige. */
	const porEvento = $derived(
		[...new Set(data.mapeo.map((fila) => fila.event))].map((evento) => ({
			evento,
			filas: data.mapeo.filter((fila) => fila.event === evento)
		}))
	);
</script>

{#if form?.success}
	<p class="mb-4 rounded-lg bg-[var(--success-soft)] px-3 py-2 text-sm">{form.success}</p>
{/if}
{#if form?.errors?.form}
	<p class="mb-4 rounded-lg bg-[var(--danger-soft)] px-3 py-2 text-sm">{form.errors.form}</p>
{/if}

<div class="mb-3">
	<h2 class="text-sm font-semibold">{m.accounting_mapping_title()}</h2>
	<p class="mt-1 max-w-3xl text-xs text-[var(--text-subtle)]">{m.accounting_mapping_hint()}</p>
</div>

<form method="POST" action="?/guardar" use:enhance={submit()}>
	<div class="grid gap-4">
		{#each porEvento as grupo (grupo.evento)}
			<div class="card p-4">
				<h3 class="mb-2 text-sm font-semibold">{eventLabel(grupo.evento)}</h3>
				<div class="grid gap-2 sm:grid-cols-2">
					{#each grupo.filas as fila (fila.event + fila.role)}
						<label class="flex items-center gap-2 text-sm">
							<span
								class="w-44 shrink-0 truncate font-mono text-xs {fila.account_id === null &&
								!fila.unmapped_on_purpose
									? 'text-[var(--danger)]'
									: 'text-[var(--text-subtle)]'}"
							>
								{fila.role}
							</span>
							{#if fila.unmapped_on_purpose}
								<span class="text-xs text-[var(--text-subtle)]">
									{m.accounting_mapping_on_purpose()}
								</span>
							{:else}
								<select name="{fila.event}|{fila.role}" class="input" value={fila.account_id ?? ''}>
									<option value="">{m.accounting_mapping_missing()}</option>
									{#each data.cuentas as cuenta (cuenta.id)}
										<option value={cuenta.id}>{cuenta.code} · {cuenta.name}</option>
									{/each}
								</select>
							{/if}
						</label>
					{/each}
				</div>
			</div>
		{/each}
	</div>

	<div class="mt-4">
		<button type="submit" class="btn btn-primary">{m.common_save()}</button>
	</div>
</form>
