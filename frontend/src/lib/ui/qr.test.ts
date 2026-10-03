import { describe, expect, it } from 'vitest';

import { QR_LEVEL, QR_QUIET_ZONE, qrDrawing } from './qr';

/** La de la factura aceptada por Hacienda, `docs/invoice/50624…346.pdf`. */
const CLAVE = '50624092600310170293400100001010001819201163700346';

/** Los rectángulos del `path`: columna, fila y largo de cada tramo oscuro. */
function tramos(path: string) {
	return [...path.matchAll(/M(\d+) (\d+)h(\d+)v1h-(\d+)z/g)].map(([, x, y, largo, vuelta]) => ({
		x: Number(x),
		y: Number(y),
		largo: Number(largo),
		vuelta: Number(vuelta)
	}));
}

describe('el QR de la clave (T-705)', () => {
	/*
	 * Que se lee se comprobó a mano el 2026-09-27: el dibujo de esta clave,
	 * pasado a imagen, lo decodifica zxing como los 50 dígitos exactos con nivel
	 * Q, lo mismo que el QR de la factura aceptada. Acá queda lo que no depende
	 * de tener un lector a mano.
	 */
	it('es una versión 3 —29 × 29— con cuatro módulos de margen por lado', () => {
		const { size } = qrDrawing(CLAVE);
		expect(size).toBe(29 + 2 * QR_QUIET_ZONE);
	});

	it('usa el nivel de la factura de referencia', () => {
		expect(QR_LEVEL).toBe('Q');
	});

	it('el path son solo tramos de una fila, todos dentro del margen', () => {
		const { size, path } = qrDrawing(CLAVE);
		const partes = tramos(path);

		expect(partes.length).toBeGreaterThan(0);
		// Nada fuera de los rectángulos: el path se lee entero con la expresión.
		expect(partes.map((t) => `M${t.x} ${t.y}h${t.largo}v1h-${t.vuelta}z`).join('')).toBe(path);
		for (const t of partes) {
			expect(t.vuelta).toBe(t.largo);
			expect(t.x).toBeGreaterThanOrEqual(QR_QUIET_ZONE);
			expect(t.y).toBeGreaterThanOrEqual(QR_QUIET_ZONE);
			expect(t.x + t.largo).toBeLessThanOrEqual(size - QR_QUIET_ZONE);
			expect(t.y).toBeLessThan(size - QR_QUIET_ZONE);
		}
	});

	it('lleva los tres patrones de posición en las esquinas', () => {
		// La fila de arriba de cada patrón es un tramo de siete módulos: arriba a
		// la izquierda, arriba a la derecha, y abajo a la izquierda.
		const { size, path } = qrDrawing(CLAVE);
		const siete = tramos(path).filter((t) => t.largo === 7);
		const q = QR_QUIET_ZONE;
		const lado = size - 2 * q;
		expect(siete).toContainEqual({ x: q, y: q, largo: 7, vuelta: 7 });
		expect(siete).toContainEqual({ x: q + lado - 7, y: q, largo: 7, vuelta: 7 });
		expect(siete).toContainEqual({ x: q, y: q + lado - 7, largo: 7, vuelta: 7 });
	});

	it('la misma clave da siempre el mismo dibujo, y otra clave otro', () => {
		expect(qrDrawing(CLAVE)).toEqual(qrDrawing(CLAVE));
		expect(qrDrawing(CLAVE.replace(/6$/, '7')).path).not.toBe(qrDrawing(CLAVE).path);
	});

	it('un texto que no son dígitos va en modo byte, que ocupa más', () => {
		// No pasa con una clave; queda probado para que el modo numérico sea una
		// decisión y no un accidente.
		expect(qrDrawing(`C${CLAVE.slice(1)}`).size).toBeGreaterThan(qrDrawing(CLAVE).size);
	});
});
