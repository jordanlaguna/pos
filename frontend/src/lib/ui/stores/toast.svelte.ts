import { untrack } from 'svelte';

/**
 * Avisos efímeros.
 *
 * Reemplazan los `MessageBox.Show(...)` del WinForms, que bloqueaban el hilo y
 * obligaban al cajero a soltar el teclado para darle clic a "Aceptar". Aquí el
 * aviso aparece en una esquina y se va solo.
 */

export type ToastKind = 'success' | 'error' | 'info' | 'warning';

export interface Toast {
	id: number;
	kind: ToastKind;
	message: string;
	/** Texto secundario opcional, p. ej. el detalle del error del backend. */
	detail?: string;
}

const DURATIONS: Record<ToastKind, number> = {
	success: 3000,
	info: 3500,
	warning: 5000,
	// Los errores se quedan más tiempo: suelen traer información que hay que leer.
	error: 7000
};

let sequence = 0;

class ToastStore {
	items = $state<Toast[]>([]);

	push(kind: ToastKind, message: string, detail?: string): number {
		const id = ++sequence;

		/*
		 * `untrack` no es decorativo: sin él esto cuelga el navegador.
		 *
		 * Reasignar `this.items` obliga a LEERLO primero. Si la llamada ocurre
		 * dentro de un `$effect`, esa lectura queda registrada como dependencia
		 * del effect, y la escritura que viene a continuación lo vuelve a
		 * disparar: aviso, lectura, escritura, aviso… hasta congelar la pestaña.
		 * Pasó de verdad, con decenas de «Caja abierta» apilados.
		 *
		 * Mostrar un aviso no es leer estado del que se dependa, así que la
		 * lectura no debe crear dependencia. Se blinda acá, en un solo lugar, en
		 * vez de confiar en que nadie vuelva a llamar a un toast desde un effect.
		 */
		untrack(() => {
			this.items = [...this.items, { id, kind, message, detail }];
		});

		if (typeof window !== 'undefined') {
			setTimeout(() => this.dismiss(id), DURATIONS[kind]);
		}
		return id;
	}

	success(message: string, detail?: string) {
		return this.push('success', message, detail);
	}
	error(message: string, detail?: string) {
		return this.push('error', message, detail);
	}
	info(message: string, detail?: string) {
		return this.push('info', message, detail);
	}
	warning(message: string, detail?: string) {
		return this.push('warning', message, detail);
	}

	dismiss(id: number) {
		untrack(() => {
			this.items = this.items.filter((t) => t.id !== id);
		});
	}

	clear() {
		this.items = [];
	}
}

export const toasts = new ToastStore();
