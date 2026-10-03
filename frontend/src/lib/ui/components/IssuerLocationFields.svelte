<script lang="ts">
	/**
	 * La ubicación del emisor con los códigos de Hacienda (T-722, RN-83).
	 *
	 * Tres desplegables encadenados —provincia, cantón, distrito— y dos textos, el
	 * barrio y las otras señas. **Elegir un padre vacía a los hijos**: un cantón
	 * «02» de San José no es el «02» de Alajuela, y dejarlo elegido mandaría a
	 * Hacienda un lugar que nadie eligió.
	 *
	 * Los nombres son los del catálogo de Hacienda y no se traducen; los rótulos,
	 * sí. Los `name` del formulario son los que lee `/configuracion`.
	 */
	import {
		NEIGHBORHOOD_MAX,
		OTHER_SIGNS_MAX,
		cantonOptions,
		districtOptions,
		provinceOptions,
		type IssuerLocation
	} from '$lib/domain/location';
	import { m } from '$lib/paraglide/messages.js';

	let {
		location = $bindable(),
		errors = {},
		required = false
	}: {
		location: IssuerLocation;
		errors?: Record<string, string | undefined>;
		/** Con la factura electrónica encendida es obligatoria (RN-83). */
		required?: boolean;
	} = $props();

	const provincias = provinceOptions();
	const cantones = $derived(cantonOptions(location.province));
	const distritos = $derived(districtOptions(location.province, location.canton));

	function elegirProvincia(event: Event) {
		const province = (event.currentTarget as HTMLSelectElement).value;
		location = { ...location, province, canton: '', district: '' };
	}

	function elegirCanton(event: Event) {
		const canton = (event.currentTarget as HTMLSelectElement).value;
		location = { ...location, canton, district: '' };
	}
</script>

<div class="grid gap-4 sm:grid-cols-3" data-ubicacion>
	<div>
		<label class="label" for="ubicacion-provincia">
			{m.settings_province()}{#if required}<span class="text-[var(--negative)]" aria-hidden="true">*</span>{/if}
		</label>
		<select
			id="ubicacion-provincia"
			name="negocio_provincia"
			class="input"
			value={location.province}
			onchange={elegirProvincia}
			aria-invalid={errors.negocio_provincia ? 'true' : undefined}
		>
			<option value="">{m.settings_choose()}</option>
			{#each provincias as p (p.code)}
				<option value={p.code}>{p.name}</option>
			{/each}
		</select>
		{#if errors.negocio_provincia}<p class="mt-1 text-xs text-[var(--negative)]">{errors.negocio_provincia}</p>{/if}
	</div>

	<div>
		<label class="label" for="ubicacion-canton">
			{m.settings_canton()}{#if required}<span class="text-[var(--negative)]" aria-hidden="true">*</span>{/if}
		</label>
		<select
			id="ubicacion-canton"
			name="negocio_canton"
			class="input"
			value={location.canton}
			onchange={elegirCanton}
			disabled={cantones.length === 0}
			aria-invalid={errors.negocio_canton ? 'true' : undefined}
		>
			<option value="">{m.settings_choose()}</option>
			{#each cantones as c (c.code)}
				<option value={c.code}>{c.name}</option>
			{/each}
		</select>
		{#if errors.negocio_canton}<p class="mt-1 text-xs text-[var(--negative)]">{errors.negocio_canton}</p>{/if}
	</div>

	<div>
		<label class="label" for="ubicacion-distrito">
			{m.settings_district()}{#if required}<span class="text-[var(--negative)]" aria-hidden="true">*</span>{/if}
		</label>
		<select
			id="ubicacion-distrito"
			name="negocio_distrito"
			class="input"
			bind:value={location.district}
			disabled={distritos.length === 0}
			aria-invalid={errors.negocio_distrito ? 'true' : undefined}
		>
			<option value="">{m.settings_choose()}</option>
			{#each distritos as d (d.code)}
				<option value={d.code}>{d.name}</option>
			{/each}
		</select>
		{#if errors.negocio_distrito}<p class="mt-1 text-xs text-[var(--negative)]">{errors.negocio_distrito}</p>{/if}
	</div>

	<div>
		<label class="label" for="ubicacion-barrio">{m.settings_neighborhood()}</label>
		<input
			id="ubicacion-barrio"
			name="negocio_barrio"
			class="input"
			maxlength={NEIGHBORHOOD_MAX}
			bind:value={location.neighborhood}
			aria-invalid={errors.negocio_barrio ? 'true' : undefined}
		/>
		{#if errors.negocio_barrio}<p class="mt-1 text-xs text-[var(--negative)]">{errors.negocio_barrio}</p>{/if}
	</div>

	<div class="sm:col-span-2">
		<label class="label" for="ubicacion-senas">
			{m.settings_other_signs()}{#if required}<span class="text-[var(--negative)]" aria-hidden="true">*</span>{/if}
		</label>
		<input
			id="ubicacion-senas"
			name="negocio_otras_senas"
			class="input"
			maxlength={OTHER_SIGNS_MAX}
			bind:value={location.otherSigns}
			aria-invalid={errors.negocio_otras_senas ? 'true' : undefined}
		/>
		{#if errors.negocio_otras_senas}
			<p class="mt-1 text-xs text-[var(--negative)]">{errors.negocio_otras_senas}</p>
		{:else}
			<p class="mt-1 text-xs text-[var(--text-subtle)]">{m.settings_other_signs_hint()}</p>
		{/if}
	</div>
</div>
