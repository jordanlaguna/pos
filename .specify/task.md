# VentaSys — Tareas

> El trabajo de [spec.md](spec.md) según el plan de [plan.md](plan.md), en orden
> de ejecución. `RF-n` y `RN-n` remiten al spec.
>
> **Cómo se usa.** Se marca `[x]` al terminar, no al empezar. Una tarea está
> terminada cuando su verificación pasa, no cuando el código compila. Lo que
> importe para quien retome va a `progress.json`; este archivo es la lista de
> trabajo, no el registro histórico.
>
> Actualizado: 2026-08-16

---

## F0 · Reestructuración del repositorio — ✅ terminada 2026-08-16

Sin cambios de comportamiento. Primero, para no escribir dos veces lo que sigue.

- [x] **T-001** Renombrar `web/` → `frontend/`.
- [x] **T-002** Crear `backend/` con la **aplicación completa** desde
      `deploy/app/` (56 archivos), sin `.env` ni `__pycache__`. No es el
      contenido de `backend-patch/`: le faltarían 17 archivos y no arranca
      (plan §2).
- [x] **T-003** Mover a `backend/`: `requirements.txt`, `migration.sql`, y los
      archivos de Docker **en la raíz**, no en un subdirectorio: ahora que
      `backend/` es la aplicación completa, `docker compose up` corre ahí mismo
      y `deploy/` deja de tener razón de ser.
- [x] **T-004** Borrar `backend-patch/`, el clon `backend/` original,
      `csharp-original/` y `docker/`.
- [x] **T-005** Reescribir `backend/README.md`: de «cómo aplicar el patch» a
      «cómo correr el backend», conservando la sección de los defectos
      corregidos —explica por qué el código es como es.
- [x] **T-006** Actualizar rutas en `CLAUDE.md`, `README.md`, `progress.json`,
      `.gitignore` y los agentes de `.claude/agents/`.
- [x] **T-007** Verificar que no quede ninguna referencia a `web/` ni a
      `backend-patch` en todo el árbol.
- [x] **T-008** Levantar el sistema completo y comprobar que funciona igual:
      login, venta, caja, factura. `cd frontend && npm run check` en 0/0.

**Fuera de guion, durante la verificación:**

- [x] **T-009** `name: ventasys` y `ventasys_db_data` en el compose. Sin eso el
      nombre del volumen sale del nombre de la carpeta, y esta misma
      reestructuración habría dejado a MySQL arrancando contra una base vacía.
- [x] **T-010** Defecto 11: `app/services/__inti__.py` (la `t` y la `i`
      cambiadas) y `app/utils/` sin `__init__.py`. Funcionaba por los paquetes de
      espacio de nombres de Python 3.

**Queda de esta fase:** `deploy/` todavía existe. Tiene el `.env` real y el stack
en marcha usa su volumen `deploy_db_data`. Se borra cuando se migre el volumen a
`ventasys_db_data` o se acepte volver a sembrar.

---

## F1 · Arquitectura limpia y pruebas

Va antes que todo lo demás. Lo que sigue toca dinero, existencias y aislamiento
entre compañías; sin pruebas que fijen el comportamiento actual, no hay forma de
saber si un cambio rompió algo. Y F2 mete el filtro por compañía justo en la
capa de persistencia que esta fase crea.

**Orden interno obligatorio: primero las pruebas, después mover el código.**
Reorganizar por capas es mover mucho sin cambiar comportamiento, que es
exactamente donde se cuelan los errores silenciosos.

### Infraestructura de pruebas

- [ ] **T-101** pytest + pytest-cov en `backend/`, con `pyproject.toml`:
      `fail_under = 100` sobre `app/domain/*` y `app/application/*`. RNF-6.
- [ ] **T-102** Vitest en `frontend/`, con umbrales al 100 % sobre
      `src/lib/domain/**` y `src/lib/application/**`. RNF-6.
- [ ] **T-103** Llevar al repositorio las pruebas de punta a punta con
      Playwright. Hoy viven en el scratchpad de cada sesión y se pierden.
      Absorbe la vieja T-901.
- [ ] **T-104** **Pruebas de caracterización** de los invariantes de
      `progress.json`: venta 3×1450 → 4 915,50; arroz+café → 6 441,00; arqueo
      50 000 + 4 915,50 − 1 638,50 = 53 277,00; cierre contando 53 000 → −277,00;
      devolución 1 638,50; entrada XML 79 800; entrada CSV 69 080. Dejan de
      comprobarse a mano. **Sin esto no se mueve una línea de código.**

### Capas del backend

- [ ] **T-105** Extraer `app/domain/`: entidades, objetos de valor (`Money`,
      `TaxRate`, `Barcode`) y reglas puras —totales, arqueo, validez de
      devolución—. Es código puro: sale sin romper nada. RN-18.
- [ ] **T-106** Definir `app/application/ports/`: `SaleRepository`,
      `ProductRepository`, `CashRepository`, `Clock`, `PasswordHasher`,
      `TokenIssuer`.
- [ ] **T-107** Puerto `Clock` y erradicar `datetime.now()` de dominio y casos
      de uso. Es el defecto 9 vuelto restricción estructural. RN-19.
- [ ] **T-108** Mover los casos de uso a `app/application/use_cases/`, dejando
      los `crud_*` como adaptadores hasta que queden vacíos.
- [ ] **T-109** `app/infrastructure/persistence/`: modelos SQLAlchemy y
      repositorios que implementan los puertos. `security/` y `external/` con lo
      suyo.
- [ ] **T-110** Adelgazar los routers a `interfaces/http/`: traducir HTTP,
      llamar al caso de uso, devolver. Sin decisiones de negocio.

### Capas del frontend

- [ ] **T-111** Reorganizar `src/lib/` en `domain/`, `application/`,
      `infrastructure/` y `ui/`. `money.ts` y las reglas del carrito quedan
      puras: sin Svelte, sin `fetch`, sin `$state`.
- [ ] **T-112** Dejar `load` y `actions` como transporte: leer, invocar el caso
      de uso, devolver.

### Idioma del código

- [ ] **T-113** Pasar a inglés los identificadores en español que metí en
      `settings.ts`, la pantalla de configuración y los componentes de
      documento: `negocio` → `business`, `moneda` → `currency`, `impuesto` →
      `tax`, `documento` → `document`, `plantilla` → `template`, `apariencia` →
      `appearance`, `electronica` → `eInvoicing`. Los textos de la interfaz
      **no** se tocan: siguen en español. RN-21, RN-22.

### Verificación — sin esto la fase no está terminada

- [ ] **T-114** Guion de comprobación de capas, corriendo en la build: el
      dominio no importa nada externo, los casos de uso no importan SQLAlchemy
      ni HTTP, el dominio del frontend no importa Svelte ni `fetch`. Cualquier
      resultado es un fallo. RN-18.
- [ ] **T-115** Cobertura al 100 % en dominio y aplicación de ambos lados, con
      la build cayéndose por debajo. Comprobarlo borrando una prueba a
      propósito y viendo que falla.
- [ ] **T-116** Las pruebas de caracterización de T-104 siguen pasando después
      de mover todo. Es el único criterio que dice que el refactor salió bien.

---

## F2 · Multiempresa

La fase de la que dependen todas las demás.

### Base de datos

- [ ] **T-201** Migración: `plans`, `companies` (UNIQUE afiliado+compañía),
      `branches`, `terminals`, `audit_log` (plan §3.1).
- [ ] **T-202** Migración: `company_id` en las 14 tablas de negocio, con índice,
      y los UNIQUE existentes convertidos en compuestos (plan §3.2). RF-3.
- [ ] **T-203** Migración de datos: plan «Comercio», compañía (1,1) activa,
      `UPDATE … SET company_id = 1` en todo, sucursal `001` y terminal `00001`.
      Después, quitar el `DEFAULT 1` de las columnas. RF-4, RN-13.
- [ ] **T-204** `settings` deja de ser una fila: `company_id` UNIQUE, una por
      compañía.
- [ ] **T-205** Probar la migración contra una copia **con datos**, no sobre
      base nueva. Es un pendiente viejo de `progress.json` y acá se cobra.

### Backend

- [ ] **T-206** `app/utils/tenancy.py`: `ContextVar`, `TenantMixin` y el
      `do_orm_execute` con `with_loader_criteria` (plan §3.3).
- [ ] **T-207** Que los modelos de negocio hereden `TenantMixin`.
- [ ] **T-208** `company_id` dentro del JWT; `get_current_user` lo devuelve y
      una dependencia lo pone en el `ContextVar`. Ningún endpoint lo acepta
      como parámetro. RF-2.
- [ ] **T-209** Filtro **explícito** por compañía en `crud_report.py` y en todo
      UPDATE/DELETE masivo: el filtro automático no los cubre (plan §3.3).
- [ ] **T-210** `crud_sale`, `crud_cash` y `crud_stock_entry` sellan
      `branch_id` y `terminal_id` en cada registro. RN-14.

### Frontend

- [ ] **T-211** La sesión lleva compañía y sucursal/terminal; se muestran en el
      menú, junto al usuario.
- [ ] **T-212** Revisar cada `load` y cada acción: ninguna manda `company_id`.

### Verificación — sin esto la fase no está terminada

- [ ] **T-213** Semilla de dos compañías con datos distintos.
- [ ] **T-214** Batería que recorre **todos** los endpoints pidiendo, con el
      token de A, los identificadores de B. Toda respuesta debe ser **404**, no
      403: un 403 confirmaría que el recurso existe. RNF-1.
- [ ] **T-215** Recalcular los invariantes de `progress.json` y confirmar que
      las cifras verificadas siguen dando igual.

---

## F3 · Soporte y suscripción

- [ ] **T-301** Rol `soporte` (usuario sin compañía) y `requireSoporte` en el
      servidor.
- [ ] **T-302** Grupo de rutas `/admin`, separado de `(app)`. Un usuario de
      compañía recibe 403; soporte recibe 403 en las pantallas del POS.
- [ ] **T-303** Listado de compañías con afiliado, estado, plan, vencimiento y
      uso. RF-5.
- [ ] **T-304** Alta de compañía: datos, plan, administrador inicial. Deja
      creadas su sucursal, su terminal y su configuración por omisión. RF-6.
- [ ] **T-305** Cambiar estado y fecha de vencimiento. RF-7.
- [ ] **T-306** *Entrar como*: token de la compañía destino, vencimiento corto,
      motivo obligatorio, franja permanente en pantalla. RF-8, RN-4.
- [ ] **T-307** Bitácora: se escribe en toda acción de soporte y se consulta
      desde el panel. RF-9.
- [ ] **T-308** Aplicar el estado de suscripción en cada carga de pantalla, con
      la gracia de 7 días y el aviso previo. RF-10, RF-11, RN-1, RN-2.
- [ ] **T-309** Validar los límites del plan al crear terminales, sucursales y
      usuarios. RF-12.
- [ ] **T-310** Comprobar de punta a punta: alta de compañía nueva, login de su
      administrador, venta, y que no ve nada de la otra compañía.

---

## F4 · Categorías de dos niveles

- [ ] **T-401** Migración: `parent_id`, `orden`, `activa` en `categories`;
      UNIQUE (company_id, parent_id, nombre).
- [ ] **T-402** Validación de profundidad en el servicio: una categoría con
      padre no puede ser madre. RN-5.
- [ ] **T-403** No borrar con productos ni con hijas: desactivar. RN-7.
- [ ] **T-404** CRUD de categorías y subcategorías, con reordenamiento. RF-13.
- [ ] **T-405** Mover una subcategoría de raíz sin tocar sus productos. RF-14.
- [ ] **T-406** Ficha de producto: elegir categoría y subcategoría. RN-6.
- [ ] **T-407** Grilla de ventas: raíces como pestañas, subcategorías como
      fichas debajo. RF-15.
- [ ] **T-408** Filtro por los dos niveles en inventario. RF-16.
- [ ] **T-409** Verificar con dos catálogos reales: un súper (Bebidas →
      Cervezas, Gaseosas) y un repuestero (Yamaha → Llantas, Focos).

---

## F5 · Impuesto por producto y CABYS

### Catálogo

- [ ] **T-501** Tabla `cabys_cache` (global, no por compañía).
- [ ] **T-502** Proxy `GET /cabys/buscar?q=` y `GET /cabys/{codigo}` en FastAPI.
      Contemplar que Hacienda devuelve **objeto** en la búsqueda por texto y
      **lista** en la búsqueda por código (plan §6.1).
- [ ] **T-503** Sin internet: responder desde la caché y decirlo. RNF-4.
- [ ] **T-504** Buscador de CABYS en la ficha del producto. RF-17.
- [ ] **T-505** Al asignar, copiar la tarifa; si el usuario la cambia, avisar
      que difiere de la oficial. RF-18, RN-11.
- [ ] **T-506** Asignación en lote para catálogos ya cargados. RF-20.

### Impuesto por línea

- [ ] **T-507** Migración: `cabys_code`, `tax_rate`, `unidad_medida` en
      `products`. La tasa de Configuración pasa a ser el valor por omisión de un
      producto nuevo. RN-9.
- [ ] **T-508** `computeTotals` recibe líneas con su tarifa y devuelve
      `porTarifa` (plan §6.3). RN-10.
- [ ] **T-509** Propagar el cambio: carrito, `crud_sale`, `crud_return`,
      reportes, mock. Las ventas viejas conservan su impuesto. RN-12.
- [ ] **T-510** Desglose por tarifa en las tres plantillas de documento, solo
      cuando hay más de una. RF-21.
- [ ] **T-511** Verificar con una venta que mezcle 13 %, 2 % y 0 %: que cuadre,
      que desglose y que su devolución reembolse lo que se cobró.

---

## F6 · Preparación de factura electrónica

- [ ] **T-601** Tabla `fe_credentials` (plan §7.1).
- [ ] **T-602** Cifrado AES-256-GCM con `FE_CRYPTO_KEY` y el `company_id` como
      dato asociado: un registro copiado a otra compañía no descifra.
- [ ] **T-603** Subida del `.p12` y el PIN, browser → BFF → FastAPI. RF-22.
- [ ] **T-604** `GET` devuelve solo `{configurado, nombre_archivo, vence_el,
      subido_el}`. **No existe** endpoint que devuelva el archivo o el PIN.
      RF-23, RN-16.
- [ ] **T-605** Reemplazar y quitar el certificado. RF-24.
- [ ] **T-606** Leer el vencimiento del propio `.p12` al subirlo, y avisar 30
      días antes.
- [ ] **T-607** Consulta de actividad económica contra
      `GET /fe/ae?identificacion=` desde Configuración. RF-25.
- [ ] **T-608** Administración de sucursales y terminales con sus códigos de 3 y
      5 dígitos. RF-26, RN-15.
- [ ] **T-609** Comprobar que el PIN no aparece en respuestas, ni en bitácora,
      ni en trazas de error. Buscarlo a propósito.

---

## F7 · Emisión

Bloqueada hasta decidir la ruta: implementación directa o proveedor autorizado
(plan §7.2). Lo que se construya en F5 y F6 sirve para las dos.

En `docs/hacienda/costa-rica/` están los esquemas XSD 4.4, comprobantes reales
de ejemplo y la normativa de PIN y llaves. La ruta directa deja de depender de
deducir el formato.

- [ ] **T-701** Decidir la ruta.
- [ ] **T-702** Leer los XSD 4.4 y los 9 comprobantes de ejemplo, y contrastar
      el modelo de datos de F5/F6 contra los campos obligatorios reales. Es lo
      que dice si falta algo antes de escribir código.
- [ ] **T-703** Definir la interfaz `EmisorFE` y dejar la implementación detrás.

---

## Transversal

- [x] **T-901** ~~Llevar las pruebas de punta a punta al repositorio.~~ Absorbida
      por **T-103** en F1, donde le corresponde.
- [ ] **T-902** Cambiar las contraseñas de demo antes de producción.
- [ ] **T-903** Resolver cómo se concede el primer administrador de una
      compañía. Con el panel de soporte (F3) deja de ser un callejón sin salida,
      pero hay que dejarlo escrito.
- [ ] **T-904** Paginación en el servidor para facturas y productos. Con varias
      compañías y años de operación, traer todo deja de ser viable.
- [ ] **T-905** Probar la impresión del tiquete en una impresora térmica real de
      80 mm. Se imprime por `@media print` del navegador y nunca se probó con
      hardware.
- [ ] **T-906** Probar la impresión de las dos facturas de página completa en
      papel. Se verificó emulando `media print` —los controles se ocultan y las
      franjas conservan el color—, pero no se comprobó que quepan en una carta
      sin cortar el pie.
- [ ] **T-907** Verificar `SELECT … FOR UPDATE` bajo concurrencia real: dos
      cajas vendiendo la última unidad a la vez. El bloqueo está implementado y
      nunca se probó con dos clientes simultáneos.
- [ ] **T-908** Probar el lector de XML con facturas reales de varios
      proveedores. Se verificó con una v4.3 construida a mano; cada emisor llena
      `CodigoComercial`, `Codigo` y `CodigoCABYS` de forma distinta. En
      `docs/hacienda/costa-rica/normativa/protocolos/` hay 9 comprobantes reales
      para empezar.
- [ ] **T-909** Probar el PDF que genera el backend con reportlab.
      `GET /sales/pdf/{id}` está proxeado desde el POS pero nunca se abrió el
      archivo resultante.
- [ ] **T-910** Confirmar si existe el `postsys.sql` original de la VM. El
      compose original lo montaba como script de inicio y nunca apareció. Si
      tiene datos reales, hay que cargarlos en `backend/initdb/`.
