<script lang="ts">
	import { enhance } from '$app/forms';
	import { submit } from '$lib/forms';
	import Icon from '$lib/components/Icon.svelte';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import Modal from '$lib/components/Modal.svelte';
	import Field from '$lib/components/Field.svelte';
	import EmptyState from '$lib/components/EmptyState.svelte';
	import Spinner from '$lib/components/Spinner.svelte';
	import { toasts } from '$lib/stores/toast.svelte';
	import { currencySettings, formatMoney, parseAmount, round2 } from '$lib/money';
	import { formatDateTime, formatInt, formatTime } from '$lib/format';
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
	 * moneda se la están pidiendo: la configura el dueño del sistema y no siempre
	 * es la del país donde se escribió este código.
	 */
	const moneda = $derived(currencySettings());

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
	title="Caja"
	description="Apertura, movimientos de efectivo y cierre de turno."
>
	{#snippet actions()}
		{#if isOpen}
			<button
				type="button"
				class="btn btn-ghost"
				onclick={() => startMovement('entrada')}
			>
				<Icon name="plus" size={15} />
				Entrada
			</button>
			<button type="button" class="btn btn-ghost" onclick={() => startMovement('salida')}>
				<Icon name="minus" size={15} />
				Salida
			</button>
			<button type="button" class="btn btn-primary" onclick={openCloseModal}>
				<Icon name="lock" size={15} />
				Cerrar caja
			</button>
		{:else}
			<button type="button" class="btn btn-primary" onclick={() => (openModal = true)}>
				<Icon name="wallet" size={15} />
				Abrir caja
			</button>
		{/if}
	{/snippet}
</PageHeader>

{#if !isOpen}
	<div class="card p-6">
		<EmptyState
			icon="wallet"
			title="La caja está cerrada"
			description="Abrí la caja con el efectivo inicial para empezar el turno. Las ventas se atribuyen al turno abierto."
		>
			<button type="button" class="btn btn-primary" onclick={() => (openModal = true)}>
				<Icon name="wallet" size={15} />
				Abrir caja
			</button>
		</EmptyState>
	</div>
{:else if session}
	<!-- Estado del turno en curso -->
	<div class="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
		<div class="card p-4">
			<p class="text-xs font-semibold tracking-wide text-[var(--text-subtle)] uppercase">
				Apertura
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
				Ventas del turno
			</p>
			<p class="mt-1 text-xl font-bold text-[var(--text)]">
				{formatMoney(session.sales_total)}
			</p>
			<p class="mt-1 text-xs text-[var(--text-subtle)]">
				{formatInt(session.sales_count)}
				{session.sales_count === 1 ? 'venta' : 'ventas'}
			</p>
		</div>

		<div class="card p-4">
			<p class="text-xs font-semibold tracking-wide text-[var(--text-subtle)] uppercase">
				Efectivo en ventas
			</p>
			<p class="mt-1 text-xl font-bold text-[var(--text)]">
				{formatMoney(session.cash_sales)}
			</p>
			<p class="mt-1 text-xs text-[var(--text-subtle)]">
				Solo el efectivo pasa por la gaveta
			</p>
		</div>

		<div class="card border-[var(--accent)] p-4">
			<p class="text-xs font-semibold tracking-wide text-[var(--text-subtle)] uppercase">
				Debe haber en caja
			</p>
			<p class="mt-1 text-xl font-bold text-[var(--accent)]">
				{formatMoney(session.expected_amount)}
			</p>
			<p class="mt-1 text-xs text-[var(--text-subtle)]">Apertura + efectivo ± movimientos</p>
		</div>
	</div>

	<div class="grid gap-4 lg:grid-cols-2">
		<!-- Desglose -->
		<section class="card p-4">
			<h2 class="mb-3 text-sm font-bold text-[var(--text)]">Desglose del turno</h2>

			<dl class="space-y-2 text-sm">
				<div class="flex justify-between">
					<dt class="text-[var(--text-muted)]">Monto de apertura</dt>
					<dd class="tabular-nums text-[var(--text)]">
						{formatMoney(session.opening_amount)}
					</dd>
				</div>
				<div class="flex justify-between">
					<dt class="text-[var(--text-muted)]">Ventas en efectivo</dt>
					<dd class="tabular-nums text-[var(--positive)]">
						+{formatMoney(session.cash_sales)}
					</dd>
				</div>
				<div class="flex justify-between">
					<dt class="text-[var(--text-muted)]">Entradas de efectivo</dt>
					<dd class="tabular-nums text-[var(--positive)]">
						+{formatMoney(session.movements_in)}
					</dd>
				</div>
				<div class="flex justify-between">
					<dt class="text-[var(--text-muted)]">Salidas de efectivo</dt>
					<dd class="tabular-nums text-[var(--negative)]">
						−{formatMoney(session.movements_out)}
					</dd>
				</div>
				<div class="flex justify-between">
					<dt class="text-[var(--text-muted)]">Devoluciones</dt>
					<dd class="tabular-nums text-[var(--negative)]">
						−{formatMoney(session.returns_total)}
					</dd>
				</div>
				<div
					class="flex justify-between border-t border-[var(--border)] pt-2 text-base font-bold"
				>
					<dt class="text-[var(--text)]">Esperado en gaveta</dt>
					<dd class="tabular-nums text-[var(--text)]">
						{formatMoney(session.expected_amount)}
					</dd>
				</div>
			</dl>

			{#if session.by_payment_method.length}
				<h3 class="mt-5 mb-2 text-xs font-bold tracking-wide text-[var(--text-subtle)] uppercase">
					Por método de pago
				</h3>
				<table class="data-table">
					<thead>
						<tr>
							<th scope="col">Método</th>
							<th scope="col" class="num">Ventas</th>
							<th scope="col" class="num">Total</th>
						</tr>
					</thead>
					<tbody>
						{#each session.by_payment_method as row (row.payment_method)}
							<tr>
								<td>{row.payment_method}</td>
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
			<h2 class="mb-3 text-sm font-bold text-[var(--text)]">Movimientos de efectivo</h2>

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
					title="Sin movimientos"
					description="Registrá entradas o salidas de efectivo que no sean ventas."
					compact
				/>
			{/if}
		</section>
	</div>
{/if}

<!-- Historial de turnos -->
<section class="mt-6">
	<h2 class="mb-3 text-sm font-bold text-[var(--text)]">Turnos anteriores</h2>
	<div class="card overflow-hidden">
		<div class="table-wrap">
			<table class="data-table">
				<thead>
					<tr>
						<th scope="col">Apertura</th>
						<th scope="col">Cierre</th>
						{#if data.user.role === 'admin'}
							<th scope="col">Cajero</th>
						{/if}
						<th scope="col" class="num">Inicial</th>
						<th scope="col" class="num">Ventas</th>
						<th scope="col" class="num">Esperado</th>
						<th scope="col" class="num">Contado</th>
						<th scope="col" class="num">Diferencia</th>
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
										Cuadrada
									</span>
								{:else}
									<span
										class="badge tabular-nums {row.difference > 0
											? 'bg-[var(--info-bg)] text-[var(--info)]'
											: 'bg-[var(--negative-bg)] text-[var(--negative)]'}"
									>
										<Icon name="alert" size={11} />
										{row.difference > 0 ? 'Sobrante' : 'Faltante'}
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
									title="Sin turnos cerrados"
									description="El historial aparece al cerrar la caja."
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
	title="Abrir caja"
	description="Contá el efectivo con el que arranca el turno."
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
			label="Monto de apertura ({moneda.codigo})"
			name="opening_amount"
			value="0"
			inputmode="decimal"
			icon="wallet"
			required
			error={form?.errors?.opening_amount}
			hint="Efectivo con el que inicia la gaveta, en {moneda.codigo}."
		>
			<span class="pr-1 text-sm font-semibold text-[var(--text-subtle)]">{moneda.simbolo}</span>
		</Field>
		<Field
			label="Notas (opcional)"
			name="notes"
			placeholder="Ej.: turno de la mañana"
			error={form?.errors?.notes}
		/>
	</form>

	{#snippet footer()}
		<button type="button" class="btn btn-ghost" onclick={() => (openModal = false)}>
			Cancelar
		</button>
		<button type="submit" form="open-form" class="btn btn-primary" disabled={submitting}>
			{#if submitting}<Spinner size={15} />Abriendo…{:else}
				<Icon name="check" size={15} />Abrir caja
			{/if}
		</button>
	{/snippet}
</Modal>

<!-- ------------------------------------------------------ movimiento -->
<Modal
	open={moveModal}
	title={moveType === 'entrada' ? 'Entrada de efectivo' : 'Salida de efectivo'}
	description={moveType === 'entrada'
		? 'Dinero que entra a la gaveta sin ser una venta.'
		: 'Dinero que sale de la gaveta: pagos, retiros, vueltos.'}
	size="sm"
	onclose={() => (moveModal = false)}
>
	<form id="move-form" method="POST" action="?/movimiento"
		use:enhance={submit({ onSuccess: () => (moveModal = false) })}
		class="space-y-4">
		<input type="hidden" name="type" value={moveType} />
		<Field
			label="Monto ({moneda.codigo})"
			name="amount"
			inputmode="decimal"
			icon="wallet"
			required
			error={form?.errors?.amount}
		>
			<span class="pr-1 text-sm font-semibold text-[var(--text-subtle)]">{moneda.simbolo}</span>
		</Field>
		<Field
			label="Motivo"
			name="reason"
			required
			placeholder={moveType === 'entrada' ? 'Ej.: cambio del banco' : 'Ej.: pago a proveedor'}
			error={form?.errors?.reason}
		/>
	</form>

	{#snippet footer()}
		<button type="button" class="btn btn-ghost" onclick={() => (moveModal = false)}>
			Cancelar
		</button>
		<button type="submit" form="move-form" class="btn btn-primary">
			<Icon name="check" size={15} />
			Registrar
		</button>
	{/snippet}
</Modal>

<!-- ------------------------------------------------------ cerrar caja -->
<Modal
	open={closeModal}
	title="Cerrar caja"
	description="Contá el efectivo real de la gaveta antes de confirmar."
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
				<span class="text-[var(--text-muted)]">Debe haber en gaveta</span>
				<span class="font-bold tabular-nums text-[var(--text)]">
					{formatMoney(session?.expected_amount ?? 0)}
				</span>
			</div>
		</div>

		<Field
			label="Efectivo contado ({moneda.codigo})"
			name="closing_amount"
			bind:value={countedInput}
			inputmode="decimal"
			icon="wallet"
			required
			error={form?.errors?.closing_amount}
		>
			<span class="pr-1 text-sm font-semibold text-[var(--text-subtle)]">{moneda.simbolo}</span>
		</Field>

		<!-- La diferencia se ve antes de confirmar: nadie cierra a ciegas. -->
		<div
			class="flex items-center justify-between rounded-lg border px-4 py-3 {previewDifference ===
			0
				? 'border-[var(--positive)]'
				: 'border-[var(--negative)]'}"
		>
			<span class="text-sm font-semibold text-[var(--text-muted)]">Diferencia</span>
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
				{previewDifference > 0
					? 'Hay más efectivo del esperado. Anotá el motivo antes de cerrar.'
					: 'Falta efectivo respecto de lo esperado. Anotá el motivo antes de cerrar.'}
			</p>
		{/if}

		<Field
			label="Notas del cierre (opcional)"
			name="notes"
			placeholder="Ej.: faltante por vuelto mal dado"
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
			Cancelar
		</button>
		<button type="submit" form="close-form" class="btn btn-primary" disabled={submitting}>
			{#if submitting}<Spinner size={15} />Cerrando…{:else}
				<Icon name="lock" size={15} />Cerrar caja
			{/if}
		</button>
	{/snippet}
</Modal>
