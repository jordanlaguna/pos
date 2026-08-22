<script lang="ts">
	import { untrack } from 'svelte';
	import { enhance } from '$app/forms';
	import { submit } from '$lib/ui/forms';
	import Icon from '$lib/ui/components/Icon.svelte';
	import PageHeader from '$lib/ui/components/PageHeader.svelte';
	import Field from '$lib/ui/components/Field.svelte';
	import Spinner from '$lib/ui/components/Spinner.svelte';
	import DocumentSheet from '$lib/ui/components/documents/DocumentSheet.svelte';
	import { computeTotals, configureMoney, formatMoney, round2 } from '$lib/domain/money';
	import { accentTheme } from '$lib/domain/color';
	import { formatDateTime } from '$lib/ui/format';
	import {
		CURRENCIES,
		TEMPLATE_IDS,
		ID_TYPES,
		type TemplateId,
		type Settings
	} from '$lib/domain/settings';
	import { m } from '$lib/paraglide/messages.js';
	import { currencyName, templateInfo } from '$lib/ui/catalogs';
	import type { Client, SaleDetail } from '$lib/domain/types';
	import type { ActionData, PageData } from './$types';

	let { data, form }: { data: PageData; form: ActionData } = $props();

	type Seccion = 'negocio' | 'moneda' | 'documentos' | 'electronica';
	let seccion = $state<Seccion>('negocio');
	let submitting = $state(false);

	/**
	 * Las cuatro pestañas. Solo el identificador y el icono: el rótulo se pide al
	 * catálogo al pintar, porque una constante de módulo con el texto adentro se
	 * evalúa una vez por proceso y todas las peticiones verían el idioma de la
	 * primera (defecto 17).
	 */
	const SECCIONES: { id: Seccion; icon: 'idcard' | 'wallet' | 'receipt' | 'bolt' }[] = [
		{ id: 'negocio', icon: 'idcard' },
		{ id: 'moneda', icon: 'wallet' },
		{ id: 'documentos', icon: 'receipt' },
		{ id: 'electronica', icon: 'bolt' }
	];

	function seccionRotulo(id: Seccion): string {
		switch (id) {
			case 'negocio':
				return m.settings_tab_business();
			case 'moneda':
				return m.settings_tab_currency();
			case 'documentos':
				return m.settings_tab_documents();
			case 'electronica':
				return m.settings_tab_einvoicing();
		}
	}

	// ---------------------------------------------------------------- borrador
	/*
	 * Los campos se enlazan a este estado y no directamente al formulario, porque
	 * la vista previa tiene que reflejar lo que se está escribiendo antes de
	 * guardarlo. Lo que se envía sigue siendo el formulario: el servidor valida
	 * lo que llega, no lo que esta pantalla creyó tener.
	 */
	// `untrack`: es el punto de partida del borrador, no una fuente que lo siga.
	// Cuando se guarda, la pantalla se recarga entera.
	const inicial = untrack(() => data.configuracion);

	let business = $state({ ...inicial.business });
	let currency = $state({ ...inicial.currency });
	let impuestoNombre = $state(inicial.tax.name);
	let tasaPorcentaje = $state(String(round2(inicial.tax.rate * 100)));
	let document = $state({ ...inicial.document });
	let colorAcento = $state(inicial.appearance.accentColor);
	let eInvoicing = $state({ ...inicial.eInvoicing });

	let quitarLogo = $state(false);
	/** Vista previa del archivo recién elegido, antes de subirlo. */
	let logoElegido = $state<string | null>(null);

	const borrador: Settings = $derived({
		business,
		currency,
		tax: { name: impuestoNombre, rate: (Number(tasaPorcentaje.replace(',', '.')) || 0) / 100 },
		document,
		appearance: { accentColor: colorAcento },
		eInvoicing
	});

	/*
	 * Mientras se está en esta pantalla, los montos se muestran con la moneda del
	 * borrador: cambiar el símbolo se ve al instante, en la vista previa y en el
	 * resto de la página. Al salir se restituye la configuración guardada, porque
	 * el formato vive en un módulo y no se limpia solo.
	 */
	$effect.pre(() => {
		configureMoney(borrador);
		return () => configureMoney(data.configuracion);
	});

	const acento = $derived(accentTheme(colorAcento));

	/*
	 * Llave para volver a dibujar los ejemplos de moneda.
	 *
	 * `formatMoney` lee el formato de un módulo, no de una señal, así que cambiar
	 * el símbolo no vuelve a renderizar nada por sí solo: un bloque cuyo contenido
	 * es una lista fija de números no tiene ninguna dependencia que se haya
	 * movido. Con esto el bloque se recrea cuando cambia la moneda —después de que
	 * el `$effect.pre` de arriba ya la aplicó— y los ejemplos dicen la verdad.
	 *
	 * La vista previa del documento no lo necesita: recibe el borrador por
	 * propiedad y se redibuja porque la propiedad cambió.
	 */
	const claveMoneda = $derived(
		`${currency.code}|${currency.symbol}|${currency.decimals}|${currency.thousandsSeparator}|${currency.decimalSeparator}|${currency.symbolAtEnd}|${currency.space}|${tasaPorcentaje}|${impuestoNombre}`
	);

	function aplicarMoneda(codigo: string) {
		const preset = CURRENCIES.find((moneda) => moneda.code === codigo);
		if (!preset) return;
		currency = { ...preset };
	}

	function elegirLogo(event: Event) {
		const input = event.currentTarget as HTMLInputElement;
		const file = input.files?.[0];
		logoElegido = file ? URL.createObjectURL(file) : null;
		if (file) quitarLogo = false;
	}

	const logoUrl = $derived(
		logoElegido ??
			(!quitarLogo && data.tieneLogo && data.logoVersion ? `/marca/logo?v=${data.logoVersion}` : null)
	);

	// ------------------------------------------------------------ vista previa
	/*
	 * Fecha fija a propósito: una fecha calculada saldría distinta en el servidor
	 * y en el navegador, y Svelte avisaría de que el HTML no coincide al hidratar.
	 */
	const FECHA_EJEMPLO = '2026-08-15T14:32:00';

	const LINEAS_EJEMPLO = [
		{ id_product: 1, name: 'Arroz Tío Pelón 1kg', quantity: 2, price: 1450 },
		{ id_product: 2, name: 'Café 1820 500g', quantity: 1, price: 4250 },
		{ id_product: 3, name: 'Leche Dos Pinos 1L', quantity: 3, price: 1290 }
	];

	const CLIENTE_EJEMPLO: Client = {
		id_client: 1,
		identification: '115670987',
		name: 'Ana',
		last_name: 'Castro',
		second_name: 'Núñez',
		email: 'ana.castro@correo.cr',
		telephone: 88012233,
		address: 'San José, Curridabat, 200 m sur del parque',
		register_date: '2026-02-11'
	};

	const ventaEjemplo: SaleDetail = $derived.by(() => {
		const items = LINEAS_EJEMPLO.map((l) => ({ ...l, subtotal: round2(l.price * l.quantity) }));
		const totales = computeTotals(items, borrador.tax.rate);
		const recibido = Math.ceil(totales.total / 1000) * 1000;
		return {
			id: 0,
			sale_number: '20260815143200',
			created_at: FECHA_EJEMPLO,
			payment_method: 'Efectivo',
			subtotal: totales.subtotal,
			tax: totales.tax,
			total: totales.total,
			cash_received: recibido,
			change_given: round2(recibido - totales.total),
			client_id: 1,
			user_id: 2,
			user_name: 'María Rojas',
			items
		};
	});

	const codigosEjemplo = { 1: '7441000100015', 2: '7441000200014', 3: '7441000300013' };

	function seleccionarPlantilla(id: TemplateId) {
		document = { ...document, template: id };
	}
</script>

<PageHeader
	title={m.settings_title()}
	description={m.settings_description()}
>
	{#snippet actions()}
		{#if data.actualizado}
			<span class="hidden text-xs text-[var(--text-subtle)] sm:inline">
				{m.settings_last_change({ date: formatDateTime(data.actualizado) })}
			</span>
		{/if}
		<button type="submit" form="config-form" class="btn btn-primary" disabled={submitting}>
			{#if submitting}<Spinner size={15} />{m.common_saving()}{:else}
				<Icon name="check" size={15} />{m.common_save_changes()}
			{/if}
		</button>
	{/snippet}
</PageHeader>

{#if form?.errors?.form}
	<p
		class="mb-4 flex items-center gap-2 rounded-lg border border-[var(--negative)] bg-[var(--negative-bg)] p-3 text-sm text-[var(--negative)]"
	>
		<Icon name="alert" size={16} />
		{form.errors.form}
	</p>
{/if}

<!-- Pestañas: cambian de sección sin desmontar los campos. -->
<div class="mb-4 flex flex-wrap gap-1 border-b border-[var(--border)]">
	{#each SECCIONES as item (item.id)}
		<button
			type="button"
			class="flex items-center gap-2 border-b-2 px-4 py-2.5 text-sm font-semibold transition-colors
				{seccion === item.id
				? 'border-[var(--accent)] text-[var(--accent)]'
				: 'border-transparent text-[var(--text-muted)] hover:text-[var(--text)]'}"
			onclick={() => (seccion = item.id)}
			aria-current={seccion === item.id ? 'true' : undefined}
		>
			<Icon name={item.icon} size={15} />
			{seccionRotulo(item.id)}
		</button>
	{/each}
</div>

<!--
	Un solo formulario para las cuatro secciones. Las que no se ven se ocultan con
	`display`, no con `{#if}`: si se desmontaran, sus campos no viajarían en el
	envío y guardar desde una pestaña borraría lo configurado en las otras.
-->
<form
	id="config-form"
	method="POST"
	action="?/guardar"
	enctype="multipart/form-data"
	use:enhance={submit({
		setBusy: (v) => (submitting = v),
		onSuccess: () => {
			/*
			 * Recarga completa en lugar de `invalidateAll`. La moneda y el acento
			 * viven en el módulo de dinero y en una etiqueta <style> del layout:
			 * una recarga garantiza que TODA la aplicación quede con lo guardado,
			 * sin depender de qué componente se acordó de volver a renderizarse.
			 */
			if (typeof window !== 'undefined') window.location.reload();
		}
	})}
>
	<!-- ------------------------------------------------------------ business -->
	<div style:display={seccion === 'negocio' ? '' : 'none'}>
		<div class="grid gap-4 lg:grid-cols-3">
			<div class="card p-5 lg:col-span-2">
				<h2 class="mb-4 text-sm font-bold text-[var(--text)]">{m.settings_business_data()}</h2>
				<div class="grid gap-4 sm:grid-cols-2">
					<Field
						label={m.settings_trade_name()}
						name="negocio_nombre"
						bind:value={business.name}
						required
						icon="tag"
						error={form?.errors?.negocio_nombre}
						hint={m.settings_trade_name_hint()}
						class="sm:col-span-2"
					/>
					<Field
						label={m.settings_legal_name()}
						name="negocio_razon_social"
						bind:value={business.legalName}
						error={form?.errors?.negocio_razon_social}
						hint={m.settings_legal_name_hint()}
					/>

					<div>
						<label class="label" for="tipo-id">{m.settings_id_type()}</label>
						<select
							id="tipo-id"
							name="negocio_tipo_identificacion"
							class="input"
							bind:value={business.taxIdType}
						>
							{#each ID_TYPES as tipo (tipo.code)}
								<option value={tipo.code}>{tipo.label}</option>
							{/each}
						</select>
					</div>

					<Field
						label={m.settings_tax_id()}
						name="negocio_identificacion"
						bind:value={business.taxId}
						icon="idcard"
						error={form?.errors?.negocio_identificacion}
					/>
					<Field
						label={m.settings_phone()}
						name="negocio_telefono"
						bind:value={business.phone}
						icon="phone"
						error={form?.errors?.negocio_telefono}
					/>
					<Field
						label={m.settings_email()}
						name="negocio_correo"
						type="email"
						bind:value={business.email}
						icon="mail"
						error={form?.errors?.negocio_correo}
					/>
					<Field
						label={m.settings_website()}
						name="negocio_sitio_web"
						bind:value={business.website}
						error={form?.errors?.negocio_sitio_web}
					/>
					<Field
						label={m.settings_address()}
						name="negocio_direccion"
						bind:value={business.address}
						error={form?.errors?.negocio_direccion}
						class="sm:col-span-2"
					/>
				</div>
			</div>

			<div class="space-y-4">
				<!-- ------------------------------------------------------- logo -->
				<div class="card p-5">
					<h2 class="mb-1 text-sm font-bold text-[var(--text)]">{m.settings_logo()}</h2>
					<p class="mb-3 text-xs text-[var(--text-subtle)]">
						{m.settings_logo_hint()}
					</p>

					<div
						class="mb-3 grid h-28 place-items-center rounded-lg border border-dashed border-[var(--border)] bg-[var(--surface-sunken)] p-2"
					>
						{#if logoUrl}
							<img src={logoUrl} alt={m.settings_logo_alt()} class="max-h-24 w-auto object-contain" />
						{:else}
							<span class="text-xs text-[var(--text-subtle)]">{m.settings_no_logo()}</span>
						{/if}
					</div>

					<input
						type="file"
						name="logo"
						accept="image/png,image/jpeg,image/webp"
						onchange={elegirLogo}
						class="input cursor-pointer file:mr-3 file:rounded file:border-0 file:bg-[var(--surface-sunken)] file:px-3 file:py-1 file:text-xs file:font-semibold file:text-[var(--text-muted)]"
					/>
					{#if form?.errors?.logo}
						<p class="mt-1 flex items-center gap-1 text-xs text-[var(--negative)]">
							<Icon name="alert" size={12} />
							{form.errors.logo}
						</p>
					{/if}

					{#if data.tieneLogo}
						<label class="mt-3 flex items-center gap-2 text-xs text-[var(--text-muted)]">
							<input type="checkbox" name="quitar_logo" bind:checked={quitarLogo} />
							{m.settings_remove_logo()}
						</label>
					{/if}

					<p class="mt-3 text-[11px] leading-relaxed text-[var(--text-subtle)]">
						{m.settings_no_svg()}
					</p>
				</div>

				<!-- ------------------------------------------------ color de la app -->
				<div class="card p-5">
					<h2 class="mb-1 text-sm font-bold text-[var(--text)]">{m.settings_accent()}</h2>
					<p class="mb-3 text-xs text-[var(--text-subtle)]">
						{m.settings_accent_hint()}
					</p>

					<div class="flex items-center gap-3">
						<input
							type="color"
							name="apariencia_color"
							bind:value={colorAcento}
							class="h-10 w-14 cursor-pointer rounded border border-[var(--border)] bg-transparent"
							aria-label={m.settings_accent()}
						/>
						<code class="text-xs text-[var(--text-muted)]">{colorAcento}</code>
					</div>

					<div class="mt-3 grid grid-cols-2 gap-2 text-center text-[11px]">
						<div class="rounded-lg border border-[var(--border)] p-2">
							<span
								class="mb-1.5 block rounded px-2 py-1.5 text-xs font-semibold"
								style="background:{acento.light}; color:{acento.inkLight}"
							>
								{m.settings_theme_light()}
							</span>
							<span class="text-[var(--text-subtle)]">
								{m.settings_contrast({ ratio: acento.contrastLight.toFixed(1) })}
							</span>
						</div>
						<div class="rounded-lg border border-[var(--border)] p-2">
							<span
								class="mb-1.5 block rounded px-2 py-1.5 text-xs font-semibold"
								style="background:{acento.dark}; color:{acento.inkDark}"
							>
								{m.settings_theme_dark()}
							</span>
							<span class="text-[var(--text-subtle)]">
								{m.settings_contrast({ ratio: acento.contrastDark.toFixed(1) })}
							</span>
						</div>
					</div>

					{#if !acento.chart}
						<p
							class="mt-3 flex gap-2 rounded-lg border border-[var(--warning)] bg-[var(--warning-bg)] p-2 text-[11px] text-[var(--warning)]"
						>
							<Icon name="info" size={13} class="mt-px shrink-0" />
							<span>
								{m.settings_accent_chart_warning()}
							</span>
						</p>
					{/if}
				</div>
			</div>
		</div>
	</div>

	<!-- ------------------------------------------------------------- currency -->
	<div style:display={seccion === 'moneda' ? '' : 'none'}>
		<div class="grid gap-4 lg:grid-cols-3">
			<div class="card p-5 lg:col-span-2">
				<h2 class="mb-1 text-sm font-bold text-[var(--text)]">{m.settings_currency()}</h2>
				<p class="mb-4 text-xs text-[var(--text-subtle)]">
					{m.settings_currency_hint()}
				</p>

				<div class="grid gap-4 sm:grid-cols-2">
					<div class="sm:col-span-2">
						<label class="label" for="moneda-preset">{m.settings_currency()}</label>
						<select
							id="moneda-preset"
							class="input"
							value={currency.code}
							onchange={(e) => aplicarMoneda(e.currentTarget.value)}
						>
							{#each CURRENCIES as moneda (moneda.code)}
								<option value={moneda.code}>
									{m.settings_currency_option({
										name: currencyName(moneda.code),
										code: moneda.code
									})}
								</option>
							{/each}
							{#if !CURRENCIES.some((moneda) => moneda.code === currency.code)}
								<option value={currency.code}>
									{m.settings_currency_custom({ code: currency.code })}
								</option>
							{/if}
						</select>
					</div>

					<Field
						label={m.settings_currency_code()}
						name="moneda_codigo"
						bind:value={currency.code}
						required
						error={form?.errors?.moneda_codigo}
						hint={m.settings_currency_code_hint()}
					/>
					<Field
						label={m.settings_currency_symbol()}
						name="moneda_simbolo"
						bind:value={currency.symbol}
						required
						error={form?.errors?.moneda_simbolo}
					/>
					<Field
						label={m.settings_currency_decimals()}
						name="moneda_decimales"
						type="number"
						min="0"
						max="4"
						bind:value={currency.decimals}
						required
						error={form?.errors?.moneda_decimales}
					/>

					<div>
						<label class="label" for="sep-miles">{m.settings_thousands_separator()}</label>
						<input
							id="sep-miles"
							class="input"
							name="moneda_separador_miles"
							maxlength="1"
							bind:value={currency.thousandsSeparator}
						/>
						<p class="mt-1 text-xs text-[var(--text-subtle)]">{m.settings_thousands_empty()}</p>
					</div>
					<div>
						<label class="label" for="sep-decimal">{m.settings_decimal_separator()}</label>
						<input
							id="sep-decimal"
							class="input"
							name="moneda_separador_decimal"
							maxlength="1"
							bind:value={currency.decimalSeparator}
						/>
					</div>

					<div class="flex flex-col justify-center gap-2 text-sm">
						<label class="flex items-center gap-2 text-[var(--text-muted)]">
							<input
								type="checkbox"
								name="moneda_simbolo_al_final"
								bind:checked={currency.symbolAtEnd}
							/>
							{m.settings_symbol_at_end()}
						</label>
						<label class="flex items-center gap-2 text-[var(--text-muted)]">
							<input type="checkbox" name="moneda_espacio" bind:checked={currency.space} />
							{m.settings_symbol_space()}
						</label>
					</div>
				</div>

				<h2 class="mt-6 mb-1 text-sm font-bold text-[var(--text)]">{m.settings_tax()}</h2>
				<p class="mb-4 text-xs text-[var(--text-subtle)]">
					{m.settings_tax_hint()}
				</p>
				<div class="grid gap-4 sm:grid-cols-2">
					<Field
						label={m.settings_tax_name()}
						name="impuesto_nombre"
						bind:value={impuestoNombre}
						required
						error={form?.errors?.impuesto_nombre}
						hint={m.settings_tax_name_hint()}
					/>
					<Field
						label={m.settings_tax_rate()}
						name="impuesto_tasa"
						inputmode="decimal"
						bind:value={tasaPorcentaje}
						required
						error={form?.errors?.impuesto_tasa}
						hint={m.settings_tax_rate_hint()}
					/>
				</div>
			</div>

			<!-- Vista previa de la moneda -->
			<div class="card h-fit p-5">
				<h2 class="mb-3 text-sm font-bold text-[var(--text)]">{m.settings_money_preview()}</h2>
				{#key claveMoneda}
					<dl class="space-y-2 text-sm">
						{#each [1450, 79800, 3175119.2, -277] as valor (valor)}
							<div class="flex justify-between gap-3 border-b border-[var(--border)] pb-1.5">
								<dt class="text-[var(--text-subtle)]">{valor}</dt>
								<dd class="font-semibold tabular-nums text-[var(--text)]">{formatMoney(valor)}</dd>
							</div>
						{/each}
					</dl>
					<p class="mt-3 text-xs text-[var(--text-subtle)]">
						{m.settings_money_example({
							amount: formatMoney(10000),
							tax: impuestoNombre,
							taxAmount: formatMoney(round2(10000 * borrador.tax.rate))
						})}
					</p>
				{/key}
			</div>
		</div>
	</div>

	<!-- --------------------------------------------------------- documentos -->
	<div style:display={seccion === 'documentos' ? '' : 'none'}>
		<div class="grid gap-4 lg:grid-cols-5">
			<div class="space-y-4 lg:col-span-2">
				<div class="card p-5">
					<h2 class="mb-1 text-sm font-bold text-[var(--text)]">{m.settings_template()}</h2>
					<p class="mb-3 text-xs text-[var(--text-subtle)]">
						{m.settings_template_hint()}
					</p>

					<div class="space-y-2">
						{#each TEMPLATE_IDS as id (id)}
							{@const plantilla = templateInfo(id)}
							<label
								class="flex cursor-pointer gap-3 rounded-lg border p-3 transition-colors
									{document.template === id
									? 'border-[var(--accent)] bg-[var(--surface-sunken)]'
									: 'border-[var(--border)] hover:bg-[var(--surface-sunken)]'}"
							>
								<input
									type="radio"
									name="documento_plantilla"
									value={id}
									checked={document.template === id}
									onchange={() => seleccionarPlantilla(id)}
									class="mt-0.5"
								/>
								<span class="min-w-0 flex-1">
									<span class="flex items-baseline justify-between gap-2">
										<span class="text-sm font-semibold text-[var(--text)]">{plantilla.name}</span>
										<span class="text-[10px] text-[var(--text-subtle)]">{plantilla.paper}</span>
									</span>
									<span class="mt-0.5 block text-xs leading-relaxed text-[var(--text-muted)]">
										{plantilla.description}
									</span>
								</span>
							</label>
						{/each}
					</div>

					{#if document.template === 'tiquete'}
						<div class="mt-4">
							<span class="label">{m.settings_roll_width()}</span>
							<div class="flex gap-4 text-sm text-[var(--text-muted)]">
								{#each [58, 80] as ancho (ancho)}
									<label class="flex items-center gap-2">
										<input
											type="radio"
											name="documento_ancho"
											value={String(ancho)}
											checked={document.receiptWidth === ancho}
											onchange={() => (document = { ...document, receiptWidth: ancho as 58 | 80 })}
										/>
										{m.settings_roll_mm({ mm: ancho })}
									</label>
								{/each}
							</div>
						</div>
					{:else}
						<!-- El ancho sigue viajando aunque no se muestre: si no, se perdería. -->
						<input type="hidden" name="documento_ancho" value={String(document.receiptWidth)} />
					{/if}
				</div>

				<div class="card p-5">
					<h2 class="mb-3 text-sm font-bold text-[var(--text)]">{m.settings_content_and_brand()}</h2>

					<div class="mb-4 flex items-center gap-3">
						<input
							type="color"
							name="documento_color"
							bind:value={document.color}
							class="h-10 w-14 cursor-pointer rounded border border-[var(--border)] bg-transparent"
							aria-label={m.settings_document_color()}
						/>
						<div class="min-w-0">
							<p class="text-xs font-semibold text-[var(--text)]">{m.settings_document_color()}</p>
							<p class="text-[11px] text-[var(--text-subtle)]">
								{m.settings_document_color_hint()}
							</p>
						</div>
					</div>

					<div class="space-y-2 text-sm text-[var(--text-muted)]">
						<label class="flex items-center gap-2">
							<input
								type="checkbox"
								name="documento_mostrar_logo"
								bind:checked={document.showLogo}
							/>
							{m.settings_show_logo()}
						</label>
						<label class="flex items-center gap-2">
							<input
								type="checkbox"
								name="documento_mostrar_codigo"
								bind:checked={document.showBarcode}
							/>
							{m.settings_show_barcode()}
						</label>
					</div>

					<div class="mt-4 space-y-4">
						<Field
							label={m.settings_thanks_message()}
							name="documento_mensaje"
							bind:value={document.thanksMessage}
							error={form?.errors?.documento_mensaje}
						/>
						<Field
							label={m.settings_legal_notice()}
							name="documento_leyenda"
							bind:value={document.legalNotice}
							error={form?.errors?.documento_leyenda}
							hint={m.settings_legal_notice_hint()}
						/>
						<div>
							<label class="label" for="doc-notas">{m.settings_notes()}</label>
							<textarea
								id="doc-notas"
								name="documento_notas"
								rows="3"
								class="input resize-y"
								bind:value={document.notes}
								placeholder={m.settings_notes_placeholder()}
							></textarea>
							<p class="mt-1 text-xs text-[var(--text-subtle)]">
								{m.settings_notes_hint()}
							</p>
						</div>
					</div>
				</div>
			</div>

			<!-- Vista previa en vivo -->
			<div class="lg:col-span-3">
				<div class="card p-4">
					<div class="mb-3 flex items-center gap-2">
						<Icon name="eye" size={15} class="text-[var(--text-subtle)]" />
						<h2 class="text-sm font-bold text-[var(--text)]">{m.settings_preview()}</h2>
						<span class="text-xs text-[var(--text-subtle)]">{m.settings_preview_sample()}</span>
					</div>
					<div class="overflow-x-auto rounded-lg bg-[var(--surface-sunken)] p-4">
						<DocumentSheet
							sale={ventaEjemplo}
							client={CLIENTE_EJEMPLO}
							returns={[]}
							settings={borrador}
							{logoUrl}
							barcodes={codigosEjemplo}
						/>
					</div>
				</div>
			</div>
		</div>
	</div>

	<!-- --------------------------------------------------------- electrónica -->
	<div style:display={seccion === 'electronica' ? '' : 'none'}>
		<div class="grid gap-4 lg:grid-cols-3">
			<div class="card p-5 lg:col-span-2">
				<h2 class="mb-1 text-sm font-bold text-[var(--text)]">{m.settings_einvoicing()}</h2>
				<p class="mb-4 text-xs text-[var(--text-subtle)]">
					{m.settings_einvoicing_hint()}
				</p>

				<div
					class="mb-5 flex gap-3 rounded-lg border border-[var(--warning)] bg-[var(--warning-bg)] p-3 text-xs text-[var(--warning)]"
				>
					<Icon name="alert" size={16} class="mt-px shrink-0" />
					<div class="space-y-1.5">
						<p class="font-semibold">{m.settings_einvoicing_warning_title()}</p>
						<p class="leading-relaxed">
							{m.settings_einvoicing_warning_1()}
						</p>
						<p class="leading-relaxed">
							{m.settings_einvoicing_warning_2()}
						</p>
					</div>
				</div>

				<label class="mb-4 flex items-start gap-2 text-sm text-[var(--text-muted)]">
					<input
						type="checkbox"
						name="electronica_activa"
						bind:checked={eInvoicing.enabled}
						class="mt-1"
					/>
					<span>
						{m.settings_einvoicing_enabled()}
						<span class="block text-xs text-[var(--text-subtle)]">
							{m.settings_einvoicing_enabled_hint()}
						</span>
					</span>
				</label>

				<div class="grid gap-4 sm:grid-cols-2">
					<div>
						<label class="label" for="fe-ambiente">{m.settings_environment()}</label>
						<select
							id="fe-ambiente"
							name="electronica_ambiente"
							class="input"
							bind:value={eInvoicing.environment}
						>
							<option value="sandbox">{m.settings_environment_sandbox()}</option>
							<option value="produccion">{m.settings_environment_production()}</option>
						</select>
					</div>
					<Field
						label={m.settings_economic_activity()}
						name="electronica_actividad"
						bind:value={eInvoicing.economicActivity}
						error={form?.errors?.electronica_actividad}
						hint={m.settings_economic_activity_hint()}
					/>
					<Field
						label={m.settings_branch()}
						name="electronica_sucursal"
						bind:value={eInvoicing.branch}
						error={form?.errors?.electronica_sucursal}
						hint={m.settings_branch_hint()}
					/>
					<Field
						label={m.settings_terminal()}
						name="electronica_terminal"
						bind:value={eInvoicing.terminal}
						error={form?.errors?.electronica_terminal}
						hint={m.settings_terminal_hint()}
					/>
					<Field
						label={m.settings_atv_user()}
						name="electronica_usuario"
						bind:value={eInvoicing.atvUser}
						error={form?.errors?.electronica_usuario}
						class="sm:col-span-2"
					/>
				</div>
			</div>

			<div class="card h-fit p-5">
				<h2 class="mb-3 text-sm font-bold text-[var(--text)]">{m.settings_missing_title()}</h2>
				<ol class="space-y-3 text-xs leading-relaxed text-[var(--text-muted)]">
					<li class="flex gap-2">
						<span class="font-bold text-[var(--text-subtle)]">1.</span>
						<span>
							<strong class="text-[var(--text)]">{m.settings_missing_1_title()}</strong>
							{m.settings_missing_1()}
						</span>
					</li>
					<li class="flex gap-2">
						<span class="font-bold text-[var(--text-subtle)]">2.</span>
						<span>
							<strong class="text-[var(--text)]">{m.settings_missing_2_title()}</strong>
							{m.settings_missing_2()}
						</span>
					</li>
					<li class="flex gap-2">
						<span class="font-bold text-[var(--text-subtle)]">3.</span>
						<span>
							<strong class="text-[var(--text)]">{m.settings_missing_3_title()}</strong>
							{m.settings_missing_3()}
						</span>
					</li>
					<li class="flex gap-2">
						<span class="font-bold text-[var(--text-subtle)]">4.</span>
						<span>
							<strong class="text-[var(--text)]">{m.settings_missing_4_title()}</strong>
							{m.settings_missing_4()}
						</span>
					</li>
					<li class="flex gap-2">
						<span class="font-bold text-[var(--text-subtle)]">5.</span>
						<span>
							<strong class="text-[var(--text)]">{m.settings_missing_5_title()}</strong>
							{m.settings_missing_5()}
						</span>
					</li>
				</ol>
			</div>
		</div>
	</div>
</form>
