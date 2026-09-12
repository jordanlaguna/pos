# VentaSys — Tareas

> El trabajo de [spec.md](spec.md) según el plan de [plan.md](plan.md), en orden
> de ejecución. `RF-n` y `RN-n` remiten al spec.
>
> **Cómo se usa.** Se marca `[x]` al terminar, no al empezar. Una tarea está
> terminada cuando su verificación pasa, no cuando el código compila. Lo que
> importe para quien retome va a `progress.json`; este archivo es la lista de
> trabajo, no el registro histórico.
>
> Actualizado: 2026-09-11

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

> **T-916 ya no es puerta de F6: se mudó a T-1001** con el reordenamiento del
> 2026-09-12 (plan §9). La razón no cambió, cambió cuál es la primera
> migración: **no** era que T-608 tocara las tablas con columnas en español,
> sino que quien escribe la primera migración se lleva el rename, porque es lo
> que plan §3.9 llama «se paga una vez». Al ejecutarse F10 antes, esa primera
> migración es la suya.
>
> Para F6 esto significa que **la puerta ya estará abierta o cerrada** cuando
> llegue: si el rename se hizo en T-1001, T-601 y T-621 escriben sobre columnas
> ya en inglés; si se decidió no hacerlo, se escriben sobre la mezcla y no hay
> nada que volver a discutir.

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

- [ ] **T-621** `companies.identification_type` con la lista de Hacienda
      (01/02/03/04), y la identificación **de solo lectura** en Configuración,
      diciendo quién la cambia. RN-45, RF-37.

      Va con T-601, que es la migración de la fase. `business.taxId` y
      `business.taxIdType` quedan como lo que son —dos campos muertos más— y se
      resuelven con los otros cinco en T-614.

      **Verificación:** un `POST` a `/settings` que traiga `business.taxId`
      **no** cambia la identificación de la compañía. Esconder el campo no es
      control de acceso.

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

### Secretos

- [ ] **T-601** Tabla `fe_credentials` con llave primaria
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

      **La clasificación en `company_dump.py` va en este mismo commit, y es por
      columna y no por tabla** (RN-47, decidido el 2026-09-06): viajan el
      certificado público, el usuario de ATV y las fechas; no viajan el `.p12`,
      el PIN ni la contraseña. Eso es lo que el guardián no contempla hoy, así
      que hay que enseñárselo — clasificar la tabla entera en un lado o en el
      otro es justo lo que la decisión descarta.

      **Verificación:** un volcado no contiene el PIN ni la contraseña —se
      buscan a propósito, como en T-609— y al restaurar la pantalla enumera lo
      que hay que volver a cargar.

- [ ] **T-602a** Cifrado en reposo: AES-256-GCM, `FE_CRYPTO_KEY`, con
      `(company_id, environment)` como dato asociado.

      **Verificación:** una fila copiada a otra compañía —o al otro ambiente de
      la misma— **no descifra**. Es lo que verifica RF-22 y RNF-5, y lo necesita
      T-603 en esta fase.

- [ ] **T-602** Puerto `DocumentSigner` —`sign(digest, company_id, environment)`—
      con **prueba de contrato**, no con dos implementaciones.

      Compañía y ambiente van explícitos y **no en un `ContextVar`**: con estado
      escondido, el caso de uso no se puede probar contra «firmá esto con el de
      pruebas» y el trabajador de fondo no tiene contexto que heredar.

      **Verificación:** la prueba de contrato la pasa el adaptador local hoy y
      tiene que pasarla el de Vault el día que llegue. Sin ella, «va aparte»
      significa que nadie sabrá si el puerto admitía dos implementaciones hasta
      que haya que escribir la segunda. El precedente es T-106.

- [ ] **T-602b** *(puede ir después de cerrar la fase)* Adaptador de **Vault
      transit**: la llave privada se importa y nunca entra en memoria de la
      aplicación.

      **El nombre de la llave se DERIVA de `(company_id, environment)`, no se
      guarda.** Un campo escribible ahí deja que la compañía 7 apunte a la llave
      de la 3 y emita firmado con el certificado de otro cliente. Es el
      equivalente del dato asociado del AES-GCM.

      **Verificación:** la prueba de contrato de T-602, más una de integración
      contra Vault en modo `-dev` en contenedor —la misma solución que ya se usa
      para MySQL—. Sin eso se entrega un adaptador que nunca corrió.

- [ ] **T-603** Subida del `.p12` y el PIN, browser → BFF → FastAPI. RF-22.
      Es de **administrador**: así el bloqueo por suscripción la alcanza sin
      tocar nada.

      **Verificación:** un PIN que no abre el `.p12` **no se guarda**. T-606 lo
      abre igual para leer el vencimiento, así que la validación sale gratis y
      evita enterarse el día de facturar.
- [ ] **T-603b** Usuario y contraseña de ATV, por ambiente. La contraseña recibe
      **el mismo trato que el PIN**; el usuario sí se muestra, porque es un
      identificador y sin verlo nadie puede comprobar que escribió el que era.
      RF-29, RN-16.
- [ ] **T-604** `GET` devuelve solo `{ambiente, certificado_configurado,
      nombre_archivo, vence_el, subido_el, atv_usuario, atv_configurado}`.
      **No existe** endpoint que devuelva el archivo, el PIN ni la contraseña.
      RF-23, RN-16.
- [ ] **T-605** Reemplazar y quitar el certificado. RF-24. De administrador.
      **Verificación:** reemplazar deja `cert_uploaded_at` nuevo y **no toca**
      las marcas de ATV; quitar no borra las credenciales de transmisión.
- [ ] **T-606** Leer el vencimiento del propio `.p12` al subirlo, y avisar 30
      días antes. Sin dependencia nueva: `cryptography` ya está y sabe leer
      PKCS#12 —comprobado el 2026-09-05 en el contenedor, versión 50.0.1—.

      La aritmética de fechas entra por el puerto `Clock`, no por
      `date.today()`: es dominio y tiene cobertura obligatoria.
      **Verificación:** con el reloj falso en el día 31 no avisa y en el 30 sí.

### Ambiente

- [ ] **T-610** Elegir ambiente y ver, para cada uno, si ya tiene certificado y
      credenciales. RF-30.
- [ ] **T-611** Pasar a producción **se confirma y queda en bitácora** (RN-35).
      Es el momento en que los documentos dejan de ser un ensayo.

      **Avisa de la certificación de Hacienda y no la impide** (RN-46, decidido
      el 2026-09-06): la confirmación enumera la factura, el tiquete y la nota
      de crédito que §12 exige haber emitido en pruebas. La puerta dura es
      T-713, en F7, que es cuando existen documentos que contar.

      **Verificación:** la entrada lleva el antes y el después —«sandbox →
      production»—, como la de T-305, y no «cambió el ambiente». Volver a
      pruebas también se registra: es el cambio que hace que las facturas dejen
      de tener efecto fiscal sin que nadie lo note.
- [ ] **T-613** `client_id`, realm y URL base **se derivan del ambiente en un
      solo sitio**, y salen de configuración y no del código. Mitigación del
      riesgo TRIBU-CR (plan §7.1 y §10).

      Va **antes** de T-612, que es su consumidor: al revés, T-612 los escribe a
      mano y T-613 se convierte en un refactor que hay que ir a buscar por el
      código. Es una función pura: dominio, con prueba.

      **Verificación:** una prueba tumba `pytest` si `comprobanteselectronicos.go.cr`
      aparece escrito fuera de ese módulo. Mismo patrón que `test_error_codes.py`.

- [ ] **T-612** Comprobar que las credenciales del ambiente sirven, **sin emitir
      nada**. RF-31.

      Es la única comprobación que no produce un documento, y sin ella la
      primera noticia de que la contraseña está mal llega el día que hay que
      facturar.

      **Verificación:** adaptador tras puerto, con doble en las pruebas y **tres
      casos distinguibles**: credenciales buenas, malas, e IdP inalcanzable. El
      tercero **no** puede reportarse como el segundo (RF-31). Tiempo de espera
      explícito, como el adaptador de CABYS. Más una comprobación en vivo
      anotada, como se hizo con T-502.

### El resto de la preparación

- [ ] **T-607** Consulta de actividad económica contra
      `GET /fe/ae?identificacion=` desde Configuración. RF-25.

      **Verificación:** el 404 de Hacienda viene **con un mensaje en inglés**
      (plan §6.1). Mostrarlo tal cual viola RN-30, así que se traduce a código y
      la frase se arma en el POS.
- [ ] **T-608** Administración de sucursales y terminales: ABM con los límites
      del plan (`max_sucursales`, `max_terminales`), y una sucursal con ventas
      **se desactiva, no se borra** —RN-7 aplicada acá—. RF-26.

      **Verificación:** crear una sucursal de más responde `plan_limit_reached`
      con su cuenta, como ya hace `domain/limits.py` desde T-309.

- [ ] **T-608b** Los códigos de 3 y 5 dígitos como **objeto de valor**, con su
      UNIQUE por compañía. RN-15. Es dominio: `Barcode` es el precedente.

      **Verificación:** «1» se guarda como «001» y «abc» no se guarda.

- [ ] **T-616** Arranque del consecutivo: la oficina y la última secuencia **por
      tipo de comprobante**, para el negocio que ya venía facturando con otro
      sistema. RF-32, RN-36 a RN-38.

      No es un número sino uno por tipo: las facturas llevan su serie y los
      tiquetes la suya, y un negocio que emitió 4 200 facturas y 15 300 tiquetes
      tiene que poder decir las dos.

      **Verificación:** el valor **solo sube**. Bajarlo significa volver a
      emitir números ya usados —rechazo seguro— así que se rechaza y queda en
      bitácora el intento.
- [ ] **T-609** Comprobar que el PIN **y la contraseña de ATV** no aparecen en
      respuestas, ni en bitácora, ni en trazas de error. Buscarlos a propósito.

      Va como prueba y no como revisión a mano, por lo mismo que el resto de los
      guardianes: una comprobación que hay que acordarse de repetir no protege
      nada. Lo que se busca es el valor literal en el cuerpo de cada respuesta
      del API, en `audit_log` y en el texto de las excepciones.

- [ ] **T-609b** La mitad positiva de la bitácora: **se registra que se usaron**,
      nunca su contenido (plan §7.1). Hoy el único uso es T-612.

- [ ] **T-615** El simulado responde los seis endpoints de FE con contrato
      idéntico, incluida **la negativa** a devolver el archivo, el PIN y la
      contraseña.

      Sin esto la fase no tiene ninguna prueba de flujo: la suite de punta a
      punta corre con `POS_MOCK=1`. Es el agujero que en F5 hizo que el simulado
      reembolsara cero durante dos días.

- [ ] **T-617** `clients.identification_type` con la lista de Hacienda
      (01/02/03/04). Hoy `clients` tiene `identification` y `email` pero **no el
      tipo**, y el XML lo exige para el receptor. Está en spec §5.4 desde el
      principio y nunca tuvo tarea.

      Barato ahora; en F7 obliga a migrar una tabla con los clientes de todos.
      **Verificación:** un cliente nuevo no se guarda sin tipo, y los existentes
      quedan en el que diga su cédula por longitud.

- [ ] **T-618** `FE_CRYPTO_KEY` en el compose, en `.env.example` y en el README
      de despliegue. RNF-5.

      **Verificación:** el arranque **falla** si no está o no mide 32 bytes
      —enterarse al firmar es tarde—, y una prueba comprueba que la llave no
      aparece en ningún volcado de `company_dump`.

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

## F7 · Emisión

Bloqueada hasta decidir la ruta: implementación directa o proveedor autorizado
(plan §7.2). Lo que se construya en F5 y F6 sirve para las dos.

En `docs/hacienda/costa-rica/` están los esquemas XSD 4.4, comprobantes reales
de ejemplo y la normativa de PIN y llaves. La ruta directa deja de depender de
deducir el formato.

- [ ] **T-701** Decidir la ruta.
- [ ] **T-702** Leer los XSD 4.4 y los 9 comprobantes de ejemplo, y contrastar
      el modelo de datos de F5/F6 contra los campos obligatorios reales. Es lo
      que dice si falta algo antes de escribir código. **Incluye comprobar
      RN-34**: que el contador de cinco dimensiones cubre lo que el XSD exige.
- [ ] **T-703** Definir la interfaz `EmisorFE` y dejar la implementación detrás.

### El recorrido, que no depende de la ruta

- [ ] **T-704** Contador de consecutivo con las **cinco** dimensiones
      `(compañía, sucursal, terminal, tipo, ambiente)` y bloqueo de fila. RN-34.

      Con menos, la serie nace con huecos: un tiquete, una factura y otro
      tiquete dan tiquetes 1, 3, 5 y facturas 2, 4. **Se confirma en la misma
      transacción que el documento** —el `UnitOfWork` que ya existe—, o una venta
      que falla después deja el número consumido. Es el defecto 1 otra vez.

      **Verificación:** una venta que falla por stock no consume número; dos
      cajas de la misma terminal no repiten.

- [ ] **T-705** La clave de 50 dígitos, con la **situación** decidida al vender
      (RN-43). La clave se imprime y se entrega, así que no se puede diferir.

      La contingencia es un **modo del negocio**, no una corazonada por venta: se
      entra por el estado de las transmisiones recientes y se sale cuando
      Hacienda responde. Emitir en contingencia con Hacienda arriba es causa de
      rechazo.

- [ ] **T-706** `sale_number` deja de venir del navegador. Hoy lo fabrica
      `cart.ts` con `yyyyMMddHHmmss` y el **reloj del cliente**: dos cajas
      cobrando en el mismo segundo chocan y una venta se rechaza en la cara del
      cliente. Decidir si pasa a ser el consecutivo o convive con él.

- [ ] **T-707** Estados del comprobante en la pantalla de facturas: numerado,
      firmado, enviado, aceptado, rechazado, reintentando, detenido. RF-33,
      RN-39.

- [ ] **T-708** Consulta del veredicto con su cadencia propia —10 s → 30 s → 1 →
      2 → 5 min—, distinta de la del reenvío. RN-40.

      **El trabajador corre fuera de una petición**, así que cada documento va
      dentro de un `with compania(cid)`: sin eso la primera lectura lanza
      `SinCompania` y la cola no avanza nunca.

- [ ] **T-709** Reenvío con espera creciente —5 → 15 → 30 min → … → 72 h— y
      **solo para fallas transitorias**. RN-41.

      Un rechazo es una respuesta y se detiene. Un certificado vencido o unas
      credenciales rotadas se detienen **en el primer intento**: reintentar tres
      días para llegar a la misma conclusión es demorar el aviso.

- [ ] **T-710** Lo **detenido** se ve y se puede reintentar a mano. RF-35, RF-36,
      RN-42. Agotar los reintentos no es rendirse: el plazo de contingencia sigue
      corriendo y el documento sigue siendo transmitible.

- [ ] **T-711** **Alarma de antigüedad de la cola.** Es lo único que avisa antes
      de que se acabe el plazo de contingencia —unos 8 días hábiles, y Hacienda
      rechaza pasados los 30 días— y lo que hace visible un Vault sellado, un
      disco lleno o un certificado que venció el sábado.

- [ ] **T-712** Archivo: el XML firmado **tal como se envió, byte por byte**, y
      la respuesta de Hacienda. Cinco años, los dos, y descargables. RF-34,
      RN-44.

      **Verificación:** lo descargado es idéntico a lo enviado —no regenerado—;
      la firma cubre esos bytes y regenerarlo da otra firma.

- [ ] **T-713** La puerta dura de la certificación: producción **no se habilita**
      sin una factura, un tiquete y una nota de crédito **aceptados** en pruebas.
      RN-46.

      Entra acá y no en F6 porque acá es donde por fin hay documentos que contar.
      En F6 el mismo candado habría nacido cerrado y sin forma de comprobar que
      abre.

      **Verificación:** con dos de los tres aceptados no habilita y **dice cuál
      falta**; «no se puede todavía» sin decir qué falta es lo que convierte una
      regla en un misterio. Se cuentan **aceptados**, no enviados.

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

- [ ] **T-1003b** *(salió de T-1004)* **RN-49 dice que la navegación esconde el
      módulo que el plan no incluye, y el código hace lo contrario a propósito.**

      `navigation.ts` ya tenía la regla escrita para los roles: lo que no se
      puede abrir **se muestra con candado, no desaparece**, porque esconderlo
      hizo creer a un cajero que el sistema no tenía inventario. Para un módulo
      vale lo mismo y una razón más: un «Contabilidad 🔒» en el menú es lo único
      que le dice al dueño que el producto la tiene, y es gratis. Escondiéndolo,
      lo que se quiere vender es invisible justo para quien lo compraría.

      Se implementó con candado. **Falta decidir si RN-49 se corrige** —la
      frase «la navegación del POS lo esconde»— o si se mantiene y se cambia el
      código. Lo demás de RN-49 no está en discusión: el 403 del servidor es
      igual en los dos casos.

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

- [ ] **T-1005** Migración `009-compras.sql` (plan §12.2) y sus modelos:
      `suppliers`, `supplier_payments`, las columnas de `stock_entries` y
      `stock_entry_details`, y `products.cost`. `company_dump.py`: las dos
      tablas viajan. RN-52, RN-54.

      **Verificación:** `test_esquema.py`; `test_respaldo_compania.py` exporta
      y restaura una compañía con proveedores y abonos y cuenta lo mismo de
      los dos lados.

### Dominio

- [ ] **T-1006** `domain/purchases.py` con la tabla de casos de plan §12.3:
      `weighted_average_cost`, `purchase_totals`, `remaining_balance`,
      `apply_payment`, `aging_bucket`. RN-53, RN-54, RN-55.

      **Verificación:** `pytest tests/domain/test_purchases.py` con los casos
      numéricos del plan —10 a 100 + 10 a 120 → 110; existencia −3 + 10 a 50 →
      50; 1 001 sobre 1 000 → `PaymentExceedsBalance`—; cobertura 100 %.

### Backend

- [ ] **T-1007** Proveedores: `SupplierRepository` y las rutas
      `GET/POST/PUT /suppliers`; se desactivan, no se borran, y comprarle a
      uno inactivo responde `supplier_inactive`. RF-41.

      **Verificación:** `test_aislamiento.py` con las tres rutas; la compra a
      un proveedor inactivo responde el código.

- [ ] **T-1008** El lector de XML (`lib/server/import/hacienda.ts`) extrae
      además `Emisor` (tipo, número, nombre), `Clave`, `NumeroConsecutivo`,
      `FechaEmision`, `CondicionVenta` con `PlazoCredito`, y por línea
      `Impuesto/Tarifa` y `Impuesto/Monto`. RF-42, RN-53.

      **Verificación:** los comprobantes de ejemplo de `docs/hacienda/`
      producen proveedor, condición y tarifa por línea; el invariante 79 800
      sigue igual en `test_characterization.py`.

- [ ] **T-1009** `RegisterPurchase`: aplica el stock como hoy, actualiza
      `products.cost` con el promedio, calcula `due_date` desde la condición,
      y de contado registra el abono por el total en el mismo acto. La factura
      duplicada pasa a ser **por proveedor** (`duplicate_supplier_document`).
      RN-52, RN-54, RN-57.

      **Verificación:** compra a crédito de 10 u a 120 sobre 10 u a 100 deja
      `products.cost` en 110, el saldo igual al total y `due_date` = fecha +
      plazo; repetir el mismo documento del mismo proveedor responde el
      código; el mismo número de **otro** proveedor entra.

- [ ] **T-1010** `PaySupplier`: comprueba el saldo (`payment_exceeds_balance`);
      en efectivo exige turno abierto en la terminal de la sesión
      (`cash_session_required`) y escribe el `cash_movements` de salida
      **antes** de guardar el abono. RN-55, RN-56, RF-44.

      **Verificación:** abono en efectivo con caja abierta → el efectivo
      esperado del arqueo baja exactamente ese monto; sin caja → código; abono
      mayor al saldo → código y nada escrito.

- [ ] **T-1011** `VoidPurchase`: solo sin abonos (`purchase_has_payments`),
      revierte el stock como la anulación de hoy, marca `anulada` y escribe en
      bitácora. **No toca `products.cost`**, y la pantalla lo dice. RF-46,
      RN-57.

      **Verificación:** anular con abonos → código; sin abonos → el stock
      vuelve, hay fila en `audit_log` y `products.cost` es el mismo de antes.

- [ ] **T-1012** Cuentas por pagar y reporte: `GET /payables` (saldo por compra
      y por proveedor, antigüedad) y `GET /reports/purchases` (base e impuesto
      **por tarifa**). RF-44, RF-45.

      **Verificación:** con una compra al 13 % y otra al 1 %, el reporte da dos
      bases y dos impuestos separados; una compra vencida hace 45 días cae en
      31–60.

### Frontend

- [ ] **T-1013** La pantalla de entradas gana proveedor, documento, condición y
      tarifa por línea, con el aviso de RN-53 cuando la del documento difiere
      de la del producto, y conserva la vista previa (§8, regla 6). RF-42,
      RF-43.

      **Verificación:** punta a punta: cargar un XML de ejemplo, ver el
      proveedor marcado «nuevo», la tarifa por línea y el aviso en la línea que
      difiere; confirmar; el stock sube y el proveedor existe.

- [ ] **T-1014** `/compras/proveedores` y `/compras/cuentas-por-pagar`: saldos,
      antigüedad y abonar con método y referencia. RF-41, RF-44.

      **Verificación:** punta a punta: abonar en efectivo con la caja abierta y
      ver el movimiento de salida en `/caja` con el motivo armado.

- [ ] **T-1015** Simulado y catálogos: los nueve endpoints con contrato
      idéntico, proveedores y una compra a crédito en el seed,
      `messages/es/purchases.json` **declarado en
      `project.inlang/settings.json`**, y los cinco códigos de compras en
      `API_CODES` y en `errors.json`.

      `module_not_in_plan` ya está —entró con T-1002, porque
      `messages.test.ts` compara las dos listas y no se podía diferir—.

      **Verificación:** `npm test` (`loose-text`, `catalogs` y
      `messages.test.ts` comparan las listas de códigos); `npm run check` en
      0/0.

### Verificación — sin esto la fase no está terminada

- [ ] **T-1016** Punta a punta con el navegador, en una compañía que la prueba
      da de alta: XML de proveedor → compra a crédito → el reporte por tarifa
      muestra su IVA → abono en efectivo → el arqueo cuadra → una segunda
      compra sin abonos se anula. Y en la compañía sin el módulo, el menú no
      lo muestra y el `POST` responde el código.

      **Verificación:** la prueba de Playwright pasa contra el simulado y, a
      mano, contra el stack real; `pytest`, `npm test` y `npm run check` en
      verde.

---

## F11 · Contabilidad

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

- [ ] **T-1101** Migración `010-contabilidad.sql` (plan §13.2) y sus modelos:
      `accounts`, `account_mappings`, `accounting_periods`, `journal_entries`,
      `journal_lines` y `sale_details.unit_cost`. `company_dump.py`: las cinco
      viajan. RN-58, RN-61, RN-63.

      **Verificación:** `test_esquema.py`; exportar y restaurar una compañía
      con un libro deja el mismo balance de comprobación.

### Dominio

- [ ] **T-1102** `domain/ledger.py`: `JournalEntry` que **no se construye
      desbalanceado**; `post_sale`, `post_return`, `post_cash_close`,
      `post_cash_movement`, `post_purchase`, `post_supplier_payment`;
      `assert_open`. La tabla de casos de plan §13.3, con las cifras de los
      invariantes. RN-58, RN-59, RN-62.

      **Verificación:** la venta 3 × 1 450 con costo 900 da el asiento de
      §13.3 —7 615,50 por lado—; construir uno desbalanceado lanza
      `EntryNotBalanced`; un método de pago sin cuenta cae en por clasificar;
      el cierre 53 000 contra 53 277,00 asienta un faltante de 277,00;
      cobertura 100 %.

- [ ] **T-1103** Reportes en el dominio: `trial_balance`, `income_statement`,
      `balance_sheet`, `vat_draft`. RF-53, RF-54, RN-65.

      **Verificación:** con los asientos de la tabla, activo = pasivo +
      patrimonio + resultado; el `vat_draft` del ejemplo da saldo a favor de
      12 434,50 (565,50 − 13 000).

### Backend

- [ ] **T-1104** `sales.payment_method` deja de ser texto libre: un conjunto
      cerrado de valores admitidos —los que hoy existen, **sin renombrar lo
      guardado**— sobre el que se define el mapeo; un valor fuera del conjunto
      se rechaza al vender.

      **Verificación:** `POST /sales` con un método desconocido responde
      código; los reportes de métodos de pago dan lo mismo que antes.

- [ ] **T-1105** Puerto `Ledger` con adaptador nulo y adaptador SQLAlchemy en
      **la misma sesión**; enganche en `RegisterSale`, `RegisterReturn`,
      `CloseCashSession`, movimientos de caja, `RegisterPurchase` y
      `PaySupplier`. RN-59, RF-50.

      **Verificación:** con el módulo apagado, `test_characterization.py` da
      las mismas cifras; con el módulo activo, una venta deja un
      `journal_entries` con `source_type = 'sale'` y el índice único impide el
      segundo; sin la cuenta `cash` en el mapeo, la línea va a 1.9.99 **y la
      venta se confirma**.

- [ ] **T-1106** `unit_cost` congelado en `sale_details` al vender, desde
      `products.cost`; `NULL` si el producto no tiene costo. RN-63.

      **Verificación:** vender, comprar más caro, y la línea vendida conserva
      su costo; `post_sale` de una línea sin costo no asienta el par costo /
      inventario.

- [ ] **T-1107** `ActivateAccounting`: la plantilla de plan §13.8, el mapeo por
      omisión completo, el periodo de la fecha de inicio y el asiento de
      apertura; `accounting` en `settings`. RF-47, RN-60.

      **Verificación:** activar deja todas las cuentas de sistema y **ninguna
      fila del mapeo falta**; una apertura desbalanceada responde
      `invalid_opening_balance`; activar dos veces responde código.

- [ ] **T-1108** Catálogo y mapeo: rutas, `account_is_system`,
      `account_in_use`, y `Reclassify`. RF-48, RF-49, RN-64.

      **Verificación:** borrar 1.1.01 → código; borrar una cuenta nueva sin
      movimientos → se va; reclasificar deja 1.9.99 en cero con un asiento
      `adjustment` que referencia al original.

- [ ] **T-1109** Asientos manuales y de ajuste; periodos y `ClosePeriod` con
      confirmación y bitácora; `period_closed`, `period_not_closeable`. RF-51,
      RF-52, RN-61.

      **Verificación:** cerrar agosto con julio abierto → código; cerrar julio
      y luego un manual con fecha en julio → `period_closed`; `audit_log`
      tiene el cierre con quién y cuándo.

- [ ] **T-1110** Rutas de los cinco reportes y del D-104, con `format=csv`.
      RF-53, RF-54.

      **Verificación:** el CSV del diario abre y suma lo mismo que la pantalla;
      el D-104 del mes da el débito por tarifa **igual** al desglose de ventas
      por tarifa (RF-21) y el crédito **igual** al reporte de compras (RF-45).

### Frontend

- [ ] **T-1111** Pantallas de `/contabilidad` (plan §13.4): el resumen con por
      clasificar en rojo, activación, cuentas, mapeo, asientos, periodos,
      reportes e IVA. Quién las ve depende de la decisión del rol contador.

      **Verificación:** punta a punta: activar, vender, abrir el asiento desde
      la venta, cerrar el mes con el resumen a la vista.

- [ ] **T-1112** Simulado y catálogos: doce endpoints con contrato idéntico, un
      libro en el seed, `messages/es/accounting.json` declarado, y los siete
      códigos en los cuatro lugares.

      **Verificación:** `npm test`; `npm run check` en 0/0.

### Verificación — sin esto la fase no está terminada

- [ ] **T-1113** Punta a punta en una compañía que la prueba da de alta:
      activar contabilidad, vender 3 × 1 450 en efectivo y ver el asiento que
      balancea, comprar a crédito, abonar, cerrar caja con faltante, cerrar el
      mes, intentar un asiento en el mes cerrado → código; el D-104 del mes
      cuadra con los dos reportes.

      **Verificación:** Playwright contra el simulado y, a mano, contra el
      stack real; `pytest`, `npm test` y `npm run check` en verde.

---

## F12 · Planilla

> **Qué deja.** Nómina costarricense: empleados y contratos, tasas con
> vigencia y país, corridas que **congelan** lo que usaron, horas extra,
> incapacidades, vacaciones, aguinaldo, liquidación, boleta, archivo para la
> CCSS, resumen de renta retenida y el asiento de la corrida (RN-66 a RN-75,
> RF-55 a RF-64). Plan §14.
>
> **De qué depende.** De F11 **solo para el asiento** (T-1206 con el `Ledger`);
> todo lo demás no. De **T-922**, en Transversal: la boleta es la cuarta
> plantilla de documento y hoy el PDF del backend no se cuenta.
>
> **Lo que no se supone.** Las cifras de la CCSS, los tramos de renta y el
> formato del archivo del SICERE **se leen de la fuente el día que se
> siembran** (plan §14.8), no de este documento ni del recuerdo de nadie.

**Costes medidos antes de empezar** —plan §14.7—:

- `test_esquema.py`: once tablas (`011`).
- `test_tenancy.py`: cuatro tablas globales **sin** `TenantMixin`, declaradas
  como excepción explícita como `cabys_cache`, o el guardián tumba `pytest`.
- `test_aislamiento.py`: unas quince rutas y una bajo `/support`.
  `test_error_codes.py`: nueve códigos. `company_dump.py`: siete viajan,
  cuatro no.
- `domain/payroll.py` supera a `ledger.py`; las pruebas usan un juego de tasas
  **inventado**, para probar la aritmética y no una cifra que vence.
- La boleta como cuarta plantilla, en los tres idiomas del documento.

### Base de datos

- [ ] **T-1201** Migración `011-planilla.sql` (plan §14.2) y sus modelos: las
      cuatro tablas globales por país y las siete de la compañía;
      `test_tenancy.py` con las excepciones; `company_dump.py` con la
      clasificación. RN-67, RN-72.

      **Verificación:** `test_esquema.py`; una consulta a `payroll_rates` sin
      compañía en la sesión funciona y una a `employees` falla cerrado;
      exportar y restaurar una compañía con corridas cuenta lo mismo.

### Dominio

- [ ] **T-1202** `domain/payroll.py`, primera mitad: `rates_at`, `gross_pay`
      (horas extra, feriados), `employee_deductions`, `employer_charges`,
      `projected_monthly`, `income_tax`. RN-66, RN-67, RN-73.

      **Verificación:** la tabla de casos de plan §14.3 con tasas inventadas;
      `rates_at` a una fecha sin `ivm` lanza `RatesMissing`; la quincena de
      600 000 es 300 000; cobertura 100 %.

- [ ] **T-1203** Segunda mitad: `aguinaldo`, `vacation_accrual`, `notice_days`,
      `severance_days`, `settlement`, `sick_leave_split`. RN-69, RN-70, RN-71.

      **Verificación:** doce meses de 500 000 → aguinaldo 500 000 sin rubros
      de CCSS ni renta; 12 años de antigüedad → los días de 8; renuncia → sin
      preaviso ni cesantía y con proporcionales; 350 días trabajados → 14 de
      vacaciones.

### Backend

- [ ] **T-1204** Siembra de tasas por país: `seed_payroll_rates.py` con fuente,
      `valid_from` y `verified_at`, **leyendo las cifras de la fuente el día
      de correrlo**; `GET /payroll/rates?on=`; `PUT /support/payroll/rates`,
      que inserta una fila con vigencia y nunca edita la vigente. RF-56,
      RN-67.

      **Verificación:** la prueba de la siembra suma los rubros obreros y
      patronales y los compara con los totales publicados ese día, que guarda
      con su fecha; intentar cambiar una fila vigente → rechazado; con
      `verified_at` de más de seis meses, `GET` lo marca y la pantalla avisa.

- [ ] **T-1205** Empleados y contratos: rutas, enlace opcional a `users`, baja
      con fecha y causa (`employee_terminated`), y un aumento que cierra el
      contrato y abre otro. RF-55, RN-72.

      **Verificación:** `test_aislamiento.py`; dar de baja crea la corrida de
      liquidación en borrador; una novedad para un empleado dado de baja
      responde el código.

- [ ] **T-1206** Corridas: `CreateRun`, novedades (`novelty_outside_period`),
      `CalculateRun` que escribe líneas y rubros —el congelamiento—,
      `ApproveRun`, `PayRun` con fecha del servidor, bitácora y `Ledger.post`
      si contabilidad está activa. RF-57, RN-66, RN-68, RN-75.

      **Verificación:** pagar; insertar una tasa nueva con `valid_from` de
      ayer; `GET` de la corrida pagada → los rubros **no** cambian; una corrida
      nueva → sí; editar la pagada → `run_already_paid`; con contabilidad
      activa, `journal_entry_id` apunta a un asiento que balancea entre
      6.1.01, 6.1.02, 2.1.03, 2.1.04, 2.1.05 y 2.1.06.

- [ ] **T-1207** Boleta: la cuarta plantilla de documento, en el idioma del
      documento (RN-29), armada **desde los rubros congelados**. RF-58, RN-66.

      **Verificación:** la boleta de una corrida pagada antes de un cambio de
      tasa muestra la tasa vieja; T-922 cuenta cuatro documentos.

- [ ] **T-1208** Aguinaldo como corrida `aguinaldo`: suma lo devengado de las
      pagadas del 1 de diciembre al 30 de noviembre y divide entre doce, sin
      rubros de CCSS ni renta. RF-59, RN-69.

      **Verificación:** doce corridas de 500 000 → 500 000 exacto; los rubros
      de la línea son todos `earning`.

- [ ] **T-1209** Vacaciones: acumulación al pagar cada corrida, disfrute como
      novedad, saldo por empleado (`vacation_balance_exceeded`). RF-60, RN-70.

      **Verificación:** 350 días trabajados → 14; disfrutar 20 → código; el
      saldo es la suma de `vacation_movements`, no una columna.

- [ ] **T-1210** Liquidación: `TerminateEmployee` deja una corrida `settlement`
      con preaviso, cesantía, vacaciones y aguinaldo proporcionales según la
      causa; `settlement_requires_termination`. RF-61, RN-71.

      **Verificación:** los tres casos de `settlement` (renuncia, despido sin
      causa, con causa) dan los rubros que dice la tabla; sin baja → código.

- [ ] **T-1211** Archivo para la CCSS y resumen de renta retenida. **Empieza
      por leer la especificación oficial del SICERE** y guardarla en
      `docs/ccss/`, como los XSD en `docs/hacienda/`; el archivo sale de un
      adaptador `CcssFileWriter` con prueba contra un ejemplo real. RF-62.

      **Verificación:** el archivo del mes valida contra el ejemplo del
      material; la renta retenida del mes es la suma de los rubros
      `income_tax` de las corridas pagadas del mes.

- [ ] **T-1212** Corrida de ajuste sobre una pagada, que la referencia y no la
      toca. RF-63, RN-68.

      **Verificación:** el ajuste tiene `adjusts_run_id`; la boleta de la
      original no cambia; el asiento del ajuste es solo la diferencia.

### Frontend

- [ ] **T-1213** Pantallas de `/planilla` (plan §14.4), con el aviso de tasas
      viejas en el resumen. RF-55 a RF-63.

      **Verificación:** punta a punta: alta de empleado, contrato, corrida,
      novedad de 4 horas extra, calcular, aprobar, pagar, imprimir la boleta.

- [ ] **T-1214** Simulado y catálogos: quince endpoints con contrato idéntico,
      dos empleados y un juego de tasas en el seed, `messages/es/payroll.json`
      declarado, y los nueve códigos en los cuatro lugares.

      **Verificación:** `npm test`; `npm run check` en 0/0.

### Verificación — sin esto la fase no está terminada

- [ ] **T-1215** Punta a punta en una compañía que la prueba da de alta: dos
      empleados (mensual y quincenal), una corrida pagada; una tasa nueva con
      vigencia futura; reimprimir → igual; la corrida siguiente → distinta;
      aguinaldo; baja con liquidación; archivo de la CCSS; y con contabilidad
      activa, el asiento.

      **Verificación:** Playwright contra el simulado y, a mano, contra el
      stack real; `pytest`, `npm test` y `npm run check` en verde.

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

- [ ] **T-916** *(antes de T-1001)* Reabrir T-913 si se hace el ABM de
      sucursales y terminales (T-608): son de las tablas con columnas en
      español. Incluye subir `FORMATO` en `company_dump.py` y darle un lector
      de compatibilidad para los respaldos anteriores, sin el cual el rename
      los deja inservibles en silencio.

      **Volvió a apuntar a F6 el 2026-09-12, después de mirarla de cerca.** Con
      el reordenamiento pasó un día a ser la puerta de T-1001, con el argumento
      de que el rename viaja en la primera migración que se escriba. Es verdad
      a medias: lo que decide no es cuál migración va primero sino **qué
      trabajo abre esos archivos**, y ese es T-608 —el ABM de sucursales y
      terminales—, que sigue en F6. F10 no las toca.

      Renombrar solo `plans` en la 008 sería lo peor de las dos opciones: se
      paga parte del costo, se rompen los respaldos ya entregados y la mezcla
      queda igual en las otras cuatro tablas.
- [ ] **T-917** El guardián de texto suelto **no lee el `<script>` de un
      `.svelte`**: `revisar()` recorre solo el marcado y `revisarTs()` solo abre
      archivos `.ts`. La consecuencia es que los sumideros de `toasts.*` son casi
      letra muerta —11 de los 13 sitios que los llaman viven en `.svelte`—, así
      que un `toasts.error('Producto agotado')` dentro de un `<script>` pasa sin
      que nadie chille. Hoy no hay ninguno, y por eso no bloquea; el arreglo es
      extraer el contenido del `<script>` y pasarlo por `revisarTs`.
- [ ] **T-922** **El PDF del backend es un cuarto documento y nadie lo cuenta.**
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
