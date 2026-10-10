<script lang="ts" generics="V = string | number | null">
	/**
	 * Una lista desplegable, con su rótulo, su error y su pista (QA-06).
	 *
	 * Es el par de `Field` para las listas: el mismo rótulo, el mismo aviso
	 * debajo y el mismo `id` (`field-<name>`), así una pantalla no arma el
	 * rótulo a mano en un sitio y con `Field` en el de al lado.
	 *
	 * **Por dentro sigue siendo la lista nativa, a propósito** (T-933). Viaja en
	 * el formulario sin JavaScript, el lector de pantalla ya sabe usarla y las
	 * pruebas de punta a punta la eligen con `selectOption`. Lo que cambió es la
	 * cara: después de hidratar, la nativa se esconde —`sr-only`, no `hidden`:
	 * sigue en el formulario— y en su lugar hay un botón con el valor y un
	 * panel propio con las opciones, que es lo que se puede dibujar igual en
	 * todas las pantallas; el desplegable de una lista nativa lo pinta el
	 * sistema operativo y no hay forma de que se parezca a nada. Hasta hidratar
	 * se ve la nativa, así que elegir antes de tiempo sigue funcionando.
	 *
	 * Las opciones van como hijos. **La opción inicial se marca con `selected` y
	 * no se pasa `value`.** Con un `value` fijo, Svelte reinicia la lista al
	 * hidratar y se come lo que la persona eligió antes: en el alta de compañía,
	 * el plan volvía al primero y la compañía nacía en Básico (QA-06). Sin
	 * `value`, o enlazado a algo que nace en `undefined`, toma la opción que esté
	 * marcada en ese momento. `bind:value` a un estado con valor solo cuando la
	 * pantalla no se puede usar antes de hidratar.
	 */
	import { onMount, tick, type Snippet } from 'svelte';
	import type { HTMLSelectAttributes } from 'svelte/elements';
	import Icon from './Icon.svelte';

	interface Props extends Omit<HTMLSelectAttributes, 'value' | 'class' | 'children'> {
		label?: string;
		/** Con el que viaja en el formulario. Sin él es un filtro de pantalla. */
		name?: string;
		value?: V;
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
		disabled = false,
		'aria-label': ariaLabel,
		error,
		hint,
		class: className = '',
		selectClass = '',
		children,
		...resto
	}: Props = $props();

	const uid = $props.id();
	const campo = $derived(id ?? (name ? `field-${name}` : `combo-${uid}`));
	const describedBy = $derived(error ? `${campo}-error` : hint ? `${campo}-hint` : undefined);

	// ------------------------------------------------------- la lista propia

	interface Opcion {
		value: string;
		label: string;
		disabled: boolean;
		selected: boolean;
	}

	let nativo = $state<HTMLSelectElement | null>(null);
	let boton = $state<HTMLButtonElement | null>(null);
	let panel = $state<HTMLUListElement | null>(null);
	/** Hasta hidratar se ve la nativa; después, el botón y el panel. */
	let montado = $state(false);
	let abierto = $state(false);
	let opciones = $state<Opcion[]>([]);
	let rotulo = $state('');
	/** La opción resaltada, por teclado o por el puntero. */
	let activa = $state(-1);
	/** Dónde flota el panel: fijo a la ventana, para que ningún `overflow` lo recorte. */
	let caja = $state({ top: 0, bottom: 0, arriba: false, left: 0, width: 0, maxHeight: 288 });

	/** La verdad está en la nativa: de ahí salen las opciones y el valor que se ve. */
	function leer() {
		if (!nativo) return;
		opciones = Array.from(nativo.options).map((o) => ({
			value: o.value,
			label: o.label || o.text,
			disabled: o.disabled,
			selected: o.selected
		}));
		const elegida = nativo.selectedOptions[0];
		rotulo = elegida ? elegida.label || elegida.text : '';
	}

	onMount(() => {
		leer();
		montado = true;
		// Las opciones pueden cambiar después (un `{#each}` que se llena al
		// cargar) y la nativa puede cambiar sola (`selectOption` en las pruebas).
		const vigia = new MutationObserver(leer);
		vigia.observe(nativo!, { childList: true, subtree: true, attributes: true, characterData: true });
		nativo!.addEventListener('change', leer);
		return () => {
			vigia.disconnect();
			nativo?.removeEventListener('change', leer);
		};
	});

	// Lo que cambie desde afuera por `bind:value` también se refleja: Svelte
	// escribe la propiedad `value` de la nativa, que no es una mutación del DOM.
	$effect(() => {
		void value;
		if (montado) tick().then(leer);
	});

	function ubicar() {
		if (!boton) return;
		const r = boton.getBoundingClientRect();
		const margen = 8;
		const abajo = window.innerHeight - r.bottom - margen;
		const encima = r.top - margen;
		const deseado = Math.min(288, opciones.length * 36 + 8);
		const arriba = abajo < deseado && encima > abajo;
		caja = {
			arriba,
			top: r.bottom + 4,
			bottom: window.innerHeight - r.top + 4,
			left: r.left,
			width: r.width,
			maxHeight: Math.max(96, Math.min(288, arriba ? encima : abajo))
		};
	}

	async function abrir() {
		if (disabled) return;
		leer();
		activa = Math.max(0, opciones.findIndex((o) => o.selected));
		abierto = true;
		await tick();
		ubicar();
		enfocarActiva();
	}

	function cerrar() {
		abierto = false;
	}

	function elegir(i: number) {
		const o = opciones[i];
		if (!o || o.disabled || !nativo) return;
		nativo.value = o.value;
		// Los mismos eventos que dispara la nativa, en el mismo orden: así el
		// `bind:value` y el `onchange` de la pantalla se enteran igual.
		nativo.dispatchEvent(new Event('input', { bubbles: true }));
		nativo.dispatchEvent(new Event('change', { bubbles: true }));
		leer();
		cerrar();
		boton?.focus();
	}

	function habil(desde: number, paso: 1 | -1): number {
		for (let i = desde; i >= 0 && i < opciones.length; i += paso) {
			if (!opciones[i].disabled) return i;
		}
		return activa;
	}

	function mover(paso: 1 | -1) {
		activa = habil(activa + paso, paso);
		enfocarActiva();
	}

	function enfocarActiva() {
		panel?.children[activa]?.scrollIntoView({ block: 'nearest' });
	}

	/** Escribir una letra salta a la opción que empieza con ella, como en la nativa. */
	function buscar(letra: string) {
		const l = letra.toLowerCase();
		const desde = abierto ? activa + 1 : opciones.findIndex((o) => o.selected) + 1;
		const orden = [...opciones.keys()].slice(desde).concat([...opciones.keys()].slice(0, desde));
		const i = orden.find((k) => !opciones[k].disabled && opciones[k].label.toLowerCase().startsWith(l));
		if (i === undefined) return;
		if (abierto) {
			activa = i;
			enfocarActiva();
		} else {
			elegir(i);
		}
	}

	function teclado(e: KeyboardEvent) {
		switch (e.key) {
			case 'ArrowDown':
				e.preventDefault();
				if (abierto) mover(1);
				else abrir();
				break;
			case 'ArrowUp':
				e.preventDefault();
				if (abierto) mover(-1);
				else abrir();
				break;
			case 'Home':
				if (abierto) {
					e.preventDefault();
					activa = habil(0, 1);
					enfocarActiva();
				}
				break;
			case 'End':
				if (abierto) {
					e.preventDefault();
					activa = habil(opciones.length - 1, -1);
					enfocarActiva();
				}
				break;
			case 'Enter':
			case ' ':
				e.preventDefault();
				if (abierto) elegir(activa);
				else abrir();
				break;
			case 'Escape':
				if (abierto) {
					e.preventDefault();
					cerrar();
				}
				break;
			case 'Tab':
				cerrar();
				break;
			default:
				if (e.key.length === 1 && /\S/.test(e.key) && !e.ctrlKey && !e.metaKey && !e.altKey) {
					e.preventDefault();
					buscar(e.key);
				}
		}
	}

	// Abierto: un clic afuera lo cierra, y desplazar o cambiar de tamaño lo
	// vuelve a ubicar, porque flota fijo a la ventana y no sigue a su botón.
	$effect(() => {
		if (!abierto) return;
		const afuera = (e: PointerEvent) => {
			const t = e.target as Node;
			if (!boton?.contains(t) && !panel?.contains(t)) cerrar();
		};
		document.addEventListener('pointerdown', afuera);
		window.addEventListener('scroll', ubicar, true);
		window.addEventListener('resize', ubicar);
		return () => {
			document.removeEventListener('pointerdown', afuera);
			window.removeEventListener('scroll', ubicar, true);
			window.removeEventListener('resize', ubicar);
		};
	});
</script>

<div class="relative {className}">
	{#if label}
		<label class="label" for={montado ? `${campo}-boton` : campo}>
			{label}
			{#if required}<span class="text-[var(--negative)]" aria-hidden="true">*</span>{/if}
		</label>
	{/if}

	{#if montado}
		<button
			bind:this={boton}
			type="button"
			id="{campo}-boton"
			role="combobox"
			aria-haspopup="listbox"
			aria-expanded={abierto}
			aria-controls={abierto ? `${campo}-lista` : undefined}
			aria-activedescendant={abierto && activa >= 0 ? `${campo}-opcion-${activa}` : undefined}
			aria-label={ariaLabel}
			aria-invalid={error ? 'true' : undefined}
			aria-describedby={describedBy}
			class="input combo-boton {selectClass}"
			{disabled}
			onclick={() => (abierto ? cerrar() : abrir())}
			onkeydown={teclado}
		>
			<span class="truncate">{rotulo}</span>
			<Icon name="down" size={14} class="shrink-0 text-[var(--text-subtle)]" />
		</button>
	{/if}

	<!-- La nativa: visible hasta hidratar, y después solo para el formulario,
	     el lector de pantalla y `selectOption`. -->
	<select
		bind:this={nativo}
		id={campo}
		{name}
		{required}
		{disabled}
		bind:value
		aria-label={ariaLabel}
		aria-invalid={error ? 'true' : undefined}
		aria-describedby={describedBy}
		aria-hidden={montado ? 'true' : undefined}
		tabindex={montado ? -1 : undefined}
		class="input {selectClass} {montado ? 'sr-only' : ''}"
		{...resto}
	>
		{@render children()}
	</select>

	{#if abierto}
		<ul
			bind:this={panel}
			id="{campo}-lista"
			role="listbox"
			aria-label={ariaLabel ?? label}
			class="combo-panel"
			style:top={caja.arriba ? 'auto' : `${caja.top}px`}
			style:bottom={caja.arriba ? `${caja.bottom}px` : 'auto'}
			style:left="{caja.left}px"
			style:width="{caja.width}px"
			style:max-height="{caja.maxHeight}px"
		>
			{#each opciones as o, i (i)}
				<li
					id="{campo}-opcion-{i}"
					role="option"
					tabindex="-1"
					aria-selected={o.selected}
					aria-disabled={o.disabled ? 'true' : undefined}
					class="combo-opcion {i === activa ? 'activa' : ''}"
					onpointerdown={(e) => e.preventDefault()}
					onpointermove={() => (activa = i)}
					onclick={() => elegir(i)}
					onkeydown={teclado}
				>
					<span class="truncate">{o.label}</span>
					{#if o.selected}
						<Icon name="check" size={14} class="shrink-0 text-[var(--text)]" />
					{/if}
				</li>
			{/each}
		</ul>
	{/if}

	{#if error}
		<p id="{campo}-error" class="mt-1 flex items-center gap-1 text-xs text-[var(--negative)]">
			<Icon name="alert" size={12} />
			{error}
		</p>
	{:else if hint}
		<p id="{campo}-hint" class="mt-1 text-xs text-[var(--text-subtle)]">{hint}</p>
	{/if}
</div>
