# VentaSys — Tareas

> El trabajo de [spec.md](spec.md) según el plan de [plan.md](plan.md), en orden
> de ejecución. `RF-n` y `RN-n` remiten al spec.
>
> **Cómo se usa.** Se marca `[x]` al terminar, no al empezar. Una tarea está
> terminada cuando su verificación pasa, no cuando el código compila. Lo que
> importe para quien retome va a `progress.json`; este archivo es la lista de
> trabajo, no el registro histórico.
>
> Actualizado: 2026-10-03

---

## QA · 2026-10-03 — va antes que las fases que faltan

> Lo que el usuario encontró probando, en `fix_y_feat_qa.txt`. Primero los
> arreglos, después los análisis contra la KB de GeneXus
> (`KbSws20_actualizado.xpz`) y T-616. Decidido con el usuario el 2026-10-03:
> **el paquete decide** los módulos (RN-49 sigue), el paquete con compras
> lleva clientes y usuarios, el producto sin tarifa propia paga **el 13 % de
> ley**, y las listas desplegables son **un componente de Svelte** sobre la
> lista nativa.

- [x] **QA-01** Paquetes de módulos. Cada sección del POS es un módulo
      —ventas, caja, facturas, devoluciones, reportes, inventario, compras,
      proveedores, contabilidad, planilla, clientes, usuarios— y
      Configuración no, porque sin ella no hay negocio. Cuatro paquetes como
      planes: **Restaurante** (ventas, facturas, clientes, usuarios),
      **Comercio** (más caja, devoluciones, inventario y proveedores),
      **Comercio con compras** (más reportes y compras) y **Completo** (todo).
      El alta muestra los módulos del paquete elegido. Los planes que ya
      existen conservan lo que tenían. RN-49 a RN-51.

      **Verificación:** una compañía en Restaurante ve Caja con candado y no
      puede abrirla, ni escribir por el API; en Completo ve todo; cambiarle el
      paquete cambia el menú en la siguiente petición.

      **Hecha el 2026-10-03.** Migración 022 y `domain/modules.py` (`MODULES`,
      `BASE`, `PACKAGES`); `require_module` en cada escritura; proveedores es
      su propio módulo y tiene su entrada en el menú; la entrada de inventario
      pide inventario, proveedores si nombra uno y compras si es a crédito;
      anular es de facturas. El «Comercio» que ya existía en la base de
      desarrollo conserva todo: se ajusta desde Planes. Precio y límites de los
      paquetes: **los carga soporte a mano** (decidido con el usuario el
      2026-10-03), así que nacen en 0 y 1/3/10 y no quedan pendientes. Pruebas: `test_modules.py`,
      `test_soporte.py`, `navigation.test.ts` y `soporte.spec.ts`.

- [x] **QA-02** El selector de idioma en el panel de soporte, como en el POS.

      **Verificación:** soporte elige inglés y el panel queda en inglés.

- [x] **QA-03** Planes muestra las compañías de cada plan y permite pasarlas a
      otro, porque el plan de una compañía cambia con el tiempo.

      **Verificación:** pasar una compañía de un plan a otro desde Planes la
      mueve de tarjeta y queda en la bitácora.

- [x] **QA-04** El alta propone el siguiente afiliado libre con su compañía 1,
      y si se escribe un afiliado que ya existe, su siguiente compañía.

      **Verificación:** con el afiliado 1 y su compañía 1, el alta propone el
      afiliado 2; al escribir 1, propone la compañía 2.

- [x] **QA-05** Quitar el impuesto de «Moneda e impuesto». La tarifa la da el
      CABYS de cada producto y, sin ella, el 13 % de ley, que ya no se
      configura. RN-9.

      **Verificación:** la pestaña no tiene el campo; un producto sin tarifa
      se cobra al 13 %; una venta, una devolución y una nota cuadran igual.

- [x] **QA-06** Los botones del certificado y de las credenciales usaban
      `btn-secondary`, una clase que no existe, y salían sin estilo; y un
      componente `Select` de Svelte para que todas las listas desplegables se
      vean iguales en tema claro y oscuro.

      **Verificación:** ninguna `btn-secondary` en el árbol; las listas de
      Configuración y del panel usan `Select`.

- [x] **QA-07** **T-616**: el último consecutivo por tipo de comprobante, que
      solo sube y queda en bitácora (en F6, abajo).

- [x] **QA-08** Analizar Proveedores en la KB y escribirlo como fase nueva.
      **Hecha:** es **F13**, abajo, con lo que trae la KB, lo que falta y lo
      que hay que decidir.

- [x] **QA-09** Analizar Compras en la KB y profundizar F10 con lo que falte.
      **Hecha:** es **F14**, abajo.

- [x] **QA-10** Analizar Inventario en la KB y anotar lo que valga la pena.
      **Hecha:** es **F15**, abajo.

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

## F1 · Arquitectura limpia y pruebas — ✅ terminada 2026-08-16

Quedan dos flecos anotados al pie, ninguno bloquea F2.

Va antes que todo lo demás. Lo que sigue toca dinero, existencias y aislamiento
entre compañías; sin pruebas que fijen el comportamiento actual, no hay forma de
saber si un cambio rompió algo. Y F2 mete el filtro por compañía justo en la
capa de persistencia que esta fase crea.

**Orden interno obligatorio: primero las pruebas, después mover el código.**
Reorganizar por capas es mover mucho sin cambiar comportamiento, que es
exactamente donde se cuelan los errores silenciosos.

### Infraestructura de pruebas

- [x] **T-101** pytest + pytest-cov en `backend/`, con `pyproject.toml`:
      `fail_under = 100` sobre `app/domain/*` y `app/application/*`. RNF-6.
      Hecho 2026-08-16. Se agregó `requirements-dev.txt` y
      `docker-compose.test.yml`: pila desechable en el 8002, con la base en
      memoria y nombre de proyecto propio, para que las pruebas no escriban
      nunca en la base de trabajo.
- [x] **T-102** Vitest en `frontend/`, con umbrales al 100 % sobre
      `src/lib/domain/**` y `src/lib/application/**`. RNF-6. Hecho 2026-08-16.
      Mientras esas carpetas no existan (las crea T-111), el umbral cubre por
      nombre `money.ts`, `color.ts`, `settings.ts` y `documents.ts`, que son las
      reglas puras de hoy: 103 pruebas, 100 % de líneas, ramas y funciones.
- [x] **T-103** Llevar al repositorio las pruebas de punta a punta con
      Playwright. Hoy viven en el scratchpad de cada sesión y se pierden.
      Absorbe la vieja T-901. Hecho 2026-08-16: `frontend/tests/e2e/`, contra
      `POS_MOCK=1` para que corran sin Docker. 9 pruebas.
- [x] **T-104** **Pruebas de caracterización** de los invariantes de
      `progress.json`: venta 3×1450 → 4 915,50; arroz+café → 6 441,00; arqueo
      50 000 + 4 915,50 − 1 638,50 = 53 277,00; cierre contando 53 000 → −277,00;
      devolución 1 638,50. Hecho 2026-08-16 en
      `backend/tests/test_characterization.py`, 12 pruebas contra FastAPI y
      MySQL de verdad. Encontraron el defecto 14.
- [x] **T-104b** Entradas de mercadería: XML de Hacienda → 42 unidades y
      79 800, y CSV → 70 unidades y 69 080. Hecho 2026-08-16, y **no con
      Playwright**: `parseHaciendaXml` recibe una cadena y `parseSpreadsheet` un
      buffer, así que se prueban directo con Vitest —más rápido y más preciso
      que subir un archivo por el navegador—. Las facturas de prueba viven en
      `frontend/tests/fixtures/`.
      El CSV original de aquella comprobación se había perdido; el nuevo
      reproduce las cifras exactas conservando todo lo que hacía difícil el
      caso: punto y coma, encabezados con otro nombre y otro orden, `1.100,00`,
      una fila vacía en medio y una cantidad en cero.

### Capas del backend

- [x] **T-105** Extraer `app/domain/`: entidades, objetos de valor (`Money`,
      `TaxRate`, `Barcode`) y reglas puras —totales, arqueo, validez de
      devolución—. Es código puro: sale sin romper nada. RN-18.
      Hecho 2026-08-16: ocho módulos (`money`, `tax`, `barcode`, `sale`, `cash`,
      `returns`, `errors`), 152 pruebas, 100 % de líneas y ramas.
- [x] **T-105b** Decidir el modo de redondeo y unificarlo. Hecho 2026-08-16:
      **`ROUND_HALF_UP`**, el redondeo comercial, alejándose del cero. Es lo que
      hacía el WinForms con `.ToString("0.00")` y lo que ya hacía el POS. El
      backend usaba el bancario por ser el valor por omisión de Python, que
      nadie eligió. De paso se corrigió `round2` del POS, que con
      `Math.round` redondeaba los negativos hacia +∞: `-1.005` daba `-1.00`
      donde el servidor decía `-1.01`.
      Cotejados 1 208 montos representativos entre las dos implementaciones: la
      diferencia máxima es de **un céntimo**, y solo cuando el binario cae justo
      por debajo de un empate a medio céntimo. Eso es inherente —el POS calcula
      en coma flotante y el servidor en decimal exacto— y es de donde sale la
      tolerancia de T-108b.
- [x] **T-106** Definir `app/application/ports/`: `SaleRepository`,
      `ProductRepository`, `CashRepository`, `Clock`, `PasswordHasher`,
      `TokenIssuer`. Hecho 2026-08-16, más `ReturnRepository` y `UnitOfWork`.
      Son `Protocol`: cumplirlos no exige heredar, así que la dependencia sigue
      apuntando hacia adentro. Con prueba de contrato.
- [x] **T-107** Puerto `Clock` y erradicar `datetime.now()` de dominio y casos
      de uso. Es el defecto 9 vuelto restricción estructural. RN-19.
      Hecho 2026-08-16: `SystemClock` y `FixedClock`. `app/utils/clock.py` queda
      como puente mientras los `crud_*` no reciban el reloj por parámetro.
- [x] **T-108** Mover los casos de uso a `app/application/use_cases/`, dejando
      los `crud_*` como adaptadores hasta que queden vacíos.
      Hecho 2026-08-16 para **los cuatro flujos que tocan plata o
      inventario**: `register_sale.py`, `cash_session.py` (abrir, mover, cerrar
      y armar el arqueo), `register_return.py` y `stock_entry.py` (recibir y
      anular). Los cuatro `crud_*` son ya solo traducción de dominio a HTTP,
      con los mismos mensajes. `_sale_tax_rate` se borró: la regla vive en
      `TaxRate.of_sale`. Quedan los `crud_*` de catálogo, clientes y usuarios,
      que son ABM sin reglas de negocio y no ganan nada con la mudanza.
- [x] **T-108b** El servidor calcula la plata. Hecho 2026-08-16: recalcula
      subtotal, impuesto y total con los precios que acaba de leer y la tasa
      configurada, **guarda los suyos** y calcula también el vuelto. Lo que
      manda la caja solo se usa para comprobar que ambos ven lo mismo; si no
      cuadra, la venta no entra y el error dice las dos cifras.
      La tolerancia es de un céntimo por lo medido en T-105b, y no afloja nada:
      lo que se guarda es siempre el número del servidor. Se quitaron del router
      las comprobaciones de efectivo y vuelto, que se hacían contra el total del
      cliente —el número del que ya no se fía nadie—.
      El simulado hace lo mismo, que es regla del proyecto.
      Verificado contra el stack real: total alterado → 400, subtotal y
      impuesto que se compensan → 400, efectivo corto → 400, y en los tres casos
      cero filas escritas y el inventario intacto.
- [~] **T-109** `app/infrastructure/persistence/`: modelos SQLAlchemy y
      repositorios que implementan los puertos. `security/` y `external/` con lo
      suyo. Hechos los seis repositorios —producto, venta, devolución, caja,
      entradas de mercadería y configuración— más `SqlAlchemyUnitOfWork`.
      Faltan los adaptadores de `security/`: hoy `bcrypt` y `python-jose` se
      usan directo desde `utils/`, y los puertos `PasswordHasher` y
      `TokenIssuer` están definidos pero sin implementar detrás.
- [~] **T-110** Adelgazar los routers a `interfaces/http/`: traducir HTTP,
      llamar al caso de uso, devolver. Sin decisiones de negocio.
      **Los de plata ya no deciden nada**: la última regla que les quedaba —el
      número de factura único— se fue a `RegisterSale`. Lo que sigue en los
      routers son comprobaciones de **autorización** (un cajero no consulta la
      caja de otro), y esas sí pertenecen a la interfaz: dependen de quién hace
      la petición, no del negocio.
      Falta mover los archivos a `interfaces/http/` —hoy siguen en `router/`—
      y adelgazar los de catálogo, clientes y usuarios.

### Capas del frontend

- [x] **T-111** Reorganizar `src/lib/` en `domain/`, `application/`,
      `infrastructure/` y `ui/`. `money.ts` y las reglas del carrito quedan
      puras: sin Svelte, sin `fetch`, sin `$state`. Hecho 2026-08-16.
      `domain/` con plata, color, configuración, documentos, tipos y **carrito**;
      `application/` con la validación de formularios; `ui/` con componentes,
      almacenes y formato.
      **`server/` se queda con ese nombre y no pasa a `infrastructure/`**:
      SvelteKit trata `$lib/server` como especial e impide compilar si el
      cliente la importa. Es la misma frontera, verificada por el compilador en
      vez de por convención; renombrarla sería perderla.
      Del almacén del carrito salieron las reglas puras —cuánto se puede
      agregar contando lo apartado en las otras ventas, el número de factura y
      los montos sugeridos de efectivo—, que ahora se prueban sin Svelte.
- [x] **T-112** Dejar `load` y `actions` como transporte: leer, invocar el caso
      de uso, devolver. Hecho 2026-08-16: la decisión de cobrar se fue a
      `application/checkout.ts`, que es una función pura —recibe lo que pidió la
      caja, el catálogo y la tasa, y devuelve el cuerpo listo o el motivo del
      rechazo—. La acción bajó de 157 a 128 líneas y no calcula nada.
      `toLocalIso` se movió de `ui/format` a `domain/datetime`: es el formato en
      que las fechas viajan al backend, no formateo de pantalla, y la capa de
      aplicación no puede importar de `ui/`.

### Idioma del código

- [x] **T-113** Pasar a inglés los identificadores en español que metí en
      `settings.ts`, la pantalla de configuración y los componentes de
      documento: `negocio` → `business`, `moneda` → `currency`, `impuesto` →
      `tax`, `documento` → `document`, `plantilla` → `template`, `apariencia` →
      `appearance`, `electronica` → `eInvoicing`. Los textos de la interfaz
      **no** se tocan: siguen en español. RN-21, RN-22. Hecho 2026-08-16.
      No era solo renombrar: **esas palabras eran también las claves del JSON
      guardado** en `settings.data`. `mergeSettings` y `crud_settings.get_tax_rate`
      leen ahora las dos formas, así que una fila escrita antes del cambio se
      sigue entendiendo; sin eso, actualizar el sistema le habría borrado al
      dueño su moneda y su tasa de impuesto en silencio.
      Verificado contra el stack real: con `impuesto.tasa = 0.04` el servidor
      cobra 4 %, y con `tax.rate = 0.07` cobra 7 %.

### Verificación — sin esto la fase no está terminada

- [x] **T-114** Guion de comprobación de capas, corriendo en la build: el
      dominio no importa nada externo, los casos de uso no importan SQLAlchemy
      ni HTTP, el dominio del frontend no importa Svelte ni `fetch`. Cualquier
      resultado es un fallo. RN-18.
      Hecho 2026-08-16 en los dos lados, y como **prueba** y no como guion
      suelto: un guion que hay que acordarse de correr no protege nada.
      Backend (`tests/test_layers.py`): lee el árbol de sintaxis en vez de
      importar. Frontend (`src/lib/domain/layers.test.ts`): comprueba además que
      el dominio no use runas, `fetch` ni almacenamiento del navegador.
      Comprobados los dos metiendo una violación a propósito; los dos fallan
      nombrando archivo y línea.
      La comprobación del frontend descarta los comentarios antes de mirar: la
      primera versión marcaba `domain/cart.ts` porque su cabecera dice «sin
      `$state`», y una comprobación que salta con el comentario que documenta la
      regla no comprueba la regla.
- [x] **T-115** Cobertura al 100 % en dominio y aplicación de ambos lados, con
      la build cayéndose por debajo. Comprobarlo borrando una prueba a
      propósito y viendo que falla. Comprobado el 2026-08-16 en los dos:
      sin las pruebas de `color.ts`, `npm test` sale con código 1; sin la clase
      `TestMovimientos`, `pytest` sale con código 1 y señala `cash.py` líneas
      63-70.
- [x] **T-116** Las pruebas de caracterización de T-104 siguen pasando después
      de mover todo. Es el único criterio que dice que el refactor salió bien.
      Comprobado 2026-08-16 con el dominio, los cuatro casos de uso, los
      repositorios y las capas del frontend ya movidos: **17 de 17 en verde**
      contra FastAPI y MySQL de verdad.
      Se cerraron además los dos invariantes que seguían comprobándose a mano:
      `reportes_dia` con una prueba de caracterización nueva —midiendo
      diferencias y no totales, porque el reporte suma por fecha y arrastra lo
      de las otras pruebas— y `ventas_en_espera` con cuatro flujos de punta a
      punta. **Los 12 invariantes de `progress.json` tienen prueba
      automatizada.**

**Flecos de F1**, para hacer cuando estorben y no antes:

- **T-109** — faltan los adaptadores de `security/`. Hoy `bcrypt` y
  `python-jose` se usan directo desde `utils/`, y los puertos `PasswordHasher` y
  `TokenIssuer` están definidos pero sin implementación detrás. F2 toca el JWT
  para meterle la compañía: conviene hacerlo ahí, de un solo viaje.
- **T-110** — los routers ya no deciden nada de negocio, pero los archivos
  siguen en `app/router/` y no en `interfaces/http/`. Es mover carpetas; el
  valor ya está cobrado.

---

## F2 · Multiempresa — ✅ terminada 2026-08-16

La fase de la que dependen todas las demás. La base compartida quedó migrada con
los datos reales adentro, el aislamiento tiene batería propia y el POS entra por
el login de dos pasos.

### Decisiones que hay que tomar antes de escribir la migración

- [x] **T-216** ¿Un correo puede pertenecer a más de una compañía? **Sí**
      (2026-08-16). No con UNIQUE (company_id, email) —eso crea cuentas
      distintas que solo comparten el texto del correo— sino separando identidad
      de pertenencia: `users` queda con el correo único global y una contraseña,
      y `user_companies` guarda la membresía con su propio rol. RN-3, plan §3.1.
- [x] **T-217** ¿Cómo se respalda y se restaura **una** compañía? **Decidido**
      (2026-08-16); la herramienta es T-225. Se restaura solo lo que no está:
      `auto_increment` de MySQL nunca reutiliza un número, así que las filas de
      una compañía dada de baja dejan sus identificadores libres para siempre y
      la restauración los conserva tal cual, sin remapear nada —que es la parte
      que se hace mal—. El procedimiento recorre las doce tablas en orden de
      clave foránea con `WHERE company_id = N`; `users` se exporta **por correo
      y no por fila**, porque la identidad es global y puede estar compartida con
      otra compañía que sigue viva. Se niega a restaurar si ya existe alguna fila
      de esa compañía: falla cerrado en vez de mezclar. Plan §3.7.

### Base de datos

- [x] **T-201** Migración: `plans`, `companies` (UNIQUE afiliado+compañía),
      `branches`, `terminals`, `user_companies`, `audit_log` (plan §3.1). En
      `backend/migrations/002-multiempresa.sql`.
- [x] **T-202** `company_id` en las tablas de negocio, con índice y clave
      foránea, y los UNIQUE existentes convertidos en compuestos. RF-3.
      **Son doce, no catorce**: `users` y `persons` quedaron fuera por ser
      identidad (corrección explicada en plan §3.2).
- [x] **T-203** Migración de datos: plan «Comercio», compañía (1,1) activa,
      `DEFAULT 1` en el ALTER y quitado después, sucursal `001` y terminal
      `00001`. RF-4, RN-13.
- [x] **T-204** `settings` deja de ser una fila: `company_id` UNIQUE.
- [x] **T-204b** Columnas de idioma en la misma migración: `companies.locale`,
      `companies.document_locale` y `users.locale`. Plan §8.3.
- [x] **T-205** Probada contra una copia **con datos** (`posdb_mig`, las 38
      ventas reales) antes de tocar la base viva. Y comprobado además que una
      instalación **nueva** —`create_all` sobre base vacía— queda con el mismo
      esquema: 155 de 155 columnas idénticas. Las cinco que diferían al principio
      eran tipos del modelo que no coincidían con la migración, y se corrigieron.

### Backend

- [x] **T-206** `app/utils/tenancy.py`: `ContextVar`, `TenantMixin` y el
      `do_orm_execute` con `with_loader_criteria`. **Falla cerrado**. RNF-1.
      Verificado en `tests/test_tenancy.py`: sin compañía levanta `SinCompania`,
      con compañía devuelve solo las suyas y `sin_filtro()` devuelve las de
      todas. 13 pruebas, sin Docker.
- [x] **T-206b** El mismo mecanismo **sella la escritura**: un `before_flush` le
      pone la compañía a toda fila nueva de negocio. No estaba en el plan y hacía
      falta: leer sin `WHERE` era imposible, pero escribir sin `company_id`
      dependía de que quince sitios se acordaran. Plan §3.3.
- [x] **T-207** Los catorce modelos de negocio heredan `TenantMixin`: las doce
      tablas más `branches` y `terminals`.
- [x] **T-208** `cid`, `bid`, `tid` y `rol` dentro del JWT; una dependencia
      **asíncrona** los pone en los `ContextVar`. Ningún endpoint los acepta como
      parámetro. RF-2.
- [x] **T-209** Filtro explícito por compañía en las siete consultas de
      `crud_report.py`, con su prueba: el automático no cubre el SQL agregado.
- [x] **T-210** Las escrituras sellan `branch_id` y `terminal_id` desde el
      token, en los cuatro repositorios que registran hechos. RN-14.

### Identidad y membresía

- [x] **T-218** Tabla `user_companies`, migración de los usuarios actuales con
      el rol que ya tenían, y `users.role` eliminada. RN-3.
- [x] **T-219** `POST /auth/login` devuelve token de tránsito (10 min) con dos o
      más compañías disponibles, y sesión directa con una sola. RN-25, plan §3.5.
- [x] **T-220** `GET /auth/companies` y `POST /auth/company`. Verifican membresía
      activa y estado de suscripción; queda en bitácora. RF-27. **Aceptan también
      un token de sesión**, no solo el de tránsito: es lo que permite cambiar de
      compañía sin volver a escribir la contraseña (RF-28), y un token de sesión
      prueba la identidad igual de bien que el otro.
- [x] **T-221** Toda ruta de negocio rechaza con 401 un token sin `cid`.
      Verificado sobre siete rutas en `test_aislamiento.py`. RN-26.
- [x] **T-226** `POST /users/membership`: dar de alta en esta compañía a alguien
      que ya tiene cuenta. Sin esto el caso del contador no se puede armar desde
      el POS. Apareció al escribir la semilla de dos compañías.

### Frontend

- [x] **T-211** La sesión lleva compañía, sucursal y terminal, y se muestran en
      el menú. «Cambiar de compañía» solo aparece si hay a dónde ir.
- [x] **T-212** Revisado: ningún `load` ni acción manda `company_id`. Ya era
      cierto antes de F2; ahora está comprobado.
- [x] **T-222** Pantalla `/compania`, con las bloqueadas visibles y su motivo.
      Una ruta del POS con token de tránsito redirige acá, no al login. RF-27.
- [x] **T-223** «Cambiar de compañía» re-emite el token y limpia carrito y
      ventas en espera antes de enviar. RF-28, RN-27. Verificado en
      `tests/e2e/cambio-de-compania.spec.ts` con la prueba que pedía la tarea:
      dos unidades en el carrito, cambio a la otra compañía, y la pestaña vuelve
      a estar vacía. Se pudo ejecutar cuando T-228 le dio dos compañías al modo
      simulado.
- [x] **T-224** La caché de configuración pasó a `Map` por compañía y
      `invalidateSettings` recibe cuál. Plan §3.6. Verificado en
      `src/lib/server/settings.test.ts`: dos sesiones de compañías distintas
      contra el mismo proceso, cada una con su marca, y contando las llamadas
      para distinguir «devolvió lo correcto» de «devolvió lo correcto porque
      volvió a preguntar». **Comprobado que se pone rojo**: volviendo a la caché
      única, 4 de las 6 fallan.
- [x] **T-227** El modo simulado se puso al día: los tres endpoints de `/auth`,
      `/users/membership`, y su token pasó a tener **forma de JWT** para que
      `lib/server/auth.ts` lea el payload por el mismo camino en los dos modos.

### Verificación — sin esto la fase no está terminada

- [x] **T-213** Dos compañías con datos propios y una contadora con membresía en
      ambas —administradora en una, cajera en la otra—, montadas con el mismo
      `bootstrap.py` que se usaría en una instalación real.
- [x] **T-214** `backend/tests/test_aislamiento.py`: 32 pruebas. Con el token de
      A, pedir los identificadores de B da 404 en las diez rutas por
      identificador; las listas no se mezclan, los reportes no suman y la
      configuración no se pisa. **Comprobado que se pone roja**: desactivando el
      filtro, 14 de las 32 fallan. Una prueba más avisa si aparece una ruta nueva
      sin cubrir ni declarar. RNF-1.
- [x] **T-215** Invariantes recalculados sobre la base viva ya migrada: 38 ventas
      por ₡360.413,50, 27 productos, 4 usuarios, 4 membresías.

### Respaldo, invitaciones y modo simulado

- [x] **T-225** `backend/company_dump.py`: exportar, borrar y restaurar **una**
      compañía, según lo decidido en T-217. Verificado en
      `tests/test_respaldo_compania.py` con la prueba que pedía la tarea: se
      exporta una compañía, se borra, se restaura, y la otra queda idéntica
      —producto por producto, venta por venta, incluida su configuración—.
      También se comprueba que restaurar encima de datos existentes se niega, y
      que sin la confirmación exacta no borra nada.
- [x] **T-228** El modo simulado tiene **dos** compañías con datos separados. El
      almacén pasó a tener una raíz global —identidad y membresías— y una porción
      por compañía; `getDb(compañía)` devuelve una vista fusionada, así que los
      61 accesos del manejador siguen escritos igual. La segunda nace vacía, que
      es lo que de verdad pasa al dar de alta una. Desbloqueó T-223.
- [x] **T-229** La membresía se acepta, no se impone. `POST /users/membership`
      deja la membresía **pendiente** y no autoriza nada hasta que la persona
      responda; `POST /auth/invitation` acepta o rechaza. Una cuenta que el
      administrador **crea** nace aceptada —no hay a quién preguntarle— y
      `bootstrap.py` también, o una instalación nueva quedaría sin poder entrar.
      Migración `003-invitaciones.sql`. 8 pruebas en `test_invitaciones.py`.

### Lo que quedó abierto

- [ ] **T-230** `Query.count()` **no** está cubierto por el filtro automático:
      envuelve la consulta en `SELECT count(*) FROM (…)` y el criterio no entra,
      así que `db.query(Product).count()` cuenta las de todas las compañías.
      Hoy no hay ninguna fuga —el único `.count()` del backend es sobre
      `user_companies` y lleva su filtro— y un guardián en `test_tenancy.py`
      tumba `pytest` si alguien escribe uno sin `company_id` a la vista. Queda
      abierto por si conviene cubrirlo de raíz en vez de vigilarlo.

---

## F3 · Soporte y suscripción — ✅ terminada 2026-08-23

> Las diez tareas, de T-301 a T-310. VentaSys pasó de ser un POS multiempresa a
> un producto que se administra: se dan de alta clientes, se les cambia la
> suscripción, se entra a diagnosticar y todo queda en bitácora. El diseño está
> en [plan.md §4](plan.md); acá queda lo que se aprendió haciéndolo.
>
> **Migración 004** (`users.is_support` y el índice de la bitácora por fecha).

- [x] **T-301** Rol `soporte` (usuario sin compañía) y `requireSoporte` en el
      servidor.

      **Hecho el 2026-08-23.** La marca es una columna, `users.is_support`, y no
      la ausencia de membresías como decía el plan: quien rechaza la única
      invitación que tenía también se queda sin ninguna, y quedaría
      administrando el producto por descarte. **La ausencia de algo no puede ser
      un permiso.**

      Su token no lleva `cid`, y eso es todo el diseño: el filtro de
      `tenancy.py` le hace fallar cerrado cualquier consulta a una tabla de
      negocio, así que para ver los datos de un cliente **tiene que** entrar
      como esa compañía —que es lo que pide RN-4 y lo que deja rastro—.

      `require_soporte` relee `is_support` de la base en cada petición, igual que
      el rol (T-221): quitarle el permiso a alguien surte efecto en su siguiente
      clic. La primera cuenta se crea con `bootstrap.py --soporte`, por lo mismo
      que la primera compañía.

- [x] **T-302** Grupo de rutas `/admin`, separado de `(app)`. Un usuario de
      compañía recibe 403; soporte recibe 403 en las pantallas del POS.

      **Hecho el 2026-08-23**, y las dos puertas se cierran en los dos sentidos:
      `requireSoporte` en `/admin/+layout.server.ts` y `requireUser` rechazando
      a soporte en `(app)`. **403 y no un redirect**, en los dos casos: el token
      vale, lo que no vale es para esto, y mandarlo al login lo dejaría en un
      círculo sin decirle nunca qué pasó.

      El API va bajo `/support` y las pantallas bajo `/admin`: `admin` ya es el
      rol del administrador de una compañía y dos cosas distintas con el mismo
      nombre en el mismo API se confunden; en la barra de direcciones, en
      cambio, `/admin` es lo que se lee bien.

      El armazón del panel **no reusa el layout del POS**. No hay moneda que
      configurar, ni marca del negocio, ni compañía en el menú: reusarlo habría
      significado llenarlo de condicionales para apagar la mitad, y esa mitad es
      justo la que RN-4 dice que no existe.

- [x] **T-303** Listado de compañías con afiliado, estado, plan, vencimiento y
      uso. RF-5.

      **Hecho el 2026-08-23.** El uso se cuenta con **cuatro consultas
      agrupadas** por `company_id` y no una por compañía y métrica: con veinte
      clientes serían ochenta viajes a la base para pintar una tabla.

      El monto del mes se muestra **sin símbolo de moneda**, y no es un olvido:
      cada compañía tiene la suya configurada y el panel no lee la configuración
      de veinte negocios para una tabla. Un símbolo por omisión diría «₡» sobre
      las ventas de un cliente que cobra en dólares, que es peor que no decir
      nada.

- [x] **T-304** Alta de compañía: datos, plan, administrador inicial. Deja
      creadas su sucursal, su terminal y su configuración por omisión. RF-6.

      **Hecho el 2026-08-23.** Las seis filas —compañía, sucursal, terminal,
      configuración, identidad y membresía— las crea `crud_company.dar_de_alta`,
      que es **la misma función que usa `bootstrap.py`**. Antes la lista vivía en
      el guion; copiarla al panel habría dejado dos altas que se parecen y que
      dejarán de parecerse el día que haya una séptima fila.

      **Los textos del documento los manda el POS**, como estaba previsto: nacen
      vacíos (T-816), el backend no tiene catálogo ni sabe en qué idioma, y el
      formulario los resuelve con `initialDocumentTexts(document_locale)` —el
      idioma **de la factura**, no el de la pantalla de quien da de alta—.

      Dos cosas que no estaban en la tarea y hubo que decidir:

      - **El par (afiliado, compañía) se puede dejar en blanco** y lo calcula el
        backend. Es el único que puede hacerlo sin que dos altas simultáneas
        elijan el mismo número.
      - **Un correo que ya existe no crea otra cuenta**: se le agrega la
        membresía y **nace pendiente** (T-229). Soporte puede sumar a alguien
        que ya trabaja en otra compañía, pero no puede darle acceso a su nombre.
        `bootstrap.py` sigue naciendo aceptada, y por eso `DatosDeAlta` lleva
        `aceptar_membresia`: quien corre el guion es el operador del sistema y no
        hay a quién preguntarle.

- [x] **T-305** Cambiar estado y fecha de vencimiento. RF-7.

      **Hecho el 2026-08-23**, y **con el plan además del estado y la fecha**.
      RF-7 nombra dos y son tres: una suscripción *es* en qué plan está, en qué
      estado y hasta cuándo. Sin el plan, el panel no puede subirle el plan a un
      cliente que creció, que es la mitad de las llamadas que va a recibir.

      El efecto es inmediato porque el estado se evalúa en cada petición (T-308):
      marcar `suspendida` deja al cajero afuera en su siguiente clic, y volver a
      `activa` lo devuelve igual de rápido.

      El detalle de la bitácora se arma con el antes y el después —`estado activa
      → suspendida, vence 2026-09-30`— porque «cambió el estado» no sirve para
      nada dentro de seis meses.

- [x] **T-306** *Entrar como*: token de la compañía destino, vencimiento corto,
      motivo obligatorio, franja permanente en pantalla. RF-8, RN-4.

      **Hecho el 2026-08-23, y es de solo lectura** (RN-32, que se agregó al
      spec por esto). RF-8 dice que soporte entra a **diagnosticar**, así que la
      visita ve todo y no escribe nada. Es la decisión más discutible de la fase
      y la más fácil de aflojar después, así que quedó escrita: si un día hay que
      dejar que soporte arregle algo, se abre a propósito y con su bitácora, no
      por descuido.

      Tres cosas más, todas visibles en pantalla porque quien entra tiene que
      saber qué puede hacer: **motivo obligatorio** (mínimo 5 caracteres, va a la
      bitácora completo y recortado al token para la franja), **media hora** de
      vigencia, y la **franja permanente** arriba de todo —viaja en `/users/me`,
      no una sola vez al entrar: una franja que se pierde al navegar no es
      permanente—.

      La sesión de soporte se guarda en una cookie aparte
      (`ventasys_support`) mientras dura la visita, así que «volver al panel» no
      pide la contraseña otra vez. Y si la media hora se acaba,
      `hooks.server.ts` la restaura en vez de mandar a soporte al login.

- [x] **T-307** Bitácora: se escribe en toda acción de soporte y se consulta
      desde el panel. RF-9.

      **Hecho el 2026-08-23**, con guardián: `test_soporte.py` lee el árbol de
      sintaxis del router y tumba `pytest` si un endpoint que escribe no llama a
      `registrar`. Las tres acciones de hoy están probadas una por una; el
      guardián es para la cuarta.

      Guarda también **los login de los clientes**, y es a propósito: la pregunta
      que se hace de verdad no es «qué hizo soporte» sino «por qué este cajero no
      puede entrar». Se puede filtrar por compañía y por acción, y el filtro es
      un GET: produce una URL que se pega en un correo y se abre mañana.

      La consulta usa `outerjoin` en las tres tablas: la bitácora tiene que
      sobrevivir a lo que narra. Un `join` normal haría desaparecer las líneas de
      un cliente dado de baja justo cuando más importan.

- [x] **T-308** Aplicar el estado de suscripción en cada carga de pantalla, con
      la gracia de 7 días y el aviso previo. RF-10, RF-11, RN-1, RN-2.

      **Hecho el 2026-08-23.** `domain/subscription.py` es aritmética pura
      —estado guardado + fecha + hoy— con 30 pruebas, y de ahí salió **RN-31**:
      el vencimiento lo pone el calendario y no una tarea manual, porque la
      alternativa es que el producto deje de cobrar el día que nadie mire.

      **El bloqueo va en un solo sitio**: `get_current_user` corta toda petición
      con método que escribe. Es la misma decisión que el filtro de compañía en
      un escuchador de SQLAlchemy —cuarenta endpoints que hay que acordarse de
      tocar no son un control de acceso— y tiene su guardián: `test_suscripcion.py`
      comprueba que toda ruta que escriba pase por ahí, que las dos excepciones
      (`/cash/close` por RN-1 y `/auth/locale`) sigan siendo rutas que existen, y
      que ninguna sobre.

      El estado **no va en el token**: se relee en cada petición. En el token
      quedaría congelado hasta el próximo login, que es lo peor de los dos
      mundos —bloquea tarde y desbloquea tarde—. Así un pago que entra hoy le
      devuelve el POS al cliente en el siguiente clic.

      En el POS, el aviso va en **todas** las pantallas (RF-11) y el bloqueo solo
      en **ventas** (RN-2): es la única donde la sorpresa cuesta plata. En las
      demás, lo que se pierde al chocar con el «no» del backend es un clic.

- [x] **T-309** Validar los límites del plan al crear terminales, sucursales y
      usuarios. RF-12.

      **Hecho el 2026-08-23.** `domain/limits.py` decide, y decide dos cosas que
      había que elegir a mano: **un máximo en 0 bloquea** —es lo que queda cuando
      alguien inserta un plan a medio llenar, y molestar es mejor que regalar el
      producto— y **−1 no limita**, que no se teclea por accidente.

      **Rompió la batería existente, y eso fue el hallazgo.** El fixture `cajero`
      crea un usuario por prueba —el arqueo se delimita por `user_id`, así que
      compartirlo haría que una prueba viera el turno de otra— y son casi veinte
      pruebas. Con el plan «Comercio» en 10 usuarios, a partir de la novena la
      batería empezaba a fallar señalando el alta de usuarios, que es lo único
      que no estaba mal. Las compañías de prueba pasaron a un plan sin límite
      (`PLAN_DE_PRUEBAS` en `conftest.py`, con el porqué escrito) y el límite se
      prueba aparte con un plan de dos.

      Los puntos donde hoy se aplica son los dos que suman gente a una compañía
      y el alta —que verifica que el plan admita la sucursal y la caja con las
      que nace—. Sucursales y terminales no tienen CRUD todavía (RF-26, F6);
      cuando lo tengan, la función ya está y con prueba.

- [x] **T-310** Comprobar de punta a punta: alta de compañía nueva, login de su
      administrador, venta, y que no ve nada de la otra compañía.

      **Hecho el 2026-08-23** en `tests/e2e/soporte.spec.ts`: 8 pruebas. El alta
      completa desde el formulario, el login de su administrador, y que su
      catálogo esté **vacío** —que es lo que prueba el aislamiento desde la
      interfaz—. Más las dos puertas de T-302, el aviso de vencimiento, la
      suspensión, la visita con su franja y la bitácora con su filtro.

      **Una prueba que suspendía la compañía del demo tumbó trece pruebas de
      otros archivos.** Restauraba el estado al final, pero falló a mitad y dejó
      el demo suspendido en `.data/mock-db.json`; las pruebas que venden ahí
      empezaron a fallar señalando la pantalla de ventas. Ahora la prueba **da de
      alta su propia compañía** y suspende esa: la salida no es restaurar mejor
      sino no tocar lo que otros usan.

---

## F4 · Categorías de dos niveles — ✅ terminada 2026-08-23

> Las nueve tareas, de T-401 a T-409. El catálogo pasa de una lista plana a un
> árbol de dos niveles: «Bebidas → Cervezas», «Yamaha → Llantas». El diseño está
> en [plan.md §5](plan.md); acá queda lo que se aprendió haciéndolo.
>
> **Migración 005** (`parent_id`, `sort_order`, `is_active`, `parent_key` y el
> UNIQUE compuesto), aplicada a la base viva y verificada.

- [x] **T-401** Migración: `parent_id`, `sort_order`, `is_active` en
      `categories`; UNIQUE (company_id, parent_id, name).

      **Hecha el 2026-08-23**, y las columnas van **en inglés** —`sort_order`,
      `is_active`— no como las nombraba la tarea: es la regla del proyecto y lo
      que ya hace `products`. Las de `companies` y `plans` están en español desde
      F2 y quedan como la excepción que son, anotada en T-913.

      **El UNIQUE que pedía la tarea no protege el caso más común.** Escrito
      `(company_id, parent_id, name)`, MySQL no considera iguales dos nulos, así
      que **dos raíces «Bebidas» entran las dos** sin que el índice diga nada.
      Es el mismo hueco que en `products.barcode` —donde es una ventaja: los
      productos sin código de barras conviven— y acá es un defecto. Se cierra con
      una columna generada: `parent_key` es el padre o 0, y el UNIQUE va sobre
      ella. STORED y no VIRTUAL, porque un índice único sobre una virtual la
      recalcula en cada lectura.

      **La foránea lleva la compañía adentro**: (parent_id, company_id) contra
      (id, company_id). Sin eso el esquema aceptaría una subcategoría de A
      colgada de una raíz de B; hoy no puede pasar porque el filtro de
      `tenancy.py` no deja ni ver esa raíz, pero eso es el cinturón y no el muro.
      InnoDB no comprueba una foránea compuesta cuando alguna columna es nula,
      así que las raíces pasan sin más.

      **Comprobada la paridad con `create_all`**: 7 columnas y 6 índices
      idénticos entre la base migrada y una creada desde el modelo, comparando
      `information_schema` (tipo, nulabilidad, valor por omisión, `EXTRA` y
      expresión de la columna generada). Es lo que pide la regla de que el modelo
      y la migración digan lo mismo.

      Y una trampa de sintaxis que costó un 1064: en una columna generada,
      `NOT NULL` va **después** de la expresión y del `STORED`. Escrito
      `INT NOT NULL AS (…) STORED`, MySQL señala la expresión, que es donde no
      está el problema.

- [x] **T-402** Validación de profundidad en el servicio: una categoría con
      padre no puede ser madre. RN-5.

      **Hecha el 2026-08-23** en `app/domain/categories.py` —pura, 19 pruebas sin
      base— y la regla se cierra **por los dos lados**: no se puede colgar de una
      subcategoría (`check_can_nest`) y una categoría con hijas no puede volverse
      hija (`check_can_become_child`). Con solo la primera, mover «Bebidas» —que
      tiene «Cervezas»— debajo de «Licores» crea un tercer nivel sin que nadie
      escriba nada de tres.

      Con la profundidad en dos, el único ciclo posible es una fila que se
      apunte a sí misma, que la foránea **no** impide. Lo impide
      `check_not_itself`: sin eso la categoría desaparece de las dos listas —no
      es raíz porque tiene madre, y no es hija de ninguna raíz—.

- [x] **T-403** No borrar con productos ni con hijas: desactivar. RN-7.

      **Hecha el 2026-08-23.** Borra solo lo que no arrastra nada; con productos
      o con hijas responde 409 y el código dice qué hacer. El «no» lleva **las
      dos cuentas** porque quien lo lee necesita saber qué mover primero.

      **Desactivar una raíz esconde su rama y no toca ninguna hija**: así volver
      a activarla devuelve la rama como estaba, en vez de tener que recordar cuál
      hija se había desactivado a mano antes.

      **De acá salió una decisión que no estaba en el spec** y que apareció
      escribiendo la prueba de punta a punta: **RN-6 cuenta las hijas activas, y
      borrar cuenta todas**. Una raíz a la que le desactivaron su única
      subcategoría vuelve a ser una hoja y vuelve a recibir productos; contando
      las desactivadas, esa rama se queda sin ningún sitio donde poner nada y la
      única salida es reactivar algo que el dueño acaba de retirar. Borrar es lo
      contrario: una hija desactivada sigue siendo una fila y borrar su madre la
      dejaría huérfana.

- [x] **T-404** CRUD de categorías y subcategorías, con reordenamiento. RF-13.

      **Hecha el 2026-08-23**, en pantalla propia (`/inventario/categorias`) y no
      en el modal que había: crear una categoría era un campo, y esto es un árbol
      que se reordena, se mueve y se desactiva. En un modal, la mitad de RF-13 no
      tenía dónde ir.

      **Reordenar es un botón, no arrastrar.** El botón manda la categoría y la
      dirección; el orden completo lo arma el servidor con `moveInOrder` —función
      pura, con prueba—. Así funciona sin JavaScript como el resto del POS, y en
      una pantalla táctil de caja arrastrar es peor. El API exige la lista
      **completa** de hermanas: con una parcial, las que faltaran conservarían su
      número y quedarían empatadas con las renumeradas.

      Cuatro endpoints nuevos (`update_category`, `reorder`, `delete_category` y
      el `register_category` que ya estaba, ahora con `parent_id`), declarados en
      los guardianes de `test_aislamiento.py` y cubiertos por `require_admin`, que
      es lo que hace que el bloqueo por suscripción los alcance sin tocar nada.

- [x] **T-405** Mover una subcategoría de raíz sin tocar sus productos. RF-14.

      **Hecha el 2026-08-23.** Es el mismo endpoint que renombra, porque las dos
      comparten la comprobación del nombre repetido: al mudarse, un nombre que
      era libre entre las hermanas viejas puede estar tomado entre las nuevas.

      **Omitir `parent_id` y mandarlo en nulo son cosas distintas** —«no lo
      toques» y «pasala a raíz»— y se leen con `model_fields_set`. Sin esa
      diferencia, renombrar una subcategoría la promovería a raíz sin que nadie
      lo pidiera, y el catálogo se iría aplanando solo.

      Los productos no se tocan: siguen colgados de la subcategoría, que es la
      que se mudó. La prueba de punta a punta lo comprueba por el camino más
      visible —la columna del inventario pasa de «Yamaha › Llantas» a
      «Suzuki › Llantas» y el producto sigue ahí—.

- [x] **T-406** Ficha de producto: elegir categoría y subcategoría. RN-6.

      **Hecha el 2026-08-23**, con dos desplegables y **un solo campo** viajando:
      `category_id` oculto, con la subcategoría cuando la raíz tiene rama y con
      la raíz cuando no. Es RN-6 escrita en un campo, y el backend la comprueba
      igual: la pantalla no ofrece lo que va a ser rechazado.

      La regla se aplica en **los dos caminos por los que nace un producto**: la
      ficha y la entrada de mercadería. Sin el segundo, el archivo del proveedor
      es la puerta de atrás de RN-6.

      **Defecto encontrado por la prueba de punta a punta:** el desplegable
      ofrecía subcategorías **desactivadas**, que el servidor rechaza. Al
      arreglarlo apareció el caso contrario: el producto que ya cuelga de una
      desactivada tiene que poder editarse sin cambiar de categoría, así que la
      suya se sigue ofreciendo. Editarle el precio no puede moverlo de sitio.

- [x] **T-407** Grilla de ventas: raíces como pestañas, subcategorías como
      fichas debajo. RF-15.

      **Hecha el 2026-08-23.** Las fichas de abajo **solo aparecen si hay**: en un
      catálogo plano la pantalla se ve igual que antes de F4, que es lo que tiene
      que pasarle a quien no usa dos niveles.

      **La raíz muestra su rama entera** (`withDescendants`). Filtrar solo por el
      id de la raíz dejaría la pestaña «Bebidas» vacía en cuanto alguien reparte
      su catálogo en subcategorías, que es justo el momento en que empieza a
      usarlo. Y cambiar de raíz descarta la subcategoría elegida: era de la otra
      rama.

- [x] **T-408** Filtro por los dos niveles en inventario. RF-16.

      **Hecha el 2026-08-23**, en **un solo desplegable** con `optgroup` por
      rama: la raíz filtra su rama entera y cada subcategoría, solo la suya. Dos
      desplegables encadenados obligarían a elegir raíz para poder elegir
      subcategoría, y el uso normal es «muéstrame Cervezas» sin pensar en dónde
      cuelga.

      La columna del inventario muestra el **camino completo** («Bebidas ›
      Cervezas»), que es lo único que distingue dos subcategorías homónimas en
      ramas distintas —el caso que el UNIQUE compuesto permite a propósito—.

- [x] **T-409** Verificar con dos catálogos reales: un súper (Bebidas →
      Cervezas, Gaseosas) y un repuestero (Yamaha → Llantas, Focos).

      **Hecha el 2026-08-23** en `tests/e2e/categorias.spec.ts`: 4 pruebas. Los
      dos catálogos se usan distinto y por eso son dos:

      * **El súper es el caso de leer** y va contra el catálogo del demo, que
        ahora nace repartido (`Bebidas → Gaseosas, Aguas y jugos, Cervezas, Café
        y té`). **No escribe nada.**
      * **El repuestero es el caso de construir** y va contra una **compañía
        propia**, dada de alta desde el panel al empezar la prueba. Es la lección
        de T-310: una prueba que cambia el catálogo del demo se lo cambia a las
        otras trece.

      **Encontró dos cosas y ninguna se veía leyendo el código**: el desplegable
      que ofrecía una subcategoría desactivada (T-406) y la decisión de las hijas
      activas (T-403). Las pruebas de unidad no podían verlas: la primera es un
      desacuerdo entre dos capas que por separado están bien.

      Tres veces hubo que reintentar un clic, y las tres por lo mismo: **los
      botones que abren un modal y los desplegables con `bind:value` no funcionan
      hasta que Svelte hidrata**. El HTML ya está pintado, así que Playwright ve
      un control listo y lo usa. `clicHasta` salió de `login.spec.ts` a
      `sesion.ts` para no tener tres copias del mismo truco.

**Fuera de guion, durante F4:**

- [x] **T-410** `company_dump.py` no sabía de columnas generadas: exportaba
      `parent_key` y la restauración fallaba con «The value specified for
      generated column is not allowed». Ahora se exportan solo las columnas con
      dato propio, y las filas salen **ordenadas por clave primaria**: desde F4
      `categories` se apunta a sí misma, y una madre siempre tiene un id menor
      que sus hijas, así que insertar en ese orden es lo que hace que la foránea
      se cumpla fila por fila.
- [x] **T-411** Cuatro mensajes de éxito en español dentro de acciones
      (`return { success: 'Producto agregado…' }`) que ninguna mitad del guardián
      de T-812 veía: no son marcado ni una llamada a `formError`. Pasaron al
      catálogo. Queda **uno** en `/caja` con interpolación, anotado en T-914.

---

## F5 · Impuesto por producto y CABYS — ✅ terminada 2026-09-05

> ~~**Antes de empezar esta fase van T-913, T-914 y T-915**~~ — **los tres
> quedaron cerrados el 2026-09-05** y F5 está desbloqueada. T-913 se aceptó por
> escrito ([plan.md §3.9](plan.md)); T-914 y T-915 se hicieron, y T-915 encontró
> de paso las cuatro UNIQUE que faltaban en los modelos.
>
> **La superficie real de F5 son ~80 sitios, no los ~20 que sugiere el plan.**
> Se midió el 2026-09-05 antes de empezar. Lo que sigue son las correcciones a
> las tareas de abajo; el diseño de fondo de [plan.md §6](plan.md) se sostiene.

### Correcciones al alcance, medidas antes de empezar (2026-09-05)

- **T-509b se queda corta: `returns` no tiene dónde guardar el impuesto.** La
  tabla guarda **solo `total`** —sin `subtotal` ni `tax`—, así que congelar la
  tarifa en `return_details` no alcanza: la devolución seguiría sin desglose que
  reimprimir ni que cuadrar. Hay que partir `returns.total` en subtotal + impuesto
  en la misma migración.
- **La tarifa no vuelve por el API, así que las plantillas no pueden desglosar
  aunque se guarde.** `get_sale_detail` arma cada línea con
  `id_product/name/quantity/price/subtotal` y nada más. Sin ampliar eso, T-510 no
  tiene con qué.
- **T-510 no es «agregar una clave».** Las tres plantillas **no pueden importar
  Paraglide** —lo prohíbe una prueba, por RN-29— así que el rótulo de cada fila
  por tarifa tiene que salir del diccionario de `ui/documents.ts`, que hoy tiene
  `subtotal` y `total` y **no tiene impuesto**. Por eso las plantillas llaman a
  `taxLabel()`, que ignora el idioma del documento: **la fila del impuesto ya sale
  hoy con el rótulo del idioma equivocado**, defecto preexistente que F5 tiene que
  arreglar de camino.
- **Hay un cuarto documento y el plan cuenta tres**: el PDF de reportlab del
  backend dibuja la factura con **ocho rótulos escritos a mano en español**
  —«Factura:», «Metodo de pago:» (sin tilde), «IVA:»…—, contra RN-30. Desglosar
  ahí es rehacer la función, no insertar filas.
- **`company_dump.py` se rompe con T-501.** `TABLAS_AJENAS = {"plans"}` y
  `verificar_cobertura()` lanzan `SystemExit` ante una tabla que no esté
  clasificada, y `cabys_cache` nace global. Hay que clasificarla en el mismo
  commit o el respaldo por compañía deja de correr.
- **Tocar el puerto `SettingsRepository` tumba `pytest`.** `test_ports.py` fija su
  superficie exacta (`{"tax_rate"}`); es costo previsto, no una sorpresa a mitad.
- **Diez archivos de prueba y dos semillas fijan el 13 %** —`test_characterization`,
  `test_error_codes`, `test_aislamiento`, `test_respaldo_compania`, los de dominio
  y aplicación, `seed.py` y `mock/db.ts`—. Después de T-509c empiezan a recibir
  `totals_mismatch`. Y tocar `mock/db.ts` obliga a subir `SEED_VERSION`.
- **El lector de XML descarta la tarifa que ya trae.** `hacienda.ts` lee
  `CodigoCABYS` solo para emparejar y no mira `<Impuesto><Tarifa>` nunca. Es la
  fuente más barata de tarifas reales y hoy se tira.
- **`update_product_information` salta los `None`**, así que un `cabys_code`
  asignado no se puede borrar por el API. Con `tax_rate` el mismo salto es peor:
  un 0 % legítimo no se distingue de «no lo toques».
- **La tolerancia ya se mide por documento.** `check_declared_totals` compara las
  tres cifras del documento una vez cada una, así que T-509c **no** tiene que
  cambiar la granularidad, solo aplicar la tarifa de cada línea.

### Catálogo

> **Migración 006** (`006-impuesto-por-producto.sql`), aplicada a la base viva y
> verificada el 2026-09-05: las nueve columnas nuevas, `cabys_cache`, y diez
> índices. **Nada de lo ya cobrado cambió** —todas las columnas nacen en NULL, y
> NULL significa «la tasa configurada», que es lo que se venía aplicando—: 38
> ventas por ₡360.413,50 y 28 productos, iguales antes y después.
>
> Los nombres van **en inglés** (`tax_rate`, `unit_of_measure`, `cabys_cache`)
> aunque plan.md §6.2 y T-507 los escribieran en español al diseñarlos. Es la
> regla del proyecto y lo que ya hizo F4 con `sort_order`.

- [x] **T-501** Tabla `cabys_cache` (global, no por compañía).

      **Hecha el 2026-09-05**, con su modelo (`model_cabys.py`). No hereda
      `TenantMixin` y por eso sus consultas **no llevan filtro por compañía**:
      es correcto —son códigos publicados por Hacienda, no dato de nadie— y es
      justo la clase de excepción que hay que mirar dos veces, así que queda
      escrita en el módulo.

      Hubo que declararla en `company_dump.py` (`TABLAS_AJENAS`) en el mismo
      commit: la herramienta tiene un control que exige que toda tabla esté
      clasificada y se niega a correr con una sin clasificar. Sin eso, el
      respaldo por compañía dejaba de funcionar el día que alguien lo necesitara.
- [x] **T-502** Proxy `GET /cabys/buscar?q=` y `GET /cabys/{codigo}` en FastAPI.
      Contemplar que Hacienda devuelve **objeto** en la búsqueda por texto y
      **lista** en la búsqueda por código (plan §6.1).

      **Hecho el 2026-09-05 y comprobado en vivo contra Hacienda**: «arroz»
      devuelve `2312000000300 Harina de arroz` al 13 % —la cifra que el plan
      documentó en agosto, todavía vigente— y de paso `Arroz precocido` al 1 %,
      que es la canasta básica del spec. Las dos formas de respuesta se leen bien.

      **Sin dependencia nueva**: `urllib` de la biblioteca estándar. Es un GET
      con tiempo de espera, y este proyecto acota sus dependencias porque fue
      `passlib` lo que le rompió una instalación entera.

      La tarifa viaja **entre 0 y 1** hacia adentro; Hacienda la publica en
      porcentaje y la traducción vive en el adaptador, así que en el sistema no
      circula nunca un `13` que alguien pueda confundir con `0.13`.

      Las entradas ilegibles del catálogo ajeno se **descartan en silencio**: sin
      código, sin tarifa o con un código que no es de trece dígitos. Quien busca
      «arroz» quiere las que sirven, no un error porque la número siete venía
      rara.

- [x] **T-503** Sin internet: responder desde la caché y decirlo. RNF-4.

      **Hecho el 2026-09-05**, y **ejercitado de verdad**: apuntando el adaptador
      a un servidor inalcanzable, la búsqueda devuelve las cinco entradas
      cacheadas con `source: cache`, y el código exacto devuelve la suya con la
      fecha en que se leyó. Sin excepción y sin bloquear nada.

      **`source` viaja siempre en la respuesta**, no solo cuando falla. No es un
      detalle interno: es la diferencia entre «esto dice Hacienda hoy» y «esto
      decía la última vez que hubo internet», y quien está clasificando un
      producto necesita saber cuál de las dos está leyendo.

      Tres decisiones que la tarea no nombraba:

      * **«Hacienda dice que no existe» NO cae a la caché.** Es una respuesta del
        catálogo, no una falla: caer ahí devolvería lo que alguien buscó antes y
        podría contradecir al catálogo de hoy. Son dos códigos distintos por eso.
      * **El formato se valida antes de salir a la red.** Trece dígitos es una
        regla del catálogo. Así no se gasta un viaje en un código imposible y el
        «no» distingue el error de quien pide del de la red.
      * **Con texto vacío no se pregunta nada.** Cada búsqueda es un viaje a
        internet.

      La caché se llena sola con lo que se va usando —no con los veinte mil
      códigos del catálogo—, y por eso **asignarle un CABYS a un producto es lo
      que hace que facturar no dependa de que Hacienda esté arriba**.
- [x] **T-504** Buscador de CABYS en la ficha del producto. RF-17.

      **Hecho el 2026-09-05.** El buscador es un componente
      (`ui/components/CabysSearch.svelte`) y no marcado repetido, porque lo usan
      dos pantallas: la ficha y la asignación en lote. Habla con
      `/inventario/cabys`, un `+server.ts` que es **el único sitio del POS donde
      el navegador pide algo por su cuenta**: buscar es teclear y ver
      resultados, y eso no cabe en un envío de formulario. El token sigue sin
      salir del servidor de SvelteKit.

      El puente acepta `q` (texto) y `codigo` (exacto). El segundo no es un lujo:
      es lo que permite saber cuál es la tarifa oficial de un producto **ya
      clasificado**, y sin eso el aviso de T-505 solo existiría durante la sesión
      en que se asignó el código.

      Un 400 o un 404 de Hacienda vuelven como lista vacía —son respuestas del
      catálogo, no fallas—; **solo no alcanzar el backend sale como 502**. Que
      Hacienda no conteste no llega nunca hasta acá: el backend responde 200
      desde su caché y lo dice en `source`.

- [x] **T-505** Al asignar, copiar la tarifa; si el usuario la cambia, avisar
      que difiere de la oficial. RF-18, RN-11.

      **Hecho el 2026-09-05**, y destapó un hueco que había que tapar primero:
      **la ficha no podía decir «la configurada»**. `update_product_information`
      se saltaba los nulos —correcto para un PUT parcial, que así no borra lo que
      no se mandó— así que un `tax_rate: null` no llegaba a la base y clasificar
      un producto era una puerta de una sola dirección. Se arregló distinguiendo
      «no mandé este campo» de «ponelo en nulo»: el router manda
      `model_dump(exclude_unset=True)` y `crud_product.VACIABLES` declara las dos
      columnas donde el nulo **es** un valor. En el resto sigue siendo una
      omisión, porque `name=None` rompería un NOT NULL.

      El aviso **no bloquea**: hay exoneraciones y casos especiales, y quien
      vende sabe de su negocio más que una tabla. Lo que hace es convertir un
      error de dedo en una decisión. Sin tarifa oficial no se avisa nada —producto
      sin clasificar, o catálogo que no se pudo leer—: inventarse una diferencia
      que nadie puede comprobar es peor que callarse.

      La tarifa se escribe en **porcentaje** y circula entre 0 y 1;
      `rateFromPercent` recorta a seis decimales, que es lo que guarda
      `DECIMAL(7,6)`. Sin recortar lo haría la base en silencio y la tarifa
      releída dejaría de ser igual a la guardada: el aviso saltaría por una
      diferencia que nadie hizo.

- [x] **T-506** Asignación en lote para catálogos ya cargados. RF-20.

      **Hecho el 2026-09-05** con endpoint propio —`PUT /products/assign_cabys`—
      y no con un bucle de PUT desde el POS. **Es todo o nada**: si un
      identificador no resuelve, no se aplica ninguno. Medio catálogo clasificado
      es exactamente el desorden que RF-20 existe para arreglar, y quien lo pidió
      no tendría cómo saber qué mitad quedó hecha.

      Los ids van en el cuerpo porque son muchos, y eso los saca de la batería de
      `RUTAS_POR_ID` —que sustituye ids en la **ruta**—. No se declaró exento: se
      probó aparte, en `TestElLoteDeCabysNoAlcanzaLoAjeno`, con las tres piezas
      (404 con un id ajeno, el ajeno intacto después, y el lote propio
      funcionando para que un 404 en todo no pase el examen).

      El código y la tarifa se validan **con el dominio** antes de tocar nada:
      `normalize_code` y `TaxRate`. `13` en vez de `0.13` multiplica la factura
      por catorce, y en un lote lo haría en cien productos a la vez.

      La pantalla (`/inventario/clasificar`) marca **lo que está a la vista** y
      no el catálogo entero: con un filtro puesto, «todos» clasificaría cosas que
      quien marcó no llegó a ver.

### Impuesto por línea

- [x] **T-507** Migración: `cabys_code`, `tax_rate`, `unit_of_measure` en
      `products`. RN-9.

      **Hecha el 2026-09-05.** `tax_rate` es `DECIMAL(7,6)` y no `DECIMAL(10,2)`:
      una tasa **no es un monto**, y con dos decimales se perdería el 2,5 % y
      cualquier tarifa fina del catálogo. Seis decimales es la precisión de
      `TaxRate` (`domain/tax.py`).

      **En NULL, y no rellenada con la tasa de cada compañía.** NULL significa
      «la configurada», que es exactamente lo que se venía aplicando, así que la
      migración no toca un solo precio. Rellenar habría congelado 28 productos en
      el 13 % sin que nadie lo pidiera, y el día que el dueño cambie su tasa
      esperaría que le cambie el catálogo que no tocó. RN-9 dice que la
      configurada es «el valor por omisión de un producto nuevo»: eso es la
      ficha proponiéndola al crear, no un relleno del pasado.

      `unit_of_measure` lleva `server_default` y no `default`: el segundo es del
      lado de Python y **no emite `DEFAULT` en el DDL**, así que `create_all`
      habría creado la columna sin valor por omisión mientras la migración sí se
      lo pone. Es el defecto 19 asomando por la puerta de al lado, y lo destapó
      ir a comprobarlo a mano —la prueba de paridad compara índices y todavía no
      compara valores por omisión (T-919)—.

- [x] **T-508** `computeTotals` recibe líneas con su tarifa y devuelve el
      desglose (plan §6.3). RN-10.

      **Hecho el 2026-09-05 en los dos lados** —`domain/sale.py::sale_totals` y
      `$lib/domain/money.ts`—, con el mismo diseño y las mismas cifras. Se llama
      `by_rate`/`byRate` y no `porTarifa`: código en inglés.

      **La decisión que lo sostiene: el redondeo va por TARIFA, no por línea.**
      Con una sola tarifa —todo el catálogo de hoy— hay un grupo único, su base
      es el subtotal entero y su impuesto es `round(subtotal × tasa)`: **el mismo
      número de siempre**. Por eso los invariantes ya verificados no se movieron
      ni un céntimo y esta fase no obliga a remedir nada. Redondeando por línea,
      tres líneas al 13 % pueden sumar un céntimo distinto del que da el subtotal
      completo. Es además lo que pide el documento: Hacienda quiere base e
      impuesto **por tarifa**, y si cada fila del desglose no cuadra con su
      propio impuesto, el desglose no suma el total.

      El desglose **siempre viene**, aunque haya una sola tarifa; quien imprime
      decide si lo muestra (RF-21). Y va **de menor a mayor**, para que un
      documento no dependa de en qué orden marcó el cajero.

      El caso del spec ya está probado en los dos lados: devolver solo el
      medicamento al 2 % da ₡1 020 y no ₡1 075; devolver solo el arroz da
      ₡1 130; y las dos parciales suman la venta entera, que es lo que impide
      que el negocio gane o pierda plata según el orden en que se devuelva.
- [x] **T-509** Propagar el cambio: carrito, `crud_sale`, `crud_return`,
      reportes, mock. Las ventas viejas conservan su impuesto. RN-12.

      **Hecho el 2026-09-05**, y verificado contra el stack real: una venta de un
      medicamento al 2 % y un arroz al 13 % guarda `tax_rate` 0,020000 / 0,130000
      y `tax_amount` 20,00 / 130,00, que suman los 150,00 del encabezado.
      Devolver **solo** el medicamento reembolsa **₡1 020,00** y solo el arroz
      **₡1 130,00**: los dos números del spec, y suman la venta entera.

      **La tarifa se resuelve en el caso de uso, no al guardar.** La línea sale
      de `RegisterSale` con una tarifa concreta, nunca nula, y el repositorio
      solo la serializa. Si se resolviera al escribir, lo que queda congelado
      dependería de lo que esté configurado en ese instante, que es justo lo que
      RN-12 prohíbe. La tasa del negocio se lee **una vez** por venta: por línea,
      alguien guardando la configuración a mitad del cobro dejaría dos líneas de
      la misma factura con tasas distintas.

      La devolución mira **primero la tarifa de la línea** y solo cae al cociente
      del encabezado cuando no la hay —ventas anteriores a la 006, que llevan una
      sola y por eso el cociente las reconstruye exactas—. `sold_tax_rates` es el
      método nuevo del puerto que lo permite.

      Costes previstos que se pagaron: `test_ports.py` fija la superficie de los
      puertos y hubo que declarar `sold_tax_rates` y `ProductSnapshot.tax_rate`;
      los repositorios falsos y una prueba de arqueo que llamaba `add` directo.

      **Los esquemas del producto no llevaban las columnas**, así que la tarifa
      existía en la base y no había forma de ponerla. `ProductRegister`,
      `ProductUpdate` y `ProductResponse` las llevan ahora, y el router las
      construye —no llegan solas, porque arma la respuesta campo por campo—.

      El simulado quedó sincronizado en sus tres puntos (venta, devolución y alta
      de producto) y `SEED_VERSION` subió a **6**.

      **Corrección del 2026-09-05, la misma tarde: el carrito NO estaba
      propagado.** Esta tarea lo daba por hecho y `CartLine` no tenía el campo,
      así que el resumen de la venta le aplicaba a todo la tasa configurada. Lo
      encontró T-511 —vendiendo de verdad, que era la única forma— y no era
      cosmético: el servidor recalcula por línea y rechaza lo que no cuadre, de
      modo que una venta con tarifas mezcladas **ni siquiera se podía cobrar**.
      Lo que engañó fue la verificación de arriba: se hizo con `curl` contra el
      API, que es el camino donde el carrito no aparece. Cerrado en T-511.

- [x] **T-509c** El servidor verifica por línea.

      **Hecho el 2026-09-05**, con menos trabajo del previsto: la tolerancia **ya
      se medía por documento** —`check_declared_totals` compara las tres cifras
      del documento una vez cada una— así que no hubo que cambiar la granularidad,
      solo que `sale_totals` aplicara la tarifa de cada línea.

      **La decisión de fondo de la fase, y se midió antes de tomarla: el redondeo
      del impuesto va por LÍNEA, no por tarifa.** Cada línea redondea el suyo, los
      grupos suman los de sus líneas y el documento suma los de sus grupos.

      El argumento decisivo es que `sale_details.tax_amount` tiene que **sumar
      exactamente** el impuesto del encabezado: redondeando por tarifa, la suma
      de las líneas de un grupo puede quedar un céntimo aparte del
      `round(base × tasa)` del grupo, y entonces la factura no cuadra consigo
      misma —y Hacienda valida justamente esa igualdad—.

      Y **no mueve ninguna cifra de referencia**, que es lo que había que
      comprobar antes de elegir: las cuatro de `progress.json` dan idéntico por
      las dos vías. Las formas difieren en un céntimo en el ~39 % de las ventas
      con precios **con céntimos** y en **ninguna** con colones enteros, que es
      todo el catálogo real. Un céntimo es además lo que ya tolera
      `TOTALS_TOLERANCE` entre el POS y el servidor.
- [x] **T-509b** Migración: `tax_rate` y `tax_amount` en `sale_details` y en
      `return_details`. **La tarifa se congela en la línea**, no se lee del
      producto (plan §6.3). `TaxRate.of_sale` queda como respaldo para las ventas
      anteriores a la migración, que tienen una sola tarifa.

      **Hecha el 2026-09-05, y con una columna más de las que pedía**: `returns`
      guardaba **solo `total`**, sin subtotal ni impuesto. Con una tarifa daba
      igual porque el impuesto se deducía; con tarifas mezcladas no hay de dónde
      deducirlo, así que una devolución se habría quedado sin desglose que
      reimprimir y sin con qué cuadrar la caja. Se partió en `subtotal` + `tax`.
      No estaba en la tarea: apareció al medir la superficie de F5.

      Se guarda `tax_amount` además de la tasa, aunque sea recalculable: es lo
      que se cobró de verdad **con su redondeo**, y una factura tiene que poder
      reimprimirse igual dentro de cinco años aunque cambie cómo se redondea.

      Escribirlas al cobrar es T-509, que quedó hecha el mismo día: las columnas
      se llenan desde entonces.
- [x] **T-510** Desglose por tarifa en las tres plantillas de documento, solo
      cuando hay más de una. RF-21.

      **Hecho el 2026-09-05** en el tiquete y las dos facturas. **El «solo cuando
      hay más de una» sale gratis**: se recorre el desglose, y con una sola
      tarifa el recorrido da una fila —exactamente la que había antes de F5—.
      No hizo falta condicional.

      **El documento lee lo COBRADO, no lo recalcula.** `taxBreakdown` agrupa lo
      que se guardó en cada línea; reimprimir una factura de hace cinco años
      tiene que dar lo que se cobró aunque la tarifa del producto sea otra o haya
      cambiado cómo se redondea (RN-12). Las ventas anteriores a la migración 006
      caen a un solo grupo con la tasa del encabezado, que en ellas es exacta.

      **Tres cosas hubo que resolver antes**, y ninguna estaba en la tarea:

      1. **El API no devolvía la tarifa**, así que el documento no tenía qué
         desglosar. `get_sale_detail` y `SaleItem` la llevan ahora.
      2. **La plantilla no puede importar Paraglide** (lo prohíbe una prueba, por
         RN-29), así que el rótulo salió del diccionario: `doc_tax_at_rate`, una
         clave nueva en los tres catálogos. El **nombre** del impuesto no se
         traduce —lo configura el negocio, puede ser IVA o ISV—; lo que aporta la
         clave es la forma.
      3. **El simulado guardaba la tarifa y no el monto**, así que el desglose
         habría salido en cero. Se guarda `tax_amount` por línea, como el
         backend.

      **Defecto preexistente corregido de camino**: las plantillas llamaban a
      `taxLabel()`, que sale del estado de módulo de `money.ts` —o sea de la
      configuración **vigente**—. Reimprimir una factura vieja después de subir
      el IVA mostraba el porcentaje de hoy junto al monto de entonces. Ahora el
      rótulo lleva la tarifa que se guardó. `taxLabel()` sigue existiendo para el
      carrito y las devoluciones, donde mirar la configuración vigente sí es lo
      correcto, y su docstring dice ahora dónde no usarlo.

      **Falta el cuarto documento**, que el plan contaba como tres: el PDF de
      reportlab del backend. Va en T-922.
- [x] **T-511** Verificar con una venta que mezcle 13 %, 2 % y 0 %: que cuadre,
      que desglose, y que la **devolución parcial de una sola tarifa** reembolse
      lo que se cobró por esa línea y no el promedio de la venta. El caso del
      medicamento al 2 % junto al arroz al 13 %: devolver solo el medicamento
      tiene que dar ₡1 020, no ₡1 075.

      **Hecho el 2026-09-05, en los dos niveles y como prueba permanente.**
      `backend/tests/test_impuesto_por_producto.py` fija la aritmética contra
      MySQL —doce pruebas— y `tests/e2e/clasificar-cabys.spec.ts` comprueba que
      esas mismas cifras lleguen a la pantalla, que entre el cálculo y la factura
      hay un carrito, un modal de cobro y tres plantillas.

      Con las tres tarifas juntas —₡1 000 al 2 %, ₡1 000 al 13 % y ₡1 000 al 0 %—
      el impuesto es ₡150 y el total ₡3 150; con una tasa única al 13 % sería
      ₡390. Devolver solo el medicamento da **₡1 020**, solo el arroz **₡1 130** y
      solo el libro **₡1 000 sin un céntimo de impuesto**, y las tres parciales
      suman la venta entera: eso es lo que impide que el negocio gane o pierda
      según el orden en que se devuelva.

      **La verificación encontró lo que las pruebas de tipos no podían: el
      carrito nunca recibió la tarifa por línea.** T-509 daba por propagado el
      carrito y no lo estaba —`CartLine` no tenía el campo—, así que
      `computeTotals` le aplicaba a todo la tasa configurada. No era un defecto
      cosmético: el servidor recalcula por línea y rechaza lo que no cuadre, de
      modo que **una venta con tarifas mezcladas ni siquiera se podía cobrar**.
      La única forma de encontrarlo era vender de verdad, que es justamente lo
      que pedía esta tarea. `newLine` copia ahora la tarifa como copia el precio,
      y el resumen del carrito muestra una línea por tarifa cuando hay más de
      una: rotular la suma con la configurada diría un porcentaje que no se está
      cobrando en ninguna.

      De paso apareció otro que tampoco tenía prueba: **el simulado reembolsaba
      cero**. Calculaba los totales de la devolución leyendo `i.unit_price`, y una
      línea devuelta se llama `price`; `undefined` entraba a `round2`, salía 0 y
      la devolución entera daba ₡0 sin fallar. Lo escondía un `any` que se
      arrastraba desde el cuerpo de la petición: ahora ese `map` declara
      `ReturnItem[]`, y con el tipo puesto el error no compila.

      Y `returns` guardaba subtotal e impuesto desde la 006 pero **el API no los
      devolvía**: se guardaba algo que nadie podía leer. Ya viajan, en el backend
      y en el simulado, en nulo para las devoluciones anteriores a esa migración.

### Salieron de mirar la pantalla, el 2026-09-06

Todas de una misma sesión: se levantó el POS para ver el avance de F5 y el arroz
cobraba 13 %. **Ninguna se habría encontrado leyendo el código**, y las cuatro
estaban en el camino que una persona recorre el primer día.

- [x] **T-512** **Escribir el código CABYS a mano no copiaba su tarifa**, contra
      RN-11. La copia colgaba solo de `asignarCabys`, que corre al elegir un
      resultado de la lupa; quien ya tiene el código —que es lo normal— lo
      tecleaba y la tarifa se quedaba en blanco.

      **Y arrastraba dos cosas peores que la molestia**, porque la misma consulta
      que faltaba es la que alimenta `officialRate`: en un producto nuevo el
      aviso de diferencia **no existía**, y en uno ya clasificado **mentía** —al
      abrirlo se leyó la tarifa del código viejo y cambiar el código a mano
      dejaba ese dato comparándose con la tarifa nueva—. Podía avisar de una
      diferencia inexistente o callar una real, y como al reabrir sí se
      consultaba, parecía intermitente.

      **Hecho el 2026-09-06.** Un `$effect` con espera de 400 ms vigila el campo,
      y `codigoLeido` dice a qué código pertenece `officialRate`. La consulta
      distingue **asignar de abrir**: abrir una ficha lee el catálogo pero no
      copia, porque el producto puede apartarse de él a propósito y copiar
      borraría justo lo que hay que mostrar.

- [x] **T-513** **El buscador solo buscaba por texto.** Escribir un código
      devolvía cero resultados —el `q=` de Hacienda no mira los códigos, se
      comprobó contra el API— así que había que buscar la descripción para
      asignar un código que ya se tenía.

      **Hecho el 2026-09-06.** Si lo escrito son solo dígitos va por `codigo=`,
      que el puente ya aceptaba y nadie usaba. Un código a medias **se dice
      mientras se escribe**, sin gastar la petición: Hacienda solo resuelve el
      exacto.

      **«Cargar todos» no se puede** y queda medido: sin `q` el API responde 400,
      no hay endpoint de listado y son unas 19 000 entradas. Filtrar por prefijo
      necesita el catálogo local — ver T-516.

- [x] **T-514** **El carrito no decía la tarifa de cada línea.** Las tarifas solo
      aparecían abajo, agrupadas: con dos, el cajero veía que las había pero no
      cuál línea puso cuál. Es el último momento en que un producto mal
      clasificado se puede atajar — después de cobrar ya está en un documento
      fiscal, y «el IVA no coincide con el definido para ese CABYS» es causa de
      rechazo (README de Hacienda, familia 3).

      **Hecho el 2026-09-06.** Y lo que importaba más: **la línea sin clasificar
      se marca**. Un producto sin CABYS no es «13 %», es que nadie lo decidió y
      se está cobrando la configurada; una es una decisión y la otra una omisión,
      y en Inventario ya se distinguían.

- [x] **T-515** **El catálogo de demostración nacía entero sin clasificar**, así
      que los 26 productos heredaban el 13 % y la pantalla enseñaba F5 como si no
      existiera: arroz y frijoles, que son canasta básica al 1 %, cobraban 13 %.
      Le pasaba a cualquiera que levantara el proyecto.

      **Hecho el 2026-09-06** en el seed y en el simulado, con **códigos reales**
      consultados a Hacienda. La tarifa **se pregunta, no se escribe**: el seed
      llama a `/cabys/{codigo}` y usa lo que responda, que es el mismo camino de
      la persona que clasifica, y sin catálogo no clasifica y lo dice — una
      tarifa inventada quedaría escrita como si alguien la hubiera comprobado.

      **Tres quedan sin clasificar a propósito** —yogurt, natilla y maní—: es el
      estado en que llega un catálogo heredado, y sin ellos la asignación en lote
      no tiene nada que hacer y el aviso del carrito no se ve nunca.

      Los códigos del simulado **eran inventados** y ahora son reales. Un código
      inventado en una prueba enseña a leer una tarifa que el catálogo no
      confirma, que es exactamente el defecto que se está previniendo.

- [x] **T-517** **Dos pruebas de punta a punta se caían por carreras, no por el
      código.** Salían solo en corridas largas y saltando de una prueba a otra,
      que es la firma de la fragilidad y no la de una rotura.

      **Arregladas el 2026-09-06.** El clic sobre el producto pasó a `clicHasta`
      contra `[data-testid="cart-lines"]` —un asidero que no depende del idioma,
      que esa prueba corre en tres—, y todo lo del modal de cobro vive ahora en
      **`abrirCobro`, en `sesion.ts`**: eran tres líneas copiadas en dos archivos
      y las tres estaban mal, cada una a su manera.

      Las tres trampas, que costaron tres intentos:

      1. **F1 abre uno de dos modales** —apertura si la caja está cerrada, cobro
         si no—, así que preguntar por el campo de apertura responde «no está»
         tanto cuando salió el otro como cuando no salió ninguno.
      2. **Cerrar el modal de apertura no termina cuando su campo deja de
         verse.** Queda la capa de fondo, que intercepta el clic sobre el botón
         de cobrar.
      3. **Abrir la caja recarga los datos de la página**, y hasta que Svelte no
         vuelve a enganchar, F1 no hace nada.

      La forma que funciona: se reintenta, **pero solo se pulsa F1 si no hay
      ningún modal abierto**. El primer intento reintentaba F1 a secas y empeoró
      la corrida de una falla a cinco, porque con un modal abierto apila una
      segunda capa —el problema 2—. La lección: **cuando la acción no es
      idempotente, el reintento necesita una guardia**, no menos reintentos.

- [ ] **T-516** **El catálogo CABYS completo en la base.** RF-38, RN-48.

      Es lo que pidió el usuario —«que cargue todos y yo filtro», «sería mejor
      guardarlos en la db»— y lo único que lo hace posible: el API de Hacienda no
      lista. Medido el 2026-09-06: sin `q` responde **400**, `q=2314` devuelve
      **cero** —la búsqueda por texto no mira los códigos— y `codigo=` solo
      resuelve el exacto. Son unas 19 000 entradas.

      **La tabla ya existe.** `cabys_cache` es global —no lleva `company_id`, se
      decidió en T-501— y tiene las columnas. Lo que cambia es qué es: deja de
      ser una caché de lo consultado y pasa a ser el catálogo. Eso arrastra tres
      cosas que no tenía:

      1. **Una importación repetible y con versión.** El CABYS 2025 ya reemplazó
         al anterior, así que «cargar una vez» no es una respuesta. Falta ubicar
         el archivo que publica Hacienda: la URL que se probó da 404, y eso se
         averigua antes de diseñar el importador, no después.
      2. **Búsqueda en SQL.** Por prefijo de código va contra la llave primaria;
         por texto es un `LIKE` sobre 19 000 filas, que en MySQL es instantáneo.
         Medir antes de meter FULLTEXT.
      3. **Su clasificación en `company_dump.py`**, que hoy no tiene: no es de
         ninguna compañía, así que no entra en el respaldo de ninguna.

      **Y la regla que lo hace seguro, que es lo que no puede faltar:** lo local
      contesta **la búsqueda**; la tarifa que se **asigna** se confirma contra
      Hacienda cuando hay internet (RN-48). Al revés —asignar desde una copia
      vieja— se emite una tarifa que Hacienda ya no acepta, y vuelve como
      «el IVA no coincide con el definido para ese CABYS», que es rechazo.

      Cierra además RNF-4 para esta pantalla: hoy sin internet no se puede
      clasificar un producto nuevo, solo releer lo ya consultado.

      **Verificación:** escribir `2316` filtra **con el contenedor sin salida a
      internet**; un código que no está en el catálogo local se rechaza antes de
      guardar; y reimportar dos veces no duplica ni pierde filas.

---

## F6 · Preparación de factura electrónica

> **Alcance corregido el 2026-09-06, antes de empezar.** La fase contemplaba
> **un** secreto y son **dos**: el `.p12` firma y las credenciales de ATV
> transmiten, y con uno solo no se emite. Y los dos son **por ambiente**, no por
> compañía —Hacienda los emite en registros separados y el IdP los valida contra
> realms distintos—, así que la llave primaria de `fe_credentials` cambia. Está
> en `docs/hacienda/costa-rica/README.md` §7 y §12, que ya estaba en el repo.
>
>
> De ahí salen RF-29 a RF-32 y RN-33 a RN-38, y la revisión de plan §7.1.
>
> **Dos piezas de infraestructura, decididas el 2026-09-13 al arrancar la fase.**
> Las pidió el usuario y cambian el diseño anterior más de lo que parece:
>
> 1. **MinIO** (plan §7.3). No es para las credenciales: es el almacén de los
>    cinco tipos de documento —el XML firmado que se manda, la respuesta firmada
>    de Hacienda, y el comprobante, el acuse y el PDF de los recibidos—. Se
>    levanta en F6 y lo llenan F7 y la recepción. Se construye ahora porque es
>    **de las pocas piezas de F7 que no dependen de la ruta sin decidir**: con
>    proveedor autorizado también hay que custodiar el XML y el acuse.
> 2. **La llave privada va a Vault** (plan §7.1). Cierra la elección de dos
>    adaptadores a uno solo. El efecto que hay que mirar no es que entre Vault
>    sino **lo que se cae**: `p12_encrypted`, `pin_encrypted` y `key_version`
>    dejan de existir, porque el PIN solo sirve para abrir el `.p12` y eso pasa
>    una vez. Y el costo tampoco es el que parece: el negocio de una sola caja
>    ya no tiene un camino sin Vault, así que **un Vault sellado no firma** y el
>    despliegue tiene que abrirlo al arrancar.

> **Dónde va la fase — al 2026-09-19.** Está hecho **todo el backend hasta el
> certificado**: los dos contenedores (T-622, T-623), la migración y los
> secretos (T-601, T-602a, T-602, T-602b, T-603, T-603b, T-604, T-605, T-606,
> T-613, T-618) y la mitad de columna de T-621 y T-617. 1 623 pruebas del
> backend con cobertura 100 % en dominio y aplicación.
>
> **Y el 2026-09-19, T-611, T-612, T-615, T-610 y las pantallas.** Los seis
> endpoints están completos —estado, subir, quitar, ATV, comprobar la conexión
> y el ambiente activo—, el simulado los reproduce y la pestaña de factura
> electrónica de `/configuracion` los recorre entera. 1 672 pruebas del backend,
> 617 del POS y 11 nuevas de punta a punta.
>
> **Y el mismo día, la segunda tanda**: T-608b (el objeto de valor de los
> códigos), T-609 y T-609b (los guardianes de los secretos) y **el backend de
> T-608** —`crud_office.py` y las seis rutas de `/offices`—. 1 731 pruebas del
> backend, 626 del POS.
>
> **Y la tercera: T-608 cerrada.** Las siete rutas de `/offices` en el simulado,
> la pestaña «Sucursales y cajas» de `/configuracion` y cinco pruebas de punta a
> punta. 1 733 pruebas del backend, 626 del POS, 72 de punta a punta.
>
> Falta: T-607 (actividad económica), T-616 (el consecutivo), T-620 (unidad de
> medida), las mitades de pantalla de T-621 y T-617, y T-619, que cierra.

**Costes medidos antes de empezar** —lo que la fase va a hacer saltar, para que
no aparezca a mitad de camino como en F5—:

- **`company_dump.py` tumba `pytest`** en cuanto exista `fe_credentials`:
  `verificar_cobertura()` lanza `SystemExit` ante una tabla sin clasificar. Hay
  que clasificarla **en el mismo commit** que la crea, y la decisión no es
  trivial (plan §7.1, «Decisión pendiente: el respaldo por compañía»).
- **`test_ports.py` fija la superficie de los puertos**: `DocumentSigner` hay
  que declararlo ahí, como pasó con `sold_tax_rates` en T-509.
- **`test_aislamiento.py` exige que ninguna ruta quede sin probar ni declarar**:
  son seis rutas nuevas.
- **El simulado**: seis endpoints con contrato idéntico, o la fase no tiene
  ninguna prueba de punta a punta —que es como se prueba todo lo demás—.
- **Cuatro tareas agregan dominio o aplicación** y la cobertura al 100 % rompe
  la build: el cifrado, el aviso de vencimiento, la derivación del ambiente y
  los códigos de sucursal y terminal.

### La puerta de la fase

> **No hay puerta: T-916 se cerró el 2026-09-13 y el español se queda.** Era la
> única condición que T-913 había dejado para reabrirse —«si F6 toca esas
> tablas»—, F6 las toca, y aun así la respuesta es no. El porqué está en T-916,
> y lo importante para esta fase es lo que se sigue: **T-601 y T-621 escriben
> sobre la mezcla**, `identification_type` queda al lado de `identificacion`, y
> eso no es una deuda anotada sino el estado final.
>
> Lo que sí sigue vigente es la otra mitad: las columnas **nuevas** van todas en
> inglés. La excepción es de las que ya existen, no una licencia (plan §3.9).

### Las cuatro decisiones — resueltas el 2026-09-06

| | Qué se decidió | Dónde vive |
|---|---|---|
| Identificación del emisor | Manda `companies`, con `identification_type` nueva; Configuración la muestra de solo lectura | RN-45, RF-37, T-621 |
| Nombre del ambiente | `'sandbox' \| 'production'`, en inglés; T-614 migra el valor guardado | plan §7.1 |
| Certificación en sandbox | En F6 se avisa y se deja pasar; la puerta dura entra en F7 | RN-46, T-611, T-713 |
| Respaldo y certificado | Va lo público, no los secretos; al restaurar se dice qué falta | RN-47, T-601 |

La de la identificación **le puso precio a T-916**: `companies` tiene sus
columnas en español, así que la columna nueva deja `identificacion` e
`identification_type` una al lado de la otra. O se renombra en la misma
migración, o esa mezcla queda escrita — y es la única decisión que sigue
abierta.

- [x] **T-621** `companies.identification_type` con la lista de Hacienda
      (01/02/03/04), y la identificación **de solo lectura** en Configuración,
      diciendo quién la cambia. RN-45, RF-37.

      Va con T-601, que es la migración de la fase. `business.taxId` y
      `business.taxIdType` quedan como lo que son —dos campos muertos más— y se
      resuelven con los otros cinco en T-614.

      **La columna, hecha el 2026-09-13** en la migración 011, con
      `check_identification_type` en `domain/hacienda.py`. **Falta la pantalla**:
      Configuración sigue mostrando la identificación como un campo editable de
      `settings`, y RF-37 pide que sea la de `companies` y de solo lectura. El
      panel de factura electrónica del 2026-09-19 no la tocó: es la pestaña de
      Negocio, no la de electrónica.

      **Verificación:** un `POST` a `/settings` que traiga `business.taxId`
      **no** cambia la identificación de la compañía. Esconder el campo no es
      control de acceso.

      **La pantalla, hecha el 2026-09-27**, porque T-705 la volvió necesaria: la
      clave lleva la cédula de `companies` y las facturas imprimían la de
      Configuración, así que un mismo papel podía decir dos. Ahora `GET
      /settings/` publica `issuer`, Configuración la muestra sin campo para
      editarla, y `withIssuer` hace que las plantillas impriman esa.

      **Y la puerta de soporte**, que RN-45 nombraba y no existía: `PUT
      /support/companies/{id}/issuer`, con bitácora (`emisor`, con el antes y el
      después), y el formulario en la ficha de la compañía del panel. El alta
      acepta además el tipo, y `bootstrap.py` gana `--identificacion` y
      `--tipo-identificacion`. Se guarda **sin guiones**, que es como va en la
      clave. La verificación de arriba está en `test_numeracion.py`.

### Primero: los campos que ya existen

- [x] **T-614** Los cinco campos muertos de Configuración, decididos **antes**
      de construir encima. `atvUser`, `environment`, `economicActivity`, `branch`
      y `terminal` vivían en el JSON de `settings` sin que nadie los consumiera:
      una pantalla que prometía algo que no pasaba.

      **Hecho el 2026-09-06.** Dos se quedan y tres se van, y el motivo de los
      tres no es que sobren sino que **estaban en el sitio equivocado**:

      | Campo | | Por qué |
      |---|---|---|
      | `environment` | se queda | Es de la compañía y uno solo. El valor guardado pasa de `'produccion'` a `'production'`. Lo consumirá T-610. |
      | `economicActivity` | se queda | Es de la compañía. Lo consumirá T-607. |
      | `atvUser` | **se va** | Es **por ambiente**: el de pruebas y el de producción son credenciales distintas. Va a `fe_credentials`, con su contraseña (T-603b). |
      | `branch` | **se va** | La sesión ya la resuelve —`sucursal_actual()`, y cada venta guarda la suya—. |
      | `terminal` | **se va** | Igual, y además **rota por construcción**. |

      Lo de la terminal es el hallazgo de la tarea y vale escribirlo: hay
      **una sola fila de `settings` por compañía** —lo garantiza
      `uq_settings_company`—, así que dos cajas del mismo negocio declaraban la
      misma terminal. Y dos terminales con el mismo código producen consecutivos
      repetidos, que es rechazo de Hacienda. Era la misma familia de defecto que
      el contador de dos dimensiones, en otro sitio.

      La sucursal y la terminal ahora **se muestran** en Configuración, sacadas
      de la sesión, que es de donde ya salían bien. La pantalla pasa de prometer
      algo que no pasaba a decir algo que es cierto.

      **Verificación:** los tres campos no reaparecen al leer una fila vieja que
      sí los tenía —`settings.test.ts` lo comprueba con la fila de claves en
      español—, y `'produccion'` **se convierte**, no se descarta: descartarlo
      daría `'sandbox'`, y un negocio que ya emitía en producción pasaría a
      pruebas sin que nadie lo pidiera ni lo viera.

### Los dos contenedores

Van primero porque todo lo de la fase se apoya en ellos y porque un adaptador
que nunca corrió contra el servicio de verdad no está entregado —es lo que
T-602b ya decía de Vault, ahora vale para los dos—.

- [x] **T-622** **MinIO y Vault en las dos pilas**: `docker-compose.yml` y
      `docker-compose.test.yml`, con sus variables en `.env.example` y el
      procedimiento en el README de despliegue. Plan §7.1 y §7.3.

      La pila de pruebas los levanta **sin persistencia** —igual que MySQL con
      su `tmpfs`— y Vault en modo `-dev`, que arranca desellado. La de trabajo
      los levanta con volumen con nombre, por lo mismo que `ventasys_db_data`:
      el nombre de la carpeta no puede decidir dónde están los comprobantes.

      **Lo que hay que escribir en el README y no es un detalle**: el respaldo
      pasa a ser **tres** —la base, el bucket y las llaves de apertura de
      Vault—, y Vault arranca **sellado** después de cada reinicio. Un negocio
      que reinicia la VM un viernes y no lo abre deja de firmar sin que nada
      falle a la vista.

      **Verificación:** `docker compose up` con un `.env` al que le falte una
      variable del almacén **no levanta y dice cuál** —es la forma `${VAR:?}`
      que ya usan las demás—, y la pila de pruebas queda arriba con el bucket
      creado y Vault desellado, comprobado desde el contenedor de FastAPI y no
      desde la máquina.

      **Hecha el 2026-09-13.** MinIO `RELEASE.2025-09-07` y Vault `1.20` en las
      dos pilas, con `fe_minio` y `fe_vault` como volúmenes **con nombre** en la
      de trabajo y sin persistencia en la de pruebas.

      **La pila de pruebas monta `transit` sola, desde el compose**
      (`vault-init`). Su Vault es en memoria, así que cada reinicio lo dejaba sin
      motor y la batería de la firma fallaba señalando el adaptador. Habilitarlo
      a mano es justo la clase de paso que nadie recuerda hasta que rompe.

      **Los puertos publicados se parametrizan**, como ya estaba `API_PORT`: en
      la VM de un negocio el 9000 está libre, pero en una máquina de desarrollo
      suele haber otro MinIO y sin eso los dos stacks no conviven.

- [ ] **T-625** **La imagen de MinIO ya no se puede descargar.** Apareció el
      2026-10-02: `quay.io/minio/minio:RELEASE.2025-09-07T16-13-09Z` responde
      401 / «no such manifest», igual que `:latest` en quay y la misma etiqueta
      en Docker Hub. Una máquina que no la tenga en caché —la VM de un negocio,
      un desarrollador nuevo— no levanta la pila. En la de Antony se salvó
      re-etiquetando una `minio/minio:latest` local que resultó ser
      exactamente esa versión. Hay que decidir de dónde sale la imagen (otra
      fuente, una construida y publicada por nosotros, o un almacén S3
      compatible distinto) sin perder lo que T-623 comprobó contra esta versión
      (`IfNoneMatch=*` devuelve 412).

      **Verificación:** con la imagen borrada de la caché local,
      `docker compose up -d --build` en las dos pilas la descarga y la batería
      del almacén pasa.

- [ ] **T-626** **`seed.py` calcula el IVA al 13 % fijo** y el backend le
      rechaza con `totals_mismatch` toda venta que lleve un producto
      clasificado con otra tarifa: de 35 pedidas entraron 11, y las demás
      fallan sin decir por qué. Tiene que calcular con la tarifa de cada
      producto (la que ya devuelve `products_list`) e informar las que fallan
      con su código.

      **Verificación:** `python seed.py --ventas 35` contra una base nueva
      registra las 35.

- [x] **T-623** Puerto `DocumentStore` y adaptador de S3 (`boto3`), con la
      **derivación de la llave en el dominio**. Plan §7.3.

      La ruta es `{company_id}/{environment}/{kind}/{yyyy}/{mm}/{clave}.{ext}` y
      la arma el servidor: quien llama pasa el hecho, no la ruta. Es la misma
      frase que ya rige el nombre de la llave de Vault y el dato asociado del
      AES-GCM, y por tercera vez el motivo es el mismo —una ruta escribible deja
      que la compañía 7 lea el comprobante de la 3—.

      **Se escribe una vez**: la subida va con `If-None-Match: *` y la segunda
      escritura de la misma llave es un error, no un reemplazo. Un XML firmado
      que cambia deja de ser el que se firmó, y un reintento de la cola que
      llegue tarde no puede pisar el acuse bueno con uno viejo.

      **Verificación:** prueba de contrato para el puerto —el precedente es
      T-106— y de integración contra el MinIO de T-622: subir dos veces la misma
      llave falla, `company_id` distinto da rutas que no se pisan, y lo que baja
      es **byte por byte** lo que subió. Esto último no es una obviedad: es la
      propiedad de la que depende que una firma verifique cinco años después.

      **Hecha el 2026-09-13**, en `infrastructure/storage/s3_documents.py`, con
      una sola batería (`test_almacen_documentos.py`) que corren **las dos
      implementaciones** —el doble en memoria y el MinIO de verdad—. Es el patrón
      de T-106: sin eso nadie sabría si el puerto admite dos hasta el día de
      escribir la segunda.

      **«Se escribe una vez» es del almacén y no del código.** Con
      `IfNoneMatch="*"` la segunda escritura devuelve **412** y el contenido
      original no se toca. Un `head_object` antes del `put` tiene carrera; esto
      no.

      **El año y el mes salen de la propia clave**, no de un parámetro, para que
      el mismo documento no pueda quedar archivado en dos meses según quién lo
      guarde. Y **el ambiente va en la ruta** porque la clave se arma con el
      consecutivo y pruebas y producción se numeran aparte: sin ese tramo, un
      tiquete de ensayo pisa una factura de verdad.

      **El puerto no lleva `delete`, y la ausencia es la decisión.** Estos
      documentos se custodian por ley: borrar uno es mantenimiento con su propio
      plazo, no una operación de la aplicación.

### Secretos

- [x] **T-601** Tabla `fe_credentials` con llave primaria
      **`(company_id, ambiente)`** (plan §7.1). Guarda las dos credenciales: la
      de firma y la de transmisión. RN-33.

      No es `company_id` a secas: con eso, pasar a producción significaba borrar
      lo de pruebas y quedarse sin poder volver.

      **Las columnas van en inglés.** Es la tercera vez que el proyecto tropieza
      con lo mismo —T-401 lo corrigió en F4, la 006 en F5— y acá el diseño lo
      inducía. plan §3.9: la excepción es de las columnas que ya existen, «no
      una licencia para las nuevas».

      Hereda `TenantMixin`, con `PrimaryKeyConstraint('company_id',
      'environment')` y no `primary_key=True` suelto. **Verificación:**
      `test_esquema.py` compara modelo y migración desde T-919, así que basta
      con que las dos digan lo mismo.

      **Tres columnas del boceto ya no existen**, por la decisión del
      2026-09-13 de llevar la privada a Vault: `p12_encrypted`, `pin_encrypted`
      y `key_version`. La de firma que queda es `certificate_pem`, que es
      pública y viaja sin cifrar dentro de cada XML.

      **La clasificación en `company_dump.py` va en este mismo commit, y es por
      columna y no por tabla** (RN-47, decidido el 2026-09-06): viajan el
      certificado público, el usuario de ATV y las fechas; no viaja la
      contraseña. Eso es lo que el guardián no contempla hoy, así que hay que
      enseñárselo — clasificar la tabla entera en un lado o en el otro es justo
      lo que la decisión descarta. Con Vault queda **una sola** columna que
      descartar a mano, y no tres.

      **Verificación:** un volcado no contiene la contraseña —se busca a
      propósito, como en T-609— y al restaurar la pantalla enumera lo que hay
      que volver a cargar, **incluido el certificado**: su llave hay que
      importarla al Vault de destino, y eso solo pasa volviendo a subir el
      `.p12`.

      **Hecha el 2026-09-13**, migración `011-factura-electronica.sql`. Dos
      tablas y dos columnas: `fe_credentials`, `fe_sequences`, y el tipo de
      identificación del emisor (T-621) y del receptor (T-617).
      Corrida **completa contra MySQL de verdad**, que es lo que `create_all` no
      comprueba.

      **`fe_sequences` tiene cinco dimensiones y no menos.** La secuencia es
      dentro del tipo de comprobante: con un contador por terminal, emitir
      tiquete, factura, tiquete deja los tiquetes en 1, 3, 5 y las facturas en
      2, 4 — y «consecutivo fuera de orden» es rechazo. El ambiente entra en la
      llave porque pruebas y producción son dos series.

      **`company_dump.py` aprendió a clasificar por columna**, que es lo que no
      sabía hacer (`COLUMNAS_DESCARTADAS`). Viaja todo menos
      `atv_password_encrypted`.

      **El `VARBINARY` y el `LONGTEXT` del boceto se cambiaron por `VARCHAR` y
      `TEXT`**: `LargeBinary(512)` compila a BLOB y no a VARBINARY, así que el
      modelo y la migración no podían decir lo mismo sin un tipo propietario, y
      eso es lo que `test_esquema.py` exige desde T-915. El certificado PEM son
      2 KB: en TEXT caben de sobra.

      **El tipo de los clientes que ya existen se deduce de la longitud.** El 04
      (NITE) también son diez dígitos y no hay forma de distinguirlo del 02
      mirando el número; se elige jurídica porque es órdenes de magnitud más
      común y quien tenga un NITE lo corrige una vez. NULL sería más honesto
      pero dejaría a todos los clientes de empresa sin tipo el día de facturar.

- [x] **T-602a** Cifrado en reposo: AES-256-GCM, `FE_CRYPTO_KEY`, con
      `(company_id, environment)` como dato asociado.

      **Le queda un solo cliente: la contraseña de ATV.** No es un digest que se
      firme sino un secreto que hay que **replayar** al IdP en cada token
      (`grant_type=password`), así que se guarda y se lee, y eso Vault transit no
      lo hace. El `.p12` y el PIN ya no pasan por acá.

      **Verificación:** una fila copiada a otra compañía —o al otro ambiente de
      la misma— **no descifra**. Es lo que verifica RF-22 y RNF-5, y lo necesita
      T-603b en esta fase.

      **Hecho el 2026-09-13** en `infrastructure/crypto/fe_crypto.py`, con
      `test_cifrado_fe.py`. El dato asociado es `(company_id, environment)`, así
      que la fila copiada no descifra y el fallo es de autenticación, no de
      formato.

- [x] **T-602** Puerto `DocumentSigner` —`sign(digest, company_id, environment)`
      e `import_key(pkcs8, company_id, environment)`— con **prueba de
      contrato**.

      El puerto no está para elegir entre Vault y otra cosa —eso ya se decidió—
      sino porque §7.2 deja abierta la ruta de emisión: si la firma termina
      pasando por un proveedor autorizado, cambia el adaptador y no el caso de
      uso. Y porque con contrato la firma se puede probar sin Vault levantado.

      Compañía y ambiente van explícitos y **no en un `ContextVar`**: con estado
      escondido, el caso de uso no se puede probar contra «firmá esto con el de
      pruebas» y el trabajador de fondo no tiene contexto que heredar.

      **Verificación:** la prueba de contrato la pasan el doble de las pruebas y
      el adaptador de T-602b, la misma batería para los dos. El precedente es
      T-106.

      **Hecho el 2026-09-13** (`application/ports/signing.py`,
      `test_firma_fe.py`). **La prueba no comprueba que devuelva bytes sino que
      la firma verifique con el certificado público**, que es lo único que le
      importa a Hacienda y lo único que delata una llave equivocada.

- [x] **T-602b** Adaptador de **Vault transit**: la llave privada se importa al
      subir el `.p12` y **nunca entra en memoria de la aplicación** después.
      Entra **dentro** de la fase —ya no «puede ir después»—: desde el
      2026-09-13 es el único adaptador, así que sin él no se firma.

      **El nombre de la llave se DERIVA de `(company_id, environment)`, no se
      guarda.** Un campo escribible ahí deja que la compañía 7 apunte a la llave
      de la 3 y emita firmado con el certificado de otro cliente.

      **Verificación:** la prueba de contrato de T-602, más una de integración
      contra el Vault en modo `-dev` de T-622. Sin eso se entrega un adaptador
      que nunca corrió. Y una que comprueba lo que hace valiosa la decisión:
      **firmar con la llave de la compañía 1 y verificar con el certificado
      público de la 2 falla**.

      **Hecho el 2026-09-13** en `infrastructure/crypto/vault_signer.py`, contra
      Vault 1.20.4 de verdad.

      **El BYOK es de tres pasos y hay que hacerlo completo**: se pide la llave
      de envoltura de Vault, se sortea una AES-256 efímera, se envuelve la
      privada con ella (AES-KWP) y se cifra la efímera con la RSA-4096 de Vault.
      La efímera existe porque una RSA-4096 **no puede cifrar directamente** una
      PKCS#8 de 2048 bits: OAEP deja unos 446 bytes útiles y la llave pasa de
      1 200.

      Tres cosas aparecieron corriéndolo y ninguna se deduce de la
      documentación:

      - **Firmar sin llave contesta 400 y no 404**, con el texto «signing key
        not found». Se resuelve **preguntando si la llave existe** en vez de
        leer ese texto, que puede cambiar entre versiones. La diferencia no es
        cosmética: `SigningUnavailable` significa «reintentá» y
        `SigningKeyMissing` significa «andá a cargar el certificado», y
        confundirlas deja la cola reintentando para siempre un documento que no
        va a firmarse nunca.
      - **Configurar una llave que no existe también contesta 400**, así que
        quitar dos veces parecía una falla de Vault. Se consulta antes.
      - **Reemplazar el certificado va por `import_version` y no por `import`**:
        importar sobre una llave que ya está es un error, y tratarlo como tal
        obligaría a borrar antes — o sea a dejar una ventana en la que la
        compañía no puede firmar.

- [x] **T-603** Subida del `.p12` y el PIN, browser → BFF → FastAPI. RF-22.
      Es de **administrador**: así el bloqueo por suscripción la alcanza sin
      tocar nada.

      **Es el único momento en que el `.p12` y el PIN existen.** La petición
      abre el archivo en memoria, saca el certificado público y la privada,
      **importa la privada a Vault** (T-602b), guarda la fila con lo público y
      descarta el resto. Ni el archivo ni el PIN llegan al disco ni a la base.

      El orden es **primero Vault, después el `COMMIT`**: son dos sistemas sin
      transacción común, y hay que elegir cuál de los dos desenlaces malos se
      prefiere. Una llave importada sin fila es inofensiva —la pisa la próxima
      subida—; una fila que dice «tiene certificado» sin llave en Vault rompe al
      firmar, que es el peor momento posible.

      **Verificación:** un PIN que no abre el `.p12` **no se guarda** —ni él ni
      nada—, y después de una subida buena, buscar el PIN en la base **no lo
      encuentra en ninguna columna**. T-606 abre el archivo igual para leer el
      vencimiento, así que la validación sale gratis y evita enterarse el día de
      facturar.

      **Hecha el 2026-09-13**, el backend: `POST /fe/{ambiente}/certificate`,
      con `infrastructure/crypto/pkcs12_reader.py` y `test_lector_p12.py`. Que
      el PIN no se guarde **dejó de ser disciplina**: no hay columna donde
      ponerlo.

      **`cryptography` no distingue un PIN malo de un archivo corrupto**: lanza
      el mismo `ValueError`. Lo que sí se distingue —y es lo que importa, porque
      lo que hay que hacer es distinto— es **haber subido otra cosa**: un
      `.cer`, un ZIP, un PDF. Se mira el primer byte, que en DER es siempre una
      SEQUENCE.

      **La pantalla, hecha el 2026-09-19.** El mismo formulario sube y
      reemplaza, porque `import_version` de Vault deja la llave nueva en uso sin
      una ventana en la que la compañía no pueda firmar: dos caminos habrían
      sido dos nombres para lo mismo.

      **El campo del PIN se vacía al enviarlo** (`reset: true`). Lo encontró la
      prueba de punta a punta buscando la contraseña de ATV: el servidor no la
      devuelve nunca —no la tiene— pero el navegador se quedaba con lo tecleado,
      y eso es guardar en la pantalla justo lo que el sistema entero se ocupa de
      no guardar en ningún lado.
- [x] **T-603b** Usuario y contraseña de ATV, por ambiente. La contraseña recibe
      **el mismo trato que el PIN**; el usuario sí se muestra, porque es un
      identificador y sin verlo nadie puede comprobar que escribió el que era.
      RF-29, RN-16.

      **Hecha el 2026-09-13**, el backend: `PUT /fe/{ambiente}/atv`, con la
      contraseña cifrada por T-602a.

      **Cambiar la contraseña invalida la verificación anterior.** Sin eso, la
      pantalla seguiría diciendo «verificadas el 3 de septiembre» sobre algo que
      se cambió hoy y que nadie probó — y eso es peor que no decir nada: invita
      a no probarla.
- [x] **T-604** `GET` devuelve solo `{ambiente, certificado_configurado,
      nombre_archivo, vence_el, subido_el, atv_usuario, atv_configurado}`.
      **No existe** endpoint que devuelva el archivo, el PIN ni la contraseña.
      RF-23, RN-16.

      **Hecho el 2026-09-13**: `GET /fe` devuelve el estado de **los dos
      ambientes** de una vez, que es lo que T-610 va a pintar.

      **«Listo» son tres condiciones y la tercera se olvida.** Un certificado
      vencido está configurado y no sirve; una pantalla que mostrara
      «certificado ✓ · ATV ✓» sin mirar la fecha diría que todo está listo el
      día que dejó de estarlo. Lo decide `domain/fe_credentials.py`, para que la
      pantalla no tenga una segunda definición.
- [x] **T-605** Reemplazar y quitar el certificado. RF-24. De administrador.

      Quitar **también quita la llave de Vault**, y ese es el orden inverso al
      de T-603: primero el `COMMIT` de la fila, después Vault. Una llave
      huérfana en Vault no firma nada —no hay fila que la nombre— mientras que
      una fila que dice «tiene certificado» sobre una llave ya borrada vuelve al
      mismo fallo al firmar.

      **Verificación:** reemplazar deja `cert_uploaded_at` nuevo y **no toca**
      las marcas de ATV; quitar no borra las credenciales de transmisión; y
      después de quitar, firmar con esa compañía falla **por no haber llave**,
      no por una firma inválida.

      **Hecha el 2026-09-13**: `DELETE /fe/{ambiente}/certificate`, y reemplazar
      es la misma subida de T-603 sobre una fila que ya está.

      **El orden entre los dos sistemas es el inverso al de T-603**, por el
      mismo criterio: acá primero el `COMMIT` y después Vault. Una llave
      huérfana en Vault no firma nada —no hay fila que la nombre—; una fila que
      dice «tiene certificado» sobre una llave ya borrada vuelve al mismo fallo
      al firmar. En los dos sentidos se trata de que **nunca exista una fila que
      prometa más de lo que hay**.
- [x] **T-606** Leer el vencimiento del propio `.p12` al subirlo, y avisar 30
      días antes. Sin dependencia nueva: `cryptography` ya está y sabe leer
      PKCS#12 —comprobado el 2026-09-05 en el contenedor, versión 50.0.1—.

      La aritmética de fechas entra por el puerto `Clock`, no por
      `date.today()`: es dominio y tiene cobertura obligatoria.
      **Verificación:** con el reloj falso en el día 31 no avisa y en el 30 sí.

      **Hecha el 2026-09-13** en `domain/fe_credentials.py` (`days_left`,
      `certificate_status`).

      **El vencimiento hay que convertirlo a hora local.** `cryptography`
      devuelve UTC con zona y todo el resto del sistema trabaja en hora local
      sin zona: compararlo con `Clock.now()` lanzaría `TypeError`, y guardarlo
      en UTC haría que un certificado que vence a las 18:00 se mostrara
      venciendo al día siguiente.

### Ambiente

- [x] **T-610** Elegir ambiente y ver, para cada uno, si ya tiene certificado y
      credenciales. RF-30.

      **Hecha el 2026-09-19.** Una tarjeta por ambiente con su certificado, su
      vencimiento, sus credenciales y un distintivo de «listo» o «incompleto»;
      arriba, cuál está en uso y con qué consecuencia. El estado lo decide el
      dominio (`ready`) y la pantalla lo pinta: una segunda definición de
      «listo» en el marcado es cómo se acaba diciendo que todo está bien el día
      que el certificado venció.

      **Los dos ambientes se ven siempre**, tenga fila o no. Con solo los
      configurados, «pruebas no está configurado» sería indistinguible de «no
      vino el dato», que es la mitad de lo que RF-30 pide.
- [x] **T-611** Pasar a producción **se confirma y queda en bitácora** (RN-35).
      Es el momento en que los documentos dejan de ser un ensayo.

      **Avisa de la certificación de Hacienda y no la impide** (RN-46, decidido
      el 2026-09-06): la confirmación enumera la factura, el tiquete y la nota
      de crédito que §12 exige haber emitido en pruebas. La puerta dura es
      T-713, en F7, que es cuando existen documentos que contar.

      **Verificación:** la entrada lleva el antes y el después —«sandbox →
      production»—, como la de T-305, y no «cambió el ambiente». Volver a
      pruebas también se registra: es el cambio que hace que las facturas dejen
      de tener efecto fiscal sin que nadie lo note.

      **Hecha el 2026-09-19**, las dos mitades: `PUT /fe/active`, con
      `needs_confirmation` en el dominio y la línea de bitácora `fe_ambiente` en
      el mismo `commit` que el cambio, y el diálogo con el aviso de RN-46 —la
      factura, el tiquete y la nota de crédito que §12 exige haber emitido en
      pruebas—, que **avisa y no impide**.

      **La confirmación es del servidor y no de la pantalla.** Un `confirm` que
      solo viviera en un modal no cumple RN-35: lo que la regla dice es que esto
      «no puede ocurrir por haber tocado un desplegable sin querer», y un
      desplegable que hace `PUT` es exactamente eso.

      **Y hubo que cerrar la puerta lateral, que era la mitad del trabajo.**
      `save_settings` reemplaza el JSON entero con lo que manda el POS, así que
      el ambiente se podía cambiar guardando la pantalla de Configuración — sin
      confirmar y sin bitácora. Con eso, RN-35 era decoración. Ahora hay
      `PROTECTED_PATHS` en `crud_settings` y una sola puerta que escribe:
      `write_protected`, que además **exige que el campo esté en la lista**, así
      que sacarlo de ahí rompe en vez de convertirse en una segunda vía
      silenciosa.

      **Se conserva lo guardado en vez de rechazar la petición**, y esa
      diferencia importa: el POS manda la configuración completa en cada
      guardado, así que rechazar obligaría a la pantalla a conocer la lista para
      no incluirlos. Hay prueba de los dos lados —mandarlo no lo cambia, y
      **omitirlo no lo borra**—; lo segundo es lo que pasaría con una versión
      del POS que no conozca el campo.

      **Defecto encontrado de paso:** `_activo` leía
      `get_settings(db).get("eInvoicing")`, pero ese diccionario tiene el JSON
      adentro de `data`, así que **siempre** devolvía `sandbox`. Era invisible
      porque hasta hoy no había forma de poner otra cosa; T-611 lo hizo visible
      el mismo día que lo habría hecho falso.
- [ ] **T-625** Un campo protegido **no tapa la forma vieja** de la
      configuración. Por decidir con el usuario; apareció el 2026-10-03 al
      cerrar F7.

      `eInvoicing.environment` se escribe por `write_protected` y
      `_conservar_protegidos` lo repone en cada guardado, así que una compañía
      que todavía guarda `electronica.activa` —de antes de T-113— y toca «Pasar
      a producción» o «Volver a pruebas» queda con `eInvoicing:
      {"environment": …}` y nada más. Y la regla de lectura es «manda la clave
      nueva si está, aunque no sirva» (`_seccion_electronica` en el backend,
      `legacy()` en el POS): la facturación aparece **apagada** en las dos
      aplicaciones, sin error. La venta sale sin tipo y sin comprobante hasta
      que alguien vuelva a guardar la pantalla.

      Hoy no afecta a nadie —no hay compañía real anterior a T-113—, pero «una
      fila vieja tiene que seguir queriendo decir lo mismo» ya no se cumple en
      ese caso. Dos salidas, cada una con su costo: que la lectura caiga a
      `electronica` **campo por campo** cuando la clave nueva no trae `enabled`
      (cambia la regla en los dos lados), o que `write_protected` traduzca la
      sección vieja a la nueva al crearla (el backend aprende los nombres
      viejos). No se decidió dentro de F7.

      **Verificación:** `test_la_forma_vieja_de_la_configuracion_tambien_cuenta`
      sobre una compañía que **ya** cambió de ambiente. Hoy corre sobre una
      recién dada de alta, que es la única donde la forma vieja sigue
      existiendo; la compañía A de la batería pasó a producción y volvió en
      `test_emision.py`, y por eso dejó de servir para esa prueba.
- [x] **T-613** `client_id`, realm y URL base **se derivan del ambiente en un
      solo sitio**, y salen de configuración y no del código. Mitigación del
      riesgo TRIBU-CR (plan §7.1 y §10).

      Va **antes** de T-612, que es su consumidor: al revés, T-612 los escribe a
      mano y T-613 se convierte en un refactor que hay que ir a buscar por el
      código. Es una función pura: dominio, con prueba.

      **Verificación:** una prueba tumba `pytest` si `comprobanteselectronicos.go.cr`
      aparece escrito fuera de ese módulo. Mismo patrón que `test_error_codes.py`.

      **Hecho el 2026-09-13** en `domain/hacienda.py`, con
      `test_dominio_de_hacienda.py`.

      **El guardián se cazó a sí mismo al escribirlo**: `/realms/rut` no
      aparecía en el texto porque el realm estaba partido entre dos literales y
      escrito dos veces —en su campo y dentro de la URL—. Ahora la URL se
      construye a partir del realm, así que hay un solo sitio donde cambiarlo.

      Y cazó de paso el correo de ejemplo de ATV escrito completo en dos
      docstrings: un ejemplo también envejece.

- [x] **T-612** Comprobar que las credenciales del ambiente sirven, **sin emitir
      nada**. RF-31.

      Es la única comprobación que no produce un documento, y sin ella la
      primera noticia de que la contraseña está mal llega el día que hay que
      facturar.

      **Verificación:** adaptador tras puerto, con doble en las pruebas y **tres
      casos distinguibles**: credenciales buenas, malas, e IdP inalcanzable. El
      tercero **no** puede reportarse como el segundo (RF-31). Tiempo de espera
      explícito, como el adaptador de CABYS. Más una comprobación en vivo
      anotada, como se hizo con T-502.

      **Hecha el 2026-09-19**: puerto `HaciendaIdp`, adaptador
      `HaciendaKeycloakIdp`, caso de uso `VerifyAtvCredentials`,
      `POST /fe/{ambiente}/atv/verify` y el botón, que queda deshabilitado
      mientras no haya credenciales que comprobar.

      **Comprobar es pedir un token y tirarlo.** No hay otra forma —Hacienda
      autentica con `grant_type=password`— y es justo lo que hace que la
      comprobación no emita nada. El puerto **devuelve el token** aunque T-612
      no lo use: F7 lo necesita para transmitir, y un puerto que devolviera
      `bool` habría que cambiarlo entonces.

      **El 400 de Keycloak es un rechazo y no una avería.** `invalid_grant`
      —una contraseña mal escrita, que es el caso más común de todos— viaja con
      **400**, no con 401. Leerlo como avería lo habría convertido en «no se
      pudo comprobar», y nadie se habría enterado nunca de que su contraseña
      está mal.

      **Pero decidir por el código de estado estaba mal, y la comprobación en
      vivo del 2026-09-19 lo destapó.** El IdP de Hacienda está detrás de
      **Cloudflare**, que tiene baneada la firma por omisión de `urllib` y
      contesta **403, «Error 1010: browser_signature_banned»**, sin que la
      petición llegue a Keycloak. Con `exc.code in (400, 401, 403)` eso se leía
      como «Hacienda rechazó sus credenciales» —con credenciales buenas— y
      encima el caso de uso borra la verificación anterior al recibir un
      rechazo: un bloqueo de red tiraba una comprobación buena. Es exactamente
      el error que RF-31 existe para no cometer.

      Ahora **decide el cuerpo**: solo `{"error": "invalid_grant"}` es un
      rechazo. Un 403 de Cloudflare, un 500 de Hacienda y un `invalid_client`
      —que sería culpa nuestra— son los tres «no se pudo comprobar». Ante la
      duda se elige ese lado: equivocarse ahí cuesta reintentar, y hacia el otro
      cuesta que alguien cambie una credencial que estaba bien. Y se manda
      `User-Agent`, configurable con `FE_HACIENDA_USER_AGENT`.

      **La batería no podía ver ninguno de los dos.** Su Keycloak de mentira
      contesta lo que uno le dice que conteste, así que las ocho pruebas del
      rechazo pasaban: el problema no estaba en Keycloak ni en el código que le
      habla, sino en un intermediario cuya existencia no se sabía. Un servidor
      de mentira prueba la traducción; no prueba el trayecto. La regresión usa
      ahora el cuerpo exacto que contestó Cloudflare —JSON válido y **sin**
      campo `error`—, que es lo que hay que saber distinguir.

      **Son cuatro códigos y no tres**, porque antes de los tres desenlaces hay
      dos cosas que pueden fallar sin llegar a preguntarle a Hacienda:
      `atv_not_configured` —no hay nada que comprobar todavía, que no es «no
      sirven»: no hay nada que corregir, hay algo que escribir— y
      `atv_password_unreadable`, cuando la guardada no descifra porque la llave
      se rotó o la fila vino de otra instalación.

      **Un rechazo borra la verificación anterior; una avería no.** El «no» de
      Hacienda es más fuerte que cualquier marca vieja, y dejarla haría que la
      pantalla dijera «verificadas el 13 de septiembre» sobre unas credenciales
      que acaban de demostrar que no sirven — que es el letrero que hace que
      nadie las vuelva a probar. Con «no se pudo comprobar» es al revés: no se
      aprendió nada, y tirar una verificación buena porque Hacienda estaba caída
      sería convertir su caída en un problema del cliente. Por eso el puerto pasó
      de `mark_verified` a `set_verified`, que admite `None`.

      **La traducción de HTTP a desenlace se prueba contra un Keycloak de
      mentira** (`test_idp_fe.py`, con `http.server`): es lo único que no se
      puede provocar en vivo —un 500 de Hacienda hay que esperar a que ocurra—
      y es donde el error cuesta caro. La comprobación en vivo queda **anotada y
      pendiente** en la cabecera de ese archivo, con qué mirar: que el 400 traiga
      `invalid_grant`, y cuánto tarda, para saber si 15 s sobra o falta.

      **`endpoints()` estrena consumidor.** Lo escribió T-613 y hasta hoy no lo
      usaba nadie; `endpoints_for` es la mitad que faltaba —leer los *overrides*
      del entorno—, y va en el adaptador para que la derivación pura se siga
      probando sin tocar variables.

### El resto de la preparación

- [ ] **T-607** Consulta de actividad económica contra
      `GET /fe/ae?identificacion=` desde Configuración. RF-25.

      **Verificación:** el 404 de Hacienda viene **con un mensaje en inglés**
      (plan §6.1). Mostrarlo tal cual viola RN-30, así que se traduce a código y
      la frase se arma en el POS.
- [x] **T-608** Administración de sucursales y terminales: ABM con los límites
      del plan (`max_sucursales`, `max_terminales`), y una sucursal con ventas
      **se desactiva, no se borra** —RN-7 aplicada acá—. RF-26.

      **Verificación:** crear una sucursal de más responde `plan_limit_reached`
      con su cuenta, como ya hace `domain/limits.py` desde T-309.

      **Hecha el 2026-09-19.** El backend: `crud_office.py`, siete rutas bajo
      `/offices` y `tests/test_sucursales.py` con 25 pruebas. El POS: las siete
      rutas en `mock/handler.ts`, la pestaña «Sucursales y cajas» de
      `/configuracion` y `tests/e2e/sucursales.spec.ts` con cinco pruebas.

      **La pestaña va en Configuración y no en el menú.** Es configuración de la
      empresa y vive donde se busca; un ítem propio en el menú sería una sección
      más para algo que se toca dos veces al año.

      **En esa pestaña no se ofrece «Guardar cambios».** Las otras cuatro son un
      solo formulario y acá cada sucursal y cada caja se guardan en su diálogo:
      un botón que promete guardar lo que se está mirando y guarda otra cosa es
      peor que no tenerlo.

      **Defecto encontrado desde la pantalla**: `_ultima_terminal_no` no miraba
      si la caja ya estaba apagada, así que borrar la de repuesto respondía
      `last_active_terminal` —había que encenderla para poder borrarla—. Desde
      el API no se nota; borrar algo que ya no está en uso es lo que se pide con
      la lista delante. Corregido, con sus dos pruebas.

      **En el simulado la historia se atribuye por código**, porque las ventas
      de ahí no llevan `branch_id`: una sucursal arrastra historia si su código
      es el que declara la sesión (`companies.branch_code`), y una caja si
      coinciden **los dos** códigos, el suyo y el de su sucursal. Con uno solo,
      el «00001» de un local nuevo heredaba las ventas del «00001» de la casa
      matriz y nacía imposible de borrar.

      **Se cuentan las activas, no las filas**, y la contrapartida está escrita
      y aplicada: **reactivar consume cupo**. Contar las desactivadas castigaría
      al que ordena sus locales; no contarlas sin la otra mitad haría que
      desactivar y reactivar fuera la forma de tener cinco con un plan de tres.

      **Dos puertas más que no pedía la tarea y hacen falta**: no se deja a la
      compañía sin sucursal activa ni a una sucursal sin caja activa. Una
      compañía sin caja no puede vender, y el POS lo descubriría con un cliente
      enfrente en vez de con alguien configurando.

      **Desactivar una sucursal apaga sus cajas.** Si no, el POS las ofrecería y
      el consecutivo saldría de un local cerrado.

      **El código no se puede cambiar después de creado** y por eso no está en
      los esquemas de actualización: moverlo cambiaría el número de todos los
      comprobantes ya emitidos desde esa sucursal.

      **El dato del «no» se llama `branch_code`, no `code`.** Es la segunda vez
      que el proyecto tropieza con lo mismo —`code` es el nombre del parámetro
      de `api_error`— y la primera vez costó un 500 en vez de un 409. Ya estaba
      escrito en `api_errors.py` para `account_code`; ahora también acá.

- [x] **T-608b** Los códigos de 3 y 5 dígitos como **objeto de valor**, con su
      UNIQUE por compañía. RN-15. Es dominio: `Barcode` es el precedente.

      **Verificación:** «1» se guarda como «001» y «abc» no se guarda.

      **Hecho el 2026-09-19** en `domain/office.py`, con 25 pruebas. El UNIQUE
      ya existía desde F2; lo que faltaba era que el valor llegara normalizado,
      que es de lo que sirve: sin rellenar, «1» y «001» son dos filas distintas
      con el mismo número en el comprobante, y el índice no las ve iguales.

      **Se miden los dígitos significativos, no la longitud del texto.**
      «00001» con tres dígitos es 1 y cabe; «1234» no cabe de ninguna manera y
      **no se recorta** — recortar en silencio sería cambiarle el número a
      alguien, que es justo el defecto que el tipo existe para no tener.

- [x] **T-616** Arranque del consecutivo: la oficina y la última secuencia **por
      tipo de comprobante**, para el negocio que ya venía facturando con otro
      sistema. RF-32, RN-36 a RN-38.

      No es un número sino uno por tipo: las facturas llevan su serie y los
      tiquetes la suya, y un negocio que emitió 4 200 facturas y 15 300 tiquetes
      tiene que poder decir las dos.

      **Verificación:** el valor **solo sube**. Bajarlo significa volver a
      emitir números ya usados —rechazo seguro— así que se rechaza y queda en
      bitácora el intento.

      **Hecha el 2026-10-03 (QA-07).** Por caja y por tipo encendido, en el
      ambiente en uso, desde Configuración → Factura electrónica.
      `check_sequence_start` en el dominio; `GET/PUT /fe/sequences`; una serie
      con la que el sistema ya emitió no se toca (`sequence_in_use`) y bajarla
      es `sequence_cannot_go_down`; cada cambio queda en bitácora como
      `serie_arranque`. Lo que queda en bitácora es el cambio, no el intento
      rechazado. Pruebas: `test_fe_key.py`, `test_series_fe.py`,
      `series.spec.ts`.
- [x] **T-609** Comprobar que el PIN **y la contraseña de ATV** no aparecen en
      respuestas, ni en bitácora, ni en trazas de error. Buscarlos a propósito.

      Va como prueba y no como revisión a mano, por lo mismo que el resto de los
      guardianes: una comprobación que hay que acordarse de repetir no protege
      nada. Lo que se busca es el valor literal en el cuerpo de cada respuesta
      del API, en `audit_log` y en el texto de las excepciones.

      **La mitad del PIN cambió de carácter el 2026-09-13**: ya no se guarda en
      ninguna parte, así que lo que hay que comprobar no es que no se devuelva
      sino que **no sobreviva a la petición que lo trajo** — se busca en las
      tres tablas y en las trazas después de una subida buena. Lo que no está no
      se filtra; lo que hay que verificar es que de verdad no está.

      **Hecho el 2026-09-19**, y **no en tres tablas sino en todas**: el
      buscador recorre cada columna de texto de cada tabla del esquema. Una
      lista escrita a mano no puede contener la columna en la que nadie pensó,
      que es justamente la que hay que descubrir. Corre dentro del contenedor,
      como `test_respaldo_compania.py`, porque la base de la pila de pruebas no
      publica puerto.

      **Con su prueba de la prueba**: se busca el **usuario** de ATV, que sí se
      guarda en claro a propósito (RN-16), y tiene que aparecer. Sin eso, un
      buscador roto —una consulta que no devuelve nada nunca— dejaría las otras
      dos en verde para siempre.

      Y las trazas: se provoca el fallo más propenso a contarlo —un PIN que no
      abre el archivo— y después se leen los registros del contenedor.

- [x] **T-609b** La mitad positiva de la bitácora: **se registra que se usaron**,
      nunca su contenido (plan §7.1). Hoy el único uso es T-612.

      **Hecho el 2026-09-19**: `fe_credenciales_probadas`, con el ambiente y el
      desenlace —«aceptadas», «rechazadas por Hacienda», «sin respuesta de
      Hacienda», «no se pudo descifrar»— y sin el usuario ni un fragmento de la
      contraseña.

      **Se anotan los cuatro desenlaces y no solo el bueno.** La pregunta que se
      hace seis meses después no es «probó alguna vez» sino «desde cuándo esto
      no funciona», y esa la contestan los «no». El único que **no** se anota es
      «no había credenciales»: no se usó ninguna, y una línea ahí diría que se
      probó algo que no existe.

      Confirma dentro del propio servicio y no en el endpoint, porque tres de
      los cuatro desenlaces terminan en excepción: sin `commit`, la línea que
      explica el fallo se iría con la sesión justo en el caso que hacía falta
      narrar.

- [x] **T-624** Los cinco códigos de error de F6 del lado del POS:
      `invalid_certificate`, `certificate_too_large`, `invalid_environment`,
      `atv_user_required` y `signing_unavailable`.

      Apareció al cerrar la mitad de backend de la fase: **`npm test` estuvo en
      rojo a propósito** entre el 2026-09-13 y el 2026-09-19.
      `messages.test.ts` compara las dos listas de códigos entre sí y estos
      cinco solo existían en `api_errors.py`.

      **Hecha el 2026-09-19** en los tres sitios de siempre —`API_CODES`, los
      catálogos `errors.json` de los tres idiomas, y el `switch` de
      `$lib/ui/messages.ts` que termina en `never`—. El cuarto, el simulado, es
      T-615.

      **`invalid_certificate` son cinco frases y no una.** El backend separa los
      cuatro motivos (`bad_pin`, `not_a_p12`, `no_private_key`,
      `no_certificate`) justamente porque lo que hay que hacer es distinto en
      cada uno, y colapsarlos en el POS tiraría esa distinción en el último
      metro: «el certificado no sirve» no le dice a nadie si vuelve a escribir
      el PIN o va a buscar otro archivo. La quinta es la red para un motivo que
      este POS todavía no conozca — el precedente es el `switch` sobre `state`
      de `company_blocked`.

      **`limit` viene en bytes y la frase dice KB.** Nadie piensa en 262 144
      mirando un archivo.

      **Verificación:** `npm test` en verde —613 pruebas, cobertura 100 %— y
      `npm run check` en 0/0. La paridad de `catalogs.test.ts` pasa con los tres
      idiomas.

      **Y otros cinco el mismo día**, con el backend de T-611 y T-612:
      `atv_not_configured`, `atv_invalid_credentials`, `atv_unreachable`,
      `atv_password_unreadable` y `confirmation_required`. La frase de
      `atv_unreachable` va **sin el ambiente y sin culpar a las credenciales**
      (RF-31): quien lea «no sirven» va a rotar su contraseña en ATV, y eso no
      es un clic. Entraron además `api_environment_sandbox` y
      `api_environment_production`, que vuelven palabra el código del ambiente;
      viven en `errors.json` hasta que T-610 tenga pantalla de dónde
      compartirlos.

- [x] **T-615** El simulado responde los seis endpoints de FE con contrato
      idéntico, incluida **la negativa** a devolver el archivo, el PIN y la
      contraseña.

      Sin esto la fase no tiene ninguna prueba de flujo: la suite de punta a
      punta corre con `POS_MOCK=1`. Es el agujero que en F5 hizo que el simulado
      reembolsara cero durante dos días.

      **Hecha el 2026-09-19**, con `SEED_VERSION` en 11 y `fe_credentials` como
      tabla por compañía que **nace vacía**: un negocio recién dado de alta no
      tiene certificado, y eso es lo que la pantalla tiene que saber pintar.

      **Le faltaba una pieza al camino y no era del simulado**: `api()` no sabía
      mandar `multipart`, así que la subida del `.p12` no tenía por dónde pasar.
      Se le agregó `upload`, con el `Content-Type` **sin escribir a mano** —lo
      pone `fetch` con su `boundary`, y ponerlo uno deja al servidor sin
      encontrar ninguna parte—.

      **Los tres desenlaces de RF-31 se piden por la contraseña.** Una que
      empieza por `mal-` la rechazan y una que empieza por `caido-` no contesta;
      la convención vive en `veredictoDe` y en ningún otro sitio. Hacía falta
      porque «Hacienda caída» no se puede provocar contra nada de verdad, y sin
      poder pedirlo, el desenlace que RF-31 separa a propósito no tendría
      ninguna prueba que lo recorra. El veredicto se deduce al llegar y **la
      contraseña se descarta**, igual que el de verdad la cifra.

      Dos choques de nombre al escribirlo, los dos del mismo tipo: ya había
      `DIAS_DE_AVISO` (7, de la suscripción) y `diasHasta` (días de calendario).
      Los nuevos son `DIAS_DE_AVISO_DEL_CERTIFICADO` y
      `diasHastaElVencimiento`, y la distinción no es cosmética: el `notAfter`
      de un certificado tiene hora, y redondearlo a medianoche diría que sirve
      durante catorce horas en que no sirve.

- [x] **T-617** `clients.identification_type` con la lista de Hacienda
      (01/02/03/04). Hoy `clients` tiene `identification` y `email` pero **no el
      tipo**, y el XML lo exige para el receptor. Está en spec §5.4 desde el
      principio y nunca tuvo tarea.

      Barato ahora; en F7 obliga a migrar una tabla con los clientes de todos.
      **Verificación:** un cliente nuevo no se guarda sin tipo, y los existentes
      quedan en el que diga su cédula por longitud.

      **La columna y el relleno, hechos el 2026-09-13** en la migración 011
      (`identification_type_for`, por longitud de la cédula). **La otra mitad,
      hecha el 2026-09-26** con T-731, que la necesitaba para imprimir «Cédula
      física» en el receptor: la ficha del cliente tiene el desplegable, el API
      lo recibe y lo devuelve, y `client_identification_type` guarda el elegido
      o, si viene en blanco, el que deja ver la cédula. Si tampoco así se sabe
      no se guarda: `identification_type_required`. Probado sin base
      (`test_hacienda.py`) y contra MySQL (`test_documento_impreso.py`).

      **En blanco no es «sin tipo», es «según la cédula»**, y el desplegable lo
      dice con el tipo que deduce mientras se escribe. Así `seed.py` y una
      importación sin el campo siguen funcionando, y el NITE —diez dígitos como
      una jurídica— es el único que hay que elegir a mano.

- [x] **T-618** `FE_CRYPTO_KEY` en el compose, en `.env.example` y en el README
      de despliegue. RNF-5.

      **Verificación:** el arranque **falla** si no está o no mide 32 bytes
      —enterarse al firmar es tarde—, y una prueba comprueba que la llave no
      aparece en ningún volcado de `company_dump`.

      **Hecho el 2026-09-13**, y el arranque que se cae está comprobado **dentro
      del contenedor**, no con un `import` desde la máquina.

- [ ] **T-620** Unidad de medida en la ficha del producto, del catálogo de
      Hacienda. La columna existe desde T-507 y **no hay campo que la llene**:
      el grep solo la encuentra en los tipos y en el simulado.

      **Verificación:** un producto guardado con «kg» lo devuelve el API y lo
      conserva al reeditar sin tocar ese campo.

- [ ] **T-619** *(cierre de la fase)* Punta a punta, con el navegador y no con
      `curl`: subir el `.p12` de pruebas con su PIN, guardar las credenciales de
      ATV, ver el estado de los dos ambientes, probar la conexión, pasar a
      producción con confirmación, y comprobar las dos entradas de bitácora.

      F3 tuvo T-310, F4 T-409 y F5 T-511 — y de T-511 salió el hallazgo mayor de
      la fase. Una fase sin tarea de aceptación se cierra creyendo.


---

## F7 · Emisión — ✅ cerrada 2026-10-03, con tareas abiertas a propósito (ver «Lo que quedó abierto» al final de la sección)

**Ruta directa, decidida el 2026-10-03** (T-701): VentaSys firma y transmite.
Lo que queda detrás de los puertos —`DocumentSigner`, `HaciendaIdp`,
`HaciendaReception`— es lo que cambiaría con un proveedor autorizado.

En `docs/hacienda/costa-rica/` están los esquemas XSD 4.4, comprobantes reales
de ejemplo y la normativa de PIN y llaves. La ruta directa deja de depender de
deducir el formato.

- [x] **T-701** Decidir la ruta. **Directa, el 2026-10-03.** El usuario ya
      había cargado el certificado y las credenciales de ATV, F6 dejó la llave
      en Vault y el IdP probado, y los comprobantes aceptados de
      `docs/hacienda/costa-rica/XML-Ejemplos/` dan la forma exacta de la firma.
      Un proveedor autorizado sigue siendo posible: cambia el adaptador de
      `HaciendaReception` y el de la firma, y el recorrido no se entera.
- [x] **T-702** Leer los XSD 4.4 y los comprobantes de ejemplo, y contrastar el
      modelo de datos de F5/F6 contra los campos obligatorios reales. Es lo que
      dice si falta algo antes de escribir código. **Incluye comprobar RN-34**:
      que el contador de cinco dimensiones cubre lo que el XSD exige.

      **Hecha el 2026-09-19** en
      [`docs/hacienda/costa-rica/casos-de-emision.md`](../docs/hacienda/costa-rica/casos-de-emision.md):
      los 23 ejemplos —no 9; aparecieron los de `normativa/protocolos/`—, las
      notas del anexo con sus catálogos completos, y los 25 protocolos de
      comprador de SWS con sus códigos exactos.

      **Lo que falta salió de ahí y son RF-65 a RF-71**: el código de tarifa por
      línea, los medios de pago múltiples, la exoneración por cliente, el IVA
      devuelto, la unidad de medida, los datos de protocolo y los tres tipos de
      comprobante que no existen (FEE, FEC, REP). Cada uno tiene su tarea abajo.

      **Tres hallazgos que cambian decisiones ya tomadas:**

      1. **`OtroContenido` es `simpleContent`**: no admite elementos hijos. Los
         protocolos de Gessa y PriceSmart, que meten un `retail:Complemento`
         adentro, **no son válidos en 4.4** —probado contra el sandbox: rechazo
         `cvc-complex-type.2.2`—. Esos complementos tienen que salir por fuera
         del XML fiscal.
      2. **El «009» del BCCR no es un código del XML**: es el número de
         protocolo interno de SWS. Lo que va en el XML son `BCCR_CUENTA_CLIENTE`,
         `BCCR_ORDEN_PEDIDO` y `BCCR_CODIGO_FACTURA`.
      3. **El documento de protocolos es de 4.3**: los cuatro que usan
         referencia escriben `TipoDoc` y `FechaEmision`, y 4.4 pide `TipoDocIR` y
         `FechaEmisionIR`. Copiarlo tal cual produce un XML que no valida.

- [x] **T-703** Definir la interfaz `EmisorFE` y dejar la implementación detrás.
      **Hecha el 2026-10-03.** No es una interfaz sino cuatro puertos, por cuatro
      razones de cambio: `DocumentSigner` (la llave, en Vault),
      `HaciendaReception` (`submit` y `status`, en
      `application/ports/transmission.py`), `CertificateParser` (lo público del
      certificado) y `TransmissionRepository` (`fe_documents` como recorrido,
      en `application/ports/fe_documents.py`). El recorrido son los casos de uso
      de `use_cases/fe_transmission.py`: `SignDocument`, `SubmitDocument`,
      `PollVerdict`, `ProcessDue`, `RetryDocument`, `QueueSummary`,
      `ProductionGate`.

### El contenido del comprobante

Antes de transmitir nada hay que poder **armarlo**. Estas siete son lo que el
modelo de F5/F6 no tiene, y ninguna depende de la ruta de T-701.

- [x] **T-714** El **armador del XML** como dominio: de una venta a un
      comprobante 4.4, sin base ni red. RF-65 a RF-68.

      **Verificación:** valida contra el XSD oficial de `docs/…/esquemas/` y la
      comparación elemento por elemento contra un ejemplo real no deja ninguna
      diferencia sin explicar. **Hecho el 2026-09-20**: los siete tipos validan
      contra su propio esquema, y las únicas diferencias contra los ejemplos
      reales son los nodos de la firma y lo que cada caso trae de más.

      Es dominio y no un adaptador porque no depende de nada: entra una
      estructura y sale texto. Si para probarlo hiciera falta levantar la base,
      estaría en la capa equivocada.

      `domain/fe_xml.py`, 118 pruebas y cobertura 100 %. Once de esas pruebas
      **validan contra el XSD oficial** con una firma de mentira, porque firmar
      es del adaptador de Vault.

      **Las diferencias entre los siete tipos son datos, no ramas**: viven en
      `PERFILES`, sacadas de los siete XSD uno por uno, y el armador las
      consulta con `Perfil.tiene`. Con un `if tipo == "10"` repartido por el
      archivo, agregar un tipo sería releerlo entero.

      **El validador y los ejemplos encontraron ocho cosas que no se habrían
      deducido leyendo**, y cada una es una prueba:

      1. `ProveedorSistemas` es obligatorio.
      2. La `Ubicacion` del emisor también, y del receptor no.
      3. En esa ubicación **`OtrasSenas` es lo obligatorio y `Barrio` lo
         opcional**, al revés de lo que parecía. Motiva T-722.
      4. El **correo del emisor** es obligatorio.
      5. **Los baldes del resumen van antes del descuento** (RN-84).
      6. **Una exoneración parcial reparte la línea** entre gravado y exonerado
         en proporción a lo perdonado, no la muda entera (RN-78).
      7. **`TotalComprobante` resta el IVA devuelto** (RN-79).
      8. Con **dos o más medios de pago**, la suma tiene que dar el total o
         Hacienda rechaza (RN-77).

      Y una que salió del propio módulo: `Decimal("10.00").normalize()` vale
      `1E+1`, así que diez puntos exonerados salían escritos «1E+1».

- [x] **T-715** **Código de tarifa por línea** (`CodigoTarifaIVA`). RF-65, RN-76.
      El producto guarda `tax_rate` desde T-506 y eso no alcanza: hay once
      códigos para nueve porcentajes y dos de ellos —`01` y `11`, los dos 0 %—
      dan derechos opuestos.

      **Verificación:** un producto al 0 % con derecho a crédito y otro al 0 %
      sin derecho salen con códigos distintos. **Hecho el 2026-09-20.**

      `domain/fe_tax_codes.py` con la nota 8.1 entera, `products.tax_code` y
      `sale_details.tax_code` (migración 012), el desplegable en la ficha del
      producto y el código congelado al cobrar.

      **El código manda sobre la tarifa**, y esa es la decisión: guardar los dos
      y dejar que cada uno venga por su lado es cómo se desincronizan. De un
      código sale siempre un porcentaje; del porcentaje **no siempre** sale un
      código, y en el 0 % no sale ninguno —hay tres y la diferencia es el
      derecho a crédito de quien compra—. Por eso la asignación en lote de CABYS
      propone el código cuando la tarifa deja uno solo y lo deja sin clasificar
      cuando no.

      Los transitorios `05`, `06` y `07` no se le ofrecen a un producto: existen
      para corregir con una nota una factura de cuando esas tarifas regían.

- [~] **T-716** **Medios de pago múltiples**, hasta cuatro con su monto. RF-66,
      RN-77. Y el mapeo desde `payment_method`, que hoy guarda nombres propios
      (`Efectivo`, `Tarjeta de crédito`, `Transferencia bancaria`, `Pago móvil`).

      **Verificación:** con condición de venta 02, 08 o 10 **no se emite ningún
      `MedioPago`**; la suma de los montos es el total del comprobante.

      **Hecho el 2026-09-20 — la mitad del armador**: las dos reglas están en
      `domain/fe_xml.py` y probadas (nada de medio de pago en las tres
      condiciones de crédito; con dos o más, la suma tiene que dar el total o
      Hacienda rechaza), y el mapeo vive en `domain/fe_payment_methods.py` con
      una prueba que **obliga a que esté completo**: agregar una forma de cobrar
      al POS sin decidir su código de la nota 6 rompe la construcción.

      **Falta la mitad cara**, y no es cara por el XML: hoy una venta guarda
      **un** medio de pago, y partirla en varios toca el arqueo —`expected_amount`
      cuenta como efectivo el total de las ventas cuyo método es «Efectivo», y
      con un pago mixto contaría de más— y el reporte por método de pago. Hace
      falta una tabla hija `sale_payments`, y el arqueo y el libro tienen que
      leer de ahí **antes** de que exista el primer cobro partido.

- [x] **T-717** **Exoneración por cliente**: tipo de documento, número,
      institución, artículo, inciso, fecha y **puntos exonerados**. RF-67, RN-78.

      **Verificación:** 13 % con 9 puntos exonerados deja `ImpuestoNeto` en el
      4 % de la base, y la línea va al balde exonerado del resumen, no al
      gravado. **Hecho el 2026-09-20**, con una corrección: el balde no se lleva
      la línea entera sino su parte —69 230.76923 de 100 000— (RN-78, RN-84).

      `domain/fe_exemptions.py` con las notas 10.1 y 23, ocho columnas en
      `clients` (migración 013) y el bloque en la ficha del cliente, que solo
      pide el artículo cuando el tipo lo exige y avisa cuando Hacienda va a
      cruzar el documento contra su registro.

      **Se guarda entera o no se guarda**: los ocho campos van juntos y los ocho
      vacíos es cómo se le quita. Guardar la mitad dejaría un cliente con número
      de documento y sin institución, y eso no se descubre hasta el rechazo.

      `Articulo` es obligatorio con los tipos 02, 03, 06, 07 y 08, e `Inciso` en
      cuanto el artículo remita a uno. Con los tipos 04 y 11 Hacienda comprueba
      que el número exista, esté vigente y que la tarifa exonerada no exceda la
      autorizada: conviene comprobarlo antes de transmitir, porque el rechazo
      llega minutos después y con el cliente ya ido.

- [~] **T-718** **IVA devuelto** en servicios de salud pagados con tarjeta.
      RF-68, RN-79.

      **Verificación:** una venta de servicios médicos cobrada con tarjeta
      declara `TotalIVADevuelto`; la misma cobrada en efectivo, no. **Probado el
      2026-09-20** dentro del dominio, hasta el XML.

      Las dos cosas que faltaban están en `domain/fe_vat_refund.py`:

      * **qué CABYS es servicio médico.** Hacienda no publica esa lista como
        archivo; publica el CABYS, donde el grupo **931** son los servicios de
        salud humana —el ejemplo real factura un `9310100000100`—. Se usa `931`
        y no la división 93 entera porque `932` es atención residencial y `933`
        asistencia social, que no son el servicio del que habla la ley. Está en
        una constante: el día que Hacienda publique su lista, cambia esa línea.
      * **el prorrateo.** El campo es el impuesto pagado *en tarjeta*: con la
        mitad en efectivo se devuelve la mitad, y declararlo entero es un
        rechazo. Con un solo medio de pago la proporción es 1 o 0 y no se nota;
        existe para cuando no lo es.

      Y una tercera que no estaba anotada: **`TotalComprobante` lo resta**
      (anexo p. 55). Sin eso, la factura de salud con tarjeta totaliza de más.

      **Falta** conectarlo: quien arme el comprobante desde una venta tiene que
      llamar a `vat_refund`, y ese armador todavía no existe.

      **Conectado el 2026-10-03, sin cerrar:** `SqlAlchemyComprobanteSource._cierre`
      llama a `vat_refund` en la venta, la devolución y la nota. Lo que falta es
      su verificación fuera del dominio: una venta con un CABYS de salud pagada
      con tarjeta, contra MySQL, que llegue con `TotalIVADevuelto` y el medio de
      pago rebajado. Sin eso la tarea sigue a medias, y está en «Lo que quedó
      abierto».

- [~] **T-719** **Protocolo de comprador por cliente**: qué datos exige y dónde
      van, en `Otros` o en `InformacionReferencia`. RF-70, RN-80.

      **Verificación:** los 25 de `SWS-Procolols_XML.docx` se pueden expresar sin
      tocar código, salvo los tres que ya no son válidos (Gessa y PriceSmart).

      **Hecho el 2026-09-20 — el armador**: `domain/fe_protocols.py`. Un
      protocolo es una lista de **entradas**, y cada entrada dice dónde va
      —`OtroTexto`, `OtroContenido` o `InformacionReferencia`—, con qué código, y
      una plantilla con marcadores (`BCCR_ORDEN_PEDIDO={orden_compra}`). Las
      tres formas que existen están probadas con los protocolos reales: Walmart
      en `OtroTexto` con sus tres códigos, el ICE en `InformacionReferencia` con
      su prefijo `MM-`, el BCCR en `OtroContenido` con pares nombre=valor. No
      hay una cuarta: el complemento anidado de Gessa y PriceSmart **no es
      válido** —`OtroContenido` es `simpleContent`— y se probó contra el sandbox.

      **RN-80 por los dos lados**: una entrada a la que le falta un dato **no se
      emite** —un `WMNumeroOrden` vacío es un dato falso— y el marcador que
      faltó **se reporta**, porque callarlo sería emitir una factura que el
      comprador va a rechazar semanas después. Un marcador mal escrito revienta
      al guardar el protocolo, no al emitir.

      **Falta capturar los datos**: código de proveedor y GLN por cliente, orden
      de compra con su fecha y número de recepción por documento, y la pantalla
      donde se arma el protocolo de cada cliente.

- [x] **T-721** **La pantalla de facturas enseña el expediente completo** de
      cada comprobante: el XML que se envió, la respuesta de Hacienda, por dónde
      va el proceso con la hora de cada paso, y un botón que **genera la
      representación impresa al vuelo**. RF-72, RN-82.

      **Hecha el 2026-10-03.** `FeExpediente.svelte` en la factura, la
      devolución y la nota: el estado, el motivo si se detuvo, lo que dijo
      Hacienda, el próximo intento, cada paso con su hora
      (`fe_document_events`) y el botón de reintentar para el administrador.
      Los dos XML se bajan desde la cabecera de la factura —primero, donde
      estaba «Devolver», que sigue después— por `/facturas/{id}/xml` y
      `/facturas/{id}/respuesta`, que pasan los bytes del almacén sin tocarlos.
      La impresión al vuelo ya era así desde T-724.

      **Verificación:** el XML que se muestra es **byte por byte** el que se
      firmó —no uno regenerado— y la firma verifica sobre esos bytes. El PDF se
      arma en la petición y no se guarda en ninguna parte.

      Los dos XML son el documento fiscal y hay que poder verlos, no solo
      descargarlos: cuando Hacienda rechaza, lo primero que alguien quiere leer
      es qué mandó y qué le contestaron, uno al lado del otro.

      **El PDF al vuelo y no guardado**, porque un PDF archivado puede
      contradecir al XML sin que nadie se entere, y el que manda es el XML.
      Regenerarlo garantiza que lo que se imprime es lo que se emitió. El molde
      ya existe: las tres plantillas de documento de F4.

- [x] **T-722** **La ubicación del emisor con los códigos de Hacienda** en
      Configuración y en el alta de compañía, y el **correo obligatorio**.
      RF-73, RN-83.

      **Verificación:** una compañía dada de alta hoy produce un `Emisor` que
      valida contra el XSD. Hoy **no**: falta la ubicación codificada y el correo
      puede quedar vacío.

      Son cuatro campos nuevos —provincia, cantón, distrito y barrio— con los
      códigos de la nota 14 del anexo (`Codificacionubicacion_V4.4`), y **no
      reemplazan a la dirección de texto libre**: esa se sigue imprimiendo en el
      tiquete. Son dos datos distintos para dos lectores distintos.

      **Hecha el 2026-09-27.** Son cinco campos y no cuatro: en la 4.4 el
      **barrio dejó de ser código** —es texto de 5 a 50— y las **otras señas**,
      obligatorias, faltaban en la lista.

      * **El catálogo es el oficial**: `Codificacionubicacion_V4.4.xlsx`, que el
        anexo nombra y no trae adentro; Hacienda lo publica aparte en la página
        de anexos de ATV (`…/v4.4/Codificacionubicacion_V4.4.rar`, del
        2024-11-20). Quedó en `docs/hacienda/costa-rica/normativa/`, y
        `docs/hacienda/costa-rica/generar_ubicaciones.py` genera de él
        `app/domain/locations_data.py` y `$lib/domain/locationsData.ts`: 7
        provincias, 84 cantones, 492 distritos, con Río Cuarto, Monteverde y
        Puerto Jiménez.
      * **La regla**, en `domain/locations.py` y `$lib/domain/location.ts`: un
        código solo vale dentro de su padre —el cantón «02» existe en las siete
        provincias—, otras señas de 5 a 250, barrio opcional. Vacía se guarda;
        a medias no (`invalid_location`, con `field` y `reason`).
      * **La factura electrónica no se enciende sin emisor**: cédula de
        `companies`, correo y ubicación (`domain/fe_issuer.py`,
        `einvoicing_needs_issuer` con la lista entera de lo que falta). Se
        revisa al guardar Configuración y **no al vender**: rechazar la venta le
        cobra el problema al cliente del mostrador.
      * **La pantalla**: `IssuerLocationFields.svelte`, tres desplegables
        encadenados —elegir un padre vacía a los hijos— y dos textos, en la
        pestaña Negocio y en el alta del panel (opcional ahí).
      * **Lo que se imprime**: en un comprobante, «Provincia: San José / Cantón:
        San José / Distrito: Zapote» y debajo el barrio y las otras señas, como
        la factura de referencia. Sin ubicación completa, la dirección de texto
        libre, que es la del tiquete de siempre.

      **Lo que la verificación todavía no puede decir**: que el `Emisor` valide
      contra el XSD con los datos de una compañía real. El armador (`fe_xml.py`)
      ya valida con una `Ubicacion` construida a mano; lo que falta es el
      adaptador que la arma desde la configuración, y ese llega con la emisión
      (T-712 en adelante).

- [~] **T-720** **FEE, FEC y REP.** RF-71, RN-81. Cada uno con su tipo en el
      consecutivo —09, 08 y 10—, su esquema y sus diferencias: la FEE lleva
      partida arancelaria y dirección extranjera y no admite tarifa 01; el REP
      no admite `Otros` y solo va con condición 09 u 11.

      **El armado está hecho** (2026-09-20): los siete tipos salen de
      `domain/fe_xml.py` y los siete validan contra su XSD. El recibo de pago es
      el que más se aparta —su línea son siete campos, su resumen no lleva
      baldes y su emisor no lleva ni ubicación ni teléfono— y sale idéntico,
      elemento por elemento, al ejemplo real de `docs/`.

      **Falta la otra mitad**: el consecutivo y la clave de cada tipo (T-704 y
      T-705), y desde dónde se emiten. Una FEC nace de una compra a un no
      contribuyente y un REP de cobrar una factura a crédito: son flujos, no
      botones. **Desde el 2026-09-26 cada flujo tiene su tarea: T-725 a T-729.**

      **Al cerrar F7 solo falta el REP**, que es T-729: la FEE y la FEC se
      emiten desde el 2026-10-03.

- [x] **T-723** **El tipo de comprobante se elige al cobrar y queda en la
      venta.** RF-74, RN-85. `sales.document_type` (migración 014), la regla en
      `domain/fe_document_type.py` y en `$lib/domain/documentType.ts`, el
      selector en el cobro, el tipo en el historial, y dos códigos nuevos:
      `invalid_sale_document_type` e `invoice_needs_receiver`.

      **Verificación:** sin cliente sale tiquete y la factura no se puede elegir;
      con cliente sale factura y se puede bajar a tiquete; una factura sin cliente
      mandada a mano la rechaza el servidor; con la facturación apagada la venta
      no lleva tipo aunque se lo pidan. Y una venta con el cliente **de otra
      compañía** responde `client_not_found` —hoy pasa—.

      Salió de mirar la pantalla: con la facturación activa, **toda** venta se
      imprimía «Factura electrónica», incluida la del cliente de contado del
      supermercado, que por definición no puede ser una factura.

      **Hecha el 2026-09-26.** Las cinco condiciones de la verificación están
      probadas contra MySQL en `tests/test_tipo_de_comprobante.py` y en el
      navegador en `tipo-de-comprobante.spec.ts`. El tipo se ve junto al botón de
      cobrar —antes de abrir nada— y en el cobro, y la factura sin cliente se ve
      apagada, no escondida.

      **Destapó un defecto que no estaba anotado: el cliente elegido al cobrar
      nunca llegaba a la venta.** Las opciones del `select` llevaban el id como
      número y el carrito lo guarda como texto; Svelte 5 elige la opción con
      `===`, no encontraba ninguna y dejaba el `select` vacío, así que el
      formulario no mandaba `client_id`. La pestaña decía «Ana» —ahí se compara
      con `String(…)`— y la venta se guardaba de contado. Con el tiquete no se
      notaba nunca; con la factura, que exige cliente, fue lo primero que falló.

      **«Hay receptor» es «hay un cliente de esta compañía»**, con un puerto
      nuevo, `ClientRepository.exists`. El **tipo** de identificación no se
      exige al vender: es la mitad pendiente de T-617, y rechazar la venta por un
      dato que la ficha todavía no pide sería cobrarle a la caja lo que falta en
      clientes.

- [x] **T-724** **Las tres plantillas imprimen el bloque fiscal**, desde un solo
      componente. RF-75, RN-86, RN-17. Y el PDF del backend se quita (T-922).

      **Verificación:** una prueba lee las tres plantillas y falla si alguna no
      incluye `FiscalBlock`; una venta con tipo y sin clave dice «pendiente de
      emisión» en las tres; el título sigue a la venta y no a la configuración de
      hoy. El estado con clave —tipo, consecutivo y clave juntos, más la leyenda
      de pruebas o de la resolución— se prueba en `fiscalBlock` y se verá de
      verdad cuando T-705 mande `einvoice`.

      **Queda por confirmar** el texto exacto de la leyenda de la resolución. El
      README §10 la cita como «Autorizada mediante resolución MH-DGT-RES-0027-2024
      del [fecha]» sin la fecha; se imprime sin ella y hay que cotejarla con la
      resolución antes de T-713.

      **Hecha el 2026-09-26**, con lo que se puede ver hoy: el estado pendiente,
      en el navegador y en las tres plantillas una tras otra
      (`tipo-de-comprobante.spec.ts`). La prueba que lee las plantillas **no
      tiene la lista escrita**: la saca de los `import` de `DocumentSheet.svelte`,
      así que una cuarta plantilla entra sola y falla si no trae el bloque.

      **Lo que queda para T-705**: mandar `einvoice` en el detalle de la venta
      —`clave`, `consecutive`, `environment`, `economic_activity`, con esa forma,
      que es la que ya leen las plantillas— y agregarle la **condición de venta**,
      que el README §10 pide impresa y que hoy es siempre «contado» por
      construcción, porque el POS no vende a crédito. Ninguna de las dos tiene
      sentido antes de que exista el comprobante.

      De paso: la factura moderna imprimía el medio de pago **sin traducir**
      —`sale.payment_method` a secas—, mientras las otras dos usaban
      `paymentName`. Una factura en inglés decía «Efectivo».

      **La leyenda, cotejada contra un comprobante real** (2026-09-26): la
      factura de referencia de `docs/invoice/` imprime «Autorizada mediante
      resolución MH-DGT-RES-0027-2024», sin fecha, que es lo que ya se imprime.
      Sigue valiendo cotejarla con la resolución antes de T-713, pero ya no es
      una suposición.

- [x] **T-731** **Las tres plantillas llevan lo que lleva un comprobante
      real.** RF-75, RN-86. Planteado por el usuario el 2026-09-26 con una
      factura de referencia (`docs/invoice/50624…346.pdf`): a las plantillas les
      faltaban la condición de venta, la moneda, el CABYS y la unidad por
      línea, el impuesto y el total de cada línea, la identificación con su
      tipo, el resumen de Hacienda, el monto en letras, la fecha con hora y el
      portal donde se verifica. Migración 016.

      **Verificación:** una factura electrónica con cliente imprime, en las
      tres plantillas, «Contado», «CRC (TC 1.00)», el CABYS de la línea, la
      cédula del receptor con su tipo, el resumen con la venta neta, «Total
      comprobante» y el monto en letras; cambiar el CABYS del producto después
      no cambia la venta; la nota de crédito repite el CABYS de la venta.

      **Hecha el 2026-09-26.** Contra MySQL en `tests/test_documento_impreso.py`
      —incluido el producto reclasificado después de vender—, y en el navegador
      en `tipo-de-comprobante.spec.ts`, plantilla por plantilla. La prueba que
      lee las plantillas exige ahora cada pieza en las tres y el bloque fiscal
      también **al pie**.

      **El tiquete no tiene columnas**: en 58 mm no caben nueve. Cada producto
      va en su renglón con el total, y debajo, en chico, la cantidad con su
      unidad y su precio, el impuesto y el CABYS. Es la misma información.

      **Lo que no se imprime y por qué:**

      * **El código QR.** Codifica la clave, y no hay clave hasta T-705. Queda
        anotado ahí. Generarlo pide una dependencia nueva (un codificador de
        QR) que se consulta antes de agregarla. *Hecho el 2026-09-27 (T-705): la
        clave sola, nivel Q, como el de la factura aceptada.*
      * **La provincia, el cantón y el distrito.** Son los códigos de T-722, que
        la compañía y el cliente todavía no tienen. Se imprime la dirección de
        texto libre. *Los del emisor se imprimen desde el 2026-09-27 (T-722).
        Los del receptor no: su `Ubicacion` es opcional en el XML y la ficha
        del cliente no los pide.*
      * **El tipo de cambio de otra moneda que no sea el colón**: el del BCCR no
        existe en el sistema, e inventarlo sería peor que callarlo.
      * **«Página 1 de 1».** Lo pone el navegador al imprimir, si se le pide.

### Desde dónde se emite cada uno (RN-87)

Son la otra mitad de T-720. El cobro ofrece lo que sale de una venta; los demás
nacen de su propio flujo. Planteado por el usuario el 2026-09-26, al ver que el
cobro ofrecía solo dos de siete: la respuesta fue que cada uno va donde nace, y
no los siete en el desplegable.

**Todos emiten de verdad recién con T-704 y T-705** —el contador por tipo y la
clave—. Lo que cada tarea puede dejar hecho antes es lo que no depende de eso:
capturar los datos que faltan y decidir y guardar el tipo en su flujo, como
T-723 hizo con la venta.

- [x] **T-727** **FEE al cobrar a un cliente del extranjero.** RF-78, RN-87.
      `COUNTER_TYPES` pasa a tres; el cliente con identificación `05`
      —extranjero no domiciliado— sugiere FEE y no admite FE. Hace falta la
      **partida arancelaria** en la ficha del producto, la **dirección
      extranjera** en la del cliente, y ampliar `IDENTIFICATION_TYPES` al `05`.

      **Verificación:** cliente `05` → el cobro sugiere FEE y la FE sale
      apagada; un producto de la venta sin partida arancelaria **no deja
      cobrar la FEE** y dice cuál es; un producto con tarifa `01` tampoco,
      porque la FEE no la admite (T-720); y el tiquete a ese cliente sigue
      pudiéndose.

      **Hecha el 2026-10-03.** La regla en `domain/fe_document_type.py`
      —`COUNTER_TYPES` son tres y `DOMESTIC_COUNTER_TYPES` los dos con que se
      le vende a la gente del país— y lo que la exportación exige en
      `domain/fe_export.py`: la partida de cada **mercancía**, una tarifa que
      la FEE admita y la dirección del cliente. `IDENTIFICATION_TYPES` son los
      seis de la 4.4 para clientes y proveedores; **el emisor sigue siendo de
      los cuatro primeros** (`fe_issuer`). Migración 021: `products.tariff_heading`
      (doce dígitos, lo que dice el XSD), `clients.foreign_address` (300) y
      `sale_details.tariff_heading`, congelada como el CABYS. La venta lo
      comprueba **antes** de escribir y con el producto en el error; el armador
      pone al receptor `05` tal como se escribió —un pasaporte no son dígitos—,
      sin ubicación y con sus señas, y sin exoneración, que el perfil 09 no
      admite. En el POS: la ficha del producto y la del cliente, el cobro —al
      extranjero no se le ofrece la factura—, las plantillas, el simulado y el
      recorrido de punta a punta hasta «aceptada».

      **Una interpretación que conviene dejar escrita.** RF-78 dice «algún
      producto»; el XSD deja la partida opcional y el anexo la exige en las
      mercancías. Se exige a las mercancías —CABYS 0 a 4, o sin CABYS— y no a
      los servicios, que no la llevan: pedírsela a una asesoría sería inventar
      un dato.

- [x] **T-730** **Los comprobantes que emite cada compañía.** RF-81, RN-88.
      `eInvoicing.documentTypes` con los siete en Configuración, saneado al leer
      en los dos lados, y la regla de la venta con lo encendido. Código nuevo:
      `document_type_not_enabled`.

      **Verificación:** una compañía nueva nace con TE, FE, NC y ND; apagar el TE
      obliga a elegir cliente para cobrar; apagar los dos de venta no se puede
      —la pantalla no lo deja y una fila escrita a mano vuelve a la de fábrica—;
      la NC no se apaga; la FEE, la FEC y el REP se ven con su motivo y no se
      mueven; pedir por el API un tipo apagado responde
      `document_type_not_enabled`.

      **Hecha el 2026-09-26.** Las seis condiciones están probadas: el saneo en
      los dos dominios, la venta con lo encendido contra MySQL
      (`test_tipo_de_comprobante.py`, incluida una fila con solo notas que vuelve
      a la de fábrica), y la pantalla en el navegador —apagar el tiquete, ver que
      la factura queda bloqueada por ser la última de venta, y que guardar **no
      apaga la NC ni la ND**, que estaban bloqueadas—.

      Ese último punto fue el diseño y no un detalle: una casilla deshabilitada
      no se envía con el formulario, así que sin más la primera vez que alguien
      guardara la pantalla se perdían la NC y la ND. Las bloqueadas y encendidas
      viajan además en un campo oculto.

      **Desde el cierre de F7 solo el REP queda bloqueado.** La ND tenía flujo
      desde T-726 y no estaba en `AVAILABLE`, así que su casilla seguía
      bloqueada «sin flujo»: una compañía cuya lista guardada no la traía no
      podía encenderla, y la nota se rechazaba con `document_type_not_enabled`.
      Corregido el 2026-10-03; la FEE y la FEC entraron con T-727 y T-728. La
      prueba de punta a punta comprueba que la ND, la FEE y la FEC se mueven y
      el REP no.

- [x] **T-725** **NC al devolver o anular.** RF-76, RN-87, RN-89. Devolver
      mercadería de una venta con comprobante emite una NC `03` con motivo `06`;
      **anular** desde la factura abierta es una devolución entera con motivo
      `01`, y solo si la venta no tiene devoluciones. La nota se imprime con las
      tres plantillas, con la referencia al original. Migración 015. Códigos
      nuevos: `annul_after_return` y `annul_must_be_full`.

      **Verificación:** devolver parte de una venta con tiquete guarda una NC
      `06` que la referencia; anularla entera, una `01`; anular una venta ya
      devuelta en parte se rechaza; devolver una venta de antes de activar la
      facturación no guarda nota; una venta con comprobante sigue emitiendo NC
      aunque hoy la facturación esté apagada; y la nota impresa dice «Nota de
      crédito electrónica», el original y el motivo, en las tres plantillas.
      La referencia a la **clave** del original se comprueba en T-705.

      **Hecha el 2026-09-26.** Las seis, contra MySQL en
      `tests/test_nota_de_credito.py` y en el navegador en
      `tipo-de-comprobante.spec.ts`. La nota se imprime en `/devoluciones/{id}`
      con `creditNoteDocument`, que convierte la devolución en la forma que ya
      imprimen las plantillas; el bloque fiscal agrega la referencia y las
      plantillas dejan de imprimir el efectivo recibido cuando es cero, que es el
      caso de una nota.

      **El orden de los rechazos importó**: anular una venta a medio devolver
      primero saltaba como «devolución excesiva», que también es cierto pero no
      es el motivo. El chequeo de la anulación va antes que el de cantidades.

      **Hasta T-704 el número de la nota es el de la devolución**, igual que el
      de la venta es su `sale_number`: el consecutivo por tipo lo traerá el
      contador.

- [x] **T-726** **ND y NC por monto desde la factura abierta.** RF-77, RN-87,
      RN-89. Las notas que no mueven mercadería, con el motivo `02` (corrige
      monto). Entidad nueva, `sale_notes` (migración 017). El diseño está en el
      plan, §7.2, «La ND y la NC por monto».

      **La plata, decidida por el usuario el 2026-09-26**: la ND se cobra al
      emitirla con su medio de pago y la NC se reembolsa de la gaveta; las dos
      van al arqueo, a las ventas netas y al asiento.

      **Verificación:** la nota queda con su motivo, su monto y la referencia a
      la venta; sobre una venta sin comprobante el botón no aparece y el
      servidor la rechaza; una NC que pasa de lo que queda de la línea se
      rechaza; la línea con NC ya no se devuelve y la venta con notas no se
      anula; la ND en efectivo sube el esperado del turno y la NC lo baja; las
      ventas netas las cuentan; el asiento dice «Nota» y no lleva costo; y la
      nota impresa dice «Nota de débito electrónica», el original y el motivo.

      **Hecha el 2026-09-26.** Las reglas de plata sin base
      (`test_fe_notes.py`, `test_register_note.py`: el tope de la NC con
      devoluciones, ND y NC anteriores; la devolución y la anulación que se
      niegan; el arqueo con la ND en efectivo, con tarjeta y la NC), contra MySQL
      en `test_notas_por_monto.py` —incluidos el cajero que recibe `admin_only`
      y la otra compañía que no ve la nota ni la emite sobre la venta ajena—, y
      en el navegador en `tipo-de-comprobante.spec.ts`: la ND se emite desde la
      factura, sale impresa con la referencia y aparece en el arqueo; la NC por
      más de lo cobrado dice cuánto queda. Doce códigos nuevos.

      **El monto se escribe con impuesto y la base sale de dividir**, así que el
      total puede quedar un céntimo arriba o abajo de lo escrito (₡100 al 13 %
      da 88,50 + 11,51 = 100,01). Vale el que cuadra con su base y su tarifa,
      que es lo que Hacienda comprueba.

      **Lo que no hace, anotado:** la nota no exige caja abierta, igual que la
      devolución hoy —la plata cae en el turno de quien la emite si lo tiene—;
      y no emite todavía, como todas, hasta T-704 y T-705: su número es su id.

      **Destapó que `test_esquema.py` comparaba solo hasta la migración 011.**
      Las cinco siguientes no se contrastaban contra el modelo; ahora entran las
      seis, y las doce pruebas siguen en verde.

- [ ] **T-732** **NC por exoneración posterior** (motivo `12`). RF-77, RN-78.
      El cliente presenta la exoneración después de comprar y se le devuelve el
      impuesto perdonado. Necesita la exoneración en la línea de la nota —como
      en la factura (T-717)— y que la nota devuelva **solo impuesto**, sin base.
      Salió de acotar T-726: no cabe en «un monto por línea».

      **Verificación:** una venta al 13 % a un cliente que después presenta una
      exoneración de 9 puntos emite una NC `12` por el 9 % de la base, con la
      exoneración en la línea, y la gaveta devuelve eso y nada más.

      **Bloqueada el 2026-10-03, por confirmar.** El anexo 4.4 (p. 72, nota 34)
      solo dice **cuándo** se usa el código 12 —«una exoneración concreta de
      impuestos locales aprobada posterior a la transacción»— y no cómo se
      arman sus líneas, y en `docs/` no hay ninguna NC-12 aceptada. Con la
      exoneración en la línea, la aritmética del anexo da `MontoTotalLinea` =
      base + impuesto neto: eso acredita base y 4 %, no el 9 % que se devuelve.
      Una línea «solo impuesto», exenta, acredita el monto correcto pero lo
      declara como venta y no como impuesto. La tercera salida es anular (NC
      `01`) y refacturar con la exoneración, que usa solo piezas que ya
      existen. Inventar la forma sería lo que RN-80 prohíbe: hay que
      confirmarla con Hacienda o con el contador antes de emitirla, y la
      decisión es del usuario.

- [x] **T-728** **FEC al comprarle a un no contribuyente.** RF-79, RN-87. El
      proveedor gana el tipo `06` —no contribuyente— en `IDENTIFICATION_TYPES`,
      y registrar una compra a uno de ellos le pone tipo `08` a la entrada, con
      el negocio como comprador.

      **Verificación:** una compra a un proveedor `06` guarda la FEC en la serie
      `08`; a un proveedor inscrito, no; y una entrada que no es compra
      (RN-52: sin proveedor) nunca.

      **Hecha el 2026-10-03.** La decisión es `purchase_document_type`
      (`domain/fe_document_type.py`): proveedor `06`, facturación encendida y
      la FEC entre lo que la compañía emite; si no, la compra entra sin
      comprobante, como la venta. `RegisterStockEntry` la numera **en la misma
      transacción** que la mercadería (`SOURCE_PURCHASE`) y
      `stock_entries.document_type` la guarda (021). **El XML es el de la FEC
      aceptada de `docs/`:** el proveedor como emisor, el negocio como receptor
      con su actividad en los dos campos, la condición y el medio de pago de la
      compra, y la referencia tipo 14 —el respaldo del proveedor— con el número
      del documento si lo dio y sin él si no, que es lo normal en quien no
      factura. La pantalla de entradas la enseña con su estado, su expediente,
      sus dos archivos y el reintento, y la lista de detenidos de Facturas
      llega a ella con `?entrada=`. Los proveedores admiten el `05` y el `06`.
      Antes de numerar se exige la cédula del proveedor, que es el emisor del
      XML: sin ella el comprobante nacería para detenerse.
      Probado sin base, contra MySQL y la Hacienda de mentira hasta «aceptada»,
      y en el navegador con el simulado.

      **El impuesto de la FEC es el que se tecleó en la línea de la compra**
      (RN-53), con el código del producto si dice la misma tarifa o el que se
      propone para ella. El recibo de un no contribuyente no trae IVA, y la
      persona lo teclea —como en el recorrido de F10—; si deja el 0 % en un
      producto del 13 %, el comprobante **se detiene** con
      `linea_sin_codigo_de_tarifa`, porque el 0 % tiene tres códigos y
      adivinar uno es lo que RN-80 prohíbe. La salida hoy es anular la compra y
      cargarla con su impuesto; que la entrada pida el código por línea es
      T-735, por decidir.

- [ ] **T-729** **REP al cobrar una venta a crédito.** RF-80, RN-81, RN-87.
      **Bloqueada**: el POS no vende a crédito —`check_payment` exige el total
      en el mostrador— y vender a crédito no está en el spec. Es una fase
      propia: condición de venta, saldo por cliente, abonos, y qué pasa con la
      caja y con el libro. Hay que decidirla antes de empezar esta tarea, no
      adentro.

      **Verificación, cuando se pueda:** cobrar una venta con condición `08` o
      `10` emite un REP en la serie `10` que referencia la factura; una venta de
      contado, nunca.

### El recorrido, que no depende de la ruta

- [x] **T-704** Contador de consecutivo con las **cinco** dimensiones
      `(compañía, sucursal, terminal, tipo, ambiente)` y bloqueo de fila. RN-34.

      Con menos, la serie nace con huecos: un tiquete, una factura y otro
      tiquete dan tiquetes 1, 3, 5 y facturas 2, 4. **Se confirma en la misma
      transacción que el documento** —el `UnitOfWork` que ya existe—, o una venta
      que falla después deja el número consumido. Es el defecto 1 otra vez.

      **Verificación:** una venta que falla por stock no consume número; dos
      cajas de la misma terminal no repiten.

      **Hecha el 2026-09-27**, sobre `fe_sequences`, que la 011 dejó creada con
      las cinco dimensiones y nadie usaba. `last_sequence` crea la fila con
      `INSERT … ON DUPLICATE KEY UPDATE` —no `INSERT IGNORE`, que convierte en
      advertencia también una foránea rota— y la lee con `FOR UPDATE`: la fila
      queda bloqueada hasta el `commit` de la venta. La aritmética es dominio
      (`fe_key.next_sequence`: de uno en uno, y al tope de diez dígitos vuelve a
      1, como permite la nota 3).

      **Las dos verificaciones**: la de stock contra MySQL
      (`test_numeracion.py`) y sin base (`test_number_document.py`, que además
      comprueba que la serie no se bloquea si la venta no llega a numerarse). La
      de dos cajas es el bloqueo de fila; **no hay prueba de concurrencia real**
      —dos peticiones a la vez contra la pila—, y el `UNIQUE (company_id,
      environment, consecutive)` de `fe_documents` es la red si el bloqueo
      fallara.

- [x] **T-705** La clave de 50 dígitos, con la **situación** decidida al vender
      (RN-43). La clave se imprime y se entrega, así que no se puede diferir.

      **Y el QR** que la codifica, en las tres plantillas (T-731): la factura de
      referencia lo lleva al pie. Pide un codificador de QR, que es una
      dependencia nueva y se consulta antes.

      La contingencia es un **modo del negocio**, no una corazonada por venta: se
      entra por el estado de las transmisiones recientes y se sale cuando
      Hacienda responde. Emitir en contingencia con Hacienda arriba es causa de
      rechazo.

      **La clave, hecha el 2026-09-27** (`domain/fe_key.py`,
      `application/use_cases/number_document.py`, migración 018). Reproduce
      dígito por dígito la de la factura de referencia del usuario. La numeran
      los tres flujos que emiten hoy —la venta, la devolución con NC y la nota
      por monto—, en su transacción y con la hora de su documento, y queda en
      `fe_documents` colgando de su origen. El detalle de los tres publica
      `einvoice` (el contrato de T-724) y las notas, `sale_clave`: referencian
      el original **por su clave**. Las plantillas la imprimen en tramos, como
      la factura de referencia.

      * **La cédula es la de `companies`** (RN-45), completada a doce con ceros
        (nota 4.1). Sin ella, `issuer_identification_required` antes de abrir
        la transacción.
      * **El código de seguridad** son ocho dígitos de `secrets`, detrás de un
        puerto para que las pruebas los fijen.
      * **La fecha** es la del sello de la venta, que es hora de Costa Rica
        porque el contenedor corre con `TZ=America/Costa_Rica`: tiene que
        coincidir con la `FechaEmision` del XML.

      **El QR, hecho el 2026-09-27**, con la dependencia aprobada por el usuario
      (`qrcode-generator` 2.0.4, MIT, sin dependencias propias). Lo que codifica
      salió de decodificar el de la factura aceptada: **la clave sola**, los 50
      dígitos, nivel de corrección Q — ni una dirección ni otros datos. Va en modo
      numérico (versión 3, 29 × 29) con cuatro módulos de margen, negro sobre
      blanco, al pie de las tres plantillas en cuanto hay clave: a la derecha en
      la hoja, centrado en el tiquete. `$lib/ui/qr.ts` es el único que importa
      el codificador. Comprobado leyéndolo: las capturas de las tres plantillas
      decodifican con zxing a la clave de su cabecera.

      **Cerrada el 2026-10-03 con T-708 y T-709:** la situación la decide
      `NumberDocument.situation()` por `ContingencyMode`, que
      `ObservedContingency` cumple con lo que la cola observó: 3 si el último
      intento contra Hacienda falló por algo transitorio y desde entonces no
      hubo contacto bueno, dentro de las últimas 24 horas; si no, 1.

      **Corregida el mismo día, al cerrar la fase, dos veces.** Primero el
      dígito: era 2 y es **3**. El anexo 4.4 (nota 3, inciso g, p. 67) dice que
      la 2, «contingencia», es la del comprobante electrónico que **sustituye uno
      físico** hecho a mano durante una caída, y la 3, «sin internet», la del
      que se generó electrónicamente sin poder transmitirlo, que es lo que hace
      VentaSys; y solo admite una fecha de emisión anterior a la validación con
      la 3 (p. 19). El README de `docs/` decía 2 y estaba mal. Después, qué
      cuenta: cualquier `retrying` disparaba la situación, incluido Vault
      sellado o el almacén caído, que son nuestros. Ahora solo cuenta
      `fe_documents.unreachable_at`, que anota el paso cuando no contestó
      Hacienda o su IdP (migración 021).

- [x] **T-706** `sale_number` deja de venir del navegador. Hoy lo fabrica
      `cart.ts` con `yyyyMMddHHmmss` y el **reloj del cliente**: dos cajas
      cobrando en el mismo segundo chocan y una venta se rechaza en la cara del
      cliente. Decidir si pasa a ser el consecutivo o convive con él.

      **Hecha el 2026-10-03: convive.** El consecutivo es el número fiscal y
      `sale_number` el recibo interno, el que se imprime sin comprobante. Lo
      pone `RegisterSale` con el reloj del servidor —`yyyyMMddHHmmss` y un
      sufijo `-2`, `-3`… si ese segundo ya tiene venta— cuando no viene; el POS
      ya no lo manda (`cart.saleNumber` se fue) y un cliente viejo que lo mande
      sigue pudiendo. El simulado hace lo mismo.

- [x] **T-707** Estados del comprobante en la pantalla de facturas: numerado,
      firmado, enviado, aceptado, rechazado, reintentando, detenido. RF-33,
      RN-39.

      **Hecha el 2026-10-03.** Migración 020: el recorrido cuelga de
      `fe_documents` (`status`, intentos, horas de cada paso, motivo, llaves del
      almacén) y la bitácora en `fe_document_events`. El listado de ventas
      publica `einvoice_status` y la columna «Hacienda» lo pinta; el detalle
      publica `einvoice` entero con el recorrido. Las reglas —qué paso sigue,
      cadencias, qué falla detiene— están en `domain/fe_transmission.py`.

- [x] **T-708** Consulta del veredicto con su cadencia propia —10 s → 30 s → 1 →
      2 → 5 min—, distinta de la del reenvío. RN-40.

      **El trabajador corre fuera de una petición**, así que cada documento va
      dentro de un `with compania(cid)`: sin eso la primera lectura lanza
      `SinCompania` y la cola no avanza nunca.

      **Hecha el 2026-10-03.** `PollVerdict` consulta con `poll_delay`: 10 s,
      30 s, 1, 2 y 5 minutos, y de ahí cada 5; a las 72 horas sin veredicto se
      detiene (`no_verdict`). Un 404 en los segundos que siguen al 202 es
      «todavía no» y no una falla. La respuesta firmada se archiva **antes** de
      cerrar el documento (RN-44); si el almacén no responde, se vuelve a
      consultar más tarde. El trabajador es `workers/fe_worker.py`: un hilo del
      proceso de la API que despierta cada `FE_WORKER_INTERVAL_SECONDS` (5),
      recorre las compañías y atiende lo debido; `FE_WORKER=0` lo apaga.

- [x] **T-709** Reenvío con espera creciente —5 → 15 → 30 min → … → 72 h— y
      **solo para fallas transitorias**. RN-41.

      Un rechazo es una respuesta y se detiene. Un certificado vencido o unas
      credenciales rotadas se detienen **en el primer intento**: reintentar tres
      días para llegar a la misma conclusión es demorar el aviso.

      **Hecha el 2026-10-03.** `after_transient_failure`: 5, 15 y 30 minutos,
      1, 2, 4, 8, 16 y 24 horas, hasta 72 desde la primera falla
      (`retries_exhausted`). Transitorio es el IdP o Hacienda que no contestan,
      un 5xx, un 429, Vault sellado y el almacén caído. Detienen en el primer
      intento: sin certificado o vencido, sin credenciales o rechazadas, un
      400 de la recepción (con su `X-Error-Cause`), un 403, y un comprobante
      al que le falta un dato (`document_invalid`, con el código:
      `linea_sin_cabys:1`). Un token vencido entre pedirlo y usarlo se pide
      otra vez, una sola.

- [x] **T-710** Lo **detenido** se ve y se puede reintentar a mano. RF-35, RF-36,
      RN-42. Agotar los reintentos no es rendirse: el plazo de contingencia sigue
      corriendo y el documento sigue siendo transmitible.

      **Hecha el 2026-10-03.** `GET /fe/queue` trae lo detenido con su motivo y
      su fecha; la lista de facturas lo enseña arriba, con enlace a la venta, la
      devolución o la nota de donde nació, y el administrador lo reintenta desde
      ahí o desde el expediente (`POST /fe/documents/{id}/retry`). El reintento
      vuelve el documento al paso en que estaba —firmar, enviar o consultar,
      según sus huellas— y la cola lo toma en el próximo turno; lo que no está
      detenido responde `document_not_stopped`. Queda en bitácora
      (`fe_reintento`).

- [x] **T-711** **Alarma de antigüedad de la cola.** Es lo único que avisa antes
      de que se acabe el plazo de contingencia —unos 8 días hábiles, y Hacienda
      rechaza pasados los 30 días— y lo que hace visible un Vault sellado, un
      disco lleno o un certificado que venció el sábado.

      **Hecha el 2026-10-03.** `queue_alarm`: `warning` con 24 horas de lo
      pendiente más viejo, `danger` con cinco días. Va en el marco de la
      aplicación para el administrador —`(app)/+layout`, como el aviso de la
      suscripción— y en la lista de facturas, con cuántos esperan y desde
      cuándo. La misma cola dice si el negocio está en contingencia.

- [x] **T-712** Archivo: el XML firmado **tal como se envió, byte por byte**, y
      la respuesta de Hacienda. Cinco años, los dos, y descargables. RF-34,
      RN-44.

      **Verificación:** lo descargado es idéntico a lo enviado —no regenerado—;
      la firma cubre esos bytes y regenerarlo da otra firma.

      **Hecha el 2026-10-03.** La firma es `domain/fe_signature.py`: XAdES-EPES
      envuelta, exclusiva, SHA-256 y RSA PKCS#1 v1.5, con la política de la 4.4
      y la forma de los comprobantes aceptados de `docs/…/XML-Ejemplos/`. **No
      firma**: arma los resúmenes y le pide a Vault la firma del `SignedInfo`
      (`DocumentSigner.sign`). La canonicalización es la de la biblioteca
      estándar (C14N 2.0), que sobre estos documentos coincide con la exclusiva
      1.0; `tests/domain/test_fe_signature.py` lo comprueba byte por byte contra
      `lxml`, verifica la firma con el certificado y valida el tiquete firmado
      contra el XSD oficial. El XML se guarda en el almacén **antes** de marcar
      el documento firmado y no se vuelve a firmar nunca; `GET
      /fe/documents/{id}/xml` y `/response` devuelven los bytes del almacén.
      `SqlAlchemyComprobanteSource` arma el `Comprobante` desde la venta, la
      devolución o la nota con el emisor de la configuración y el receptor de la
      ficha; lo que falte detiene con `document_invalid` y el código.

- [x] **T-713** La puerta dura de la certificación: producción **no se habilita**
      sin una factura, un tiquete y una nota de crédito **aceptados** en pruebas.
      RN-46.

      Entra acá y no en F6 porque acá es donde por fin hay documentos que contar.
      En F6 el mismo candado habría nacido cerrado y sin forma de comprobar que
      abre.

      **Verificación:** con dos de los tres aceptados no habilita y **dice cuál
      falta**; «no se puede todavía» sin decir qué falta es lo que convierte una
      regla en un misterio. Se cuentan **aceptados**, no enviados.

      **Hecha el 2026-10-03.** `production_gate` cuenta los `accepted` en
      `sandbox` por tipo; `PUT /fe/active` a producción responde
      `production_gate_locked` con `missing`, `GET /fe` publica
      `production_gate` y la pestaña lo dice con los nombres de los
      comprobantes. Probado contra el stack real en `test_emision.py`.

      **Y partió en dos la prueba de punta a punta de T-611.** Pasar a
      producción ya no se puede sin los tres aceptados, así que
      `factura-electronica.spec.ts` comprueba la puerta cerrada —el diálogo
      avisa, confirmar no alcanza y el aviso dice qué falta— y el paso de
      verdad vive en el recorrido de `tipo-de-comprobante.spec.ts`: tiquete,
      factura y nota de crédito aceptados, la puerta abierta, la confirmación,
      la puerta lateral de guardar la pantalla, la vuelta a pruebas sin
      confirmar y la bitácora con el antes y el después.

- [ ] **T-733** **Entrega al receptor por correo**, con el XML y la
      representación impresa, cuando Hacienda acepta (plan §7.2, «piezas que
      faltan»). Necesita un remitente configurado y decidir si se manda al
      aceptar o a pedido.

      **Verificación:** una factura aceptada a un cliente con correo le llega
      con los dos adjuntos; un tiquete sin receptor no manda nada.

- [ ] **T-734** **`callbackUrl` en el despliegue hospedado** (plan §7.2): el
      puerto admite la consulta y el aviso; el primario sigue siendo la
      consulta porque un POS en la LAN no tiene URL pública.

      **Verificación:** con la URL configurada, el veredicto llega por el
      callback y la consulta no se dispara.

- [ ] **T-735** **La línea de la entrada pide el código de tarifa** cuando la
      tarifa deja más de uno. Salió de T-728: el recibo de un no contribuyente
      no trae IVA, y una compra cargada al 0 % sobre un producto del 13 % emite
      una FEC que se detiene con `linea_sin_codigo_de_tarifa` —el 0 % tiene tres
      códigos y adivinarlo es lo que RN-80 prohíbe—. Hoy la salida es anular y
      volver a cargar. Por decidir con el usuario: que la entrada lo pida, o que
      baste con la tarifa.

      **Verificación:** una compra a un `06` con 0 % en un producto del 13 % y
      sin código se rechaza **antes de guardar**, con su código de error; con
      código, la FEC llega a «aceptada».

- [ ] **T-736** **Reemitir un comprobante rechazado.** Un rechazo es final
      (RN-41) y la clave no se reusa: hay que emitir otro con consecutivo nuevo
      (plan §7.2, «Un rechazo sí deja hueco»). Hoy no hay cómo: `RetryDocument`
      solo toma lo detenido, y corregir el dato que causó el rechazo —la cédula
      del receptor, digamos— no llega al documento, que ya está firmado. Salió
      de la revisión del plan al cerrar F7; **no tiene requisito en el spec**, y
      por eso se consulta antes de construirla. Lo que hay que decidir: quién
      puede reemitir, si el nuevo referencia al rechazado (la nota 10 del anexo
      tiene el tipo `10`, «comprobante rechazado por el Ministerio de
      Hacienda») y qué ve el cliente que ya se llevó el papel.

      **Verificación:** una clave terminada en `99` contra la Hacienda de mentira
      queda rechazada; reemitirla crea un segundo comprobante del mismo origen,
      con consecutivo nuevo, que llega a «aceptado»; el detalle de la venta
      publica el vigente y el rechazado sigue visible en su expediente.

- [ ] **T-737** **Un turno de la cola con presupuesto de tiempo.** El hilo
      atiende las compañías una tras otra, hasta 20 documentos cada una, y cada
      paso puede esperar 15 s al IdP y 30 s a la recepción. Con Hacienda lenta y
      muchas compañías, un turno dura más que la cadencia de 10 s del veredicto
      y la cola entera se atrasa. Salió de la revisión del plan; no estaba en
      ningún documento.

      **Verificación:** con una recepción que tarda el máximo en cada llamada,
      un turno no pasa de su presupuesto y lo que no alcanzó queda para el
      siguiente, empezando por la compañía donde se cortó.

### Lo que quedó abierto al cerrar la fase (2026-10-03)

La ruta directa emite y transmite el tiquete, la factura, la de exportación, la
nota de crédito, la de débito y la factura de compra, con su recorrido, su
archivo y su puerta de producción. Lo que sigue queda abierto a propósito, cada
cosa con su porqué escrito en su entrada:

| Tarea | Por qué no entró | Qué la destraba |
|---|---|---|
| T-729 REP (y lo que queda de T-720) | El POS no vende a crédito; es una fase propia (condición de venta, saldo, abonos, caja, libro). | Decidir esa fase. |
| T-732 NC-12 | El anexo no dice cómo se arman sus líneas y no hay ejemplo aceptado; inventarlo viola RN-80. | Confirmar la forma con Hacienda o el contador. |
| T-733 correo al receptor | Necesita un remitente configurado y decidir si se manda al aceptar o a pedido. | Esa decisión y un servicio de correo. |
| T-734 `callbackUrl` | Un POS en la LAN no tiene URL pública; es del despliegue hospedado. | Que exista ese despliegue. |
| T-735 el código de tarifa por línea en la entrada | Con 0 % en un producto del 13 % la FEC se detiene, y la entrada no deja elegir el código. | Decidir si la entrada lo pide. |
| T-736 reemitir un rechazado | No tiene requisito; un rechazo hoy no tiene salida. **Es la que más conviene antes de producción.** | Decidir quién reemite y si referencia al rechazado. |
| T-737 presupuesto del turno de la cola | Riesgo con muchas compañías y Hacienda lenta. | Construirla; no pide decisión. |
| T-716 varios medios de pago | El XML ya los arma; falta `sale_payments`, y que el arqueo y el libro lean de ahí antes del primer cobro partido. | Diseñarlo en el plan, que hoy no lo tiene. |
| T-718 IVA devuelto de salud | Conectado al armador; falta su prueba contra MySQL con tarjeta y un CABYS de salud. | Escribir esa prueba. |
| T-719 protocolos de comprador | El XML los copia; falta capturarlos por cliente y por documento. | Diseñar la captura. |
| ~~T-616 (F6) arrancar la numeración~~ | **Hecha el 2026-10-03 (QA-07).** | — |
| El sandbox real | **La FE ya pasó (2026-10-03):** consecutivo 0000500210, aceptada en once segundos —firma, política y `ProveedorSistemas` juzgados por Hacienda—. Antes, la cola nunca había llegado: la URL del sandbox era una ruta muerta y el Gateway contestaba 403 (ver `progress.json`). Hacienda dejó dos avisos sin rechazar: la provincia, el cantón y el distrito del emisor no coinciden con su RUT (-37), y la tarifa del 1 % (-300, no aplica a canasta básica). Los dos TE detenidos con `forbidden` se pueden reintentar. | Que el usuario emita un TE y una NC, y corrija la ubicación del emisor en Configuración. |
| `lxml` en `requirements-dev.txt` | Las pruebas contra el XSD se saltan en silencio en una máquina sin él. | Decidir si se agrega; es de desarrollo, no de producción. |

---

## F8 · Multi-idioma — ✅ terminada 2026-08-23

Español, inglés y portugués. El español en **usted**, no en voseo (RN-22).

**El mecanismo tiene que existir antes de F3**, aunque los catálogos de inglés y
portugués se llenen después. F3 agrega el panel de soporte, F4 las categorías,
F5 el buscador de CABYS y F6 la pantalla del certificado: cada pantalla escrita
con la cadena adentro es una pantalla que hay que volver a abrir. Escribirla con
`t('ventas.cobrar')` desde el primer día cuesta lo mismo.

> **El mecanismo ya existe, y F3 puede empezar** (2026-08-22). Están hechas
> T-801 a T-805, T-812, T-815 y T-816: la biblioteca elegida y montada, los
> códigos del backend, las 18 pantallas y las tres plantillas en catálogo, el
> usted, y la prueba que tumba la build si alguien escribe una cadena dentro de
> un componente, dentro de una acción o dentro del dominio.
>
> **F8 está terminada** (2026-08-23). Las 17 tareas, de T-801 a T-817.
>
> El POS habla **español, inglés y portugués**: 915 claves por idioma, con una
> prueba que las compara —claves, parámetros y nada huérfano—, el idioma saliendo
> del token, selector para la persona y para la compañía, fechas por locale, y el
> documento impreso en el idioma de la compañía y no en el de la pantalla
> (RN-29). El flujo completo se prueba en los tres idiomas (T-814).
>
> El orden importó: primero la red (T-813), después los catálogos. Con Paraglide,
> una clave que falta cae al idioma base **en silencio** y un parámetro que falta
> también, así que llenar los catálogos antes de la prueba habría sido llenarlos
> a ciegas.

### La decisión que faltaba — tomada el 2026-08-23

**RN-30 se reescribió.** Decía «el backend no escribe texto para una persona» y
ahora dice **«ninguna capa que no sea la interfaz escribe texto para una
persona»**, que es lo que se venía aplicando: la regla, puesta solo en el borde
HTTP, no cerraba —el dominio del backend mandaba «el monto debe ser mayor que
cero» y el adaptador lo reenviaba; el dominio del POS devolvía frases;
`$lib/server/api.ts` escribía las suyas—. Los cuatro sitios devuelven código y
datos y la frase se arma en un solo lugar por lado: `ui/messages.ts` en el POS y
nada en el backend.

El requisito **también cubre los valores por omisión que acaban impresos**, que
es lo que apareció al escribir el guardián de T-816. Un `spec.md` ampliado sin
que la decisión estuviera tomada habría sido inventarse el alcance; con la
decisión tomada, lo que quedaba sin requisito ya lo tiene.

### El backend deja de escribir texto

- [x] **T-801** Elegir la biblioteca con una prueba real sobre la pantalla de
      ventas, que es la más cargada. Candidatos: Paraglide (Inlang) y
      `typesafe-i18n`. Criterios, en orden: que funcione en el servidor, que una
      clave que falta rompa `npm run check`, y que no pese en el arranque.
      Plan §8.5.
      **Gana Paraglide** (2026-08-22, `@inlang/paraglide-js` 2.24.1). Se probaron
      los dos con los mismos doce mensajes de `/ventas` —texto suelto, atributos,
      parámetros y plural—, no leyendo documentación:

      | Criterio | Paraglide | typesafe-i18n |
      |---|---|---|
      | Sirve en el servidor | sí | sí |
      | Clave o parámetro mal escrito rompe `npm run check` | sí, 3 de 3 | sí |
      | Clave que falta en un catálogo **que no es el base** | **no**, cae al base en silencio | **sí**, error de tipo |
      | Peso con 455 claves usando 3 | **5,55 kB** (2,19 gz) | **87,48 kB** (8,00 gz), y con dos idiomas en vez de tres |

      Pierde en lo único que T-813 ya existía para cubrir, y gana en lo que
      ninguna prueba arregla: el peso —16× en una caja modesta— y el
      mantenimiento (Paraglide publicó el 2026-08-15 y es la integración oficial
      de SvelteKit; `typesafe-i18n` publicó 266 versiones hasta agosto de 2023 y
      una sola después, en febrero de 2026: su autor murió en 2023).
      Queda montado y corriendo: `paraglideVitePlugin` en `vite.config.ts`,
      catálogos en `messages/{es,en,pt}.json`, y `npm run i18n` atado a `prepare`
      y a `check` —`svelte-check` no corre Vite, así que sin eso un clon nuevo
      no compila—.
      **`strategy: ['baseLocale']` a propósito**: la de fábrica incluye
      `globalVariable`, que es una variable de módulo y en el servidor la
      comparten todas las peticiones. Sería el defecto 17 otra vez. El idioma
      entra por `paraglideMiddleware` (AsyncLocalStorage, por petición) en T-809.
- [x] **T-802** Los 68 mensajes del backend pasan a **código y datos**:
      `{"code": "insufficient_stock", "product": "Arroz", "available": 2}`.
      El dominio ya lanza los errores con esos datos —es el pago de F1—, así que
      el cambio vive en los adaptadores `crud_*`, un archivo por flujo. RN-30.

      **Hecho el 2026-08-22.** Fueron **81 `raise`** en 17 archivos, no 68, más
      12 mensajes de éxito y 70 sitios del simulado. Quedan en **64 códigos**:
      el conteo baja porque cuatro pares decían lo mismo con distintas palabras
      («no hay caja abierta» tenía dos frases según dónde se topara uno, y el
      código de barras repetido tenía tres).

      Todos se construyen en `app/utils/api_errors.py` con
      `api_error(status, code, **datos)`. La forma del cuerpo es la que ya usaban
      las invitaciones: `{"detail": {"code": …, …datos}}`.

      Tres cosas que el plan no preveía y sin las cuales la regla no cerraba:

      - **El dominio también escribía español.** `InvalidMovement` llevaba la
        frase («el monto debe ser mayor que cero») y el adaptador la reenviaba
        tal cual cuando no la reconocía; `InvalidBarcode` igual; y
        `TotalsMismatch.campo` decía «impuesto», que iba a la pantalla. Ahora
        llevan código y el nombre del campo del API (`tax`).
      - **Los «sí» también.** `{"message": "Venta registrada exitosamente"}` no
        lo lee nadie —el POS escribe sus propios avisos— pero una respuesta con
        prosa adentro es prosa que alguien acabará mostrando. Son códigos
        (`sale_registered`); el campo se sigue llamando `message` porque es el
        contrato publicado.
      - **El POS también.** `api.ts` escribía «No se pudo conectar con el
        backend en …» dentro de `$lib/server`, que no es la interfaz. `ApiError`
        lleva ahora `code` y `data`; `toMessage()` se llama `toLog()` y es para
        el registro. La frase la arma `apiMessage()` en `$lib/ui/messages.ts`,
        el mismo lugar que ya armaba las del carrito y el validador.

      Lo que **no** se cambió: los mensajes de `Exception` del dominio (salen en
      un traceback, no en una pantalla), los `print` de `bootstrap.py` y
      compañía (son para quien corre el guion en su terminal) y el saludo de
      `GET /` (es el «¿está encendido?» de quien despliega). Ninguno es texto
      para quien usa el POS.
- [x] **T-803** Cada código de error tiene su prueba: «esta situación devuelve
      este código». Sustituye a comparar cadenas, que es lo que hacen hoy las de
      caracterización.

      **Hecho el 2026-08-22**, en `backend/tests/test_error_codes.py`: 67
      pruebas, y las dos de caracterización que comparaban cadenas
      (`"no coincide" in detail`) ahora comparan el código. La suite pasó de 412
      a **479**.

      Y tres guardianes, porque una regla sin red dura hasta el primer apuro:

      1. **`HTTPException` solo se construye en `api_errors.py`.** Se lee el
         árbol de sintaxis de `app/`. Un `detail="…"` escrito con prisa tumba
         `pytest` en vez de llegar a la pantalla de alguien.
      2. **Ningún código inventado y ninguno de adorno.** Las dos direcciones:
         un `raise` con un código que no está en `CODES`, y un código en `CODES`
         que nadie levanta —que casi siempre es un error de dedo en uno de los
         dos lados—.
      3. **El backend y el POS dicen lo mismo.** `messages.test.ts` lee
         `api_errors.py` y compara con `API_CODES`. Comprobado tumbándolo: se
         agregó un código al backend y la prueba lo señaló por nombre.

      Del lado del POS, el `switch` de `apiMessage` es exhaustivo y termina en
      `never`. Se comprobó igual —quitando el caso de `last_admin`— y
      `svelte-check` lo rechazó. El primer intento tenía un `as never` que
      desactivaba la verificación sin que se notara: el `switch` compilaba
      completo o incompleto por igual.

### Los catálogos

- [x] **T-804** Extraer los textos del frontend a catálogos. Plan §8.1.
      **Inventario corregido el 2026-08-22**, midiendo sobre el código de hoy: el
      plan decía 455 en 33 archivos y hay más, pero la diferencia es de reparto y
      no de tamaño. Lo que **no** entra:

      - `lib/server/mock/db.ts` (28) — nombres de productos y clientes de
        mentira. Son datos, no interfaz.
      - `lib/server/mock/handler.ts` (39) — errores del backend simulado. Iban
        con **T-802**, y ahí se resolvieron: `fail()` recibe código y datos, así
        que en el simulado ya no hay texto que extraer.
      - `F1`…`F4` — nombres de tecla.
      - `PAYMENT_METHODS` — se guardan en `sales.payment_method` y se comparan en
        las plantillas y los reportes. **El valor no se traduce nunca**;
        `paymentLabel()` traduce cómo se muestra.

      Los catálogos están partidos por pantalla (`messages/{locale}/*.json`), que
      `pathPattern` admite como array. Son 18: `common`, `errors`, `nav`, `auth`,
      `fields`, `validation`, `cart`, `checkout`, `sales`, `cash`, `returns`,
      `inventory`, `entries`, `people`, `reports`, `invoices`, `settings` y
      `documents`.

      **Hecho** (2026-08-22), en este orden y por una razón:

      1. `/ventas` — la más cargada, la que el plan pedía como referencia. Con su
         acción y su dominio.
      2. **T-815**, el `Validator`. Antes de seguir con pantallas, porque cada
         `+page.server.ts` se abre una sola vez.
      3. **Lo compartido**: el menú (`navigation.ts` + `(app)/+layout.svelte`),
         `Modal`, `Toaster`, `forms.ts`, `+error.svelte` y `hooks.server.ts`. Se
         paga una vez y se cobra en todas las pantallas.
      4. **Las de entrada**: `/login`, `/registro`, `/compania` y sus acciones.

      5. **Las de plata y catálogo**: `/caja`, `/devoluciones`, `/inventario`,
         `/usuarios`, `/clientes` y sus acciones.

      6. **Las que faltaban** (2026-08-22, segunda jornada): `entradas`,
         `entradas/nueva`, `dashboard`, `facturas`, `facturas/[id]`, el puente al
         PDF, los tres gráficos, `configuracion` y las **tres plantillas de
         documento**.

      **Terminada.** 18 catálogos, **893 claves en español**. El de documentos va
      aparte a propósito (`documents.json`): el idioma del documento no es el de
      la pantalla (RN-29), así que T-811 solo tiene que cambiar de dónde sale el
      idioma —no las claves ni quién arma la frase, que ya es
      `$lib/ui/documents.ts`—.

      **Tres cosas aparecieron al hacerlo y no estaban en el inventario:**

      - **Los lectores de archivos escribían las frases.** `import/spreadsheet.ts`
        e `import/hacienda.ts` lanzaban `new Error('No se pudo leer el CSV…')` y
        la pantalla mostraba `error.message` tal cual. Ahora devuelven
        `ImportFailure` e `ImportNote` —código y datos— y la frase la arma
        `importMessage()`. Las cinco pruebas que comparaban cadenas comparan el
        código, igual que se hizo en T-803.
      - **El dominio guardaba rótulos.** `CURRENCIES[].label` («Colón
        costarricense»), `TEMPLATES[].name/description/paper` y, en
        `domain/documents.ts`, `documentTitle()` («Factura electrónica») y las
        líneas del emisor ya compuestas («Cédula 3-101…», «Tel. 2222-3333»).
        Todo eso era texto para una persona en una constante de módulo: el
        defecto 17 esperando. `TEMPLATES` pasó a `TEMPLATE_IDS`,
        `documentTitle()` a `domain/documentKind()` + `ui/documents.ts`, y los
        rótulos al catálogo, resueltos por función.
      - **`ID_TYPES` se queda con su rótulo, y no es una excepción perezosa.**
        «Cédula jurídica» es el nombre legal del documento en Costa Rica: no se
        traduce a portugués, se cambia por la lista de otro país. Lo que hará
        falta el día que VentaSys se venda fuera es una lista por país, no una
        traducción.

      **`navigation.ts` tuvo que pasar de constante a función.** El menú era un
      `const NAV` de módulo: se evaluaría una vez por proceso y todas las
      peticiones verían los rótulos del idioma de la primera. Con las de esta
      jornada —los presets del dashboard, las pestañas de configuración, el
      origen de cada entrada— van **seis** veces que aparece el defecto 17
      disfrazado en esta fase.

      **Un rastreador, no una prueba**: `scratchpad/buscar-texto-suelto.py`
      encuentra rótulos literales (`label="…"`) y texto suelto en el marcado. Con
      él se cazó un «Nuevo cliente» que había quedado en `/clientes`. Es un
      heurístico y da falsos positivos (una línea de comentario, un ternario de
      clases); la red de verdad es **T-812**, que corre como prueba.
- [x] **T-805** Reescribir a **usted** en la misma pasada.

      **Terminada de verdad el 2026-08-22**, al cerrar T-804: el voseo se fue con
      cada pantalla que pasó al catálogo. La búsqueda buena da **cero** en
      `src/`; las tres coincidencias que quedan son la palabra «caché» en
      descripciones de pruebas, que es un sustantivo.

      Lo que sigue vale como advertencia, porque el error de método fue peor que
      el voseo:

      **Se marcó terminada antes, el mismo día, y no lo estaba. La búsqueda con la que
      se verificó estaba invertida.** Era `grep -E` con `\b` alrededor de
      palabras acentuadas, y para grep la «á» no es carácter de palabra: un
      patrón `...á\b` solo casa **cuando después viene una letra**. Así que
      encontraba «dejá» dentro de «dejándolo» —falso positivo— y se perdía
      «Actualizá el FastAPI», que es voseo de verdad. Buscaba justo lo
      contrario.

      De ahí salieron dos conclusiones falsas: que no quedaba voseo, y que el
      plan había contado de más. **El plan tenía razón**: 48 en 19 archivos era
      una estimación buena. Con un patrón Unicode quedan **unos 30 en 12
      archivos**, todos en texto de pantalla.

      Sirve para buscarlo: `scratchpad/buscar-voseo.py`, que además separa lo que
      está en un comentario de lo que ve una persona. Cuidado con dos casos que
      ni ese patrón ve, porque se escriben **sin tilde**: «Guardalo»,
      «limpialos» —imperativo de vos con el pronombre pegado—.

      Lo que **sí** es cierto de lo verificado: las pantallas ya extraídas están
      limpias (ventas, caja, devoluciones, inventario, usuarios, clientes, login,
      registro, compania y el layout), y el simulado también, porque su voseo se
      fue con las frases al pasar a códigos en T-802.

      Lo que quedaba **coincidía casi exactamente con lo que faltaba de T-804**,
      así que no fue una pasada aparte: se resolvió al extraer cada pantalla.
      Estaba en `entradas/nueva` (10), `entradas` (3), su acción (3),
      `import/spreadsheet.ts` (4), las tres plantillas (4), y uno en cada uno de
      `configuracion`, `dashboard`, `charts/SalesTrendChart`, `facturas` y el
      puente al PDF.

      **La lección, que es lo que importa**: una búsqueda que devuelve cero se
      comprueba al revés antes de creerle —buscando algo que uno sabe que está—.
      Un cero es el resultado más fácil de fabricar por accidente, y el que menos
      se cuestiona.
- [x] **T-815** El `Validator` deja de recibir la etiqueta en español.
      Apareció al extraer `/ventas`. Hecho 2026-08-22: **92 sitios en 10
      archivos**, y ninguno quedó sin migrar.
      El validador devuelve regla y datos (`{ code: 'validation_required', label
      }`) y `validationErrors()` los convierte en frases **justo antes del
      `fail()`**. Ese detalle es el que hizo que **los 8 componentes que muestran
      `form.errors` no se tocaran**: el contrato con la pantalla sigue siendo
      `Record<string, string>`. `formError()` tuvo que seguir devolviendo texto
      por lo mismo —al devolver el tipo nuevo, `form.errors` pasaba a ser la
      unión de las dos formas y las ocho pantallas dejaban de compilar—.
      El rótulo llega resuelto del catálogo desde `$lib/ui/fields.ts`, con **54
      campos declarados una sola vez**. Son funciones y no constantes: una
      constante se evaluaría al importar el módulo y congelaría el idioma de la
      primera petición para todas: el defecto 17 otra vez.
      **Defecto 22, encontrado acá:** el rótulo traía el género en el texto pero
      el mensaje decía «es obligatorio» fijo, así que los 20 campos femeninos y
      plurales salían mal —«La cédula es obligatorio», «Los decimales es
      obligatorio»—. Y la prueba de `integer` lo **afirmaba**. Ahora la
      concordancia viaja con el rótulo (`m`/`f`/`mp`/`fp`) y la elige una
      variante de Paraglide. Verificado contra el backend real.
- [x] **T-806** `ui/format.ts` deja de formatear fechas fijo en es-CR: los meses
      y el orden dependen del locale.

      **Hecho el 2026-08-23.** `15/08/2026` en español y portugués, `08/15/2026`
      en inglés, y los meses cortos del eje del gráfico cambian de nombre. La
      etiqueta de Intl lleva región (`es-CR`, `en-US`, `pt-BR`) porque el idioma
      solo no dice el orden: `en` a secas se resuelve distinto según dónde corra,
      y el orden de la fecha es justo lo que cambia entre `en-US` y `en-GB`.

      Cada función acepta un `locale` explícito, y no es adorno: las tres
      plantillas de documento pasan el suyo (T-811). La fecha de prueba es el
      **15** de agosto a propósito: con un día menor que 12, un orden equivocado
      pasa inadvertido.

      **La hora no depende del idioma, a propósito**: 24 h en los tres. Son horas
      de turnos de caja, se leen en columna, y `2:05 PM` junto a `14:05` es una
      columna que no se puede comparar de un vistazo. La tarea pedía «los meses y
      el orden», que es lo que sí cambia. 7 pruebas en `format.test.ts`.
- [x] **T-807** Catálogo de inglés. Medidas el 2026-08-23 son **898 claves en 18
      archivos** (893 al cerrar T-804; las cinco de diferencia son de las dos
      jornadas siguientes).

      **Terminado el 2026-08-23: 898 de 898**, los 18 catálogos. `en` ya no
      aparece en `SIN_TRADUCIR`, así que la prueba de T-813 lo exige completo
      —claves, parámetros y nada huérfano— y no puede volver a quedarse atrás sin
      que la build lo diga.

      **El inglés no tiene género pero sí concordancia de número.** El sitio que
      llama sigue pasando `concord` (T-815), así que la traducción tiene que
      declararlo o el parámetro se pierde; y los cuatro casos del español se
      doblan en dos, no en uno: `mp` y `fp` van a «are required» y el resto a «is
      required». Hoy solo dos campos son plurales (`notes` y `documentNotes`) y
      en inglés también lo son. Comprobado armando las frases: «The notes are
      required.», «The amount is required.»

      **Glosario, para que los 12 que faltan y el portugués no se contradigan:**

      | Español | Inglés | Por qué no la obvia |
      |---|---|---|
      | Caja (la sección) | Cash register | «Cash» se confunde con el método de pago |
      | Caja (la terminal) | Register | En `nav_branch_terminal`, junto a Branch |
      | Clientes | Customers | «Clients» es de despacho de abogados |
      | Cédula | ID number | No es un número de seguro social ni un pasaporte |
      | Razón social | Legal name | |
      | Leyenda | Legal notice | |
      | Tiquete | Receipt | |
      | Anular | Void | «Cancel» ya es el botón de cerrar un diálogo |
      | Entrada de mercadería | Entry | El contexto lo da la pantalla |
      | Sin identificar | (unidentified) | Va donde va un nombre de producto: «the product unidentified» es inglés roto y «the product (unidentified)» se lee como el nombre que falta |

      Lo que **no** se traduce, y ya está decidido: los valores de
      `PAYMENT_METHODS` (son dato de `sales.payment_method`), los rótulos de
      `ID_TYPES` (nombre legal costarricense) y la marca.

      **Todavía no se puede ver en pantalla**: con `strategy: ['baseLocale']`
      todo se sirve en español hasta que T-809 ponga el idioma en el token. Lo
      traducido se comprueba llamando a los mensajes con `{ locale: 'en' }`, que
      es lo que hay hasta entonces. **T-814 —el flujo en tres idiomas— es lo que
      de verdad cierra esta tarea**, y depende de T-809.

      Dos rótulos quedaron con una decisión adentro, no con una traducción
      literal: `invoices_col_tax` dice «IVA» en español y **«Tax» en inglés**,
      porque el nombre del impuesto se configura y el encabezado no puede
      afirmar cuál es; y `entries_source_xml` pasa de «XML Hacienda» a «Tax
      authority XML», por lo mismo que en el resto del catálogo se habla de «the
      tax authority» y no de Hacienda: quien lee la interfaz en inglés puede no
      saber qué es Hacienda.
- [x] **T-808** Catálogo de portugués (Brasil). **Solo la interfaz**: la factura
      electrónica sigue siendo la de Hacienda Costa Rica. Vender en Brasil
      implica NF-e —otro esquema, otra autoridad, otro certificado— y sería una
      fase aparte.

      **Terminado el 2026-08-23: los 18 catálogos, 915 claves.** Los tres idiomas
      tienen ahora las mismas 915, así que `SIN_TRADUCIR` quedó vacía y se borró
      junto con la prueba que la vigilaba: una lista de excepciones vacía es una
      prueba que no puede fallar y aun así tranquiliza.

      **La concordancia de género no se pudo copiar del español, y eso cambió la
      redacción.** La concordancia la declara el campo una sola vez en
      `$lib/ui/fields.ts`, y se escribió desde el español: «la cédula» es
      femenino y «o documento» es masculino, y el mismo campo no puede ser los
      dos. Así que los dos mensajes que concuerdan en género —obligatorio, no
      válido— se redactaron en portugués de una forma que no depende del género:
      «{field}: campo obrigatório». La alternativa era elegir palabras
      portuguesas por el género del español, que es escribir mal para no
      contradecir una constante.

      Glosario propio del portugués, sobre el del inglés: Estoque (no
      «inventário»), Caixa, Fatura, Devoluções, Relatórios, Usuários, Filial,
      Fornecedor, Estornar (no «cancelar», que es el botón de cerrar), Troco,
      Dinheiro, Operador de caixa, «autoridade fiscal» por Hacienda.

### Dónde vive

- [x] **T-809** El `locale` efectivo entra en el JWT junto con la compañía y el
      rol; el `load` del layout lo lee de ahí. Orden: lo de la persona, si no lo
      de la compañía, si no `es`. Plan §8.4.

      **Hecho el 2026-08-23.** La regla vive en `app/domain/locale.py` —pura, con
      11 pruebas— y no en el router: descarta además lo que no se puede usar, así
      que un `fr` guardado a mano no se propaga y un `es-CR` cae a `es`. El token
      lo emite `_token_de_sesion`, que ahora recibe la compañía y no su id.

      **En el POS entra por una estrategia de Paraglide y no por un `load`.** La
      pantalla pide los mensajes *durante* el render, así que el idioma tiene que
      estar puesto antes: `hooks.server.ts` registra `custom-session`, que saca el
      `loc` del token, y `paraglideMiddleware` lo guarda por petición en
      AsyncLocalStorage. `strategy` quedó en
      `['custom-session', 'cookie', 'baseLocale']`, y **la misma lista está en el
      guion `i18n`**: `svelte-check` no pasa por Vite, y cuando divergían la
      comprobación de tipos miraba un runtime con otras estrategias.

      **La cookie `PARAGLIDE_LOCALE` es un espejo, no una fuente.** Después de
      hidratar no hay token que leer del lado del cliente —la cookie de sesión es
      httpOnly—, así que sin ella la primera navegación sin recargar volvería al
      español. En el servidor manda siempre el token; quien edite la cookie solo
      se cambia el idioma a sí mismo hasta el siguiente render.

      También `<html lang>` dice la verdad ahora (`%paraglide.lang%` +
      `transformPageChunk`): de ahí salen la pronunciación de un lector de
      pantalla y el guionado del navegador.

      **En el demo, Carlos tiene el POS en inglés** y es el único. Sin eso lo
      único comprobable sería que el reclamo viaja, no que la pantalla lo obedece:
      `tests/e2e/idioma.spec.ts` entra como él y comprueba el menú en inglés, el
      `lang`, que sobrevive a navegar del lado del cliente, y que a los otros dos
      no les cambia nada. 4 pruebas, y las 24 de punta a punta en verde.

      **Lo que queda atado a T-810**: el idioma cambia cuando se emite un token
      nuevo. Hoy eso pasa al entrar y al cambiar de compañía; el selector tendrá
      que re-emitir igual que hace «cambiar de compañía» (RF-28), o el cambio no
      se vería hasta el siguiente login.
- [x] **T-810** Selector de idioma: en Configuración el de la compañía, en el
      menú del usuario el suyo. RN-28.

      **Hecho el 2026-08-23.** Dos endpoints, porque son dos cosas distintas y
      con permisos distintos:

      - `POST /auth/locale` — el de la persona, cualquiera el suyo. `locale` en
        nulo **borra la preferencia** en vez de guardar «español»: volver a
        heredar el de la compañía no es lo mismo que elegir español, y la
        diferencia se nota el día que el dueño cambia el idioma del negocio.
      - `PUT /settings/locales` — los dos de la compañía (pantalla y documento),
        solo administrador.

      **Los dos devuelven un token nuevo**, y eso no es un detalle: el idioma
      vive en el token (T-809), así que cambiarlo es emitir sesión otra vez,
      igual que cambiar de compañía (RF-28). Sin renovar la cookie, el cambio no
      se vería hasta el siguiente login.

      En el menú va un formulario de verdad con su botón, no un `onchange`: así
      funciona sin JavaScript como el resto del POS. **Defecto 27, encontrado
      acá:** el `<select>` con `value={…}` se reinicia al hidratar, y eso se come
      la elección de quien alcanzó a tocarlo antes —en una caja lenta, lo
      normal—. Quedó sin controlar, con `selected` en cada opción. Lo encontró la
      prueba de punta a punta: elegía «el de la compañía», el valor volvía solo a
      «inglés», y el formulario mandaba el idioma que ya estaba puesto.

      10 pruebas de integración en `backend/tests/test_idioma.py` —incluidas «lo
      que eligió la persona le gana a la compañía» y «un cajero no puede cambiar
      el de la compañía»— y una de punta a punta que cambia el idioma por el menú
      y lo devuelve.
- [x] **T-811** Idioma del **documento**, separado del de la pantalla. La
      factura es para el cliente y para Hacienda: una compañía costarricense
      emite en español aunque su cajero use el POS en portugués. RN-29.

      **Hecho el 2026-08-23, y salió más caro de lo previsto.** La nota anterior
      decía que «ya no toca las tres plantillas»: no era cierto. Las plantillas
      llamaban a `m.doc_*()` directamente, que resuelve con el idioma de la
      **sesión**; pasarles el del documento habría sido agregar un segundo
      argumento a 84 llamadas y confiar en que nadie olvide el siguiente.

      Se hizo al revés: `documentLabels(locale)` devuelve **todo el texto del
      documento ya resuelto** y las plantillas reciben ese diccionario. Ahora no
      tienen forma de equivocarse, porque no importan el catálogo —y eso lo
      vigila una prueba: ninguna de las tres importa `$lib/paraglide`—. Las
      fechas del documento también van en su idioma, por el `locale` explícito de
      T-806.

      `document_locale` viaja por `/users/me` y **no** por el token, a propósito:
      `/users/me` se relee en cada petición, así que cambiarlo en Configuración
      surte efecto en el siguiente clic y no en el siguiente login. No es un
      valor de autorización, así que no necesita estar firmado.

      Verificado de punta a punta con el caso exacto de RN-29: pantalla en
      portugués, factura en español —«Cant.» y no «Qtd.»—; y la vista previa de
      Configuración cambia de idioma sin mover la pantalla.

### Verificación — sin esto la fase no está terminada

- [x] **T-812** Prueba que recorre las plantillas buscando texto suelto: si
      alguien escribe una cadena dentro de un componente, la build se cae. Es lo
      único que impide que los catálogos se vayan quedando atrás. RNF-2.

      **Hecha el 2026-08-22** en `frontend/src/lib/ui/loose-text.test.ts`, y es
      **lo último que faltaba para empezar F3**: el plan pedía el mecanismo antes
      de F3 porque «cada pantalla escrita con la cadena adentro es una pantalla
      que hay que volver a abrir» (§8.7), y sin esta prueba nada impide que las
      pantallas de `/admin` nazcan así.

      **Lee el árbol de sintaxis, no las líneas.** El rastreador por líneas del
      scratchpad daba falsos positivos con lo que más abunda acá —comentarios de
      varias líneas y ternarios de clases de Tailwind— y una prueba que grita en
      falso se termina desactivando. En el árbol la diferencia es exacta: un
      comentario es un `Comment`, un `class={a ? 'x' : 'y'}` es un
      `ExpressionTag`, y el texto de verdad es un `Text`. Usa `svelte/compiler`
      para las pantallas y `typescript` para las acciones; ninguno compila nada,
      los dos solo leen.

      Cubre **dos mitades**, y la segunda va un poco más allá de la letra de la
      tarea a propósito: una acción de formulario produce tantos mensajes como la
      pantalla, así que se vigilan también los sumideros de texto de los `.ts`
      —`formError()`, `v.add()`, `toasts.*()`—. Dejar solo el marcado habría
      cubierto la mitad menos probable.

      **Encontró 12 textos que dos pasadas de T-804 y el rastreador por líneas no
      vieron**: un `aria-label="Editar …"` en `/clientes`, cuatro en `/registro`,
      dos en `/compania`, «vs. periodo anterior» en `StatCard` y cuatro rótulos
      en línea de `FacturaModerna` («Cédula», «Tel.», «Devuelto»). Es la
      justificación de la tarea, medida.

      Comprobada tumbándola: se inyectó un texto suelto en una pantalla y una
      frase en un `formError()`, y las dos mitades fallaron nombrando archivo y
      línea.

      La lista de excepciones tiene **una** entrada —`VentaSys`, la marca, en los
      seis `<title>`— y las razones escritas. No están los nombres de tecla
      porque no hacen falta: viven en expresiones. Una excepción que no se usa es
      la que después justifica la siguiente.
- [x] **T-817** El guardián también vigila el texto que va **dentro de un
      objeto**. Apareció leyendo `$lib/server/auth.ts` para T-809: había **seis
      `error(status, { message: 'frase en español' })`** que ninguna de las dos
      mitades de T-812 veía —el marcado no los toca y no son una llamada a
      `formError`—. Hecho el 2026-08-23.

      La lección es de la forma de la prueba: **un sumidero se declara por dónde
      entra el texto, no por cómo se llama la función.** La primera versión
      buscaba literales en posiciones de argumento, y acá el literal está una
      capa más adentro.

      Las cinco de `routes/**` pasaron al catálogo —son interfaz y pueden resolver
      la frase—; la de `$lib/server/auth.ts` no, porque es un adaptador: lanza
      `{ code: 'admin_only' }` y la frase la arma `+error.svelte`. `App.Error`
      quedó con `message` opcional por eso. Claves nuevas:
      `common_session_required`, `error_admin_only`, `invoice_not_found`,
      `settings_logo_missing` y `settings_logo_undecodable`.
- [x] **T-816** El guardián de RN-30 llega a `lib/domain` y `lib/application`
      del POS. Apareció al tomar la decisión de arriba: la regla ahí la sostenía
      una decisión y ninguna prueba. `layers.test.ts` no la habría visto —una
      frase suelta no importa nada, y `$lib/paraglide` no estaba en su lista de
      prohibidos—. Hecho el 2026-08-23.

      **No se vigilan llamadas, se vigilan literales.** `formError` y `toasts`
      viven en `ui/`, que el dominio no puede importar, así que la mitad de
      T-812 que mira sumideros no encontraría nada nunca ahí: una prueba que no
      puede fallar tranquiliza igual que una que funciona, y es peor. Lo que se
      busca es la frase devuelta como valor, que es la forma en que esto se
      colaba (`documentTitle()` devolvía «Factura electrónica»,
      `CURRENCIES[].label` decía «Colón costarricense»).

      **Dos disparadores.** Una frase es tres letras y un espacio —eso deja
      fuera los códigos y las claves, que es casi todo lo legítimo de esas dos
      carpetas— más la tilde y los signos de apertura, que un identificador no
      lleva y que atrapan la palabra sola («Cédula», «Anulación»). Queda un
      **hueco conocido y escrito**: una palabra sola sin tilde («Pendiente»)
      pasa. No se cierra con esta forma de prueba.

      Y `$lib/paraglide` entró a la lista de prohibidos del dominio, con su
      razón aparte en el mensaje de fallo: no es un asunto de pureza —el
      catálogo no arrastra Svelte— sino de RN-30, porque una capa que puede leer
      el catálogo puede armar la oración, y para armarla hay que saber el idioma
      de la petición. La aplicación ya lo rechazaba por la regla que solo le deja
      importar el dominio; comprobado.

      **Encontró dos**, y los dos eran de verdad: `thanksMessage`
      («¡Gracias por su compra!») y `legalNotice` («Este documento no tiene
      validez tributaria.») venían de fábrica en español dentro de
      `domain/settings.ts` **y se imprimen**. La factura de una compañía
      brasileña habría salido con la despedida en español hasta que alguien
      abriera Configuración. Se vaciaron: el dominio no puede traducirlos y la
      interfaz no puede ponerlos como respaldo del vacío, porque `optional()`
      distingue «nunca se configuró» de «se borró a propósito» y ese respaldo
      borraría la diferencia —quien quite la despedida la vería volver—. Los
      siembra el alta de compañía (T-304).

      Los otros cinco hallazgos son dato y quedaron como excepciones con su
      razón: los tres métodos de pago con espacio (valor de
      `sales.payment_method`, que se compara en reportes y plantillas) y los dos
      rótulos de `ID_TYPES` (nombre legal del documento en Costa Rica: no se
      traduce, se cambia por la lista de otro país).

      Comprobado tumbándolo tres veces: una frase y una palabra con tilde
      inyectadas en `domain/cart.ts`, y un `import` de `$lib/paraglide` en
      `domain/documents.ts` y en `application/checkout.ts`. Las tres fallan
      nombrando archivo y línea.
- [x] **T-813** Prueba de que los tres catálogos tienen las mismas claves. Una
      clave que falta en portugués no puede aparecer como `undefined` en la
      pantalla del cajero.
      **Sube de prioridad con la decisión de T-801**: Paraglide no avisa de esto
      —una clave que falta en `en` o `pt` cae al español en silencio, comprobado—
      así que esta prueba es la única red. No es un extra de la fase: es la mitad
      del criterio 2 del plan §8.5, y se paga acá.

      **Hecha el 2026-08-23** en `frontend/src/lib/ui/catalogs.test.ts`: 11
      pruebas. Y **hay un tercer silencio que el plan no preveía**, medido acá:

      | Lo que se rompe | Qué dice `npm run check` | Qué se ve en pantalla |
      |---|---|---|
      | Una clave falta en `en` | nada | la frase sale en español |
      | **Un parámetro falta en la traducción** | **nada** | **el dato desaparece de la frase** |
      | Una clave existe en `en` y no en `es` | nada | una función que nadie llama |

      El del medio es el peor y es el que justifica que la prueba mire los
      parámetros y no solo las claves: si `es` dice «Solo quedan {free} de
      {product}: hay {reserved} apartadas en otra venta» y el inglés dice «Only
      {free} left of {product}», no se ve una frase sin traducir —eso se nota—
      sino una frase completa a la que le falta un dato. El cajero inglés no se
      entera de que hay unidades apartadas.

      **La lista de pendientes solo puede encoger.** Como faltan 1.764 claves
      entre los dos idiomas, la prueba lleva `SIN_TRADUCIR` por archivo: un
      catálogo se quita de ahí cuando se traduce, y desde ese momento se exige
      completo. Va por archivo y no por clave porque una lista de 1.764 líneas no
      se lee ni se mantiene. **Y no se puede quedar vieja**: si un catálogo
      declarado pendiente ya está completo, la prueba falla pidiendo que lo
      saquen —una lista de pendientes desactualizada es una prueba apagada—.

      Comprobada tumbándola **cuatro veces**, una por red: un catálogo sacado de
      la lista sin traducir (14 claves nombradas), una clave huérfana en `en`, un
      parámetro de menos, y un catálogo completo que seguía declarado pendiente.

      Las excepciones son solo para las claves que faltan: **los parámetros y las
      claves huérfanas no admiten ninguna**, ni en un catálogo a medio traducir.
- [x] **T-814** Flujo de punta a punta en los tres idiomas: entrar, cobrar y ver
      la factura. Con el documento en español aunque la pantalla esté en
      portugués.

      **Hecha el 2026-08-23** en `tests/e2e/tres-idiomas.spec.ts`: 5 pruebas. Tres
      cobran una venta completa —una por idioma— y dos son las de RN-29: pantalla
      en portugués con factura en español, y la vista previa de Configuración
      cambiando de idioma sin mover la pantalla.

      **Los selectores no dependen del idioma**, y es la mitad del trabajo:
      `input[name=…]`, el `form` del modal y la tecla F1. Una prueba multi-idioma
      que busca botones por su texto solo prueba el idioma en que se escribió.

      Dos cosas que costaron y quedan escritas porque van a volver:

      - **Sin caja abierta, el botón de cobrar abre otro modal.** La primera
        versión fallaba señalando el campo de efectivo, que no existía porque el
        modal era el de apertura. Ahora la abre si hace falta.
      - **Las pestañas de Configuración son client-only**, así que el primer clic
        —si cae antes de que Svelte hidrate— marca el botón como activo y no
        cambia de sección. Se reintenta, igual que `clicHasta` en `login.spec.ts`.

      También quedó anotada la fragilidad de las pruebas que cambian el idioma de
      alguien: el estado del simulado se guarda en disco y sobrevive a la corrida,
      así que cada una lo deja como lo encontró y `idioma.spec.ts` **no da por
      hecho el seed** —lo pone como lo necesita—. Una corrida que falló a mitad
      dejó a Carlos en español y las tres pruebas siguientes empezaron a fallar
      señalando la pantalla.

---

## F10 · Compras y cuentas por pagar

> **Qué deja.** El mecanismo de módulos por plan (RN-49 a RN-51, RF-39 y
> RF-40) y el primer módulo: proveedores, la compra como entrada de mercadería
> con documento, condición de pago y crédito fiscal por línea, el costo
> promedio del producto, abonos y antigüedad de saldos (RN-52 a RN-57, RF-41 a
> RF-46). Plan §11 y §12.
>
> **De qué depende.** De F2 (compañías y planes) y de nada más. **Es la
> siguiente fase que se ejecuta**, antes que F6 y F7 (plan §9): emitir es
> obligatorio y por eso mismo todos los prospectos ya lo resolvieron, mientras
> que nadie está obligado a llevar su contabilidad en un programa. Es
> prerrequisito de F11: el crédito fiscal sale de acá.
>
> **Va primero aunque el número diga otra cosa.** Los números no se mueven —F8
> ya se ejecutó antes que F5 y se quedó en su casilla—; el orden de ejecución
> vive en plan §9. Y no hay F9: el número de tarea lleva la fase y el 9 lo
> ocupa Transversal (T-9nn) desde F2.
>
> **La puerta de la fase: T-916, decidida el 2026-09-12.** Se mantiene el
> español; T-913 sigue vigente y T-916 vuelve a apuntar a F6/T-608.
>
> El motivo para renombrar nunca fue la migración sino **el trabajo que abre
> esos archivos**, y ese trabajo es el ABM de sucursales y terminales (T-608),
> que está en F6. F10 abre `plans`, no `branches` ni `terminals`: renombrar
> solo `plans` daría lo peor de las dos —se paga parte del costo, se rompen los
> respaldos ya entregados y la mezcla queda igual—. El argumento fuerte de
> plan §3.9 tampoco cambió: `company_dump.py` exporta **por nombre de
> columna** y su `FORMATO = 1` no se entera de un rename, así que todo respaldo
> en manos de un cliente quedaría inservible en silencio.
>
> Que `plans` termine con `purchases`, `accounting` y `payroll` en inglés al
> lado de `nombre` y `max_*` en español **no es un defecto**: es lo que §3.9
> manda —«esta excepción es de las columnas que ya existen, no una licencia
> para las nuevas»—, y es lo mismo que hace T-621 con
> `companies.identification_type`.

**Costes medidos antes de empezar** —plan §12.7—:

- `test_esquema.py`: dos tablas y tres `ALTER` en una migración (`009`), más
  la `008` de los módulos.
- `test_aislamiento.py`: nueve rutas nuevas que declarar y probar.
- `test_error_codes.py`: seis códigos (uno de módulos, cinco de compras),
  cuatro lugares cada uno.
- `company_dump.py`: `suppliers` y `supplier_payments` viajan; se clasifican en
  el commit que las crea o `pytest` se cae.
- El invariante «entrada XML 79 800» se conserva: el lector agrega campos, no
  cambia cantidades.

### Módulos por plan

- [x] **T-1001** Migración `008-modulos-por-plan.sql`: `purchases`, `accounting`
      y `payroll` en `plans`, en inglés, y el modelo con `Boolean` y
      `server_default` como ya está `factura_electronica`. RN-51.

      **Hecho el 2026-09-12.** `TINYINT(1) NOT NULL DEFAULT 0` las tres, igual
      que `factura_electronica`, y la migración entró a la lista `MIGRACIONES`
      de `test_esquema.py` —sin eso el guardián compara contra un esquema que
      ya no es el de nadie—. Apagadas por omisión a propósito: un plan que ya
      existe es uno que alguien compró sin estos módulos.

      **Verificación:** `test_esquema.py`, 12 pruebas en verde: el modelo y la
      migración declaran lo mismo.

- [x] **T-1002** `require_module(name)` al lado de `get_current_user`: lee el
      plan de la compañía **en cada petición** (plan §11, misma razón que la
      suscripción) y se aplica solo a las escrituras. Código
      `module_not_in_plan` con `{module}` en los cuatro lugares. RN-49, RN-50,
      RF-40.

      **Hecho el 2026-09-12.** La regla quedó en `domain/modules.py` —qué
      módulos existen y qué significa que un plan incluya uno—, la consulta en
      `crud_membership.modulos_de` y la aplicación en la dependencia. Un `GET`
      **ni siquiera consulta el plan**: pasa antes del `if`, que es RN-50 y de
      paso no le cuesta una consulta a cada lectura.

      Un nombre de módulo que no existe —`require_module("purchase")`, en
      singular— **revienta con `UnknownModule`** en vez de dar 403: es un error
      de quien escribe la ruta, y un 403 lo disfrazaría de problema del plan
      del cliente y mandaría a soporte a mirar la suscripción equivocada.

      Los cuatro lugares del código se hicieron acá y no en T-1015: los tres
      catálogos van con variante por módulo —interpolar daría «Su plan no
      incluye accounting»— y `messages.test.ts` compara las dos listas de
      códigos, así que dejarlo para después tumbaba `npm test`.

      **Verificación:** `tests/test_modulos.py`, 24 pruebas. La primera ruta que
      usa la dependencia llega en T-1007, así que se prueba directa: las cuatro
      escrituras responden 403 con el código y el módulo como dato, las tres
      lecturas pasan con el plan vacío, y una lectura que consultara el plan
      hace fallar la prueba. `test_error_codes.py` ve el código levantado.

- [x] **T-1003** Panel de soporte: las tres casillas en el formulario de planes
      y la columna de módulos en el listado de compañías. RF-39.

      **Hecho el 2026-09-12.** Hizo falta un endpoint que no existía —había
      `GET /support/plans` y nada para editarlos—: `PUT
      /support/plans/{id}/modules`, con los tres módulos siempre y no un
      parche, porque una casilla sin marcar no viaja en el formulario y
      «la desmarcó» sería indistinguible de «no la tocó». Pantalla nueva
      `/admin/planes`.

      **Alcanza a todos los clientes del plan**, así que la bitácora anota
      cuántos son: apagar contabilidad en «Comercio» se la apaga a los catorce
      negocios que están ahí. Para dárselo a uno solo se le cambia el plan, que
      es el camino que ya existía.

      **Verificación:** `test_soporte.py::TestLosModulosDelPlan`, 6 pruebas: un
      plan nace sin módulos, se encienden y se apagan, el detalle de la bitácora
      trae el antes, el después y a cuántas compañías alcanza, un plan que no
      existe es 404 y el administrador de una compañía recibe 403. Los dos
      guardianes que saltaron —`test_aislamiento` y `test_suscripcion`— llevan
      la ruta declarada con su motivo.

- [x] **T-1003b** *(salió de T-1004)* **RN-49 dice que la navegación esconde el
      módulo que el plan no incluye, y el código hace lo contrario a propósito.**

      `navigation.ts` ya tenía la regla escrita para los roles: lo que no se
      puede abrir **se muestra con candado, no desaparece**, porque esconderlo
      hizo creer a un cajero que el sistema no tenía inventario. Para un módulo
      vale lo mismo y una razón más: un «Contabilidad 🔒» en el menú es lo único
      que le dice al dueño que el producto la tiene, y es gratis. Escondiéndolo,
      lo que se quiere vender es invisible justo para quien lo compraría.

      **Decidido con el usuario el 2026-09-12: se queda con candado y se
      corrigió RN-49.** La frase «la navegación del POS lo esconde» pasó a decir
      que se muestra con candado, con su porqué. Lo demás de RN-49 no estaba en
      discusión: el 403 del servidor es igual en los dos casos.

      Lo que cuesta, y hay que saberlo: el menú enseña algo que no se puede
      usar, así que alguien va a hacer clic y toparse con el 403. Se aceptó a
      cambio de que el módulo se pueda descubrir desde dentro del producto. Si
      esa fricción molesta, la salida es una pantalla que explique el módulo en
      vez de esconderlo —se planteó y se descartó por ahora—.

- [x] **T-1004** POS: `modules` viaja con el estado de la suscripción,
      `+layout.server.ts` arma la navegación con eso y `requireModule` en
      `lib/server/auth.ts` protege las `actions`. El simulado pone las
      banderas en los planes del seed —compañía 1 con los tres, compañía 2 sin
      ninguno— y `SEED_VERSION` sube. RF-40.

      **Hecho el 2026-09-12.** `modules` viaja en `/users/me`, que es donde el
      POS ya pregunta en cada petición: una compañía que sube de plan lo ve en
      su siguiente clic, sin volver a entrar. `requireModule` y `hasModule` en
      `lib/server/auth.ts`, `visibleGroups` recibe los módulos, `app.d.ts` gana
      `module` al lado de `state` y `+error.svelte` arma la frase. Lo que no
      venga queda apagado: falla cerrado contra un backend que todavía no mande
      el campo. `SEED_VERSION` a 8.

      **La entrada del menú llega con T-1014**, que es la que crea `/compras`.
      El mecanismo está y probado; lo que falta es un ítem que marcar.

      **Verificación:** `npm run check` en 0/0 y 550 pruebas del POS en verde.
      La de punta a punta con las dos compañías del demo va con T-1016, que es
      cuando hay una pantalla que abrir.

### Base de datos

- [x] **T-1005** Migración `009-compras.sql` (plan §12.2) y sus modelos:
      `suppliers`, `supplier_payments`, las columnas de `stock_entries` y
      `stock_entry_details`, y `products.cost`. `company_dump.py`: las dos
      tablas viajan. RN-52, RN-54.

      **Hecho el 2026-09-12.** En `company_dump.py` el orden importa y no es
      alfabético: `suppliers` va **antes** de `stock_entries` —una entrada
      puede referenciar uno— y `supplier_payments` al final de todo, porque
      referencia la compra y el movimiento de caja.

      Dos cosas que el guardián de esquema corrigió: `server_default="0"`
      emite `'0'` **con comillas** y hay que escribir `server_default=text("0")`
      para que diga lo mismo que la migración; y `is_active` tiene que ser
      `Boolean` y no `Integer` para dar `TINYINT(1)`.

      **Verificación:** `test_esquema.py` en verde, y la migración se corrió
      contra el MySQL de la pila de pruebas —no solo se leyó—, así que el SQL
      está comprobado además del modelo.

- [x] **T-1006** `domain/purchases.py` con la tabla de casos de plan §12.3:
      `weighted_average_cost`, `purchase_totals`, `remaining_balance`,
      `apply_payment`, `aging_bucket`. RN-53, RN-54, RN-55.

      **Hecho el 2026-09-12.** `purchase_totals` devuelve además el desglose
      **por tarifa**, ordenado, que es el crédito fiscal del D-104 (RF-45): sin
      ordenarlo, el orden lo decidiría en qué fila del documento apareció cada
      tarifa y el reporte del mes saldría distinto cada vez.

      `remaining_balance` nunca devuelve negativo aunque `apply_payment` ya lo
      impida: es la red por si una fila vieja trae un abono de más, que se
      sumaría al saldo del proveedor y le rebajaría lo que sí debe en otra
      factura.

      **Verificación:** `pytest tests/domain/test_purchases.py`, 31 pruebas,
      cobertura 100 %. Los casos numéricos del plan dan: 10 a 100 + 10 a 120 →
      110; existencia −3 + 10 a 50 → 50; 1 001 sobre 1 000 →
      `PaymentExceedsBalance`; y un documento con 13 %, 1 % y exento desglosa
      en tres tarifas sin promediarlas.

### Dominio


### Backend

- [x] **T-1007** Proveedores: las rutas `GET/POST/PUT /suppliers`; se
      desactivan, no se borran. RF-41.

      **Hecho el 2026-09-12.** Es la primera ruta que exige un módulo de
      verdad, y quedó demostrado lo que T-1002 solo fijaba en abstracto: la
      escritura responde `module_not_in_plan` y la lista se lee igual (RN-50).

      **Sin `SupplierRepository`.** El puerto no se escribió porque no hay
      todavía ningún caso de uso que lo necesite: esto es un ABM y el servicio
      habla con SQLAlchemy como los demás `crud_*`. El puerto entra con T-1009,
      que es cuando `RegisterPurchase` tiene que poder probarse sin base
      (RN-20). Declararlo antes sería un puerto con un solo implementador y
      ningún cliente.

      `supplier_inactive` **tampoco** entró acá: lo levanta la compra a un
      proveedor desactivado, que es T-1009. Un código en `CODES` que nadie
      lanza tumba `test_error_codes.py`.

      Cuatro códigos nuevos que el plan no tenía: `supplier_not_found`,
      `supplier_identification_taken` —con el nombre de quién ya la tiene, o la
      frase manda a buscar en la lista—, y dos genéricos de identificación,
      `invalid_identification_type` e `identification_required`, sin prefijo de
      proveedor porque `companies` (T-621) y `clients` (T-617) tienen el mismo
      par de columnas. Anotados en plan §12.5.

      De paso, `bootstrap.py` gana `--plan-modulos`: sin eso no había forma de
      dar de alta una compañía con compras, ni en una instalación real ni en la
      batería. Un módulo que no existe detiene el guion en vez de ignorarse.

      **Verificación:** `tests/test_proveedores.py`, 15 pruebas, y las dos
      rutas dentro de `test_aislamiento.py` —la lista no mezcla y el `PUT` a un
      proveedor de otra compañía da 404—. 872 pruebas del backend en verde.

- [x] **T-1008** El lector de XML (`lib/server/import/hacienda.ts`) extrae
      además `Emisor` (tipo, número, nombre), `Clave`, `NumeroConsecutivo`,
      `FechaEmision`, `CondicionVenta` con `PlazoCredito`, y por línea
      `Impuesto/Tarifa` y `Impuesto/Monto`. RF-42, RN-53.

      **Hecho el 2026-09-12.** Tres cosas que solo se ven leyendo los
      comprobantes de verdad, y que el diseño no contemplaba:

      1. **Una línea puede traer varios `<Impuesto>`** —el IVA y uno
         selectivo—. La tarifa que se guarda es la del código `01`, que es la
         que va al D-104; si no hay IVA se toma la del primero.
      2. **El monto sale de `ImpuestoNeto`, no de la suma de los montos.** El
         neto ya descuenta `ImpuestoAsumidoEmisorFabrica`, que es impuesto que
         el comprador **no** pagó y por lo tanto no puede acreditarse.
      3. **`CondicionVenta` tiene más de dos valores.** Apartado, consignación
         y prepago se tratan como contado: tratarlos como crédito crearía una
         cuenta por pagar que nadie va a cobrar.

      La clave de 50 dígitos se guarda aparte del consecutivo: son dos cosas.

      **Verificación:** `hacienda.test.ts`, 22 pruebas. Tres corren contra
      comprobantes **reales** del material de Hacienda que está en el repo
      —una a crédito a 30 días con IVA de 175,50 y 70,20 por línea, una al 1 %
      y una con condición 11—, y una comprueba que el invariante de 79 800 no
      se movió: esa factura no trae impuesto ni condición, así que los campos
      nuevos salen en su valor de reposo. El lector aprendió a leer más, no a
      leer distinto.

- [x] **T-1009** `RegisterPurchase`: aplica el stock como hoy, actualiza
      `products.cost` con el promedio, calcula `due_date` desde la condición.
      La factura duplicada pasa a ser **por proveedor**. RN-52, RN-54, RN-57.

      **Hecho el 2026-09-12.** No hay clase `RegisterPurchase`: una compra **es**
      una entrada con proveedor, así que se extendió `RegisterStockEntry`
      (plan §12.1). El puerto `suppliers` es opcional, y por eso las pruebas de
      lo que ya existía no tuvieron que aprender nada nuevo.

      Tres cosas que aparecieron al escribirlo:

      1. **El costo y el stock van en el mismo paso, por línea.** Si un
         producto aparece dos veces en la misma factura, el segundo promedio
         tiene que ver las existencias que dejó el primero; calculándolos en
         dos vueltas, los dos promediarían contra la existencia original. Hay
         una prueba con ese caso: 10 a 100 + 10 a 120 → 110, después + 20 a
         140 → 125.
      2. **El vencimiento se cuenta desde la fecha del documento**, no desde la
         de carga. Una factura del 28 que se digita el 3 vence a los 30 días
         del 28; contar desde la captura le regala al negocio los días que
         tardó en digitarla.
      3. **Un crédito a cero días es contado.** Una deuda que vence el mismo
         día no es una deuda, y dejarla como crédito abriría una cuenta por
         pagar que nace saldada.

      El código duplicado se sigue llamando `duplicate_document` —el que ya
      existía— y lo que cambió es con qué se compara: ahora lleva el
      proveedor. `duplicate_supplier_document` no hizo falta.

      **Lo que no entró:** el abono automático de una compra de contado. Es de
      T-1010, donde vive `PaySupplier`: escribirlo acá sería tener la regla del
      efectivo (RN-56) en dos sitios. Hasta entonces, una compra de contado
      queda con saldo.

      **Verificación:** `tests/application/test_compra.py`, 22 pruebas sin base,
      y cinco de dominio nuevas para el impuesto de la línea. 904 del backend
      en verde con cobertura 100 %.

      De paso se quitó una rama muerta: el `if producto is not None` antes de
      actualizar el costo no lo puede alcanzar ninguna prueba —el producto o se
      validó arriba o se acaba de crear—, y la cobertura al 100 % lo señaló.

- [x] **T-1010** `PaySupplier`: comprueba el saldo (`payment_exceeds_balance`);
      en efectivo exige turno abierto y escribe el `cash_movements` de salida
      **antes** de guardar el abono. RN-55, RN-56, RF-44. Ruta:
      `POST /purchases/{entry_id}/payments`, con `require_admin` y
      `require_module("purchases")` al lado.

      **Incluye el abono automático de una compra de contado**, que T-1009 dejó
      pendiente a propósito: la regla del efectivo vive acá y escribirla dos
      veces es como se separan.

      **Verificación:** `tests/test_compras.py`, 13 pruebas contra la pila real
      —el esperado del arqueo baja exactamente lo abonado—, y
      `tests/application/test_abono_a_proveedor.py`, 22 con dobles. 956 del
      backend en verde con cobertura 100 %; 570 del POS y `npm run check` 0/0.

      **Cuatro cosas que aparecieron escribiéndolo, y que cambian el plan:**

      1. **`cash_session_required` no se creó: es `cash_no_open_session`, que ya
         existía.** Dos códigos para el mismo hecho es peor que uno solo, y la
         frase que ya estaba —«No hay una caja abierta. Ábrala antes de
         continuar»— sirve igual acá. Plan §12.5 hay que corregirlo.

      2. **El motivo del movimiento de caja lo arma el POS, no el backend.** El
         plan decía que `PaySupplier` escribiera «Pago a ‹proveedor›, factura
         ‹n›», y eso es texto para una persona escrito fuera de la interfaz: lo
         prohíbe RN-30 y dejaría a un cajero brasileño con la mitad del arqueo
         en español. Viaja en `reason`, que es de donde ya sale el motivo de
         cualquier otro movimiento de gaveta.

      3. **Una compra de contado no se paga sola: hace falta decir con qué.**
         `payment_terms` dice **cuándo** y el XML de Hacienda no trae más que
         eso (`CondicionVenta` 01 es contado y no dice cómo). Sin
         `payment_method` la compra queda con saldo y se abona desde cuentas
         por pagar. Adivinar «efectivo» descuadraría un arqueo, y adivinar
         «transferencia» inventaría un movimiento bancario.

         La consecuencia hay que mirarla de frente: una compra de contado
         pagada **en efectivo sin turno abierto** no entra —ni la mercadería—,
         porque la compra y el pago son el mismo hecho. El «no» es accionable:
         se abre la caja, o se marca el pago como transferencia.

      4. **`not_a_purchase` tampoco se creó.** Una entrada sin proveedor no
         genera cuenta por pagar (RN-52), así que desde cuentas por pagar **no
         existe**: responde `entry_not_found`, con el mismo criterio por el que
         un proveedor de otra compañía responde «no está» y no «no es suyo»
         (RNF-1). La respuesta se da desde donde se pregunta.

      Los códigos que sí nacieron son cinco y no uno: `payment_exceeds_balance`,
      `payment_not_positive`, `invalid_payment_method`, `purchase_cancelled` y
      `payment_failed`. Los cuatro lugares de cada uno se hicieron acá, no en
      T-1015, por lo mismo que en T-1002: `messages.test.ts` compara las dos
      listas de códigos y diferirlo tumba `npm test`.

      De paso, `AddCashMovement` ganó un `apply()` que no confirma, y
      `PaySupplier` otro igual. Es lo que permite que la salida de caja, el
      abono y —en una compra de contado— la mercadería entren en una sola
      transacción, sin que la regla del efectivo quede escrita dos veces.

- [x] **T-1011** Anular una compra: solo sin abonos
      (`purchase_has_payments`), revierte el stock como la anulación de hoy,
      marca `anulada` y escribe en bitácora. **No toca `products.cost`**, y la
      pantalla lo dirá (T-1013). RF-46, RN-57.

      **Verificación:** `tests/test_compras.py`, 4 pruebas nuevas contra la
      pila real —la fila de `audit_log` con el motivo incluido—, y 6 con dobles
      en `tests/application/test_compra.py`. 966 del backend con cobertura
      100 %; 572 del POS y `npm run check` 0/0.

      **No se creó `VoidPurchase` ni `POST /purchases/{id}/void`.** Se extendió
      `CancelStockEntry` y su ruta de siempre,
      `POST /inventory/entry/{id}/cancel`, por la misma razón por la que la
      compra es la entrada (plan §12.1): es el mismo acto sobre la misma fila.
      Dos rutas serían dos sitios donde escribir la regla de los abonos, y el
      día que cambie va a cambiar en uno. Plan §12.4 corregido.

      Tres cosas que decidió el código:

      1. **El motivo es obligatorio solo si es compra.** RF-46 lo pide para una
         compra; la pantalla de entradas nunca lo pidió y exigirlo en el
         esquema la rompería. Por eso se comprueba **después** de `apply()`,
         que es cuando se sabe cuál de las dos es, y por eso el cuerpo del POST
         es opcional. Código nuevo: `void_reason_required`.

      2. **Se pregunta por los abonos siempre, sin mirar `supplier_id`.** Una
         entrada que no es compra no tiene abonos y la respuesta es la lista
         vacía; condicionarlo a la columna sería confiar en que esa columna y
         la tabla de abonos nunca se contradigan, y la que manda es la tabla.

      3. **La cuenta por pagar se revierte sola.** Es implícita —total menos
         abonos— así que marcar `anulada` basta, siempre que `/payables`
         (T-1012) filtre por estado. Queda anotado ahí.

      La anotación de bitácora entra en la transacción de la anulación, con el
      mismo `apply()` que T-1010 le puso a `AddCashMovement` y `PaySupplier`:
      una anulación sin su rastro es justo la que después nadie puede explicar.
      Acción `anular_compra` o `anular_entrada` según tenga proveedor.

      **Lo que no pudo probarse contra la pila:** que `products.cost` no cambie.
      El costo **no está en la respuesta de producto**, así que no hay por dónde
      leerlo desde una prueba de API. La regla sí está cubierta con dobles. La
      pantalla de compras lo va a necesitar igual, así que exponerlo es parte de
      T-1013.

- [x] **T-1011b** El módulo también se exige al **registrar** una compra.
      RN-49, RN-50. Apareció al cerrar T-1011 y lo decidió el usuario el
      2026-09-12.

      T-1009 hizo que `POST /inventory/entry` aceptara `supplier_id`, pero esa
      ruta nunca llevó `require_module`: una compañía que **bajaba** de plan
      seguía registrando compras a los proveedores que ya tenía. Sin el módulo
      no puede dar de alta proveedores nuevos, así que solo lo alcanzaba quien
      ya los tenía —que es exactamente el caso que describe RN-50—.

      **No se puso como dependencia de ruta**, y ahí está lo que enseña: una
      dependencia decide **antes de que exista el cuerpo**, y este endpoint
      escribe dos cosas distintas según lo que traiga —entrada sin proveedor,
      compra con él (RN-52)—. Ponerla igual le cerraría el inventario a quien
      bajó de plan, que es lo contrario de RN-50. Así que `require_module`
      quedó apoyado en una función suelta, `exigir_modulo(db, sesion, module)`,
      que el endpoint llama solo si hay `supplier_id`.

      **Verificación:** `tests/test_compras.py`, dos pruebas con una compañía
      cuyo plan no trae el módulo: con proveedor responde 403
      `module_not_in_plan`, y sin proveedor la entrada sube el stock igual.

- [x] **T-1012** Cuentas por pagar y reporte: `GET /payables` (saldo por compra
      y por proveedor, antigüedad) y `GET /reports/purchases` (base e impuesto
      **por tarifa**). RF-44, RF-45.

      **Los dos filtran por `status = 'aplicada'` y por `supplier_id NOT
      NULL`.** Lo primero es lo que hace que anular revierta la cuenta por pagar
      (RN-57): el saldo es implícito —total menos abonos— así que basta con
      dejar las anuladas fuera. Lo segundo es RN-52: una entrada sin proveedor
      no debe nada ni respalda un crédito fiscal, por mucho que haya movido
      inventario.

      **El reporte filtra por la fecha del documento, no por la de carga.** Una
      factura del 28 que se digita el 3 es IVA del mes de la factura; contarla
      por la carga desplazaría **dos** declaraciones a la vez. Para las que no
      la traen se usa la de carga, que es lo único que hay.

      **Verificación:** `tests/test_compras.py`, 12 pruebas nuevas contra la
      pila; `tests/test_aislamiento.py`, dos más. 982 del backend con cobertura
      100 %; 572 del POS y `npm run check` 0/0.

      Tres cosas que decidió el código:

      1. **`/payables` es su propio prefijo y no `/purchases/payables`.** Lo que
         se debe no es una compra sino el estado de un conjunto de ellas, y F11
         va a leerlo para el asiento sin entrar por el módulo de compras.
         Tampoco lleva `require_module`: leer se puede siempre (RN-50), y dejar
         de pagar no es una funcionalidad que se compre.
      2. **Los cuatro tramos vienen siempre**, aunque vayan en cero. Una tabla
         que cambia de columnas según los datos se lee distinto cada vez, y el
         tramo que falta es justo el que uno querría ver vacío.
      3. **`days_overdue` lo calcula el servidor**, como `as_of`. Con el reloj
         del cliente, dos cajas verían tramos distintos del mismo saldo.

      **`crud_payables.py` lleva el filtro por compañía escrito a mano**, igual
      que `crud_report.py` y por lo mismo: la consulta agrupa y no carga
      entidades, así que el filtro automático de `tenancy.py` no la alcanza. Hay
      prueba de aislamiento para las dos consultas nuevas.

      **De paso, un defecto en las pruebas que no era de F10:** la base de la
      pila de pruebas vive mientras viva la pila, así que un reporte comparado
      contra un absoluto pasa la primera corrida y falla la segunda. Las de
      reportes ahora miden **por diferencia**, y la de aislamiento le da a cada
      corrida su propio día. Está anotado como defecto.

      **Lo que no se hizo:** `GET /purchases?supplier=&from=&to=`, la lista de
      compras que plan §12.4 menciona. No la pide ninguna tarea ni ninguna
      pantalla: `/inventory/entries` ya lista las entradas, compras incluidas.
      Si T-1013 la necesita con filtros propios, se agrega ahí.

### Frontend

- [x] **T-1013** La pantalla de entradas gana proveedor, documento, condición y
      tarifa por línea, con el aviso de RN-53 cuando la del documento difiere
      de la del producto, y conserva la vista previa (§8, regla 6). RF-42,
      RF-43.

      Hechas también las tres que dejaron T-1010 y T-1011: el **método de pago**
      cuando la condición es contado —con el aviso de que en efectivo hace falta
      caja abierta—, el **motivo al anular** una compra, y **`cost` en la
      respuesta de producto**.

      **Verificación:** `tests/e2e/compras.spec.ts`, tres pruebas contra el
      simulado: una compra a crédito con su vencimiento contado desde la fecha
      del documento, una anulación que exige motivo, y el XML que marca al
      proveedor como nuevo conservando el invariante de ₡79 800. 982 del
      backend, 574 del POS, `npm run check` 0/0.

      Cuatro cosas que decidió el código:

      1. **El serializador de entradas no devolvía nada de F10.** La pantalla no
         tenía cómo saber si una entrada era compra, así que `serialize()` pasa
         a devolver `supplier_id`, la fecha y clave del documento, la condición,
         el vencimiento, el subtotal, el impuesto y la tarifa de cada línea.
      2. **El proveedor se reconoce por identificación, nunca por nombre.** El
         nombre cambia —razón social, nombre comercial, cómo lo escribió el
         emisor ese día— sin que cambie con quién se trata; emparejar por nombre
         crearía una ficha nueva cada vez que el proveedor edite su factura y el
         saldo quedaría repartido entre las dos.
      3. **El proveedor nuevo se da de alta antes que la compra**, no dentro. Si
         la compra falla, el proveedor queda dado de alta y el segundo intento lo
         encuentra en la lista; al revés dejaría una compra sin a quién pagarle.
         El cuerpo se relee campo por campo: lo que llega por un formulario es de
         quien tenga la pantalla abierta.
      4. **El motivo del pago en efectivo lo arma la pantalla** y viaja en
         `payment_reason` (RN-30), que es lo que T-1010 dejó preparado.

      **El simulado se puso al día acá y no en T-1015**, porque sin él la
      pantalla no se puede verificar: proveedores con sus tres rutas, los campos
      de compra en la entrada, el costo promedio, el abono automático con su
      salida de caja, y la anulación con motivo y guardia de abonos.
      `SEED_VERSION` sube a 9.

      **Un defecto que no era de F10 y que esto destapó:** una fecha sin hora se
      mostraba **un día antes**. Está anotado aparte.

- [x] **T-1014** `/compras/proveedores` y `/compras/cuentas-por-pagar`: saldos,
      antigüedad y abonar con método y referencia. RF-41, RF-44.

      **Verificación:** `tests/e2e/compras.spec.ts`, una prueba que abre la
      caja, abona 1 200 en efectivo a una factura de 2 000 y comprueba las tres
      cosas a la vez: el saldo baja a 800, el «debe haber en caja» del arqueo
      baja exactamente 1 200, y el movimiento lleva el motivo que armó la
      pantalla. 52 de punta a punta en verde, 574 del POS, 982 del backend,
      `npm run check` 0/0.

      Cuatro cosas que decidió el código:

      1. **«Compras» es la primera entrada del menú atada a un módulo** (RN-49).
         Con el plan sin él se ve con candado y no desaparece, que es lo que
         `visibleGroups` ya hacía para los roles: un «Compras 🔒» es lo único
         que le dice al dueño que el producto lo tiene.
      2. **`/compras` redirige a cuentas por pagar**, no a proveedores: lo que
         se mira todos los días es a quién hay que pagarle; dar de alta un
         proveedor pasa una vez al mes.
      3. **El motivo del movimiento de caja lo arma la pantalla** y viaja en
         `reason` (RN-30), cerrando lo que T-1010 dejó preparado.
      4. **`/payables` se lee con `apiSafe`**: leer no exige el módulo (RN-50),
         pero un backend sin F10 no tiene la ruta y la pantalla tiene que abrir
         igual, con los cuatro tramos en cero.

      Entró también el catálogo `messages/*/purchases.json` —77 claves en los
      tres idiomas, declarado en `project.inlang/settings.json`— y los tres
      endpoints que le faltaban al simulado, que eran lo último de T-1015.

- [x] **T-1015** Simulado y catálogos. **Se hizo repartida entre las tareas que
      la necesitaban**, y esa es la lección: el simulado no es un paso al final
      sino la condición para verificar cada pantalla.

      - Los **códigos** en sus cuatro lugares: con T-1002, T-1007 y T-1010.
        Siempre por lo mismo —`messages.test.ts` compara las dos listas de
        códigos y diferirlos tumba `npm test`—.
      - **Proveedores, campos de compra, costo promedio, abono automático y
        anulación con motivo**: con T-1013, sin lo cual la pantalla de entradas
        no se podía verificar. `SEED_VERSION` a 9.
      - **`POST /purchases/{id}/payments`, `GET /payables` y
        `GET /reports/purchases`**, y el catálogo `purchases.json` declarado en
        `project.inlang/settings.json`: con T-1014.

      **Verificación:** las 52 de punta a punta pasan contra el simulado, que es
      la prueba de que el contrato coincide; `npm test` y `npm run check` en
      0/0.

### Verificación — sin esto la fase no está terminada

- [x] **T-1016** Punta a punta con el navegador, en una compañía que la prueba
      da de alta: XML de proveedor → compra a crédito → el reporte por tarifa
      muestra su IVA → abono en efectivo → el arqueo cuadra → una segunda
      compra sin abonos se anula. Y en la compañía sin el módulo, el menú lo
      muestra **con candado** —T-1003b, decidido— y la escritura rebota.

      `tests/e2e/compras-cierre.spec.ts`, dos pruebas. La primera recorre los
      cinco pasos en una compañía propia con el catálogo vacío, que es lo que
      hace comprobables las cifras: 24 × 1 200 = 28 800 de base, 3 744 de
      impuesto al 13 %, 32 544 de saldo, 20 000 abonados y el arqueo en 30 000.
      La segunda comprueba las dos mitades de RN-50: la pantalla **abre** sin el
      módulo y el alta rebota.

      **Hizo falta una pantalla que ninguna tarea creaba:** el reporte de
      compras por tarifa en `/dashboard`. Plan §12.4 lo dice —«va con los demás,
      en `/dashboard`»— y la verificación de esta tarea lo exige, pero no tenía
      tarea propia. Entró acá, con sus claves en los tres catálogos.

      **Y destapó dos defectos reales**, los dos anotados aparte:

      1. **El candado del menú decía algo falso.** A un administrador sin el
         módulo le decía «solo para administradores. Pídale a un administrador
         que le cambie el rol»: lo mandaba a resolver algo que ya tenía
         resuelto, cuando lo que le faltaba era el plan. Peor todavía, era justo
         el mensaje que tenía que vender el módulo.
      2. **`requireModule` existía desde T-1004 y no lo usaba nadie.** Las tres
         acciones de escritura del POS lo llaman ahora, y el simulado ganó su
         `exigirModulo()`: sin él una compañía en plan Básico creaba proveedores
         contra el simulado mientras el backend los rechazaba, que es la clase
         de divergencia que hace que una prueba de punta a punta mienta.

      **Verificación:** la prueba de Playwright pasa contra el simulado y, a
      mano, contra el stack real; `pytest`, `npm test` y `npm run check` en
      verde.

---

## F11 · Contabilidad — **terminada el 2026-09-13**

> **Qué deja.** Partida doble por compañía: catálogo desde plantilla, asientos
> automáticos **en la misma transacción** con «por clasificar» para que nada
> se detenga, asientos manuales y de ajuste, periodos con cierre inmutable,
> libro diario, mayor, balance de comprobación, estado de resultados, balance
> general y el borrador del D-104 (RN-58 a RN-65, RF-47 a RF-54). Plan §13.
>
> **De qué depende.** De F10: el crédito fiscal y el costo del producto salen
> de ahí. Funciona sin F12 y recibe su asiento cuando exista.

**Costes medidos antes de empezar** —plan §13.7—:

- `test_esquema.py`: cinco tablas y un `ALTER` (`010`).
- `test_ports.py`: `Ledger` entra en la firma de **seis** casos de uso que ya
  existen; `test_characterization.py` es la prueba de que el enganche no toca
  el dinero.
- `test_aislamiento.py`: unas doce rutas. `test_error_codes.py`: siete
  códigos. `company_dump.py`: las cinco tablas viajan.
- `sales.payment_method` es texto libre y el mapeo necesita un conjunto
  cerrado: T-1104 va antes que el enganche.
- `domain/ledger.py` es el módulo de dominio más grande hasta ahora, y la
  cobertura al 100 % es obligatoria.

### Decisiones que hay que tomar antes de empezar

| | Qué hay que decidir | Qué espera |
|---|---|---|
| Rol contador | Hoy solo el administrador entra a contabilidad y compras. Un contador externo (RN-3 ya lo describe) necesita leer los libros y escribir asientos **sin** tocar catálogo, precios ni usuarios. ¿Cuarto rol o el administrador se lo presta? Toca `user_companies.rol`, `requireAdmin` y el panel. Plan §13.6 | T-1111 (quién ve las pantallas). Lo anterior no depende de esto |

### Base de datos

- [x] **T-1101** Migración `010-contabilidad.sql` (plan §13.2) y sus modelos:
      `accounts`, `account_mappings`, `accounting_periods`, `journal_entries`,
      `journal_lines` y `sale_details.unit_cost`. `company_dump.py`: las cinco
      viajan. RN-58, RN-61, RN-63.

      **Verificación:** `test_esquema.py`; exportar y restaurar una compañía
      con un libro deja el mismo balance de comprobación.

      **Hecho.** El `SHOW CREATE TABLE` que deja la migración y el que deja
      `create_all` solo difieren en el orden de las columnas y en los nombres
      que MySQL autogenera para las foráneas, como ya pasa con el resto.
      `month` va en SMALLINT y no en el TINYINT del boceto: el byte que se
      ahorra no paga un tipo que solo existe en MySQL.

### Dominio

- [x] **T-1102** `domain/ledger.py`: `JournalEntry` que **no se construye
      desbalanceado**; `post_sale`, `post_return`, `post_cash_close`,
      `post_cash_movement`, `post_purchase`, `post_supplier_payment`;
      `assert_open`. La tabla de casos de plan §13.3, con las cifras de los
      invariantes. RN-58, RN-59, RN-62.

      **Verificación:** la venta 3 × 1 450 con costo 900 da el asiento de
      §13.3 —7 615,50 por lado—; construir uno desbalanceado lanza
      `EntryNotBalanced`; un método de pago sin cuenta cae en por clasificar;
      el cierre 53 000 contra 53 277,00 asienta un faltante de 277,00;
      cobertura 100 %.

      **Hecho.** Con el mapeo VACÍO la venta sigue dejando asiento, que es
      RN-59 comprobada. Dos hallazgos: `TaxRate.as_percent` escribe el 10 %
      como `1E+1` —el papel habría quedado en 'sales_1E+1' y todas esas
      ventas en «por clasificar» sin aviso—, y la compra tiene que ir
      **siempre** contra proveedores: el «caja (contado)» del plan contaba
      la plata dos veces, porque desde F10 la de contado ya crea su abono.

- [x] **T-1103** Reportes en el dominio: `trial_balance`, `income_statement`,
      `balance_sheet`, `vat_draft`. RF-53, RF-54, RN-65.

      **Verificación:** con los asientos de la tabla, activo = pasivo +
      patrimonio + resultado; el `vat_draft` del ejemplo da saldo a favor de
      12 434,50 (565,50 − 13 000).

      **Hecho.** El escenario de la prueba se arma con los `post_*` de
      T-1102 y no a mano: así no puede cuadrar por casualidad. Activo
      214 938,50 = pasivo 63 565,50 + patrimonio 150 000 + resultado 1 373,
      y el D-104 del ejemplo da los 12 434,50 a favor.

### Backend

- [x] **T-1104** `sales.payment_method` deja de ser texto libre: un conjunto
      cerrado de valores admitidos —los que hoy existen, **sin renombrar lo
      guardado**— sobre el que se define el mapeo; un valor fuera del conjunto
      se rechaza al vender.

      **Verificación:** `POST /sales` con un método desconocido responde
      código; los reportes de métodos de pago dan lo mismo que antes.

      **Hecho.** Los cuatro valores que ya existen, sin renombrar ninguno.
      `CASH_METHOD` se mudó al dominio: estaba escrito en el caso de uso y
      otra vez en el POS, y el libro lo necesitaba en un tercer sitio.

- [x] **T-1105** Puerto `Ledger` con adaptador nulo y adaptador SQLAlchemy en
      **la misma sesión**; enganche en `RegisterSale`, `RegisterReturn`,
      `CloseCashSession`, movimientos de caja, `RegisterPurchase` y
      `PaySupplier`. RN-59, RF-50.

      **Verificación:** con el módulo apagado, `test_characterization.py` da
      las mismas cifras; con el módulo activo, una venta deja un
      `journal_entries` con `source_type = 'sale'` y el índice único impide el
      segundo; sin la cuenta `cash` en el mapeo, la línea va a 1.9.99 **y la
      venta se confirma**.

      **Hecho.** El puerto recibe **el hecho y no el asiento**: con
      `post(entry)` quien llama tendría que leer el mapeo, o sea saber de
      contabilidad, que es lo que el puerto existe para evitar. El
      correlativo sin huecos exige serializar, y se serializa sobre la fila
      de la compañía.

- [x] **T-1106** `unit_cost` congelado en `sale_details` al vender, desde
      `products.cost`; `NULL` si el producto no tiene costo. RN-63.

      **Verificación:** vender, comprar más caro, y la línea vendida conserva
      su costo; `post_sale` de una línea sin costo no asienta el par costo /
      inventario.

      **Hecho.** El repositorio gana `sold_costs`, que es lo que hace que
      devolver mercadería la reponga por lo que costó y no por lo de hoy.

- [x] **T-1107** `ActivateAccounting`: la plantilla de plan §13.8, el mapeo por
      omisión completo, el periodo de la fecha de inicio y el asiento de
      apertura; `accounting` en `settings`. RF-47, RN-60.

      **Verificación:** activar deja todas las cuentas de sistema y **ninguna
      fila del mapeo falta**; una apertura desbalanceada responde
      `invalid_opening_balance`; activar dos veces responde código.

      **Hecho.** La prueba corre los seis `post_*` contra el catálogo
      sembrado en vez de leer la tabla del mapeo. Así apareció que faltaba
      una fila: la venta cobrada por transferencia o SINPE Móvil no tenía
      cuenta y se habría ido entera a 1.9.99 el primer día.

- [x] **T-1108** Catálogo y mapeo: rutas, `account_is_system`,
      `account_in_use`, y `Reclassify`. RF-48, RF-49, RN-64.

      **Verificación:** borrar 1.1.01 → código; borrar una cuenta nueva sin
      movimientos → se va; reclasificar deja 1.9.99 en cero con un asiento
      `adjustment` que referencia al original.

      **Hecho.** El dato de los tres códigos de cuenta se llama
      `account_code` y no `code`: `code` es el nombre del parámetro de
      `api_error` y pasarlo como dato revienta en tiempo de ejecución.

- [x] **T-1109** Asientos manuales y de ajuste; periodos y `ClosePeriod` con
      confirmación y bitácora; `period_closed`, `period_not_closeable`. RF-51,
      RF-52, RN-61.

      **Verificación:** cerrar agosto con julio abierto → código; cerrar julio
      y luego un manual con fecha en julio → `period_closed`; `audit_log`
      tiene el cierre con quién y cuándo.

      **Hecho.** Y se cerró un agujero que RN-61 dejaba abierto: cerrar
      enero no impedía capturar algo con fecha en diciembre **si diciembre
      nunca tuvo un asiento**, porque entonces no tiene fila y nacía
      abierto. Un mes ya no puede nacer detrás de uno cerrado.

- [x] **T-1110** Rutas de los cinco reportes y del D-104, con `format=csv`.
      RF-53, RF-54.

      **Verificación:** el CSV del diario abre y suma lo mismo que la pantalla;
      el D-104 del mes da el débito por tarifa **igual** al desglose de ventas
      por tarifa (RF-21) y el crédito **igual** al reporte de compras (RF-45).

      **Hecho.** Faltaba media ruta: `GET /reports/sales_by_rate`, el espejo
      de `/reports/purchases`. Y las dos mitades venían en unidades
      distintas —la venta guarda 0,13 y la compra 13—, que sin convertir
      parte el D-104 en dos filas. El `?format=csv` del plan no va en el
      backend: un CSV lleva encabezados y los encabezados son texto (RN-30).

### Frontend

- [x] **T-1111** Pantallas de `/contabilidad` (plan §13.4): el resumen con por
      clasificar en rojo, activación, cuentas, mapeo, asientos, periodos,
      reportes e IVA. Quién las ve depende de la decisión del rol contador.

      **Verificación:** punta a punta: activar, vender, abrir el asiento desde
      la venta, cerrar el mes con el resumen a la vista.

      **Hecho.** Siete pantallas y el CSV, que lo arma el POS.

- [x] **T-1112** Simulado y catálogos: doce endpoints con contrato idéntico, un
      libro en el seed, `messages/es/accounting.json` declarado, y los siete
      códigos en los cuatro lugares.

      **Verificación:** `npm test`; `npm run check` en 0/0.

      Avance del 2026-10-02: los 28 códigos nuevos ya están en `api_errors.py`,
      en `API_CODES` y en los tres `errors.json` —el campo y el motivo se
      traducen con variantes, no con una frase por combinación—. Falta el
      simulado: los endpoints, el seed y `payroll.json`.

      **Hecho.** El simulado tiene su propio libro (`mock/ledger.ts`).
      Al escribirlo aparecieron dos defectos suyos: ponía en la venta la
      hora del **cliente** —que es local, mientras el turno se sella en
      UTC, así que el arqueo del demo decía «0 ventas» siempre— y
      `db.settings = …` escribía en la copia que devuelve `getDb()`.

### Verificación — sin esto la fase no está terminada

- [x] **T-1113** Punta a punta en una compañía que la prueba da de alta:
      activar contabilidad, vender 3 × 1 450 en efectivo y ver el asiento que
      balancea, comprar a crédito, abonar, cerrar caja con faltante, cerrar el
      mes, intentar un asiento en el mes cerrado → código; el D-104 del mes
      cuadra con los dos reportes.

      **Verificación:** Playwright contra el simulado y, a mano, contra el
      stack real; `pytest`, `npm test` y `npm run check` en verde.

      **Hecho.** 56 pruebas de punta a punta en verde. La del recorrido
      espera a que el pie de la tabla sume antes de llenar los saldos
      iniciales: lo tecleado antes de hidratar se borra al hidratar, y el
      formulario llegaba a medias con un «no cuadran» que engañaba.

---

## F12 · Planilla

> **Qué deja.** Nómina costarricense: empleados con los datos que piden la
> CCSS y el INS, puestos con sus dos códigos, jornadas mensuales, quincenales,
> bisemanales y semanales con sus cortes, **acciones de personal** que la
> corrida parte por el calendario, tasas con vigencia y país, corridas que
> **congelan** lo que usaron, renta del mes que cuadra, embargos y deducciones
> recurrentes con saldo, vacaciones, aguinaldo, liquidación, boleta, los
> archivos para la CCSS y el INS, el resumen de renta retenida, la importación
> desde Excel de quien viene de otro sistema y el asiento de la corrida
> (RN-66 a RN-75, RN-90 a RN-97, RF-55 a RF-64, RF-82 a RF-86). Plan §14.
>
> **De qué depende.** De F11 **solo para el asiento** (T-1206 con el `Ledger`);
> todo lo demás no. De **T-922**, en Transversal: la boleta es la cuarta
> plantilla de documento y hoy el PDF del backend no se cuenta.
>
> **Lo que no se supone.** Las cifras de la CCSS, los tramos de renta, el
> salario mínimo y los formatos del SICERE y de RT-Virtual **se leen de la
> fuente el día que se usan** (plan §14.8), no de este documento, ni del ERP de
> origen, ni del recuerdo de nadie.
>
> **Ampliada el 2026-09-27** con lo que el ERP de origen tiene y el primer
> diseño no: acciones de personal en lugar de novedades por corrida, jornadas
> con cortes, puestos, el archivo del INS, embargos, renta liquidada al cierre
> del mes y la importación. Lo que se dejó para después está en spec §4.

**Costes medidos antes de empezar** —plan §14.7—:

- `test_esquema.py`: quince tablas (`019`).
- `test_tenancy.py`: cuatro tablas globales **sin** `TenantMixin`, declaradas
  como excepción explícita como `cabys_cache`, o el guardián tumba `pytest`.
- `test_aislamiento.py`: unas treinta rutas y una bajo `/support`.
  `test_error_codes.py`: diecisiete códigos. `company_dump.py`: once viajan,
  cuatro no.
- El dominio de planilla supera a `ledger.py`; las pruebas usan un juego de
  tasas **inventado**, para probar la aritmética y no una cifra que vence.
- La boleta como cuarta plantilla, en los tres idiomas del documento.

### Base de datos

- [x] **T-1201** Migración `019-planilla.sql` (plan §14.2) y sus modelos: las
      cuatro tablas globales por país y las once de la compañía;
      `test_tenancy.py` con las excepciones; `company_dump.py` con la
      clasificación. RN-67, RN-72, RN-90, RN-94, RN-95, RN-97.

      **Verificación:** `test_esquema.py`; una consulta a `payroll_rates` sin
      compañía en la sesión funciona y una a `employees` falla cerrado;
      exportar y restaurar una compañía con corridas y acciones cuenta lo
      mismo; la migración corre contra el MySQL de pruebas.

      Avance del 2026-09-27: la migración y `model_payroll.py` dicen lo mismo
      (`test_esquema.py`), la 019 corrió dos veces contra el MySQL de pruebas
      sin error, `test_tenancy.py` lee `payroll_rates` sin compañía y falla
      cerrado en `employees`, y `company_dump.py` clasifica las quince. **Falta
      la ida y vuelta con datos**: no hay todavía ruta que cree un empleado ni
      una corrida, así que se cierra con T-1205 y T-1206.

      **Cerrada el 2026-10-02.** `test_respaldo_compania.py` exporta, borra y
      restaura una compañía con jornada, puesto, póliza, empleado, contrato,
      una acción y una corrida pagada con sus rubros, y el retrato por la API
      —las once tablas— es idéntico antes y después. La compañía de esa prueba
      pasó a ser **propia de cada corrida**: la «3» fija nacía con el plan de
      su primera corrida, sin planilla, y no había forma de darle el módulo
      después.

### Dominio

- [x] **T-1202** Sueldos y calendario: `rates_at`, `period_for` (cortes de las
      cuatro periodicidades, `InvalidCutDate`), `monthly_equivalent`,
      `day_value`, `hour_value`, `employee_deductions`, `employer_charges`,
      `income_tax` e `income_tax_withholding` (la última del mes liquida).
      RN-66, RN-67, RN-73, RN-94.

      **Verificación:** la tabla de casos de plan §14.3 con tasas inventadas;
      `rates_at` a una fecha sin `ivm` lanza `RatesMissing`; la quincena de
      600 000 es 300 000; una quincenal que corta el 14 da 15–29 y, en
      febrero, 15–28; dos quincenas con extras solo en la segunda retienen en
      el mes exactamente el impuesto del mes; cobertura 100 %.

      Hecha el 2026-09-27: `payroll_calendar.py` y `payroll.py`. Lo que vale un
      día salió del decreto de salarios mínimos (art. 7), no del ERP de
      origen, que lo tiene al revés. `projected_monthly` es la misma cuenta que
      `monthly_equivalent` y no existe aparte. El bruto no es una función: es
      la suma de los rubros, y la arma la corrida (T-1206).

- [x] **T-1216** Acciones: `portions`, `action_items` (los dieciséis
      tipos), `remaining_balance`, `garnishment_amount` y `apply_deductions`.
      RN-90, RN-92, RN-93, RN-94.

      **Verificación:** una incapacidad del 10 al 20 en quincenas → 6 días en
      la primera y 5 en la segunda, con sus fechas; una ausencia de 20 días en
      una quincena no rebaja más que la quincena; el subsidio de incapacidad
      no lleva cargas ni renta; un embargo entre una y tres veces el mínimo
      toma un octavo del exceso y nunca más que el saldo; con deducciones que
      no caben, el neto queda en cero y la última queda sin aplicar;
      cobertura 100 %.

      Hecha el 2026-09-27: `payroll_actions.py`. El tramo se llama `portions` y
      no `split_action` porque devuelve uno por cada periodo que la acción
      cruza, también los ya pagados (RN-91). La incapacidad que prolonga otra
      no le vuelve a cobrar al patrono sus primeros días. Qué rubros cotizan y
      cuáles pagan renta (`CONTRIBUTORY`, `TAXABLE`) se contrasta con el
      reglamento de la CCSS en T-1204, igual que las cifras.

- [x] **T-1203** Aguinaldo, vacaciones y liquidación: `aguinaldo` (con los
      saldos de apertura), `vacation_accrual`, `proportional_vacation`,
      `notice_days`, `severance_days`, `average_salary`, `settlement`. RN-69,
      RN-70, RN-71, RN-97.

      **Verificación:** doce meses de 500 000 → aguinaldo 500 000 sin rubros
      de CCSS ni renta; cinco meses de apertura y siete pagados suman igual
      que doce pagados; 12 años de antigüedad → los días de 8; renuncia → sin
      preaviso ni cesantía y con proporcionales; 350 días trabajados → 12 días
      hábiles de vacaciones en semana de seis, 10 en semana de cinco.

      Hecha el 2026-09-27: `payroll_benefits.py`. Las vacaciones son **días
      hábiles** —dos semanas son doce o diez, art. 153— y no los catorce que
      decía el primer plan; por eso la jornada ganó `workdays_per_week`. Al
      salir antes de las cincuenta semanas, al menos un día por mes. La
      antigüedad se cuenta por meses completos: con días entre 365, dos años
      que cruzan un bisiesto cobraban un pedazo de día de más. El reparto de
      la incapacidad (`sick_leave_split`) quedó dentro de `action_items`.

### Backend

- [x] **T-1204** Siembra de tasas por país: `seed_payroll_rates.py` con fuente,
      `valid_from` y `verified_at`, **leyendo las cifras de la fuente el día
      de correrlo** —cargas, tramos, créditos, cesantía, incapacidades,
      maternidad y salario mínimo inembargable—; `GET /payroll/rates?on=`;
      `PUT /support/payroll/rates`, que inserta una fila con vigencia y nunca
      edita la vigente. RF-56, RN-67, RN-93.

      **Verificación:** la prueba de la siembra suma los rubros obreros y
      patronales y los compara con los totales publicados ese día, que guarda
      con su fecha; intentar cambiar una fila vigente → rechazado; con
      `verified_at` de más de seis meses, `GET` lo marca y la pantalla avisa.

      Hecha el 2026-09-27. Los datos viven en
      `app/infrastructure/payroll_rates_cr.py`, cada fila con su norma, y la API
      los siembra al arrancar —solo lo que falta—; el guion queda para verlo a
      mano. Suman 10,83 % y 26,83 %, lo publicado para 2026
      (`test_siembra_planilla.py`). Lo que salió de leer las fuentes y cambió el
      dominio:

      - Hay **diez** cargas patronales y no ocho: el Banco Popular cobra dos
        veces y la LPT suma un 1 % al INS.
      - El **INA** no lo paga el patrono no agrícola con menos de cinco
        trabajadores: `employer_charges(…, exempt=…)`; la casilla va en
        T-1217.
      - Lo que se paga durante una **incapacidad es subsidio**: sin cargas ni
        renta, también los tres días del patrono (MTSS, DAJ-AE-201-12). La
        **maternidad** cotiza sobre el salario entero (art. 95).
      - El INS paga su incapacidad desde el día del riesgo: el patrono, nada.
      - La **cesantía** cuenta como año la fracción de más de seis meses.
      - El **embargo** es un tope por salario que se reparten todos, y la
        pensión alimentaria llega a la mitad (art. 172).
      - El simulado lee `payrollRates.ts`, generado de los mismos datos por
        `generar_tasas_simulado.py`; la prueba falla si quedó viejo.

      **Pendiente de decidir con el usuario:** la base mínima contributiva
      (SEM ₡346 789, IVM ₡324 590) está sembrada pero no se aplica. Con un
      salario menor —tiempo parcial— la CCSS cobra sobre la base mínima y la
      boleta, sobre el salario real, así que no coinciden.

      **Y dos más, aparecidas al cerrar la fase (2026-10-02):** las vacaciones
      que se pagan en la liquidación salen hoy sin cargas ni renta, como el
      preaviso y la cesantía, y la CCSS las considera salario; y el aguinaldo
      cuenta de la maternidad lo que pagó el patrono (la mitad), cuando el art.
      95 podría pedir el salario entero. Las dos están aisladas en
      `EARNED_CONCEPTS` y en `settlement`, y se cambian en un sitio.

- [x] **T-1221** Tramos y créditos de renta del año siguiente por el panel.
      Hoy entran con la siembra, y el decreto sale cada diciembre: soporte
      tendría que poder cargar el juego nuevo con su `valid_from` sin esperar
      un despliegue. RF-56, RN-67.

      **Verificación:** un juego de tramos con `valid_from` del 1 de enero
      siguiente; `GET /payroll/rates?on=` antes y después de esa fecha devuelve
      cada uno; un juego con huecos o que no empieza en cero se rechaza.

      **Hecha el 2026-10-02.** `PUT /support/payroll/brackets` recibe el juego
      **entero** —tramos, crédito por hijo y por cónyuge— con una sola
      vigencia: el decreto lo publica así y `GET /payroll/rates?on=` devuelve
      el juego más reciente que rige, así que medio juego nuevo taparía la
      mitad del viejo. `check_tax_brackets` exige que empiece en cero, sin
      huecos ni solapes y con el último tramo sin techo (`invalid_tax_brackets`,
      con el tramo señalado); un juego no se edita (`payroll_rate_not_newer`
      con el concepto `income_tax_brackets`). Queda en bitácora como
      `tramos_renta`. La prueba calcula el 1 de enero siguiente al juego más
      nuevo que haya, porque la base sobrevive entre corridas.

- [x] **T-1217** Configuración de planilla: datos patronales en `settings`
      con validación del backend, jornadas (`schedule_locked` si tiene
      corridas pagadas), puestos con sus dos códigos y pólizas del INS con su
      prima. RF-56, RF-83, RF-84, RN-94, RN-95.

      **Verificación:** `test_aislamiento.py`; cambiar la periodicidad de una
      jornada con una corrida pagada → código; un puesto sin código de la
      CCSS → rechazado; la póliza por omisión es una sola.

      **Hecha el 2026-10-02.** Los datos patronales viven en la sección
      `payroll` de `settings.data` con su propia puerta (`PUT
      /payroll/settings`): el número patronal se valida en
      `domain/payroll_staff.py` (dígitos y guiones, de 9 a 25) y el INA exento
      es una casilla. Jornadas, puestos y pólizas son el ABM de `crud_payroll`
      con las reglas del dominio; el nombre repetido responde
      `payroll_name_taken` con el recurso; una jornada con corridas pagadas no
      cambia de periodicidad ni de cortes (`schedule_locked`), pero sí de
      nombre; la primera póliza queda por omisión y marcar otra la reemplaza.

      **Apareció un defecto de F11 de camino**: la pantalla de Configuración
      manda solo sus seis secciones y `save_settings` reemplazaba el JSON
      entero, así que guardar la moneda **desactivaba la contabilidad** sin un
      solo error. `OWNED_SECTIONS` conserva ahora las secciones que escribe el
      backend (`accounting`, `payroll`) y las ignora si vienen en la petición;
      la regresión está en `test_contabilidad.py` y en `test_planilla.py`.

- [x] **T-1205** Empleados y contratos: rutas con los datos de RN-72, enlace
      opcional a `users`, contrato con jornada, puesto y póliza, baja con
      fecha y causa (`employee_terminated`) que registra la acción
      `termination`, y un aumento que cierra el contrato y abre otro. RF-55,
      RN-72.

      **Verificación:** `test_aislamiento.py`; dar de baja crea la corrida de
      liquidación en borrador y la acción en el historial; una acción para un
      empleado dado de baja después de su fecha responde el código.

      **Hecha el 2026-10-02.** `check_employee` revisa la forma de lo que
      piden los archivos —tipo y número de identificación, apellidos, fecha de
      nacimiento (quince años al ingresar), género, estado civil,
      nacionalidad, IBAN— y los códigos dicen el campo y el motivo. El contrato
      nuevo cierra el anterior el día antes y tiene que empezar después de él
      (`invalid_contract` / `overlaps`); la baja es `TerminateEmployee`: cierra
      el contrato, registra la acción `termination` con origen `system` y deja
      la liquidación **vacía y en borrador**, que T-1210 calcula.

- [x] **T-1218** Acciones de personal: `RegisterAction`, `CancelAction`,
      `SuspendAction`, el historial por empleado con lo que aplicó cada
      corrida y el saldo. `action_not_editable`, `action_already_cancelled`,
      `action_not_recurring`. RF-82, RN-90 a RN-92.

      **Verificación:** editar una acción aplicada en una pagada → código;
      anularla deja una acción con `cancels_action_id` que la corrida
      siguiente aplica al revés; suspender una recurrente deja quién, cuándo
      y motivo, y la corrida siguiente ya no la toma; el saldo es la suma de
      rubros, no una columna.

      **Hecha el 2026-10-02.** Cuatro casos de uso —`RegisterAction`,
      `UpdateAction`, `CancelAction`, `SuspendAction`— y el historial con lo que
      aplicó cada corrida y el saldo. El aumento y el cambio de puesto se
      aplican **al registrarse**: cierran el contrato vigente y abren otro, y
      por eso no se editan ni se anulan (`action_not_editable` / `contract`).
      Anular es siempre otra acción con `cancels_action_id`, también si la
      original no entró en ninguna corrida: así el historial dice que existió.
      «Aplicado» cuenta corridas **aprobadas y pagadas**, y no solo pagadas
      como dice RN-92 del saldo: una aprobada no se recalcula, y contarla evita
      que la siguiente vuelva a aplicar lo mismo mientras la anterior espera el
      pago.

- [x] **T-1206** Corridas: `CreateRun` para una jornada y un corte
      (`invalid_cut_date`), `CalculateRun` que toma las acciones del periodo
      y las pendientes de periodos pagados y escribe líneas y rubros —el
      congelamiento—, `ApproveRun`, `PayRun` con fecha del servidor, bitácora
      y `Ledger.post` si contabilidad está activa. RF-57, RN-66, RN-68, RN-73,
      RN-75, RN-91, RN-93.

      **Verificación:** pagar; insertar una tasa nueva con `valid_from` de
      ayer; `GET` de la corrida pagada → los rubros **no** cambian; una corrida
      nueva → sí; editar la pagada → `run_already_paid`; una incapacidad
      registrada después de pagar su quincena entra en la siguiente con sus
      fechas; con contabilidad activa, `journal_entry_id` apunta a un asiento
      que balancea entre 6.1.01, 6.1.02, 2.1.03, 2.1.04, 2.1.05 y 2.1.06.

      **Hecha el 2026-10-02.** `CreateRun`, `CalculateRun`, `ApproveRun` y
      `PayRun`, con `Ledger.record_payroll` —el único `record_*` que devuelve
      algo: el id del asiento, que la corrida guarda— y `post_payroll` en el
      dominio del libro (la renta devuelta cambia de lado en vez de romper el
      asiento). Lo que decidió el cálculo y no estaba escrito:

      - El salario base se prorratea por los días que cuenta el tramo —en mes
        comercial— cuando el contrato o el empleo no cubren el periodo entero
        (`base_item`); entero, sale tal cual, sin pasar por el valor del día.
      - Una anulación revierte en la corrida siguiente los rubros que la
        original dejó en corridas aprobadas o pagadas, copiados al revés y con
        sus fechas; si no dejó ninguno, un rubro de cero dice que se recogió.
      - El solidarista del contrato es una deducción «otra», como la pensión y
        el embargo; la prima de riesgos es cero si la compañía no tiene póliza.
      - Solo las corridas regulares se calculan acá; el aguinaldo, la
        liquidación y el ajuste responden `run_not_editable` hasta T-1208,
        T-1210 y T-1212. Y la corrida pagada **todavía no acumula vacaciones**:
        es T-1209.

      Verificado contra el stack: la corrida pagada no cambia con una tasa
      nueva de ayer y la siguiente sí la trae; la incapacidad registrada
      después de pagar entra en la siguiente con sus dos tramos; el asiento
      balancea entre las seis cuentas; `planilla_pagada` en la bitácora; y las
      diecisiete rutas por id responden 404 con el token de otra compañía.

- [x] **T-1207** Boleta: la cuarta plantilla de documento, en el idioma del
      documento (RN-29), armada **desde los rubros congelados**, con cada
      acción aplicada y sus fechas. RF-58, RN-66.

      **Verificación:** la boleta de una corrida pagada antes de un cambio de
      tasa muestra la tasa vieja; T-922 cuenta cuatro documentos.

      **Hecha el 2026-10-02.** `GET /payroll/runs/{id}/payslips/{employee}`
      devuelve los rubros congelados con el nombre del puesto, la jornada y de
      qué acción salió cada uno; `Boleta.svelte` los imprime con
      `payslipLabels(docLocale)` —los rótulos y los nombres de los rubros en
      `documents.json`, en los tres idiomas— y `loose-text.test.ts` la cuida
      como a las otras tres. La prueba HTTP compara la boleta con los rubros de
      la corrida pagada después de insertar una tasa nueva.

- [x] **T-1208** Aguinaldo como corrida `aguinaldo`: suma lo devengado de las
      pagadas del 1 de diciembre al 30 de noviembre y los saldos de apertura
      del mismo periodo, y divide entre doce, sin rubros de CCSS ni renta.
      RF-59, RN-69, RN-97.

      **Verificación:** doce corridas de 500 000 → 500 000 exacto; los rubros
      de la línea son todos `earning`.

      **Hecha el 2026-10-02.** `CreateAguinaldoRun(year)` (`POST
      /payroll/runs/aguinaldo`, una por año, pago el 20 de diciembre si no se
      dice otra fecha) y `aguinaldo_lines` en `use_cases/payroll_special.py`:
      suma `paid_earnings` de las regulares y ajustes pagados más los meses de
      apertura; quien salió antes del corte no entra (su proporcional fue en la
      liquidación) y quien no devengó nada tampoco. Lo que cuenta como salario
      es `EARNED_CONCEPTS` (lo que paga renta: sin subsidios).

- [x] **T-1209** Vacaciones: acumulación al pagar cada corrida, disfrute como
      acción `vacation`, saldo de apertura, saldo por empleado
      (`vacation_balance_exceeded`). RF-60, RN-70.

      **Verificación:** 350 días trabajados → 12; disfrutar 20 → código; el
      saldo es la suma de `vacation_movements`, no una columna.

      **Hecha el 2026-10-02.** `PayRun` acumula por los días de calendario que
      cubrió el salario base de cada línea (una quincena de quince días da 0,51
      hábiles) y, en una liquidación, deja pagados los días que liquidó;
      `RegisterAction` revisa el saldo antes de aceptar un disfrute y deja el
      movimiento `taken` con la acción; corregirla lo corrige y anularla lo
      devuelve con un movimiento negativo. `GET /payroll/vacations/{employee}`
      da el saldo —la suma, `vacation_balance`— y los movimientos. La
      acumulación no descuenta los días de permiso sin goce: anotado.

- [x] **T-1210** Liquidación: `TerminateEmployee` deja una corrida `settlement`
      con preaviso, cesantía, vacaciones y aguinaldo proporcionales según la
      causa, sobre el promedio de los últimos seis meses;
      `settlement_requires_termination`. RF-61, RN-71.

      **Verificación:** los tres casos de `settlement` (renuncia, despido sin
      causa, con causa) dan los rubros que dice la tabla; con dos meses de
      apertura el promedio los cuenta; sin baja → código.

      **Hecha el 2026-10-02.** La liquidación nace con **una línea vacía** que
      dice de quién es (la corrida no tiene columna de empleado), y
      `settlement_lines` la llena: el promedio de los seis meses calendario
      **anteriores** al de la salida —pagados o de apertura, o el salario del
      contrato si no hay ninguno—, las vacaciones del saldo con el piso de un
      día por mes para quien no llegó a las cincuenta semanas, el aguinaldo
      desde el 1 de diciembre, y preaviso y cesantía solo en el despido sin
      causa con la tabla de `severance_table` (`RatesMissing` si no hay). La
      tabla de cesantía entra por `RateTable.severance_at`. Conviene calcularla
      después de pagar la última corrida regular: la acumulación de vacaciones
      de esos días llega con ese pago.

- [x] **T-1211** Archivo para la CCSS y resumen de renta retenida. **Empieza
      por leer la especificación oficial del SICERE** y guardarla en
      `docs/ccss/`, como los XSD en `docs/hacienda/`; el archivo sale de un
      adaptador `CcssFileWriter` con prueba contra un ejemplo real, con los
      movimientos que salen de las acciones —ingreso, incapacidades,
      permisos, cambio de ocupación, exclusión—. `export_data_incomplete`
      lista a quién le falta qué. RF-62, RN-96.

      **Verificación:** el archivo del mes valida contra el ejemplo del
      material; una incapacidad que cruzó dos quincenas sale con sus fechas;
      la renta retenida del mes es la suma de los rubros `income_tax` de las
      corridas pagadas del mes.

      **Hecha el 2026-10-02, con un cambio de forma que hay que saber.** La
      CCSS **no publica** la estructura del archivo de texto: la carga por
      archivo es de «grandes clientes» (unos mil patronos) y su trazado no
      está en ccss.sa.cr ni en ningún documento abierto; el 98 % de los
      patronos presenta la planilla por el formulario de Autogestión. Lo que
      sí hay es la guía oficial de ese formulario (GF-DSCR-F004) y el
      formulario de ajuste (GF-DSCR-F071), guardados en `docs/ccss/` con un
      README que lo explica. Como el formato no se supone (plan §14.8), `GET
      /payroll/exports/ccss` entrega **el informe del mes con exactamente lo
      que el formulario pide** —identificación como la pide la Caja,
      ocupación, jornada, salario que cotiza, días y cada movimiento con sus
      fechas, juntando los tramos de una misma incapacidad— y la pantalla lo
      muestra y lo baja en CSV. La renta retenida es `GET
      /payroll/exports/income-tax`. `export_data_incomplete` lista empleados
      y campos, y los de la compañía. El archivo de texto queda como
      **T-1222**.

- [x] **T-1219** Archivo para el INS, uno por póliza. **Empieza por leer la
      especificación oficial de RT-Virtual** y guardarla en `docs/ins/`;
      adaptador `InsFileWriter` con prueba contra un ejemplo real. RF-85,
      RN-96.

      **Verificación:** el archivo valida contra el ejemplo; un empleado que
      ingresó y salió en el mes lleva esa condición; dos pólizas → dos
      archivos que suman la planilla del mes.

      **Hecha el 2026-10-02, con una salvedad.** El INS publica la estructura
      **dentro** de RT-Virtual, con la sesión de la póliza; lo que hay afuera
      es el generador público que reproduce su plantilla (`RTVirtual.html`,
      versión **V08D**: tres líneas de encabezado y un registro de 114
      posiciones por trabajador) y la charla oficial del INS con las reglas de
      identificación. El trazado está en `docs/ins/README.md` con su
      procedencia, `domain/payroll_files.py` lo escribe (`ins_file`, en
      ISO-8859-1, con el nombre `PL<póliza>M<año><mes>-V08D (Texto).txt`) y
      `GET /payroll/exports/ins?policy=` lo entrega. **Falta cotejarlo con el
      documento del INS**: T-1223.

- [x] **T-1212** Corrida de ajuste sobre una pagada, que la referencia y no la
      toca. RF-63, RN-68.

      **Verificación:** el ajuste tiene `adjusts_run_id`; la boleta de la
      original no cambia; el asiento del ajuste es solo la diferencia.

      **Hecha el 2026-10-02.** `AdjustRun` (`POST /payroll/runs/{id}/adjust`,
      solo sobre una regular pagada: `run_not_paid`) abre una corrida
      `adjustment` con el mismo periodo; calcularla vuelve a correr el cálculo
      regular **valorando los mismos tramos de acciones que la pagada aplicó**
      con los datos de hoy —salario, prima, tasas—, copia las cuotas y las
      anulaciones tal cual, y escribe la diferencia rubro por rubro
      (`difference_lines`): quien no estaba entra entero, quien no debía estar
      sale en negativo. La renta se proyecta como la pagada si el mes sigue
      abierto y se liquida contra el mes si ya cerró. Las retenciones del mes
      cuentan ahora regulares **y ajustes**.

- [x] **T-1220** Importación: `ImportPayroll` con `dry_run` —puestos,
      empleados con contrato, vacaciones y devengado de apertura, deducciones
      recurrentes con su saldo— en una transacción, y la plantilla
      descargable. `import_has_errors`. RF-86, RN-97.

      **Verificación:** un archivo con una fila mala → el ensayo la señala
      con su código y no escribe nada; corregido → entra entero; una cédula
      repetida o un puesto que no existe no entra; los saldos quedan con
      `source = 'import'` y su fecha.

      **Hecha el 2026-10-02.** `POST /payroll/import?dry_run=` recibe cuatro
      listas ya leídas —puestos, empleados con su contrato por **nombre** de
      jornada, puesto y póliza, devengado por mes y deducciones con su saldo—
      y `ImportPayroll` las revisa con las mismas reglas del formulario
      (`check_position`, `check_employee`, `check_contract`, `check_action`),
      responde fila por fila con el mismo código y, sin ensayo, escribe todo
      o nada (`import_has_errors`). Un puesto que ya existe se reutiliza; una
      cédula que ya está no entra; el saldo de una deducción entra como lo
      pactado que falta por cobrar. El POS lee una hoja por archivo (`.xlsx` o
      `.csv`, encabezados por sinónimo, valores en español o del API) en
      `$lib/server/import/payroll.ts`, con una plantilla CSV por hoja.

### Frontend

- [x] **T-1213** Pantallas de `/planilla` (plan §14.4): resumen con lo que
      vence y los datos que faltan para los archivos, empleados, acciones,
      corridas, vacaciones, configuración (datos patronales, jornadas, puestos
      y pólizas), importar con vista previa y tasas. RF-55 a RF-63, RF-82 a
      RF-86.

      **Verificación:** punta a punta: configurar una jornada y un puesto,
      alta de empleado, contrato, una acción de 4 horas extra, calcular,
      aprobar, pagar, imprimir la boleta; importar un Excel con una fila
      mala, corregirla y confirmar.

      **Hecha el 2026-10-02.** Nueve pestañas bajo `/planilla` —resumen,
      empleados (lista y ficha con contrato, historial, vacaciones y baja),
      acciones (para uno o varios empleados, con anular y suspender),
      corridas (lista, detalle con rubros, boleta y lista de IBAN para la
      transferencia), vacaciones, **archivos del mes** (la novena, que el plan
      no listaba: el informe de la CCSS, la renta y el archivo del INS por
      póliza), configuración, importar y tasas— con `payroll.json` en los
      tres idiomas y la entrada «Planilla» en el menú con su candado de
      módulo. Leer no exige el módulo; escribir sí, en cada acción. La
      importación por Excel con una fila mala está en la prueba HTTP; la de
      punta a punta la deja para cuando Playwright suba archivos (T-1215).

- [x] **T-1214** Simulado y catálogos: unos treinta endpoints con contrato
      idéntico, dos empleados, dos jornadas, dos puestos, una póliza y un
      juego de tasas en el seed, `messages/es/payroll.json` declarado, y los
      quince códigos en los cuatro lugares (los dos de las tasas ya están, T-1204).

      **Verificación:** `npm test`; `npm run check` en 0/0.

      **Hecha el 2026-10-02.** `mock/payroll.ts` (las treinta y cuatro rutas
      de `/payroll/*`, mismos códigos y mismos estados) y `mock/payrollCalc.ts`
      (los cortes de las cuatro periodicidades, lo que vale un día, las cargas,
      la renta del mes, el trazado V08D): una versión compacta del dominio,
      para que las pantallas y Playwright tengan cifras con la misma forma; la
      aritmética al céntimo es la del backend. La compañía de demostración trae
      dos jornadas, dos puestos, una póliza y dos empleados con contrato
      (`SEED_VERSION` 17). Los treinta y tres códigos de F12 están en los
      cuatro lugares.

### Verificación — sin esto la fase no está terminada

- [x] **T-1215** Punta a punta en una compañía que la prueba da de alta: dos
      empleados (mensual y quincenal), una incapacidad que cruza la quincena,
      un préstamo recurrente, una corrida pagada; una tasa nueva con vigencia
      futura; reimprimir → igual; la corrida siguiente → distinta y con el
      saldo del préstamo bajando; aguinaldo; baja con liquidación; archivos de
      la CCSS y del INS; y con contabilidad activa, el asiento.

      **Verificación:** Playwright contra el simulado y, a mano, contra el
      stack real; `pytest`, `npm test` y `npm run check` en verde.

      **Hecha el 2026-10-02.** `tests/e2e/planilla.spec.ts` recorre todo eso
      en el simulado, menos la tasa nueva con vigencia futura: la carga
      soporte por el API y no tiene pantalla, así que esa parte vive en
      `backend/tests/test_planilla.py` contra el stack real (la pagada no
      cambia, la siguiente sí). Lo que falta de la verificación: el recorrido
      **a mano** contra el stack de desarrollo, que es del usuario.

- [ ] **T-1222** El archivo de texto de la planilla para la CCSS («grandes
      clientes»), el día que la Dirección SICERE entregue su estructura
      (`plautogestion@ccss.sa.cr`): el escritor va en `domain/payroll_files.py`
      al lado del del INS, con la prueba contra el ejemplo que venga con la
      especificación. Los datos ya están (`ccss_report`). RF-62, RN-96.

      **Verificación:** el archivo del mes valida contra el ejemplo oficial.

- [ ] **T-1223** Cotejar el trazado V08D del archivo del INS con «Estructura
      del archivo» de RT-Virtual (requiere la sesión de la póliza) y, si
      difiere, corregir `ins_record`/`ins_header` y su prueba. Hasta entonces,
      un rechazo del INS se corrige acá y no en la planilla. RF-85.

      **Verificación:** RT-Virtual acepta el archivo de un mes real.

- [ ] **T-1224** Acortar el arranque del POS. La compilación de Paraglide tarda
      tres minutos con los 2 250 mensajes de hoy (dos antes de F12, y crece
      más que proporcional) y la pagan `npm run dev`, `npm test` y `npm run
      check` cada vez. No es la máquina ni los catálogos: el hilo principal de
      Node está ocioso el 95 % y el trabajo lo hace la base SQLite del SDK de
      inlang; subir a 2.25.4 (SDK 3.0.6) tarda lo mismo. **Decidir con el
      usuario:** abrir el caso arriba, quitar el plugin de Vite y compilar solo
      con `npm run i18n` (se pierde la recompilación automática al editar un
      catálogo), o aceptar el costo. Mientras tanto el `webServer` de
      Playwright espera diez minutos en vez de dos.

      **Verificación:** `npm run dev` dice «ready» en menos de treinta segundos
      con los catálogos de hoy.

- [x] **T-1225** El alta del empleado con su contrato (RF-55). La ficha de
      alta lo creaba sin contrato y el contrato iba después, desde el detalle,
      así que cada alta pasaba por la lista como «Sin contrato» hasta que
      alguien se acordaba. `POST /payroll/employees` acepta `contract`
      (jornada, puesto, póliza, salario del periodo, aporte solidarista) y
      guarda los dos en la misma transacción, rigiendo desde la fecha de
      ingreso; la ficha del POS trae la sección con la casilla «Asignarle el
      contrato ahora», marcada si hay jornada y puesto activos. Los contratos
      que siguen —un aumento, otro puesto— van por la ficha, como antes.

      **Verificación:** `test_planilla.py::TestElAltaConSuContrato` (entra
      con su contrato desde el ingreso; si el contrato no pasa, el empleado
      tampoco queda y la cédula sigue libre); `planilla.spec.ts` da de alta a
      una persona con el contrato en la ficha y a otra sin él, que se contrata
      desde el detalle.

      **Hecha el 2026-10-03.** El contrato **no tiene número**: el usuario lo
      pidió como «el número de contrato», y ni el spec ni el modelo lo traen.
      Se le consultó si hace falta uno propio. La acción del alta avisa ahora
      el primer error de validación (`message`): antes un dato mal escrito no
      decía nada.

---

## F13 · Proveedores — alcance decidido el 2026-10-03; va segunda (F15 → F13 → F14)

> El módulo `suppliers` de QA-01 (el paquete Comercio lo trae sin compras),
> analizado contra la KB del ERP (`KbSws20_actualizado.xpz`, prefijo `Pro`:
> 9 transacciones, 110 procedimientos y 24 pantallas, más `BanPago` en Bancos).
> Hoy un proveedor es casi solo una agenda: nombre, identificación, contacto,
> plazo y si está activo. En la KB es la mitad de las cuentas por pagar.

**Lo que trae la KB.**

- **La ficha** (`ProProveedor`): tipo e identificación —validada por tipo, y
  con la consulta al padrón al crear—, nombre, **clase** (servicios,
  mercancías, tráfico), **tipo de proveedor** (un catálogo de la compañía),
  ubicación de Hacienda o señas del extranjero con el tipo `05`, país,
  teléfonos, correo (y si rebota), **plazo y moneda**, saldo, inactivo, si se le
  manda el XML, y dos marcas fiscales: **no emisor de factura electrónica** y
  **gasto menor**. Cada activar, desactivar y cambio de esas marcas queda en
  bitácora.
- **Lo que se le compra** (`ProProveedorConcepto`): conceptos por proveedor con
  su CABYS, su tarifa y si dan crédito fiscal, sacados de **tipos de concepto**
  (`ProConceptoTipo`: adelanto, no declarable, retención de renta o de IVA; los
  tipos 1 a 9 reservados —1 compras, 2 seguro, 3 flete, 4 envío y manejo—).
- **Contactos** (nombre, puesto, teléfono, extensión, correo) y **cuentas
  bancarias** (`ProCuenta`: número, SINPE, IBAN, banco, moneda).
- **El documento del proveedor** (`ProDocumento`): factura, nota de crédito o
  de débito **por concepto**, que es la cuenta por pagar de lo que no es
  inventario —servicios y gastos—, con plazo, vencimiento, moneda, tipo de
  cambio y crédito o gasto del IVA. Reglas: la nota de crédito va en negativo y
  la factura en positivo, nada en cero, nada a un proveedor inactivo, y un
  concepto sin CABYS no pasa si el proveedor no emite.
- **Aplicaciones** (`ProAplicacion`): una nota de crédito o un adelanto
  aplicados a facturas, sin pasarse del saldo y nunca con fecha posterior.
- **Pagos** (`BanPago`): uno solo paga **varias facturas** de un proveedor, o es
  un **adelanto** —no las dos cosas—, sin pasarse del saldo; y la
  **liquidación** (`ProLiquidacion`) paga en lote lo que vence, hasta un límite.
- **El buzón de comprobantes recibidos** (`XMLProveedores`): el XML que manda
  el proveedor, el **mensaje de receptor** a Hacienda (aceptar, aceptar
  parcial, rechazar) con la condición del impuesto, y el documento que generó.
- Consultas: estado de cuenta, antigüedad de saldos, pendientes, por línea,
  facturas recibidas y saldos.

**Lo que ya tenemos (F10).** Proveedores con tipo e identificación (`01` a
`06`), nombre, correo, teléfono, plazo y activo; la compra de mercadería como
entrada con proveedor (también leída del XML del proveedor); un abono por
compra, en efectivo o por transferencia, que sale de la caja; cuentas por
pagar con antigüedad; la FEC para el no contribuyente.

**Lo que falta, por valor para un comercio.**

1. Una ficha más completa: tipo de proveedor, clase (servicios o mercancías),
   moneda, ubicación de Hacienda, contactos, cuentas bancarias, la marca «no
   emite factura electrónica» —hoy se deduce del tipo `06`— y la bitácora de
   activar y desactivar.
2. **Los gastos y servicios**: el documento del proveedor por concepto, con su
   CABYS y su crédito fiscal, sin tocar inventario (alquiler, luz, fletes). Hoy
   solo se compra mercadería, así que el IVA de los gastos no llega al reporte.
3. Notas de crédito y de débito del proveedor, y aplicarlas a sus facturas.
4. Adelantos a proveedores y su aplicación.
5. Un pago a varias facturas a la vez.
6. El estado de cuenta del proveedor.
7. El buzón de comprobantes recibidos con su mensaje de receptor. Pide firmar y
   transmitir, como F7 pero con lo recibido; la investigación está en
   `docs/hacienda/costa-rica/recepcion-comprobantes-mensaje-receptor.md`.

**Lo que no conviene traer:** la clase «tráfico», las retenciones de El
Salvador y República Dominicana, caja chica, centros de costo, producción, la
consulta al padrón (es un servicio aparte) y las integraciones con otros
sistemas.

- [ ] **T-1301** Requisitos al spec y diseño al plan de lo que se decida de la
      lista, con el revisor de cada documento.

      **Verificación:** `spec-reviewer` y `plan-reviewer` sin observaciones.
- [ ] **T-1302** La ficha completa (punto 1): migración, dominio, rutas,
      simulado y pantalla.

      **Verificación:** activar y desactivar quedan en bitácora; un proveedor
      `05` pide señas del extranjero.
- [ ] **T-1303** Los gastos (punto 2): tipos de concepto, conceptos por
      proveedor y el documento del proveedor que no mueve inventario.

      **Verificación:** un gasto de ₡100 000 al 13 % aparece en cuentas por
      pagar y su IVA en el reporte por tarifa, sin tocar existencias.
- [ ] **T-1304** Notas del proveedor, adelantos y aplicaciones (puntos 3 y 4).

      **Verificación:** una nota de crédito aplicada baja el saldo de la
      factura y no puede pasarse de él.
- [ ] **T-1305** Un pago a varias facturas y el estado de cuenta (puntos 5 y 6).

      **Verificación:** el pago se reparte entre las facturas y el arqueo
      cuadra.
- [ ] **T-1306** El buzón de comprobantes recibidos con mensaje de receptor
      (punto 7). Depende de F7.

      **Verificación:** un XML recibido se acepta ante Hacienda en el sandbox y
      queda enlazado a su compra o su gasto.

**Decidido con el usuario el 2026-10-03:** entran los siete puntos, con el
buzón (punto 7) en esta misma fase. Los gastos y servicios son del módulo de
**proveedores**, no de compras: el paquete Comercio los registra sin tener
compras, que queda para la mercadería a crédito y la orden de compra. Las
fases van en el orden **F15 → F13 → F14**.

---

## F14 · Compras a fondo — alcance decidido el 2026-10-03; va tercera

> El módulo `purchases`, contra la KB (prefijo `Cpa`: 4 transacciones, 47
> procedimientos, 15 pantallas). F10 dejó la compra de mercadería como una
> entrada con proveedor, documento, condición de pago y crédito fiscal por
> línea, con costo promedio y anulación sin abonos. La KB la rodea de lo que
> pasa antes —el pedido— y de lo que cuesta además de la mercadería.

**Lo que trae la KB.**

- **La orden de compra** (`CpaOrden`): el pedido al proveedor, con bodega,
  moneda, descripción, instrucciones y condiciones; **aprobaciones**
  (`CpaConfigurador`: cuántas hacen falta y quiénes aprueban); al aprobarse se
  le **manda por correo** al proveedor; y después se **aplica a la compra**
  cuando llega la factura, con la cantidad disponible por línea.
- **La compra** (`CpaCompra`): solo a proveedores de clase mercancías y de
  productos inventariables; bodega y moneda con tipo de cambio; por línea el
  producto con su **unidad y factor**, **descuento**, costo unitario y total;
  y los **costos adicionales** —flete, seguro, envío y manejo, otros— que se
  **reparten al costo** de cada línea por su participación. Separa el IVA
  acreditable del que va al costo (**proporcionalidad**), no se borra si ya
  tiene pagos, y genera su cuenta por pagar y su asiento.
- **La importación** (`CpaImportacion`): nacionalizar lo comprado en el
  extranjero con su DUA, valor declarado y tipo de cambio, de un almacén
  fiscal a una bodega.
- Consultas: compras, compras detalladas, por proveedor, **estadística por
  producto**, **reabastecimiento** (lo que hay que pedir según mínimos y días
  de reposición), semestral por proveedor y órdenes.

**Lo que ya tenemos (F10).** La compra como entrada con proveedor, documento
(con su clave), fecha, condición contado o crédito, plazo y vencimiento;
líneas con costo e impuesto; crédito fiscal por línea; costo promedio;
anulación solo sin abonos; el documento duplicado se rechaza
(`duplicate_document`); y el XML del proveedor leído para llenarla.

**Lo que falta, por valor para un comercio.**

1. Los **costos adicionales** (flete, envío, seguro) repartidos al costo de
   las líneas: sin ellos el costo promedio queda bajo y el margen, inflado.
2. El **descuento por línea** de la factura del proveedor.
3. **Unidades de compra con factor**: comprar la caja de 12 y que entren 12
   unidades al precio de cada una.
4. **Moneda y tipo de cambio** de la compra, para el que compra en dólares.
5. La **orden de compra**: pedir, mandarla al proveedor y convertirla en
   compra al recibir, completa o en partes. Las aprobaciones, opcionales.
6. El **reabastecimiento**: qué pedir según el mínimo de cada producto y lo que
   se vende (depende del mínimo por producto de F15).
7. Reportes de compras por proveedor y por producto.
8. La **proporcionalidad del IVA**, para quien vende gravado y exento a la vez.
   Toca el crédito fiscal y la contabilidad: conviene confirmarla con un
   contador.

**Lo que no conviene traer:** importaciones con DUA y almacén fiscal (un
importador es otro tipo de cliente), y la clase de proveedor como candado (con
la ficha de F13 alcanza).

- [ ] **T-1401** Requisitos al spec y diseño al plan, con sus revisores.

      **Verificación:** `spec-reviewer` y `plan-reviewer` sin observaciones.
- [ ] **T-1402** Costos adicionales y descuento por línea (puntos 1 y 2).

      **Verificación:** una compra de ₡100 000 con ₡10 000 de flete deja el
      costo de cada línea con su parte del flete, y el costo promedio la
      refleja.
- [ ] **T-1403** Unidades con factor (punto 3). Toca la ficha del producto
      (F15).

      **Verificación:** 2 cajas de 12 entran como 24 unidades.
- [ ] **T-1404** Moneda y tipo de cambio de la compra (punto 4).

      **Verificación:** una compra en dólares queda en colones al tipo del día
      del documento, y su abono también.
- [ ] **T-1405** La orden de compra (punto 5).

      **Verificación:** una orden de 10 recibida en dos compras de 6 y 4 queda
      cerrada, y no se puede recibir más de lo pedido.
- [ ] **T-1406** Reabastecimiento y reportes (puntos 6 y 7).

      **Verificación:** un producto bajo su mínimo aparece con la cantidad
      sugerida.

- [ ] **T-1407** La proporcionalidad del IVA (punto 8). **Bloqueada:** se
      construye después de confirmar con un contador cómo se calcula para los
      clientes que venden gravado y exento.

      **Verificación:** a definir con el contador.

**Decidido con el usuario el 2026-10-03:** entran los puntos 1 a 7. La orden de
compra lleva **aprobación opcional por compañía** —cada una elige si la
necesita y cuántas; por omisión, ninguna—. La proporcionalidad espera al
contador (T-1407). F14 va tercera, después de F15 y F13: el reabastecimiento
necesita el mínimo por producto de F15.

---

## F15 · Inventario — alcance decidido el 2026-10-03; va primera

> Contra la KB (prefijo `Inv`: 17 transacciones, 143 procedimientos, 42
> pantallas, y la ficha `FaeProducto` de facturación). El nuestro está completo
> para un local con una sola existencia: productos con dos niveles de
> categoría, CABYS y tarifa, código de barras, unidad y costo promedio;
> entradas manuales, importadas y por compra, con anulación; la venta y la
> devolución mueven el stock. Lo que la KB tiene y nosotros no es **dónde** está
> la mercadería y **por qué** se movió.

**Lo que trae la KB.**

- **Bodegas** (`InvBodega`), con **existencias por bodega** (`InvExistencia`:
  cantidad, reservada, disponible, costo) y bodegas bloqueadas.
- **El kárdex** (`InvMovimiento`): cada movimiento con la existencia y el costo
  de antes y de después, el documento que lo causó y quién.
- **Entradas y salidas con motivo** (`InvEntrada`, `InvSalida`, `InvMotivo`:
  merma, daño, consumo interno…), y **traslados** entre bodegas.
- **La toma física** (`InvTomaFisica`): contar por bodega, marca, tipo o
  grupo, y aplicar las diferencias como ajuste.
- En la ficha del producto: **mínimo** y **días de reabastecimiento**,
  **marca**, códigos alternos, unidad con factor, código sanitario y su
  vencimiento; y por línea de movimiento, **lote y vencimiento**.
- Reservados (apartados), préstamos, consignación, requisición, alisto,
  empaque y despacho, y las tiendas en línea.
- Consultas: existencias, **bajo mínimo**, **rotación**, **valorado**, consumo,
  movimientos, saldos y resumen.

**Lo que falta, por valor para un comercio.**

1. **Salidas con motivo** —merma, daño, vencido, consumo interno—: hoy lo único
   que baja el stock es vender, así que una merma se arregla vendiendo de
   mentira o editando el número.
2. **El kárdex** por producto: sin él no hay cómo explicar por qué un producto
   tiene la existencia que tiene.
3. **La toma física**: contar y aplicar las diferencias como ajuste con motivo.
4. **El mínimo por producto** —hoy es uno solo para todos, de configuración—
   y el reporte de lo que está bajo mínimo.
5. **Existencias por sucursal**: ya hay sucursales y cajas (F6), pero el stock
   es uno solo por producto. Una cadena necesita saber cuánto hay en cada local
   y trasladar entre ellos. Es el cambio más grande de la lista.
6. Reportes: inventario valorado y rotación.
7. Marca, lote y vencimiento, para quien los necesita (farmacias, alimentos).

**Lo que no conviene traer:** préstamos, consignación, requisición, alisto,
empaque y despacho, producción y las tiendas en línea: son de otro tipo de
negocio.

- [x] **T-1501** Requisitos al spec y diseño al plan, con sus revisores.
      Escrito el 2026-10-03: spec §5.10 (RN-98 a RN-105), RF-87 a RF-94 y
      plan §15 (§15.1 a §15.8). Cinco pasadas de cada revisor; lo que cambió
      por ellas está en `progress.json`, sesión 83.

      **Verificación:** `spec-reviewer` y `plan-reviewer` sin observaciones.
      **Hecha el 2026-10-03.**
- [ ] **T-1502** El kárdex y las salidas con motivo (puntos 1 y 2; RN-98,
      RN-99, RN-105; RF-87, RF-88, RF-94; plan §15.1 a §15.3). Migración 023 con `stock_movements`,
      `stock_levels`, `stock_reasons`, `stock_exits` y la apertura de lo que
      había; `domain/inventory.py` con `move`; `MoveStock` reemplaza a
      `adjust_stock` en los cuatro casos de uso que lo llaman;
      `RegisterStockExit` y `CancelStockExit` con su asiento; el alta y la
      edición de productos pasan a `RegisterProduct` y `UpdateProduct` (con
      caracterización antes), la ficha pierde el campo de existencia (RF-94)
      y `PUT /products/update_product/{id}` responde `stock_not_editable`,
      `DELETE` de un producto con kárdex responde `product_has_movements`; `/inventario/kardex/[id]`, `/inventario/salidas`
      y `/inventario/motivos`; el simulado.

      **Verificación:** una venta, una devolución, una entrada y una merma
      aparecen en el kárdex del producto con antes y después, la existencia
      final es la suma, y `products.stock` coincide con `stock_levels` en toda
      la batería. Editar la existencia desde la ficha ya no es posible.

      **Avance del 2026-10-10 (el núcleo).** Hecho: la migración 023 entera
      con sus once modelos (`model_inventory.py`); `domain/inventory.py` con
      `move` y `Movement`; los puertos `StockLevelRepository`, `KardexWriter`
      y `KardexReader`; `MoveStock` reemplazando a `adjust_stock` en la venta,
      la devolución, la entrada y su anulación, con `lock_for_sale` → `lock`
      y `branch_id` en las tres peticiones; `GET /inventory/kardex` y
      `GET /inventory/levels`; la apertura de un producto nuevo por el kárdex,
      `stock_not_editable` en el PUT y `product_has_movements` en el DELETE,
      con la ficha del POS mostrando la existencia sin editarla;
      `tests/test_inventario.py`, que compara `products.stock` con la suma de
      `stock_levels` después de cada documento.

      **Avance del 2026-10-10 (segundo tramo, el backend entero).** Las
      salidas con motivo: `domain/inventory.py` con los motivos de fábrica,
      `check_exit_reason` y `ExitLine`; `RegisterStockExit` y
      `CancelStockExit` con `post_stock_exit` en el libro y las cuentas
      `6.3.01` y `4.9.02` con sus cinco mapeos en `chart.py`; los motivos se
      siembran al nacer la compañía (`crud_company._motivos`); rutas
      `/inventory/reasons` (GET, POST, PUT) y `/inventory/exits` (GET, POST,
      `/{id}/cancel`); ocho códigos nuevos en los cuatro lugares;
      `tests/test_salidas.py` contra la pila, con el asiento y su inverso. Y
      la ficha en casos de uso: `domain/product.py` (el código manda sobre la
      tarifa, qué vacía un PUT parcial, `stock` no se edita),
      `RegisterProduct`, `UpdateProduct` y `DeleteProduct` con
      `CategoryRepository`; `crud_product.py` queda de adaptador. **Falta
      solo el POS:** `/inventario/kardex/[id]`, `/inventario/salidas`,
      `/inventario/motivos`, y el simulado de los dos `GET` de lectura y de
      las seis rutas de motivos y salidas.
- [ ] **T-1503** Toma física (punto 3; RN-100; RF-89). `stock_counts` y sus líneas
      con `system_qty` al contar; abrir, contar, aplicar y descartar; el
      asiento de la diferencia; `/inventario/toma-fisica`.

      **Verificación:** contar 8 donde el sistema dice 10 deja un ajuste de −2
      con el motivo «toma física» en el kárdex; vender una unidad entre contar
      y aplicar no cambia el ajuste; abrir una toma de una subcategoría con
      otra abierta de su raíz responde con código.
- [ ] **T-1504** Mínimo por producto y bajo mínimo (punto 4; RN-101; RF-90).
      `products.min_stock`, el mínimo general en `settings` y
      `LOW_STOCK_THRESHOLD` fuera del `.env`; el reporte y el aviso del panel.

      **Verificación:** el reporte lista los que están por debajo de su propio
      mínimo y, sin mínimo propio, del general; el `.env` del POS ya no tiene
      el umbral.
- [ ] **T-1505** Existencias por sucursal y traslados (punto 5; RN-102,
      RN-105; RF-91; plan §15.3). **Primero la caja de la sesión**:
      `terminal_id` opcional en `POST /auth/company`, validado contra la
      compañía (`terminal_not_found`, que ya existe), `token_de_sesion`
      conservando la terminal al cambiar de idioma, `CompanyOption` con sus terminales y la pantalla `/compania` con la
      lista cuando hay más de una y «Cambiar de caja» en el menú; el
      cajero de una compañía con una sola terminal sigue entrando directo.
      Después: `SaleRequest` y `ReturnRequest` ganan `branch_id` desde el
      `bid`, la venta descuenta de la sucursal de su terminal, la entrada
      elige sucursal, `TransferStock` y `/inventario/traslados`; la lista de
      inventario desglosa por sucursal cuando hay más de una; el simulado
      gana una segunda sucursal con su terminal.

      **Verificación:** una sesión abierta en la terminal de la sucursal 2
      vende y no baja la existencia de la 1, un traslado mueve las dos y el
      valorado total no cambia; una compañía migrada con dos sucursales
      reparte con traslados y no le queda ningún ajuste en el kárdex; con una
      sola terminal el login no pregunta nada.
- [ ] **T-1506** Valorado y rotación (punto 6; RN-103; RF-92). Las dos consultas, el
      saldo contable al lado del valorado, y los dos reportes en `/dashboard`.

      **Verificación:** el valorado suma existencia por costo promedio y
      cuadra con el saldo de inventario de la contabilidad cuando la apertura
      se hizo con el valorado del día y no hubo reversiones a costo histórico
      ni productos sin costo; con una devolución después de que el promedio
      cambió, el reporte nombra la causa y el monto de la diferencia.

- [ ] **T-1507** Marca, y lote y vencimiento por línea de entrada y de salida
      (punto 7; RN-104; RF-93). `brands`, `stock_lots`, `allocate_lots` en la venta,
      el interruptor en `/configuracion`, `/inventario/marcas` y el reporte de
      lo que vence. Lote y vencimiento **se activan por compañía**: quien no
      los usa no los ve.

      **Verificación:** con lote activado, una entrada con lote y vencimiento
      aparece en el kárdex y en el reporte de lo que vence, una venta
      descuenta del lote que vence primero, y una toma física cuenta por
      lote y puede anotar un sobrante en un lote nuevo; sin activarlo, la
      pantalla no los pide.
- [ ] **T-1508** Sembrar en las compañías que ya tenían contabilidad activa las
      cuentas y los mapeos que se agregaron a la plantilla **después** de que
      activaran (los de planilla, F12), con la misma forma que la migración
      023 usa para los de inventario: lo que ya existe se salta. **Surgió en
      la revisión del plan el 2026-10-03** —ninguna migración lo hizo y esos
      eventos hoy caen en «por clasificar»— y **confirmada con el usuario el
      2026-10-10**. Es una corrección de F11/F12 sin RN propio: RN-59
      («por clasificar») es lo que sostiene mientras tanto.

      **Verificación:** una compañía activada antes de F12 paga una planilla y
      el asiento no toca «por clasificar».
- [ ] **T-1509** La herramienta de soporte que recalcula existencias desde el
      kárdex (RF-95; plan §15.1 y §15.4, `RebuildStockLevels`):
      `POST /support/companies/{id}/rebuild-stock-levels`, que fija la
      compañía con `tenancy.compania(cid)` por el tiempo de la petición,
      reescribe `stock_levels` y `products.stock` con la suma del kárdex y
      deja en bitácora cuántas filas cambió; el botón en la ficha de la
      compañía del panel; el simulado. Va después de T-1502, que es donde
      nace el kárdex. Es la excepción escrita a RN-32 y la única escritura de
      soporte sobre datos de negocio: `tests/test_soporte.py` tiene que
      vigilar que siga siendo la única.

      **Verificación:** con un nivel alterado a mano en la base, la acción lo
      devuelve a la suma del kárdex, `products.stock` queda igual a la suma de
      `stock_levels`, la bitácora dice cuántas filas cambió, y correrla sobre
      una compañía cuadrada no cambia nada.

**Decidido con el usuario el 2026-10-03:** entran los siete puntos, con las
existencias por sucursal (punto 5) y con lote y vencimiento activables por
compañía. F15 va **primera**: el kárdex y el mínimo por producto los usan F13 y
F14.

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
- [x] **T-909** ~~Probar el PDF que genera el backend con reportlab.~~ Ya no hay
      qué probar: el endpoint se quitó el 2026-09-26 (T-922).
- [ ] **T-910** Confirmar si existe el `postsys.sql` original de la VM. El
      compose original lo montaba como script de inicio y nunca apareció. Si
      tiene datos reales, hay que cargarlos en `backend/initdb/`.
- [x] **T-911** Migrar el volumen de datos de `deploy/` a `backend/`. Hecho
      2026-08-16: el stack corría como proyecto `deploy` sobre el volumen
      `deploy_db_data`, así que levantar desde `backend/` habría creado uno
      vacío y parecería una pérdida total. Se copió con un contenedor auxiliar y
      se comprobó `diff -r` idéntico (186 archivos, 207 MB) y los mismos
      registros (38 ventas por ₡360.413,50, 27 productos, 4 usuarios). Ahora el
      stack vivo es `backend/` sobre `ventasys_db_data`.
- [ ] **T-912** Borrar `deploy/` y su volumen `deploy_db_data`. Se dejaron
      intactos como respaldo de la migración de T-911; hay además un volcado en
      SQL fuera del repositorio. Borrarlos cuando haya confianza de que el stack
      nuevo va bien.

**Antes de empezar F5** — los tres salieron de hacer F4 y ninguno se empezó.
Tocan sitios que F5 va a volver a abrir: el esquema, los mensajes de la interfaz
y el guardián que los vigila.

- [x] **T-913** *(antes de F5)* Las columnas de `companies`, `plans` y
      `user_companies` están en **español**, contra la regla de código en inglés.

      **Decidido el 2026-09-05: se aceptan por escrito.** El porqué, con las
      cifras medidas, está en [plan.md §3.9](plan.md). En corto: son **58
      archivos y ~890 menciones**; **trece de los diecisiete nombres son claves
      JSON publicadas** que hay que mover en cinco frentes sin compilador común
      —y una que quede vieja no rompe la build, devuelve `undefined` en
      pantalla—; y `company_dump.py` exporta por nombre de columna sin versionar
      el esquema, así que **todo respaldo ya entregado quedaría inservible en
      silencio**.

      Dos correcciones al enunciado de la tarea, que medía de menos: son **cinco
      tablas y no tres** —`branches` y `terminals` tienen las mismas columnas en
      español— y **diecisiete columnas**, no diez.

      **Dónde se reabre**: F5 no toca estas tablas, pero **F6 sí** (T-608, el ABM
      de sucursales y terminales). Si se corrige, es ahí: se paga una vez, con la
      migración que F6 ya va a escribir. Anotado en T-916.

- [x] **T-914** *(antes de F5)* El mensaje de éxito en español de `/caja` y, lo
      que importaba más, las formas que el guardián de T-812 no veía.

      **Hecho el 2026-09-05.** El mensaje pasó a `cash_movement_registered`, una
      **variante de Paraglide con selector sobre el tipo** y no una
      interpolación: en los tres idiomas la frase entera cambia, no solo la
      palabra. Antes ni «entrada» pasaba por el catálogo, aunque las claves
      `cash_movement_in` y `cash_movement_out` ya existían.

      El guardián creció por tres lados, y los tres tenían un caso real:

      1. **La propiedad, no la llamada.** `SUMIDEROS_OBJETO` indexaba por nombre
         de función (`error`, posición 1), así que no podía ver
         `return { success: '…' }` —que no es una llamada a nada y es por donde
         salen casi todos los avisos de éxito del POS—. Pasó a
         `PROPIEDADES_QUE_SE_VEN = ['success', 'message']`, comprobadas en **todo**
         objeto literal. Cubre de una vez `return { success }`,
         `return { message }`, `fail(400, { message })` y `error(404, { message })`.
         Es la lección que el propio archivo tenía escrita y no había aplicado
         del todo: **un sumidero se declara por dónde entra el texto, no por cómo
         se llama la función**.
      2. **El `{:else}` de un `{#each}`.** El recorrido no bajaba por `fallback`,
         así que todo lo que hubiera ahí era invisible. Se agregó, más
         `pending`/`then`/`catch` de `{#await}`. Encontró el «Sin datos.» de
         `SalesTrendChart`, cuyo gemelo `BarListChart` ya usaba la clave del
         catálogo para lo mismo.
      3. Y con eso apareció el tercero: `{ message: 'Datos de demostración
         reiniciados' }` en `/mock/reset`, la única respuesta del simulado con
         prosa adentro entre doce que ya devolvían código (T-802).

      **Comprobado que se pone rojo** en las dos formas nuevas, devolviendo cada
      texto a su sitio y viendo fallar la prueba señalando archivo y línea.

      Lo que **no** se cerró y queda anotado en T-917: el `<script>` de un
      `.svelte` sigue sin leerlo nadie, así que los sumideros de `toasts.*` son
      casi letra muerta —11 de los 13 sitios que los llaman viven en `.svelte`—.

- [x] **T-915** *(antes de F5)* El desacuerdo entre `create_all` y la migración.

      **Hecho el 2026-09-05, y la tarea estaba mal justificada.** Verificado
      contra la base viva: las catorce tablas **sí** tienen `company_id`
      encabezando un índice, pero no como decía la tarea. Son **siete** por su
      UNIQUE compuesto y **siete** por el índice que InnoDB fabrica solo para la
      foránea sobre `(company_id)`. No falta ningún índice: `create_all` creaba
      **uno de más**, porque en su `CREATE TABLE` la foránea va en línea y el
      `CREATE INDEX` viene después, así que InnoDB ya había hecho el suyo.

      Se quitó `index=True` del `TenantMixin`. Y **la prueba que pedía la
      decisión encontró lo que la tarea no veía**: cuatro UNIQUE que existían
      solo en la migración y que ningún modelo declaraba —`companies`
      (afiliado, compania), `branches` (company_id, codigo), `terminals`
      (company_id, branch_id, codigo) y **`user_companies` (user_id,
      company_id)`**—, más `idx_companies_estado` y nueve índices de rendimiento
      (entre ellos `idx_cash_sessions_user_status`, que es la consulta del
      arqueo).

      **Eso es más grave que el índice**: `docker-compose.test.yml` no corre las
      migraciones, crea la base con `create_all`. O sea que **toda la batería
      corría sobre un esquema que aceptaba membresías duplicadas** mientras
      producción las rechazaba: un camino que las creara pasaba verde en `pytest`
      y reventaba con `IntegrityError` en la base del cliente.

      Se declararon las cinco restricciones y los nueve índices.

      La red es `backend/tests/test_esquema.py`: lee los `.sql` en orden
      —aplicando los `DROP INDEX`— y los compara con `Base.metadata`, sin
      levantar ninguna base. **Comprobado que se pone rojo** en las tres
      direcciones: falta en el modelo, sobra en el modelo, y mismo nombre con
      distinto contenido. Lleva además una prueba de sí misma —que el lector de
      SQL encuentre algo—, por la lección del defecto 25: un cero es el resultado
      más fácil de fabricar por accidente.

      **CORRECCIÓN, el 2026-09-05, al empezar F5.** Acá se escribió «paridad
      total» y esa medida estaba mal tomada. El lector de SQL no entendía la
      forma `CREATE INDEX` suelta; al enseñársela aparecieron cuatro índices más,
      y tirando de ahí salió lo de fondo:

      **`backend/migration.sql` nunca se aplicó a esta base.** No es el esquema
      base: son «arreglos heredados, para una base anterior a F1»
      (`backend/README.md:23`). Se comprobó por los nombres de los índices vivos
      —`products` tiene `ix_products_barcode`, el que genera SQLAlchemy, y no el
      `idx_products_barcode` que declara ese archivo—. Las tablas de negocio las
      creó **`create_all`** al arrancar, y encima fueron las migraciones
      numeradas.

      Dos consecuencias:

      1. **Los nueve índices «de la migración» no existían en ninguna base.**
         Salían de ese archivo heredado, así que estaban escritos, revisados y
         sin efecto desde antes de F1 —incluido `idx_cash_sessions_user_status`,
         que es la consulta del arqueo en cada venta—. Ahora van en la migración
         **006**, que es lo que sí los pone en producción; aplicada y verificada
         el 2026-09-05.
      2. **Quitar los 19 `index=True` fue el movimiento equivocado.** Catorce de
         esos índices **existen en las bases desplegadas** (los creó `create_all`
         al nacer cada tabla), así que quitarlos del modelo dejaba a una
         instalación nueva con un esquema distinto del de las que ya corren. Se
         restauraron los catorce. Los otros cinco no se restauraron y no deben
         restaurarse: son los de `model_company.py`, cuyas tablas creó la
         migración 002/004, y ahí `create_all` nunca llegó a poner el índice.
         Igualar por el otro lado —`DROP INDEX` en producción— se planteó y **se
         decidió no hacerlo**.

      La lista vive en `INDICES_DE_CREATE_ALL`, con su porqué, y hay una prueba
      que la vigila en el otro sentido: una entrada que el modelo ya no declare
      tumba `pytest`, porque una excepción de adorno tranquiliza sin cubrir.

      La lección es la de siempre y esta vez me la aplico a mí: **la verificación
      midió limpio porque no sabía mirar una forma entera**. Un verde vale lo que
      valga lo que el lector alcanza a leer.

**Salieron de cerrar los tres, el 2026-09-05:**

- [x] **T-916** ~~*(antes de T-1001)* Reabrir T-913 si se hace el ABM de
      sucursales y terminales (T-608)~~ — **cerrada el 2026-09-13: no se hace.
      El español se queda, y esta vez para siempre.**

      Era la única condición que T-913 había dejado escrita para reabrirse
      —«si F6 toca esas tablas»—, y F6 las toca. Se cumplió la condición y aun
      así la respuesta es no, por tres razones y ninguna es la comodidad:

      1. **Ningún argumento de plan §3.9 se debilitó y uno se reforzó.** Siguen
         siendo 58 archivos, ~890 menciones y trece claves JSON publicadas que
         hay que mover en cinco frentes sin compilador común. Y desde entonces
         se entregaron más respaldos, que es justo lo que el rename rompe en
         silencio.
      2. **La mezcla ya está escrita, y escribirla no dolió.** La migración 011
         puso `identification_type` al lado de `identificacion` en `companies` y
         en `clients`. Lo que se temía era que esa vecindad fuera una herida
         abierta; con dos columnas nuevas puestas, se ve que es una cicatriz:
         fea de leer, inerte. El costo de convivir con ella es un párrafo de
         documentación, no un defecto que muerda.
      3. **Reabrirla tiene su propio costo y ya se pagó tres veces.** T-913 →
         T-916 → T-1001 → otra vez F6: cada vuelta consumió una sesión en
         volver a medir lo mismo para llegar al mismo sitio. Una decisión que
         se reabre en cada fase no es una decisión pendiente, es un impuesto.

      **Qué haría falta para volver a abrirla**, y se escribe para que no vuelva
      a abrirse por menos: que el rename deje de romper respaldos —o sea, que
      `company_dump.py` versione el esquema *antes* y por otro motivo—, o que
      una de esas columnas empiece a salir en un contrato nuevo hacia afuera.
      Ninguna de las dos está prevista.

      **Lo que sí queda vigente** es la otra mitad de T-913, que nunca estuvo en
      discusión: plan §3.9 dice que la excepción es de **las columnas que ya
      existen y no una licencia para las nuevas**. Las de F6 van todas en
      inglés, y `test_esquema.py` lo comprueba tabla por tabla.
- [ ] **T-917** El guardián de texto suelto **no lee el `<script>` de un
      `.svelte`**: `revisar()` recorre solo el marcado y `revisarTs()` solo abre
      archivos `.ts`. La consecuencia es que los sumideros de `toasts.*` son casi
      letra muerta —11 de los 13 sitios que los llaman viven en `.svelte`—, así
      que un `toasts.error('Producto agotado')` dentro de un `<script>` pasa sin
      que nadie chille. Hoy no hay ninguno, y por eso no bloquea; el arreglo es
      extraer el contenido del `<script>` y pasarlo por `revisarTs`.
- [x] **T-922** **El PDF del backend es un cuarto documento y nadie lo cuenta.**
      **Cerrada el 2026-09-26 quitándolo**, con el visto bueno del usuario: se
      fueron `GET /sales/pdf/{id}`, su proxy en el POS, el botón «PDF del
      backend», el código `sale_details_not_found` —que solo levantaba ese
      endpoint— y `reportlab` de `requirements.txt`. Rehacerlo con el bloque
      fiscal era escribir las tres plantillas dos veces (RN-86). El PDF sale de
      «Imprimir», y el botón ahora lo dice.
      `sale_routes.py` dibuja la factura con reportlab y le faltan las dos cosas
      que F5 le dio a las otras tres: el desglose por tarifa (RF-21) y el idioma
      del documento. Además tiene **ocho rótulos escritos a mano en español**
      —«Factura:», «Fecha:», «Metodo de pago:» (sin tilde), «Detalle:», «Unit:»,
      «Subtotal:», «IVA:», «Total:»—, contra RN-30, así que desglosarlo es
      rehacer la función y no insertarle filas. Y su `IVA:` afirma un nombre de
      impuesto que se configura.
      Anotado también: `crud_sale.get_sale_detail` arma
      `f"Producto #{detail.product_id}"` cuando el producto ya no existe, que es
      otra frase del backend para una persona.
- [x] **T-920** **El archivo del modo simulado crecía sin techo entre corridas.**
      Las pruebas de punta a punta que dan de alta su propia compañía —la salida
      de T-310, y es la correcta— no la retiran al terminar, así que
      `.data/mock-db.json` acumulaba una por corrida. Llegó a **29 compañías** y
      esa pila tumbó **cuatro pruebas de tres archivos**, incluida una del aviso
      de vencimiento que no toca nada de eso.

      **Arreglado el 2026-09-05**: `POS_MOCK_FRESH=1`, que pone la configuración
      de Playwright, hace que el simulado **ignore lo guardado y siembre de
      cero**. La salida no es que cada prueba limpie lo suyo —una que falla a
      mitad no limpia nada, que es justo cómo empezó esto en T-310— sino empezar
      limpio.

      **Se ignora el archivo, no se borra**: la demostración de quien esté usando
      el POS a mano no se toca. Y subir `SEED_VERSION` deja de ser el martillo
      con el que se vaciaba.

      Verificado: 42 de 42 dos corridas seguidas.

      **Y no estaba funcionando** (visto el 2026-09-26). `playwright.config.ts`
      tenía **dos** claves `env` en `webServer`; en un literal la segunda pisa a
      la primera, así que `POS_MOCK_FRESH` no llegaba nunca. El archivo tenía 109
      compañías, y la del aviso de vencimiento ya estaba vencida: la prueba de
      soporte fallaba por la fecha. Arreglado en un solo `env`.

      Arreglarlo destapó la segunda mitad: `persist()` escribía en el mismo
      archivo aunque se sembrara de cero, así que con la bandera activa la
      primera venta de la batería **reemplazaba** la demostración. Ahora la
      batería escribe en `.data/mock-db.e2e.json`, y `mock-db.json` no se toca —ni
      se limpia: las 109 compañías siguen ahí hasta que alguien pulse «Reiniciar
      demo»—.
- [ ] **T-921** Una prueba de punta a punta navegaba **sin esperar** a que se
      enviara el formulario de mover una categoría, y el `goto` ganaba la carrera
      con la máquina cargada: pasaba sola y fallaba en la suite completa,
      señalando el inventario —el único sitio donde no estaba el problema—.
      Corregido en `categorias.spec.ts` esperando a que el modal se cierre.
      **Queda barrer las demás**: es la misma familia que las tres de T-409, y el
      patrón «enviar y navegar» aparece en más de un archivo.

      **Cayó otra el 2026-09-05**, del mismo árbol pero por la otra rama: un
      `selectOption` pelado después de un `goto`, en la última línea de «dos
      niveles, sus reglas y sus productos». Playwright fija el valor del DOM
      aunque Svelte todavía no le haya enganchado el `onchange`, así que la raíz
      cambiaba en la pantalla y no en el estado; fallaba una de cada varias
      corridas y **señalaba la subcategoría**, que no era el problema. Ese mismo
      archivo ya tenía `elegirHasta` escrito para esto y esa llamada no lo usaba.
      Vale para el barrido: buscar `selectOption` y `click` sueltos después de un
      `goto`, no solo el patrón «enviar y navegar».
- [x] **T-923** El tirador de plegar el menú se monta **sobre el borde**, y la
      compañía y el idioma suben a la barra de arriba. Pedido por el usuario el
      2026-09-12, con capturas de referencia.

      Dos cosas, y las dos por la misma razón: lo que hay que ver sin buscar no
      puede vivir donde desaparece.

      1. **El tirador.** Estaba dentro del encabezado del menú, así que al
         plegarse se corría con él y había que ir a encontrarlo entre los
         iconos. Ahora va a caballo del borde —`-right-3.5` sobre un `nav` que
         pasó de `lg:static` a `lg:relative`, porque un `static` no ancla un
         `absolute`— y queda en el mismo punto de la pantalla en los dos
         estados. El icono lleva **flecha**: señala hacia dónde va a ir, no
         dónde está, así que son dos —`panelclose` y `panelopen`—.

      2. **La compañía, la caja y el idioma** pasaron del pie del menú a la
         barra. Al pie desaparecían con el menú plegado, y T-211 dice que en qué
         compañía y en qué caja se trabaja es lo que evita cobrarle una venta al
         negocio equivocado. De paso la barra dejó de ser un título y un botón
         de tema en todo lo ancho.

      **Se definen una vez, con `{#snippet}`, y se usan en dos sitios**: la barra
      en pantalla ancha y el cajón del menú en pantalla chica, donde arriba no
      caben. Dos copias del mismo bloque es como una se queda sin el arreglo que
      recibió la otra.

      **Lo que costó, y que vale para la próxima:** duplicar un bloque por
      responsividad rompe toda prueba que diga `getByText(...).first()`, porque
      la copia oculta suele ir primero en el árbol. Cuatro pruebas cayeron por
      eso y ninguna tenía que ver con el menú. Las tres afectadas ahora piden
      **la copia visible**, que además es lo que la prueba quiere decir: el
      selector de idioma ya se mudó una vez y un `#id` en la prueba hace que
      mudarlo cueste una ronda de fallos ajenos al cambio.

      **Verificación:** 580 del POS, 54 de punta a punta, `npm run check` 0/0.

- [x] **T-927** **Contabilidad arrastraba la página de lado en un teléfono.**
      RNF: el POS se usa en pantallas chicas.

      **Verificación:** a 390 px, `main.scrollWidth == main.clientWidth` en las
      siete pantallas de `/contabilidad`.

      **Hecha el 2026-09-19.** La causa no estaba en contabilidad sino en dos
      clases de `app.css`: ni `.input` ni `.table-wrap` tenían `min-width: 0`.
      Dentro de una rejilla o un flex el ancho mínimo por omisión es el del
      contenido, y el contenido de un `<select>` es su opción más larga: el
      desplegable de cuentas —«1.1.01.001 · Efectivo en caja»— estiraba la
      columna a 544 px dentro de un hueco de 316 y el desbordamiento subía hasta
      `main`, que se desplazaba con el encabezado incluido. Lo mismo le pasa a un
      contenedor con `overflow-x: auto`: sin `min-width: 0` crece hasta la tabla
      en vez de desplazarla, y entonces el `overflow-x` no se usa nunca.

      **Se midió antes de tocar nada**, con un guion de Playwright que compara
      `scrollWidth` contra `clientWidth` a 390 px y nombra al elemento más
      externo que se sale. Sin eso habría arreglado a ciegas: los
      `overflow-x-auto` ya estaban puestos y la pantalla *parecía* correcta.

      **Y destapó que nueve pantallas más se arrastran** —`/caja`, `/facturas`,
      `/dashboard`, `/inventario`, `/inventario/entradas`, `/clientes`,
      `/usuarios`, `/compras/proveedores`, `/compras/cuentas-por-pagar`—, que es
      anterior y queda como T-928.

- [ ] **T-928** **Nueve pantallas se arrastran de lado en un teléfono.** Las de
      arriba. Medido el 2026-09-19 con el mismo guion que T-927, antes y después
      de su arreglo: la lista no cambió, así que es anterior.

      En las que arrastra el documento, el único contenedor que se desplaza es
      `div.table-wrap`, y **se desplaza bien** (356→712 con `overflow-x: auto`):
      el desbordamiento viene de otro lado y hay que encontrarlo antes de
      arreglar. En `/caja` y `/dashboard` el que se desplaza es `main`.

      **Verificación:** una prueba de punta a punta que recorra las pantallas a
      390 px y exija `scrollWidth == clientWidth` en `main` y en el documento.
      Hoy no se puede escribir sin lista de excepciones —por eso esta tarea—, y
      una prueba con lista de excepciones es la que después nadie limpia.

- [ ] **T-929** **El aviso de la pestaña de factura electrónica dice algo que
      dejó de ser cierto.** `settings_einvoicing_warning_2` afirma que «la llave y
      su PIN no se piden ni se guardan», y desde T-603 se piden, y la llave va a
      Vault. La primera mitad del aviso —que todavía no se emite— sigue siendo
      verdad hasta F7. Visto el 2026-09-26 al reescribir el aviso de al lado;
      no se tocó porque no era parte de T-723.

- [ ] **T-926** **La prueba de punta a punta de F11 pasa sola y falla en la
      suite completa.** `contabilidad.spec.ts › de la activación al mes cerrado`
      falla en el cierre de caja: el asiento «Cierre de caja n.º …» no aparece.
      Corrida aislada —una vez o dos seguidas— pasa siempre.

      **Es anterior a F6**, medido el 2026-09-19: con el árbol en `HEAD` y sin
      ninguno de los cambios de la sesión, la suite da **55 pasan y esta falla**.
      Con los cambios da 66 y 1, la misma. Se anota para que nadie la atribuya
      a lo último que tocó, que es justo lo que hace una prueba que falla por
      estado ajeno.

      La pista está en el registro del servidor: durante el envío del cierre
      aparece un `TypeError: Failed to fetch` en el `update()` de
      `$lib/ui/forms.ts`, precedido de `[vite] The next HMR update will cause
      the page to reload`. **El simulado guarda su estado en `.data/`, que está
      dentro del proyecto, y `vite` lo vigila**: una escritura del simulado
      dispara HMR y recarga la página a mitad del envío. Aislada casi no pasa
      porque hay pocas escrituras; en la suite entera hay cientos.

      Si eso se confirma, la salida es sacar `.data/` de lo que vigila `vite`
      (`server.watch.ignored`) y no reintentar el clic: un reintento escondería
      el mismo problema en las otras cincuenta y seis.

      **Sigue igual el 2026-09-26**, con el árbol de T-723: falla en la suite
      completa —75 pasan y esta falla— y pasa sola. Con el simulado sembrando de
      cero por primera vez (el arreglo de T-920 que no llegaba) sigue fallando,
      así que la pila de compañías viejas no era la causa. La pista de HMR queda
      en pie: el simulado ahora escribe en `.data/mock-db.e2e.json`, que sigue
      dentro de lo que vigila `vite`.

      **Y no es la única** (2026-09-26, con T-726): en una corrida completa de
      81 falló `categorias.spec.ts › dos niveles, sus reglas y sus productos`, y
      corrida sola —con las de idiomas— pasa. El mismo síntoma que esta: estado
      o recarga ajenos a la prueba, no lo que prueba.

      **Sigue igual el 2026-09-27** (T-705, T-722): 83 de 84, y la que falla es
      esta. En el camino apareció otra de la misma familia y esa sí se arregló:
      `factura-electronica.spec.ts › guardar la configuración no mueve el
      ambiente` esperaba `networkidle` después de guardar, que se cumple antes de
      que salga el POST, y el `goto` siguiente cortaba el guardado
      (`ERR_ABORTED`). Ahora espera la respuesta, como `guardarConfiguracion`.
      No se reintenta nada.

- [ ] **T-930** **El día de la compra de `test_aislamiento.py` se repite cada 50
      minutos.** `DIA_DE_LA_COMPRA` es `2020-01-01 + (segundos del reloj % 3000)`
      días, y la pila de pruebas conserva la base entre corridas: dos corridas
      separadas por un múltiplo de 50 minutos compran el mismo día, y
      `test_el_credito_fiscal_de_A_no_suma_las_compras_de_B` ve 4 000 en vez de
      2 000. Pasó el 2026-09-27 con dos corridas completas a unos 50 minutos una
      de la otra; sola pasa.

      No es una fuga entre compañías —lo que la prueba vigila— sino compras de
      la **misma** compañía hechas por la corrida anterior. La salida es que el
      día no pueda repetirse entre corridas (un contador guardado, o el día más
      lejano con compras más uno), no ensanchar la cuenta.

      **Verificación:** dos corridas completas seguidas, sin reiniciar la pila,
      en verde las dos.

- [ ] **T-925** **`account_not_found` sirve para dos cosas.** Lo levantan
      `crud_accounting` en seis sitios, con `account_id`, sobre una cuenta del
      catálogo contable, y `/users/membership` en uno, sin datos, cuando no
      existe cuenta con ese correo.

      Salió el 2026-09-19 al quitar el duplicado que el código tenía en las dos
      listas: **no era copia y pega, era el síntoma**. Estaba anotado una vez en
      el bloque de usuarios y otra en el de contabilidad porque de verdad
      pertenece a los dos, y como las listas se comparan como conjuntos nadie
      lo notaba.

      La frase que sale hoy es «Esa cuenta no existe.», que es la contable. Al
      administrador que escribe un correo equivocado para dar una membresía le
      dice algo casi cierto y nada útil: no le dice que el problema es el correo
      ni que la persona tiene que tener cuenta antes.

      Lo que hay que decidir es **si se parte en dos códigos** —el de
      `/users/membership` pasaría a uno propio, con el correo como dato— o si se
      deja. Partirlo son los cuatro sitios de siempre (`api_errors.py`,
      `API_CODES`, los tres `errors.json` y el simulado) y toca un endpoint que
      ya existe, así que no es gratis.

      Relacionado: T-903 dice que ese alta debería ser una invitación que se
      acepta, y eso reescribe el endpoint entero. Si T-903 se hace antes, esto
      se resuelve de paso.

- [x] **T-919** `tests/test_esquema.py` compara **índices y restricciones, no
      columnas**. El defecto 19 fue justo de columnas —cinco con un tipo en el
      modelo y otro en la migración— y se verificó a mano una vez, en F2. Al
      escribir T-507 volvió a asomar: `default="Unid"` es del lado de Python y no
      emite `DEFAULT` en el DDL, así que `create_all` habría creado la columna sin
      valor por omisión mientras la migración sí se lo pone. Lo cazó mirarlo a
      mano, que es exactamente lo que no escala. Falta extender la prueba a
      nombre, tipo, nulabilidad y valor por omisión.

      **Hecho el 2026-09-06**, y encontró treinta diferencias el primer día.
      Cinco pruebas nuevas; el archivo pasa de 7 a 12.

      **El modelo no se traduce a mano: se le pide a SQLAlchemy que compile el
      `CREATE TABLE` para MySQL y se lee con el mismo lector que los `.sql`.**
      Así lo comparado es literalmente el DDL que corre una instalación nueva
      contra el que corrió una vieja, y no la opinión de la prueba sobre a qué
      equivale un `Numeric(7, 6)`. Es además lo que hace visible el caso de
      T-507: un `default=` de Python no aparece en ese DDL y un `server_default=`
      sí. Lo que sí hay que normalizar es la notación —`INT`/`INTEGER`,
      `TINYINT(1)`/`BOOL`, `DECIMAL(7,6)`/`NUMERIC(7, 6)`, la ausencia de
      `NOT NULL`, el `AFTER x` que es posición y no definición—.

      **Tipos y nulabilidad coincidían en todo.** Las treinta diferencias eran de
      valor por omisión, en dos grupos con causas distintas:

      - **Doce del lado del modelo**, y las doce eran el defecto de T-507 otra
        vez: `default=0`, `default="prueba"`, `default=True` en `plans`,
        `companies`, `branches`, `terminals`, `user_companies` y `users`. Del
        lado de Python, o sea invisibles en el DDL. Ahora llevan `server_default`
        —con `text("1")` y no `"1"`, porque una cadena se emite entrecomillada y
        `DEFAULT '1'` no es `DEFAULT 1`—. No toca ninguna base desplegada:
        `create_all` no altera lo que ya existe.
      - **Dieciocho del lado de la migración**: el `DEFAULT 1` de `company_id`,
        `branch_id` y `terminal_id`. Ver la **migración 007**.

      **La prueba se comprobó al revés**, que es la lección del defecto 25: se
      rompió el esquema de cuatro maneras —tipo distinto, `server_default` que
      falta, nulabilidad distinta y una excepción de adorno— y las cuatro veces
      falló la prueba que tenía que fallar, y solo esa.

      `OMISIONES_DE_LA_MIGRACION` queda **vacía a propósito**: existe para que la
      primera excepción tenga dónde ir con su porqué, no para llenarla.

- [x] **T-919b** Migración 007: quitar el `DEFAULT 1` de compañía, sucursal y
      terminal. **Aplicada el 2026-09-06.**

      Los dieciocho no eran una decisión de diseño sino **la cicatriz del
      backfill de la 002**: `ADD COLUMN company_id INT NOT NULL` sobre una tabla
      con filas necesita un valor para las que ya estaban, se le puso 1 —la
      única compañía que existía— y el DEFAULT se quedó en la definición para
      siempre.

      Lo que arreglaba: en una instalación nueva un INSERT que olvide la
      compañía revienta con «Field 'company_id' doesn't have a default value»;
      en la base migrada de un cliente entraba callado y la fila quedaba en la
      compañía 1. En la columna que sostiene todo el aislamiento entre clientes,
      esa es la diferencia entre un error ruidoso y un dato ajeno archivado en
      silencio. **La base de pruebas era la estricta y la de producción la
      permisiva**, o sea al revés de como conviene.

      Se eligió quitarlos en vez de declararlos excepción porque es lo único que
      cierra la divergencia en lugar de bendecirla, y porque el riesgo es
      medible: `DROP DEFAULT` no toca una sola fila, es reversible con
      `SET DEFAULT 1`, y **la prueba de que nada dependía del defecto es que la
      batería entera ya corría contra el esquema sin él**.

      Comprobado en la base de trabajo: cero columnas con defecto, 38 ventas por
      ₡360.413,50 intactas, y `sql_mode` con `STRICT_TRANS_TABLES` —sin eso
      MySQL habría insertado un 0 con una advertencia en vez de fallar—.
- [ ] **T-918** `backend/initdb/` está vacío y `docker-compose.test.yml` no corre
      las migraciones, así que la batería y toda instalación nueva se arman con
      `create_all`. T-915 igualó lo que las dos formas declaran, pero la asimetría
      de fondo sigue: `create_all` corre con `checkfirst`, nunca alcanza a una
      tabla que ya existe, y **ninguna prueba ejecuta las migraciones**. Una
      migración con un error de sintaxis no la caza nadie hasta el día de
      aplicarla. Vale la pena una prueba que las aplique sobre una base vacía.
- [x] **T-931** La página entera se desplazaba y se llevaba el menú. En el
      detalle de una venta con el tiquete, el menú quedaba cortado a media
      pantalla y debajo, fondo vacío. La causa era un `sr-only` —el rótulo
      invisible del monto en letras—: es `position: absolute`, y como `main`
      desplazaba sin estar posicionado, el rótulo no quedaba dentro de él sino
      del documento, y lo estiraba hasta su altura. `main` es `relative` en el
      POS y en el panel de soporte.

      **Verificación:** `tests/e2e/desplazamiento.spec.ts` recorre las treinta
      y cuatro pantallas del POS y las cinco del panel con una ventana baja
      (480 px) y comprueba que el documento no pase de la ventana. Sin el
      arreglo fallaban el detalle de una venta y la configuración de planilla.

- [x] **T-932** Configuración: «Guardar cambios» volvía siempre a la pestaña
      Negocio. Guardar recarga la pantalla entera —para que la moneda y el
      acento lleguen a todo el POS— y la pestaña vivía solo en memoria. Ahora
      va en la dirección (`?seccion=moneda`), con `replaceState`: sobrevive a
      la recarga y el servidor ya la pinta abierta.

      **Verificación:** `tests/e2e/configuracion.spec.ts`: guardar desde
      «Moneda e impuesto» deja abierta esa pestaña; sin pestaña en la
      dirección, o con una que no existe, abre Negocio.
