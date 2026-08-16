import type { IconName } from '$lib/components/Icon.svelte';
import type { Role } from '$lib/types';

export interface NavItem {
	href: string;
	label: string;
	icon: IconName;
	/** Roles que pueden verlo. Sin la lista, lo ve cualquier sesión iniciada. */
	roles?: Role[];
	/** Tecla rápida mostrada en el menú (se maneja en el layout). */
	shortcut?: string;
}

export interface NavGroup {
	title: string;
	items: NavItem[];
}

export const NAV: NavGroup[] = [
	{
		title: 'Operación',
		items: [
			{ href: '/ventas', label: 'Ventas', icon: 'cart', shortcut: 'F2' },
			{ href: '/caja', label: 'Caja', icon: 'wallet' },
			{ href: '/facturas', label: 'Facturas', icon: 'receipt' },
			{ href: '/devoluciones', label: 'Devoluciones', icon: 'undo' }
		]
	},
	{
		title: 'Administración',
		items: [
			{ href: '/dashboard', label: 'Reportes', icon: 'chart', roles: ['admin'] },
			{ href: '/inventario', label: 'Inventario', icon: 'box', roles: ['admin'] },
			{ href: '/clientes', label: 'Clientes', icon: 'users' },
			{ href: '/usuarios', label: 'Usuarios', icon: 'user', roles: ['admin'] },
			{ href: '/configuracion', label: 'Configuración', icon: 'settings', roles: ['admin'] }
		]
	}
];

/** Ítem del menú resuelto para un rol: los que no puede abrir van bloqueados. */
export interface ResolvedItem extends NavItem {
	locked: boolean;
}

/**
 * Menú para un rol.
 *
 * Las secciones que el rol no puede abrir se muestran igual, atenuadas y con
 * candado, en vez de desaparecer. Ocultarlas hacía que un cajero creyera que el
 * sistema no tiene inventario ni reportes, en lugar de entender que le falta
 * permiso; pasó de verdad. No es un dato sensible —el control de acceso está en
 * el servidor, no en el menú— y ahorra la pregunta de «¿dónde está X?».
 */
export function visibleGroups(role: Role): (NavGroup & { items: ResolvedItem[] })[] {
	return NAV.map((group) => ({
		...group,
		items: group.items.map((item) => ({
			...item,
			locked: Boolean(item.roles && !item.roles.includes(role))
		}))
	})).filter((group) => group.items.length > 0);
}

/** Título de la pestaña y encabezado, resuelto por la ruta activa. */
export function titleFor(pathname: string): string {
	for (const group of NAV) {
		for (const item of group.items) {
			if (pathname === item.href || pathname.startsWith(`${item.href}/`)) return item.label;
		}
	}
	return 'VentaSys';
}
