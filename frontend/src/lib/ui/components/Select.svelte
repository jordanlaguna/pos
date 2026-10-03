<script lang="ts">
	/**
	 * Una lista desplegable, con su rótulo, su error y su pista (QA-06).
	 *
	 * Es el par de `Field` para las listas: el mismo rótulo, el mismo aviso
	 * debajo y el mismo `id` (`field-<name>`), así una pantalla no arma el
	 * rótulo a mano en un sitio y con `Field` en el de al lado.
	 *
	 * **Por dentro es la lista nativa, a propósito.** Viaja en el formulario sin
	 * JavaScript, el teclado y el lector de pantalla ya saben usarla, y las
	 * pruebas de punta a punta la eligen con `selectOption`. El aspecto lo pone
	 * `select.input` en `app.css`.
	 *
	 * Las opciones van como hijos. **La opción inicial se marca con `selected` y
	 * no se pasa `value`.** Con un `value` fijo, Svelte reinicia la lista al
	 * hidratar y se come lo que la persona eligió antes: en el alta de compañía,
	 * el plan volvía al primero y la compañía nacía en Básico (QA-06). Sin
	 * `value`, o enlazado a algo que nace en `undefined`, toma la opción que esté
	 * marcada en ese momento. `bind:value` a un estado con valor solo cuando la
	 * pantalla no se puede usar antes de hidratar.
	 */
	import type { Snippet } from 'svelte';
	import type { HTMLSelectAttributes } from 'svelte/elements';
	import Icon from './Icon.svelte';

	interface Props extends Omit<HTMLSelectAttributes, 'value' | 'class' | 'children'> {
		label?: string;
		name: string;
		value?: string | number | null;
		error?: string | null;
		hint?: string;
		/** Clases del contenedor. */
		class?: string;
		/** Clases extra de la lista, para las compactas (`h-8 text-xs`). */
		selectClass?: string;
		children: Snippet;
	}

	let {
		label,
		name,
		id,
		value = $bindable(),
		required = false,
		error,
		hint,
		class: className = '',
		selectClass = '',
		children,
		...resto
	}: Props = $props();

	const campo = $derived(id ?? `field-${name}`);
	const describedBy = $derived(error ? `${campo}-error` : hint ? `${campo}-hint` : undefined);
</script>

<div class={className}>
	{#if label}
		<label class="label" for={campo}>
			{label}
			{#if required}<span class="text-[var(--negative)]" aria-hidden="true">*</span>{/if}
		</label>
	{/if}

	<select
		id={campo}
		{name}
		{required}
		bind:value
		aria-invalid={error ? 'true' : undefined}
		aria-describedby={describedBy}
		class="input {selectClass}"
		{...resto}
	>
		{@render children()}
	</select>

	{#if error}
		<p id="{campo}-error" class="mt-1 flex items-center gap-1 text-xs text-[var(--negative)]">
			<Icon name="alert" size={12} />
			{error}
		</p>
	{:else if hint}
		<p id="{campo}-hint" class="mt-1 text-xs text-[var(--text-subtle)]">{hint}</p>
	{/if}
</div>
