import { describe, expect, it } from 'vitest';
import {
	accentTheme,
	contrastRatio,
	hexToRgb,
	oklabToRgb,
	readableInk,
	relativeLuminance,
	rgbToHex,
	rgbToOklab,
	withLightness
} from './color';

const BLANCO = '#ffffff';
const TINTA = '#0f172a';

describe('invariante de progress.json', () => {
	it('el acento #b45309 deriva 5,0:1 en claro y #fea575 a 9,2:1 en oscuro', () => {
		const t = accentTheme('#b45309');
		expect(t.light).toBe('#b45309');
		expect(t.inkLight).toBe(BLANCO);
		expect(t.contrastLight).toBeCloseTo(5.0, 1);
		expect(t.dark).toBe('#fea575');
		expect(t.inkDark).toBe(TINTA);
		expect(t.contrastDark).toBeCloseTo(9.2, 1);
	});
});

describe('conversión de hex', () => {
	it('va y vuelve sin perder nada', () => {
		for (const hex of ['#000000', '#ffffff', '#0e7490', '#b45309', '#22d3ee']) {
			expect(rgbToHex(hexToRgb(hex))).toBe(hex);
		}
	});

	it('acepta el hex sin numeral', () => {
		expect(hexToRgb('ffffff')).toEqual({ r: 1, g: 1, b: 1 });
	});

	it('recorta los canales que se salen de rango', () => {
		expect(rgbToHex({ r: 2, g: -1, b: 0.5 })).toBe('#ff0080');
	});
});

describe('OKLab', () => {
	it('el blanco tiene L 1 y no tiene croma', () => {
		const { L, a, b } = rgbToOklab({ r: 1, g: 1, b: 1 });
		expect(L).toBeCloseTo(1, 3);
		expect(a).toBeCloseTo(0, 3);
		expect(b).toBeCloseTo(0, 3);
	});

	it('el negro tiene L 0', () => {
		expect(rgbToOklab({ r: 0, g: 0, b: 0 }).L).toBeCloseTo(0, 6);
	});

	it('la ida y la vuelta reconstruyen el color', () => {
		for (const hex of ['#0e7490', '#b45309', '#22d3ee', '#7c3aed']) {
			const rgb = hexToRgb(hex);
			expect(rgbToHex(oklabToRgb(rgbToOklab(rgb)))).toBe(hex);
		}
	});
});

describe('withLightness', () => {
	it('mueve el brillo y deja el tono', () => {
		const original = rgbToOklab(hexToRgb('#0e7490'));
		const claro = rgbToOklab(hexToRgb(withLightness('#0e7490', 0.8)));

		expect(claro.L).toBeCloseTo(0.8, 2);

		/*
		 * El ángulo de tono se conserva aunque el croma se haya reducido. Se mide
		 * en grados y no en radianes porque la tolerancia solo tiene sentido ahí:
		 * el resultado se guarda como hex de 8 bits por canal, y ese redondeo solo
		 * ya corre el ángulo unas décimas de grado. Un grado es invisible; lo que
		 * esta prueba descarta es que bajar la luminosidad vuelva verdoso al cian,
		 * que es lo que pasaba en HSL.
		 */
		const grados = (o: { a: number; b: number }) => (Math.atan2(o.b, o.a) * 180) / Math.PI;
		expect(Math.abs(grados(claro) - grados(original))).toBeLessThan(1);
	});

	it('baja el croma en vez de recortar cuando el color no cabe en la pantalla', () => {
		// Un rojo saturadísimo a luminosidad alta no existe en sRGB: tiene que
		// desaturarse, no volverse naranja por recorte de canales.
		const alto = withLightness('#ff0000', 0.95);
		const { L, a, b } = rgbToOklab(hexToRgb(alto));
		expect(L).toBeCloseTo(0.95, 2);
		expect(Math.hypot(a, b)).toBeLessThan(Math.hypot(...Object.values(rgbToOklab(hexToRgb('#ff0000'))).slice(1)));
	});

	it('cae a gris cuando ni sin croma el tono es representable', () => {
		// L = 1 solo la alcanza el blanco: cualquier tono termina en gris claro.
		expect(withLightness('#ff0000', 1)).toBe('#ffffff');
	});
});

describe('contraste WCAG', () => {
	it('negro contra blanco es 21:1', () => {
		expect(contrastRatio('#000000', BLANCO)).toBeCloseTo(21, 5);
	});

	it('un color contra sí mismo es 1:1', () => {
		expect(contrastRatio('#0e7490', '#0e7490')).toBeCloseTo(1, 5);
	});

	it('no depende del orden de los argumentos', () => {
		expect(contrastRatio('#0e7490', BLANCO)).toBeCloseTo(contrastRatio(BLANCO, '#0e7490'), 6);
	});

	it('la luminancia relativa del blanco es 1 y la del negro 0', () => {
		expect(relativeLuminance(BLANCO)).toBeCloseTo(1, 6);
		expect(relativeLuminance('#000000')).toBeCloseTo(0, 6);
	});
});

describe('readableInk', () => {
	it('pone tinta oscura sobre un fondo claro', () => {
		expect(readableInk('#fde68a')).toBe(TINTA);
	});

	it('y blanco sobre uno oscuro', () => {
		expect(readableInk('#0e7490')).toBe(BLANCO);
	});
});

describe('accentTheme', () => {
	it('sujeta a la banda 0,38–0,62 un color demasiado oscuro', () => {
		const { L } = rgbToOklab(hexToRgb(accentTheme('#020617').light));
		expect(L).toBeCloseTo(0.38, 2);
	});

	it('y uno demasiado claro', () => {
		const { L } = rgbToOklab(hexToRgb(accentTheme('#fef9c3').light));
		expect(L).toBeCloseTo(0.62, 2);
	});

	it('respeta el color cuando ya cae dentro de la banda', () => {
		expect(accentTheme('#0e7490').light).toBe('#0e7490');
	});

	it('el acento oscuro siempre queda más claro que el claro', () => {
		for (const hex of ['#0e7490', '#b45309', '#7c3aed', '#020617']) {
			const t = accentTheme(hex);
			expect(relativeLuminance(t.dark)).toBeGreaterThan(relativeLuminance(t.light));
		}
	});

	it('da tono de gráfico solo si pasa 3:1 contra las dos superficies', () => {
		const cian = accentTheme('#0891b2');
		expect(cian.chart).not.toBeNull();
		expect(contrastRatio(cian.chart as string, BLANCO)).toBeGreaterThanOrEqual(3);
		expect(contrastRatio(cian.chart as string, '#1e293b')).toBeGreaterThanOrEqual(3);
	});

	it('y lo niega cuando no llega contra alguna de las dos', () => {
		// Un tono oscuro pasa contra el fondo claro y falla contra el oscuro.
		expect(accentTheme('#020617').chart).toBeNull();
	});

	it('siempre reconstruye el hex, aunque no haya que ajustar nada', () => {
		// Lo que devuelve termina dentro de una etiqueta <style>: no puede ser la
		// cadena que entró.
		expect(accentTheme('#0E7490').light).toBe('#0e7490');
	});
});
