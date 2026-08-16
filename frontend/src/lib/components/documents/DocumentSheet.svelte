<script lang="ts">
	/**
	 * Elige la plantilla configurada.
	 *
	 * Quien imprime una venta —la pantalla de factura, la vista previa de
	 * Configuración— usa este componente y no las plantillas directamente, para
	 * que exista un solo lugar donde se decide cuál se muestra.
	 */
	import type { DocumentProps } from '$lib/documents';
	import FacturaClasica from './FacturaClasica.svelte';
	import FacturaModerna from './FacturaModerna.svelte';
	import Tiquete from './Tiquete.svelte';

	let props: DocumentProps = $props();
</script>

{#if props.settings.documento.plantilla === 'clasica'}
	<FacturaClasica {...props} />
{:else if props.settings.documento.plantilla === 'moderna'}
	<FacturaModerna {...props} />
{:else}
	<Tiquete {...props} />
{/if}
