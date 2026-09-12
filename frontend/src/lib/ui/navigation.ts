import type { IconName } from '$lib/ui/components/Icon.svelte';
import type { ModuleName, Modules, Role } from '$lib/domain/types';
import { m } from '$lib/paraglide/messages.js';

export interface NavItem {
	href: string;
	label: string;
	icon: IconName;
	/** Roles que pueden verlo. Sin la lista, lo ve cualquier sesión iniciada. */
	roles?: Role[];
	/**
	 * Módulo del plan al que pertenece (RN-49). Sin él, no depende de ninguno.
	 *
	 * Se trata **igual que un rol que falta**: la sección se ve con candado, no
	 * desaparece. Ver `visibleGroups`.
	 */
	module?: ModuleName;
	/** Tecla rápida mostrada en el menú (se maneja en el layout). */
	shortcut?: string;
}

export interface NavGroup {
	title: string;
	items: NavItem[];
}

/**
 * El menú.
 *
 * **Es una función y no una constante** (T-804). Una constante se evaluaría al
 * importar el módulo, o sea una vez por proceso de Node, y todas las peticiones
 * verían los rótulos del idioma de la primera. Es el mismo motivo por el que
 * `$lib/ui/fields.ts` también son funciones, y la tercera vez que aparece el
 * defecto 17 disfrazado en esta fase.
 *
 * Las rutas y los iconos sí podrían ser constantes, pero separarlos dejaría la
 * definición del menú en dos sitios que hay que mantener en paralelo.
 */
export function nav(): NavGroup[] {
	return [
		{
			title: m.nav_group_operations(),
			items: [
				{ href: '/ventas', label: m.nav_sales(), icon: 'cart', shortcut: 'F2' },
				{ href: '/caja', label: m.nav_cash(), icon: 'wallet' },
				{ href: '/facturas', label: m.nav_invoices(), icon: 'receipt' },
				{ href: '/devoluciones', label: m.nav_returns(), icon: 'undo' }
			]
		},
		{
			title: m.nav_group_admin(),
			items: [
				{ href: '/dashboard', label: m.nav_reports(), icon: 'chart', roles: ['admin'] },
				{ href: '/inventario', label: m.nav_inventory(), icon: 'box', roles: ['admin'] },
				{ href: '/clientes', label: m.nav_clients(), icon: 'users' },
				{ href: '/usuarios', label: m.nav_users(), icon: 'user', roles: ['admin'] },
				{
					href: '/configuracion',
					label: m.nav_settings(),
					icon: 'settings',
					roles: ['admin']
				}
			]
		}
	];
}

/** Ítem del menú resuelto para un rol: los que no puede abrir van bloqueados. */
export interface ResolvedItem extends NavItem {
	locked: boolean;
}

/**
 * Menú para un rol y para los módulos que incluye el plan.
 *
 * Las secciones que no se pueden abrir se muestran igual, atenuadas y con
 * candado, en vez de desaparecer. Ocultarlas hacía que un cajero creyera que el
 * sistema no tiene inventario ni reportes, en lugar de entender que le falta
 * permiso; pasó de verdad. No es un dato sensible —el control de acceso está en
 * el servidor, no en el menú— y ahorra la pregunta de «¿dónde está X?».
 *
 * **Un módulo que el plan no incluye se trata igual** (RN-49), por la misma
 * razón y por una más: un «Contabilidad 🔒» en el menú es lo único que le dice
 * al dueño que el producto la tiene. Escondiéndola, el módulo que se quiere
 * vender es invisible justo para quien lo compraría.
 */
export function visibleGroups(
	role: Role,
	modules?: Modules | null
): (NavGroup & { items: ResolvedItem[] })[] {
	return nav()
		.map((group) => ({
			...group,
			items: group.items.map((item) => ({
				...item,
				locked:
					Boolean(item.roles && !item.roles.includes(role)) ||
					Boolean(item.module && modules?.[item.module] !== true)
			}))
		}))
		.filter((group) => group.items.length > 0);
}

/**
 * Título de la pestaña y encabezado, resuelto por la ruta activa.
 *
 * «VentaSys» no se traduce: es el nombre del producto.
 */
export function titleFor(pathname: string): string {
	for (const group of nav()) {
		for (const item of group.items) {
			if (pathname === item.href || pathname.startsWith(`${item.href}/`)) return item.label;
		}
	}
	return 'VentaSys';
}
