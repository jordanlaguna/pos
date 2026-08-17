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
		TEMPLATES,
		ID_TYPES,
		type TemplateId,
		type Settings
	} from '$lib/domain/settings';
	import type { Client, SaleDetail } from '$lib/domain/types';
	import type { ActionData, PageData } from './$types';

	let { data, form }: { data: PageData; form: ActionData } = $props();

	type Seccion = 'negocio' | 'moneda' | 'documentos' | 'electronica';
	let seccion = $state<Seccion>('negocio');
	let submitting = $state(false);

	const SECCIONES: { id: Seccion; label: string; icon: 'idcard' | 'wallet' | 'receipt' | 'bolt' }[] =
		[
			{ id: 'negocio', label: 'Negocio', icon: 'idcard' },
			{ id: 'moneda', label: 'Moneda e impuesto', icon: 'wallet' },
			{ id: 'documentos', label: 'Documentos', icon: 'receipt' },
			{ id: 'electronica', label: 'Factura electrónica', icon: 'bolt' }
		];

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
		const preset = CURRENCIES.find((m) => m.code === codigo);
		if (!preset) return;
		// `label` es la etiqueta del selector, no parte de la moneda que se guarda.
		const { label: _label, ...valores } = preset;
		currency = { ...valores };
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
	title="Configuración"
	description="Los datos del negocio, la moneda, el impuesto y cómo se ve lo que se imprime."
>
	{#snippet actions()}
		{#if data.actualizado}
			<span class="hidden text-xs text-[var(--text-subtle)] sm:inline">
				Última modificación: {formatDateTime(data.actualizado)}
			</span>
		{/if}
		<button type="submit" form="config-form" class="btn btn-primary" disabled={submitting}>
			{#if submitting}<Spinner size={15} />Guardando…{:else}
				<Icon name="check" size={15} />Guardar cambios
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
			{item.label}
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
				<h2 class="mb-4 text-sm font-bold text-[var(--text)]">Datos del negocio</h2>
				<div class="grid gap-4 sm:grid-cols-2">
					<Field
						label="Nombre comercial"
						name="negocio_nombre"
						bind:value={business.name}
						required
						icon="tag"
						error={form?.errors?.negocio_nombre}
						hint="Es el que sale en el menú y encabeza el documento."
						class="sm:col-span-2"
					/>
					<Field
						label="Razón social"
						name="negocio_razon_social"
						bind:value={business.legalName}
						error={form?.errors?.negocio_razon_social}
						hint="Solo si difiere del nombre comercial."
					/>

					<div>
						<label class="label" for="tipo-id">Tipo de identificación</label>
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
						label="Cédula"
						name="negocio_identificacion"
						bind:value={business.taxId}
						icon="idcard"
						error={form?.errors?.negocio_identificacion}
					/>
					<Field
						label="Teléfono"
						name="negocio_telefono"
						bind:value={business.phone}
						icon="phone"
						error={form?.errors?.negocio_telefono}
					/>
					<Field
						label="Correo"
						name="negocio_correo"
						type="email"
						bind:value={business.email}
						icon="mail"
						error={form?.errors?.negocio_correo}
					/>
					<Field
						label="Sitio web"
						name="negocio_sitio_web"
						bind:value={business.website}
						error={form?.errors?.negocio_sitio_web}
					/>
					<Field
						label="Dirección"
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
					<h2 class="mb-1 text-sm font-bold text-[var(--text)]">Logo</h2>
					<p class="mb-3 text-xs text-[var(--text-subtle)]">
						Aparece en el menú y en el documento. PNG, JPG o WebP, hasta 250 KB.
					</p>

					<div
						class="mb-3 grid h-28 place-items-center rounded-lg border border-dashed border-[var(--border)] bg-[var(--surface-sunken)] p-2"
					>
						{#if logoUrl}
							<img src={logoUrl} alt="Logo del negocio" class="max-h-24 w-auto object-contain" />
						{:else}
							<span class="text-xs text-[var(--text-subtle)]">Sin logo</span>
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
							Quitar el logo actual
						</label>
					{/if}

					<p class="mt-3 text-[11px] leading-relaxed text-[var(--text-subtle)]">
						Los SVG no se admiten: son XML y pueden traer código dentro. El logo se sirve desde
						el mismo origen que el POS, así que solo se aceptan imágenes.
					</p>
				</div>

				<!-- ------------------------------------------------ color de la app -->
				<div class="card p-5">
					<h2 class="mb-1 text-sm font-bold text-[var(--text)]">Color de la interfaz</h2>
					<p class="mb-3 text-xs text-[var(--text-subtle)]">
						El tono para el tema oscuro y el color del texto se calculan a partir de este.
					</p>

					<div class="flex items-center gap-3">
						<input
							type="color"
							name="apariencia_color"
							bind:value={colorAcento}
							class="h-10 w-14 cursor-pointer rounded border border-[var(--border)] bg-transparent"
							aria-label="Color de la interfaz"
						/>
						<code class="text-xs text-[var(--text-muted)]">{colorAcento}</code>
					</div>

					<div class="mt-3 grid grid-cols-2 gap-2 text-center text-[11px]">
						<div class="rounded-lg border border-[var(--border)] p-2">
							<span
								class="mb-1.5 block rounded px-2 py-1.5 text-xs font-semibold"
								style="background:{acento.light}; color:{acento.inkLight}"
							>
								Tema claro
							</span>
							<span class="text-[var(--text-subtle)]">
								contraste {acento.contrastLight.toFixed(1)}:1
							</span>
						</div>
						<div class="rounded-lg border border-[var(--border)] p-2">
							<span
								class="mb-1.5 block rounded px-2 py-1.5 text-xs font-semibold"
								style="background:{acento.dark}; color:{acento.inkDark}"
							>
								Tema oscuro
							</span>
							<span class="text-[var(--text-subtle)]">
								contraste {acento.contrastDark.toFixed(1)}:1
							</span>
						</div>
					</div>

					{#if !acento.chart}
						<p
							class="mt-3 flex gap-2 rounded-lg border border-[var(--warning)] bg-[var(--warning-bg)] p-2 text-[11px] text-[var(--warning)]"
						>
							<Icon name="info" size={13} class="mt-px shrink-0" />
							<span>
								Este tono no se distingue lo suficiente sobre el fondo de los gráficos, así que
								las barras conservan el color validado. El resto de la interfaz sí lo usa.
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
				<h2 class="mb-1 text-sm font-bold text-[var(--text)]">Moneda</h2>
				<p class="mb-4 text-xs text-[var(--text-subtle)]">
					Elegí una y se completa el resto. Los separadores quedan editables porque la
					convención local no siempre coincide con el estándar.
				</p>

				<div class="grid gap-4 sm:grid-cols-2">
					<div class="sm:col-span-2">
						<label class="label" for="moneda-preset">Moneda</label>
						<select
							id="moneda-preset"
							class="input"
							value={currency.code}
							onchange={(e) => aplicarMoneda(e.currentTarget.value)}
						>
							{#each CURRENCIES as m (m.code)}
								<option value={m.code}>{m.label} ({m.code})</option>
							{/each}
							{#if !CURRENCIES.some((m) => m.code === currency.code)}
								<option value={currency.code}>{currency.code} (personalizada)</option>
							{/if}
						</select>
					</div>

					<Field
						label="Código"
						name="moneda_codigo"
						bind:value={currency.code}
						required
						error={form?.errors?.moneda_codigo}
						hint="ISO 4217: CRC, USD, EUR…"
					/>
					<Field
						label="Símbolo"
						name="moneda_simbolo"
						bind:value={currency.symbol}
						required
						error={form?.errors?.moneda_simbolo}
					/>
					<Field
						label="Decimales"
						name="moneda_decimales"
						type="number"
						min="0"
						max="4"
						bind:value={currency.decimals}
						required
						error={form?.errors?.moneda_decimales}
					/>

					<div>
						<label class="label" for="sep-miles">Separador de miles</label>
						<input
							id="sep-miles"
							class="input"
							name="moneda_separador_miles"
							maxlength="1"
							bind:value={currency.thousandsSeparator}
						/>
						<p class="mt-1 text-xs text-[var(--text-subtle)]">Vacío = sin separar.</p>
					</div>
					<div>
						<label class="label" for="sep-decimal">Separador decimal</label>
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
							Símbolo después de la cifra
						</label>
						<label class="flex items-center gap-2 text-[var(--text-muted)]">
							<input type="checkbox" name="moneda_espacio" bind:checked={currency.space} />
							Espacio entre símbolo y cifra
						</label>
					</div>
				</div>

				<h2 class="mt-6 mb-1 text-sm font-bold text-[var(--text)]">Impuesto</h2>
				<p class="mb-4 text-xs text-[var(--text-subtle)]">
					Se aplica al cobrar. Las devoluciones de ventas anteriores siguen usando la tasa con
					la que se cobraron, no esta.
				</p>
				<div class="grid gap-4 sm:grid-cols-2">
					<Field
						label="Nombre del impuesto"
						name="impuesto_nombre"
						bind:value={impuestoNombre}
						required
						error={form?.errors?.impuesto_nombre}
						hint="IVA, ISV, IGV…"
					/>
					<Field
						label="Tasa (%)"
						name="impuesto_tasa"
						inputmode="decimal"
						bind:value={tasaPorcentaje}
						required
						error={form?.errors?.impuesto_tasa}
						hint="13 para el IVA de Costa Rica."
					/>
				</div>
			</div>

			<!-- Vista previa de la moneda -->
			<div class="card h-fit p-5">
				<h2 class="mb-3 text-sm font-bold text-[var(--text)]">Así se van a ver los montos</h2>
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
						Una venta de {formatMoney(10000)} lleva {impuestoNombre}
						{formatMoney(round2(10000 * borrador.tax.rate))}.
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
					<h2 class="mb-1 text-sm font-bold text-[var(--text)]">Plantilla</h2>
					<p class="mb-3 text-xs text-[var(--text-subtle)]">
						Lo que se imprime al cobrar y desde cada factura.
					</p>

					<div class="space-y-2">
						{#each TEMPLATES as plantilla (plantilla.id)}
							<label
								class="flex cursor-pointer gap-3 rounded-lg border p-3 transition-colors
									{document.template === plantilla.id
									? 'border-[var(--accent)] bg-[var(--surface-sunken)]'
									: 'border-[var(--border)] hover:bg-[var(--surface-sunken)]'}"
							>
								<input
									type="radio"
									name="documento_plantilla"
									value={plantilla.id}
									checked={document.template === plantilla.id}
									onchange={() => seleccionarPlantilla(plantilla.id)}
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
							<span class="label">Ancho del rollo</span>
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
										{ancho} mm
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
					<h2 class="mb-3 text-sm font-bold text-[var(--text)]">Contenido y marca</h2>

					<div class="mb-4 flex items-center gap-3">
						<input
							type="color"
							name="documento_color"
							bind:value={document.color}
							class="h-10 w-14 cursor-pointer rounded border border-[var(--border)] bg-transparent"
							aria-label="Color del documento"
						/>
						<div class="min-w-0">
							<p class="text-xs font-semibold text-[var(--text)]">Color del documento</p>
							<p class="text-[11px] text-[var(--text-subtle)]">
								Franjas y cabeceras. No afecta al tiquete térmico.
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
							Mostrar el logo
						</label>
						<label class="flex items-center gap-2">
							<input
								type="checkbox"
								name="documento_mostrar_codigo"
								bind:checked={document.showBarcode}
							/>
							Mostrar el código de barras de cada producto
						</label>
					</div>

					<div class="mt-4 space-y-4">
						<Field
							label="Mensaje de despedida"
							name="documento_mensaje"
							bind:value={document.thanksMessage}
							error={form?.errors?.documento_mensaje}
						/>
						<Field
							label="Leyenda legal"
							name="documento_leyenda"
							bind:value={document.legalNotice}
							error={form?.errors?.documento_leyenda}
							hint="Mientras no se emita factura electrónica, conviene decirlo acá."
						/>
						<div>
							<label class="label" for="doc-notas">Notas y condiciones</label>
							<textarea
								id="doc-notas"
								name="documento_notas"
								rows="3"
								class="input resize-y"
								bind:value={document.notes}
								placeholder="Ej.: Los cambios se aceptan dentro de los 8 días con la factura."
							></textarea>
							<p class="mt-1 text-xs text-[var(--text-subtle)]">
								Solo en las facturas de página completa.
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
						<h2 class="text-sm font-bold text-[var(--text)]">Vista previa</h2>
						<span class="text-xs text-[var(--text-subtle)]">con datos de ejemplo</span>
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
				<h2 class="mb-1 text-sm font-bold text-[var(--text)]">Facturación electrónica</h2>
				<p class="mb-4 text-xs text-[var(--text-subtle)]">
					Datos del emisor ante Hacienda. Se guardan para tenerlos listos; VentaSys todavía no
					emite comprobantes.
				</p>

				<div
					class="mb-5 flex gap-3 rounded-lg border border-[var(--warning)] bg-[var(--warning-bg)] p-3 text-xs text-[var(--warning)]"
				>
					<Icon name="alert" size={16} class="mt-px shrink-0" />
					<div class="space-y-1.5">
						<p class="font-semibold">Todavía no emite comprobantes.</p>
						<p class="leading-relaxed">
							Emitir de verdad exige firmar el XML con la llave criptográfica del negocio,
							enviarlo a Hacienda y esperar la respuesta de aceptación. Nada de eso está
							implementado, así que activar esta casilla no hace que se emita: solo deja
							anotado que el negocio factura electrónicamente.
						</p>
						<p class="leading-relaxed">
							La llave y su PIN no se piden ni se guardan. Guardar una credencial que el
							sistema no usa es regalar el riesgo sin ganar nada.
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
						El negocio factura electrónicamente
						<span class="block text-xs text-[var(--text-subtle)]">
							Cambia el título del documento a «Factura electrónica». Conviene ajustar también
							la leyenda legal en la pestaña de Documentos.
						</span>
					</span>
				</label>

				<div class="grid gap-4 sm:grid-cols-2">
					<div>
						<label class="label" for="fe-ambiente">Ambiente</label>
						<select
							id="fe-ambiente"
							name="electronica_ambiente"
							class="input"
							bind:value={eInvoicing.environment}
						>
							<option value="sandbox">Pruebas (sandbox)</option>
							<option value="produccion">Producción</option>
						</select>
					</div>
					<Field
						label="Actividad económica"
						name="electronica_actividad"
						bind:value={eInvoicing.economicActivity}
						error={form?.errors?.electronica_actividad}
						hint="Código de 6 dígitos inscrito ante Hacienda."
					/>
					<Field
						label="Sucursal"
						name="electronica_sucursal"
						bind:value={eInvoicing.branch}
						error={form?.errors?.electronica_sucursal}
						hint="3 dígitos. Normalmente 001."
					/>
					<Field
						label="Terminal"
						name="electronica_terminal"
						bind:value={eInvoicing.terminal}
						error={form?.errors?.electronica_terminal}
						hint="5 dígitos. Una por caja."
					/>
					<Field
						label="Usuario de ATV"
						name="electronica_usuario"
						bind:value={eInvoicing.atvUser}
						error={form?.errors?.electronica_usuario}
						class="sm:col-span-2"
					/>
				</div>
			</div>

			<div class="card h-fit p-5">
				<h2 class="mb-3 text-sm font-bold text-[var(--text)]">Lo que falta para emitir</h2>
				<ol class="space-y-3 text-xs leading-relaxed text-[var(--text-muted)]">
					<li class="flex gap-2">
						<span class="font-bold text-[var(--text-subtle)]">1.</span>
						<span>
							<strong class="text-[var(--text)]">Código CABYS por producto.</strong>
							Hacienda exige la clasificación de bienes y servicios en cada línea. Hoy el
							catálogo no tiene ese campo.
						</span>
					</li>
					<li class="flex gap-2">
						<span class="font-bold text-[var(--text-subtle)]">2.</span>
						<span>
							<strong class="text-[var(--text)]">Consecutivo y clave.</strong>
							Numeración de 20 dígitos por sucursal y terminal, y una clave de 50 que
							incorpora la cédula y la fecha.
						</span>
					</li>
					<li class="flex gap-2">
						<span class="font-bold text-[var(--text-subtle)]">3.</span>
						<span>
							<strong class="text-[var(--text)]">Firma XAdES.</strong>
							El XML se firma con la llave criptográfica del contribuyente. Es la pieza que
							obliga a manejar un secreto en el servidor.
						</span>
					</li>
					<li class="flex gap-2">
						<span class="font-bold text-[var(--text-subtle)]">4.</span>
						<span>
							<strong class="text-[var(--text)]">Envío y respuesta.</strong>
							Se manda a Hacienda y se espera la aceptación, que es asíncrona: hay que
							guardar el estado y reintentar.
						</span>
					</li>
					<li class="flex gap-2">
						<span class="font-bold text-[var(--text-subtle)]">5.</span>
						<span>
							<strong class="text-[var(--text)]">Contingencia.</strong>
							Si Hacienda no responde, la venta igual tiene que poder cobrarse y enviarse
							después. Un POS no puede quedarse esperando con el cliente enfrente.
						</span>
					</li>
				</ol>
			</div>
		</div>
	</div>
</form>
