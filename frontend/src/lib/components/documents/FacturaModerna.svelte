<script lang="ts">
	/**
	 * Factura moderna, página completa.
	 *
	 * Misma información que la clásica, con más presencia de marca: encabezado en
	 * diagonal, tabla con cabecera de color, filas alternas y una barra de
	 * contacto al pie. Está pensada para el negocio que manda la factura por
	 * correo y quiere que se le reconozca.
	 *
	 * Las diagonales son `clip-path` sobre bloques de color, no imágenes: la
	 * factura se arma con el color que el dueño eligió y ninguna imagen puede
	 * seguirlo. También significa que no hay nada que descargar al imprimir.
	 */
	import { formatMoney, taxLabel } from '$lib/money';
	import { formatDate, formatDateTime, fullName } from '$lib/format';
	import {
		brandTones,
		documentTitle,
		issuerLines,
		returnedTotal,
		type DocumentProps
	} from '$lib/documents';

	let { sale, client, returns, settings, logoUrl, barcodes = {} }: DocumentProps = $props();

	const doc = $derived(settings.documento);
	const marca = $derived(brandTones(doc.color));
	const emisor = $derived(issuerLines(settings));
	const devuelto = $derived(returnedTotal(returns));

	const contacto = $derived(
		[settings.negocio.telefono, settings.negocio.correo, settings.negocio.sitio_web].filter(Boolean)
	);
</script>

<svelte:head>
	{@html `<style>@media print { @page { size: auto; margin: 10mm; } }</style>`}
</svelte:head>

<article
	class="print-sheet mx-auto w-full max-w-3xl overflow-hidden rounded-xl border border-[var(--border)] shadow-sm"
	style="background:#ffffff; color:#0f172a; font-variant-numeric: tabular-nums"
>
	<!-- Encabezado en diagonal -->
	<header class="relative isolate" style="background:#f1f5f9">
		<div
			class="ink-exact absolute inset-y-0 left-0 -z-10 w-[68%]"
			style="background:{marca.base}; clip-path: polygon(0 0, 100% 0, 86% 100%, 0 100%)"
		></div>

		<div class="flex items-start justify-between gap-4 px-8 py-7">
			<div class="min-w-0" style="color:{marca.ink}">
				<h1 class="text-2xl font-bold tracking-[0.2em] uppercase">
					{documentTitle(settings)}
				</h1>
				<dl class="mt-3 space-y-1 text-xs">
					<div class="flex gap-2">
						<dt class="w-24 shrink-0 font-semibold">N.º</dt>
						<dd class="font-mono">{sale.sale_number}</dd>
					</div>
					<div class="flex gap-2">
						<dt class="w-24 shrink-0 font-semibold">Fecha</dt>
						<dd>{formatDate(sale.created_at)}</dd>
					</div>
					<div class="flex gap-2">
						<dt class="w-24 shrink-0 font-semibold">Pago</dt>
						<dd>{sale.payment_method}</dd>
					</div>
				</dl>
			</div>

			<div class="max-w-[38%] shrink-0 pt-1 text-right">
				{#if doc.mostrar_logo && logoUrl}
					<img src={logoUrl} alt="" class="ml-auto max-h-12 w-auto object-contain" />
				{/if}
				<p class="mt-1.5 text-sm leading-tight font-bold">{settings.negocio.nombre}</p>
				{#if settings.negocio.identificacion}
					<p class="text-[11px] text-slate-500">Cédula {settings.negocio.identificacion}</p>
				{/if}
			</div>
		</div>

		<!-- Barra diagonal inferior: es la firma visual de esta plantilla -->
		<div class="relative h-3.5">
			<div
				class="ink-exact absolute inset-y-0 left-0 w-[46%]"
				style="background:{marca.deep}; clip-path: polygon(0 0, 100% 0, 92% 100%, 0 100%)"
			></div>
			<div
				class="ink-exact absolute inset-y-0 right-0 w-[30%]"
				style="background:{marca.base}; clip-path: polygon(6% 0, 100% 0, 100% 100%, 0 100%)"
			></div>
		</div>
	</header>

	<div class="px-8 py-6">
		<!-- Emisor y receptor -->
		<div class="mb-6 grid gap-6 sm:grid-cols-2">
			<section>
				<h2 class="mb-1 text-[11px] font-bold tracking-widest uppercase" style="color:{marca.base}">
					Facturar a
				</h2>
				{#if client}
					<p class="text-sm font-bold">{fullName(client)}</p>
					{#if client.identification}
						<p class="text-xs text-slate-600">Cédula {client.identification}</p>
					{/if}
					{#if client.address}<p class="text-xs text-slate-600">{client.address}</p>{/if}
					{#if client.telephone}<p class="text-xs text-slate-600">Tel. {client.telephone}</p>{/if}
					{#if client.email}<p class="text-xs text-slate-600">{client.email}</p>{/if}
				{:else}
					<p class="text-sm font-bold">Cliente de contado</p>
					<p class="text-xs text-slate-600">Venta sin cliente registrado</p>
				{/if}
			</section>

			<section class="sm:text-right">
				<h2 class="mb-1 text-[11px] font-bold tracking-widest uppercase" style="color:{marca.base}">
					Emisor
				</h2>
				{#each emisor as line (line)}
					<p class="text-xs leading-relaxed text-slate-600">{line}</p>
				{:else}
					<p class="text-xs text-slate-400">Completá los datos del negocio en Configuración.</p>
				{/each}
			</section>
		</div>

		<!-- Detalle -->
		{#if sale.items.length}
			<table class="w-full overflow-hidden rounded text-sm">
				<thead>
					<tr class="ink-exact" style="background:{marca.base}; color:{marca.ink}">
						<th scope="col" class="px-3 py-2.5 text-left text-xs font-bold tracking-wider uppercase">
							Descripción
						</th>
						<th scope="col" class="px-3 py-2.5 text-right text-xs font-bold tracking-wider uppercase">
							P. unitario
						</th>
						<th scope="col" class="px-3 py-2.5 text-right text-xs font-bold tracking-wider uppercase">
							Cant.
						</th>
						<th scope="col" class="px-3 py-2.5 text-right text-xs font-bold tracking-wider uppercase">
							Total
						</th>
					</tr>
				</thead>
				<tbody>
					{#each sale.items as item, index (item.id_product)}
						<tr class="ink-exact" style={index % 2 ? `background:${marca.tint}` : ''}>
							<td class="px-3 py-2.5 font-medium">
								{item.name}
								{#if doc.mostrar_codigo && barcodes[item.id_product]}
									<span class="block font-mono text-[11px] font-normal text-slate-500">
										{barcodes[item.id_product]}
									</span>
								{/if}
							</td>
							<td class="px-3 py-2.5 text-right text-slate-600">{formatMoney(item.price)}</td>
							<td class="px-3 py-2.5 text-right text-slate-600">{item.quantity}</td>
							<td class="px-3 py-2.5 text-right font-semibold">{formatMoney(item.subtotal)}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		{:else}
			<p class="border-y border-dashed border-slate-200 py-6 text-center text-sm text-slate-500">
				El backend no expone el detalle de esta venta.
			</p>
		{/if}

		<!-- Notas a la izquierda, totales a la derecha -->
		<div class="mt-6 grid gap-8 sm:grid-cols-2">
			<section>
				<h2 class="mb-2 text-sm font-bold" style="color:{marca.base}">Notas</h2>
				{#if doc.notas}
					<p class="text-xs leading-relaxed whitespace-pre-line text-slate-600">{doc.notas}</p>
				{:else}
					<!-- Renglones en blanco para escribir a mano, como las facturas de referencia -->
					<div class="space-y-4 pt-1">
						<div class="h-px bg-slate-200"></div>
						<div class="h-px bg-slate-200"></div>
						<div class="h-px bg-slate-200"></div>
					</div>
				{/if}
			</section>

			<div>
				<dl class="space-y-1.5 text-sm">
					<div class="flex justify-between border-b border-slate-200 pb-1">
						<dt class="font-semibold">Subtotal</dt>
						<dd>{formatMoney(sale.subtotal)}</dd>
					</div>
					<div class="flex justify-between border-b border-slate-200 pb-1">
						<dt class="font-semibold">{taxLabel()}</dt>
						<dd>{formatMoney(sale.tax)}</dd>
					</div>
					{#if sale.payment_method === 'Efectivo' && sale.cash_received > 0}
						<div class="flex justify-between text-slate-600">
							<dt>Efectivo recibido</dt>
							<dd>{formatMoney(sale.cash_received)}</dd>
						</div>
						<div class="flex justify-between text-slate-600">
							<dt>Vuelto</dt>
							<dd>{formatMoney(sale.change_given)}</dd>
						</div>
					{/if}
				</dl>

				<div
					class="ink-exact mt-2 flex items-baseline justify-between px-4 py-3"
					style="background:{marca.tint}; border-left: 4px solid {marca.base}"
				>
					<span class="text-sm font-bold tracking-wider uppercase">Total</span>
					<span class="text-xl font-bold" style="color:{marca.deep}">
						{formatMoney(sale.total)}
					</span>
				</div>

				{#if devuelto > 0}
					<p class="mt-2 text-right text-sm font-semibold text-red-700">
						Devuelto: −{formatMoney(devuelto)}
					</p>
				{/if}

				<div class="mt-8 text-center">
					<div class="mx-auto w-48 border-t border-slate-400 pt-1">
						<p class="text-xs font-semibold">{sale.user_name ?? '—'}</p>
						<p class="text-[11px] text-slate-500">Atendido por</p>
					</div>
				</div>
			</div>
		</div>

		{#if returns.length}
			<section class="mt-6 rounded border border-red-200 bg-red-50 px-4 py-3">
				<h2 class="text-xs font-bold tracking-wider text-red-700 uppercase">
					Devoluciones aplicadas
				</h2>
				<ul class="mt-1 space-y-0.5 text-xs text-red-700">
					{#each returns as devolucion (devolucion.id)}
						<li>
							{formatDateTime(devolucion.created_at)} — {formatMoney(devolucion.total)} ·
							{devolucion.reason}
						</li>
					{/each}
				</ul>
			</section>
		{/if}

		{#if doc.mensaje_gracias || doc.leyenda}
			<div class="mt-6 text-center">
				{#if doc.mensaje_gracias}
					<p class="text-sm font-semibold" style="color:{marca.base}">{doc.mensaje_gracias}</p>
				{/if}
				{#if doc.leyenda}<p class="mt-0.5 text-[11px] text-slate-500">{doc.leyenda}</p>{/if}
			</div>
		{/if}
	</div>

	<!-- Barra de contacto -->
	<footer class="relative h-12">
		<div
			class="ink-exact absolute inset-0"
			style="background:{marca.deep}; clip-path: polygon(0 0, 100% 0, 100% 100%, 3% 100%)"
		></div>
		<div
			class="relative flex h-full items-center justify-center gap-6 px-8 text-[11px] font-medium"
			style="color:#ffffff"
		>
			{#each contacto as dato (dato)}
				<span class="truncate">{dato}</span>
			{:else}
				<span class="opacity-70">Agregá teléfono y correo en Configuración</span>
			{/each}
		</div>
	</footer>
</article>
