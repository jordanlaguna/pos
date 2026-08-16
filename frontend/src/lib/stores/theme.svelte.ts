import { browser } from '$app/environment';

/** Tema claro/oscuro. El valor inicial lo fija el script en línea de app.html. */

export type Theme = 'light' | 'dark';

const STORAGE_KEY = 'ventasys-theme';

function initial(): Theme {
	if (!browser) return 'light';
	const attr = document.documentElement.dataset.theme;
	return attr === 'dark' ? 'dark' : 'light';
}

class ThemeStore {
	current = $state<Theme>(initial());

	set(theme: Theme) {
		this.current = theme;
		if (!browser) return;
		document.documentElement.dataset.theme = theme;
		try {
			localStorage.setItem(STORAGE_KEY, theme);
		} catch {
			// Modo privado sin almacenamiento: el tema dura lo que la pestaña.
		}
	}

	toggle() {
		this.set(this.current === 'dark' ? 'light' : 'dark');
	}
}

export const theme = new ThemeStore();
