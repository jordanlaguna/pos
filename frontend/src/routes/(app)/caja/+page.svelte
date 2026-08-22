<script lang="ts">
	import { enhance } from '$app/forms';
	import { submit } from '$lib/ui/forms';
	import Icon from '$lib/ui/components/Icon.svelte';
	import PageHeader from '$lib/ui/components/PageHeader.svelte';
	import Modal from '$lib/ui/components/Modal.svelte';
	import Field from '$lib/ui/components/Field.svelte';
	import EmptyState from '$lib/ui/components/EmptyState.svelte';
	import Spinner from '$lib/ui/components/Spinner.svelte';
	import { toasts } from '$lib/ui/stores/toast.svelte';
	import { currencySettings, formatMoney, parseAmount, round2 } from '$lib/domain/money';
	import { formatDateTime, formatInt, formatTime } from '$lib/ui/format';
	import { m } from '$lib/paraglide/messages.js';
	import { paymentLabel } from '$lib/ui/messages';
	import type { ActionData, PageData } from './$types';

	let { data, form }: { data: PageData; form: ActionData } = $props();

	let openModal = $state(false);
	let moveModal = $state(false);
	let closeModal = $state(false);
	let submitting = $state(false);

	let moveType = $state<'entrada' | 'salida'>('entrada');
	let countedInput = $state('');

	const session = $derived(data.current);
	const isOpen = $derived(session != null && session.status === 'abierta');

	/*
	 * La moneda se nombra en los campos donde se escribe efectivo. Quien cuenta la
	 * gaveta está tecleando una cifra suelta, sin símbolo, y tiene que ver en qué
	 * currency se la están pidiendo: la configura el dueño del sistema y no siempre
	 * es la del país donde se escribió este código.
	 */
	const currency = $derived(currencySettings());

	// Diferencia en vivo mientras el cajero cuenta la gaveta, antes de confirmar.
	const counted = $derived(parseAmount(countedInput) ?? 0);
	const previewDifference = $derived(
		session ? round2(counted - session.expected_amount) : 0
	);

	function openCloseModal() {
		countedInput = session ? session.expected_amount.toFixed(2) : '';
		closeModal = true;
	}

	function startMovement(type: 'entrada' | 'salida') {
		moveType = type;
		moveModal = true;
	}

</script>

<PageHeader
	title={m.cash_title()}
	description={m.cash_description()}
>
	{#snippet actions()}
		{#if isOpen}
			<button
				type="button"
				class="btn btn-ghost"
				onclick={() => startMovement('entrada')}
			>
				<Icon name="plus" size={15} />
				{m.cash_movement_in()}
			</button>
			<button type="button" class="btn btn-ghost" onclick={() => startMovement('salida')}>
				<Icon name="minus" size={15} />
				{m.cash_movement_out()}
			</button>
			<button type="button" class="btn btn-primary" onclick={openCloseModal}>
				<Icon name="lock" size={15} />
				{m.cash_close_register()}
			</button>
		{:else}
			<button type="button" class="btn btn-primary" onclick={() => (openModal = true)}>
				<Icon name="wallet" size={15} />
				{m.cash_open_register()}
			</button>
		{/if}
	{/snippet}
</PageHeader>

{#if !isOpen}
	<div class="card p-6">
		<EmptyState
			icon="wallet"
			title={m.cash_closed()}
			description={m.cash_closed_hint()}
		>
			<button type="button" class="btn btn-primary" onclick={() => (openModal = true)}>
				<Icon name="wallet" size={15} />
				{m.cash_open_register()}
			</button>
		</EmptyState>
	</div>
{:else if session}
	<!-- Estado del turno en curso -->
	<div class="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
		<div class="card p-4">
			<p class="text-xs font-semibold tracking-wide text-[var(--text-subtle)] uppercase">
				{m.cash_opening()}
			</p>
			<p class="mt-1 text-xl font-bold text-[var(--text)]">
				{formatMoney(session.opening_amount)}
			</p>
			<p class="mt-1 text-xs text-[var(--text-subtle)]">
				{formatDateTime(session.opened_at)}
			</p>
		</div>

		<div class="card p-4">
			<p class="text-xs font-semibold tracking-wide text-[var(--text-subtle)] uppercase">
				{m.cash_shift_sales()}
			</p>
			<p class="mt-1 text-xl font-bold text-[var(--text)]">
				{formatMoney(session.sales_total)}
			</p>
			<p class="mt-1 text-xs text-[var(--text-subtle)]">
				{m.cash_sales_count({ count: session.sales_count })}
			</p>
		</div>

		<div class="card p-4">
			<p class="text-xs font-semibold tracking-wide text-[var(--text-subtle)] uppercase">
				{m.cash_cash_sales()}
			</p>
			<p class="mt-1 text-xl font-bold text-[var(--text)]">
				{formatMoney(session.cash_sales)}
			</p>
			<p class="mt-1 text-xs text-[var(--text-subtle)]">
				{m.cash_only_cash_hint()}
			</p>
		</div>

		<div class="card border-[var(--accent)] p-4">
			<p class="text-xs font-semibold tracking-wide text-[var(--text-subtle)] uppercase">
				{m.cash_expected_in_register()}
			</p>
			<p class="mt-1 text-xl font-bold text-[var(--accent)]">
				{formatMoney(session.expected_amount)}
			</p>
			<p class="mt-1 text-xs text-[var(--text-subtle)]">{m.cash_expected_formula()}</p>
		</div>
	</div>

	<div class="grid gap-4 lg:grid-cols-2">
		<!-- Desglose -->
		<section class="card p-4">
			<h2 class="mb-3 text-sm font-bold text-[var(--text)]">{m.cash_breakdown()}</h2>

			<dl class="space-y-2 text-sm">
				<div class="flex justify-between">
					<dt class="text-[var(--text-muted)]">{m.cash_opening_amount()}</dt>
					<dd class="tabular-nums text-[var(--text)]">
						{formatMoney(session.opening_amount)}
					</dd>
				</div>
				<div class="flex justify-between">
					<dt class="text-[var(--text-muted)]">{m.cash_sales_in_cash()}</dt>
					<dd class="tabular-nums text-[var(--positive)]">
						+{formatMoney(session.cash_sales)}
					</dd>
				</div>
				<div class="flex justify-between">
					<dt class="text-[var(--text-muted)]">{m.cash_movements_in()}</dt>
					<dd class="tabular-nums text-[var(--positive)]">
						+{formatMoney(session.movements_in)}
					</dd>
				</div>
				<div class="flex justify-between">
					<dt class="text-[var(--text-muted)]">{m.cash_movements_out()}</dt>
					<dd class="tabular-nums text-[var(--negative)]">
						−{formatMoney(session.movements_out)}
					</dd>
				</div>
				<div class="flex justify-between">
					<dt class="text-[var(--text-muted)]">{m.cash_returns()}</dt>
					<dd class="tabular-nums text-[var(--negative)]">
						−{formatMoney(session.returns_total)}
					</dd>
				</div>
				<div
					class="flex justify-between border-t border-[var(--border)] pt-2 text-base font-bold"
				>
					<dt class="text-[var(--text)]">{m.cash_expected_in_drawer()}</dt>
					<dd class="tabular-nums text-[var(--text)]">
						{formatMoney(session.expected_amount)}
					</dd>
				</div>
			</dl>

			{#if session.by_payment_method.length}
				<h3 class="mt-5 mb-2 text-xs font-bold tracking-wide text-[var(--text-subtle)] uppercase">
					{m.cash_by_payment_method()}
				</h3>
				<table class="data-table">
					<thead>
						<tr>
							<th scope="col">{m.cash_col_method()}</th>
							<th scope="col" class="num">{m.cash_col_sales()}</th>
							<th scope="col" class="num">{m.common_total()}</th>
						</tr>
					</thead>
					<tbody>
						{#each session.by_payment_method as row (row.payment_method)}
							<tr>
								<td>{paymentLabel(row.payment_method)}</td>
								<td class="num tabular-nums">{formatInt(row.count)}</td>
								<td class="num tabular-nums">{formatMoney(row.total)}</td>
							</tr>
						{/each}
					</tbody>
				</table>
			{/if}
		</section>

		<!-- Movimientos -->
		<section class="card flex flex-col p-4">
			<h2 class="mb-3 text-sm font-bold text-[var(--text)]">{m.cash_movements()}</h2>

			{#if session.movements.length}
				<ul class="divide-y divide-[var(--border)]">
					{#each session.movements as movement (movement.id)}
						<li class="flex items-center gap-3 py-2.5">
							<span
								class="grid h-8 w-8 shrink-0 place-items-center rounded-full {movement.type ===
								'entrada'
									? 'bg-[var(--positive-bg)] text-[var(--positive)]'
									: 'bg-[var(--negative-bg)] text-[var(--negative)]'}"
							>
								<Icon name={movement.type === 'entrada' ? 'plus' : 'minus'} size={14} />
							</span>
							<div class="min-w-0 flex-1">
								<p class="truncate text-sm text-[var(--text)]">{movement.reason}</p>
								<p class="text-xs text-[var(--text-subtle)]">
									{formatTime(movement.created_at)}
								</p>
							</div>
							<span
								class="shrink-0 text-sm font-semibold tabular-nums {movement.type ===
								'entrada'
									? 'text-[var(--positive)]'
									: 'text-[var(--negative)]'}"
							>
								{movement.type === 'entrada' ? '+' : '−'}{formatMoney(movement.amount)}
							</span>
						</li>
					{/each}
				</ul>
			{:else}
				<EmptyState
					icon="wallet"
					title={m.cash_no_movements()}
					description={m.cash_no_movements_hint()}
					compact
				/>
			{/if}
		</section>
	</div>
{/if}

<!-- Historial de turnos -->
<section class="mt-6">
	<h2 class="mb-3 text-sm font-bold text-[var(--text)]">{m.cash_previous_shifts()}</h2>
	<div class="card overflow-hidden">
		<div class="table-wrap">
			<table class="data-table">
				<thead>
					<tr>
						<th scope="col">{m.cash_col_opened()}</th>
						<th scope="col">{m.cash_col_closed()}</th>
						{#if data.user.role === 'admin'}
							<th scope="col">{m.cash_col_cashier()}</th>
						{/if}
						<th scope="col" class="num">{m.cash_col_initial()}</th>
						<th scope="col" class="num">{m.cash_col_sales()}</th>
						<th scope="col" class="num">{m.cash_col_expected()}</th>
						<th scope="col" class="num">{m.cash_col_counted()}</th>
						<th scope="col" class="num">{m.cash_col_difference()}</th>
					</tr>
				</thead>
				<tbody>
					{#each data.history.filter((s) => s.status === 'cerrada') as row (row.id)}
						<tr>
							<td class="whitespace-nowrap text-xs">{formatDateTime(row.opened_at)}</td>
							<td class="whitespace-nowrap text-xs">{formatDateTime(row.closed_at)}</td>
							{#if data.user.role === 'admin'}
								<td class="text-xs">{row.user_name ?? `#${row.user_id}`}</td>
							{/if}
							<td class="num tabular-nums">{formatMoney(row.opening_amount)}</td>
							<td class="num tabular-nums">{formatMoney(row.sales_total)}</td>
							<td class="num tabular-nums">{formatMoney(row.expected_amount)}</td>
							<td class="num tabular-nums">{formatMoney(row.closing_amount ?? 0)}</td>
							<td class="num">
								{#if row.difference == null || row.difference === 0}
									<span class="badge bg-[var(--positive-bg)] text-[var(--positive)]">
										<Icon name="check" size={11} />
										{m.cash_balanced()}
									</span>
								{:else}
									<span
										class="badge tabular-nums {row.difference > 0
											? 'bg-[var(--info-bg)] text-[var(--info)]'
											: 'bg-[var(--negative-bg)] text-[var(--negative)]'}"
									>
										<Icon name="alert" size={11} />
										{row.difference > 0 ? m.cash_over() : m.cash_short()}
										{formatMoney(Math.abs(row.difference))}
									</span>
								{/if}
							</td>
						</tr>
					{:else}
						<tr>
							<td colspan="8">
								<EmptyState
									icon="clock"
									title={m.cash_no_closed_shifts()}
									description={m.cash_no_closed_shifts_hint()}
									compact
								/>
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	</div>
</section>

<!-- ------------------------------------------------------ abrir caja -->
<Modal
	open={openModal}
	title={m.cash_open_register()}
	description={m.cash_open_hint()}
	size="sm"
	busy={submitting}
	onclose={() => (openModal = false)}
>
	<form
		id="open-form"
		method="POST"
		action="?/abrir"
		use:enhance={submit({
			onSuccess: () => (openModal = false),
			setBusy: (v) => (submitting = v)
		})}
		class="space-y-4"
	>
		<Field
			label={m.cash_opening_amount_in({ currency: currency.code })}
			name="opening_amount"
			value="0"
			inputmode="decimal"
			icon="wallet"
			required
			error={form?.errors?.opening_amount}
			hint={m.cash_opening_amount_hint({ currency: currency.code })}
		>
			<span class="pr-1 text-sm font-semibold text-[var(--text-subtle)]">{currency.symbol}</span>
		</Field>
		<Field
			label={m.cash_notes_optional()}
			name="notes"
			placeholder={m.cash_notes_placeholder()}
			error={form?.errors?.notes}
		/>
	</form>

	{#snippet footer()}
		<button type="button" class="btn btn-ghost" onclick={() => (openModal = false)}>
			{m.common_cancel()}
		</button>
		<button type="submit" form="open-form" class="btn btn-primary" disabled={submitting}>
			{#if submitting}<Spinner size={15} />{m.cash_opening_now()}{:else}
				<Icon name="check" size={15} />{m.cash_open_register()}
			{/if}
		</button>
	{/snippet}
</Modal>

<!-- ------------------------------------------------------ movimiento -->
<Modal
	open={moveModal}
	title={moveType === 'entrada' ? m.cash_movement_in_title() : m.cash_movement_out_title()}
	description={moveType === 'entrada' ? m.cash_movement_in_hint() : m.cash_movement_out_hint()}
	size="sm"
	onclose={() => (moveModal = false)}
>
	<form id="move-form" method="POST" action="?/movimiento"
		use:enhance={submit({ onSuccess: () => (moveModal = false) })}
		class="space-y-4">
		<input type="hidden" name="type" value={moveType} />
		<Field
			label={m.cash_amount_in({ currency: currency.code })}
			name="amount"
			inputmode="decimal"
			icon="wallet"
			required
			error={form?.errors?.amount}
		>
			<span class="pr-1 text-sm font-semibold text-[var(--text-subtle)]">{currency.symbol}</span>
		</Field>
		<Field
			label={m.cash_reason()}
			name="reason"
			required
			placeholder={moveType === 'entrada'
				? m.cash_reason_in_placeholder()
				: m.cash_reason_out_placeholder()}
			error={form?.errors?.reason}
		/>
	</form>

	{#snippet footer()}
		<button type="button" class="btn btn-ghost" onclick={() => (moveModal = false)}>
			{m.common_cancel()}
		</button>
		<button type="submit" form="move-form" class="btn btn-primary">
			<Icon name="check" size={15} />
			{m.cash_register_movement()}
		</button>
	{/snippet}
</Modal>

<!-- ------------------------------------------------------ cerrar caja -->
<Modal
	open={closeModal}
	title={m.cash_close_register()}
	description={m.cash_close_hint()}
	busy={submitting}
	onclose={() => (closeModal = false)}
>
	<form
		id="close-form"
		method="POST"
		action="?/cerrar"
		use:enhance={submit({
			onSuccess: () => (closeModal = false),
			setBusy: (v) => (submitting = v)
		})}
		class="space-y-4"
	>
		<div class="rounded-lg bg-[var(--surface-sunken)] p-4">
			<div class="flex justify-between text-sm">
				<span class="text-[var(--text-muted)]">{m.cash_must_be_in_drawer()}</span>
				<span class="font-bold tabular-nums text-[var(--text)]">
					{formatMoney(session?.expected_amount ?? 0)}
				</span>
			</div>
		</div>

		<Field
			label={m.cash_counted_in({ currency: currency.code })}
			name="closing_amount"
			bind:value={countedInput}
			inputmode="decimal"
			icon="wallet"
			required
			error={form?.errors?.closing_amount}
		>
			<span class="pr-1 text-sm font-semibold text-[var(--text-subtle)]">{currency.symbol}</span>
		</Field>

		<!-- La diferencia se ve antes de confirmar: nadie cierra a ciegas. -->
		<div
			class="flex items-center justify-between rounded-lg border px-4 py-3 {previewDifference ===
			0
				? 'border-[var(--positive)]'
				: 'border-[var(--negative)]'}"
		>
			<span class="text-sm font-semibold text-[var(--text-muted)]">{m.cash_difference()}</span>
			<span
				class="text-xl font-bold tabular-nums {previewDifference === 0
					? 'text-[var(--positive)]'
					: 'text-[var(--negative)]'}"
			>
				{previewDifference > 0 ? '+' : ''}{formatMoney(previewDifference)}
			</span>
		</div>

		{#if previewDifference !== 0}
			<p class="text-xs text-[var(--text-muted)]">
				{previewDifference > 0 ? m.cash_over_hint() : m.cash_short_hint()}
			</p>
		{/if}

		<Field
			label={m.cash_close_notes()}
			name="notes"
			placeholder={m.cash_close_notes_placeholder()}
			error={form?.errors?.notes}
		/>
	</form>

	{#snippet footer()}
		<button
			type="button"
			class="btn btn-ghost"
			onclick={() => (closeModal = false)}
			disabled={submitting}
		>
			{m.common_cancel()}
		</button>
		<button type="submit" form="close-form" class="btn btn-primary" disabled={submitting}>
			{#if submitting}<Spinner size={15} />{m.cash_closing_now()}{:else}
				<Icon name="lock" size={15} />{m.cash_close_register()}
			{/if}
		</button>
	{/snippet}
</Modal>
