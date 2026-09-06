<script lang="ts">
	/**
	 * Buscador del catálogo CABYS (T-504).
	 *
	 * Es el mismo en la ficha del producto y en la asignación en lote, y por eso
	 * está acá: en los dos sitios hay que buscar por texto, ver la tarifa de cada
	 * resultado antes de elegir y enterarse de si lo que se está leyendo viene de
	 * Hacienda o de la caché (RNF-4).
	 *
	 * Habla con `/inventario/cabys`, que es el puente hacia el backend. El
	 * navegador nunca alcanza ni a Hacienda ni a la VM.
	 */
	import Icon from './Icon.svelte';
	import Spinner from './Spinner.svelte';
	import { ratePercentText } from '$lib/domain/money';
	import { formatDateTime } from '$lib/ui/format';
	import { m } from '$lib/paraglide/messages.js';
	import { CABYS_CODE_LENGTH, type CabysAnswer, type CabysEntry } from '$lib/domain/cabys';

	interface Props {
		/** Qué hacer con el código elegido. Asignarlo **es** copiar su tarifa (RN-11). */
		onpick: (entry: CabysEntry) => void;
		/** El código ya elegido, para marcarlo en la lista. */
		selected?: string | null;
	}

	let { onpick, selected = null }: Props = $props();

	let query = $state('');
	let results = $state<CabysEntry[]>([]);
	let source = $state<CabysAnswer['source']>('hacienda');
	let cachedAt = $state<string | null>(null);
	let busy = $state(false);
	let failed = $state(false);
	let searched = $state(false);
	/** Cómo se buscó lo que hay en pantalla, para que «sin resultados» diga la verdad. */
	let buscadoPorCodigo = $state(false);

	/**
	 * Lo escrito, sin los espacios ni los guiones con que se suele copiar un
	 * código de otra pantalla.
	 */
	const limpio = $derived(query.trim().replace(/[\s-]/g, ''));
	/**
	 * Buscar por código y buscar por texto son dos consultas distintas del API de
	 * Hacienda, y la de texto **no mira los códigos**: `q=2314` devuelve cero
	 * resultados, no «los que empiezan por 2314». Por eso se decide acá cuál de
	 * las dos se manda, en vez de mandar siempre la misma.
	 */
	const esCodigo = $derived(limpio.length > 0 && /^\d+$/.test(limpio));
	/**
	 * Un código a medias no se puede consultar: Hacienda solo resuelve el exacto.
	 * Se dice antes de gastar la petición, y se dice mientras se escribe.
	 */
	const codigoIncompleto = $derived(esCodigo && limpio.length !== CABYS_CODE_LENGTH);

	export async function buscar() {
		if (!query.trim() || busy || codigoIncompleto) return;
		busy = true;
		failed = false;

		const consulta = esCodigo
			? `codigo=${encodeURIComponent(limpio)}`
			: `q=${encodeURIComponent(query.trim())}`;

		let answer: CabysAnswer | null = null;
		try {
			const respuesta = await fetch(`/inventario/cabys?${consulta}`);
			if (respuesta.ok) answer = (await respuesta.json()) as CabysAnswer;
		} catch {
			answer = null;
		}

		busy = false;
		searched = true;
		buscadoPorCodigo = esCodigo;
		if (!answer) {
			// El backend nunca falla por falta de internet —degrada y lo dice en
			// `source`—, así que llegar acá significa que no se lo alcanzó.
			failed = true;
			results = [];
			return;
		}
		results = answer.items;
		source = answer.source;
		cachedAt = answer.cached_at;
	}
</script>

<div>
	<label class="label" for="cabys-buscar">{m.inventory_cabys_search()}</label>
	<div class="flex gap-2">
		<input
			id="cabys-buscar"
			bind:value={query}
			type="search"
			class="input"
			placeholder={m.inventory_cabys_search_placeholder()}
			onkeydown={(e) => {
				// El buscador puede vivir dentro de otro formulario: sin esto, Enter
				// enviaría ese formulario a medio clasificar.
				if (e.key === 'Enter') {
					e.preventDefault();
					buscar();
				}
			}}
		/>
		<button
			type="button"
			class="btn btn-ghost shrink-0"
			onclick={buscar}
			disabled={busy || !query.trim() || codigoIncompleto}
		>
			{#if busy}
				<Spinner size={15} />
			{:else}
				<Icon name="search" size={15} />
			{/if}
			{m.common_search()}
		</button>
	</div>

	{#if codigoIncompleto}
		<!--
			Se avisa mientras se escribe y no al pulsar: el catálogo solo resuelve el
			código exacto, así que decirlo después de la petición sería decirlo tarde
			y con una petición gastada de por medio.
		-->
		<p class="mt-2 text-xs text-[var(--text-subtle)]">
			{m.inventory_cabys_code_partial({ typed: limpio.length, length: CABYS_CODE_LENGTH })}
		</p>
	{:else if failed}
		<p class="mt-2 text-xs text-[var(--negative)]">{m.inventory_cabys_unreachable()}</p>
	{:else if searched && source === 'cache'}
		<!--
			RNF-4: lo que necesita internet degrada con aviso y nunca bloquea. La
			fecha es la mitad importante del aviso: dice qué tan vieja es la tarifa
			que se está a punto de copiar.
		-->
		<p class="mt-2 flex items-start gap-1.5 text-xs text-[var(--warning)]">
			<Icon name="alert" size={13} />
			{cachedAt
				? m.inventory_cabys_offline_since({ date: formatDateTime(cachedAt) })
				: m.inventory_cabys_offline()}
		</p>
	{/if}

	{#if results.length > 0}
		<ul class="mt-2 max-h-56 space-y-1 overflow-y-auto" data-testid="cabys-results">
			{#each results as entry (entry.code)}
				<li>
					<button
						type="button"
						class="flex w-full items-center gap-2 rounded-lg p-2 text-left hover:bg-[var(--surface)] {entry.code ===
						selected
							? 'bg-[var(--surface-sunken)] ring-1 ring-[var(--accent)]'
							: ''}"
						onclick={() => onpick(entry)}
						aria-label={m.inventory_cabys_assign({ description: entry.description })}
					>
						<span class="font-mono text-xs text-[var(--text-subtle)]">{entry.code}</span>
						<span class="flex-1 truncate text-sm text-[var(--text)]">{entry.description}</span>
						<span class="badge bg-[var(--surface-sunken)] text-[var(--text-muted)]">
							{ratePercentText(entry.tax_rate)} %
						</span>
					</button>
				</li>
			{/each}
		</ul>
	{:else if searched && !busy && !failed && !codigoIncompleto}
		<p class="mt-2 text-xs text-[var(--text-subtle)]">
			{buscadoPorCodigo ? m.inventory_cabys_code_unknown() : m.inventory_cabys_no_results()}
		</p>
	{/if}
</div>
