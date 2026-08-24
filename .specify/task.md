# VentaSys — Tareas

> El trabajo de [spec.md](spec.md) según el plan de [plan.md](plan.md), en orden
> de ejecución. `RF-n` y `RN-n` remiten al spec.
>
> **Cómo se usa.** Se marca `[x]` al terminar, no al empezar. Una tarea está
> terminada cuando su verificación pasa, no cuando el código compila. Lo que
> importe para quien retome va a `progress.json`; este archivo es la lista de
> trabajo, no el registro histórico.
>
> Actualizado: 2026-08-23

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
- [ ] **T-509b** Migración: `tax_rate` y `tax_amount` en `sale_details` y en
      `return_details`, escritos al cobrar. **La tarifa se congela en la línea**,
      no se lee del producto (plan §6.3): la del producto cambia, y con tarifas
      mezcladas el cociente `tax / subtotal` del encabezado es un promedio que
      devuelve de más o de menos según qué se devuelva. `TaxRate.of_sale` queda
      como respaldo para las ventas anteriores a la migración, que tienen una
      sola tarifa.
- [ ] **T-509c** El servidor verifica por línea: `sale_totals` deja de recibir
      una tasa única y aplica la de cada línea. La tolerancia de T-108b se mide
      **por documento**, no por línea: con tres tarifas hay tres redondeos donde
      antes había uno, y por línea una venta larga se rechazaría por acumulación.
- [ ] **T-510** Desglose por tarifa en las tres plantillas de documento, solo
      cuando hay más de una. RF-21.
- [ ] **T-511** Verificar con una venta que mezcle 13 %, 2 % y 0 %: que cuadre,
      que desglose, y que la **devolución parcial de una sola tarifa** reembolse
      lo que se cobró por esa línea y no el promedio de la venta. El caso del
      medicamento al 2 % junto al arroz al 13 %: devolver solo el medicamento
      tiene que dar ₡1 020, no ₡1 075.

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
- [x] **T-911** Migrar el volumen de datos de `deploy/` a `backend/`. Hecho
      2026-08-16: el stack corría como proyecto `deploy` sobre el volumen
      `deploy_db_data`, así que levantar desde `backend/` habría creado uno
      vacío y parecería una pérdida total. Se copió con un contenedor auxiliar y
      se comprobó `diff -r` idéntico (186 archivos, 207 MB) y los mismos
      registros (38 ventas por ₡360.413,50, 27 productos, 4 usuarios). Ahora el
      stack vivo es `backend/` sobre `ventasys_db_data`.
- [ ] **T-912** Borrar `deploy/` y su volumen `deploy_db_data`. Se dejaron
      intactos como respaldo de la migración de T-911; hay además un volcado en
- [ ] **T-913** Las columnas de `companies`, `plans` y `user_companies` están en
      **español** (`afiliado`, `estado`, `vence_el`, `max_usuarios`, `rol`),
      contra la regla de código en inglés. Vienen de la migración 002 y hoy son
      la única excepción; renombrarlas toca el modelo, los servicios, el panel de
      soporte y una migración con datos. Decidir si se corrige o se acepta por
      escrito.
- [ ] **T-914** Un mensaje de éxito en español dentro de una acción: el
      `Movimiento de ${type} registrado` de `/caja`. Lleva interpolación, así que
      necesita una clave con el tipo de movimiento traducido, no un `m.*` pelado.
      Y **el guardián de T-812 no ve esa forma**: conviene agregar `success` a los
      sumideros de objeto, que es lo que encontró los cuatro de T-411.
- [ ] **T-915** `create_all` crea `ix_<tabla>_company_id` en las catorce tablas
      de negocio y la base migrada **no lo tiene**: en la base viva el índice que
      usa el filtro es el UNIQUE compuesto que empieza por `company_id`. No
      degrada nada hoy —la columna sigue siendo la primera de un índice— pero es
      el mismo código con dos esquemas, que es justo lo que la regla prohíbe.
      Apareció al comparar `information_schema` en T-401.
      SQL fuera del repositorio. Borrarlos cuando haya confianza de que el stack
      nuevo va bien.
