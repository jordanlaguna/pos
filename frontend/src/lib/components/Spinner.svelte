<script lang="ts">
	interface Props {
		size?: number;
		label?: string;
		class?: string;
	}

	let { size = 16, label, class: className = '' }: Props = $props();
</script>

<span class="inline-flex items-center gap-2 {className}" role="status">
	<svg
		width={size}
		height={size}
		viewBox="0 0 24 24"
		fill="none"
		class="animate-spin"
		aria-hidden="true"
	>
		<circle cx="12" cy="12" r="9" stroke="currentColor" stroke-opacity="0.25" stroke-width="3" />
		<path
			d="M21 12a9 9 0 0 0-9-9"
			stroke="currentColor"
			stroke-width="3"
			stroke-linecap="round"
		/>
	</svg>
	{#if label}<span class="text-sm">{label}</span>{/if}
	<span class="sr-only">{label ?? 'Cargando'}</span>
</span>
