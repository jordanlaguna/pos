<script lang="ts">
	import Icon, { type IconName } from './Icon.svelte';

	interface Props {
		label: string;
		value: string;
		icon: IconName;
		/** Variación contra el periodo anterior, ya formateada (`+12,5 %`). */
		delta?: string | null;
		/** Si subir es bueno. En "devoluciones" subir es malo, así que va en false. */
		deltaIsGood?: boolean;
		hint?: string;
		tone?: 'neutral' | 'positive' | 'negative' | 'warning';
	}

	let {
		label,
		value,
		icon,
		delta = null,
		deltaIsGood = true,
		hint,
		tone = 'neutral'
	}: Props = $props();

	const TONES = {
		neutral: 'text-[var(--accent)]',
		positive: 'text-[var(--positive)]',
		negative: 'text-[var(--negative)]',
		warning: 'text-[var(--warning)]'
	} as const;

	// El signo del texto manda: `+` es alza, `−` (U+2212, el que emite formatDelta) es baja.
	const rising = $derived(delta ? delta.trim().startsWith('+') : null);
	const deltaTone = $derived(
		rising === null
			? 'text-[var(--text-subtle)]'
			: rising === deltaIsGood
				? 'text-[var(--positive)]'
				: 'text-[var(--negative)]'
	);
</script>

<div class="card p-4">
	<div class="flex items-start justify-between gap-3">
		<p class="text-xs font-semibold tracking-wide text-[var(--text-subtle)] uppercase">
			{label}
		</p>
		<span class={TONES[tone]}><Icon name={icon} size={18} /></span>
	</div>

	<!-- Cifra grande con figuras proporcionales: tabular-nums las deja sueltas a este tamaño. -->
	<p class="mt-2 text-2xl font-bold tracking-tight text-[var(--text)]">
		{value}
	</p>

	<div class="mt-1 flex items-center gap-2 text-xs">
		{#if delta}
			<span class="font-semibold tabular-nums {deltaTone}">{delta}</span>
			<span class="text-[var(--text-subtle)]">vs. periodo anterior</span>
		{:else if hint}
			<span class="text-[var(--text-subtle)]">{hint}</span>
		{/if}
	</div>
</div>
