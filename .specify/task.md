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

## F8 · Multi-idioma

Español, inglés y portugués. El español en **usted**, no en voseo (RN-22).

**El mecanismo tiene que existir antes de F3**, aunque los catálogos de inglés y
portugués se llenen después. F3 agrega el panel de soporte, F4 las categorías,
F5 el buscador de CABYS y F6 la pantalla del certificado: cada pantalla escrita
con la cadena adentro es una pantalla que hay que volver a abrir. Escribirla con
`t('ventas.cobrar')` desde el primer día cuesta lo mismo.

### El backend deja de escribir texto

- [ ] **T-801** Elegir la biblioteca con una prueba real sobre la pantalla de
      ventas, que es la más cargada. Candidatos: Paraglide (Inlang) y
      `typesafe-i18n`. Criterios, en orden: que funcione en el servidor, que una
      clave que falta rompa `npm run check`, y que no pese en el arranque.
      Plan §8.5.
- [ ] **T-802** Los 68 mensajes del backend pasan a **código y datos**:
      `{"code": "insufficient_stock", "product": "Arroz", "available": 2}`.
      El dominio ya lanza los errores con esos datos —es el pago de F1—, así que
      el cambio vive en los adaptadores `crud_*`, un archivo por flujo. RN-30.
- [ ] **T-803** Cada código de error tiene su prueba: «esta situación devuelve
      este código». Sustituye a comparar cadenas, que es lo que hacen hoy las de
      caracterización.

### Los catálogos

- [ ] **T-804** Extraer los 455 textos del frontend a catálogos: 223 nodos de
      texto, 205 atributos y 27 mensajes de acciones, en 33 archivos. Plan §8.1.
- [ ] **T-805** Reescribir a **usted** en la misma pasada. Son 48 apariciones de
      voseo en 19 archivos; hacerlo después obliga a volver a abrirlos todos.
- [ ] **T-806** `ui/format.ts` deja de formatear fechas fijo en es-CR: los meses
      y el orden dependen del locale.
- [ ] **T-807** Catálogo de inglés.
- [ ] **T-808** Catálogo de portugués (Brasil). **Solo la interfaz**: la factura
      electrónica sigue siendo la de Hacienda Costa Rica. Vender en Brasil
      implica NF-e —otro esquema, otra autoridad, otro certificado— y sería una
      fase aparte.

### Dónde vive

- [ ] **T-809** El `locale` efectivo entra en el JWT junto con la compañía y el
      rol; el `load` del layout lo lee de ahí. Orden: lo de la persona, si no lo
      de la compañía, si no `es`. Plan §8.4.
- [ ] **T-810** Selector de idioma: en Configuración el de la compañía, en el
      menú del usuario el suyo. RN-28.
- [ ] **T-811** Idioma del **documento**, separado del de la pantalla. La
      factura es para el cliente y para Hacienda: una compañía costarricense
      emite en español aunque su cajero use el POS en portugués. Toca las tres
      plantillas. RN-29.

### Verificación — sin esto la fase no está terminada

- [ ] **T-812** Prueba que recorre las plantillas buscando texto suelto: si
      alguien escribe una cadena dentro de un componente, la build se cae. Es lo
      único que impide que los catálogos se vayan quedando atrás. RNF-2.
- [ ] **T-813** Prueba de que los tres catálogos tienen las mismas claves. Una
      clave que falta en portugués no puede aparecer como `undefined` en la
      pantalla del cajero.
- [ ] **T-814** Flujo de punta a punta en los tres idiomas: entrar, cobrar y ver
      la factura. Con el documento en español aunque la pantalla esté en
      portugués.

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
      SQL fuera del repositorio. Borrarlos cuando haya confianza de que el stack
      nuevo va bien.
