/**
 * El código QR del comprobante (T-705, RN-86).
 *
 * Lo que se codifica lo dice la factura aceptada por Hacienda que el usuario dejó
 * en `docs/invoice/`: **la clave sola**, los 50 dígitos, con corrección de
 * errores Q. Decodificado, su QR es exactamente
 * `50624092600310170293400100001010001819201163700346`: ni una dirección ni
 * otros datos. Quien lo escanea consulta esa clave en el portal de Hacienda.
 *
 * Vive en la interfaz y no en el dominio porque es cómo se dibuja, no qué se
 * emite: el dominio ya decide la clave. Y es el único módulo que importa el
 * codificador (`qrcode-generator`, sin dependencias propias).
 *
 * Sale un solo `path` de SVG y no una imagen: se imprime nítido a cualquier
 * tamaño, en el rollo térmico y en la hoja, y se arma igual en el servidor que
 * en el navegador —no hay `canvas` de por medio—.
 */

import qrcode from 'qrcode-generator';

/** El de la factura de referencia: recupera hasta un cuarto de los módulos. */
export const QR_LEVEL = 'Q';

/**
 * El margen blanco alrededor, en módulos. Cuatro es lo que pide la norma del
 * QR: con menos, un lector puede confundir el borde con un dato, y en la hoja
 * moderna el QR va sobre la franja de color.
 */
export const QR_QUIET_ZONE = 4;

export interface QrDrawing {
	/** Lado del dibujo en módulos, con el margen incluido. Es el `viewBox`. */
	size: number;
	/** Los módulos oscuros, fila por fila, como un `path` de SVG. */
	path: string;
}

/**
 * El QR de un texto, listo para un `<svg viewBox="0 0 size size">`.
 *
 * Los dígitos van en modo numérico, que es el que usa el de Hacienda y el que
 * deja el QR más chico: 50 dígitos caben en una versión 3 (29 × 29).
 */
export function qrDrawing(text: string): QrDrawing {
	const qr = qrcode(0, QR_LEVEL);
	qr.addData(text, /^\d+$/.test(text) ? 'Numeric' : 'Byte');
	qr.make();

	const n = qr.getModuleCount();
	const partes: string[] = [];
	for (let fila = 0; fila < n; fila++) {
		let columna = 0;
		while (columna < n) {
			if (!qr.isDark(fila, columna)) {
				columna++;
				continue;
			}
			// Un rectángulo por tramo oscuro de la fila y no uno por módulo: el
			// `path` queda varias veces más corto y se dibuja igual.
			const desde = columna;
			while (columna < n && qr.isDark(fila, columna)) columna++;
			const largo = columna - desde;
			partes.push(`M${desde + QR_QUIET_ZONE} ${fila + QR_QUIET_ZONE}h${largo}v1h-${largo}z`);
		}
	}
	return { size: n + 2 * QR_QUIET_ZONE, path: partes.join('') };
}
