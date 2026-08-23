# VentaSys — contexto para Claude Code

Punto de venta migrado de C#/WinForms a SvelteKit, sobre FastAPI + MySQL en
Docker. Interfaz en español (usted), con inglés y portugués por venir. Moneda:
configurable; por omisión colones.
IVA 13 %.

## Al empezar una sesión

**Leé `.specify/`.** Son cuatro documentos y cada hecho vive en uno solo:

| Archivo | Qué guarda |
|---|---|
| `spec.md` | Qué se construye y por qué. Requisitos numerados (RF, RN, RNF). |
| `plan.md` | Cómo. Arquitectura, modelo de datos, fases, riesgos del plan. |
| `task.md` | El trabajo pendiente, en orden y con su verificación. |
| `progress.json` | Lo que ya pasó: decisiones con su porqué, defectos corregidos, cifras de referencia y bitácora. |

Los tres primeros miran hacia adelante; `progress.json` mira hacia atrás. Ahí
está el giro grande del proyecto: VentaSys pasa de ser un POS para un negocio a
un producto multiempresa que se vende por suscripción.

Si dos se contradicen sobre qué falta, manda `task.md`.

## Al terminar una sesión

**Actualizá `.specify/progress.json`** si hubo cambios que importen:

- `actualizado` con la fecha de hoy.
- Una entrada nueva en `sesiones` con lo que se hizo.
- `decisiones` si se decidió algo con consecuencias.
- `defectos_corregidos` si se arregló un defecto real.
- `invariantes_verificados` si cambia alguna cifra de referencia.

Y **marcá en `.specify/task.md`** lo que quedó terminado, agregando lo que haya
aparecido. Los pendientes viven ahí, no en `progress.json`.

Es un registro de trabajo, no un diario: anotá lo que le sirva a quien retome,
no cada archivo que se tocó.

## Qué se hace sin preguntar y qué no

Editar no se pregunta: crear archivos, cambiarlos, reescribirlos. Hay dos
excepciones, y las dos son del mismo tipo —lo que no se puede deshacer leyendo
el diff—.

**Borrar se consulta.** Archivos, ramas, volúmenes de Docker, filas de la base.
`.claude/settings.json` lo respalda con una lista de patrones (`rm`, `git clean`,
`git reset`, `docker compose down`, `docker volume rm`…), pero esa lista es un
cinturón, no un muro: solo reconoce las formas que alguien anotó. Un borrado
escrito de otra manera —dentro de un script, en un `docker compose exec … mysql`,
en un `python -c`— la esquiva sin esfuerzo. Lo que garantiza el aviso es la
regla, no el patrón.

**Una mejora que no está en `.specify/` se consulta.** Si aparece algo que
conviene hacer y no figura en `spec.md`, `plan.md` ni `task.md`, se plantea
antes de implementarlo: primero porque quizá ya se descartó por una razón que no
está a la vista, y segundo porque lo que se construye sin pasar por los
documentos queda sin requisito que lo justifique y sin tarea que lo verifique.

Consultar no es frenarse. Lo que sí está en los documentos se sigue haciendo
mientras tanto, y la pregunta se hace cuando toca decidir, no al empezar.

## Mapa

```
.specify/            spec.md, plan.md, task.md, progress.json
frontend/            el POS (SvelteKit 2, Svelte 5 runes, Tailwind 4)
backend/             la API (FastAPI + MySQL). Se levanta sola con su compose.
docs/                ejemplos de factura y material de Hacienda (XSD 4.4)
deploy/              despliegue viejo, en desuso. NO se versiona.
```

`backend/` es la aplicación completa, no un parche: se levanta con
`docker compose up` desde su propia carpeta. `deploy/` existía solo porque antes
había que ensamblar el backend a partir de un patch; ya no hace falta y se puede
borrar en cuanto se migre su `.env` y su volumen de datos.

## Levantar

```bash
cd backend && docker compose up -d --build    # backend + MySQL en :8001

# Base nueva: primero la compañía, después los datos. En ese orden.
docker compose exec fastapi python bootstrap.py \
    --nombre "Mi negocio" --email admin@ventasys.cr --password admin123
python seed.py --ventas 35                    # datos de prueba

# Y la cuenta de soporte, que administra la plataforma (F3). Sin compañía.
docker compose exec fastapi python bootstrap.py --soporte \
    --email soporte@ventasys.cr --password soporte123

cd frontend && npm run dev                    # POS en :5173
```

`bootstrap.py` da de alta una compañía con su sucursal, su terminal y su primer
administrador. Es el único guion que habla con la base directamente, y tiene que
serlo: no hay sesión sin membresía ni membresía sin compañía, así que la primera
no se puede crear por la API. Lo mismo con `--soporte`: no hay API que otorgue un
permiso que todavía nadie tiene. `seed.py` sí va por HTTP y necesita que la
compañía ya exista.

Desde F3 las compañías también se dan de alta **desde el panel** (`/admin`), con
el mismo código: `app/services/crud_company.py`.

Para desarrollar sin backend: `POS_MOCK=1` en `frontend/.env`. El modo simulado
tiene **dos** compañías: la primera con catálogo y ventas, la segunda vacía como
nace una recién dada de alta. El administrador pertenece a las dos y por eso ve
la pantalla de selección; los cajeros, a una sola, y entran directo.

## Reglas del proyecto

- **El dinero se calcula en el servidor**, releyendo los precios del backend.
  Toda aritmética monetaria pasa por `$lib/money.ts`, que redondea a 2 decimales
  en cada paso.
- **El idioma sale del token**, no del navegador. Lo resuelve el backend al emitir
  la sesión —lo de la persona, si no lo de la compañía, si no `es`— y viaja como
  `loc`. En el POS lo lee la estrategia `custom-session` de
  `hooks.server.ts`, y `paraglideMiddleware` lo guarda por petición
  (AsyncLocalStorage). La cookie `PARAGLIDE_LOCALE` es **el espejo para el
  navegador**, nunca la fuente: después de hidratar no hay token que leer porque
  la cookie de sesión es httpOnly. Cambiar de idioma significa emitir un token
  nuevo.
- **La moneda y el impuesto se configuran**, no se escriben en el código. Salen
  de `/configuracion` (tabla `settings`) vía `$lib/settings.ts`. En un `load` o
  una acción hay que leerlos con `loadSettings()` y pasar la tasa explícita a
  `computeTotals`: el estado de módulo de `money.ts` lo fija el layout al
  renderizar, y ahí todavía no corrió.
- **Una devolución usa la tasa de SU venta** (`tax / subtotal`), no la
  configurada hoy. Si el dueño cambia el IVA, lo que se reembolsa sigue siendo
  lo que se cobró.
- **La hora de las ventas la pone el backend**, nunca el cliente. El arqueo de
  caja depende de comparar marcas del mismo reloj.
- **Los permisos se aplican en el servidor** (`requireUser`, `requireAdmin`,
  `requireSoporte` en cada `load` y cada `action`). Esconder un botón no es
  control de acceso.
- **Soporte y el POS son dos aplicaciones en el mismo despliegue.** El panel vive
  en `/admin` (API: `/support`) y su sesión **no tiene compañía** (RN-4): su
  token no lleva `cid`, así que el filtro de `tenancy.py` le hace fallar cerrado
  cualquier consulta de negocio. Para ver los datos de un cliente tiene que
  *entrar como* esa compañía, y eso es **solo lectura** y queda en bitácora
  (RN-32). Las dos puertas se cierran en los dos sentidos y responden **403, no
  un redirect**: el token vale, lo que no vale es para esto.
- **Quien no paga deja de vender, no deja de entrar.** El estado de la
  suscripción se evalúa en **cada petición** —`domain/subscription.py`, contra la
  fecha de hoy (RN-31)— y el bloqueo de escritura vive en un solo sitio,
  `get_current_user`, con sus dos excepciones escritas y vigiladas
  (`tests/test_suscripcion.py`). No va en el token a propósito: ahí quedaría
  congelado hasta el siguiente login y desbloquearía tarde, justo cuando el
  cliente acaba de pagar.
- **El modo mock se mantiene sincronizado.** Un endpoint nuevo en FastAPI va
  también a `frontend/src/lib/server/mock/handler.ts`, con contrato idéntico.
- **Los colores salen de los tokens de `app.css`.** Hay tema claro y oscuro. El
  acento se puede cambiar desde Configuración: el tono oscuro y el color del
  texto se derivan en OKLab (`$lib/color.ts`), nunca se eligen a ojo.
- **Arquitectura limpia.** Las dependencias apuntan hacia adentro: `domain` no
  importa nada, `application` habla con puertos, `infrastructure` e `interfaces`
  son los adaptadores. Si para probar una regla hay que levantar la base, la
  regla está en la capa equivocada. Lo custodia el agente `architect`; el
  destino está en `.specify/plan.md` §1.2.
- **Ningún texto que ve una persona se escribe dentro de un componente.** Va al
  catálogo (`frontend/messages/es/<pantalla>.json`) y se usa con `m.<clave>()`.
  Lo custodia `src/lib/ui/loose-text.test.ts`, que lee el árbol de sintaxis de
  cada pantalla y de cada acción: una cadena suelta en el marcado, un
  `label="…"` literal o un `formError('frase')` tumban `npm test`. Vale también
  para las acciones, no solo para el marcado.
- **Cada función tiene su prueba.** En `domain/` y `application/` es
  obligatorio y la cobertura rompe la build (100 %). En adaptadores, prueba de
  integración; en la interfaz, flujos de punta a punta. Una función nueva de
  esas dos capas sin prueba está incompleta, no «pendiente».
- **El código va en inglés** —identificadores, archivos, tablas, columnas,
  rutas—, igual que el código heredado (`products`, `sales`, `company_id`).
  **La interfaz va en español, tratando de usted** —no voseo— y **la
  documentación también**. La interfaz se traduce (F8): ningún texto que ve una
  persona se escribe dentro de un componente, y **el backend no escribe texto
  para personas**: devuelve un código y los datos, y el POS arma la frase.
- **Un «no» es un código y sus datos, en las dos aplicaciones.** En el backend
  se construye con `api_error(status, code, **datos)` de
  `app/utils/api_errors.py` y en ningún otro lado: `tests/test_error_codes.py`
  lee el árbol de sintaxis y tumba `pytest` si aparece un `HTTPException(...)`
  suelto, un código que no está en `CODES` o uno que nadie levanta. En el POS,
  el dominio y la aplicación devuelven lo mismo y la frase se arma en
  `$lib/ui/messages.ts`, con un `switch` que termina en `never`. Las dos listas
  de códigos se comparan entre sí en `messages.test.ts`. Un código nuevo se
  agrega en cuatro lugares: `api_errors.py`, `API_CODES`, `messages/es/errors.json`
  y el simulado.
- Al terminar: `cd frontend && npm run check` en 0 errores y 0 advertencias,
  `npm test` y `cd backend && pytest` en verde.

## Git

- **El autor de los commits es el usuario, nunca Claude.** Sin línea
  `Co-Authored-By`, sin mención en el cuerpo, sin `--author`. Es su repositorio y
  su autoría; el trailer haría que GitHub muestre a Claude como coautor en todo
  el historial.
- **Identidad por repositorio, no global.** Acá va la cuenta personal
  (`jordanlaguna` / `jordanlaguna10@gmail.com`); la global de la máquina es la
  del trabajo y no se toca.
- El remoto lleva el usuario en la URL
  (`https://jordanlaguna@github.com/…`). Sin eso, git reutiliza el token del
  trabajo en silencio y GitHub responde `404 Repository not found` —no `403`—
  cuando el repositorio personal no le es visible.

## Trampas conocidas

- El puerto de la API es **8001**, no 8000 (el compose publica `"8001:80"`).
- `node build/index.js` **no lee el `.env`**: hace falta `--env-file=.env`.
- `ORIGIN` es obligatoria en producción o todo POST responde 403.
- Con `curl` contra el POS hay que mandar `-H "Origin: http://localhost:3000"`.
- El cliente `mysql` **negocia latin1** si nadie le dice otra cosa. Todo `.sql`
  con acentos empieza con `SET NAMES utf8mb4;` o «Compañía» entra a la base como
  «CompaÃ±Ã­a». Las tablas ya son utf8mb4; lo que falta es la conexión.
- La dependencia que fija la compañía (`payload_del_token`) es **asíncrona a
  propósito**. FastAPI corre las síncronas en otro hilo, con una copia del
  contexto, y un `ContextVar` fijado ahí no llega al endpoint. Volverla `def`
  hace que todo empiece a lanzar `SinCompania`.
- Después de un `commit`, SQLAlchemy **expira los objetos**: leer un atributo de
  una tabla de negocio dispara una relectura, y si el contexto ya no tiene
  compañía, falla. En los guiones hay que armar el resumen antes de confirmar.
- **Las pruebas de punta a punta ya no reutilizan un servidor que esté
  escuchando.** `reuseExistingServer` estaba en `!CI`, y un `npm run dev`
  olvidado en el 4173 hizo que la suite entera pasara en verde contra el código
  de horas antes. Si el puerto está ocupado, ahora falla y lo dice.
- **`Query.count()` no se filtra por compañía.** `db.query(Product).all()`
  devuelve las propias; `db.query(Product).count()` cuenta las de todas, porque
  `count()` envuelve la consulta en una subconsulta donde el criterio no entra.
  Se cuenta con `db.query(func.count(Modelo.id))`. Hay un guardián en
  `tests/test_tenancy.py` que tumba `pytest` si aparece uno sin filtro.
- **`npm run check` mientras corre `vite dev` se pelean por `.svelte-kit`.** Los
  dos ejecutan `svelte-kit sync` y en Windows la colisión sale como
  `EPERM, Permission denied: …\.svelte-kit\types\…\proxy+page.server.ts`. El
  servidor de desarrollo queda sirviendo **500 en todas las rutas** aunque el
  código esté bien —`npm run check` y las pruebas de punta a punta pasan, porque
  esas levantan su propio servidor—. Se arregla reiniciando `npm run dev`; el
  síntoma engaña porque parece que se rompió lo último que se tocó.
- **Un `vite dev` olvidado también reescribe la carpeta de Paraglide**, y el
  síntoma es peor. Cada servidor de desarrollo vigila `messages/` y recompila
  `src/lib/paraglide/` cuando un catálogo cambia; si además corre `npm run
  check`, los dos escriben la misma carpeta y `svelte-check` la lee a medio
  escribir. Salen **cientos de errores** —hasta 900, uno por mensaje— diciendo
  `Cannot find module './es.js'` o `File 'pt.js' is not a module`: ninguno tiene
  que ver con lo que se acaba de tocar. La pista es que **el segundo `npm run
  check` seguido da 0**. Antes de creerle a un muro de errores así, `Get-Process
  node` y contar cuántos hay: en agosto de 2026 había seis de este proyecto, del
  16 y el 22, y hacían que el primer `check` después de editar un catálogo
  mintiera siempre.
- **Las pruebas de integración del backend hablan con el contenedor, y la imagen
  hornea el código.** `docker-compose.test.yml` no monta `app/` como volumen, así
  que después de cambiar el backend hay que
  `docker compose -f docker-compose.test.yml up -d --build` o `pytest` seguirá
  probando el código de la última construcción. El síntoma engaña: la prueba
  nueva falla señalando lo que uno acaba de escribir.
- **El estado del modo simulado se guarda en `.data/mock-db.json`.** Un archivo
  de una versión anterior del seed sobrevive al cambio, así que al tocar el seed
  hay que subir `SEED_VERSION` en `mock/db.ts`; si no, la prueba de punta a punta
  falla señalando la pantalla, que es el único sitio donde no está el problema.
- **Un catálogo nuevo hay que declararlo en `project.inlang/settings.json`.** El
  `pathPattern` lista los archivos **uno por uno**. Uno que no esté ahí existe,
  se traduce a los tres idiomas, pasa las pruebas de paridad de `catalogs.test.ts`
  —tiene las mismas claves y los mismos parámetros— y **Paraglide no lo
  compila**: `m.mi_clave()` no existe. El síntoma son cientos de «Property
  'admin_x' does not exist» señalando las pantallas, que es el único sitio donde
  no está el problema. Hay una prueba que lo caza desde F3, en los dos sentidos
  (catálogo sin declarar y patrón sin archivo).
- **Una prueba de punta a punta que cambia el estado del demo se lo cambia a
  todas.** El simulado guarda su estado en `.data/mock-db.json` y una prueba que
  falla a mitad no restaura nada: suspenderle la suscripción a la compañía 1
  tumbó trece pruebas de otros archivos, todas señalando la pantalla de ventas.
  La salida no es restaurar mejor sino **no tocar lo que otros usan**: la prueba
  da de alta su propia compañía y juega con esa.
- El modelo y la migración tienen que decir lo **mismo**. Una instalación nueva
  crea el esquema con `create_all` y una vieja lo trae de la migración: si
  difieren, el mismo código se comporta distinto en cada una. En F3 apareció el
  caso al revés: `audit_log` tenía sus índices solo en la migración, así que la
  base de pruebas —hecha con `create_all`— no los tenía. Ahora los declara el
  modelo también.

## Agentes del proyecto

| Agente | Para qué |
|---|---|
| `pos-fullstack` | Implementar funcionalidad que cruza frontend y backend. |
| `pos-qa` | Verificar de punta a punta contra el stack real. |
| `pos-deploy` | Docker, variables de entorno, red, respaldos, diagnóstico. |
| `pos-auditor` | Revisar plata, stock, caja y permisos. Solo lee. |
| `architect` | Custodia las capas: dependencias hacia adentro, puertos, y que dominio y aplicación tengan prueba. Solo lee. |
| `spec-reviewer` | Revisa `.specify/spec.md`: verificable, sin CÓMO, sin contradicciones. Solo lee. |
| `plan-reviewer` | Revisa `.specify/plan.md` contra el spec y el código. Solo lee. |
| `task-reviewer` | Revisa `.specify/task.md`: nada sin tarea, nada sin verificación, y que lo marcado sea cierto. Solo lee. |

Los cuatro últimos revisan, no escriben. Conviene pasarles el documento antes de
empezar una fase y al cerrarla.
