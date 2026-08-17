<script lang="ts">
	import type { Snippet } from 'svelte';

	interface Props {
		title: string;
		description?: string;
		actions?: Snippet;
	}

	let { title, description, actions }: Props = $props();
</script>

<header class="mb-5 flex flex-wrap items-end justify-between gap-3">
	<div>
		<h1 class="text-xl font-bold tracking-tight text-[var(--text)] sm:text-2xl">{title}</h1>
		{#if description}
			<p class="mt-1 text-sm text-[var(--text-muted)]">{description}</p>
		{/if}
	</div>

	{#if actions}
		<div class="no-print flex flex-wrap items-center gap-2">{@render actions()}</div>
	{/if}
</header>
