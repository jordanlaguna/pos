import type { ImportFailure } from '$lib/domain/types';

/**
 * Lo que impide leer un archivo, en código y datos.
 *
 * Un `Error` con la frase adentro obligaba a la pantalla a mostrar
 * `error.message` tal cual, y eso es texto en español escrito por un adaptador
 * —no por la interfaz—. La frase la arma `importMessage()` en
 * `$lib/ui/messages` (RN-30).
 */
export class ImportError extends Error {
	readonly failure: ImportFailure;

	constructor(failure: ImportFailure) {
		super(failure.code);
		this.name = 'ImportError';
		this.failure = failure;
	}
}
