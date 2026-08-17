<script lang="ts">
	import type { Snippet } from 'svelte';
	import Icon, { type IconName } from './Icon.svelte';

	interface Props {
		icon?: IconName;
		title: string;
		description?: string;
		compact?: boolean;
		children?: Snippet;
	}

	let { icon = 'info', title, description, compact = false, children }: Props = $props();
</script>

<div
	class="flex flex-col items-center justify-center text-center {compact ? 'gap-2 py-8' : 'gap-3 py-14'}"
>
	<span
		class="grid place-items-center rounded-full bg-[var(--surface-sunken)] text-[var(--text-subtle)] {compact
			? 'h-10 w-10'
			: 'h-14 w-14'}"
	>
		<Icon name={icon} size={compact ? 18 : 24} />
	</span>

	<div>
		<p class="font-semibold text-[var(--text)]">{title}</p>
		{#if description}
			<p class="mx-auto mt-1 max-w-sm text-sm text-[var(--text-muted)]">{description}</p>
		{/if}
	</div>

	{#if children}
		<div class="mt-1">{@render children()}</div>
	{/if}
</div>
