<script lang="ts">
	import { enhance } from '$app/forms';
	import { submit } from '$lib/ui/forms';
	import Icon from '$lib/ui/components/Icon.svelte';
	import PageHeader from '$lib/ui/components/PageHeader.svelte';
	import Modal from '$lib/ui/components/Modal.svelte';
	import Field from '$lib/ui/components/Field.svelte';
	import { m } from '$lib/paraglide/messages.js';
	import type { StockReason } from '$lib/domain/types';
	import type { ActionData, PageData } from './$types';

	let { data, form }: { data: PageData; form: ActionData } = $props();

	let fCode = $state('');
	let fName = $state('');
	let editando = $state<StockReason | null>(null);
	let fNuevoNombre = $state('');
	let submitting = $state(false);

	function abrirRenombrar(motivo: StockReason) {
		editando = motivo;
		fNuevoNombre = motivo.name;
	}
</script>

<PageHeader title={m.reasons_title()} description={m.reasons_description()}>
	{#snippet actions()}
		<a href="/inventario/salidas" class="btn btn-ghost">
			<Icon name="back" size={15} />
			{m.reasons_back()}
		</a>
	{/snippet}
</PageHeader>

<div class="grid gap-4 lg:grid-cols-[1fr_2fr]">
	<!-- ------------------------------------------------------------ alta -->
	<form
		method="POST"
		action="?/crear"
		class="card h-fit space-y-3 p-4"
		use:enhance={submit({
			onSuccess: () => {
				fCode = '';
				fName = '';
			},
			setBusy: (v) => (submitting = v)
		})}
	>
		<h2 class="text-sm font-semibold text-[var(--text)]">{m.reasons_new()}</h2>
		<Field
			label={m.reasons_code_label()}
			name="code"
			bind:value={fCode}
			required
			hint={m.reasons_code_hint()}
			error={form?.action === 'crear' ? form?.errors?.code : undefined}
		/>
		<Field
			label={m.reasons_name_label()}
			name="name"
			bind:value={fName}
			required
			error={form?.action === 'crear' ? form?.errors?.name : undefined}
		/>
		{#if form?.action === 'crear' && form?.errors?.form}
			<p class="rounded-lg bg-[var(--negative-bg)] p-2 text-sm text-[var(--negative)]" role="alert">
				{form.errors.form}
			</p>
		{/if}
		<button type="submit" class="btn btn-primary w-full" disabled={submitting}>
			<Icon name="plus" size={15} />
			{m.reasons_create()}
		</button>
	</form>

	<!-- ----------------------------------------------------------- lista -->
	<div class="card overflow-hidden">
		<div class="table-wrap">
			<table class="data-table">
				<thead>
					<tr>
						<th scope="col">{m.reasons_col_code()}</th>
						<th scope="col">{m.reasons_col_name()}</th>
						<th scope="col">{m.reasons_col_status()}</th>
						<th scope="col"><span class="sr-only">{m.common_actions()}</span></th>
					</tr>
				</thead>
				<tbody>
					{#each data.reasons as motivo (motivo.id)}
						<tr class:opacity-60={!motivo.is_active} data-testid="reason-row" data-code={motivo.code}>
							<td class="font-mono text-xs">{motivo.code}</td>
							<td>{motivo.name}</td>
							<td>
								{#if motivo.is_system}
									<span class="badge bg-[var(--surface-sunken)] text-[var(--text-muted)]">
										<Icon name="lock" size={11} />
										{m.reasons_system()}
									</span>
								{:else if motivo.is_active}
									<span class="badge bg-[var(--positive-bg)] text-[var(--positive)]">
										<Icon name="check" size={11} />
										{m.reasons_active()}
									</span>
								{:else}
									<span class="badge bg-[var(--negative-bg)] text-[var(--negative)]">
										<Icon name="close" size={11} />
										{m.reasons_inactive()}
									</span>
								{/if}
							</td>
							<td>
								<div class="flex justify-end gap-1">
									<button
										type="button"
										class="rounded-lg p-1.5 text-[var(--text-subtle)] hover:bg-[var(--surface-sunken)] hover:text-[var(--accent)]"
										onclick={() => abrirRenombrar(motivo)}
										aria-label={m.reasons_rename({ reason: motivo.name })}
									>
										<Icon name="edit" size={15} />
									</button>
									{#if !motivo.is_system}
										<!-- Apagar y encender van por formulario: funcionan sin
										     JavaScript y no exigen confirmación, porque se deshacen
										     con el mismo botón. -->
										<form method="POST" action="?/activar" use:enhance={submit({})}>
											<input type="hidden" name="id" value={motivo.id} />
											<input type="hidden" name="is_active" value={motivo.is_active ? 'false' : 'true'} />
											<button
												type="submit"
												class="rounded-lg p-1.5 text-[var(--text-subtle)] hover:bg-[var(--surface-sunken)] hover:text-[var(--accent)]"
												aria-label={motivo.is_active
													? m.reasons_deactivate({ reason: motivo.name })
													: m.reasons_activate({ reason: motivo.name })}
											>
												<Icon name={motivo.is_active ? 'eyeoff' : 'eye'} size={15} />
											</button>
										</form>
									{/if}
								</div>
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
		<p class="border-t border-[var(--border)] p-3 text-xs text-[var(--text-subtle)]">
			{m.reasons_system_note()}
		</p>
	</div>
</div>

<!-- -------------------------------------------------------- renombrar -->
<Modal
	open={editando !== null}
	title={m.reasons_edit_title()}
	description={editando?.name}
	size="sm"
	busy={submitting}
	onclose={() => (editando = null)}
>
	<form
		id="form-renombrar"
		method="POST"
		action="?/renombrar"
		use:enhance={submit({
			onSuccess: () => (editando = null),
			setBusy: (v) => (submitting = v)
		})}
	>
		<input type="hidden" name="id" value={editando?.id ?? ''} />
		<Field
			label={m.reasons_name_label()}
			name="name"
			bind:value={fNuevoNombre}
			required
			error={form?.action === 'renombrar' ? form?.errors?.name : undefined}
		/>
	</form>
	{#snippet footer()}
		<button type="button" class="btn btn-ghost" onclick={() => (editando = null)}>{m.common_cancel()}</button>
		<button type="submit" form="form-renombrar" class="btn btn-primary" disabled={submitting}>
			{m.common_save()}
		</button>
	{/snippet}
</Modal>
