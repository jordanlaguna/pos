<script lang="ts">
	import { untrack } from 'svelte';
	import { enhance } from '$app/forms';
	import { replaceState } from '$app/navigation';
	import { page } from '$app/state';
	import { submit } from '$lib/ui/forms';
	import Icon from '$lib/ui/components/Icon.svelte';
	import PageHeader from '$lib/ui/components/PageHeader.svelte';
	import Field from '$lib/ui/components/Field.svelte';
	import Select from '$lib/ui/components/Select.svelte';
	import Modal from '$lib/ui/components/Modal.svelte';
	import Spinner from '$lib/ui/components/Spinner.svelte';
	import DocumentSheet from '$lib/ui/components/documents/DocumentSheet.svelte';
	import IssuerLocationFields from '$lib/ui/components/IssuerLocationFields.svelte';
	import { identificationTypeName } from '$lib/domain/identification';
	import { computeTotals, configureMoney, formatMoney, round2 } from '$lib/domain/money';
	import { accentTheme } from '$lib/domain/color';
	import {
		ALL_TYPES,
		ALWAYS_ON,
		AVAILABLE,
		DEBIT_NOTE,
		EXPORT_INVOICE,
		INVOICE,
		PURCHASE_INVOICE,
		TICKET,
		canToggle
	} from '$lib/domain/documentType';
	import { documentTypeLabel } from '$lib/ui/messages';
	import { formatDateTime } from '$lib/ui/format';
	import {
		CURRENCIES,
		TEMPLATE_IDS,
		VAT,
		type TemplateId,
		type Settings
	} from '$lib/domain/settings';
	import { m } from '$lib/paraglide/messages.js';
	import { currencyName, templateInfo } from '$lib/ui/catalogs';
	import type { Client, SaleDetail } from '$lib/domain/types';
	import type { ActionData, PageData } from './$types';

	let { data, form }: { data: PageData; form: ActionData } = $props();

	type Seccion = 'negocio' | 'moneda' | 'inventario' | 'documentos' | 'electronica' | 'sucursales';
	let submitting = $state(false);

	/**
	 * Las seis pestañas. Solo el identificador y el icono: el rótulo se pide al
	 * catálogo al pintar, porque una constante de módulo con el texto adentro se
	 * evalúa una vez por proceso y todas las peticiones verían el idioma de la
	 * primera (defecto 17).
	 */
	const SECCIONES: {
		id: Seccion;
		icon: 'idcard' | 'wallet' | 'box' | 'receipt' | 'bolt' | 'home';
	}[] = [
		{ id: 'negocio', icon: 'idcard' },
		{ id: 'moneda', icon: 'wallet' },
		{ id: 'inventario', icon: 'box' },
		{ id: 'documentos', icon: 'receipt' },
		{ id: 'electronica', icon: 'bolt' },
		{ id: 'sucursales', icon: 'home' }
	];

	function seccionRotulo(id: Seccion): string {
		switch (id) {
			case 'negocio':
				return m.settings_tab_business();
			case 'moneda':
				return m.settings_tab_currency();
			case 'inventario':
				return m.settings_tab_inventory();
			case 'documentos':
				return m.settings_tab_documents();
			case 'electronica':
				return m.settings_tab_einvoicing();
			case 'sucursales':
				return m.settings_tab_offices();
		}
	}

	/*
	 * La pestaña abierta viaja en la dirección (`?seccion=moneda`).
	 *
	 * Guardar recarga la pantalla entera —ver el formulario—, y con la pestaña
	 * solo en memoria la recarga volvía siempre a Negocio: quien acababa de
	 * cambiar la moneda tenía que ir a buscarla para ver si se guardó. En la
	 * dirección sobrevive a la recarga y el servidor ya la pinta abierta.
	 * `replaceState` y no `goto`: cambiar de pestaña no es navegar, no vuelve a
	 * pedir los datos ni deja una entrada por pestaña en el historial.
	 */
	function seccionDe(valor: string | null): Seccion {
		return SECCIONES.find((item) => item.id === valor)?.id ?? 'negocio';
	}

	let seccion = $state<Seccion>(untrack(() => seccionDe(page.url.searchParams.get('seccion'))));

	function abrirSeccion(id: Seccion) {
		seccion = id;
		const url = new URL(page.url);
		url.searchParams.set('seccion', id);
		replaceState(url, page.state);
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
	let document = $state({ ...inicial.document });
	let colorAcento = $state(inicial.appearance.accentColor);
	// El mínimo general (RN-101): en blanco es «sin general».
	let minimoGeneral = $state(
		inicial.inventory.minStock === null ? '' : String(inicial.inventory.minStock)
	);
	let eInvoicing = $state({ ...inicial.eInvoicing });

	/*
	 * Los dos idiomas de la compañía (T-810, T-811).
	 *
	 * No salen de `data.configuracion` como el resto: viven en columnas de
	 * `companies` y llegan con la sesión. La vista previa usa el del borrador, así
	 * que el documento se ve en el idioma elegido **antes** de guardar.
	 */
	// `untrack` por lo mismo que `inicial`: es el punto de partida del borrador.
	let locale = $state(untrack(() => data.user?.company_locale) ?? 'es');
	let documentLocale = $state(untrack(() => data.user?.document_locale) ?? 'es');

	let quitarLogo = $state(false);
	/** Vista previa del archivo recién elegido, antes de subirlo. */
	let logoElegido = $state<string | null>(null);

	const borrador: Settings = $derived({
		business,
		currency,
		// El impuesto no se configura (QA-05): es el IVA de ley.
		tax: { ...VAT },
		document,
		appearance: { accentColor: colorAcento },
		eInvoicing,
		inventory: {
			minStock: minimoGeneral.trim() === '' ? null : Number(minimoGeneral),
			lotsEnabled: inicial.inventory.lotsEnabled
		}
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
		`${currency.code}|${currency.symbol}|${currency.decimals}|${currency.thousandsSeparator}|${currency.decimalSeparator}|${currency.symbolAtEnd}|${currency.space}`
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
			/*
			 * Con la casilla marcada, la muestra sale como la vería el cliente: la
			 * venta tiene cliente, así que es factura (RN-85), y todavía no tiene
			 * clave, así que dice «pendiente de emisión» (RN-86). No se le inventa una
			 * clave de ejemplo: la vista previa prometería algo que hoy no pasa.
			 */
			document_type: borrador.eInvoicing.enabled ? INVOICE : null,
			items
		};
	});

	const codigosEjemplo = { 1: '7441000100015', 2: '7441000200014', 3: '7441000300013' };

	function seleccionarPlantilla(id: TemplateId) {
		document = { ...document, template: id };
	}

	// ---------------------------------- comprobantes que emite (RN-88)

	/** Enciende o apaga uno. La casilla solo se mueve si `canToggle` la deja. */
	function alternarComprobante(codigo: string, encendido: boolean) {
		const resto = eInvoicing.documentTypes.filter((c) => c !== codigo);
		eInvoicing = {
			...eInvoicing,
			documentTypes: ALL_TYPES.filter((c) => (c === codigo ? encendido : resto.includes(c)))
		};
	}

	/**
	 * Qué es cada uno o, si la casilla no se mueve, por qué. Una casilla apagada
	 * sin decir por qué es un misterio; con el motivo, es una respuesta.
	 */
	function detalleComprobante(codigo: string): string {
		if (ALWAYS_ON.includes(codigo)) return m.settings_doctype_always_on();
		// Solo el REP espera todavía su flujo: la venta a crédito (T-729).
		if (!AVAILABLE.includes(codigo)) return m.settings_doctype_pending_receipt();
		if (!canToggle(codigo, eInvoicing.documentTypes)) return m.settings_doctype_last_counter();
		if (codigo === EXPORT_INVOICE) return m.settings_doctype_export();
		if (codigo === DEBIT_NOTE) return m.settings_doctype_debit();
		if (codigo === PURCHASE_INVOICE) return m.settings_doctype_purchase();
		return codigo === TICKET ? m.settings_doctype_ticket() : m.settings_doctype_invoice();
	}

	// ------------------------------------------ factura electrónica (F6)

	/** Abierto el diálogo de RN-35, que es el único camino a producción. */
	let confirmando = $state(false);

	/**
	 * El ambiente dicho como palabra.
	 *
	 * Las claves son las mismas que usa `apiMessage` para los «no» del backend:
	 * dos juegos de rótulos para el mismo par de valores acabarían diciendo
	 * «pruebas» en un sitio y «sandbox» en el otro.
	 */
	function rotuloAmbiente(valor: string): string {
		return valor === 'production' ? m.api_environment_production() : m.api_environment_sandbox();
	}

	/** El color del vencimiento. Un certificado vencido no es un aviso, es un no. */
	function colorDelEstado(estado: string): string {
		switch (estado) {
			case 'expired':
				return 'text-[var(--negative)]';
			case 'expiring':
				return 'text-[var(--warning)]';
			default:
				return 'text-[var(--text)]';
		}
	}

	// ------------------------------------------ sucursales y cajas (T-608)

	/*
	 * Los dos tipos salen de `PageData` y no se importan de `+page.server.ts`:
	 * así no hay dos declaraciones de la misma forma que puedan separarse, y esta
	 * pantalla no nombra un módulo del servidor ni para los tipos.
	 */
	type Sucursal = NonNullable<PageData['oficinas']>['branches'][number];
	type Caja = NonNullable<PageData['oficinas']>['terminals'][number];

	/** `null` es el diálogo cerrado; una con `id: 0`, el alta. */
	let sucursalEditando = $state<Sucursal | null>(null);
	/** Lo mismo para una caja. Al crear, `branch_id` dice en cuál sucursal. */
	let cajaEditando = $state<Caja | null>(null);
	/**
	 * Lo que se va a borrar, con su tipo.
	 *
	 * Un solo diálogo para los dos: la pregunta es la misma y el aviso también
	 * —lo que arrastra historia no se borra, se desactiva—, así que dos modales
	 * serían dos sitios donde mantener el mismo texto.
	 */
	let borrando = $state<{ tipo: 'sucursal' | 'caja'; id: number; nombre: string } | null>(null);

	const cupo = $derived(data.oficinas?.quota);
	/** Cabe otra si el plan no limita (−1) o todavía no se llegó al techo. */
	const cabeSucursal = $derived(!cupo || cupo.max_branches < 0 || cupo.branches < cupo.max_branches);
	const cabeCaja = $derived(!cupo || cupo.max_terminals < 0 || cupo.terminals < cupo.max_terminals);

	function cajasDe(branchId: number): Caja[] {
		return data.oficinas?.terminals.filter((caja) => caja.branch_id === branchId) ?? [];
	}

	function nuevaSucursal(): Sucursal {
		return { id: 0, codigo: '', nombre: '', activa: true };
	}

	function nuevaCaja(branchId: number): Caja {
		return { id: 0, branch_id: branchId, codigo: '', nombre: '', activa: true };
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
		<!--
			En «Sucursales» no se ofrece: ahí no hay nada que pertenezca a este
			formulario —cada sucursal y cada caja se guardan en su propio diálogo—,
			y un botón que promete guardar lo que se está mirando y guarda otra cosa
			es peor que no tenerlo.
		-->
		{#if seccion !== 'sucursales'}
			<button type="submit" form="config-form" class="btn btn-primary" disabled={submitting}>
				{#if submitting}<Spinner size={15} />{m.common_saving()}{:else}
					<Icon name="check" size={15} />{m.common_save_changes()}
				{/if}
			</button>
		{/if}
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
			onclick={() => abrirSeccion(item.id)}
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

					<!--
						La identificación del emisor **se ve y no se edita** (RN-45, RF-37,
						T-621). Es la de `companies`: el certificado se emite a ella y va
						dentro de la clave de cada comprobante. La fija soporte.
					-->
					<div data-cedula-emisor>
						<span class="label">{m.settings_tax_id()}</span>
						{#if data.issuer?.identification}
							<p class="font-mono text-sm text-[var(--text)]">
								{identificationTypeName(data.issuer.identification_type) ?? ''}
								{data.issuer.identification}
							</p>
							<p class="mt-1 text-xs text-[var(--text-subtle)]">{m.settings_issuer_id_hint()}</p>
						{:else}
							<p class="text-sm text-[var(--warning)]">{m.settings_issuer_id_missing()}</p>
						{/if}
					</div>
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
						hint={m.settings_address_hint()}
						class="sm:col-span-2"
					/>

					<!--
						La ubicación del XML (T-722, RN-83): códigos de Hacienda y otras
						señas. No reemplaza a la dirección de arriba, que es la del tiquete.
					-->
					<fieldset class="sm:col-span-2" data-ubicacion-emisor>
						<legend class="mb-1 text-sm font-bold text-[var(--text)]">
							{m.settings_location_title()}
						</legend>
						<p class="mb-3 text-xs text-[var(--text-subtle)]">
							{eInvoicing.enabled ? m.settings_location_required() : m.settings_location_hint()}
						</p>
						<IssuerLocationFields
							bind:location={business.location}
							errors={form?.errors ?? {}}
							required={eInvoicing.enabled}
						/>
					</fieldset>

					<!--
						El idioma de la compañía (T-810, RN-28). Es el que recibe quien no
						eligió otro para su sesión; cada persona cambia el suyo desde el
						menú, sin tocar esto.
					-->
					<Select
						id="idioma-interfaz"
						name="idioma_interfaz"
						label={m.settings_locale()}
						hint={m.settings_locale_hint()}
						bind:value={locale}
					>
						<option value="es">{m.language_es()}</option>
						<option value="en">{m.language_en()}</option>
						<option value="pt">{m.language_pt()}</option>
					</Select>
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
					<Select
						id="moneda-preset"
						name="moneda_preset"
						label={m.settings_currency()}
						class="sm:col-span-2"
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
					</Select>

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

				<!--
					El impuesto ya no se escribe acá (QA-05): lo da el CABYS de cada
					producto y, sin él, el 13 % de ley. Queda dicho, para que nadie
					lo busque.
				-->
				<h2 class="mt-6 mb-1 text-sm font-bold text-[var(--text)]">{m.settings_tax()}</h2>
				<p class="text-xs text-[var(--text-subtle)]" data-impuesto-de-ley>
					{m.settings_tax_hint()}
				</p>
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
							tax: VAT.name,
							taxAmount: formatMoney(round2(10000 * borrador.tax.rate))
						})}
					</p>
				{/key}
			</div>
		</div>
	</div>

	<!-- --------------------------------------------------------- documentos -->
	<!-- ----------------------------------------------------- inventario -->
	<div style:display={seccion === 'inventario' ? '' : 'none'}>
		<div class="card p-5 lg:max-w-2xl">
			<h2 class="mb-1 text-sm font-bold text-[var(--text)]">{m.settings_inventory()}</h2>
			<p class="mb-4 text-xs text-[var(--text-subtle)]">{m.settings_inventory_hint()}</p>
			<div class="grid gap-4 sm:grid-cols-2">
				<Field
					label={m.settings_min_stock()}
					name="inventario_minimo"
					type="number"
					min="0"
					max="1000000"
					bind:value={minimoGeneral}
					error={form?.errors?.inventario_minimo}
					hint={m.settings_min_stock_hint()}
				/>
			</div>
		</div>
	</div>

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
						<!--
							El idioma del documento, que **no** es el de la pantalla (RN-29,
							T-811). La factura es para el cliente y para Hacienda: una
							compañía costarricense la emite en español aunque su cajero use
							el POS en portugués. Va acá, en la pestaña del documento, porque
							es del documento.
						-->
						<div>
							<Select
								id="idioma-documento"
								name="idioma_documento"
								label={m.settings_document_locale()}
								hint={m.settings_document_locale_hint()}
								bind:value={documentLocale}
							>
								<option value="es">{m.language_es()}</option>
								<option value="en">{m.language_en()}</option>
								<option value="pt">{m.language_pt()}</option>
							</Select>
						</div>

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
							docLocale={documentLocale}
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

				<!--
					Los comprobantes que emite este negocio (RN-88). Los siete se ven; el
					que no se puede mover dice por qué. Una casilla apagada no se envía,
					así que la que está encendida y bloqueada viaja además en un campo
					oculto: si no, guardar la pantalla apagaría la NC o la ND sin que
					nadie lo pidiera.
				-->
				<fieldset class="mb-5" data-comprobantes>
					<legend class="label">{m.settings_document_types()}</legend>
					<p class="mb-2 text-xs text-[var(--text-subtle)]">{m.settings_document_types_hint()}</p>
					<div class="grid gap-2 sm:grid-cols-2">
						{#each ALL_TYPES as codigo (codigo)}
							{@const encendido = eInvoicing.documentTypes.includes(codigo)}
							{@const movible = canToggle(codigo, eInvoicing.documentTypes)}
							<label
								class="flex items-start gap-2 rounded-lg border p-2.5 text-sm {encendido
									? 'border-[var(--accent)]'
									: 'border-[var(--border)]'} {movible ? 'cursor-pointer' : 'cursor-not-allowed'}"
								data-comprobante={codigo}
							>
								<input
									type="checkbox"
									name="electronica_comprobantes"
									value={codigo}
									checked={encendido}
									disabled={!movible}
									onchange={(e) => alternarComprobante(codigo, e.currentTarget.checked)}
									class="mt-1"
								/>
								{#if encendido && !movible}
									<input type="hidden" name="electronica_comprobantes" value={codigo} />
								{/if}
								<span class="min-w-0">
									<span class="font-semibold {movible || encendido ? 'text-[var(--text)]' : 'text-[var(--text-muted)]'}">
										{documentTypeLabel(codigo)}
									</span>
									<span class="block text-xs text-[var(--text-subtle)]">
										{detalleComprobante(codigo)}
									</span>
								</span>
							</label>
						{/each}
					</div>
				</fieldset>

				<!--
					El ambiente **ya no se elige acá** (T-611). Vivía en este formulario
					como un desplegable más, y eso es justo lo que RN-35 prohíbe: pasar a
					producción es el momento en que los documentos dejan de ser un ensayo,
					y no puede ocurrir por haber tocado un desplegable sin querer. Se
					cambia abajo, con confirmación y bitácora, contra `PUT /fe/active` —y
					el backend lo conserva aunque llegue por este formulario—.
				-->
				<div class="grid gap-4 sm:grid-cols-2">
					<Field
						label={m.settings_economic_activity()}
						name="electronica_actividad"
						bind:value={eInvoicing.economicActivity}
						error={form?.errors?.electronica_actividad}
						hint={m.settings_economic_activity_hint()}
					/>
					<!--
						La sucursal y la terminal se **muestran**, no se escriben (T-614).
						Las fija la sesión desde el token y cada venta ya guarda la suya. El
						campo editable era una copia por compañía de algo que es por sesión,
						y rota por construcción: hay **una sola fila de configuración por
						compañía**, así que dos cajas del mismo negocio declaraban la misma
						terminal — y dos terminales con el mismo código producen
						consecutivos repetidos, que Hacienda rechaza.

						El usuario de ATV tampoco está: es por ambiente, no por compañía, y
						vive con su contraseña en `fe_credentials` (F6).
					-->
					<div class="sm:col-span-2">
						<span class="label">{m.settings_branch_terminal()}</span>
						<p class="font-mono text-sm text-[var(--text)]">
							{data.branchCode || '—'} · {data.terminalCode || '—'}
						</p>
						<p class="mt-1 text-xs text-[var(--text-subtle)]">
							{m.settings_branch_terminal_hint()}
						</p>
					</div>
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

<!--
	--------------------------------------- credenciales de Hacienda (F6)

	Va **fuera** del formulario grande, y no por maquetado: cada botón de acá
	habla con un endpoint propio que hace algo irreversible o auditado —importar
	una llave a Vault, borrarla, salir a internet, dejar una línea de bitácora—.
	Dentro del «Guardar cambios» de la pantalla, corregir una coma en la
	dirección del negocio dispararía las cuatro.
-->
{#if seccion === 'electronica'}
	<div class="mt-4 space-y-4">
		{#if !data.fe}
			<!-- `apiSafe` en el `load`: la pestaña lo dice en vez de tumbar las otras tres. -->
			<p
				class="flex items-center gap-2 rounded-lg border border-[var(--warning)] bg-[var(--warning-bg)] p-3 text-sm text-[var(--warning)]"
			>
				<Icon name="alert" size={16} />
				{m.settings_fe_unavailable()}
			</p>
		{:else}
			<!-- ------------------------------------------------ ambiente activo -->
			<div class="card flex flex-wrap items-center justify-between gap-3 p-5">
				<div class="flex items-center gap-3">
					<Icon name="bolt" size={18} class="text-[var(--accent)]" />
					<div>
						<p class="text-sm font-bold text-[var(--text)]">
							{m.settings_fe_active_environment({ environment: rotuloAmbiente(data.fe.active) })}
						</p>
						<p class="text-xs text-[var(--text-subtle)]">
							{data.fe.active === 'production'
								? m.settings_fe_active_production_hint()
								: m.settings_fe_active_sandbox_hint()}
						</p>
					</div>
				</div>
				{#if data.fe.active === 'production'}
					<form method="POST" action="?/feAmbiente" use:enhance={submit()}>
						<input type="hidden" name="ambiente" value="sandbox" />
						<button type="submit" class="btn btn-ghost">
							<Icon name="back" size={15} />
							{m.settings_fe_back_to_sandbox()}
						</button>
					</form>
				{:else}
					<button type="button" class="btn btn-primary" onclick={() => (confirmando = true)}>
						{m.settings_fe_go_to_production()}
					</button>
				{/if}
			</div>
			{#if data.fe.production_gate && data.fe.active !== 'production'}
				<!-- T-713, RN-46: la puerta dura de la certificación, con lo que falta. -->
				<p
					class="flex gap-2 rounded-lg border p-3 text-xs {data.fe.production_gate.ready
						? 'border-[var(--positive)] bg-[var(--positive-bg)] text-[var(--positive)]'
						: 'border-[var(--border)] bg-[var(--surface-sunken)] text-[var(--text-muted)]'}"
					data-puerta-produccion={data.fe.production_gate.ready ? 'abierta' : 'cerrada'}
				>
					<Icon name={data.fe.production_gate.ready ? 'check' : 'info'} size={15} class="mt-px shrink-0" />
					<span>
						{data.fe.production_gate.ready
							? m.settings_production_gate_ready()
							: m.settings_production_gate_missing({
									missing: data.fe.production_gate.missing
										.map((t) => documentTypeLabel(t) ?? t)
										.join(', ')
								})}
					</span>
				</p>
			{/if}

			<!-- ------------------------------------------ una tarjeta por ambiente -->
			<div class="grid gap-4 lg:grid-cols-2">
				{#each data.fe.environments as amb (amb.environment)}
					<div
						class="card space-y-5 p-5 {amb.environment === data.fe.active
							? 'border-[var(--accent)]'
							: ''}"
						data-ambiente={amb.environment}
					>
						<div class="flex items-start justify-between gap-3">
							<div>
								<h3 class="text-sm font-bold text-[var(--text)]">
									{rotuloAmbiente(amb.environment)}
								</h3>
								<p class="text-xs text-[var(--text-subtle)]">
									{amb.environment === data.fe.active
										? m.settings_fe_in_use()
										: m.settings_fe_not_in_use()}
								</p>
							</div>
							<span
								class="rounded-full px-2.5 py-1 text-xs font-semibold {amb.ready
									? 'bg-[var(--positive-bg)] text-[var(--positive)]'
									: 'bg-[var(--surface-sunken)] text-[var(--text-subtle)]'}"
							>
								{amb.ready ? m.settings_fe_ready() : m.settings_fe_not_ready()}
							</span>
						</div>

						<!-- ......................................... el certificado -->
						<section class="space-y-3">
							<h4 class="flex items-center gap-2 text-xs font-bold text-[var(--text-muted)]">
								<Icon name="lock" size={14} />
								{m.settings_fe_certificate()}
							</h4>

							{#if amb.certificate_configured}
								<dl class="space-y-1 text-xs">
									<div class="flex justify-between gap-2">
										<dt class="text-[var(--text-subtle)]">{m.settings_fe_holder()}</dt>
										<dd class="text-right font-semibold text-[var(--text)]">
											{amb.certificate_name}
										</dd>
									</div>
									<div class="flex justify-between gap-2">
										<dt class="text-[var(--text-subtle)]">{m.settings_fe_expires()}</dt>
										<dd class="text-right font-semibold {colorDelEstado(amb.certificate_status)}">
											{amb.expires_at ? formatDateTime(amb.expires_at) : '—'}
										</dd>
									</div>
								</dl>

								{#if amb.certificate_status !== 'valid'}
									<p
										class="flex items-start gap-2 rounded-lg border p-2.5 text-xs {amb.certificate_status ===
										'expired'
											? 'border-[var(--negative)] bg-[var(--negative-bg)] text-[var(--negative)]'
											: 'border-[var(--warning)] bg-[var(--warning-bg)] text-[var(--warning)]'}"
									>
										<Icon name="alert" size={14} class="mt-px shrink-0" />
										{amb.certificate_status === 'expired'
											? m.settings_fe_certificate_expired()
											: m.settings_fe_certificate_expiring({ days: amb.days_left ?? 0 })}
									</p>
								{/if}
							{:else}
								<p class="text-xs text-[var(--text-subtle)]">{m.settings_fe_no_certificate()}</p>
							{/if}

							<!--
								El mismo formulario sube y reemplaza: `import_version` de Vault
								deja la llave nueva en uso sin una ventana en la que la compañía
								no pueda firmar, así que no hacen falta dos caminos.
							-->
							<!--
								`reset: true` y no por pulcritud: el PIN se queda escrito en el
								campo después de enviarlo, y ahí sigue mientras la pestaña esté
								abierta. El servidor no lo devuelve nunca —no lo tiene—, pero
								dejarlo en el DOM sería guardar en la pantalla justo lo que el
								sistema entero se ocupa de no guardar en ningún lado.
							-->
							<form
								method="POST"
								action="?/feCertificado"
								enctype="multipart/form-data"
								use:enhance={submit({ reset: true })}
								class="space-y-2"
							>
								<input type="hidden" name="ambiente" value={amb.environment} />
								<div>
									<label class="label" for="p12-{amb.environment}">
										{amb.certificate_configured
											? m.settings_fe_replace_certificate()
											: m.settings_fe_upload_certificate()}
									</label>
									<input
										id="p12-{amb.environment}"
										type="file"
										name="certificado"
										accept=".p12,.pfx,application/x-pkcs12"
										class="input"
									/>
									{#if form?.errors?.certificado}
										<p class="mt-1 text-xs text-[var(--negative)]">{form.errors.certificado}</p>
									{/if}
								</div>
								<Field
									label={m.settings_fe_pin()}
									name="pin"
									type="password"
									error={form?.errors?.pin}
									hint={m.settings_fe_pin_hint()}
								/>
								<div class="flex flex-wrap gap-2">
									<button type="submit" class="btn btn-primary">
										<Icon name="check" size={15} />
										{m.settings_fe_send_certificate()}
									</button>
									{#if amb.certificate_configured}
										<button
											type="submit"
											formaction="?/feQuitarCertificado"
											class="btn btn-ghost text-[var(--negative)]"
										>
											<Icon name="trash" size={14} />
											{m.settings_fe_remove()}
										</button>
									{/if}
								</div>
							</form>
						</section>

						<!-- ................................. las credenciales de ATV -->
						<section class="space-y-3 border-t border-[var(--border)] pt-4">
							<h4 class="flex items-center gap-2 text-xs font-bold text-[var(--text-muted)]">
								<Icon name="clock" size={14} />
								{m.settings_fe_atv()}
							</h4>

							<p class="text-xs text-[var(--text-subtle)]">
								{#if !amb.atv_configured}
									{m.settings_fe_atv_missing()}
								{:else if amb.atv_verified_at}
									{m.settings_fe_atv_verified({ date: formatDateTime(amb.atv_verified_at) })}
								{:else}
									{m.settings_fe_atv_unverified()}
								{/if}
							</p>

							<!--
								`reset: true` por lo mismo que el PIN: la contraseña no puede
								quedarse escrita en el campo después de guardarla. El `reset`
								nativo devuelve cada campo a su atributo `value`, así que el
								usuario vuelve a mostrarse y la contraseña —que no tiene— queda
								vacía. Es exactamente lo que hace falta.
							-->
							<form
								method="POST"
								action="?/feAtv"
								use:enhance={submit({ reset: true })}
								class="space-y-2"
							>
								<input type="hidden" name="ambiente" value={amb.environment} />
								<!--
									El usuario se muestra y la contraseña no (RN-16). El usuario es
									un identificador: sin verlo, nadie puede comprobar que escribió
									el que era.
								-->
								<Field
									label={m.settings_fe_atv_user()}
									name="atv_usuario"
									value={amb.atv_user ?? ''}
									error={form?.errors?.atv_usuario}
								/>
								<Field
									label={m.settings_fe_atv_password()}
									name="atv_clave"
									type="password"
									error={form?.errors?.atv_clave}
									hint={m.settings_fe_atv_password_hint()}
								/>
								<button type="submit" class="btn btn-primary">
									<Icon name="check" size={15} />
									{m.settings_fe_save_atv()}
								</button>
							</form>

							<form method="POST" action="?/feProbar" use:enhance={submit()}>
								<input type="hidden" name="ambiente" value={amb.environment} />
								<button type="submit" class="btn btn-ghost w-full" disabled={!amb.atv_configured}>
									<Icon name="refresh" size={14} />
									{m.settings_fe_test_connection()}
								</button>
								<p class="mt-1 text-xs text-[var(--text-subtle)]">
									{m.settings_fe_test_connection_hint()}
								</p>
							</form>
						</section>
					</div>
				{/each}
			</div>
		{/if}

		<!--
			La numeración que viene de otro sistema (T-616, RF-32, RN-36 a RN-38).
			Una fila por caja y por comprobante encendido, en el ambiente en uso. La
			que ya emitió con este sistema se muestra sin campo: desde ahí el
			contador es del sistema. Que solo suba lo decide el servidor.
		-->
		{#if data.series}
			<section class="card mt-4 p-5" data-series>
				<h3 class="text-sm font-bold text-[var(--text)]">{m.settings_fe_sequences_title()}</h3>
				<p class="mt-1 mb-4 text-xs text-[var(--text-subtle)]">
					{m.settings_fe_sequences_hint({ environment: rotuloAmbiente(data.series.environment) })}
				</p>
				{#if data.series.items.length === 0}
					<p class="text-sm text-[var(--text-muted)]">{m.settings_fe_sequences_empty()}</p>
				{:else}
					<div class="overflow-x-auto">
						<table class="data-table">
							<thead>
								<tr>
									<th>{m.settings_fe_sequence_terminal()}</th>
									<th>{m.settings_fe_sequence_document()}</th>
									<th>{m.settings_fe_sequence_last()}</th>
								</tr>
							</thead>
							<tbody>
								{#each data.series.items as serie (`${serie.terminal_id}-${serie.document_type}`)}
									{@const caja = `${serie.branch_code}-${serie.terminal_code}`}
									<tr data-serie={serie.document_type}>
										<td class="whitespace-nowrap">
											<span class="font-mono text-xs">{caja}</span>
											<span class="text-[var(--text-muted)]">{serie.terminal_name}</span>
										</td>
										<td>{documentTypeLabel(serie.document_type) ?? serie.document_type}</td>
										<td>
											{#if serie.in_use}
												<span class="tabular-nums">{serie.last_number}</span>
												<span class="ml-2 text-xs text-[var(--text-subtle)]" data-serie-usada>
													{m.settings_fe_sequence_in_use()}
												</span>
											{:else}
												<form
													method="POST"
													action="?/feSerie"
													class="flex items-center gap-2"
													use:enhance={submit()}
												>
													<input type="hidden" name="terminal_id" value={serie.terminal_id} />
													<input type="hidden" name="document_type" value={serie.document_type} />
													<!--
														`defaultValue` y no `value`: con `value`, Svelte lo reinicia al
														hidratar y se come lo que se escribió antes —se guardaba el número
														de siempre y aparecía «Numeración guardada» igual—.
													-->
													<input
														name="last_number"
														class="input w-36 py-1 text-right tabular-nums"
														inputmode="numeric"
														defaultValue={String(serie.last_number)}
														aria-label={m.settings_fe_sequence_label({
															document: documentTypeLabel(serie.document_type) ?? serie.document_type,
															terminal: caja
														})}
													/>
													<button type="submit" class="btn btn-primary px-3 py-1 text-xs">
														<Icon name="check" size={13} />
														{m.settings_fe_sequence_save()}
													</button>
												</form>
											{/if}
										</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				{/if}
			</section>
		{/if}
	</div>
{/if}

<!--
	------------------------------------------ sucursales y cajas (T-608)

	Fuera del formulario grande por lo mismo que las credenciales: cada alta, cada
	cambio y cada borrado habla con su propio endpoint. Y la pestaña se monta con
	`{#if}` en vez de esconderse con `display` como las cuatro de arriba, porque
	acá no hay ningún campo que tenga que viajar en el envío de ese formulario.
-->
{#if seccion === 'sucursales'}
	<div class="space-y-4">
		{#if !data.oficinas || !cupo}
			<!-- `apiSafe` en el `load`: la pestaña lo dice en vez de tumbar las otras. -->
			<p
				class="flex items-center gap-2 rounded-lg border border-[var(--warning)] bg-[var(--warning-bg)] p-3 text-sm text-[var(--warning)]"
			>
				<Icon name="alert" size={16} />
				{m.settings_offices_unavailable()}
			</p>
		{:else}
			<!-- ------------------------------------------------ el cupo del plan -->
			<div class="card flex flex-wrap items-start justify-between gap-3 p-5">
				<div>
					<h2 class="mb-1 text-sm font-bold text-[var(--text)]">{m.settings_offices_title()}</h2>
					<p class="max-w-prose text-xs text-[var(--text-subtle)]">{m.settings_offices_hint()}</p>
					<!--
						El cupo se dice **antes** de abrir el formulario, no al chocar con
						él: enterarse del techo después de llenarlo es el mismo error de
						diseño que un botón que promete algo que no pasa.
					-->
					<div class="mt-3 flex flex-wrap items-center gap-2">
						<span class="badge bg-[var(--surface-sunken)] text-[var(--text-muted)]">
							<Icon name="home" size={11} />
							{cupo.max_branches < 0
								? m.settings_offices_quota_branches_free({ current: cupo.branches })
								: m.settings_offices_quota_branches({
										current: cupo.branches,
										max: cupo.max_branches
									})}
						</span>
						<span class="badge bg-[var(--surface-sunken)] text-[var(--text-muted)]">
							<Icon name="wallet" size={11} />
							{cupo.max_terminals < 0
								? m.settings_offices_quota_terminals_free({ current: cupo.terminals })
								: m.settings_offices_quota_terminals({
										current: cupo.terminals,
										max: cupo.max_terminals
									})}
						</span>
						<span class="text-xs text-[var(--text-subtle)]">{m.settings_offices_quota_hint()}</span>
					</div>
				</div>
				<div class="text-right">
					<button
						type="button"
						class="btn btn-primary"
						disabled={!cabeSucursal}
						onclick={() => (sucursalEditando = nuevaSucursal())}
					>
						<Icon name="plus" size={15} />
						{m.settings_offices_new_branch()}
					</button>
					{#if !cabeSucursal}
						<p class="mt-1 text-xs text-[var(--text-subtle)]">{m.settings_offices_branch_full()}</p>
					{/if}
				</div>
			</div>

			<!-- ------------------------------------- una tarjeta por sucursal -->
			{#each data.oficinas.branches as sucursal (sucursal.id)}
				<div class="card p-5" class:opacity-60={!sucursal.activa} data-sucursal={sucursal.codigo}>
					<div class="flex flex-wrap items-start justify-between gap-3">
						<div class="flex items-start gap-3">
							<span class="font-mono text-lg font-bold text-[var(--accent)]">{sucursal.codigo}</span>
							<div>
								<p class="text-sm font-bold text-[var(--text)]">{sucursal.nombre}</p>
								{#if sucursal.activa}
									<span class="badge bg-[var(--positive-bg)] text-[var(--positive)]">
										<Icon name="check" size={11} />
										{m.settings_offices_active()}
									</span>
								{:else}
									<span class="badge bg-[var(--surface-sunken)] text-[var(--text-muted)]">
										<Icon name="close" size={11} />
										{m.settings_offices_inactive()}
									</span>
								{/if}
							</div>
						</div>
						<div class="flex items-center gap-1">
							<button
								type="button"
								class="rounded-lg p-1.5 text-[var(--text-subtle)] hover:bg-[var(--surface-sunken)] hover:text-[var(--accent)]"
								onclick={() => (sucursalEditando = { ...sucursal })}
								aria-label={m.settings_offices_edit_branch_action({ name: sucursal.nombre })}
							>
								<Icon name="edit" size={15} />
							</button>
							<button
								type="button"
								class="rounded-lg p-1.5 text-[var(--text-subtle)] hover:bg-[var(--surface-sunken)] hover:text-[var(--negative)]"
								onclick={() =>
									(borrando = { tipo: 'sucursal', id: sucursal.id, nombre: sucursal.nombre })}
								aria-label={m.settings_offices_delete_branch_action({ name: sucursal.nombre })}
							>
								<Icon name="trash" size={15} />
							</button>
						</div>
					</div>

					<!-- ................................................ sus cajas -->
					<ul class="mt-4 space-y-1 border-t border-[var(--border)] pt-3">
						{#each cajasDe(sucursal.id) as caja (caja.id)}
							<li
								class="flex flex-wrap items-center gap-3 rounded-lg px-2 py-1.5 hover:bg-[var(--surface-sunken)]"
								data-caja={caja.codigo}
							>
								<Icon name="wallet" size={14} class="text-[var(--text-subtle)]" />
								<span class="font-mono text-xs text-[var(--text-muted)]">{caja.codigo}</span>
								<span class="text-sm text-[var(--text)]">{caja.nombre}</span>
								{#if !caja.activa}
									<span class="badge bg-[var(--surface-sunken)] text-[var(--text-muted)]">
										{m.settings_offices_inactive()}
									</span>
								{/if}
								<span class="ml-auto flex items-center gap-1">
									<button
										type="button"
										class="rounded-lg p-1.5 text-[var(--text-subtle)] hover:text-[var(--accent)]"
										onclick={() => (cajaEditando = { ...caja })}
										aria-label={m.settings_offices_edit_terminal_action({ name: caja.nombre })}
									>
										<Icon name="edit" size={14} />
									</button>
									<button
										type="button"
										class="rounded-lg p-1.5 text-[var(--text-subtle)] hover:text-[var(--negative)]"
										onclick={() => (borrando = { tipo: 'caja', id: caja.id, nombre: caja.nombre })}
										aria-label={m.settings_offices_delete_terminal_action({ name: caja.nombre })}
									>
										<Icon name="trash" size={14} />
									</button>
								</span>
							</li>
						{:else}
							<li class="px-2 py-1.5 text-xs text-[var(--text-subtle)]">
								{m.settings_offices_no_terminals()}
							</li>
						{/each}
					</ul>

					<button
						type="button"
						class="btn btn-ghost mt-2"
						disabled={!cabeCaja}
						onclick={() => (cajaEditando = nuevaCaja(sucursal.id))}
					>
						<Icon name="plus" size={14} />
						{m.settings_offices_add_terminal()}
					</button>
					{#if !cabeCaja}
						<p class="mt-1 text-xs text-[var(--text-subtle)]">{m.settings_offices_terminal_full()}</p>
					{/if}
				</div>
			{/each}
		{/if}
	</div>
{/if}

<!-- ------------------------------------------------ la ficha de la sucursal -->
<Modal
	open={sucursalEditando !== null}
	title={sucursalEditando?.id
		? m.settings_offices_edit_branch()
		: m.settings_offices_branch_form_new()}
	size="sm"
	onclose={() => (sucursalEditando = null)}
>
	{#if sucursalEditando}
		<form
			id="form-sucursal"
			method="POST"
			action="?/sucursalGuardar"
			use:enhance={submit({ onSuccess: () => (sucursalEditando = null) })}
			class="space-y-4"
		>
			<input type="hidden" name="id" value={sucursalEditando.id || ''} />

			{#if sucursalEditando.id}
				<!--
					El código **se muestra y no se edita**: no está en el esquema de
					actualización del backend, y cambiarlo movería el número de todos los
					comprobantes ya emitidos desde esta sucursal.
				-->
				<div>
					<span class="label">{m.settings_offices_label_branch_code()}</span>
					<p class="font-mono text-sm text-[var(--text)]">{sucursalEditando.codigo}</p>
					<p class="mt-1 text-xs text-[var(--text-subtle)]">{m.settings_offices_code_locked()}</p>
				</div>
			{:else}
				<Field
					label={m.settings_offices_label_branch_code()}
					name="codigo"
					bind:value={sucursalEditando.codigo}
					inputmode="numeric"
					hint={m.settings_offices_branch_code_hint()}
					error={form?.errors?.codigo}
					required
				/>
			{/if}

			<Field
				label={m.settings_offices_label_name()}
				name="nombre"
				bind:value={sucursalEditando.nombre}
				error={form?.errors?.nombre}
				required
			/>

			{#if sucursalEditando.id}
				<!-- Solo al editar: una nueva nace activa, y una casilla desmarcable
				     en el alta solo sirve para dar de alta algo apagado. -->
				<div>
					<label class="flex cursor-pointer items-center gap-2 text-sm text-[var(--text)]">
						<input
							type="checkbox"
							name="activa"
							class="h-4 w-4 accent-[var(--accent)]"
							checked={sucursalEditando.activa}
						/>
						{m.settings_offices_label_active()}
					</label>
					<p class="mt-1 text-xs text-[var(--text-subtle)]">
						{m.settings_offices_branch_active_hint()}
					</p>
				</div>
			{/if}
		</form>
	{/if}

	{#snippet footer()}
		<button type="button" class="btn btn-ghost" onclick={() => (sucursalEditando = null)}>
			{m.common_cancel()}
		</button>
		<button type="submit" form="form-sucursal" class="btn btn-primary">
			<Icon name="check" size={15} />
			{m.common_save()}
		</button>
	{/snippet}
</Modal>

<!-- ----------------------------------------------------- la ficha de la caja -->
<Modal
	open={cajaEditando !== null}
	title={cajaEditando?.id
		? m.settings_offices_edit_terminal()
		: m.settings_offices_terminal_form_new({
				branch:
					data.oficinas?.branches.find((s) => s.id === cajaEditando?.branch_id)?.nombre ?? ''
			})}
	size="sm"
	onclose={() => (cajaEditando = null)}
>
	{#if cajaEditando}
		<form
			id="form-caja"
			method="POST"
			action="?/cajaGuardar"
			use:enhance={submit({ onSuccess: () => (cajaEditando = null) })}
			class="space-y-4"
		>
			<input type="hidden" name="id" value={cajaEditando.id || ''} />
			<input type="hidden" name="branch_id" value={cajaEditando.branch_id} />

			{#if cajaEditando.id}
				<div>
					<span class="label">{m.settings_offices_label_terminal_code()}</span>
					<p class="font-mono text-sm text-[var(--text)]">{cajaEditando.codigo}</p>
					<p class="mt-1 text-xs text-[var(--text-subtle)]">{m.settings_offices_code_locked()}</p>
				</div>
			{:else}
				<Field
					label={m.settings_offices_label_terminal_code()}
					name="codigo"
					bind:value={cajaEditando.codigo}
					inputmode="numeric"
					hint={m.settings_offices_terminal_code_hint()}
					error={form?.errors?.codigo}
					required
				/>
			{/if}

			<Field
				label={m.settings_offices_label_name()}
				name="nombre"
				bind:value={cajaEditando.nombre}
				error={form?.errors?.nombre}
				required
			/>

			{#if cajaEditando.id}
				<div>
					<label class="flex cursor-pointer items-center gap-2 text-sm text-[var(--text)]">
						<input
							type="checkbox"
							name="activa"
							class="h-4 w-4 accent-[var(--accent)]"
							checked={cajaEditando.activa}
						/>
						{m.settings_offices_label_active()}
					</label>
					<p class="mt-1 text-xs text-[var(--text-subtle)]">
						{m.settings_offices_terminal_active_hint()}
					</p>
				</div>
			{/if}
		</form>
	{/if}

	{#snippet footer()}
		<button type="button" class="btn btn-ghost" onclick={() => (cajaEditando = null)}>
			{m.common_cancel()}
		</button>
		<button type="submit" form="form-caja" class="btn btn-primary">
			<Icon name="check" size={15} />
			{m.common_save()}
		</button>
	{/snippet}
</Modal>

<!--
	El borrado, uno solo para los dos: la pregunta es la misma y el aviso también
	—lo que arrastra historia no se borra, se desactiva—, así que dos diálogos
	serían dos sitios donde mantener el mismo texto.

	Y es una cortesía, no el control: quien tenga ventas recibe `branch_in_use`
	del backend aunque confirme.
-->
<Modal
	open={borrando !== null}
	title={borrando?.tipo === 'caja'
		? m.settings_offices_delete_terminal_title()
		: m.settings_offices_delete_branch_title()}
	description={borrando?.nombre}
	size="sm"
	onclose={() => (borrando = null)}
>
	<p class="text-sm text-[var(--text-muted)]">{m.settings_offices_delete_warning()}</p>

	{#snippet footer()}
		<button type="button" class="btn btn-ghost" onclick={() => (borrando = null)}>
			{m.common_cancel()}
		</button>
		{#if borrando}
			<form
				method="POST"
				action={borrando.tipo === 'caja' ? '?/cajaBorrar' : '?/sucursalBorrar'}
				use:enhance={submit({ onSuccess: () => (borrando = null) })}
			>
				<input type="hidden" name="id" value={borrando.id} />
				<button type="submit" class="btn btn-primary bg-[var(--negative)]">
					<Icon name="trash" size={15} />
					{m.settings_offices_delete_confirm()}
				</button>
			</form>
		{/if}
	{/snippet}
</Modal>

<!--
	La confirmación de RN-35, que también viaja al servidor: sin `confirmar`, el
	backend responde `confirmation_required`. El modal es la cortesía; la puerta
	está del otro lado.
-->
<Modal
	open={confirmando}
	title={m.settings_fe_confirm_title()}
	description={m.settings_fe_confirm_description()}
	size="sm"
	onclose={() => (confirmando = false)}
>
	<div class="space-y-3 text-sm text-[var(--text-muted)]">
		<p>{m.settings_fe_confirm_effect()}</p>
		<!--
			RN-46: se **avisa** de lo que Hacienda exige y no se impide. La puerta
			dura es T-713, en F7, que es cuando existen comprobantes que contar.
		-->
		<div
			class="flex gap-2 rounded-lg border border-[var(--warning)] bg-[var(--warning-bg)] p-3 text-xs text-[var(--warning)]"
		>
			<Icon name="info" size={14} class="mt-px shrink-0" />
			<div class="space-y-1">
				<p class="font-semibold">{m.settings_fe_confirm_certification_title()}</p>
				<p>{m.settings_fe_confirm_certification()}</p>
			</div>
		</div>
	</div>
	{#snippet footer()}
		<button type="button" class="btn btn-ghost" onclick={() => (confirmando = false)}>
			{m.common_cancel()}
		</button>
		<form
			method="POST"
			action="?/feAmbiente"
			use:enhance={submit({ onSuccess: () => (confirmando = false) })}
		>
			<input type="hidden" name="ambiente" value="production" />
			<input type="hidden" name="confirmar" value="true" />
			<button type="submit" class="btn btn-primary">
				{m.settings_fe_confirm_go()}
			</button>
		</form>
	{/snippet}
</Modal>
