<script lang="ts">
	import type { Snippet } from 'svelte';
	import type { HTMLInputAttributes } from 'svelte/elements';
	import Icon, { type IconName } from './Icon.svelte';

	interface Props {
		label: string;
		name: string;
		value?: string | number | null;
		type?: 'text' | 'email' | 'password' | 'number' | 'date' | 'tel' | 'search';
		placeholder?: string;
		required?: boolean;
		disabled?: boolean;
		readonly?: boolean;
		autocomplete?: HTMLInputAttributes['autocomplete'];
		icon?: IconName;
		error?: string;
		hint?: string;
		step?: string | number;
		min?: string | number;
		max?: string | number;
		inputmode?: 'text' | 'numeric' | 'decimal' | 'tel' | 'email' | 'search';
		class?: string;
		children?: Snippet;
	}

	let {
		label,
		name,
		value = $bindable(''),
		type = 'text',
		placeholder,
		required = false,
		disabled = false,
		readonly = false,
		autocomplete,
		icon,
		error,
		hint,
		step,
		min,
		max,
		inputmode,
		class: className = '',
		children
	}: Props = $props();

	const id = $derived(`field-${name}`);
	const describedBy = $derived(error ? `${id}-error` : hint ? `${id}-hint` : undefined);
</script>

<div class={className}>
	<label class="label" for={id}>
		{label}
		{#if required}<span class="text-[var(--negative)]" aria-hidden="true">*</span>{/if}
	</label>

	<div class="relative">
		{#if icon}
			<span
				class="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-[var(--text-subtle)]"
			>
				<Icon name={icon} size={16} />
			</span>
		{/if}

		<!--
			`type` no puede ir con bind:value en Svelte, así que se fija por atributo.
			Number devuelve string y cada formulario decide cómo interpretarlo.
		-->
		<input
			{id}
			{name}
			{type}
			{placeholder}
			{required}
			{disabled}
			{readonly}
			{autocomplete}
			{step}
			{min}
			{max}
			{inputmode}
			bind:value
			aria-invalid={error ? 'true' : undefined}
			aria-describedby={describedBy}
			class="input {icon ? 'pl-9' : ''}"
		/>

		{#if children}
			<div class="absolute top-1/2 right-2 -translate-y-1/2">
				{@render children()}
			</div>
		{/if}
	</div>

	{#if error}
		<p id="{id}-error" class="mt-1 flex items-center gap-1 text-xs text-[var(--negative)]">
			<Icon name="alert" size={12} />
			{error}
		</p>
	{:else if hint}
		<p id="{id}-hint" class="mt-1 text-xs text-[var(--text-subtle)]">{hint}</p>
	{/if}
</div>
