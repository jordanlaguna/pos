<script lang="ts">
	import { fly } from 'svelte/transition';
	import { toasts, type ToastKind } from '$lib/ui/stores/toast.svelte';
	import Icon, { type IconName } from './Icon.svelte';

	const ICON: Record<ToastKind, IconName> = {
		success: 'check',
		error: 'alert',
		warning: 'alert',
		info: 'info'
	};

	const STYLES: Record<ToastKind, string> = {
		success: 'border-l-[var(--positive)] text-[var(--positive)]',
		error: 'border-l-[var(--negative)] text-[var(--negative)]',
		warning: 'border-l-[var(--warning)] text-[var(--warning)]',
		info: 'border-l-[var(--info)] text-[var(--info)]'
	};
</script>

<!-- aria-live: un lector de pantalla anuncia el aviso sin que se mueva el foco. -->
<div
	class="no-print pointer-events-none fixed top-4 right-4 z-[100] flex w-[min(24rem,calc(100vw-2rem))] flex-col gap-2"
	role="region"
	aria-live="polite"
	aria-label="Notificaciones"
>
	{#each toasts.items as toast (toast.id)}
		<div
			transition:fly={{ x: 24, duration: 180 }}
			class="card pointer-events-auto flex items-start gap-3 border-l-4 p-3 shadow-lg {STYLES[
				toast.kind
			]}"
		>
			<Icon name={ICON[toast.kind]} size={18} class="mt-0.5 shrink-0" />
			<div class="min-w-0 flex-1">
				<p class="text-sm font-semibold text-[var(--text)]">{toast.message}</p>
				{#if toast.detail}
					<p class="mt-0.5 text-xs break-words text-[var(--text-muted)]">{toast.detail}</p>
				{/if}
			</div>
			<button
				type="button"
				class="shrink-0 rounded p-1 text-[var(--text-subtle)] hover:text-[var(--text)]"
				onclick={() => toasts.dismiss(toast.id)}
				aria-label="Cerrar aviso"
			>
				<Icon name="close" size={14} />
			</button>
		</div>
	{/each}
</div>
