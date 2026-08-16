import type { SubmitFunction } from '@sveltejs/kit';
import { toasts } from '$lib/stores/toast.svelte';

/**
 * Envío de formularios con aviso y cierre de diálogo.
 *
 * Reemplaza al patrón de reaccionar a `form` desde un `$effect`, que tenía dos
 * problemas. Uno grave: llamar a un toast dentro de un effect creaba un bucle
 * infinito que congelaba la pestaña (ver el comentario de `toasts.push`). Y otro
 * silencioso: `form` conserva su valor al navegar, así que al volver a la
 * pantalla el aviso se mostraba de nuevo, sin que nadie hubiera enviado nada.
 *
 * El callback de `use:enhance` corre exactamente una vez por envío, que es justo
 * la semántica que se quería.
 *
 *     <form method="POST" action="?/crear" use:enhance={submit({
 *         onSuccess: () => (modalOpen = false),
 *         setBusy: (v) => (submitting = v)
 *     })}>
 */
export interface SubmitOptions {
	/** Corre tras un envío correcto. El sitio para cerrar el diálogo. */
	onSuccess?: (data: Record<string, unknown> | undefined) => void;
	/** Corre cuando la acción devuelve `fail(...)`. */
	onFailure?: (data: Record<string, unknown> | undefined) => void;
	/**
	 * Corre cuando la acción termina en `redirect`. Es el caso del cobro: la
	 * venta se registró y Kit está por navegar a la factura.
	 */
	onRedirect?: () => void;
	/** Título del aviso de error. */
	errorTitle?: string;
	/** Vaciar los campos al terminar. Por defecto no, para poder corregir. */
	reset?: boolean;
	/** Se llama con `true` al empezar y `false` al terminar. */
	setBusy?: (busy: boolean) => void;
	/** Silencia el aviso automático de éxito. */
	quiet?: boolean;
}

function textOf(value: unknown): string | null {
	return typeof value === 'string' && value.trim() ? value : null;
}

export function submit(options: SubmitOptions = {}): SubmitFunction {
	const { onSuccess, onFailure, onRedirect, errorTitle, reset = false, setBusy, quiet } = options;

	return () => {
		setBusy?.(true);

		return async ({ result, update }) => {
			if (result.type === 'success') {
				const data = result.data as Record<string, unknown> | undefined;
				const message = textOf(data?.success);
				if (message && !quiet) toasts.success(message);
				onSuccess?.(data);
			} else if (result.type === 'failure') {
				const data = result.data as Record<string, unknown> | undefined;
				const errors = data?.errors as Record<string, string> | undefined;
				// `errors.form` es el error general; `message` lo usan las acciones
				// que no validan campo por campo, como el cobro.
				const message = textOf(errors?.form) ?? textOf(data?.message);
				if (message) toasts.error(errorTitle ?? 'No se pudo completar', message);
				onFailure?.(data);
			} else if (result.type === 'redirect') {
				onRedirect?.();
			}

			// Los redirect y los error los maneja Kit por su cuenta.
			await update({ reset });
			setBusy?.(false);
		};
	};
}
