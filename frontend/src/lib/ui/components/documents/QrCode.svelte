<script lang="ts">
	/**
	 * El QR de la clave, como lo lleva la factura aceptada por Hacienda (T-705).
	 *
	 * **Negro sobre blanco siempre**, también con el tema oscuro y sobre la franja
	 * de color de la hoja moderna: un QR que sigue los tokens de la pantalla deja
	 * de leerse, y el fondo blanco es parte del margen que el lector necesita.
	 * Por eso los colores son las clases fijas de Tailwind y no los de `app.css`.
	 */
	import { qrDrawing } from '$lib/ui/qr';

	let {
		text,
		label,
		class: className = ''
	}: {
		/** Lo que se codifica: la clave. */
		text: string;
		/** Para un lector de pantalla, en el idioma del documento. */
		label: string;
		class?: string;
	} = $props();

	const dibujo = $derived(qrDrawing(text));
</script>

<svg
	viewBox="0 0 {dibujo.size} {dibujo.size}"
	class="ink-exact block {className}"
	role="img"
	aria-label={label}
	shape-rendering="crispEdges"
	data-qr={text}
>
	<rect width={dibujo.size} height={dibujo.size} class="fill-white" />
	<path d={dibujo.path} class="fill-black" />
</svg>
