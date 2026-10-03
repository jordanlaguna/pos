<script lang="ts">
	import Icon from '$lib/ui/components/Icon.svelte';
	import Boleta from '$lib/ui/components/documents/Boleta.svelte';
	import { employeeName } from '$lib/domain/payroll';
	import { m } from '$lib/paraglide/messages.js';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	const logoUrl = $derived(data.logoVersion ? `/marca/logo?v=${data.logoVersion}` : null);
</script>

<svelte:head>
	<title>{m.payslip_tab_title({ name: employeeName(data.payslip.employee) })}</title>
</svelte:head>

<div class="no-print mb-4 flex flex-wrap items-center justify-between gap-3">
	<a
		href="/planilla/corridas/{data.payslip.run.id}"
		class="inline-flex items-center gap-1.5 text-sm font-semibold text-[var(--text-muted)] hover:text-[var(--text)]"
	>
		<Icon name="back" size={15} />
		{m.payslip_back()}
	</a>
	<button type="button" class="btn btn-primary" onclick={() => window.print()}>
		<Icon name="printer" size={15} />
		{m.payslip_print()}
	</button>
</div>

<!--
	`docLocale` es el idioma de la **compañía**, no el de la pantalla (RN-29): la
	boleta es para el empleado, no para quien la imprime.
-->
<Boleta
	payslip={data.payslip}
	settings={data.settings}
	{logoUrl}
	docLocale={data.user?.document_locale ?? 'es'}
/>
