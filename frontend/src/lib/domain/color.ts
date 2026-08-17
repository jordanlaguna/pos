/**
 * Color de marca: derivar un tema legible a partir de un solo tono.
 *
 * El dueño del negocio elige un color y espera que el sistema se vea de ese
 * color. Lo que no espera —y con razón— es tener que pensar en contraste, en
 * qué tono usar sobre fondo oscuro, ni en si el texto del botón va blanco o
 * negro. Eso se calcula acá.
 *
 * El ajuste se hace en OKLab y no en HSL. En HSL, dos colores con la misma `L`
 * se ven con brillos distintos —un amarillo al 50 % deslumbra y un azul al 50 %
 * se hunde—, así que bajar la luminosidad de un amarillo para que aguante texto
 * blanco lo deja sucio y verdoso. OKLab es perceptualmente uniforme: mover la L
 * cambia el brillo y deja el tono donde estaba.
 *
 * Nada de esto es cuestión de gusto: el contraste es una división y se calcula.
 * `contrastRatio` es la fórmula de WCAG 2.1, y la pantalla de configuración
 * muestra el resultado en vez de dar por bueno el color elegido.
 */

export interface Rgb {
	r: number;
	g: number;
	b: number;
}

export interface Oklab {
	L: number;
	a: number;
	b: number;
}

export function hexToRgb(hex: string): Rgb {
	const clean = hex.replace('#', '');
	return {
		r: parseInt(clean.slice(0, 2), 16) / 255,
		g: parseInt(clean.slice(2, 4), 16) / 255,
		b: parseInt(clean.slice(4, 6), 16) / 255
	};
}

function channel(value: number): string {
	return Math.round(Math.min(1, Math.max(0, value)) * 255)
		.toString(16)
		.padStart(2, '0');
}

export function rgbToHex({ r, g, b }: Rgb): string {
	return `#${channel(r)}${channel(g)}${channel(b)}`;
}

/** sRGB con gamma → lineal. La gamma existe para la pantalla, no para la matemática. */
function toLinear(c: number): number {
	return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
}

function toGamma(c: number): number {
	return c <= 0.0031308 ? 12.92 * c : 1.055 * Math.pow(c, 1 / 2.4) - 0.055;
}

/** Coeficientes de Björn Ottosson (2020), la definición de OKLab. */
export function rgbToOklab({ r, g, b }: Rgb): Oklab {
	const lr = toLinear(r);
	const lg = toLinear(g);
	const lb = toLinear(b);

	const l = Math.cbrt(0.4122214708 * lr + 0.5363325363 * lg + 0.0514459929 * lb);
	const m = Math.cbrt(0.2119034982 * lr + 0.6806995451 * lg + 0.1073969566 * lb);
	const s = Math.cbrt(0.0883024619 * lr + 0.2817188376 * lg + 0.6299787005 * lb);

	return {
		L: 0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s,
		a: 1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
		b: 0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s
	};
}

export function oklabToRgb({ L, a, b }: Oklab): Rgb {
	const l = Math.pow(L + 0.3963377774 * a + 0.2158037573 * b, 3);
	const m = Math.pow(L - 0.1055613458 * a - 0.0638541728 * b, 3);
	const s = Math.pow(L - 0.0894841775 * a - 1.291485548 * b, 3);

	return {
		r: toGamma(4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s),
		g: toGamma(-1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s),
		b: toGamma(-0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s)
	};
}

/**
 * Mismo tono, otra luminosidad.
 *
 * Al subir o bajar la L, un color muy saturado puede salirse de lo que la
 * pantalla sabe mostrar (sRGB). En vez de recortar cada canal —que corre el
 * tono— se baja el croma hasta que vuelve a caber, que es lo que hacen los
 * espacios de color modernos.
 */
export function withLightness(hex: string, lightness: number): string {
	const { a, b } = rgbToOklab(hexToRgb(hex));
	let scale = 1;

	for (let i = 0; i < 24; i++) {
		const rgb = oklabToRgb({ L: lightness, a: a * scale, b: b * scale });
		const inGamut = [rgb.r, rgb.g, rgb.b].every((c) => c >= -0.001 && c <= 1.001);
		if (inGamut) return rgbToHex(rgb);
		scale *= 0.92;
	}
	// Gris de esa luminosidad: si ni sin croma cabe, el tono no era representable.
	return rgbToHex(oklabToRgb({ L: lightness, a: 0, b: 0 }));
}

/** Luminancia relativa de WCAG 2.1. */
export function relativeLuminance(hex: string): number {
	const { r, g, b } = hexToRgb(hex);
	return 0.2126 * toLinear(r) + 0.7152 * toLinear(g) + 0.0722 * toLinear(b);
}

/** Razón de contraste WCAG: de 1 (idénticos) a 21 (negro contra blanco). */
export function contrastRatio(a: string, b: string): number {
	const la = relativeLuminance(a);
	const lb = relativeLuminance(b);
	const [light, dark] = la > lb ? [la, lb] : [lb, la];
	return (light + 0.05) / (dark + 0.05);
}

/** Blanco o casi negro, el que se lea mejor encima del color dado. */
export function readableInk(background: string): string {
	const white = '#ffffff';
	const ink = '#0f172a';
	return contrastRatio(background, white) >= contrastRatio(background, ink) ? white : ink;
}

export interface AccentTheme {
	/** Acento del tema claro. */
	light: string;
	/** Acento del tema oscuro: el mismo tono, subido de luminosidad. */
	dark: string;
	inkLight: string;
	inkDark: string;
	/** Tono para los gráficos, o null si el elegido no pasa contra ambas superficies. */
	chart: string | null;
	/** Contraste del texto sobre el acento en cada tema. */
	contrastLight: number;
	contrastDark: number;
}

// Superficies contra las que se mide (de app.css).
const SURFACE_LIGHT = '#ffffff';
const SURFACE_DARK = '#1e293b';

/**
 * Tema completo a partir de un color.
 *
 * La luminosidad del acento claro se sujeta a la banda 0,38–0,62: por debajo el
 * botón se ve casi negro y por encima el texto blanco deja de leerse. Si el
 * color elegido ya cae dentro, se respeta tal cual.
 *
 * El acento oscuro va a 0,80 —el mismo lugar donde estaba el cian original
 * (#22d3ee)— porque sobre fondo oscuro hace falta un tono claro, no el mismo.
 */
export function accentTheme(hex: string): AccentTheme {
	const { L } = rgbToOklab(hexToRgb(hex));
	/*
	 * Aunque la L ya esté en banda se vuelve a componer el hex desde los canales
	 * en vez de devolver la cadena recibida. El resultado termina dentro de una
	 * etiqueta <style>, y que ahí solo puedan llegar valores fabricados acá es más
	 * barato que confiar en que quien llame ya validó.
	 */
	const light = withLightness(hex, Math.min(0.62, Math.max(0.38, L)));
	const dark = withLightness(hex, 0.8);

	const inkLight = readableInk(light);
	const inkDark = readableInk(dark);

	/*
	 * Los gráficos exigen ≥3:1 contra AMBAS superficies, porque el mismo tono se
	 * usa en tema claro y oscuro (así estaba validado el cian). Si el color del
	 * business no llega, se devuelve null y el gráfico se queda con el suyo: vale
	 * más una barra que se vea que una que combine.
	 */
	const chart =
		contrastRatio(light, SURFACE_LIGHT) >= 3 && contrastRatio(light, SURFACE_DARK) >= 3
			? light
			: null;

	return {
		light,
		dark,
		inkLight,
		inkDark,
		chart,
		contrastLight: contrastRatio(light, inkLight),
		contrastDark: contrastRatio(dark, inkDark)
	};
}
