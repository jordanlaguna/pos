<script lang="ts">
	import type { Snippet } from 'svelte';
	import { fade, scale } from 'svelte/transition';
	import Icon from './Icon.svelte';

	interface Props {
		open: boolean;
		title: string;
		description?: string;
		size?: 'sm' | 'md' | 'lg' | 'xl';
		/** Bloquea cerrar con Escape o clic fuera. Útil mientras se está guardando. */
		busy?: boolean;
		onclose: () => void;
		children: Snippet;
		footer?: Snippet;
	}

	let {
		open,
		title,
		description,
		size = 'md',
		busy = false,
		onclose,
		children,
		footer
	}: Props = $props();

	const WIDTHS = {
		sm: 'max-w-md',
		md: 'max-w-xl',
		lg: 'max-w-3xl',
		xl: 'max-w-5xl'
	} as const;

	let dialog = $state<HTMLDivElement | null>(null);
	let previouslyFocused: HTMLElement | null = null;

	const FOCUSABLE =
		'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

	$effect(() => {
		if (!open) return;

		previouslyFocused = document.activeElement as HTMLElement | null;
		// El fondo no debe poder desplazarse mientras el diálogo está arriba.
		const overflow = document.body.style.overflow;
		document.body.style.overflow = 'hidden';

		// Se enfoca el primer campo real; si no hay, el propio diálogo.
		queueMicrotask(() => {
			const first = dialog?.querySelector<HTMLElement>(FOCUSABLE);
			(first ?? dialog)?.focus();
		});

		return () => {
			document.body.style.overflow = overflow;
			previouslyFocused?.focus?.();
		};
	});

	/** El foco no debe escaparse del diálogo mientras esté abierto. */
	function onkeydown(event: KeyboardEvent) {
		if (event.key === 'Escape' && !busy) {
			event.preventDefault();
			onclose();
			return;
		}
		if (event.key !== 'Tab' || !dialog) return;

		const focusables = [...dialog.querySelectorAll<HTMLElement>(FOCUSABLE)].filter(
			(el) => el.offsetParent !== null
		);
		if (!focusables.length) return;

		const first = focusables[0];
		const last = focusables[focusables.length - 1];
		if (event.shiftKey && document.activeElement === first) {
			event.preventDefault();
			last.focus();
		} else if (!event.shiftKey && document.activeElement === last) {
			event.preventDefault();
			first.focus();
		}
	}
</script>

<svelte:window onkeydown={open ? onkeydown : undefined} />

{#if open}
	<div class="no-print fixed inset-0 z-50 flex items-center justify-center p-4">
		<button
			type="button"
			class="absolute inset-0 cursor-default bg-black/50 backdrop-blur-[2px]"
			transition:fade={{ duration: 120 }}
			onclick={() => !busy && onclose()}
			tabindex="-1"
			aria-hidden="true"
		></button>

		<div
			bind:this={dialog}
			transition:scale={{ duration: 140, start: 0.97 }}
			class="card relative flex max-h-[calc(100vh-2rem)] w-full {WIDTHS[
				size
			]} flex-col shadow-2xl"
			role="dialog"
			aria-modal="true"
			aria-labelledby="modal-title"
			aria-describedby={description ? 'modal-description' : undefined}
			tabindex="-1"
		>
			<header class="flex items-start gap-4 border-b border-[var(--border)] px-5 py-4">
				<div class="min-w-0 flex-1">
					<h2 id="modal-title" class="text-lg font-bold text-[var(--text)]">{title}</h2>
					{#if description}
						<p id="modal-description" class="mt-0.5 text-sm text-[var(--text-muted)]">
							{description}
						</p>
					{/if}
				</div>
				<button
					type="button"
					class="-mt-1 -mr-1 shrink-0 rounded-lg p-2 text-[var(--text-subtle)] hover:bg-[var(--surface-sunken)] hover:text-[var(--text)] disabled:opacity-40"
					onclick={onclose}
					disabled={busy}
					aria-label="Cerrar"
				>
					<Icon name="close" size={18} />
				</button>
			</header>

			<div class="min-h-0 flex-1 overflow-y-auto px-5 py-4">
				{@render children()}
			</div>

			{#if footer}
				<footer
					class="flex flex-wrap justify-end gap-2 border-t border-[var(--border)] px-5 py-3"
				>
					{@render footer()}
				</footer>
			{/if}
		</div>
	</div>
{/if}
