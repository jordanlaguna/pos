<script lang="ts">
	import { enhance } from '$app/forms';
	import { submit } from '$lib/ui/forms';
	import Icon from '$lib/ui/components/Icon.svelte';
	import PageHeader from '$lib/ui/components/PageHeader.svelte';
	import Modal from '$lib/ui/components/Modal.svelte';
	import Field from '$lib/ui/components/Field.svelte';
	import EmptyState from '$lib/ui/components/EmptyState.svelte';
	import { formatMoney } from '$lib/domain/money';
	import { formatDate } from '$lib/ui/format';
	import { m } from '$lib/paraglide/messages.js';
	import type { PayablePurchase, PayableSupplier } from '$lib/domain/types';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	/** La factura que se está abonando, con su proveedor para armar el motivo. */
	let abonando = $state<{ proveedor: PayableSupplier; compra: PayablePurchase } | null>(null);
	let monto = $state('');
	let metodo = $state('transfer');

	$effect(() => {
		if (abonando === null) return;
		// Se propone el saldo completo: abonar de más no se puede (RN-55) y lo
		// más común es cancelar la factura de una vez.
		monto = String(abonando.compra.balance);
	});

	/**
	 * El motivo del movimiento de caja, armado acá (RN-30).
	 *
	 * El backend no escribe texto para personas, así que si esto no lo armara, el
	 * arqueo mostraría una salida sin explicación —o peor, en español para quien
	 * tiene la pantalla en otro idioma—.
	 */
	const motivo = $derived(
		abonando
			? m.payment_reason({
					supplier: abonando.proveedor.name,
					document: abonando.compra.document_number ?? `#${abonando.compra.entry_id}`
				})
			: ''
	);

	/** El rótulo del tramo. El backend manda el número; la frase va acá. */
	function tramoRotulo(bucket: number): string {
		switch (bucket) {
			case 30:
				return m.payables_bucket_30();
			case 60:
				return m.payables_bucket_60();
			case 90:
				return m.payables_bucket_90();
			default:
				return m.payables_bucket_0();
		}
	}

	/** Cuán vieja es una deuda, en palabras. */
	function antiguedad(compra: PayablePurchase): string {
		if (compra.days_overdue === null) return m.payables_no_due();
		if (compra.days_overdue > 0) return m.payables_overdue({ days: compra.days_overdue });
		if (compra.days_overdue === 0) return m.payables_due_today();
		return m.payables_due_in({ days: -compra.days_overdue });
	}
</script>

<PageHeader title={m.payables_title()} description={m.payables_description()}>
	{#snippet actions()}
		<a href="/compras/proveedores" class="btn btn-ghost">
			<Icon name="truck" size={15} />
			{m.purchases_tab_suppliers()}
		</a>
	{/snippet}
</PageHeader>

<div class="mb-4 grid gap-3 sm:grid-cols-5">
	<div class="card p-3">
		<p class="text-xs font-semibold tracking-wide text-[var(--text-subtle)] uppercase">
			{m.payables_total()}
		</p>
		<p class="mt-1 text-xl font-bold text-[var(--text)]">{formatMoney(data.payables.total)}</p>
		<p class="mt-0.5 text-xs text-[var(--text-subtle)]">
			{m.payables_as_of({ date: formatDate(data.payables.as_of) })}
		</p>
	</div>
	{#each data.payables.by_bucket as tramo (tramo.bucket)}
		<!-- Los cuatro siempre, aunque vayan en cero: una tabla que cambia de
		     columnas según los datos se lee distinto cada vez. -->
		<div class="card p-3 {tramo.bucket >= 60 && tramo.balance > 0 ? 'border-[var(--negative)]' : ''}">
			<p class="text-xs font-semibold tracking-wide text-[var(--text-subtle)] uppercase">
				{tramoRotulo(tramo.bucket)}
			</p>
			<p
				class="mt-1 text-lg font-bold {tramo.bucket >= 60 && tramo.balance > 0
					? 'text-[var(--negative)]'
					: 'text-[var(--text)]'}"
			>
				{formatMoney(tramo.balance)}
			</p>
		</div>
	{/each}
</div>

{#each data.payables.suppliers as proveedor (proveedor.supplier_id)}
	<div class="card mb-4 overflow-hidden">
		<div class="flex items-center justify-between border-b border-[var(--border)] px-4 py-3">
			<h2 class="text-sm font-bold text-[var(--text)]">{proveedor.name}</h2>
			<p class="text-sm font-semibold tabular-nums text-[var(--text)]">
				{m.payables_supplier_balance({ balance: formatMoney(proveedor.balance) })}
			</p>
		</div>
		<div class="table-wrap">
			<table class="data-table">
				<thead>
					<tr>
						<th scope="col">{m.payables_col_document()}</th>
						<th scope="col">{m.payables_col_document_date()}</th>
						<th scope="col">{m.payables_col_due()}</th>
						<th scope="col">{m.payables_col_age()}</th>
						<th scope="col" class="num">{m.payables_col_total()}</th>
						<th scope="col" class="num">{m.payables_col_paid()}</th>
						<th scope="col" class="num">{m.payables_col_balance()}</th>
						<th scope="col"><span class="sr-only">{m.common_actions()}</span></th>
					</tr>
				</thead>
				<tbody>
					{#each proveedor.purchases as compra (compra.entry_id)}
						<tr>
							<td class="font-mono text-xs">{compra.document_number ?? `#${compra.entry_id}`}</td>
							<td class="whitespace-nowrap text-xs">{formatDate(compra.document_date)}</td>
							<td class="whitespace-nowrap text-xs">{formatDate(compra.due_date)}</td>
							<td class="text-xs {compra.bucket >= 30 ? 'text-[var(--negative)]' : 'text-[var(--text-muted)]'}">
								{antiguedad(compra)}
							</td>
							<td class="num tabular-nums">{formatMoney(compra.total)}</td>
							<td class="num tabular-nums text-[var(--text-muted)]">{formatMoney(compra.paid)}</td>
							<td class="num font-semibold tabular-nums">{formatMoney(compra.balance)}</td>
							<td class="text-right">
								<button
									type="button"
									class="btn btn-ghost h-8 px-2 text-xs"
									onclick={() => (abonando = { proveedor, compra })}
									aria-label={m.payables_pay_action({
										document: compra.document_number ?? `#${compra.entry_id}`
									})}
								>
									{m.payables_pay()}
								</button>
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	</div>
{:else}
	<div class="card p-6">
		<EmptyState icon="check" title={m.payables_none()} description={m.payables_none_hint()} />
	</div>
{/each}

<!-- ------------------------------------------------------------- abonar -->
<Modal
	open={abonando !== null}
	title={m.payment_title()}
	description={abonando
		? m.payment_subtitle({
				supplier: abonando.proveedor.name,
				document: abonando.compra.document_number ?? `#${abonando.compra.entry_id}`
			})
		: undefined}
	size="sm"
	onclose={() => (abonando = null)}
>
	{#if abonando}
		<form
			id="form-abono"
			method="POST"
			action="?/abonar"
			use:enhance={submit({
				errorTitle: m.payment_failed(),
				onSuccess: () => (abonando = null)
			})}
			class="grid gap-4"
		>
			<input type="hidden" name="entry_id" value={abonando.compra.entry_id} />
			<input type="hidden" name="reason" value={motivo} />

			<p class="text-sm text-[var(--text-muted)]">
				{m.payment_balance({ balance: formatMoney(abonando.compra.balance) })}
			</p>

			<Field
				label={m.payment_label_amount()}
				name="amount"
				bind:value={monto}
				inputmode="decimal"
				required
			/>

			<div>
				<label class="label" for="metodo-abono">{m.payment_label_method()}</label>
				<select id="metodo-abono" name="method" bind:value={metodo} class="input">
					<option value="transfer">{m.payment_method_transfer()}</option>
					<option value="cash">{m.payment_method_cash()}</option>
					<option value="other">{m.payment_method_other()}</option>
				</select>
				{#if metodo === 'cash'}
					<!-- RN-56: el efectivo sale de la caja abierta o no sale. Vale
					     decirlo antes de que el «no» lo diga después. -->
					<p class="mt-1 text-xs text-[var(--warning)]">{m.payment_cash_warning()}</p>
				{/if}
			</div>

			<Field
				label={m.payment_label_reference()}
				name="reference"
				hint={m.payment_reference_hint()}
			/>
		</form>
	{/if}

	{#snippet footer()}
		<button type="button" class="btn btn-ghost" onclick={() => (abonando = null)}>
			{m.common_cancel()}
		</button>
		<button type="submit" form="form-abono" class="btn btn-primary">
			<Icon name="check" size={15} />
			{m.payment_confirm()}
		</button>
	{/snippet}
</Modal>
