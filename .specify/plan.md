# VentaSys — Plan técnico

> **Qué es este documento.** Cómo se construye lo que define
> [spec.md](spec.md). Las tareas concretas y su orden están en
> [task.md](task.md).
>
> Actualizado: 2026-09-11

---

## 1. Arquitectura

### 1.1 Despliegue

Sin cambios de fondo. Lo que ya existe funciona y la razón por la que existe
sigue siendo válida.

```
Navegador ──HTTPS/LAN──> SvelteKit (BFF) ──HTTP interna──> FastAPI ──> MySQL 8
             cookie httpOnly            Bearer JWT
```

El navegador **nunca** habla con FastAPI: el JWT vive en una cookie httpOnly, no
hay CORS que configurar y la IP del backend no se expone. Toda pantalla nueva
—incluido el panel de soporte— entra por el mismo camino.

### 1.2 Capas (spec §5.5)

Hoy el backend está organizado por tipo de archivo —`models/`, `router/`,
`schemas/`, `services/`— que es una convención de framework, no una
arquitectura: `crud_sale.py` mezcla la regla de negocio, la consulta SQL y el
manejo de errores HTTP en la misma función. Por eso no hay forma de probar el
cálculo de una venta sin levantar MySQL.

**Destino:**

```
backend/app/
├── domain/                 puro. No importa nada de fuera.
│   ├── entities/           Sale, Product, CashSession, StockEntry,
│   │                       Supplier, JournalEntry, Employee, PayrollRun (F10–F12)
│   ├── values/             Money, TaxRate, Barcode, Consecutive, RateSet
│   └── services/           reglas: totales, arqueo, validez de devolución,
│                           promedio ponderado, asiento por evento, planilla
├── application/
│   ├── use_cases/          CreateSale, CloseCashSession, RegisterStockEntry,
│                           RegisterPurchase, ClosePeriod, PayRun
│   └── ports/              SaleRepository, ProductRepository, Clock,
│                           CabysCatalog, PasswordHasher, TokenIssuer,
│                           Ledger, RateTable
├── infrastructure/
│   ├── persistence/        modelos SQLAlchemy + repositorios (implementan puertos)
│   ├── security/           jwt_handler, bcrypt
│   └── external/           cliente CABYS
└── interfaces/http/        routers FastAPI + DTOs Pydantic
```

```
frontend/src/lib/
├── domain/                 money, totals, reglas del carrito. Sin Svelte, sin fetch
├── application/            casos de uso que invocan load y actions
├── infrastructure/         cliente HTTP, backend simulado, lectores de XML y planilla
└── ui/                     componentes y stores
frontend/src/routes/        transporte delgado
```

**Qué gana esto, en concreto:**

- El cálculo de totales con impuesto por línea (§6.3) se prueba con una tabla de
  casos, sin base de datos ni servidor.
- El filtro por compañía (§3.3) es cosa de `infrastructure/persistence/`: los
  casos de uso no se enteran, y no hay dónde olvidarse de aplicarlo.
- El puerto `Clock` vuelve estructural la regla de que la hora la pone el
  servidor. Con `datetime.now()` esparcido por los servicios, esa regla depende
  de que nadie se equivoque; con un puerto, un caso de uso que quiera saltársela
  no compila la prueba.
- La emisión de comprobantes (§7.2) es un puerto `EmisorFE` con dos
  implementaciones posibles. La decisión directo-o-proveedor deja de bloquear.

**Cómo se llega sin romper nada.** No de un tirón. El orden es:

1. **Pruebas de caracterización primero.** Antes de mover una línea, fijar el
   comportamiento actual con los invariantes ya verificados de `progress.json`
   (venta 3×1450, arqueo 53 277,00, devolución 1638,50, entrada XML 79 800…).
   Son la red: si después de mover el código siguen dando igual, el movimiento
   fue correcto.
2. **Extraer el dominio**, que es puro y no rompe nada al salir.
3. **Definir los puertos y mover los casos de uso**, dejando los `crud_*`
   actuales como adaptadores hasta que queden vacíos.
4. **Los routers adelgazan** a traducir HTTP y llamar al caso de uso.

Lo custodia el agente `architect`, con búsquedas que fallan si alguna capa
importa de más.

### 1.3 Pruebas (RNF-6)

Las capas y las pruebas son la misma decisión: el motivo de separar el dominio
es poder ejecutarlo solo.

| Dónde | Herramienta | Qué se prueba |
|---|---|---|
| `backend/app/domain`, `application` | **pytest** + `pytest-cov` | Cada función. Sin base, sin red, sin reloj real |
| `backend/app/infrastructure` | pytest contra MySQL en Docker | Cada adaptador y su caso de fallo |
| `frontend/src/lib/domain`, `application` | **Vitest** | Cada función |
| Flujos completos | **Playwright** | Cobrar, arquear, devolver, entrar mercadería |

**La cobertura rompe la build.** No es un informe que alguien mira: es un umbral.

```toml
# backend/pyproject.toml
[tool.coverage.report]
fail_under = 100
include = ["app/domain/*", "app/application/*"]
```

```ts
// frontend/vitest.config.ts
coverage: {
  include: ['src/lib/domain/**', 'src/lib/application/**'],
  thresholds: { lines: 100, functions: 100, branches: 100, statements: 100 }
}
```

Los umbrales cubren **solo** dominio y aplicación, a propósito. Exigir 100 % en
adaptadores e interfaz llevaría a escribir pruebas que confirman que SQLAlchemy
es SQLAlchemy: mucho trabajo y ninguna información. Ahí el criterio es cubrir el
camino real y el fallo, y los flujos se prueban de punta a punta.

**Las pruebas de caracterización son las primeras.** Los invariantes ya
verificados de `progress.json` —venta 3×1450 → 4 915,50; arqueo 53 277,00;
devolución 1 638,50; cierre contando 53 000 → −277,00; entrada XML 79 800—
dejan de comprobarse a mano y pasan a ser casos de prueba. Es la red para todo
lo que viene después.

Comandos: `cd backend && pytest`, `cd frontend && npm test`.

---

## 2. Reestructuración del repositorio (F0) — hecha el 2026-08-16

Se hizo **primero** y sin cambiar comportamiento, para que todo lo demás se
escriba una sola vez en su lugar definitivo.

```
antes                          después
─────────────────────────      ──────────────────────────────────────────
web/                     →     frontend/
backend-patch/           →     backend/          (ver la trampa de abajo)
backend/     (clon ref)  →     borrado
csharp-original/         →     borrado
docker/      (original)  →     borrado
deploy/                        en desuso; queda hasta migrar su volumen
                               .specify/         (este directorio)
```

**Los archivos de Docker quedaron en la raíz de `backend/`, no en un
subdirectorio.** Era la consecuencia de la decisión de abajo y no se había
previsto: si `backend/` es la aplicación completa, el Dockerfile ya tiene ahí al
lado el `app/`, el `requirements.txt` y el `wait-for-db.sh` que copia, así que
`docker compose up` corre desde `backend/` sin ensamblar nada. `deploy/` existía
únicamente porque el patch no era una aplicación; deja de tener razón de ser.

### La trampa del renombrado

`backend-patch/` **no es una aplicación**: son los 39 archivos que reemplazan o
agregan sobre el FastAPI original. La aplicación completa tiene 56. Renombrarlo
tal cual deja un backend que no arranca — faltarían, entre otros:

```
app/database/database.py        app/models/model_client.py
app/models/model_categories.py  app/models/model_person.py
app/models/model_sale_details.py app/schemas/schemas_product.py
app/services/crud_client.py     app/services/crud_categories.py   (+ 9 más)
```

**Decisión.** El nuevo `backend/` es la **aplicación completa**, tomada de
`deploy/app/` (que es el patch ya aplicado sobre el original) sin `.env` ni
`__pycache__`. Deja de ser un parche y pasa a ser el código fuente del backend,
que es lo que corresponde ahora que el original ya no es el ancestro sino el
punto de partida.

`backend/README.md` cambia de «cómo aplicar este patch» a «cómo correr este
backend», conservando la sección de los defectos corregidos: explica por qué el
código es como es.

### Qué se pierde al borrar

`backend/` (clon de `backend-python`) y `csharp-original/` son clones de
repositorios que siguen publicados en GitHub — las URL están en
`progress.json` → `proyecto.repos_origen`. Lo único irrecuperable sería el
análisis, y ese ya está escrito: los 10 defectos con su impacto viven en
`progress.json` → `defectos_corregidos` y en `backend/README.md`.

`docker/` es la carpeta original del usuario, cuyos seis problemas ya están
corregidos en el compose que sí se usa.

### Después de mover

Actualizar toda referencia a las rutas viejas: `CLAUDE.md`, `progress.json`,
`README.md`, los README internos, `.gitignore` y los cuatro agentes de
`.claude/agents/`. Se verifica con una búsqueda de `web/` y `backend-patch` en
todo el árbol; el criterio de terminado es que no quede ninguna viva —las
menciones históricas, las que cuentan cómo fue la migración, se conservan.

### El volumen no puede depender de la carpeta

Salió al verificar, y por poco cuesta la base de datos. Compose toma el nombre
del proyecto del **nombre del directorio** y lo usa de prefijo del volumen: el
stack levantado desde `deploy/` guarda los datos en `deploy_db_data`. Levantar
lo mismo desde `backend/` habría creado `backend_db_data`, vacío, y habría
parecido que se perdió todo.

Se corrigió fijando en el compose `name: ventasys` y el volumen
`ventasys_db_data`, que no dependen de dónde esté la carpeta. La migración del
volumen viejo queda pendiente (§8, F0).

---

## 3. Multiempresa (F2)

Es la fase que toca todo. Va primero: cualquier tabla que se cree después la
necesita, y hacerla al final significa migrar dos veces.

### 3.1 Tablas nuevas

```sql
CREATE TABLE companies (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    afiliado       INT          NOT NULL,
    compania       INT          NOT NULL,
    nombre         VARCHAR(160) NOT NULL,
    identificacion VARCHAR(30)  NULL,
    plan_id        INT          NOT NULL,
    estado         VARCHAR(20)  NOT NULL DEFAULT 'prueba',
    vence_el       DATE         NULL,
    creada_el      DATETIME     NOT NULL,
    -- La identidad del cliente es el par, no el id. El id existe para que las
    -- claves foráneas y los índices sean de 4 bytes y no de 8.
    UNIQUE KEY uq_companies_afiliado_compania (afiliado, compania),
    INDEX idx_companies_estado (estado)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

CREATE TABLE plans (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    nombre         VARCHAR(60)    NOT NULL,
    precio_mensual DECIMAL(10,2)  NOT NULL DEFAULT 0,
    max_sucursales INT            NOT NULL DEFAULT 1,
    max_terminales INT            NOT NULL DEFAULT 1,
    max_usuarios   INT            NOT NULL DEFAULT 3,
    factura_electronica TINYINT(1) NOT NULL DEFAULT 0
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

CREATE TABLE branches (          -- sucursales
    id         INT AUTO_INCREMENT PRIMARY KEY,
    company_id INT          NOT NULL,
    codigo     CHAR(3)      NOT NULL,          -- 001, formato Hacienda
    nombre     VARCHAR(120) NOT NULL,
    activa     TINYINT(1)   NOT NULL DEFAULT 1,
    UNIQUE KEY uq_branches (company_id, codigo),
    CONSTRAINT fk_branches_company FOREIGN KEY (company_id) REFERENCES companies (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

CREATE TABLE terminals (         -- cajas
    id         INT AUTO_INCREMENT PRIMARY KEY,
    company_id INT          NOT NULL,
    branch_id  INT          NOT NULL,
    codigo     CHAR(5)      NOT NULL,          -- 00001, formato Hacienda
    nombre     VARCHAR(120) NOT NULL,
    activa     TINYINT(1)   NOT NULL DEFAULT 1,
    UNIQUE KEY uq_terminals (company_id, branch_id, codigo),
    CONSTRAINT fk_terminals_company FOREIGN KEY (company_id) REFERENCES companies (id),
    CONSTRAINT fk_terminals_branch  FOREIGN KEY (branch_id)  REFERENCES branches (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

-- Membresía: qué persona entra a qué compañía y con qué rol.
--
-- Existe porque `users` es la IDENTIDAD (un correo, una contraseña) y la
-- pertenencia es otra cosa. Repetir el correo con UNIQUE (company_id, email)
-- parecía más simple, pero crea tres cuentas distintas que solo se parecen en
-- el texto del correo: tres contraseñas que se desincronizan, y un login que
-- tendría que preguntar la compañía ANTES de autenticar —o sea, mostrarle la
-- cartera de clientes a cualquiera que escriba un correo (RN-24).
CREATE TABLE user_companies (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    user_id    INT         NOT NULL,
    company_id INT         NOT NULL,
    rol        VARCHAR(20) NOT NULL,          -- por compañía, no por persona
    activa     TINYINT(1)  NOT NULL DEFAULT 1,
    creada_el  DATETIME    NOT NULL,
    UNIQUE KEY uq_user_companies (user_id, company_id),
    INDEX idx_user_companies_company (company_id),
    CONSTRAINT fk_uc_user    FOREIGN KEY (user_id)    REFERENCES users (id_user),
    CONSTRAINT fk_uc_company FOREIGN KEY (company_id) REFERENCES companies (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

CREATE TABLE audit_log (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    user_id    INT          NOT NULL,
    company_id INT          NULL,              -- sobre qué compañía se actuó
    accion     VARCHAR(60)  NOT NULL,
    detalle    VARCHAR(500) NULL,
    ip         VARCHAR(45)  NULL,
    creado_el  DATETIME     NOT NULL,
    INDEX idx_audit_company (company_id, creado_el)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;
```

### 3.2 Tablas existentes

**Doce** tablas reciben `company_id INT NOT NULL` con su índice y su clave
foránea, y **cada UNIQUE pasa a ser compuesto**:

| Tabla | Cambio adicional |
|---|---|
| `users` | **No lleva `company_id` ni `role`.** Queda como identidad: `email` único global y una contraseña. La pertenencia y el rol pasan a `user_companies` (RN-3). Soporte es una persona sin ninguna membresía. |
| `persons` | **Tampoco lleva `company_id`.** Ver la corrección de abajo. |
| `clients` | `company_id`. UNIQUE (company_id, identification) y (company_id, email). |
| `categories` | `company_id`, `parent_id`, `orden`, `activa`. UNIQUE (company_id, parent_id, nombre). |
| `products` | `company_id`, `cabys_code`, `tax_rate`, `unidad_medida`, `activo`. UNIQUE (company_id, barcode). |
| `sales` | `company_id`, `branch_id`, `terminal_id`. UNIQUE (company_id, sale_number). |
| `sale_details` | `company_id` (redundante vía `sales`, pero necesario para el filtro automático). |
| `returns`, `return_details` | igual que ventas. |
| `cash_sessions`, `cash_movements` | `company_id`, `terminal_id`. |
| `stock_entries`, `stock_entry_details` | `company_id`, `branch_id`. |
| `settings` | Deja de ser una fila: `company_id` UNIQUE. |

`company_id` se repite en las tablas de detalle a propósito. Es
desnormalización, y se paga con un `INT` por fila a cambio de que el filtro
automático de la sección siguiente cubra **toda** consulta, incluidas las que
entran por el detalle sin pasar por la cabecera.

**Corrección al escribir la migración: `persons` es identidad, no negocio.**

Esta sección decía «`persons`, `clients` → `company_id`», y al ir a escribirlo se
vio que `persons` es 1 a 1 con `users`: `/persons/register` crea las dos filas
juntas y ninguna otra tabla la referencia. O sea que `persons` no guarda datos de
clientes —esos están en `clients`— sino el nombre y la cédula de la misma
identidad que representa `users`.

Ponerle `company_id` obligaría a decidir a qué compañía «pertenece» el contador
que atiende tres locales, que es exactamente el problema que T-216 acababa de
resolver para `users`. Queda global, con su cédula única en todo el sistema: dos
personas distintas no comparten cédula aunque trabajen en compañías distintas.

Por eso la cuenta da doce y no catorce. Lo que sí cambió es quién puede verlas:
`/persons/persons_list` devolvía la libreta entera de la base y ahora se une con
`user_companies` para devolver solo las de la compañía de la sesión.

### 3.3 Cómo se garantiza el aislamiento

No con disciplina. Con tres capas:

**1. El `company_id` sale del token, nunca del cliente.** Se agrega al JWT al
iniciar sesión y `get_current_user` lo devuelve. Ningún endpoint lo acepta como
parámetro: si llega, se ignora.

**2. Filtro automático en SQLAlchemy.** Un `ContextVar` por petición y un
`with_loader_criteria` global:

```python
# app/utils/tenancy.py
current_company: ContextVar[int | None] = ContextVar("current_company", default=None)

class TenantMixin:
    """Lo heredan todos los modelos de negocio."""
    company_id = Column(Integer, nullable=False, index=True)

class SinCompania(Exception):
    """Se intentó leer una tabla de negocio sin compañía en la petición."""

@event.listens_for(Session, "do_orm_execute")
def _filtrar_por_compania(state):
    if not state.is_select:
        return
    if state.execution_options.get("sin_filtro_de_compania"):
        return                       # única salida, y se pide por escrito
    cid = current_company.get()
    if cid is None:
        # Falla cerrado. Ver más abajo: la versión que dejaba pasar era un
        # agujero, no una comodidad.
        raise SinCompania(state.statement)
    state.statement = state.statement.options(
        with_loader_criteria(TenantMixin, lambda cls: cls.company_id == cid,
                             include_aliases=True)
    )
```

Olvidar el `WHERE` deja de ser posible en las consultas del ORM. Para las pocas
que necesitan cruzar compañías —el panel de soporte— hay que pedirlo explícito
con `sin_filtro_de_compania`, que es justo lo que se quiere: que salte a la
vista al leer el código.

**Por qué falla cerrado.** La primera versión de este filtro decía `if cid is
not None: aplicar`. Con un usuario por compañía nunca se notaba, porque el
`company_id` siempre venía en el token. La pantalla de selección (RF-27) crea
justo el estado que faltaba: **autenticado y todavía sin compañía**. Con la
versión permisiva, una consulta en esa ventana no se filtra por nada y devuelve
las filas de **todas** las compañías —sin error, sin aviso, en un reporte que se
ve perfecto—. Lo mismo pasaba con soporte, que tiene la compañía en nulo: veía
todo por omisión, no por haberlo pedido, que es lo contrario de lo que dice el
párrafo anterior.

Ahora la ausencia de compañía es una excepción. El panel de soporte y el propio
login —que consulta `users` y `user_companies` antes de que haya compañía— pasan
por `sin_filtro_de_compania`, escrito y visible.

**Ajuste al implementarlo: se exige compañía solo si la consulta toca negocio.**

El esbozo de arriba lanza `SinCompania` en toda consulta sin compañía. Escrito
así, el login —que lee `users` y `user_companies` antes de que exista compañía—
tendría que marcarse con `sin_filtro_de_compania`, igual que cualquier lectura de
identidad. Y ahí la marca deja de significar algo: si aparece en las consultas
normales, ya no señala «acá se cruzan compañías a propósito», que es lo único que
la hace útil al leer el código.

La versión implementada mira `state.all_mappers` y solo exige compañía si la
consulta involucra alguna clase que herede `TenantMixin`. No se pierde nada:
una consulta que no toca ninguna tabla de negocio no puede filtrar datos de
negocio.

**La otra mitad: sellar la escritura.**

El plan solo cubría la lectura, y eso deja el aislamiento cojo. Si leer sin
`WHERE company_id` es imposible pero escribir sin `company_id` depende de que
quince sitios se acuerden, el fallo entra por el lado de la escritura: una venta
guardada sin compañía queda visible para nadie —o, peor, para quien tenga ese
número— y el defecto aparece semanas después, cuando ya hay datos encima.

Se resuelve con el mismo mecanismo y en el mismo archivo:

```python
@event.listens_for(Session, "before_flush")
def _sellar_compania(session, flush_context, instances):
    for objeto in session.new:
        if isinstance(objeto, TenantMixin) and objeto.company_id is None:
            objeto.company_id = compania_actual()   # falla cerrado
```

No pisa lo que ya venga puesto: `bootstrap.py` y las semillas crean filas de una
compañía distinta de la del contexto a propósito.

Sucursal y terminal se sellan igual pero **explícitas**, en los cuatro
repositorios que registran hechos (`sucursal_actual()`, `terminal_actual()`).
Ahí la magia no ayudaría: `Terminal.branch_id` también se llama así y significa
otra cosa.

**Límite conocido, y es más ancho de lo que parecía.** `with_loader_criteria`
cubre los SELECT del ORM que **cargan entidades**. No cubre:

- el SQL agregado de `crud_report.py` ni los `UPDATE`/`DELETE` masivos —eso ya
  estaba previsto, y esos llevan su `company_id ==` escrito a mano, siete
  consultas, con prueba propia—;
- **`Query.count()`**, que no estaba previsto. `count()` no ejecuta la consulta
  de la entidad: la envuelve en `SELECT count(*) FROM (…)` y el criterio no
  entra en la envoltura. O sea que `db.query(Product).all()` devuelve solo las
  propias pero `db.query(Product).count()` cuenta las de **todas**.

Lo segundo es más peligroso que lo primero, porque un `.count()` no parece SQL
agregado: parece una llamada inocente del ORM. Se descubrió al escribir la
prueba de T-206 —no había ninguna fuga en el código, pero el hueco estaba— y la
respuesta fue un guardián: `tests/test_tenancy.py` recorre el árbol de sintaxis
de `app/` y tumba `pytest` si aparece un `.count()` sin `company_id` ni
`sin_filtro` en la misma sentencia. La forma que sí se filtra es
`db.query(func.count(Modelo.id))`, porque ahí la columna pertenece a la entidad.

Está anotado como riesgo en §10.

**Dónde se fija la compañía, y por qué la dependencia es asíncrona.**

FastAPI corre las dependencias síncronas en un hilo aparte, con una **copia** del
contexto: un `ContextVar` fijado ahí no se ve desde el endpoint. Las asíncronas
corren en la misma tarea que la petición. Por eso `payload_del_token` es `async`
y no lo es por gusto; si alguien la vuelve síncrona, el filtro deja de recibir la
compañía y todo empieza a lanzar `SinCompania`.

**3. Pruebas que intentan cruzarse.** Dos compañías sembradas y una batería que
recorre **todos** los endpoints pidiendo, con el token de la compañía A, los
identificadores de la B. Toda respuesta debe ser 404 (no 403: un 403 confirma
que el recurso existe). Sin esta prueba la fase no está terminada.

### 3.4 Migración de lo que ya hay

```sql
INSERT INTO plans (id, nombre, precio_mensual, max_sucursales, max_terminales, max_usuarios)
     VALUES (1, 'Comercio', 25000, 1, 3, 10);

INSERT INTO companies (id, afiliado, compania, nombre, plan_id, estado, creada_el)
     VALUES (1, 1, 1, 'Compañía inicial', 1, 'activa', NOW());

-- Toda fila existente pasa a la compañía 1.
UPDATE products SET company_id = 1;   -- ídem para cada tabla
```

El sistema actual queda como afiliado 1, compañía 1, activa, sin perder nada.
Los `ALTER TABLE ... ADD COLUMN company_id NOT NULL DEFAULT 1` se ejecutan con
el valor por omisión y **después** se le quita el DEFAULT, para que las filas
nuevas estén obligadas a decir a quién pertenecen.

Cada usuario actual recibe su membresía con el rol que ya tenía, antes de que
`users.role` desaparezca:

```sql
INSERT INTO user_companies (user_id, company_id, rol, activa, creada_el)
     SELECT id_user, 1, role, 1, NOW() FROM users;
```

### 3.5 Entrar: dos pasos, no uno

Con membresías, el login deja de ser una sola operación. Se parte en dos, con un
estado intermedio corto y sin permisos (RN-26).

```
correo + contraseña ─┬─► 1 compañía disponible ──► adentro          (RN-25)
                     └─► 2 o más ──► elegir compañía ──► adentro    (RF-27)
```

**Paso 1 — autenticar.** `POST /auth/login` valida la contraseña y devuelve un
token **de tránsito**: lleva `sub` (la persona) y *no* lleva `cid`. Dura pocos
minutos y solo sirve para dos endpoints: listar las compañías propias y elegir
una. Cualquier ruta de negocio lo rechaza con 401 —y aunque no lo hiciera, el
filtro de §3.3 falla cerrado.

**Paso 2 — elegir.** `POST /auth/company` recibe el `company_id`, verifica que
exista la membresía **activa** y que el estado de la suscripción deje entrar, y
devuelve el token de sesión, ahora sí con `cid` y con el `rol` de esa membresía.
Queda en bitácora.

Reglas que no son cosméticas:

- **La lista solo se ve con un token**, de tránsito o de sesión (RN-24). Si se
  pudiera pedir con el correo a secas, cualquiera enumeraría los clientes del
  producto escribiendo direcciones. Que también valga el token de sesión es lo
  que permite cambiar de compañía sin volver a escribir la contraseña (RF-28):
  prueba la identidad igual de bien, y lo único que deja ver son las membresías
  propias.
- **Una sola compañía disponible ⇒ no hay pantalla** (RN-25). El backend
  devuelve el token de sesión directo en el paso 1, y el cajero no se entera de
  que esto existe.
- **Las bloqueadas se listan igual, con su motivo** (RF-27). Una compañía
  suspendida que simplemente no aparece se lee como «me borraron la cuenta».
- **Cambiar de compañía re-emite el token** y limpia el estado del navegador
  (RN-27): carrito, ventas en espera y la caché de configuración de §3.6.

### 3.6 La caché de configuración es de una sola compañía

`frontend/src/lib/server/settings.ts` guarda la configuración en una variable de
módulo:

```ts
let cache: { value: StoredSettings; at: number } | null = null;
```

Esa variable vive en el proceso de Node, no en la petición. Con una compañía es
correcto y ahorra una llamada por pantalla. Con varias, **la primera compañía
que cargue una página le presta su nombre, su logo, su moneda y su color de
acento a todas las demás durante 30 segundos**. `invalidateSettings()` tiene el
mismo problema al revés: quien guarda le borra la caché a todos.

La caché pasa a estar indexada por compañía (`Map<company_id, …>`) y la
invalidación a ser de una sola. Entra en F2 junto con el resto del aislamiento,
no después: es exactamente el mismo defecto que el `WHERE` olvidado, solo que en
el otro lado del BFF.

### 3.7 Respaldar y restaurar una sola compañía (T-217, herramienta en T-225)

Con base compartida, devolverle sus datos a un cliente deja de ser un
`mysqldump`. La decisión, tomada al escribir la migración:

**Se restaura solo lo que no está.** `auto_increment` de MySQL nunca reutiliza un
número, así que las filas de una compañía dada de baja dejan sus identificadores
libres para siempre. La restauración los conserva tal cual y no remapea nada
—remapear claves entre doce tablas es donde este tipo de herramienta se rompe—.
El precio es que restaurar sobre una compañía que todavía tiene filas está
prohibido: el guion se niega antes de tocar nada, en vez de mezclar.

**El orden lo dictan las claves foráneas**, no el guion. Por eso la migración las
crea: al exportar e importar, la base misma obliga a hacerlo bien y un error de
orden falla en vez de dejar huérfanos.

**`users` se exporta por correo, no por fila.** Es identidad global y puede estar
compartida con otra compañía que sigue viva; copiar la fila crearía una cuenta
duplicada o chocaría con el UNIQUE. Se exportan las membresías y, al restaurar,
se busca la cuenta por correo y se crea solo si no existe.

**Sirve para dos cosas distintas** y por eso vale la pena hacerlo bien: devolver
los datos a quien se da de baja, y volver atrás cuando una compañía se daña sin
tocar a las otras once que están vendiendo en ese momento.

Implementado en `backend/company_dump.py` (`exportar`, `borrar`, `importar`).
Borrar pide el par afiliado-compañía escrito a mano: es la única operación que
destruye datos, y un `--compania 2` mal tecleado se lleva el negocio equivocado
sin ninguna otra señal. Una prueba —`verificar_cobertura()`— falla si aparece una
tabla que nadie clasificó, porque una exportación incompleta se descubre el día
que hace falta restaurar, que es el peor día para descubrirlo.

### 3.8 La membresía se acepta, no se impone (T-229)

Un administrador tiene que poder sumar a su compañía a alguien que ya tiene
cuenta: es la única forma de armar el caso del contador que atiende tres locales
(RN-3). Pero poder sumarlo no es poder entrar por él.

La primera versión daba el acceso de una: el administrador escribía un correo y
esa compañía aparecía en la lista de la otra persona al entrar. No le hacía daño
—tenía que elegirla para que pasara algo— pero tampoco le había preguntado. Con
base compartida eso pesa más de lo que parece: la lista de compañías de alguien
dice con quién trabaja, y llenársela de invitados ajenos es ruido y, peor, una
superficie de engaño —basta dar de alta una compañía con nombre parecido al suyo
para que aparezca ahí, al lado de la de verdad—.

`user_companies.aceptada_el` en nulo significa «invitada, sin responder». Los
tres estados de una fila:

| `activa` | `aceptada_el` | Qué es |
|---|---|---|
| 1 | nulo | invitación pendiente: se ve, no abre |
| 1 | fecha | membresía en uso |
| 0 | — | revocada por el administrador, o rechazada por la persona |

La frontera está en **quién crea la cuenta**:

- `POST /users/` la crea el administrador, con el correo y la contraseña que él
  eligió. Nace **aceptada**: pedirle a esa cuenta que acepte una invitación a sí
  misma no protegería a nadie.
- `POST /users/membership` suma una identidad **que ya existía**. Nace
  **pendiente**.
- `bootstrap.py` nace aceptada, por lo mismo que el primer caso y porque una
  invitación que nadie puede aceptar dejaría la instalación sin poder entrar.

Reinvitar a quien rechazó vuelve a dejar la membresía pendiente: haber dicho que
no una vez no es haber dicho que sí.

### 3.9 Las columnas de la suscripción se quedan en español (T-913, decidido el 2026-09-05)

`companies`, `plans`, `user_companies`, `branches` y `terminals` tienen sus
columnas en **español** —`afiliado`, `compania`, `nombre`, `identificacion`,
`estado`, `vence_el`, `creada_el`, `precio_mensual`, `max_sucursales`,
`max_terminales`, `max_usuarios`, `factura_electronica`, `rol`, `activa`,
`aceptada_el`, `codigo`—, contra la regla de código en inglés. Vienen de la
migración 002 y son la única excepción: F4 no las siguió y usó `sort_order` e
`is_active`.

**Se aceptan como están.** No es pereza; es que el rename no es un rename:

- Son **58 archivos y unas 890 menciones**, medidas, no estimadas.
- **Trece de los diecisiete nombres son claves JSON publicadas** —`CompanyOption`,
  `CompanyOut`, `PlanOut`, `NewCompany`, `SubscriptionUpdate`— y hay que moverlas
  en el mismo commit en cinco frentes que **no comparten compilador**: modelo y
  migración, esquemas Pydantic, el simulado, los tipos y formularios de `/admin`,
  y los catálogos `es`/`en`/`pt`. `npm run check` no ve el backend y `pytest` no
  ve el POS, así que una clave que quede vieja **no rompe la build**: devuelve
  `undefined` en pantalla.
- El punto de no retorno es `company_dump.py`. Exporta **por nombre de columna**
  (`fila._mapping`) y su `FORMATO = 1` no cambia con un rename, así que la guarda
  de versión deja pasar un respaldo viejo como si fuera compatible y revienta
  después, al insertar. **Todo respaldo entregado a un cliente antes del cambio
  quedaría inservible**, en silencio, hasta el día que haya que restaurarlo —que
  es el peor día para descubrirlo—.
- No compra nada funcional. Es consistencia, y se pagaría con el presupuesto de
  riesgo justo antes de F5, que toca todo el cálculo de impuestos.

**La condición de reapertura se cumplió, y la respuesta siguió siendo no**
(T-916, cerrada el 2026-09-13). Esta sección decía que F6 tocaría esas tablas
—T-608 construye el ABM de sucursales y terminales— y que ahí se pagaría una
vez. F6 llegó, las toca, y la decisión se confirma en vez de revertirse:

- Ningún argumento de arriba se debilitó, y el de los respaldos se **reforzó**:
  desde 2026-09-05 se entregaron más, y son justo lo que el rename rompe en
  silencio.
- La mezcla dejó de ser hipotética: la migración 011 puso `identification_type`
  al lado de `identificacion`. Con las columnas nuevas ya escritas se ve que esa
  vecindad es una cicatriz y no una herida — fea de leer, inerte.
- Y reabrirla tiene costo propio, ya pagado tres veces (T-913 → T-916 → T-1001 →
  F6). Una decisión que se reabre en cada fase no es una decisión pendiente.

**Qué la reabriría de verdad**, escrito para que no vuelva a abrirse por menos:
que `company_dump.py` versione el esquema por otro motivo —con lo que el rename
dejaría de romper respaldos—, o que una de esas columnas empiece a salir en un
contrato nuevo hacia afuera. Ninguna de las dos está prevista.

Mientras tanto, la regla de código en inglés **sigue vigente para todo lo demás**:
esta excepción es de las columnas que ya existen, no una licencia para las nuevas.
F6 estrena dos tablas y las dos van enteras en inglés.

---

## 4. Panel de soporte (F3) — hecho el 2026-08-23

Grupo de rutas `/admin` en el mismo despliegue, no una aplicación aparte:
duplicar autenticación y despliegue para cinco pantallas no se paga.

- Solo rol `soporte`, verificado en el servidor en cada `load` y cada acción.
- Su sesión **no tiene compañía**: las pantallas del POS le responden 403.
- *Entrar como* emite un token con el `company_id` de la compañía destino, con
  vencimiento corto y motivo obligatorio, y escribe en `audit_log`. La interfaz
  muestra una franja permanente mientras dure.
- Toda acción de soporte se registra: alta, cambio de estado, entrada.

### 4.1 Quién es soporte

**Una columna: `users.is_support`** (migración 004). El plan decía «soporte es
una persona sin ninguna membresía» y como definición no servía: quien rechaza la
única invitación que tenía también se queda sin ninguna, y quedaría
administrando el producto por descarte. La ausencia de algo no puede ser un
permiso.

La marca vive en `users` y no en `user_companies` porque es una propiedad de la
identidad, como el correo. La primera cuenta se crea con
`bootstrap.py --soporte`, por lo mismo que la primera compañía: no hay API que
pueda otorgar un permiso que todavía nadie tiene.

### 4.2 Cuatro tipos de token

| `tipo` | Lleva `cid` | Dura | Para qué |
|---|---|---|---|
| `transito` | no | 10 min | elegir compañía (RN-26) |
| `sesion` | sí | 8 h | el POS |
| `soporte` | **no** | 8 h | el panel |
| `suplantacion` | sí | **30 min** | *entrar como* (RF-8) |

Que el de soporte no lleve compañía es todo el diseño: el filtro de
`tenancy.py` le hace fallar cerrado cualquier consulta a una tabla de negocio,
así que para ver los datos de un cliente **tiene que** entrar como esa compañía
—que es lo que pide RN-4 y lo que deja rastro—. Las consultas del panel, que
cruzan compañías a propósito, van todas por `crud_support.py` con `sin_filtro`.

El de suplantación no lleva rol: lo pone `auth_dependency` en `admin`. Escribir
el rol en dos sitios es la forma de que un día digan cosas distintas.

### 4.3 El bloqueo por vencimiento va en un solo sitio

`get_current_user` corta toda petición con método que escribe cuando la sesión
es de solo lectura. **Acá y no en cada ruta**, por la misma razón que el filtro
de compañía vive en un escuchador de SQLAlchemy: cuarenta endpoints que hay que
acordarse de tocar no son un control de acceso.

Las dos excepciones están en `ESCRITURA_EN_SOLO_LECTURA` con su motivo escrito
—`/cash/close` por RN-1 y `/auth/locale` porque el aviso de pago hay que poder
leerlo en su idioma—, y `tests/test_suscripcion.py` obliga a que sigan siendo
rutas que existen. El mismo archivo tiene el guardián que importa a futuro: toda
ruta que escriba pasa por `get_current_user` o está declarada con su porqué.

En el POS el bloqueo se adelanta a **una** pantalla, ventas, porque es la única
donde la sorpresa cuesta plata (RN-2). Las demás se quedan con el aviso del
layout: allá lo que se pierde al chocar con el «no» es un clic.

### 4.4 El estado se evalúa en cada petición, no se guarda

`domain/subscription.py` es aritmética pura: estado guardado + fecha + hoy →
qué se puede hacer. Se llama en cada `get_current_user` y viaja al POS por
`/users/me`, **no en el token**. Meterlo en el token lo congelaría hasta el
próximo login, que es lo peor de los dos mundos: bloquea tarde y desbloquea
tarde. Así, un pago que entra hoy le devuelve el POS al cliente en el siguiente
clic.

### 4.5 El alta es una sola función, usada por dos caminos

`crud_company.dar_de_alta` crea las seis filas —compañía, sucursal, terminal,
configuración, identidad y membresía— y la llaman `bootstrap.py` y
`POST /support/companies`. Antes la lista vivía en el guion; copiarla al panel
habría dejado dos altas que se parecen y que dejarán de parecerse el día que
haya una séptima fila.

**Los textos del documento los manda el POS** (T-304). Nacen vacíos en el
dominio (T-816) y el backend no puede escribirlos —no tiene catálogo y no sabe
en qué idioma—, así que el formulario del panel los resuelve con
`initialDocumentTexts(document_locale)` y los envía en `settings`. Es el único
momento en que se conocen las dos cosas a la vez: el idioma del documento y las
palabras.

### 4.6 El API va bajo `/support` y las pantallas bajo `/admin`

Dos nombres para lo mismo, a propósito: `admin` ya es el rol del administrador
de una compañía, y dos cosas distintas con el mismo nombre en el mismo API se
confunden. En la barra de direcciones, en cambio, `/admin` es lo que se lee
bien.

---

## 5. Categorías de dos niveles (F4)

`parent_id` con `NULL` para las raíces. Aunque el árbol quede limitado a dos
niveles por regla (RN-5), la columna permite abrir un tercero sin migrar.

La profundidad se valida en el servicio, no en la base: al crear una categoría
con `parent_id`, se verifica que el padre sea raíz. Un `CHECK` de MySQL no
alcanza para esto.

Migración: las categorías actuales quedan como raíces sin hijas. Nada se rompe.

---

## 6. Impuesto por producto y CABYS (F5)

### 6.1 Contrato del API — verificado el 2026-08-16

```
GET https://api.hacienda.go.cr/fe/cabys?q=<texto>&top=<n>
→ { "total": 16, "cantidad": 3,
    "cabys": [ { "codigo": "2312000000300",
                 "descripcion": "Harina de arroz",
                 "categorias": [ …8 niveles… ],
                 "impuesto": 13,
                 "uri": "…?codigo=2312000000300",
                 "estado": "" } ] }

GET https://api.hacienda.go.cr/fe/cabys?codigo=<13 dígitos>
→ [ { "categorias": […], "codigo": "…", "descripcion": "…", "impuesto": 13 } ]
```

**Ojo:** la consulta por texto devuelve un **objeto** con la lista adentro; la
consulta por código devuelve una **lista pelada**. Formas distintas en el mismo
endpoint; el lector tiene que contemplar las dos.

Tarifas comprobadas: harina de arroz 13 %, medicamentos 2 %, libros infantiles
0 %. La tarifa viene en el catálogo, que es exactamente el motivo por el que el
impuesto no puede ser un número global.

También existe `GET /fe/ae?identificacion=<cédula>` para la actividad económica;
responde 404 con un mensaje en inglés cuando la cédula no existe.

### 6.2 Diseño

- **Proxy en FastAPI**, no llamada desde el navegador: el POS puede estar en una
  LAN sin salida, no queremos exponer internet al cliente ni pelear con CORS, y
  así la respuesta se puede cachear una vez para todas las compañías.
- **Tabla `cabys_cache`** (`codigo` PK, `descripcion`, `impuesto`,
  `actualizado_el`), global y no por compañía: el catálogo es el mismo para
  todos. Se llena con los códigos que se van usando.
- Al asignar un código a un producto se copia la tarifa y se guarda en caché,
  de modo que **facturar no depende de que Hacienda esté arriba**.
- Sin internet, la búsqueda responde desde la caché y lo dice.

### 6.3 Impuesto por línea

`computeTotals` deja de recibir una tasa y pasa a recibir líneas con su propia
tarifa:

```ts
computeTotals([{ price, quantity, taxRate }, …])
  → { subtotal, tax, total, porTarifa: [{ tarifa, base, impuesto }] }
```

El desglose `porTarifa` es lo que necesitan el documento impreso (RF-21) y, más
adelante, el XML de Hacienda. Toca `money.ts`, el carrito, `crud_sale`,
`crud_return`, los reportes, las tres plantillas y el mock. Es la parte más
invasiva de la fase y conviene hacerla de un solo tirón.

#### La tarifa se congela en la línea, no en el producto

`sale_details` recibe `tax_rate` y `tax_amount`, escritos en el momento de
cobrar. **No basta con tener la tarifa en `products`**, por dos razones que son
la misma regla vista de dos lados:

1. La tarifa del producto cambia —Hacienda actualiza el catálogo, o el dueño
   corrige el código CABYS—. Sin congelarla, devolver algo vendido el mes pasado
   usaría la tarifa de hoy. Es exactamente lo que RN prohíbe.
2. Con tarifas mezcladas, la del encabezado deja de servir. Hoy la devolución
   reconstruye la tasa como `tax / subtotal` (`TaxRate.of_sale`), y eso funciona
   mientras toda la venta lleve una sola tarifa. En cuanto se mezclan, ese
   cociente es un **promedio**:

   ```
   venta: 1 medicamento ₡1 000 al 2 %  +  1 arroz ₡1 000 al 13 %
          subtotal ₡2 000 · impuesto ₡150 · promedio 7,5 %

   devolver solo el medicamento →  correcto  1 000 × 1,02 = ₡1 020
                                   promedio  1 000 × 1,075 = ₡1 075
   ```

   ₡55 de más, y ₡55 de menos si lo que se devuelve es el arroz. La caja no
   cuadra y nadie sabe por qué.

`TaxRate.of_sale` no se borra: sigue siendo lo correcto para las ventas
anteriores a esta migración, que tienen una sola tarifa y no tienen la columna.
La devolución usa la tarifa de la línea cuando está, y el cociente del
encabezado cuando no.

#### Y el servidor tiene que verificar por línea

El cálculo del servidor (T-108b) recibe hoy **una** tasa
(`sale_totals(lines, rate)`) y la aplica al subtotal. Con tarifas por línea pasa
a aplicar la de cada una y a sumar. La tolerancia de un céntimo se vuelve más
apretada de lo que parece: con tres tarifas distintas hay tres redondeos donde
antes había uno, así que la tolerancia debe medirse **por documento y no por
línea**, o una venta larga con tarifas mezcladas se rechazaría por acumulación.

---

## 7. Facturación electrónica

### 7.1 Credenciales de Hacienda (entra en F6)

#### Son dos secretos y los dos son por ambiente

Firmar y transmitir son operaciones distintas con credenciales distintas, y
Hacienda las emite por separado para pruebas y para producción
(`docs/hacienda/costa-rica/README.md` §7 y §12):

| | Para qué | Dónde se obtiene |
|---|---|---|
| `.p12` + PIN | Firmar el XML (XAdES-EPES) | ATV → Llave Criptográfica |
| Usuario + contraseña ATV | Token OIDC del IdP, para transmitir | ATV → Credenciales API |

El usuario tiene forma `cpf-01-1234-5678@comprobanteselectronicos.go.cr`, el
`grant_type` es `password` y el `client_secret` va vacío. El `client_id` y el
realm los decide el ambiente: `api-stag`/`rut-stag` contra `api-prod`/`rut`.

**La llave primaria es `(company_id, environment)` y no `company_id`.** El diseño
anterior solo admitía un juego por compañía, y con eso «pasar a producción»
significaba borrar lo de pruebas sin poder volver. Un cliente en integración
tiene los dos a la vez (RN-33).

```sql
CREATE TABLE fe_credentials (
    company_id      INT          NOT NULL,
    environment     VARCHAR(12)  NOT NULL,   -- 'sandbox' | 'production'

    -- Firma -----------------------------------------------------------------
    -- La parte PÚBLICA se guarda siempre y NO es secreta: viaja en el KeyInfo
    -- de cada XML firmado.
    --
    -- **La privada no está acá, ni cifrada ni de ninguna forma**: se importa a
    -- Vault al subir el `.p12` y desde entonces vive solo ahí. Por eso tampoco
    -- están el `.p12` ni el PIN — ver «La llave privada va a Vault», abajo.
    certificate_pem LONGTEXT     NULL,       -- parte pública, sin cifrar
    key_custody     VARCHAR(12)  NULL,       -- 'vault'; NULL = sin certificado
    certificate_name VARCHAR(160) NULL,
    expires_at      DATETIME     NULL,       -- DATETIME y no DATE: el notAfter tiene hora
    cert_uploaded_at DATETIME    NULL,
    cert_uploaded_by INT         NULL,

    -- Transmisión -----------------------------------------------------------
    atv_user        VARCHAR(160) NULL,       -- identificador, NO secreto: se muestra
    atv_password_encrypted VARBINARY(512) NULL,
    atv_updated_at  DATETIME     NULL,
    atv_updated_by  INT          NULL,
    atv_verified_at DATETIME     NULL,       -- última vez que el IdP dio token

    PRIMARY KEY (company_id, environment),
    CONSTRAINT fk_fe_credentials_company FOREIGN KEY (company_id) REFERENCES companies (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;
```

**Los nombres van en inglés**, como el resto del código. §3.9 cierra ese punto
diciendo que la excepción de las columnas en español «es de las columnas que ya
existen, **no una licencia para las nuevas**», y esta fase estrena una tabla
entera. El valor del ambiente es `'sandbox'` y no `'pruebas'` porque es el que
el POS ya publica hoy (`settings.eInvoicing.environment`), y tener dos vocablos
para el mismo estado es cómo se pierde una migración.

**Las marcas de tiempo son dos pares** porque son dos secretos con vidas
distintas: rotar la contraseña de ATV en marzo no puede hacer que la pantalla
diga que el certificado se subió en marzo.

**Hereda `TenantMixin`.** Es una tabla de compañía y va con el filtro automático
de `tenancy.py`, que falla cerrado: dejarla fuera la convertiría en la única
tabla de negocio cuya lectura depende de que alguien se acuerde de escribir el
`WHERE`, y lo que se filtraría es un certificado de firma. Dos consecuencias que
hay que escribir porque muerden:

1. El `company_id` del mixin entra en una **clave primaria compuesta**, así que
   se declara con `PrimaryKeyConstraint('company_id', 'environment')` y no con
   `primary_key=True` suelto.
2. **El trabajador de transmisión corre fuera de una petición** (§7.2), donde no
   hay compañía en el contexto. Sin un `with compania(cid)` alrededor de cada
   documento, la primera lectura de credenciales lanza `SinCompania` y la cola
   no avanza nunca. Es la misma trampa que CLAUDE.md ya documenta para los
   objetos expirados después del `commit`.

#### La llave privada va a Vault, y el `.p12` no se guarda (decidido el 2026-09-13)

**Vault transit es el único sitio donde vive la privada.** Al subir el `.p12` se
abre en memoria con su PIN, se extrae la llave, **se importa a Vault y se
descarta todo lo demás**. De ahí en adelante firmar es mandarle el digest y
recibir la firma (PKCS#1 v1.5, que es lo que pide XAdES-EPES); la llave nunca
vuelve a entrar en memoria de la aplicación. Es lo que ya hace DetCore
(`docs/hacienda/costa-rica/recepcion-comprobantes-mensaje-receptor.md` §3.1).

El diseño anterior ofrecía dos adaptadores —uno local con el `.p12` cifrado en
una columna— y elegía según el despliegue. Se cierra a uno.

**Lo que se cae de la tabla es la mitad de las columnas de firma**, y esa es la
señal de que la decisión simplifica en vez de agregar:

| Ya no existe | Por qué |
|---|---|
| `p12_encrypted` | La privada está en Vault; guardar además el `.p12` sería tener dos copias de un secreto, una de ellas olvidable |
| `pin_encrypted` | **El PIN solo sirve para abrir el `.p12`, y eso pasa una sola vez.** Importada la llave, no hay nada que volver a abrir |
| `key_version` | Existía para rotar `FE_CRYPTO_KEY` sin Vault. Transit versiona solo, y la versión que firmó viaja dentro de la propia firma (`vault:v1:…`) |

Que el PIN **no se guarde en ninguna parte** es el mayor efecto secundario, y
cambia el carácter de T-609: hasta ahora había que comprobar que no se filtrara
por respuestas, bitácora ni trazas; ahora esa comprobación pasa a ser sobre un
valor que solo existió durante una petición. Lo que no está no se filtra.

**El puerto sigue existiendo, con un solo adaptador.** `DocumentSigner` no está
ahí para elegir entre Vault y otra cosa —esa decisión ya se tomó— sino porque
§7.2 deja abierta la ruta de emisión: si la firma termina pasando por un
proveedor autorizado, el que cambia es el adaptador y no el caso de uso. Y
porque un puerto con prueba de contrato es lo que hace que la firma se pueda
probar sin Vault levantado.

```python
class DocumentSigner(Protocol):
    def sign(self, digest: bytes, *, company_id: int, environment: str) -> bytes: ...
    def import_key(self, pkcs8: bytes, *, company_id: int, environment: str) -> None: ...
```

**La compañía y el ambiente van explícitos y no en un `ContextVar`.** Con estado
escondido, el caso de uso no se puede probar contra «firmá esto con el de
pruebas», y el adaptador no tendría cómo elegir llave sin heredar el contexto de
la petición — que es justo lo que el trabajador de fondo no tiene.

**El nombre de la llave en Vault se DERIVA, no se guarda.** Se calcula en el
servidor a partir de `(company_id, environment)`. Guardarlo como un campo que
alguien pueda escribir sería dejar que el administrador de la compañía 7 apunte
a la llave de la compañía 3 y emita documentos fiscales firmados con el
certificado de otro cliente. Es la misma frase que ya rige la ruta del almacén
de documentos (§7.3): la identidad la fija el servidor, no quien llama.

**`FE_CRYPTO_KEY` no desaparece: le queda un solo cliente.** La contraseña de
ATV hay que poder **replayarla** al IdP en cada token (`grant_type=password`),
así que no es un digest que se firme sino un secreto que se guarda y se lee.
Sigue en su columna con AES-256-GCM y `(company_id, environment)` como dato
asociado. El arranque falla si la llave no está o no mide 32 bytes: enterarse el
día que alguien guarda credenciales es tarde.

#### Lo que Vault arregla, y el modo de falla que introduce

Lo que gana es exactamente lo flojo de una llave estática en una columna: no
rota, no deja rastro de cada uso y, si se pierde, obliga a todos los clientes a
volver a subir su certificado. Transit da rotación y **bitácora de cada firma**,
que para una llave que emite documentos fiscales es la mitad del valor. Y quita
el peor escenario del diseño anterior: un respaldo robado ya no contiene ninguna
llave de firma, porque en la base no hay ninguna.

**El modo de falla nuevo no es «sin internet» — es el sello, y ahora alcanza
también al negocio de una sola caja.** Con dos adaptadores, la VM de un negocio
corría el local y Vault nunca estaba en el camino. Con uno, Vault está en el
camino siempre, y **un Vault sellado no firma**: se sigue vendiendo, se sigue
numerando, y la cola crece sin que nada falle a la vista.

Eso hay que resolverlo en el despliegue, no en el código, y conviene escribir
que **no es gratis**: Vault arranca sellado después de cada reinicio. Las salidas
son auto-unseal contra un KMS —que pide internet y una cuenta en la nube— o las
llaves de apertura en el disco de la propia VM con una unidad de systemd que lo
abra al arrancar. La segunda es la realista para un negocio, y deja el modelo de
amenaza en «cifrado en reposo con la llave en el mismo disco», que es más o menos
lo que daba el adaptador local. **Lo que se gana igual** es que la llave no está
en la base ni en sus respaldos, que hay bitácora de cada firma y que la privada
no pasa por la memoria de la aplicación. Va en el README de despliegue, con el
procedimiento de apertura y el aviso de qué pasa si no se hace.

Y tiene reloj. Lo emitido en contingencia tiene un plazo para transmitirse —unos
8 días hábiles— y Hacienda rechaza por antigüedad pasados los 30 días. Un Vault
sellado un viernes por un reinicio, sin quien lo abra hasta el lunes, se come
tres días de ese presupuesto en silencio. **La mitigación es la alarma de
antigüedad de la cola (§7.2), no el desellado**: cualquier cosa que detenga la
firma —Vault, un certificado vencido, un disco lleno— se ve por el mismo sitio.

#### Reglas que no dependen del adaptador

- El `GET` de estado devuelve **los dos ambientes**, no el activo: RF-30 pide ver
  qué le falta a cada uno, y con un objeto singular la pantalla necesitaría dos
  llamadas y no podría decir «producción está listo, pruebas no».
- El archivo, el PIN y la contraseña **no tienen** endpoint de lectura. No existe
  el camino.
- No se registran en bitácora ni en trazas de error. Sí se registra **que** se
  usaron —quién pidió un token, quién reemplazó un certificado—, nunca su
  contenido.
- Subir, reemplazar o quitar credenciales es de **administrador**. Con eso el
  bloqueo por suscripción las alcanza sin tocar nada.
- Probar la conexión (RF-31) pide un token y lo descarta, con tiempo de espera
  explícito —el precedente es el adaptador de CABYS— y distinguiendo los tres
  desenlaces. Guarda `atv_verified_at` para que la pantalla pueda decir
  «verificadas el 3 de septiembre» en vez de obligar a probar a ciegas.

#### El ambiente activo

`fe_credentials` guarda credenciales **por** ambiente; cuál está en uso es otro
dato y vive en la configuración de la compañía, que es donde ya está hoy
(`settings.eInvoicing.environment`). RN-35 —confirmar y registrar el paso a
producción— es un cambio de estado sobre ese dato.

**Y el ambiente viaja también en la fila del documento**, no solo en la del
contador. Sin eso: cinco tiquetes de prueba quedan en cola sin firmar porque el
sandbox estaba lento, al día siguiente el administrador pasa a producción, el
trabajador toma la cola y toma las credenciales vigentes — cinco documentos con
efecto fiscal real que nadie quiso emitir.

#### El respaldo por compañía: lo público sí, los secretos no (decidido el 2026-09-06)

`company_dump.py` tiene un guardián que tumba `pytest` en cuanto aparece una
tabla sin clasificar, así que `fe_credentials` se clasifica **por columna y no
por tabla**, que es lo que el guardián no contemplaba y hay que enseñarle:

| Va en el respaldo | No va |
|---|---|
| `certificate_pem`, `certificate_name`, `expires_at` | `atv_password_encrypted` |
| `atv_user`, las marcas de tiempo | |
| `environment`, `key_custody` | |

**Con la llave en Vault, la columna que más costaba clasificar ya no existe.**
El `.p12` y el PIN no están en la base (§7.1), así que el volcado no puede
llevárselos aunque alguien los clasificara mal: es la diferencia entre una regla
y una imposibilidad. Queda una sola columna que descartar a mano, la contraseña
de ATV, y el motivo es el de siempre —en otra instalación, con otra
`FE_CRYPTO_KEY`, es un valor indescifrable que nadie distingue de uno bueno
hasta el día de transmitir—.

Lo que sí viaja es todo lo que puede volver solo, y **al restaurar la pantalla
dice qué falta cargar** (RN-47): la contraseña de ATV y **el certificado, que
hay que volver a subir para que su llave se importe al Vault de destino**. Un
respaldo que parece completo y no lo es solo se descubre cuando hace falta.

#### La identificación del emisor vive en `companies` (decidido el 2026-09-06)

Estaba en dos sitios y ninguno alcanzaba solo: `companies.identificacion` la pone
soporte al dar de alta pero es **opcional y sin tipo**, y `business.taxId` +
`business.taxIdType` de Configuración tienen el tipo pero los edita el
administrador del negocio.

Manda `companies`, con una columna `identification_type` nueva, y Configuración
la muestra **de solo lectura** (RN-45, RF-37). El argumento no es de orden sino
de consecuencia: el `.p12` se emite **a esa identificación** y el usuario de ATV
la lleva dentro de su nombre. Un campo editable deja que el negocio la haga
discrepar de su propio certificado, y ahí no se rechaza un comprobante: se
rechazan todos.

**Y esa mezcla quedó escrita** (T-916, cerrada el 2026-09-13). `companies` es de
las tablas con columnas en español, así que `identification_type` vive al lado de
`identificacion` en la misma tabla, y lo mismo pasa en `clients`. Era el precio
que T-916 ponía sobre la mesa; se decidió pagarlo y no renombrar. §3.9 tiene el
porqué y qué haría falta para volver a discutirlo.

#### La certificación previa en sandbox se avisa, no se impide (decidido el 2026-09-06)

Hacienda exige emitir una factura, un tiquete y una nota de crédito en pruebas
antes de producción (README §12). En F6 el paso a producción **avisa de los tres
y deja pasar**, con la bitácora de RN-35; la puerta dura entra en F7 (RN-46).

**Y entró (T-713, 2026-10-03):** `production_gate` cuenta los `accepted` en
`sandbox` por tipo, `PUT /fe/active` a producción responde
`production_gate_locked` con `missing`, y Configuración dice cuál falta.

El motivo es que en F6 no existe nada que contar: no hay emisión todavía. Un
candado construido acá nacería cerrado, sin forma de comprobar que abre, y la
primera vez que se ejercitaría sería con un cliente esperando.

#### Riesgo abierto: TRIBU-CR

`docs/hacienda/costa-rica/README.md` §12 deja pendiente confirmar si TRIBU-CR
—que reemplaza a ATV desde octubre de 2025— cambia URLs o credenciales.
Mitigación comprobable: **ambiente, `client_id`, realm y URL base salen de un
solo módulo**, y una prueba tumba `pytest` si el dominio de Hacienda aparece
escrito en cualquier otro sitio. Es el mismo patrón que ya sostiene
`test_error_codes.py`.

### 7.2 Emisión (F7 — ruta directa, decidida el 2026-10-03)

La ruta se decidió por la directa: VentaSys firma y transmite. Lo que pesó fue
lo que ya había —la llave en Vault, el IdP probado, el certificado y las
credenciales cargados por el usuario— y los comprobantes aceptados de
`docs/hacienda/costa-rica/XML-Ejemplos/`, que dan la forma exacta de la firma.
La tabla queda como registro de lo que se comparó:

| | Directo | Vía proveedor autorizado |
|---|---|---|
| Firma XAdES-EPES | nuestra | del proveedor |
| Cambios de esquema de Hacienda | los seguimos nosotros | los sigue el proveedor |
| Costo | cero por documento | mensual o por documento |
| Salir a producción | lento | rápido |
| Dependencia | ninguna | fuerte |

**Nada de lo que sigue depende de esa decisión.** El recorrido del documento, sus
estados, la numeración, la contingencia y lo que se guarda son iguales por las
dos rutas; lo que cambia es quién está del otro lado de los puertos. `EmisorFE`
terminó siendo cinco: `DocumentSigner` (firma un resumen), `HaciendaIdp` (el
token, de F6), `HaciendaReception` (`submit`, `status`), `CertificateParser` y
`TransmissionRepository`, más la fuente del comprobante (`ComprobanteSource`).
Con un proveedor autorizado cambian la firma, el IdP y la recepción, y el
recorrido no se entera.

#### Cómo quedó construida (2026-10-03)

| Pieza | Dónde | Lo que importa |
|---|---|---|
| La firma XAdES-EPES | `domain/fe_signature.py` | Envuelta, exclusiva, SHA-256, RSA PKCS#1 v1.5, política de la 4.4. **No firma**: arma los resúmenes y le pide a Vault la firma del `SignedInfo`. Canonicaliza con la biblioteca estándar (C14N 2.0), que sobre estos documentos coincide con la exclusiva 1.0; se comprueba contra `lxml` byte por byte y contra el XSD |
| El recorrido | `domain/fe_transmission.py` | Estados, pasos, las dos cadencias, qué falla detiene, la contingencia, la alarma y la puerta de producción. Sin base ni red |
| Los pasos | `use_cases/fe_transmission.py` | `SignDocument` → `SubmitDocument` → `PollVerdict`, cada uno una transacción; `ProcessDue` los encadena cuando salen bien; `RetryDocument`, `QueueSummary`, `ObservedContingency`, `ProductionGate` |
| El comprobante desde su origen | `persistence/sqlalchemy_fe_documents.py` | `SqlAlchemyComprobanteSource` lee la venta, la devolución, la nota o la compra (`_de_compra`, T-728) con el emisor de la configuración y el receptor de la ficha. Lo que falte es `document_invalid` con el código |
| Hacienda | `external/hacienda_reception.py` | `urllib`, como el IdP. 202 recibido; 400 → `ReceptionRejected` con `X-Error-Cause`; 401 → otro token; 403 → detenido; 404 al consultar → todavía no; 429/5xx/red → transitorio |
| El trabajador | `workers/fe_worker.py` | Un hilo del proceso de la API (`lifespan`), cada 5 s, una sesión y un `with compania(cid)` por compañía. `FE_WORKER=0` lo apaga |
| Los datos | migración 020 | El recorrido cuelga de `fe_documents` (estado, intentos, horas, motivo, llaves del almacén) y la bitácora va en `fe_document_events`. Lo numerado antes de la migración entra a la cola |
| El API | `/fe/queue`, `/fe/documents/{id}`, `/xml`, `/response`, `/retry` | Leer lo puede quien ve la factura; reintentar, el administrador |
| La prueba contra el stack | `tests/test_emision.py` | Con la Hacienda de mentira de `tests/stub_hacienda.py` en la pila de pruebas: un tiquete recorre la cola entera con Vault y MinIO de verdad |

**`ProveedorSistemas`** es `FE_PROVEEDOR_SISTEMAS` o, sin ella, la cédula del
propio emisor, que es lo que traen los comprobantes aceptados.

#### La numeración

El consecutivo son 20 dígitos: **sucursal (3) + terminal (5) + tipo (2) +
secuencia (10)**, y la secuencia es «dentro del tipo». De ahí que el contador
tenga **cinco dimensiones**:

```
(company_id, branch, terminal, document_type, environment) → última secuencia
```

Con menos, la serie nace con huecos. Escenario con un contador por terminal: se
emite un tiquete, luego una factura, luego otro tiquete → los tiquetes van 1, 3,
5 y las facturas 2, 4. Las dos series quedan con saltos, que es exactamente lo
que Hacienda rechaza («consecutivo fuera de orden»).

**El contador se confirma en la misma transacción que el documento.** Un contador
en transacción propia y corta no serializa las cajas, pero una venta que después
falla —por stock, por un total que no cuadra— deja el número consumido y abre un
hueco. Es el defecto 1 del proyecto otra vez, y el `UnitOfWork` que ya existe es
donde se hace comprobable.

**Un rechazo sí deja hueco, y es esperado.** La clave es la llave de idempotencia
de Hacienda: un comprobante rechazado no se reenvía con la misma clave, hay que
emitir otro con consecutivo nuevo. El número del rechazado queda fuera de la
serie aceptada por diseño de Hacienda, no por defecto nuestro, y hay que
documentarlo o el primer rechazo va a parecer un contador roto.

**Arranque de un negocio que ya facturaba** (RN-36 a RN-38, RF-32): el cliente
indica su oficina y la última secuencia por tipo, y el sistema continúa desde
ahí. Solo se puede subir, queda en bitácora, y una vez que el sistema emitió el
contador es suyo. **Es diseño y no está construido**: es T-616, en F6, y hasta
que exista un negocio que viene de otro sistema empieza su serie en 1, que
Hacienda rechaza por consecutivo repetido.

**Y hay un consecutivo que ya existe y no sirve para esto.** `sale_number` lo
fabricaba **el navegador**, con `yyyyMMddHHmmss` y el reloj del cliente. Dos
cajas cobrando en el mismo segundo chocaban contra `UNIQUE (company_id,
sale_number)` y una de las dos ventas se rechazaba en la cara del cliente.
**Decidido el 2026-10-03 (T-706): conviven.** El consecutivo es el número
fiscal y `sale_number` el recibo interno; lo pone `RegisterSale` con el reloj
del servidor —y un sufijo si ese segundo ya tiene venta— cuando no viene, y el
POS dejó de mandarlo.

#### La clave y la contingencia

La clave son 50 dígitos y su posición 42 es la **situación**: 1 normal, 2
contingencia, 3 sin internet. Esa clave es **contenido obligatorio de la
representación impresa** y se entrega en el mostrador, así que **se decide al
vender**, no al transmitir.

De ahí RN-43: **la contingencia es un modo del negocio**. Si las transmisiones
recientes vienen fallando, el POS está en contingencia y los documentos nuevos
nacen con situación 2; cuando Hacienda vuelve, sale del modo. No se le pregunta
al cajero y no se adivina por documento — y emitir con situación 2 cuando
Hacienda estaba arriba es causa de rechazo, así que la decisión tiene que salir
de un hecho observado y no de una precaución.

**Lo que sí se difiere es la firma**, no la clave. Son cosas distintas: la clave
es aritmética y se arma sin red; la firma necesita la llave y puede esperar al
momento de transmitir. Esa separación es la que hace que el adaptador de Vault
no agregue un modo de falla en el mostrador.

#### El recorrido y sus estados

```
numerado ──> firmado ──> enviado ──> aceptado
                │            │
                │            └──> rechazado        (respuesta final)
                │
                └──> reintentando ──> detenido     (necesita a una persona)
```

Cada uno se ve en la pantalla de facturas (RF-33). `reintentando` muestra el
último intento y el próximo; `detenido` muestra el motivo.

#### Dos ciclos, no uno

Son dos esperas distintas y confundirlas se paga de los dos lados:

| Ciclo | Cuándo | Cadencia |
|---|---|---|
| **Veredicto** | Hacienda ya recibió (202) | 10 s → 30 s → 1 → 2 → 5 min |
| **Reenvío** | No se pudo alcanzar a Hacienda | 5 → 15 → 30 min → … → 72 h |

El primero sale de `docs/hacienda/costa-rica/README.md` §8: tras el 202 hay que
esperar 5–10 s y «en condiciones normales la validación toma segundos». Con la
cadencia del segundo ciclo, una venta que Hacienda resolvió en tres segundos se
vería «pendiente» cinco minutos en la pantalla del cajero.

**Solo lo transitorio se reintenta** (RN-41). Un rechazo es una respuesta. Un
certificado vencido o unas credenciales rotadas son fallas nuestras y se
detienen en el primer intento: hacer backoff 72 horas sobre eso es demorar el
aviso tres días para llegar a la misma conclusión.

**Y agotar los reintentos no es rendirse** (RN-42): el documento pasa a
`detenido`, sigue transmitible a mano, y su antigüedad se ve. **La alarma de
antigüedad de la cola es una pieza, no un detalle**: es lo único que avisa antes
de que se acabe el plazo de contingencia, y lo que hace visible un Vault sellado,
un disco lleno o un certificado que venció el sábado.

#### Por qué polling y no callbacks

Hacienda soporta `callbackUrl` en el `POST /recepcion` y avisa ella, reintentando
tres veces (README §8). Es más barato que consultar. **Pero un POS en la LAN de
una tienda no tiene URL pública**, así que para este producto el mecanismo
primario es la consulta. En un despliegue hospedado el callback sí sirve y el
puerto tiene que admitir los dos sin cambiar el resto.

#### Lo que se guarda

El **XML firmado tal como se envió**, byte por byte —la firma cubre esos bytes,
regenerarlo da otra firma y deja de ser el documento— y la **respuesta de
Hacienda**, que va firmada por ella y es la prueba de la aceptación. Los dos por
**cinco años**, y los dos descargables (RF-34).

Las piezas que hacían falta en cualquiera de las dos rutas —la clave de 50
dígitos, el consecutivo de 20 sin huecos, el envío asíncrono con consulta de
estado y el modo «sin internet» para cobrar con Hacienda caída— están desde F7.
Quedan la entrega al receptor por correo (T-733) y el aviso por `callbackUrl`
(T-734).

**La situación es la 3, «sin internet», no la 2** (corregido al cerrar F7). El
anexo 4.4 (nota 3, inciso g, p. 67) reserva la 2 para el comprobante
electrónico que **sustituye uno físico** hecho a mano durante una caída —con la
referencia a ese provisional—; la 3 es la del que se generó electrónicamente
sin poder transmitirlo, que es el caso de VentaSys, y es la única con la que el
anexo admite una fecha de emisión anterior a la validación (p. 19). Y la decide
solo lo que es de Hacienda: `fe_documents.unreachable_at` anota cuándo no
contestó Hacienda o su IdP; Vault sellado o el almacén caído son nuestros y no
cambian la clave.

#### El tipo de comprobante se guarda en la venta (RN-85, T-723)

`sales.document_type CHAR(2) NULL` —`'01'` factura, `'04'` tiquete, nulo sin
facturación electrónica—, migración 014. Va en la venta y no en la tabla del
comprobante que traerán T-704 y T-705 porque **existe antes que él**: se decide
al cobrar, y el contador por tipo lo va a leer de ahí.

Lo decide el dominio, `domain/fe_document_type.py`, con tres entradas —lo que
pidió la caja, si la compañía factura electrónicamente y si hay receptor— y en
este orden:

1. Un valor que no es `'01'`, `'04'` ni —desde T-727— `'09'` se rechaza con
   `invalid_sale_document_type`, esté o no activa la facturación: es un cliente
   roto, no una preferencia.
2. Con la facturación apagada, nulo. **Se ignora, no se rechaza**: el dueño puede
   apagarla con una caja abierta, y rechazar esa venta sería cobrarle el cambio de
   configuración al cliente que está en el mostrador.
3. Sin tipo pedido, la sugerencia: factura con cliente, tiquete sin él. Es lo que
   recibe una pantalla abierta antes de activar la facturación.
4. Factura sin cliente, `invoice_needs_receiver`.

**«Hay receptor» es «hay un cliente de esta compañía».** `clients.identification`
es obligatoria, así que todo cliente registrado tiene la suya. El caso de uso
comprueba que el cliente **exista y sea de la compañía** con un puerto nuevo,
`ClientRepository.exists`: hasta ahora `client_id` pasaba derecho a la foránea,
que no sabe de compañías, y una venta podía colgar del cliente de otro negocio.
El **tipo** de identificación, que el XML también exige, no se mira acá: es la
mitad pendiente de T-617, y la venta no puede rechazarse por un dato que la
pantalla de clientes todavía no pide.

En el POS la misma regla vive en `$lib/domain/documentType.ts`, para que el
selector de la pantalla de cobro proponga lo mismo que el servidor va a aplicar.
Lo que el cajero eligió se guarda en la venta en espera; cambiar de cliente lo
descarta y vuelve a la sugerencia.

#### Un solo molde para lo que se imprime (RN-86, T-724)

El título del documento sale **de la venta**, no de la configuración:
`documentKind(sale)` reemplaza a `documentKind(settings)`. Antes, activar la
facturación convertía en «Factura electrónica» hasta las ventas de antes de
activarla.

Lo fiscal lo arma una función pura, `fiscalBlock(sale)`, y lo imprime **un solo
componente**, `FiscalBlock.svelte`, que usan las tres plantillas. Una prueba lee
las tres y falla si alguna no lo incluye: el día que se agregue una cuarta, se
entera la prueba y no el cliente.

El bloque tiene tres estados:

| La venta | Lo que imprime |
|---|---|
| Sin tipo | Nada. Es el documento de siempre, y su leyenda es la del dueño (T-304). |
| Con tipo, sin clave | «Pendiente de emisión». Es todo lo que hay hasta T-705. |
| Con clave | Tipo, consecutivo y clave juntos (Nota 1), actividad económica, y la leyenda de pruebas o la de la resolución. |

El tercero lee `einvoice` en el detalle de la venta, con `clave`, `consecutive`,
`environment`, `economic_activity` y `situation`. Viaja desde T-705 (2026-09-27)
en los tres detalles —venta, devolución y nota—; una venta con tipo de antes de
esa fecha no lo tiene y el bloque cae al segundo estado, que es la verdad.

**Lo que imprime además (T-731).** El resto de RN-86 sale de funciones puras de
`$lib/domain/documents.ts`, y las tres plantillas solo lo acomodan:

| Pieza | De dónde sale |
|---|---|
| Número de la cabecera | `documentNumber`: el consecutivo si lo hay, si no `sale_number`. Uno solo: el bloque ya no repite el consecutivo. |
| Identificación con su tipo | `issuerLines(settings, { activity })` para el emisor; `clients.identification_type` para el receptor (T-617). El nombre legal es el de `ID_TYPES`. |
| Actividad económica | `issuerActivity`: la del emitido, si no la configurada. |
| Condición de venta | `SALE_CONDITION_CASH`, `'01'`. Constante mientras no haya venta a crédito (T-729). |
| Moneda y tipo de cambio | la configurada; el tipo de cambio solo en colones (1), porque el del BCCR no existe todavía en el sistema. |
| Líneas | `documentLines`: número, CABYS, unidad, tarifa, impuesto y total de la línea. |
| Resumen | `documentSummary`: los renglones de `ResumenFactura`. Los descuentos son cero porque el POS no descuenta. |
| Monto en letras | `$lib/ui/amountInWords.ts`, en el idioma del documento. Son reglas, no frases: no caben en el catálogo. |

**El CABYS y la unidad se congelan en la línea** (`sale_details.cabys_code` y
`unit_of_measure`, migración 016), por la misma razón que la tarifa: la factura
reimpresa dice con qué se vendió, y el dueño puede reclasificar el producto
mañana. La nota de crédito los toma de la línea de la venta.

El bloque fiscal va **en dos partes**: arriba la clave, la referencia de una nota
y el aviso de pendiente o de pruebas —que no puede quedar escondido al pie—;
abajo, el **QR de la clave** en cuanto la hay y, solo si está autorizado, la
resolución y el portal donde se verifica. La prueba de las plantillas exige las
dos.

**El QR codifica la clave sola** —50 dígitos, nivel Q—, que es lo que lleva el de
la factura aceptada por Hacienda. Lo dibuja `$lib/ui/qr.ts` con
`qrcode-generator` como un solo `path` de SVG: nítido en el rollo y en la hoja,
igual en el servidor que en el navegador, y negro sobre blanco aunque la pantalla
esté en tema oscuro.

**El PDF del backend se quitó.** `GET /sales/pdf/{id}` dibujaba con reportlab un
cuarto documento sin emisor, sin desglose, sin idioma y con sus rótulos en
español (T-922). Para que dijera lo mismo que las plantillas habría que haberlas
escrito dos veces. El PDF sale de imprimir la plantilla, que es además lo que
RN-82 pide: se genera cada vez y no se guarda.

#### El comprobante numerado (T-704, T-705, migración 018)

```sql
CREATE TABLE fe_documents (
    id                INT AUTO_INCREMENT PRIMARY KEY,
    company_id        INT         NOT NULL,
    source_type       VARCHAR(10) NOT NULL,     -- 'sale', 'return', 'note', 'purchase'
    source_id         INT         NOT NULL,
    document_type     CHAR(2)     NOT NULL,
    environment       VARCHAR(12) NOT NULL,
    branch_id         INT         NOT NULL,
    terminal_id       INT         NOT NULL,
    sequence_number   BIGINT      NOT NULL,
    consecutive       CHAR(20)    NOT NULL,
    clave             CHAR(50)    NOT NULL,
    situation         CHAR(1)     NOT NULL,
    economic_activity VARCHAR(10) NULL,
    issued_at         DATETIME    NOT NULL,
    UNIQUE (company_id, clave),
    UNIQUE (company_id, environment, consecutive),
    INDEX (source_type, source_id)
);
```

**Aparte de la venta, y colgando de su origen**, porque nacen comprobantes de
tres flujos —la venta, la devolución con NC y la nota por monto— y un mismo
origen puede tener más de uno: un rechazo se corrige con otra clave, no
reescribiendo esta. El vigente es el último. Acá se van a colgar el estado del
recorrido (T-707) y el XML firmado.

**El contador es `fe_sequences`**, que la 011 dejó creada. La fila se crea con
`INSERT … ON DUPLICATE KEY UPDATE` y se lee con `FOR UPDATE`, dentro de la
transacción de la venta.

**Las piezas y quién las pone:**

| Pieza | De dónde |
|---|---|
| País, fecha | `506` y el día del sello del documento, que es hora de Costa Rica (`TZ` del contenedor) |
| Emisor | `companies.identificacion`, completada a doce (nota 4.1) |
| Consecutivo | los códigos de oficina de la sesión, el tipo y `fe_sequences` |
| Situación | `1`, normal, o `3`, «sin internet», cuando lo último que se intentó contra Hacienda no contestó y no volvió a contestar (`ObservedContingency`, RN-43) |
| Código de seguridad | ocho dígitos de `secrets`, detrás del puerto `SecurityCodes` |

`NumberDocument` (aplicación) se usa en dos tiempos: `prepare()` **antes** de la
transacción —sin cédula dice que no sin tocar existencias— y `number()` adentro.
Los tres casos de uso lo reciben como el libro: opcional, y sin él la venta con
tipo queda «pendiente de emisión», que es lo que pasaba antes.

#### La ubicación del emisor (T-722, RN-83)

Vive en la configuración, `business.location` —`province`, `canton`,
`district`, `neighborhood`, `otherSigns`—, y no en `companies`: el negocio se
muda y la corrige él, a diferencia de la cédula, que es la del certificado. No
reemplaza a `business.address`, que es la del tiquete.

El catálogo es el Excel oficial de Hacienda, y `generar_ubicaciones.py` genera
de él los dos lados —`domain/locations_data.py` y `$lib/domain/locationsData.ts`—
porque son dos aplicaciones que no se ven. La regla está escrita dos veces, una
por lado (`locations.py`, `location.ts`), como la del tipo de comprobante.

**La puerta es encender la facturación, no vender.** `save_settings` rechaza
encenderla sin cédula, correo y ubicación (`einvoicing_needs_issuer`, con la
lista entera) y rechaza siempre una ubicación a medias (`invalid_location`). La
vacía se guarda.

**La cédula que se imprime es la de `companies`.** `GET /settings/` la publica
en `issuer` y el POS la pone en el emisor (`withIssuer`). La corrige soporte,
por `PUT /support/companies/{id}/issuer`, con bitácora (RN-45).

#### De dónde nace cada comprobante (RN-87, T-725 a T-729)

El armador del XML ya sabe los siete (T-714, T-720). Lo que falta es **quién
los pide**, y cada uno tiene su sitio:

| Tipo | Se decide en | Se guarda en | Le falta al modelo |
|---|---|---|---|
| TE, FE | el cobro | `sales.document_type` | — (T-723) |
| FEE `09` | el cobro, con cliente extranjero | `sales.document_type` | **hecho (021, T-727)**: `products.tariff_heading`, `clients.foreign_address`, el tipo `05` y la partida congelada en `sale_details` |
| NC `03` | la devolución | la devolución, con la referencia a la venta | — |
| ND `02` | la factura abierta | una nota nueva, con la referencia | **hecho (017, T-726)**: `sale_notes` y sus líneas |
| FEC `08` | la compra | `stock_entries.document_type` | **hecho (021, T-728)**: el tipo `06` en proveedores; el negocio es el receptor del XML y el proveedor el emisor |
| REP `10` | el cobro de una venta a crédito | el abono | **la venta a crédito entera** |

**Cómo quedaron (2026-10-03).** La FEE exige la partida arancelaria solo a las
**mercancías** —CABYS 0 a 4, o sin CABYS—: el XSD la deja opcional porque los
servicios no la llevan. Rechaza las tarifas 01 y 11 (no tiene balde de no
sujeto) y pone al receptor `05` tal como se escribió, sin `Ubicacion`, con sus
`OtrasSenasExtranjero` y sin exoneración; el armador exige las dos cosas para
cualquier origen. La FEC se arma como la aceptada de `docs/`: **el proveedor es
el emisor y el negocio el receptor**, con la actividad del negocio en los dos
campos, la condición y el medio de pago de la compra, y la referencia tipo 14
—el respaldo del proveedor— con su número si lo dio. Su impuesto es el que se
tecleó en la línea (RN-53), con el código del producto si dice la misma tarifa
(`fe_tax_codes.purchase_line_code`); un 0 % sobre un producto del 13 % la
detiene, y elegir el código en la entrada es T-735. Antes de numerar se exige la
cédula del proveedor, que es el emisor del XML.

**La FEE entra por la misma regla que TE y FE.** `COUNTER_TYPES` pasa a ser tres,
y la sugerencia gana un caso: cliente con identificación de extranjero no
domiciliado (`05`) → FEE. La FE a ese cliente no se ofrece —no tiene cédula
costarricense— y el tiquete sí, por lo mismo que con cualquier cliente.

**Las notas referencian con la clave del original**, así que no se pueden emitir
antes de T-705: sin clave no hay a qué referirse. Lo que sí se puede antes es que
la devolución decida y guarde su tipo, igual que la venta.

**Los identificadores de Hacienda son seis, no cuatro.** Desde T-727
`check_identification_type` acepta los seis: la FEE necesita el `05` en el
cliente y la FEC el `06` en el proveedor. Es el mismo par de columnas en
`clients` y `suppliers`, y se amplió una vez para los dos. **El emisor sigue
siendo de los cuatro primeros** (`fe_issuer`): un extranjero no domiciliado o
un no contribuyente reciben comprobantes, no los emiten.

**El REP no tiene sobre qué montarse.** Nace de cobrar una venta con condición
`08` o `10` (RN-81), y el POS exige hoy el total en el mostrador (`check_payment`).
Vender a crédito es una fase propia —condición de venta, saldo del cliente,
abonos, qué pasa con la caja— y no está en el spec: hay que decidirla antes de
T-729, no dentro de ella.

#### Los comprobantes de cada compañía (RN-88, T-730)

`eInvoicing.documentTypes` en el JSON de `settings`: la lista de códigos
encendidos. Ausente es la de fábrica —TE, FE, NC, ND—. **No se valida al
guardar: se sanea al leer**, en los dos lados y con la misma regla
(`domain/fe_document_type.enabled_types` y `$lib/domain/documentType.ts`): se
tiran los códigos desconocidos, se agrega la NC si falta, y si no quedó ni TE
ni FE se vuelve a la de fábrica. Lo que no tiene flujo **no se tira**: se guarda
y su casilla no se mueve, para que el día que llegue el flujo ya esté. Es como el
resto de la configuración —`mergeSettings` nunca lanza— y hace imposible que una
fila escrita a mano deje al negocio sin poder vender.

Qué tiene flujo es **una lista del dominio** (`AVAILABLE`), no una casilla.
Al cerrar F7 son todos menos el REP: la ND entró tarde —tenía flujo desde T-726
y la lista no la traía, así que su casilla seguía bloqueada—, la FEE con T-727
y la FEC con T-728.

La regla de la venta gana una entrada, lo encendido: sin cliente sale TE si está
encendido y, si no, la venta necesita cliente (`invoice_needs_receiver`); con
cliente, FE si está encendida y si no TE; y pedir un tipo apagado es
`document_type_not_enabled`.

#### La nota de crédito cuelga de la devolución (RN-89, T-725)

`returns.document_type` y `returns.reference_code` (migración 015): `03` y el
motivo cuando la venta original fue comprobante, nulos cuando no. Lo decide el
dominio (`domain/fe_notes.py`) con el tipo **de la venta** —nunca con la
configuración de hoy— y con si es anulación.

**Anular es una devolución entera con otro motivo.** No hay un flujo aparte: el
mismo `RegisterReturn`, con `annul=True`, exige que la venta no tenga
devoluciones previas y que se devuelvan todas sus líneas, y guarda `01` en vez
de `06`. Así la caja, el inventario y el libro de la anulación son exactamente
los de una devolución total, que ya están probados, y no una segunda copia de
esa plata.

La nota se imprime con las mismas tres plantillas: `DocumentSheet` recibe la
devolución vuelta forma de venta, el título dice «Nota de crédito electrónica»,
el bloque fiscal agrega **la referencia** —tipo, número y fecha del original y
el motivo— y los renglones del efectivo recibido y el vuelto no salen, porque
una nota no cobra.

#### La ND y la NC por monto (RF-77, T-726)

**La plata, decidida por el usuario el 2026-09-26**: sin venta a crédito no hay
saldo del cliente donde dejar una nota, así que se mueve en el momento. La ND se
**cobra** al emitirla, con su medio de pago, y entra al turno como una venta; la
NC por monto se **reembolsa de la gaveta**, como una devolución —que ya sale
toda de la gaveta, sea cual sea el medio de la venta—.

**Una tabla nueva**, `sale_notes`, con sus líneas en `sale_note_lines`
(migración 017). No cuelga de la devolución porque no hay mercadería: es la otra
mitad de RN-87.

| Columna | Qué guarda |
|---|---|
| `sale_id` | el comprobante que corrige; tiene que tener tipo |
| `document_type`, `reference_code` | `02` o `03`, y el motivo de Hacienda |
| `reason` | por qué, en palabras de quien la emite |
| `payment_method` | cómo se cobró la ND; nulo en la NC, que sale de la gaveta |
| `subtotal`, `tax`, `total` | el desglose, como la venta |
| las líneas | producto, base, tarifa, impuesto, código de tarifa, CABYS y unidad **de la línea de la venta** |

**La nota ajusta líneas de la venta, no un monto suelto.** Cada línea hereda la
tarifa con que se cobró, y así una venta con tarifas mezcladas no obliga a
adivinar a cuál corresponde la corrección. El monto se escribe **con impuesto**
—es lo que se cobra o se devuelve en la mano— y el servidor lo parte: la base es
el monto entre uno más la tarifa, y el impuesto es la tarifa sobre la base.

**Solo el motivo `02`, corrige monto**, en las dos. Los otros tres de RF-77 no
tienen de dónde salir en un mostrador de contado: la ND y la NC **financieras**
(`10` y `09`) son intereses y descuentos por pronto pago, que solo existen con
venta a crédito (T-729); la NC por **exoneración posterior** (`12`) necesita la
exoneración en la línea de la nota y devolver solo el impuesto perdonado, y es su
propia tarea (T-732). **Bloqueada al cerrar F7:** el anexo solo dice cuándo se
usa el código 12, no cómo se arman sus líneas, y no hay una aceptada en
`docs/`. Con la exoneración en la línea la aritmética del anexo acredita la base
más el 4 %, no el 9 % que se devuelve; una línea exenta acredita el monto pero
lo declara como venta; anular y refacturar usa solo lo que ya existe. Elegir una
sin Hacienda o el contador es lo que RN-80 prohíbe.

**Tres reglas de plata:**

1. **Una NC no pasa de lo que queda de la línea**: lo cobrado, más lo que le
   subieron las ND, menos lo devuelto, menos las NC anteriores. Sin eso se podría
   reembolsar más de lo que el cliente pagó.
2. **Una línea con NC por monto ya no se devuelve**, y **una venta con notas por
   monto no se anula**: la devolución reembolsa el precio de la línea, y sumado a
   la NC reembolsaría dos veces la misma plata. Se rechaza con su código; la
   salida es otra NC por lo que falte.
3. **Solo el administrador las emite.** Mueven plata sin mercadería, que es
   justo lo que un arqueo no puede cruzar contra el inventario.

**El arqueo** suma las ND cobradas en efectivo y resta todas las NC por monto;
el corte Z las muestra en su propio renglón. **Las ventas netas** suman las ND y
restan las NC con las devoluciones. **El asiento** es el de la venta y el de la
devolución —la ND por el medio de pago, la NC contra la caja—, sin el par costo
/ inventario porque no hay mercadería, y con su propio origen (`note`) para que
el libro diga «Nota n.º 3» y no la confunda con una venta.

La nota se imprime con las tres plantillas en `/notas/{id}`, con la referencia al
original, igual que la NC de una devolución. Hasta T-704 su número es su id.

---


### 7.3 El almacén de documentos (se levanta en F6, lo llenan F7 y la recepción)

Entra **MinIO** al compose, hablado por la API de S3. No es para las
credenciales —la llave de firma va a Vault y el `.p12` no se guarda, §7.1—: es
para los documentos, que son cinco clases y todas tienen la misma forma —un
archivo que hay que devolver idéntico años después—:

| Clase | Qué es | Quién lo escribe |
|---|---|---|
| `signed-payload` | El XML firmado que se le mandó a Hacienda | F7, al firmar |
| `gov-response` | La respuesta **firmada** de Hacienda | F7, al consultar el veredicto |
| `received-comprobante` | El XML que manda un proveedor | Recepción |
| `received-response` | Nuestro mensaje receptor, firmado | Recepción |
| `received-pdf` | La representación gráfica que viene con el recibido | Recepción |

**Por qué no en MySQL.** No es el tamaño de uno sino el de todos: son tres
archivos por comprobante emitido y hasta tres por cada uno recibido, para
siempre. Un negocio mediano llega al millón de objetos antes de los diez años.
En columnas eso convierte cada respaldo de la base en horas, hace que un
`SELECT *` distraído se traiga cien megas a memoria, y mete al `mysqldump` —que
es cómo se restaura una compañía— en el camino crítico de algo que solo hace
falta cuando Hacienda pregunta.

**Por qué ahora y no en F7.** La ruta de emisión sigue sin decidir (§7.2:
firmamos nosotros o pasa por un proveedor autorizado), y **el almacén es de las
pocas piezas de F7 que no dependen de esa decisión**: con proveedor también hay
que conservar el XML firmado y el acuse, porque la obligación de custodia es del
emisor y no de quien transmite. Se puede construir hoy sin apostar a nada.

**Estos objetos NO se cifran, y es lo contrario de lo que se hace con el
`.p12`.** La asimetría es a propósito y vale escribirla: el `.p12` es un secreto
cuya pérdida se repone pidiendo otro certificado; el XML firmado es un documento
legal cuya pérdida no se repone con nada, y no es secreto —ya lo tienen Hacienda
y el cliente—. Cifrarlo agregaría un modo de falla —`FE_CRYPTO_KEY` perdida— que
borra documentos que la ley obliga a conservar. Se protege con permisos del
bucket y con el respaldo, no con una llave.

**La llave del objeto se deriva, igual que las otras dos:**

```
{company_id}/{environment}/{kind}/{yyyy}/{mm}/{clave}.{xml|pdf}
```

- **`company_id` primero** y puesto por el servidor, nunca por quien llama: es
  el mismo argumento del dato asociado del AES-GCM y del nombre de la llave de
  Vault. Y deja que el prefijo de una compañía sea lo que se copia, se borra al
  darla de baja o se le entrega al irse.
- **`environment` en la ruta.** La clave numérica se arma con el consecutivo, y
  el de pruebas y el de producción se numeran aparte: dos documentos distintos
  **pueden** tener la misma clave. Sin el ambiente en la ruta, un tiquete de
  ensayo pisa una factura real. Es la misma trampa que §7.1 ya obliga a evitar
  guardando el ambiente en la fila del documento.
- **Año y mes.** La custodia tiene plazo, y borrar lo que pasó el plazo así es
  listar un prefijo en vez de recorrer el bucket entero.
- **La clave numérica como nombre**, que es el identificador que usan Hacienda,
  el proveedor y nosotros. Buscar «el XML de esta factura» no necesita un índice.

**Se escribe una vez.** Un XML firmado que cambia deja de ser el que se firmó
—la firma no verificaría— y la respuesta de Hacienda para una clave es final; un
documento rechazado se corrige emitiendo **otra** clave, no reescribiendo esta.
Así que el puerto sube con `If-None-Match: *` y la segunda escritura de la misma
llave es un error, no un reemplazo silencioso. Sin eso, un reintento de la cola
que llegue tarde puede pisar el acuse bueno con uno viejo.

**El respaldo pasa a ser dos, y hay que escribirlo porque muerde.** Hasta hoy
respaldar la VM era el volumen de MySQL. Ahora es ese y el del almacén, y hay
que decir en el README que un respaldo que se lleve solo la base restaura un
sistema que cree tener sus comprobantes y no los tiene. Lo mismo para
`company_dump.py`: exportar una compañía es sus filas **y su prefijo**.

**`boto3` y no el SDK de MinIO.** Es la misma API y el adaptador no cambia si el
despliegue hospedado termina en S3, R2 o Backblaze; atarse al cliente de MinIO
sería elegir el proveedor desde el código. En la VM de un negocio, MinIO en su
contenedor; en el hospedado, lo que haya — y el puerto no se entera.

**Compañía y ambiente van explícitos en el puerto, no en un `ContextVar`**, por
la misma razón que `DocumentSigner`: quien más va a usar esto es el trabajador
de transmisión, que corre fuera de una petición y no tiene contexto que heredar.

**Lo que entrega F6 es el almacén, no su contenido.** En esta fase no hay
documentos todavía, así que lo que se construye es el contenedor en las dos
pilas, el puerto, el adaptador y la derivación de la llave — verificados contra
el MinIO de verdad, no contra un doble. Un adaptador que nunca corrió es lo que
T-602b ya dice que no se entrega.

## 8. Multi-idioma (F8)

Español, inglés y portugués (RNF-2, RN-22, RN-28 a RN-30). El español en
**usted**: el voseo que tiene hoy la interfaz venía de una suposición sobre el
mercado que el dueño del producto corrigió —en Costa Rica el ustedeo es más
común—, y además «Cobrá rápido» le suena extranjero a un usuario mexicano o
colombiano.

### 8.1 Lo que hay que mover

Medido el 2026-08-16 sobre el código real:

| Dónde | Cuánto |
|---|---|
| Nodos de texto en componentes | 223 |
| Atributos (`title`, `placeholder`, `label`, `aria-label`, `hint`) | 205 |
| Mensajes de acciones del servidor | 27 |
| **Mensajes que produce el backend** | **68** |
| Archivos con texto visible | 33 |
| Apariciones de voseo | 48, en 19 archivos |

Los 48 de voseo no se cuentan aparte: los 455 textos del frontend se tocan igual
al extraerlos, así que reescribirlos a usted en la misma pasada no cuesta nada
adicional. Hacerlo después sí, porque habría que volver a abrir los 33 archivos.

### 8.2 Los 68 mensajes del backend son el trabajo de fondo

Hoy FastAPI escribe la frase que ve el cajero:

```python
detail="Solo podés consultar tu propia caja."
detail=f"Stock insuficiente para {nombre}: quedan {e.available} y se piden {e.requested}."
```

Eso no se puede traducir desde el POS. La API pasa a devolver **código y datos**:

```json
{ "code": "insufficient_stock", "product": "Arroz Tío Pelón 1kg",
  "available": 2, "requested": 5 }
```

y el POS arma la frase con su catálogo.

**El trabajo ya está medio hecho y es el pago de F1.** El dominio lanza errores
tipados que llevan exactamente esos datos —`InsufficientStock(product_id,
available, requested)`, `TotalsMismatch(campo, declarado, calculado)`— y quien
los convierte en texto es el adaptador (`crud_*`). Cambiar el adaptador para que
emita el código en vez de la frase es un archivo por flujo, no una cacería por
todo el backend.

Con el código de error viajando, el mensaje del backend deja de ser un `detail`
suelto: se vuelve un contrato tan estable como el resto del API, y eso hace
posible probar «esta situación devuelve este código» sin comparar cadenas.

### 8.3 Dónde vive el idioma

```sql
ALTER TABLE companies ADD COLUMN locale       CHAR(5) NOT NULL DEFAULT 'es';
ALTER TABLE companies ADD COLUMN document_locale CHAR(5) NOT NULL DEFAULT 'es';
ALTER TABLE users     ADD COLUMN locale       CHAR(5) NULL;
```

- `companies.locale` — el idioma con el que arranca quien entra a esa compañía.
- `users.locale` — lo que esa persona prefiera. En nulo, hereda el de la compañía.
- `companies.document_locale` — **el idioma de la factura, que no es el de la
  pantalla** (RN-29). La factura es para el cliente y para Hacienda: una
  compañía costarricense emite en español aunque su cajero use el POS en
  portugués.

Las tres columnas entran en la migración de F2. No porque F2 las necesite, sino
porque una migración sobre tablas con datos es cara y hacer dos donde cabe una
es trabajo regalado.

### 8.4 Cómo se resuelve el idioma en cada petición

El `locale` efectivo entra en el JWT junto con la compañía y el rol, y de ahí lo
lee el `load` del layout. Así una pantalla nunca tiene que preguntarlo: llega ya
resuelto, igual que la moneda.

El orden es: lo que eligió la persona, si no lo de la compañía, si no `es`.

### 8.5 Biblioteca

Los criterios, en orden:

1. **Que funcione en el servidor.** El POS renderiza en SvelteKit y las acciones
   producen mensajes; una biblioteca que solo viva en el navegador deja fuera la
   mitad.
2. **Que el catálogo se compruebe al compilar.** Una clave que falta tiene que
   romper `npm run check`, no aparecer como `undefined` en la pantalla del
   cajero.
3. **Sin peso en el arranque.** El POS se abre en una caja modesta.

**Paraglide (Inlang)** es el candidato principal: compila los catálogos a
funciones, así que las claves quedan tipadas y solo viaja lo que se usa. La
alternativa es `typesafe-i18n`. La decisión se cierra al empezar la fase, con una
prueba de las dos sobre la pantalla de ventas —que es la más cargada— y no antes:
el ecosistema se mueve y elegir hoy por leer documentación es elegir a ciegas.

### 8.6 Lo que ya es independiente del idioma, y lo que no

**Ya lo es.** La moneda y el impuesto salen de Configuración desde el principio,
no del idioma. Es lo correcto: un negocio en Costa Rica que atiende en inglés
sigue cobrando en colones. Lo mismo el separador de miles.

**Todavía no.** `ui/format.ts` formatea fechas fijo en es-CR: `formatDate`,
`formatDateTime` y los nombres de mes salen escritos a mano. Pasan a depender
del locale.

**Los documentos.** Las tres plantillas llevan sus rótulos —«Factura»,
«Subtotal», «IVA», «Gracias por su compra»— dentro del componente. Se traducen
con el `document_locale`, no con el de la pantalla.

### 8.7 Cuándo hacerlo

**Cuanto antes, y la razón es aritmética.** F3 agrega el panel de soporte, F4 las
categorías de dos niveles, F5 el buscador de CABYS y F6 la pantalla del
certificado. Cada pantalla escrita antes de la extracción es una pantalla que
hay que volver a abrir después.

Lo mínimo razonable: que **el mecanismo exista antes de F3**, aunque los
catálogos de inglés y portugués se llenen más tarde. Escribir pantallas nuevas
con `t('ventas.cobrar')` desde el primer día cuesta lo mismo que escribirlas con
la cadena adentro; convertirlas después, no.

---

## 9. Fases

| Fase | Qué deja | Terminado cuando |
|---|---|---|
| **F0** Repositorio ✅ | `frontend/`, `backend/`, sin clones de referencia | El sistema levanta igual y no queda ninguna referencia a las rutas viejas |
| **F1** Arquitectura y pruebas ✅ | Capas, puertos, y la infraestructura de pruebas con cobertura exigida | El dominio no importa nada, los invariantes de `progress.json` siguen dando igual y la build se cae si baja la cobertura |
| **F2** Multiempresa ✅ | `company_id` en todo, filtro automático de lectura y sellado de escritura, login de dos pasos, migración | Las pruebas de cruce entre compañías dan 404 en todos los endpoints —y se ponen rojas si se desactiva el filtro |
| **F3** Soporte | Panel `/admin`, planes, estados, bitácora | Se puede dar de alta una compañía y operarla de punta a punta |
| **F4** Categorías | Dos niveles en catálogo, ventas e inventario | Un repuestero y un súper organizan su catálogo sin tocar código |
| **F5** Impuesto y CABYS | Tarifa por producto, búsqueda de CABYS, totales por línea | Una venta con 13 %, 2 % y 0 % cuadra y desglosa bien |
| **F6** Preparación FE | Certificado y credenciales ATV cifrados **por ambiente**, sucursales, terminales, actividad, arranque del consecutivo | Se suben el `.p12` y las credenciales de los dos ambientes, se ve el estado de cada uno, se prueba la conexión, se pasa a producción con confirmación y bitácora, y no hay forma de leer de vuelta ni el archivo ni el PIN ni la contraseña |
| **F7** Emisión | Ruta directa (T-701). Numeración, firma, envío, veredicto, reintentos, «sin internet», archivo, puerta de producción, y la FEE y la FEC. Cerrada el 2026-10-03 con lo abierto escrito en `task.md` | Una venta se emite, se ve pasar por sus estados hasta aceptada, y su XML firmado y la respuesta de Hacienda se pueden descargar |
| **F8** Multi-idioma | Español, inglés y portugués; el backend deja de escribir texto | Los tres catálogos tienen las mismas claves y la build se cae si alguien escribe una cadena dentro de un componente |
| **F10** Compras y cuentas por pagar — **terminada el 2026-09-12** | Módulos por plan; proveedores; la compra como entrada con documento, condición de pago y crédito fiscal por línea; costo promedio; abonos y antigüedad | Una factura XML de un proveedor entra como compra a crédito, su IVA aparece en el reporte por tarifa, un abono en efectivo sale de la caja y el arqueo cuadra |
| **F11** Contabilidad — **terminada el 2026-09-13** | Catálogo por compañía desde plantilla, asientos automáticos en la misma transacción, periodos con cierre, libros y borrador del D-104 | La venta 3×1450 deja un asiento que balancea, el mes se cierra, y una escritura con fecha adentro responde con código |
| **F12** Planilla | Empleados, puestos, jornadas con cortes, acciones de personal, tasas con vigencia, corridas congeladas, aguinaldo, vacaciones, liquidación, archivos para la CCSS y el INS, importación desde Excel y asiento de la corrida | Una corrida de dos empleados se paga, una incapacidad que cruza la quincena se parte sola, se cambia una tasa con vigencia futura y la boleta reimpresa da lo mismo |
| **F13** Proveedores — alcance decidido, va segunda | La ficha completa, los gastos por concepto, notas, adelantos, pagos a varias facturas, estado de cuenta y el buzón de comprobantes recibidos (task.md, F13) | Sus seis tareas de construcción verificadas (T-1302 a T-1306) |
| **F14** Compras a fondo — alcance decidido, va tercera | Costos adicionales al costo, descuento por línea, unidades con factor, moneda, orden de compra, reabastecimiento (task.md, F14) | T-1402 a T-1406 verificadas; la proporcionalidad (T-1407) espera al contador |
| **F15** Inventario — alcance decidido, va primera | Salidas con motivo, kárdex, toma física, mínimo por producto, existencias por sucursal, valorado y rotación (task.md, F15) | T-1502 a T-1507 verificadas, con marca, lote y vencimiento |

**F1 fue primero y no era opcional.** Todo lo que sigue toca dinero, existencias o
aislamiento entre compañías, y sin pruebas que fijen el comportamiento actual no
hay forma de saber si un cambio rompió algo: los invariantes de `progress.json`
se verifican hoy a mano, una vez, y eso no escala a seis fases más. Además, F2
mete un filtro por compañía en la capa de persistencia, que es justamente la
capa que F1 crea.

F4 y F5 pueden ir en paralelo. F6 depende de F2, que ya está.

**F8 lleva número alto pero conviene adelantarla.** El orden de las fases es de
dependencia, no de calendario, y multi-idioma no depende de ninguna: solo de que
existan las columnas, que entran con la migración de F2. Lo que sí importa es
que el **mecanismo** esté antes de F3, porque F3, F4, F5 y F6 agregan pantallas
y cada una escrita con la cadena adentro hay que volver a abrirla. Llenar los
catálogos de inglés y portugués puede esperar; escribir con `t('…')` desde el
primer día, no.

**El orden de ejecución es F10 → F11 → F6 → F7 → F12**, y no el de los
números. **Después siguen F15 → F13 → F14** (decidido con el usuario el
2026-10-03): inventario primero porque el kárdex y el mínimo por producto los
usan proveedores y compras. La tabla va numerada porque los números no se mueven —F8 ya sentó el
precedente: se ejecutó antes que F5 y se quedó en su casilla—; lo que manda es
este párrafo.

El primer borrador ponía los tres módulos después de F7, con el argumento de
que la emisión es lo único legalmente obligatorio. El argumento es cierto y
por eso mismo **no vende**: como todos los negocios están obligados, todos ya
lo resolvieron de alguna forma antes de conocernos. Emitir no gana el trato,
evita perderlo. Nadie está obligado a llevar su contabilidad en un programa, y
ahí es donde el producto cobra más y donde el cliente se queda: los libros de
tres años no se mudan de sistema.

Lo que sí hay que mirar es **de qué depende cada cosa**, y ahí no hay
conflicto: contabilidad necesita el IVA por tarifa (F5, hecho), el crédito
fiscal y el costo del producto (F10). Nada de F6 ni de F7. La compra desde XML
lee el comprobante **del proveedor**, que existe se emita o no, y el asiento
referencia la venta por su `id`, no por su número, así que cuando F7 cambie la
numeración (T-706) el libro no se entera.

Entre los módulos el orden sigue siendo de dependencia: el crédito fiscal sale
de las compras, así que F10 va antes que F11.

**F12 se queda de última, y a propósito.** No comparte nada con el POS —ni
productos, ni ventas, ni caja—, su soporte es estacional (todos necesitan el
aguinaldo la misma semana de diciembre) y es lo único que ata el producto a un
país. Adelantar contabilidad y adelantar planilla no son la misma apuesta.

**El 2026-09-27 F12 pasó delante de lo que falta de F7**, por decisión del
dueño del producto después de comparar los tres módulos con el ERP del que
viene VentaSys: compras y contabilidad ya estaban y planilla era el único
hueco entero. De F7 quedan la transmisión, su consulta y la contingencia
(T-707 a T-712); la numeración y la clave ya están, y nada de F12 depende de
ellas.

**Lo que decide cuánto cuesta postergar F6 y F7 es T-701**, no su número: vía
proveedor autorizado, F7 es un adaptador detrás de `EmisorFE`; directo, son
XAdES, el IdP de Hacienda y seguirle los cambios de esquema. Mientras esa
decisión siga abierta, F7 no es una fase grande sino una de tamaño
desconocido, y eso es lo que la manda al final.

Y no hay F9: el número de tarea lleva la fase —T-5nn, T-6nn— y el 9 lo ocupa
Transversal (T-9nn) desde F2. Saltarlo cuesta una línea; renumerar veinte
tareas cerradas, no.

---

## 10. Riesgos

| Riesgo | Mitigación |
|---|---|
| Una consulta sin filtro filtra datos entre compañías | Filtro automático en el ORM + pruebas de cruce en todos los endpoints |
| `with_loader_criteria` no cubre el SQL agregado de reportes ni los UPDATE masivos | Filtro escrito a mano en `crud_report.py`, con prueba propia. Revisar en cada agregado nuevo |
| El refactor de F2 toca todos los archivos y puede romper lo que ya funciona | Las pruebas de F1 son la red. Por eso F1 va antes: los invariantes de `progress.json` dejan de comprobarse a mano y pasan a correr solos |
| Reorganizar por capas (F1) es mover mucho código sin cambiar comportamiento, que es donde se cuelan los errores silenciosos | Pruebas de caracterización **antes** de mover nada, y se mueve capa por capa, no todo junto |
| La cobertura del 100 % empuja a escribir pruebas de relleno para pasar el umbral | El umbral cubre solo dominio y aplicación, que son código puro y de reglas. Ahí una función sin prueba es una regla sin verificar, no burocracia |
| `FE_CRYPTO_KEY` se pierde | **El arranque falla si no está o no mide 32 bytes**, para no enterarse al firmar. `key_version` en la fila permite rotarla como trabajo de fondo en vez de pedirle a cada cliente que vuelva a subir su certificado. Se guarda fuera del repositorio y fuera de la base |
| **Vault sellado con el backend arriba**: se sigue vendiendo y numerando, y la cola de transmisión crece sin que nada falle a la vista | La alarma de antigüedad de la cola (§7.2). No es el desellado: cualquier cosa que detenga la firma —Vault, un certificado vencido, un disco lleno— se ve por el mismo sitio, y avisa antes de que se acabe el plazo de contingencia |
| **TRIBU-CR** cambia URLs o credenciales de ATV (README §12 lo deja pendiente de confirmar) | Ambiente, `client_id`, realm y URL base salen de **un solo módulo**, y una prueba tumba `pytest` si el dominio de Hacienda aparece escrito en otro sitio |
| **Un comprobante rechazado no tiene salida**: el rechazo es final, la clave no se reusa y corregir el dato no llega al XML firmado | Abierto: T-736, que pide decisión. Hasta entonces el expediente lo muestra con lo que dijo Hacienda |
| **La situación «sin internet» por fallas nuestras**: Vault sellado declararía ante Hacienda una caída que no hubo | `unreachable_at` anota solo lo que no contestó Hacienda o su IdP; la prueba de Vault sellado comprueba que no lo toca |
| **Un turno de la cola sin presupuesto**: con Hacienda lenta y muchas compañías, el turno dura más que la cadencia | Abierto: T-737 |
| **El recorrido solo se probó contra la Hacienda de mentira** | El XML real de la FEE y la FEC se valida contra su XSD en `test_emision.py`; lo que el XSD no ve —la política de firma, `ProveedorSistemas`— lo juzga el sandbox real, que hace el usuario con sus credenciales antes de pasar a producción |
| **El certificado vence sin que nadie mire** y la emisión se detiene | Aviso 30 días antes (T-606) y estado `detenido` con su motivo en la lista de RF-35. `expires_at` guarda la hora, no solo el día |
| Diferir la firma alarga la ventana entre emitir y transmitir, y la contingencia tiene plazo | El plazo se vigila explícitamente: la antigüedad de la cola es visible y alarma antes de los 8 días hábiles. Hacienda además rechaza por antigüedad mayor a 30 días |
| El API de CABYS no responde | Caché local; la venta nunca depende de él |
| Borrar los clones de referencia | Están en GitHub y el análisis quedó escrito en `progress.json` y en `backend/README.md` |
| El impuesto por línea toca dinero ya verificado | Los invariantes de `progress.json` se recalculan y se documentan de nuevo |
| Un mapeo incompleto detiene una venta, porque el asiento va en la misma transacción | La cuenta «por clasificar» (RN-59): el asiento siempre existe y balancea; lo que falta se ve en rojo en contabilidad, no en la caja |
| Una tasa de la CCSS o un tramo de renta cambia y nadie lo siembra | Tablas con vigencia y `verified_at` visibles (RN-67); la pantalla de planilla avisa cuando la vigencia más reciente tiene más de seis meses; soporte actualiza para todas las compañías desde el panel |
| Planilla ancla el producto a un país | Las fórmulas reciben las tablas por parámetro y no conocen ningún porcentaje; el país es una columna. Otro país es sembrar, no programar —aunque no se construya— |
| El promedio ponderado con existencias negativas o con una compra anulada | Regla escrita y probada: existencia ≤ 0 → el costo es el de la compra; anular no deshace el promedio (RN-57) y la siguiente compra lo corrige. Está en la tabla de casos de `weighted_average_cost` |
| El formato del archivo de la CCSS no se conoce hasta leer la especificación | T-1211 empieza por leer el material oficial, como T-702 con los XSD; el archivo sale de un adaptador con prueba contra un ejemplo real |
| Cerrar un periodo por error, sin poder reabrir | La confirmación muestra el resumen del periodo y el saldo de «por clasificar» antes de cerrar; lo que quede mal se ajusta en el siguiente, que es lo que un contador hace de todos modos |
| `sales.payment_method` es texto libre y el mapeo necesita un conjunto cerrado | T-1104 lo cierra a un catálogo de valores antes de mapear; un valor desconocido va a «por clasificar», no rompe la venta |

---

## 11. Módulos por plan (F10–F12, QA-01)

> **Desde QA-01 (2026-10-03) cada sección del POS es un módulo** y los planes
> son paquetes: doce banderas en `plans` (migración 022, `domain/modules.py`
> con `MODULES`, `BASE` y `PACKAGES`). Lo de abajo cuenta cómo nacieron las
> tres primeras y sigue valiendo para las doce: el plan decide, se aplica en el
> servidor solo a lo que escribe, y el menú muestra con candado. Lo que agregó
> QA-01: `BASE` —lo que el POS tuvo siempre— nace encendido en los planes que
> ya existían y en los que crea `bootstrap.py`; proveedores es su propio módulo
> y la entrada de inventario pide inventario, proveedores si nombra uno y
> compras si es a crédito; anular una factura es del módulo de facturas y
> devolver, del de devoluciones; reportes solo se apaga en el menú, porque no
> escribe.

Compras, contabilidad y planilla se venden aparte, y el sistema ya tiene el
lugar donde se dice qué se vende: `plans`. `factura_electronica` es una bandera
del plan desde F2, y estos tres son tres banderas más. No hay tabla nueva ni
interruptor por compañía (RN-51): dos sitios para la misma verdad —el plan
dice una cosa y la compañía otra— es donde se separan, y el que mira soporte
es el plan.

```sql
-- 008-modulos-por-plan.sql
ALTER TABLE plans
    ADD COLUMN purchases  TINYINT(1) NOT NULL DEFAULT 0,
    ADD COLUMN accounting TINYINT(1) NOT NULL DEFAULT 0,
    ADD COLUMN payroll    TINYINT(1) NOT NULL DEFAULT 0;
```

Las tres en inglés: la excepción de §3.9 es de las columnas que ya existen, no
una licencia para las nuevas (T-601). `factura_electronica` se queda como está
por la misma decisión.

**Cómo se aplica.** Una dependencia `require_module("accounting")`, al lado de
`get_current_user`, que lee el plan de la compañía **en cada petición**. No va
en el token por la misma razón que el estado de la suscripción (§4.4): ahí
quedaría congelado hasta el siguiente login, y el cliente que acaba de subir
de plan tendría que salir y volver a entrar para ver lo que pagó. Se aplica a
las **escrituras** de las rutas del módulo; las lecturas quedan libres (RN-50),
porque lo que ya existe es de la compañía y tiene que poder consultarse y
exportarse siempre. La respuesta es `403` con `module_not_in_plan` y
`{"module": "accounting"}` —el token vale, lo que no vale es para esto—, igual
que las dos puertas de soporte.

**En el POS**, la carga que ya trae el estado de la suscripción trae también
`modules: {purchases, accounting, payroll}`; el `+layout.server.ts` arma la
navegación con eso, y cada `action` de un módulo pasa por `requireModule(...)`
además de `requireAdmin`. Esconder la entrada del menú es cortesía; el
servidor es el control.

**En el panel de soporte**, el formulario de planes gana las tres casillas y
el listado de compañías (RF-5) muestra los módulos de cada una. Cambiar el plan
de una compañía ya queda en bitácora (RF-7); no hace falta nada nuevo.

**En el simulado**, el plan de la primera compañía trae los tres módulos y el
de la segunda ninguno: así la prueba de punta a punta tiene con qué comprobar
el rechazo sin dar de alta nada.

---

## 12. Compras y cuentas por pagar (F10)

### 12.1 La compra es la entrada de mercadería

`stock_entries` ya es un documento y no un ajuste: guarda proveedor (como
texto), número de factura, quién y cuándo, y se puede anular. Le faltan tres
cosas —a quién de verdad, con qué condición de pago y con qué impuesto por
línea— y con ellas es una compra (RN-52). Se extiende esa tabla en vez de crear
`purchases` por tres razones:

1. El lector de XML de Hacienda (`lib/server/import/hacienda.ts`) **ya produce
   una entrada** a partir de la factura del proveedor, y el invariante «entrada
   XML 79 800» la fija. Con una tabla nueva habría que mantener dos caminos que
   hacen lo mismo.
2. La anulación ya existe y recorre las líneas para revertir el stock. Una
   compra anulada tiene que revertir lo mismo más la cuenta por pagar.
3. Dos tablas son dos verdades: una entrada con compra y una compra sin
   entrada son estados que no significan nada y que alguien tendría que
   impedir.

Una entrada con `supplier_id` nulo sigue siendo una entrada: las que ya
existen, las de ajuste, las de un proveedor que no se quiso registrar. No
generan cuenta por pagar ni crédito fiscal y el reporte de compras las deja
fuera. La columna `supplier` de texto se conserva para leer el histórico; las
compras nuevas la llenan con el nombre del proveedor por si el registro se
desactiva.

### 12.2 Modelo de datos

```sql
-- 009-compras.sql
CREATE TABLE suppliers (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    company_id          INT          NOT NULL,
    identification_type CHAR(2)      NULL,       -- 01/02/03/04, la lista de Hacienda (T-621)
    identification      VARCHAR(30)  NULL,       -- NULL: proveedor informal
    name                VARCHAR(160) NOT NULL,
    email               VARCHAR(160) NULL,
    phone               VARCHAR(30)  NULL,
    payment_terms_days  INT          NOT NULL DEFAULT 0,   -- 0 = contado
    is_active           TINYINT(1)   NOT NULL DEFAULT 1,
    created_at          DATETIME     NOT NULL,
    -- La misma identificación es el mismo proveedor: el XML llega con ella y es
    -- como se lo reconoce sin preguntarle a nadie. NULL no choca con NULL.
    UNIQUE KEY uq_suppliers_identification (company_id, identification),
    INDEX idx_suppliers_name (company_id, name),
    CONSTRAINT fk_suppliers_company FOREIGN KEY (company_id) REFERENCES companies (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

ALTER TABLE stock_entries
    ADD COLUMN supplier_id   INT           NULL,             -- NULL: entrada, no compra (RN-52)
    ADD COLUMN document_key  CHAR(50)      NULL,             -- clave de Hacienda, cuando hay XML
    ADD COLUMN document_date DATE          NULL,
    ADD COLUMN payment_terms VARCHAR(10)   NOT NULL DEFAULT 'cash',   -- 'cash' | 'credit'
    ADD COLUMN due_date      DATE          NULL,
    ADD COLUMN subtotal      DECIMAL(12,2) NOT NULL DEFAULT 0,
    ADD COLUMN tax           DECIMAL(12,2) NOT NULL DEFAULT 0,
    -- total_cost ya existe y pasa a valer subtotal + tax. El nombre se queda:
    -- lo leen el lector de XML, la anulación y una prueba de caracterización.
    ADD INDEX idx_stock_entries_supplier (company_id, supplier_id, status),
    ADD INDEX idx_stock_entries_due (company_id, due_date),
    ADD CONSTRAINT fk_stock_entries_supplier FOREIGN KEY (supplier_id) REFERENCES suppliers (id);

ALTER TABLE stock_entry_details
    ADD COLUMN tax_rate   DECIMAL(5,2)  NOT NULL DEFAULT 0,    -- la del documento (RN-53)
    ADD COLUMN tax_amount DECIMAL(12,2) NOT NULL DEFAULT 0;

-- El producto no sabía cuánto costó. Promedio ponderado, a dos decimales como
-- todo lo demás (RN-54).
ALTER TABLE products
    ADD COLUMN cost DECIMAL(12,2) NOT NULL DEFAULT 0;

CREATE TABLE supplier_payments (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    company_id       INT           NOT NULL,
    supplier_id      INT           NOT NULL,
    entry_id         INT           NOT NULL,     -- el abono es a UNA compra (RN-55)
    amount           DECIMAL(12,2) NOT NULL,
    method           VARCHAR(20)   NOT NULL,     -- 'cash' | 'transfer' | 'other'
    reference        VARCHAR(100)  NULL,         -- número de transferencia, cheque
    cash_movement_id INT           NULL,         -- si salió de la caja (RN-56)
    user_id          INT           NOT NULL,
    paid_at          DATETIME      NOT NULL,     -- la pone el servidor
    INDEX idx_supplier_payments_entry (entry_id),
    INDEX idx_supplier_payments_supplier (company_id, supplier_id, paid_at),
    CONSTRAINT fk_sp_company  FOREIGN KEY (company_id)       REFERENCES companies (id),
    CONSTRAINT fk_sp_supplier FOREIGN KEY (supplier_id)      REFERENCES suppliers (id),
    CONSTRAINT fk_sp_entry    FOREIGN KEY (entry_id)         REFERENCES stock_entries (id),
    CONSTRAINT fk_sp_movement FOREIGN KEY (cash_movement_id) REFERENCES cash_movements (id),
    CONSTRAINT fk_sp_user     FOREIGN KEY (user_id)          REFERENCES users (id_user)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;
```

El abono es **por compra** y no «a cuenta» a propósito: un abono a cuenta que
se reparte entre facturas (PEPS de deudas) necesita una regla de reparto, y la
regla de reparto es lo primero que un proveedor discute. Con el abono atado a
un documento, el saldo de cada factura es un hecho y el del proveedor es una
suma.

### 12.3 Dominio y aplicación

`domain/purchases.py`, puro, con su tabla de casos:

| Función | Regla | Casos que la prueban |
|---|---|---|
| `weighted_average_cost(stock, cost, qty, unit_cost)` | RN-54; existencia ≤ 0 → `unit_cost` | 10 u a 100 + 10 u a 120 → 110; 0 u + 5 a 80 → 80; −3 u + 10 a 50 → 50; redondeo a 2 |
| `purchase_totals(lines)` | RN-53: suma línea por línea, por tarifa | las mismas tablas de `sale_totals` (§6.3), con tarifas mezcladas |
| `remaining_balance(total, payments)` | RN-55 | sin abonos → total; con abonos → resta; nunca negativo |
| `apply_payment(balance, amount)` | RN-55: lanza `PaymentExceedsBalance` | 800 sobre 1 000 → 200; 1 001 sobre 1 000 → error |
| `aging_bucket(due_date, today)` | RF-44 | 0–30, 31–60, 61–90, > 90; sin vencimiento → 0–30 |

Puertos: `SupplierRepository`, `SupplierPaymentRepository`; `StockEntryRepository`
gana los campos nuevos. Casos de uso:

- `RegisterPurchase` **es** `RegisterStockEntry` con proveedor, documento y
  condición: aplica el stock igual que hoy, actualiza `products.cost` con el
  promedio, calcula el vencimiento desde `payment_terms_days` y deja la cuenta
  por pagar implícita (saldo = total − abonos). Con condición de contado, el
  pago se registra en el mismo acto como un abono por el total.
- `PaySupplier`: comprueba el saldo; si el método es efectivo, exige un turno
  de caja abierto y escribe el movimiento de salida antes de guardar el abono
  —el abono lo apunta—, todo en la misma transacción (RN-56). Sin turno
  abierto, `cash_no_open_session`.

  **El motivo del movimiento lo arma el POS y viaja en `reason`.** La versión
  anterior de este párrafo decía que lo escribiera el backend —«Pago a
  ‹proveedor›, factura ‹n›»— y eso es texto para una persona escrito fuera de
  la interfaz: lo prohíbe RN-30 y dejaría a un cajero brasileño con la mitad
  del arqueo en español. Es además de donde ya sale el motivo de cualquier otro
  movimiento de gaveta.

  Reutiliza `AddCashMovement`, que ganó un `apply()` que no confirma: así las
  dos comprobaciones del turno —que haya uno abierto y que alcance el
  efectivo— son literalmente las mismas de cualquier salida de caja, porque es
  la misma plata.
- **Anular una compra es `CancelStockEntry`, extendido** —no un `VoidPurchase`
  aparte, por lo mismo que la compra es la entrada (§12.1): es el mismo acto
  sobre la misma fila, y dos caminos serían dos sitios donde escribir la regla
  de los abonos—. Rechaza si los hay (`purchase_has_payments`); si no, revierte
  el stock como siempre, marca `anulada` y escribe en bitácora, todo en una
  transacción. **No recalcula el costo promedio**: hacerlo exige rehacer todas
  las compras posteriores del mismo producto en orden, y el promedio móvil no
  guarda de dónde vino cada céntimo. La siguiente compra lo corrige sola; la
  pantalla lo dice al anular.

  Los abonos se consultan **siempre**, sin mirar antes si la entrada tiene
  proveedor: una que no es compra no tiene abonos y la respuesta es la lista
  vacía. Condicionarlo a `supplier_id` sería confiar en que esa columna y la
  tabla de abonos nunca se contradigan, y la que manda es la tabla.

  El motivo es obligatorio **solo si es compra** (RF-46): la pantalla de
  entradas nunca lo pidió. Se comprueba después de anular en memoria, que es
  cuando se sabe cuál de las dos es, y por eso el cuerpo del POST es opcional.
  Código: `void_reason_required`.

**Una compra de contado se paga en el mismo acto, pero solo si se dice cómo.**
`payment_terms` dice **cuándo** se paga y `payment_method` **cómo**: son dos
cosas distintas y el XML de Hacienda solo trae la primera —`CondicionVenta` 01
es contado y no dice con qué—. Sin método, la compra queda con saldo y se abona
desde cuentas por pagar; inventarle uno sería adivinar de dónde salió la plata,
y adivinar «efectivo» descuadra un arqueo. Con método, el abono entra en la
transacción de la compra, así que una de contado pagada en efectivo **sin turno
abierto no entra, ni la mercadería**: la compra y el pago son el mismo hecho, y
registrar una y no el otro deja una deuda que no existe.

### 12.4 API y pantallas

```
GET  /suppliers                      lista, con saldo
POST /suppliers · PUT /suppliers/{id}  admin
POST /inventory/entry                admin · la vista previa confirmada. Con
                                     `supplier_id` es una compra y exige el
                                     módulo; sin él, la entrada de siempre
                                     (T-1011b). También recibe lo que el BFF
                                     sacó del XML: proveedor, condición y
                                     líneas con su impuesto
GET  /inventory/entries              lista entradas y compras. No se agregó un
                                     `GET /purchases` aparte: no lo pide
                                     ninguna pantalla (T-1012)
POST /inventory/entry/{id}/cancel    admin · {reason} opcional, y obligatorio
                                     si la entrada es compra (T-1011). No hay
                                     `/purchases/{id}/void`: es el mismo acto
                                     sobre la misma fila
POST /purchases/{id}/payments        admin · {amount, method, reference, reason}
                                     `reason` es el motivo del movimiento de
                                     caja, armado por el POS (RN-30)
GET  /payables?supplier_id=          saldos por compra y antigüedad. Prefijo
                                     propio y sin `require_module`: leer se
                                     puede siempre (RN-50) y F11 lo lee para
                                     el asiento sin entrar por compras
GET  /reports/purchases?from=&to=    base e impuesto por tarifa (RF-45), por
                                     **fecha del documento**
```

**No hay un `POST /purchases` aparte: la compra se registra por
`POST /inventory/entry` con `supplier_id`**, que es la consecuencia directa de
§12.1 —la compra es la entrada—. Ese endpoint exige el módulo `purchases`
**solo cuando el cuerpo trae proveedor** (T-1011b), y eso no cabe en una
dependencia de ruta porque decide antes de que el cuerpo exista: la
comprobación vive en el endpoint, apoyada en `exigir_modulo()`. Ponerla como
dependencia le cerraría el inventario a quien bajó de plan (contra RN-50); no
ponerla lo dejaría registrando compras sin el módulo (contra RN-49). En el POS, la pantalla de entradas de
`/inventario` **es** la de compras: gana el selector de proveedor, el documento,
la condición de pago y la tarifa por línea, y conserva la vista previa (§8,
regla 6). Nuevas: `/compras/proveedores` y `/compras/cuentas-por-pagar`
(saldos, antigüedad, abonar). El reporte de compras va con los demás, en
`/dashboard`.

El lector de XML pasa a extraer, además de las líneas: `Emisor` (tipo y número
de identificación, nombre), `Clave`, `NumeroConsecutivo`, `FechaEmision`,
`CondicionVenta` (`01` contado, `02` crédito) con `PlazoCredito`, y por línea
`Impuesto/Tarifa` y `Impuesto/Monto`. Si el proveedor no existe, la vista
previa lo muestra como «nuevo» y se crea al confirmar (RF-42).

### 12.5 Códigos de error

`supplier_inactive`, `purchase_has_payments`, `payment_exceeds_balance`. Cada
uno en los cuatro lugares.

**Dos de esta lista no existen, y es a propósito** (T-1010):

- `cash_session_required` **es `cash_no_open_session`**, que ya estaba. Dos
  códigos para el mismo hecho es peor que uno solo, y la frase que ya existía
  sirve igual acá.
- `duplicate_supplier_document` tampoco hizo falta: lo que cambió no es el
  código sino **con qué se compara**. `duplicate_document` ahora lleva el
  proveedor, porque la factura 1234 de un mayorista no es la 1234 de otro.

**Y seis que sí nacieron.** Con la anulación (T-1011): `purchase_has_payments`
—con **cuántos** abonos, porque deshacer uno o siete no es la misma tarea— y
`void_reason_required`. Con los abonos (T-1010): `payment_not_positive` —cero pasa
la prueba del saldo sin problema y dejaría una fila que no significa nada—,
`invalid_payment_method` —un método mal escrito se escapa del `if` del efectivo
y el turno cierra con un sobrante igual a lo que se pagó—, `purchase_cancelled`
y `payment_failed`. Los dos primeros se levantan desde una tabla
(`codigos[e.code]`) igual que los de `InvalidMovement`, así que van declarados
en `test_error_codes.py`: el AST no los ve.

Abonar a una entrada **sin proveedor** no tiene código propio: no genera cuenta
por pagar (RN-52), así que desde cuentas por pagar no existe y responde
`entry_not_found`. Es el mismo criterio por el que un proveedor de otra
compañía responde «no está» y no «no es suyo» (RNF-1).

**Y cuatro más, que aparecieron al escribir T-1007** y que esta lista no tenía:

| Código | Cuándo | Datos |
|---|---|---|
| `supplier_not_found` | Pedir o editar uno que no existe —o que es de otra compañía, que para esta sesión es lo mismo (RNF-1)— | `supplier_id` |
| `supplier_identification_taken` | La misma identificación es el mismo proveedor: dos fichas del mismo mayorista se reparten sus compras y ninguno de los dos saldos es el que se le debe | `identification`, `name` de quien ya la tiene |
| `invalid_identification_type` | No es uno de los cuatro de Hacienda | `identification_type` |
| `identification_required` | Vino el tipo sin el número: un «02» sin cédula jurídica no sirve ni para emitir ni para reconocerlo en un XML | — |

Los dos últimos van **sin prefijo de proveedor** a propósito: `companies`
(T-621) y `clients` (T-617) tienen el mismo par de columnas y les sirve el
mismo «no».

### 12.6 Decisiones

| Tema | Qué se decidió | Por qué | Estado |
|---|---|---|---|
| Compra vs. entrada | La compra es la entrada, extendida | §12.1: un solo camino, una sola anulación, el lector de XML ya está | tomada |
| Costeo | Promedio ponderado móvil, en el producto | PEPS exige capas por lote y devoluciones que las deshacen; con 5 000 productos es donde se descuadra. Hacienda acepta los dos | tomada |
| Abonos | Por compra, no a cuenta | El reparto es lo primero que se discute; atado al documento, el saldo es un hecho | tomada |
| Efectivo | Sale de la caja abierta o no sale | RN-56: lo que no está en un turno no aparece en un arqueo | tomada |
| Anular | Solo sin abonos; no deshace el promedio | Rehacer el promedio hacia atrás exige rehacer la historia; la siguiente compra lo corrige | tomada |
| Devoluciones a proveedor | Fuera, con la compra preparada para recibirlas | Tres efectos a la vez (stock, saldo, crédito fiscal) y ningún caso real todavía | tomada |

### 12.7 Costes medidos antes de empezar

- `test_esquema.py`: dos tablas y tres `ALTER`, modelo y migración iguales.
- `test_aislamiento.py`: nueve rutas nuevas que declarar y probar.
- `test_error_codes.py`: cinco códigos, cuatro lugares cada uno.
- `test_ports.py`: dos puertos nuevos y uno que cambia de firma.
- `company_dump.py`: `suppliers` y `supplier_payments` **viajan**; se clasifican
  en el mismo commit que las crea.
- Cobertura: `domain/purchases.py` nace con su tabla de casos.
- El simulado: nueve endpoints, proveedores y una compra a crédito en el seed,
  `SEED_VERSION` sube.
- Catálogo `purchases.json` en `messages/es/` **y** en `project.inlang/settings.json`.
- El invariante «entrada XML 79 800» se conserva: el lector agrega campos, no
  cambia cantidades. `test_characterization.py` lo vigila.

---

## 13. Contabilidad (F11)

### 13.1 El asiento va en la misma transacción, y nunca falta

Había dos formas de generar los asientos automáticos: **en la misma
transacción** del evento, o como una **proyección** posterior que lee los
eventos y escribe el libro. La proyección tiene una virtud real —se puede
borrar y rehacer cuando se corrige el mapeo— y un defecto que la descarta:
admite el estado «venta sin asiento», que es exactamente lo que un libro no
puede tener. Un cajero que vende a las 11:59 y un contador que cierra el mes a
las 12:00 no pueden depender de que una tarea de fondo haya corrido.

La objeción a la transacción es que un mapeo incompleto detendría la venta, y
eso viola RNF-4. La salida es que el mapeo **no pueda estar incompleto**: cada
papel que un evento necesita y no tiene cuenta asignada va a una cuenta de
sistema, **«por clasificar»** (RN-59). El asiento balancea siempre, existe
siempre, y el contador ve en rojo un saldo que no debería existir. Corregirlo
es un asiento de ajuste que mueve ese saldo a la cuenta correcta, y eso
recupera lo bueno de la proyección sin su agujero.

Otras cuatro decisiones de fondo:

- **Empieza en una fecha** (RN-60). Las ventas anteriores no tienen costo
  congelado; reconstruirlas sería inventar. Los saldos iniciales entran por un
  asiento de apertura que el contador dicta.
- **Periodos mensuales, sin reabrir** (RN-61). Reabrir es la puerta por donde
  un balance ya entregado deja de coincidir con el libro. Lo que quedó mal se
  ajusta en el siguiente, que es lo que un contador hace de todos modos.
- **La retención y la comisión de tarjetas no se estiman al vender.** La venta
  con tarjeta va a «tarjetas por cobrar» por su bruto; cuando el adquirente
  liquida, el contador registra la comisión y la retención con el monto real.
  Un porcentaje adivinado produce un número que después no coincide con el
  banco, y conciliar dos números que nunca fueron iguales es peor que asentar
  uno tarde.
- **Exportación en CSV**, no en Excel: cualquier programa contable lo importa
  y el POS no gana una dependencia.

### 13.2 Modelo de datos

```sql
-- 010-contabilidad.sql
CREATE TABLE accounts (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    company_id INT          NOT NULL,
    code       VARCHAR(20)  NOT NULL,     -- '1.1.01'; jerárquico por texto
    name       VARCHAR(120) NOT NULL,
    -- 'asset' | 'liability' | 'equity' | 'income' | 'cost' | 'expense'
    kind       VARCHAR(10)  NOT NULL,
    parent_id  INT          NULL,
    is_system  TINYINT(1)   NOT NULL DEFAULT 0,   -- la usa el mapeo: no se borra (RN-64)
    is_active  TINYINT(1)   NOT NULL DEFAULT 1,
    UNIQUE KEY uq_accounts_code (company_id, code),
    CONSTRAINT fk_accounts_company FOREIGN KEY (company_id) REFERENCES companies (id),
    CONSTRAINT fk_accounts_parent  FOREIGN KEY (parent_id)  REFERENCES accounts (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

-- Qué cuenta usa cada papel de cada evento. Un evento tiene varios papeles: la
-- venta en efectivo usa 'cash', 'sales_13', 'vat_payable', 'cogs' e 'inventory'.
CREATE TABLE account_mappings (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    company_id INT         NOT NULL,
    -- 'sale' | 'return' | 'cash_close' | 'cash_movement' | 'purchase' |
    -- 'supplier_payment' | 'payroll'
    event      VARCHAR(40) NOT NULL,
    -- 'cash', 'cards_receivable', 'sales_13', 'vat_payable', 'vat_credit',
    -- 'inventory', 'cogs', 'payables', 'cash_over', 'cash_short', …
    role       VARCHAR(40) NOT NULL,
    account_id INT         NOT NULL,
    UNIQUE KEY uq_account_mappings (company_id, event, role),
    CONSTRAINT fk_am_company FOREIGN KEY (company_id) REFERENCES companies (id),
    CONSTRAINT fk_am_account FOREIGN KEY (account_id) REFERENCES accounts (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

CREATE TABLE accounting_periods (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    company_id INT         NOT NULL,
    year       SMALLINT    NOT NULL,
    month      TINYINT     NOT NULL,
    status     VARCHAR(10) NOT NULL DEFAULT 'open',   -- 'open' | 'closed'
    closed_at  DATETIME    NULL,
    closed_by  INT         NULL,
    UNIQUE KEY uq_accounting_periods (company_id, year, month),
    CONSTRAINT fk_ap_company FOREIGN KEY (company_id) REFERENCES companies (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

CREATE TABLE journal_entries (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    company_id       INT          NOT NULL,
    period_id        INT          NOT NULL,
    entry_number     INT          NOT NULL,      -- correlativo por compañía, sin huecos
    entry_date       DATE         NOT NULL,
    -- 'auto' | 'manual' | 'adjustment' | 'opening'
    kind             VARCHAR(12)  NOT NULL,
    -- 'sale' | 'return' | 'cash_session' | 'cash_movement' | 'stock_entry' |
    -- 'supplier_payment' | 'payroll_run'
    source_type      VARCHAR(20)  NULL,
    source_id        INT          NULL,
    adjusts_entry_id INT          NULL,          -- el que corrige (RN-61)
    description      VARCHAR(255) NOT NULL,
    user_id          INT          NOT NULL,
    created_at       DATETIME     NOT NULL,
    UNIQUE KEY uq_journal_entries_number (company_id, entry_number),
    -- Un evento, un asiento automático. La anulación de una venta no lo edita:
    -- escribe uno de ajuste que lo revierte.
    UNIQUE KEY uq_journal_entries_source (company_id, source_type, source_id, kind),
    INDEX idx_journal_entries_period (period_id, entry_date),
    CONSTRAINT fk_je_company FOREIGN KEY (company_id)       REFERENCES companies (id),
    CONSTRAINT fk_je_period  FOREIGN KEY (period_id)        REFERENCES accounting_periods (id),
    CONSTRAINT fk_je_adjusts FOREIGN KEY (adjusts_entry_id) REFERENCES journal_entries (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

CREATE TABLE journal_lines (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    company_id INT           NOT NULL,
    entry_id   INT           NOT NULL,
    account_id INT           NOT NULL,
    debit      DECIMAL(12,2) NOT NULL DEFAULT 0,
    -- Una de las dos es 0. Lo vigila el dominio, no un CHECK (§5).
    credit     DECIMAL(12,2) NOT NULL DEFAULT 0,
    -- En las líneas de IVA, para el D-104 (RN-65).
    tax_rate   DECIMAL(5,2)  NULL,
    memo       VARCHAR(160)  NULL,
    INDEX idx_journal_lines_entry (entry_id),
    INDEX idx_journal_lines_account (company_id, account_id),
    CONSTRAINT fk_jl_company FOREIGN KEY (company_id) REFERENCES companies (id),
    CONSTRAINT fk_jl_entry   FOREIGN KEY (entry_id)   REFERENCES journal_entries (id),
    CONSTRAINT fk_jl_account FOREIGN KEY (account_id) REFERENCES accounts (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

-- El costo se congela al vender (RN-63). NULL en las ventas anteriores a F11:
-- esas no entran al libro (RN-60).
ALTER TABLE sale_details
    ADD COLUMN unit_cost DECIMAL(12,2) NULL;
```

La fecha de inicio, la plantilla elegida y cuándo se activó van en el JSON de
`settings`, sección `accounting`, como el resto de la configuración de la
compañía.

### 13.3 Dominio y aplicación

`domain/ledger.py`, puro. `JournalEntry` no se puede construir desbalanceado:
el constructor suma y lanza `EntryNotBalanced` (RN-58). Las funciones que
convierten evento en asiento reciben el evento, sus líneas y el mapeo, y
devuelven el asiento; no saben de base ni de reloj.

El caso que fija todo lo demás es el invariante de siempre. Venta 3 × 1 450 al
13 %, en efectivo, con costo unitario ₡900:

```
subtotal 4 350,00 · IVA 565,50 · total 4 915,50

D  Caja                        4 915,50
   C  Ventas 13 %                          4 350,00
   C  IVA por pagar 13 %                     565,50   (tax_rate 13)
D  Costo de ventas             2 700,00
   C  Inventario                           2 700,00
                               ────────    ────────
                               7 615,50    7 615,50
```

| Función | Qué asienta | Casos |
|---|---|---|
| `post_sale(sale, lines, mapping)` | caja / tarjetas por cobrar / clientes según `payment_method`; ventas por tarifa; IVA por tarifa; costo e inventario | el de arriba; tarjeta; tarifas mezcladas 13 + 2 + 0; línea sin costo (NULL → sin par costo/inventario); método desconocido → por clasificar |
| `post_return(ret, lines, mapping)` | el inverso, con la tarifa de la línea (RN-12) | devolución parcial del ejemplo de §6.3 |
| `post_cash_close(session, expected, counted, mapping)` | la diferencia a sobrante o faltante | 53 000 contra 53 277,00 → faltante 277,00; cuadrado → sin asiento |
| `post_cash_movement(mov, mapping)` | entrada o salida contra por clasificar, salvo que sea de un abono | entrada 5 000; salida ligada a `supplier_payments` → no duplica |
| `post_purchase(entry, lines, mapping)` | inventario; IVA crédito por tarifa; **siempre** proveedores | compra a crédito 100 000 + 13 000; contado |
| `post_supplier_payment(pay, mapping)` | proveedores contra caja o bancos | abono 50 000 en efectivo |
| `trial_balance(lines)`, `income_statement`, `balance_sheet` | sumas por cuenta y por tipo | un periodo con los asientos de arriba: activo = pasivo + patrimonio + resultado |
| `vat_draft(sales_by_rate, purchases_by_rate)` | débito − crédito por tarifa | 565,50 − 13 000 → saldo a favor |
| `assert_open(period, date)` | RN-61 | fecha en cerrado → `PeriodClosed` |

La compra va **siempre** contra proveedores, también la de contado. Decía «caja
(contado)» y eso contaba la plata dos veces: desde F10 una compra de contado con
método de pago crea su propio abono, y el abono asienta proveedores contra caja.
Cargando siempre el pasivo, la de contado queda —sumando las dos— en inventario
e IVA contra caja; y la de contado **sin** método de pago queda debiendo, que
también es correcto, porque nadie registró que se pagara (T-1102, 2026-09-12).

Puertos: `Ledger` (`post(entry)`), `AccountRepository`, `MappingRepository`,
`PeriodRepository`, `EntryNumberSequence`. El puerto `Ledger` es lo que permite
que `RegisterSale`, `RegisterReturn`, `CloseCashSession`, `RegisterCashMovement`,
`RegisterPurchase` y `PaySupplier` **no sepan si contabilidad está activa**:
con el módulo apagado el adaptador es nulo y las pruebas de caracterización
siguen dando las mismas cifras; con el módulo activo, el adaptador escribe en
la misma sesión de SQLAlchemy y el `commit` es uno solo.

Casos de uso nuevos: `ActivateAccounting` (siembra catálogo y mapeo, crea el
periodo de la fecha de inicio, escribe la apertura), `RecordManualEntry`,
`Reclassify` (mueve un saldo de por clasificar con un asiento de ajuste),
`ClosePeriod` (exige el anterior cerrado; deja el siguiente abierto; bitácora).

### 13.4 API y pantallas

```
POST /accounting/activate     admin · {template, start_date, opening_lines}
GET  /accounting/accounts · POST · PUT /{id}       admin escribe
GET  /accounting/mappings · PUT                    admin
GET  /accounting/entries?year=&month=&kind=        cualquiera con el módulo
POST /accounting/entries                           admin · manual o de ajuste
GET  /accounting/entries/{id}
GET  /accounting/periods · POST /{y}/{m}/close     admin, con confirmación
GET  /accounting/reports/{journal|ledger|trial-balance|income|balance}
                                                   ?year=&month=
GET  /accounting/vat?year=&month=                  el borrador del D-104
```

El `?format=csv` que decía este bloque **no va en el backend**: un CSV lleva
encabezados, y los encabezados son texto que lee una persona (RN-30). Lo arma el
POS a partir del JSON, que es lo que ya hace la plantilla de importación de
inventario (T-1110, 2026-09-13).

Y hacía falta una ruta más: `GET /reports/sales_by_rate`, el espejo de
`/reports/purchases`. El D-104 cruza los dos desgloses por tarifa y el de ventas
no existía; sin él habría que sumar el libro aparte, que es justo lo que RN-65
manda no hacer.

Pantallas: `/contabilidad` (el periodo abierto, el saldo de por clasificar en
rojo si no es cero, los últimos asientos), `/contabilidad/cuentas`,
`/contabilidad/mapeo`, `/contabilidad/asientos` con el detalle y el manual,
`/contabilidad/periodos` con el cierre, `/contabilidad/reportes` con los cinco
y su CSV, `/contabilidad/iva`.

### 13.5 Códigos de error

`accounting_not_active`, `entry_not_balanced`, `period_closed`,
`period_not_closeable` (el anterior sigue abierto), `account_in_use`,
`account_is_system`, `invalid_opening_balance`.

Y un octavo que apareció al escribir el dominio: `invalid_entry_line`, para la
línea que trae débito y crédito a la vez, la que viene en negativo y el asiento
sin líneas. No es «no balancea» —un asiento con esas tres cosas puede cuadrar
perfectamente— y un asiento manual lo provoca escribiendo, así que necesita su
propia respuesta (T-1102, 2026-09-12).

### 13.6 Decisiones

| Tema | Qué se decidió | Por qué | Estado |
|---|---|---|---|
| Cuándo se asienta | En la misma transacción, con «por clasificar» | §13.1 | tomada |
| Desde cuándo | Fecha de inicio y apertura; nada hacia atrás | RN-60 | tomada |
| Periodos | Mensuales; cerrado no se reabre | RN-61 | tomada |
| Tarjetas | Bruto a tarjetas por cobrar; retención y comisión al liquidar | El número adivinado no coincide con el banco | tomada |
| Exportación | CSV | Sin dependencias; todo lo importa | tomada |
| **Rol contador** | Hoy solo el administrador entra a contabilidad y compras. Un contador externo (RN-3 ya lo menciona) necesitaría leer libros y escribir asientos sin tocar catálogo ni usuarios: un rol nuevo, el cuarto | Es una decisión de producto —cuántos roles se venden— y toca `user_companies.rol`, `requireAdmin` y el panel | **pendiente** |

### 13.7 Costes medidos antes de empezar

- `test_esquema.py`: cinco tablas y un `ALTER`.
- `test_aislamiento.py`: unas doce rutas.
- `test_error_codes.py`: siete códigos.
- `test_ports.py`: cinco puertos, y `Ledger` entra en la firma de seis casos de
  uso existentes.
- `company_dump.py`: las cinco tablas **viajan**.
- `test_characterization.py`: `RegisterSale` llama al `Ledger`; con el
  adaptador nulo las cifras no cambian, y esa es la prueba de que el enganche
  no toca el dinero.
- `sales.payment_method` es `VARCHAR(50)` libre: antes de mapear hay que
  cerrarlo a un conjunto de valores (T-1104).
- Cobertura: `domain/ledger.py` es el módulo de dominio más grande hasta ahora.
- El simulado: doce endpoints y un libro en el seed.
- Catálogo `accounting.json`, declarado.

### 13.8 Datos de referencia

Plantilla «comercio» que siembra `ActivateAccounting`. Es una plantilla de
trabajo, no una norma: el contador de cada compañía la ajusta, y se **revisa
con un contador antes de sembrarla** en producción.

| Código | Cuenta | Tipo | Sistema |
|---|---|---|---|
| 1.1.01 | Caja | asset | sí |
| 1.1.02 | Bancos | asset | sí |
| 1.1.03 | Tarjetas por cobrar | asset | sí |
| 1.1.04 | Clientes | asset | sí |
| 1.1.05 | IVA crédito fiscal | asset | sí |
| 1.1.06 | Retenciones a favor | asset | no |
| 1.2.01 | Inventario | asset | sí |
| 1.9.99 | Por clasificar | asset | sí |
| 2.1.01 | Proveedores | liability | sí |
| 2.1.02 | IVA por pagar | liability | sí |
| 2.1.03 | Retenciones de renta por pagar | liability | sí |
| 2.1.04 | CCSS por pagar | liability | sí |
| 2.1.05 | Salarios por pagar | liability | sí |
| 2.1.06 | Otras deducciones por pagar | liability | sí |
| 3.1.01 | Capital | equity | sí |
| 3.2.01 | Resultados acumulados | equity | sí |
| 4.1.01 … 4.1.05 | Ventas 13 %, 4 %, 2 %, 1 %, 0 % y exentas | income | sí |
| 4.2.01 | Devoluciones sobre ventas | income | sí |
| 4.9.01 | Sobrantes de caja | income | sí |
| 5.1.01 | Costo de ventas | cost | sí |
| 6.1.01 | Salarios | expense | sí |
| 6.1.02 | Cargas sociales patronales | expense | sí |
| 6.1.03 | Aguinaldo | expense | sí |
| 6.2.01 | Comisiones de tarjetas | expense | no |
| 6.9.01 | Faltantes de caja | expense | sí |
| 6.9.02 | Gastos generales | expense | no |

Mapeo por omisión: `sale` → `cash` 1.1.01, `cards_receivable` 1.1.03,
`receivable` 1.1.04, `sales_{tarifa}` 4.1.0n, `vat_payable` 2.1.02, `cogs`
5.1.01, `inventory` 1.2.01; `return` → los mismos más `sales_returns` 4.2.01;
`cash_close` → `cash_over` 4.9.01, `cash_short` 6.9.01; `purchase` →
`inventory`, `vat_credit` 1.1.05, `payables` 2.1.01; `supplier_payment` →
`payables`, `cash`, `bank` 1.1.02; `payroll` → 6.1.01, 6.1.02, 2.1.03, 2.1.04,
2.1.05, 2.1.06. Todo papel sin fila cae en 1.9.99.

---

## 14. Planilla (F12)

El diseño se amplió el 2026-09-27 después de leer el módulo de planilla del ERP
del que viene VentaSys (una base de GeneXus exportada, que no se versiona):
acciones de personal, jornadas con cortes, puestos con sus códigos, el archivo
del INS y la importación desde Excel (RN-90 a RN-97). El ERP es **una
referencia, no la fuente**: sus fórmulas se leyeron para saber qué casos
existen, y cada cifra y cada formato se siguen tomando de la norma o de la
especificación oficial (§14.8). Hay una razón concreta para no copiarlo: su
tabla de horas trae la jornada mixta mensual en 110 horas, y son 210 (30 × 7).

### 14.1 Lo que se congela y lo que se parametriza

La corrida guarda **cada rubro con su base, su tasa y su monto**
(`payroll_run_items`). Esa tabla **es** el congelamiento de RN-66: la boleta se
reimprime leyéndola, nunca recalculando. Cambiar una tasa es insertar una fila
con `valid_from` en `payroll_rates`; las corridas ya pagadas no la ven, y las
que vengan la toman por fecha de corte.

Las tasas son **globales por país**, no por compañía: son las mismas para
todos los patronos, las siembra la plataforma y las actualiza soporte desde
el panel para todas las compañías a la vez. Lo único que varía por compañía
—la prima de riesgos del trabajo, que el INS fija por póliza según la
actividad, y el aporte a la asociación solidarista— vive en la póliza o en el
contrato, no en la tabla global. Las globales no llevan `company_id`, como
`cabys_cache`, y hay que declararlas como excepción en `test_tenancy.py`.

Las fórmulas del dominio **no conocen ningún porcentaje**: reciben un
`RateSet` resuelto a una fecha y lo aplican. Las pruebas usan un juego de tasas
inventado; así prueban la aritmética y no una cifra que vence.

Decisiones que definen el alcance:

- **Empleado ≠ usuario** (RN-72). `employees.user_id` es opcional.
- **La acción de personal es la fuente, la corrida la consume** (RN-90). Una
  acción tiene fechas y vive en el empleado; `CalculateRun` toma las que se
  cruzan con el periodo, las **parte por el calendario** y escribe un rubro por
  cada tramo aplicado, con `action_id` y sus fechas. Lo que una acción ya
  aplicó es la suma de sus rubros en corridas pagadas: de ahí salen el saldo
  de una deducción (RN-92) y las líneas de incapacidad y permiso del archivo de
  la CCSS, que piden desde y hasta. Reemplaza a `payroll_novelties`, que ataba
  la novedad a una corrida y obligaba a partir a mano una incapacidad que
  cruzaba la quincena.
- **Lo que cae en un periodo pagado entra en la corrida siguiente** (RN-91),
  con sus fechas originales en el rubro. Anular es una acción nueva con
  `cancels_action_id`, que entra igual. La corrida pagada no se toca.
- **La jornada es de la compañía y la corrida es de una jornada** (RN-94).
  Una compañía con cajeros quincenales y bodegueros semanales tiene dos
  jornadas y corre cada una en su corte. La periodicidad, la clase y los
  cortes viven en `work_schedules`, no en cada contrato: son del grupo, y el
  archivo de la CCSS los pide por empleado desde ahí.
- **El salario del contrato es el del periodo**, y el mensual se deriva
  (× 1, × 2, × 26/12, × 52/12). Es como lo escribe la persona que contrata
  —«₡150 000 por semana»— y como lo hace el ERP.
- **Renta del mes calendario, liquidada en la última corrida del mes**
  (RN-73). Las corridas intermedias retienen sobre la proyección
  (`monthly_equivalent`) y la que cierra el mes calcula el impuesto de lo
  devengado en el mes menos lo ya retenido. El resumen de renta del mes
  (RF-62) suma rubros, y por eso cuadra con la declaración. Una corrida
  semanal pertenece al mes de su corte.
- **La quincena es la mitad del salario mensual**, sin importar si el mes tiene
  28 o 31 días. Es lo que hacen los patronos y lo que el empleado espera. En
  mensual y quincenal el día vale el mensual entre treinta y una ausencia no
  rebaja más que el salario del periodo (RN-94).
- **Incapacidades**: quién paga qué y desde qué día son **parámetros**
  (`payroll_rates` con conceptos `sick_leave_employer_days`,
  `sick_leave_employer_rate`…), porque cambian y difieren entre CCSS e INS. Lo
  que paga el patrono durante una incapacidad es un subsidio y no un salario:
  el dominio sabe qué rubros llevan cargas y renta, y lo prueba.
- **El orden de las deducciones es del dominio** (RN-93): cargas, renta,
  pensión alimentaria, embargo y las demás, en ese orden, hasta dejar el neto
  en cero. Lo que no cupo no se aplica y el saldo lo arrastra.
- **El aguinaldo es una corrida** de tipo `aguinaldo`: suma lo devengado de las
  corridas pagadas del periodo **más los saldos de apertura** del mismo
  periodo, y lo divide entre doce (RN-69, RN-97); no lleva rubros de CCSS ni
  renta, y la prueba lo comprueba explícitamente.
- **La liquidación es una corrida** de tipo `settlement`, que nace al dar de
  baja: sus rubros son preaviso, cesantía, vacaciones y aguinaldo
  proporcionales, según la causa (RN-71), sobre el promedio de los últimos seis
  meses —pagados o de apertura—.
- **Importar es una sola ruta con ensayo** (RN-97). El BFF lee el Excel con el
  lector de las entradas de mercadería (`$lib/server/import/spreadsheet.ts`)
  y manda las filas; el backend las valida y responde fila por fila con
  `dry_run`, y sin él las escribe en una transacción. La vista previa es la
  respuesta del ensayo: la validación vive en un solo lugar.
- **Fuera de la primera versión** (spec §4): archivos de pago de los bancos,
  boletas por correo, régimen y bonos de vacaciones, renta con otros patronos,
  constancias, centros de costo y departamentos, otras monedas, varios
  contratos a la vez, pensión voluntaria, expediente, INSS y **salario por
  hora** —que necesitaría un tipo de acción «horas ordinarias» cada periodo—.
  La corrida pagada muestra la lista de IBAN y montos para copiar.

### 14.2 Modelo de datos

```sql
-- 019-planilla.sql
-- Globales, por país: sin company_id (como cabys_cache). Excepción en test_tenancy.
CREATE TABLE payroll_rates (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    country     CHAR(2)       NOT NULL,      -- 'CR'
    -- 'sem', 'ivm', 'banco_popular', 'asignaciones_familiares', 'imas', 'ina',
    -- 'fcl', 'rop', 'sick_leave_employer_rate', 'minimum_wage_unseizable', …
    concept     VARCHAR(40)   NOT NULL,
    payer       VARCHAR(8)    NOT NULL,      -- 'employee' | 'employer' | 'rule'
    -- Según el concepto: 0.0550 = 5,50 %, un número de días o un monto
    -- (el salario mínimo inembargable de RN-93). Por eso no cabe en (9,4).
    value       DECIMAL(14,4) NOT NULL,
    valid_from  DATE          NOT NULL,
    valid_to    DATE          NULL,
    source      VARCHAR(255)  NOT NULL,      -- la norma o la URL
    verified_at DATE          NOT NULL,      -- cuándo alguien lo comprobó
    UNIQUE KEY uq_payroll_rates (country, concept, payer, valid_from)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

CREATE TABLE income_tax_brackets (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    country     CHAR(2)       NOT NULL,
    valid_from  DATE          NOT NULL,
    valid_to    DATE          NULL,
    lower_bound DECIMAL(12,2) NOT NULL,
    upper_bound DECIMAL(12,2) NULL,        -- NULL: el último tramo
    rate        DECIMAL(5,4)  NOT NULL,
    source      VARCHAR(255)  NOT NULL,
    verified_at DATE          NOT NULL,
    UNIQUE KEY uq_income_tax_brackets (country, valid_from, lower_bound)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

CREATE TABLE income_tax_credits (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    country     CHAR(2)       NOT NULL,
    concept     VARCHAR(20)   NOT NULL,     -- 'child' | 'spouse'
    valid_from  DATE          NOT NULL,
    valid_to    DATE          NULL,
    amount      DECIMAL(12,2) NOT NULL,     -- mensual
    source      VARCHAR(255)  NOT NULL,
    verified_at DATE          NOT NULL,
    UNIQUE KEY uq_income_tax_credits (country, concept, valid_from)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

CREATE TABLE severance_table (              -- art. 29: días por año de antigüedad
    id          INT AUTO_INCREMENT PRIMARY KEY,
    country     CHAR(2)      NOT NULL,
    valid_from  DATE         NOT NULL,
    years_from  DECIMAL(4,2) NOT NULL,      -- 0.25 = tres meses
    years_to    DECIMAL(4,2) NULL,
    days        DECIMAL(5,2) NOT NULL,
    source      VARCHAR(255) NOT NULL,
    UNIQUE KEY uq_severance_table (country, valid_from, years_from)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

-- De acá en adelante, todo es de la compañía.
CREATE TABLE work_schedules (                  -- las jornadas (RN-94)
    id             INT AUTO_INCREMENT PRIMARY KEY,
    company_id     INT          NOT NULL,
    name           VARCHAR(80)  NOT NULL,
    -- 'monthly' | 'semimonthly' (quincenal) | 'biweekly' (bisemanal) | 'weekly'
    frequency      VARCHAR(12)  NOT NULL,
    shift          VARCHAR(8)   NOT NULL,      -- 'day' | 'mixed' | 'night'
    hours_per_day  DECIMAL(4,2) NOT NULL,      -- 8 · 7 · 6 por omisión (art. 136)
    workdays_per_week SMALLINT  NOT NULL DEFAULT 6,  -- las vacaciones (art. 153)
    rest_day_paid  TINYINT(1)   NOT NULL DEFAULT 1,  -- comercial (art. 152)
    first_cut_day  SMALLINT     NULL,          -- quincenal: corta el 8..15
    cut_weekday    SMALLINT     NULL,          -- semanal: 0 = lunes … 6 = domingo
    series_start   DATE         NULL,          -- bisemanal: primer día de la serie
    is_active      TINYINT(1)   NOT NULL DEFAULT 1,
    UNIQUE KEY uq_work_schedules_name (company_id, name),
    CONSTRAINT fk_ws_company FOREIGN KEY (company_id) REFERENCES companies (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

CREATE TABLE positions (                       -- RN-95
    id         INT AUTO_INCREMENT PRIMARY KEY,
    company_id INT          NOT NULL,
    name       VARCHAR(80)  NOT NULL,
    ccss_code  VARCHAR(4)   NOT NULL,          -- ocupación, cuatro dígitos
    ins_code   VARCHAR(5)   NOT NULL,
    is_active  TINYINT(1)   NOT NULL DEFAULT 1,
    UNIQUE KEY uq_positions_name (company_id, name),
    CONSTRAINT fk_positions_company FOREIGN KEY (company_id) REFERENCES companies (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

CREATE TABLE ins_policies (                    -- pólizas de riesgos del trabajo
    id         INT AUTO_INCREMENT PRIMARY KEY,
    company_id INT          NOT NULL,
    number     VARCHAR(20)  NOT NULL,
    rt_rate    DECIMAL(6,4) NOT NULL,          -- la prima que fija el INS
    is_default TINYINT(1)   NOT NULL DEFAULT 0,
    UNIQUE KEY uq_ins_policies_number (company_id, number),
    CONSTRAINT fk_insp_company FOREIGN KEY (company_id) REFERENCES companies (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

CREATE TABLE employees (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    company_id          INT          NOT NULL,
    user_id             INT          NULL,               -- RN-72: opcional
    -- 'national' | 'dimex' | 'nite' | 'passport' | 'work_permit'. Palabras y
    -- no códigos: Hacienda, la CCSS y el INS numeran distinto, y cada
    -- adaptador de archivo traduce a los suyos.
    identification_type VARCHAR(12)  NOT NULL,
    identification      VARCHAR(30)  NOT NULL,
    first_name          VARCHAR(60)  NOT NULL,
    last_name_1         VARCHAR(40)  NOT NULL,
    last_name_2         VARCHAR(40)  NULL,               -- hay quien tiene uno solo
    insured_number      VARCHAR(25)  NULL,   -- CCSS; en nacionales, la cédula
    birth_date          DATE         NOT NULL,
    gender              CHAR(1)      NOT NULL,           -- 'F' | 'M'
    -- 'single' | 'married' | 'divorced' | 'widowed' | 'separated' |
    -- 'free_union' | 'unknown'
    marital_status      VARCHAR(10)  NOT NULL,
    nationality         CHAR(2)      NOT NULL,           -- ISO 3166, 'CR'
    phone               VARCHAR(20)  NULL,
    email               VARCHAR(120) NULL,
    is_pensioner        TINYINT(1)   NOT NULL DEFAULT 0, -- la CCSS cotiza distinto
    iban                VARCHAR(34)  NULL,
    hired_on            DATE         NOT NULL,
    terminated_on       DATE         NULL,
    -- 'resignation' | 'dismissal_with_cause' | 'dismissal_without_cause' |
    -- 'mutual' | 'end_of_contract'
    termination_cause   VARCHAR(30)  NULL,
    dependent_children  SMALLINT     NOT NULL DEFAULT 0, -- crédito fiscal
    spouse_credit       TINYINT(1)   NOT NULL DEFAULT 0,
    is_active           TINYINT(1)   NOT NULL DEFAULT 1,
    UNIQUE KEY uq_employees_identification (company_id, identification),
    CONSTRAINT fk_employees_company FOREIGN KEY (company_id) REFERENCES companies (id),
    CONSTRAINT fk_employees_user    FOREIGN KEY (user_id)    REFERENCES users (id_user)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

CREATE TABLE employment_contracts (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    company_id       INT           NOT NULL,
    employee_id      INT           NOT NULL,
    schedule_id      INT           NOT NULL,   -- la jornada: periodicidad y cortes
    position_id      INT           NOT NULL,
    ins_policy_id    INT           NULL,       -- NULL: la póliza por omisión
    valid_from       DATE          NOT NULL,
    valid_to         DATE          NULL,       -- un aumento lo cierra y abre otro
    period_salary    DECIMAL(12,2) NOT NULL,   -- el del periodo de su jornada
    solidarista_rate DECIMAL(5,4)  NULL,       -- aporte obrero, si hay
    INDEX idx_employment_contracts_employee (employee_id, valid_from),
    CONSTRAINT fk_ec_company  FOREIGN KEY (company_id)    REFERENCES companies (id),
    CONSTRAINT fk_ec_employee FOREIGN KEY (employee_id)   REFERENCES employees (id),
    CONSTRAINT fk_ec_schedule FOREIGN KEY (schedule_id)   REFERENCES work_schedules (id),
    CONSTRAINT fk_ec_position FOREIGN KEY (position_id)   REFERENCES positions (id),
    CONSTRAINT fk_ec_policy   FOREIGN KEY (ins_policy_id) REFERENCES ins_policies (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

CREATE TABLE payroll_runs (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    company_id       INT         NOT NULL,
    -- 'regular' | 'aguinaldo' | 'settlement' | 'adjustment'
    kind             VARCHAR(12) NOT NULL,
    schedule_id      INT         NULL,      -- las regulares y sus ajustes
    period_from      DATE        NOT NULL,  -- sale del corte (RN-94); se guarda
    period_to        DATE        NOT NULL,  -- porque la corrida se congela
    pay_date         DATE        NOT NULL,
    -- 'draft' | 'approved' | 'paid' (RN-68)
    status           VARCHAR(10) NOT NULL DEFAULT 'draft',
    adjusts_run_id   INT         NULL,
    journal_entry_id INT         NULL,      -- RN-75, si hay contabilidad
    created_by       INT         NOT NULL,
    created_at       DATETIME    NOT NULL,
    approved_by      INT         NULL,
    approved_at      DATETIME    NULL,
    paid_by          INT         NULL,
    paid_at          DATETIME    NULL,
    INDEX idx_payroll_runs_period (company_id, period_from, kind),
    CONSTRAINT fk_pr_company  FOREIGN KEY (company_id)     REFERENCES companies (id),
    CONSTRAINT fk_pr_schedule FOREIGN KEY (schedule_id)    REFERENCES work_schedules (id),
    CONSTRAINT fk_pr_adjusts  FOREIGN KEY (adjusts_run_id) REFERENCES payroll_runs (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

CREATE TABLE payroll_run_lines (               -- un empleado en una corrida
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    company_id          INT           NOT NULL,
    run_id              INT           NOT NULL,
    employee_id         INT           NOT NULL,
    contract_id         INT           NOT NULL,
    gross               DECIMAL(12,2) NOT NULL,
    employee_deductions DECIMAL(12,2) NOT NULL,
    income_tax          DECIMAL(12,2) NOT NULL,
    other_deductions    DECIMAL(12,2) NOT NULL,  -- pensión, embargo, préstamos
    net                 DECIMAL(12,2) NOT NULL,
    employer_charges    DECIMAL(12,2) NOT NULL,
    UNIQUE KEY uq_payroll_run_lines (run_id, employee_id),
    CONSTRAINT fk_prl_company  FOREIGN KEY (company_id)  REFERENCES companies (id),
    CONSTRAINT fk_prl_run      FOREIGN KEY (run_id)      REFERENCES payroll_runs (id),
    CONSTRAINT fk_prl_employee FOREIGN KEY (employee_id) REFERENCES employees (id),
    CONSTRAINT fk_prl_contract FOREIGN KEY (contract_id) REFERENCES employment_contracts (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

CREATE TABLE personnel_actions (               -- RN-90: vive en el empleado
    id                INT AUTO_INCREMENT PRIMARY KEY,
    company_id        INT           NOT NULL,
    employee_id       INT           NOT NULL,
    -- 'overtime' | 'double_time' | 'bonus' | 'sick_leave_ccss' |
    -- 'sick_leave_ins' | 'maternity' | 'paid_leave' | 'unpaid_leave' |
    -- 'absence' | 'vacation' | 'deduction' | 'child_support' | 'garnishment' |
    -- 'raise' | 'position_change' | 'termination'
    kind              VARCHAR(20)   NOT NULL,
    starts_on         DATE          NOT NULL,
    ends_on           DATE          NULL,      -- NULL: recurrente sin fecha final
    hours             DECIMAL(8,2)  NULL,      -- horas extra y dobles
    days              DECIMAL(6,2)  NULL,      -- ausencias y vacaciones
    amount            DECIMAL(12,2) NULL,      -- bonificación, o cuota por corrida
    total_amount      DECIMAL(12,2) NULL,      -- lo pactado (RN-92); NULL: sin tope
    new_salary        DECIMAL(12,2) NULL,      -- aumento
    position_id       INT           NULL,      -- cambio de puesto
    is_recurring      TINYINT(1)    NOT NULL DEFAULT 0,
    memo              VARCHAR(160)  NULL,
    cancels_action_id INT           NULL,      -- la anulación (RN-91)
    suspended_at      DATETIME      NULL,
    suspended_by      INT           NULL,
    suspension_reason VARCHAR(160)  NULL,
    source            VARCHAR(8)    NOT NULL DEFAULT 'manual',  -- 'manual' | 'import' | 'system'
    created_by        INT           NOT NULL,
    created_at        DATETIME      NOT NULL,
    INDEX idx_personnel_actions_employee (employee_id, starts_on),
    CONSTRAINT fk_pa_company  FOREIGN KEY (company_id)        REFERENCES companies (id),
    CONSTRAINT fk_pa_employee FOREIGN KEY (employee_id)       REFERENCES employees (id),
    CONSTRAINT fk_pa_position FOREIGN KEY (position_id)       REFERENCES positions (id),
    CONSTRAINT fk_pa_cancels  FOREIGN KEY (cancels_action_id) REFERENCES personnel_actions (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

-- Los rubros SON las tasas congeladas (RN-66). La boleta se reimprime de acá.
CREATE TABLE payroll_run_items (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    company_id   INT           NOT NULL,
    line_id      INT           NOT NULL,
    -- 'base', 'overtime', 'double_time', 'sick_leave_subsidy', 'sem', 'ivm',
    -- 'income_tax', 'solidarista', 'garnishment', 'child_support', …
    concept      VARCHAR(40)   NOT NULL,
    payer        VARCHAR(8)    NOT NULL,    -- 'earning' | 'employee' | 'employer'
    base         DECIMAL(12,2) NOT NULL,
    -- NULL en los montos fijos (una deducción de ₡20 000).
    rate         DECIMAL(9,4)  NULL,
    amount       DECIMAL(12,2) NOT NULL,
    -- De qué acción sale y qué tramo de ella aplicó (RN-90). Las fechas son
    -- las de la acción, no las de la corrida: una retroactiva (RN-91) las trae
    -- de un periodo ya pagado, y el archivo de la CCSS las pide así.
    action_id    INT           NULL,
    quantity     DECIMAL(8,2)  NULL,        -- horas o días de ese tramo
    applied_from DATE          NULL,
    applied_to   DATE          NULL,
    INDEX idx_payroll_run_items_line (line_id),
    INDEX idx_payroll_run_items_action (action_id),
    CONSTRAINT fk_pri_company FOREIGN KEY (company_id) REFERENCES companies (id),
    CONSTRAINT fk_pri_line    FOREIGN KEY (line_id)    REFERENCES payroll_run_lines (id),
    CONSTRAINT fk_pri_action  FOREIGN KEY (action_id)  REFERENCES personnel_actions (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

CREATE TABLE vacation_movements (              -- el saldo es una suma (RN-70)
    id          INT AUTO_INCREMENT PRIMARY KEY,
    company_id  INT          NOT NULL,
    employee_id INT          NOT NULL,
    kind        VARCHAR(10)  NOT NULL,     -- 'accrual' | 'taken' | 'paid' | 'opening'
    days        DECIMAL(6,2) NOT NULL,
    on_date     DATE         NOT NULL,
    run_id      INT          NULL,
    action_id   INT          NULL,         -- el disfrute sale de una acción
    INDEX idx_vacation_movements_employee (employee_id, on_date),
    CONSTRAINT fk_vm_company  FOREIGN KEY (company_id)  REFERENCES companies (id),
    CONSTRAINT fk_vm_employee FOREIGN KEY (employee_id) REFERENCES employees (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

-- Lo devengado antes de VentaSys, mes a mes (RN-97). El aguinaldo suma los
-- meses de su periodo y la liquidación promedia los últimos seis: una sola
-- tabla sirve a los dos.
CREATE TABLE payroll_opening_earnings (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    company_id   INT           NOT NULL,
    employee_id  INT           NOT NULL,
    period_month DATE          NOT NULL,    -- el primer día del mes
    gross        DECIMAL(12,2) NOT NULL,
    imported_by  INT           NOT NULL,
    imported_at  DATETIME      NOT NULL,
    UNIQUE KEY uq_payroll_opening_earnings (employee_id, period_month),
    CONSTRAINT fk_poe_company  FOREIGN KEY (company_id)  REFERENCES companies (id),
    CONSTRAINT fk_poe_employee FOREIGN KEY (employee_id) REFERENCES employees (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;
```

Los datos patronales —número patronal de la CCSS— van en el JSON de
`settings`, validados por el backend como la ubicación del emisor (T-722): no
son una tabla porque son uno por compañía. Las pólizas sí, porque una compañía
con tienda y cuadrilla de construcción tiene dos, con primas distintas.

### 14.3 Dominio y aplicación

Cuatro módulos puros (T-1202, T-1216, T-1203), todos al 100 %:

- `payroll_calendar.py`: jornadas, cortes, periodos y lo que vale un día.
- `payroll.py`: tasas con vigencia, cargas y renta.
- `payroll_actions.py`: los dieciséis tipos de acción, sus tramos y sus
  rubros, y las deducciones.
- `payroll_benefits.py`: aguinaldo, vacaciones y liquidación.

Todo recibe el `RateSet` resuelto a la fecha de corte; `rates_at(rates,
date)` es la única función que mira la vigencia, exige **al resolver** todas
las cargas que Costa Rica cobra (`REQUIRED_CONTRIBUTIONS`) y lanza
`RatesMissing` si falta una. Las reglas —días de incapacidad, salario mínimo
inembargable— se piden **cuando hacen falta** (`RateSet.rule`): una corrida sin
incapacidades no necesita la de incapacidades.

**Lo que vale un día lo dice el decreto de salarios mínimos**, art. 7 (el
43633-MTSS; la regla se repite cada año): la semana paga seis días, o siete en
los establecimientos comerciales (art. 152); la quincena, quince; el mes,
treinta, «indistintamente de la actividad». El ERP de origen lo tiene al revés
en su tabla de horas, y por eso se leyó el decreto.

| Función | Regla | Casos (con tasas inventadas) |
|---|---|---|
| `check_schedule` | RN-94: cada periodicidad pide su dato de corte y solo ese | una mensual con día de quincena → `unexpected`; una semanal sin día → `required`; siete días hábiles → fuera de rango |
| `period_for(schedule, cut)` | el periodo sale del corte; un corte que no es de la jornada lanza `InvalidCutDate` | mensual al 30 de abril → 1–30; quincenal que corta el 15 → 1–15 y 16–fin; que corta el 14 → 30–14 y 15–29, y en febrero el 28, y cruzando el año; bisemanal desde su serie; semanal del domingo; el 20 en una quincenal → error |
| `next_cut`, `cut_on_or_after`, `closes_month` | el corte que sigue, el del periodo que contiene un día, y si la corrida es la última del mes (RN-73) | después del 29, el 14 del mes siguiente; la semana del 25 de enero cierra enero |
| `monthly_equivalent(amount, frequency)` | × 1, × 2, × 26/12, × 52/12; sirve para el contrato y para proyectar la renta | los cuatro |
| `paid_days`, `day_value`, `hour_value` | el decreto: 30, 15, 7 o 6 por semana; el día sin redondear —se redondea el rubro—; la hora, el día entre las horas de la jornada | diurna mensual 600 000 → hora 2 500; mixta ÷ 210; nocturna ÷ 180; semana comercial de 140 000 y no comercial de 120 000 → día de 20 000 |
| `rates_at`, `RateSet.rule` | gana la fila de `valid_from` más reciente, sin importar el orden; lo vencido y lo futuro no rigen | una tasa nueva desde el 1 de marzo; sin IVM → `RatesMissing` con los dos pagadores |
| `employee_deductions`, `employer_charges` | cada rubro base × tasa, redondeado por rubro; la prima de RT de la póliza | la suma de la boleta es la de sus renglones |
| `income_tax(monthly, brackets, credits)` | tramos marginales, menos créditos, nunca negativo | bajo el piso → 0; en los cuatro tramos; con dos hijos y cónyuge |
| `income_tax_withholding(…)` | RN-73: la intermedia retiene su parte de la proyección; la que cierra el mes, el impuesto del mes menos lo retenido, y puede devolver | dos quincenas iguales → mitad y mitad; extras solo en la segunda → el mes cuadra al céntimo; la primera retuvo de más → la segunda devuelve |
| `check_action` | RN-90: cada tipo pide lo suyo; las de un día no tienen rango; solo la deducción y la pensión son recurrentes por elección | dieciséis tipos; los faltantes y los sobrantes, por campo |
| `counted_days(schedule, from, to)` | RN-94, mes comercial: cada fin de mes que el tramo cruza suma o resta hasta treinta; nunca más de lo que paga el periodo | la segunda quincena entera son quince en enero y en febrero; el 31 solo, cero; la semana no comercial rebaja seis |
| `portions(action, schedule, first_unapplied, period)` | RN-90 y RN-91: desde el primer día que nadie aplicó hasta el fin del periodo, un tramo por cada periodo que cruza | del 10 al 20 en quincenas → 6 y 5; la que llegó tarde → los dos tramos en la segunda corrida, con sus fechas |
| `action_items(…)` | extras × 1,5 (art. 139), dobles × 2 (arts. 148–149), bonificación; ausencias en negativo; incapacidad con los primeros días del patrono como subsidio, salvo si prolonga otra; maternidad con la parte del patrono; todo tramo deja al menos un rubro, aunque sea de cero | uno por tipo |
| `contribution_base`, `taxable_base` | lo que cotiza y lo que paga renta; el subsidio no; nunca negativas | con incapacidad y subsidio |
| `deduction_due`, `remaining_balance`, `is_active` | RN-92: vigente, no suspendida y con saldo; una no recurrente, una vez | préstamo a mitad, al final y agotado; suspendido antes y después del periodo |
| `garnishment_amount`, `garnishment_capacity`, `child_support_capacity` | RN-93, art. 172: ⅛ del exceso hasta 3 × el inembargable, ¼ de lo que lo supere; **un tope por salario**, que dos embargos se reparten con `apply_deductions`; la pensión alimentaria, hasta la mitad del neto | bajo el mínimo → 0; entre 1 y 3 veces; sobre 3 veces; una quincena → la mitad; dos embargos contra un mismo tope |
| `apply_deductions`, `deduction_order` | RN-93: pensión, embargo y las demás, la más vieja primero, hasta dejar el neto en cero | todas caben; una en parte y la siguiente en nada; con neto negativo, ninguna |
| `aguinaldo`, `aguinaldo_period` | suma ÷ 12, del 1 de diciembre al 30 de noviembre; un solo rubro, sin cargas ni renta (RN-69); los meses de apertura suman igual (RN-97) | doce iguales; siete; con extras; cinco de apertura y siete pagados |
| `vacation_accrual`, `proportional_vacation` | art. 153: dos semanas por cincuenta —doce días hábiles en semana de seis, diez en semana de cinco— y, al salir antes, al menos un día por mes | 350 días → 12 o 10; cuatro meses en semana de cinco → 4 |
| `months_between`, `years_between` | la antigüedad por meses completos, no por días entre 365 | del 10 de enero al 9 de abril, tres; dos años y medio |
| `notice_days(months)` | art. 28 | 2 meses → 0; 4 → 7; 8 → 15; 24 → 30 |
| `severance_years`, `severance_days(months, table)` | art. 29: totales bajo el año; desde el año, días por año de la fila de los años contados —**la fracción de más de seis meses cuenta como año**—, topado a ocho | 2 años y 7 meses → 3; 5 años → 106,2; 12 → 164 |
| `average_salary(last_months)` | art. 30: los últimos seis, pagados o de apertura, o los que haya | seis; dos; ninguno |
| `settlement(data, table)` | RN-71: preaviso y cesantía solo en el despido sin causa; vacaciones y aguinaldo proporcionales siempre; el día, el promedio entre treinta | las cinco causas |

La jornada lleva además `workdays_per_week` —seis o cinco—, que no estaba en el
primer DDL: sin ella no se sabe si dos semanas de vacaciones son doce días o
diez.

Puertos: `RateTable`, `EmployeeRepository`, `PayrollRepository` (corridas,
líneas y rubros), `ActionRepository`, `PayslipRenderer`, `CcssFileWriter`,
`InsFileWriter`, y el `Ledger` de F11. Casos de uso: `RegisterAction`,
`CancelAction`, `SuspendAction`, `CreateRun`, `CalculateRun` (toma las
acciones del periodo y las pendientes de periodos pagados, y escribe líneas y
rubros: el congelamiento), `ApproveRun`, `PayRun` (fecha del servidor,
bitácora, `Ledger.post` si hay contabilidad), `AdjustRun`,
`TerminateEmployee` (registra la acción `termination`, cierra el contrato y
crea la corrida de liquidación en borrador), `ImportPayroll` (con `dry_run`),
`ExportCcssFile`, `ExportInsFile`, `IncomeTaxSummary`.

### 14.4 API y pantallas

```
GET  /payroll/settings · PUT                número patronal                    admin
GET  /payroll/schedules · POST · PUT /{id}  jornadas (schedule_locked)          admin
GET  /payroll/positions · POST · PUT /{id}  puestos                            admin
GET  /payroll/policies · POST · PUT /{id}   pólizas del INS                    admin
GET  /payroll/employees · POST · PUT /{id} · POST /{id}/terminate              admin
     (el POST admite `contract`: el alta y su contrato en una transacción, desde el ingreso)
GET  /payroll/contracts?employee= · POST                                       admin
GET  /payroll/employees/{id}/actions        historial, con lo que aplicó cada corrida y el saldo
POST /payroll/actions · /{id}/cancel · /{id}/suspend                           admin
POST /payroll/import?dry_run=               las filas ya leídas por el BFF     admin
GET  /payroll/rates?on=                     lo vigente a una fecha, con su
                                            fuente y su verified_at
PUT  /support/payroll/rates                 soporte · inserta una fila con
                                            vigencia; nunca edita la vigente
GET  /payroll/runs · POST                   admin; POST con jornada y corte
POST /payroll/runs/{id}/calculate · /approve · /pay · /adjust
GET  /payroll/runs/{id}                     líneas y rubros
GET  /payroll/runs/{id}/payslips/{employee} la boleta
POST /payroll/runs/aguinaldo                la corrida de aguinaldo del año (T-1208)
GET  /payroll/vacations/{employee}          saldo y movimientos
GET  /payroll/exports/ccss?year=&month=     el informe del mes para Autogestión (RF-62; ver §14.6)
GET  /payroll/exports/ins?year=&month=&policy=  el archivo de texto V08D (RF-85)
GET  /payroll/exports/income-tax?year=&month=
```

Pantallas: `/planilla` (las corridas en curso y lo que vence: aguinaldo,
tasas viejas, empleados a los que les falta un dato para los archivos),
`/planilla/empleados` con contrato, historial de acciones y baja,
`/planilla/acciones` (registrar una, para uno o varios empleados),
`/planilla/corridas` y `/planilla/corridas/{id}` con cálculo, aprobación,
pago y boletas, `/planilla/vacaciones`, `/planilla/configuracion` (datos
patronales, jornadas, puestos y pólizas), `/planilla/importar` (plantilla,
vista previa fila por fila y confirmar), `/planilla/tasas` (solo lectura,
con fecha y fuente) y `/planilla/archivos` —agregada al cerrar la fase: el
informe del mes para la CCSS con su CSV, la renta retenida y el archivo del
INS por póliza—. La boleta es la **cuarta plantilla de documento** —T-922
ya avisa que el PDF del backend no se cuenta—, con el idioma del documento
(RN-29): `Boleta.svelte` con `payslipLabels(docLocale)`.

### 14.5 Códigos de error

`rates_missing_for_date`, `contract_missing`, `employee_terminated`,
`run_not_editable`, `run_not_approved`, `run_already_paid`,
`settlement_requires_termination`, `vacation_balance_exceeded`,
`invalid_cut_date`, `schedule_locked`, `action_not_editable`,
`invalid_payroll_rate`, `payroll_rate_not_newer` (T-1204),
`action_already_cancelled`, `action_not_recurring`, `import_has_errors`,
`export_data_incomplete` (con la lista de empleados y los datos que les
faltan). `novelty_outside_period` sale: una acción fuera del periodo no es un
error, es una que entra en otra corrida.

### 14.6 Decisiones

| Tema | Qué se decidió | Por qué | Estado |
|---|---|---|---|
| Tasas | Globales por país, con vigencia; la prima de RT en la póliza y el solidarista en el contrato | Son las mismas para todos; lo que varía es poco y es de la compañía | tomada |
| Congelamiento | Los rubros de la corrida, con base y tasa | La boleta se reimprime de datos, no de código | tomada |
| Acciones de personal | En el empleado, con fechas; la corrida las parte y deja el tramo en el rubro | Una incapacidad que cruza la quincena no se parte a mano, y los archivos piden fechas | tomada 2026-09-27 |
| Tipos de acción | Lista cerrada de dieciséis | Cada tipo tiene su efecto en el cálculo y en los archivos | tomada 2026-09-27 |
| Jornadas | De la compañía; la corrida es de una jornada y un corte | Grupos que cobran en calendarios distintos | tomada 2026-09-27 |
| Renta | Del mes calendario: proyección en las intermedias, liquidación en la que cierra el mes | Proyectar y partir descuadra el mes con horas extra desiguales | tomada 2026-09-27 (antes: solo proyección) |
| Quincena | Mitad del mensual | Lo que hacen los patronos y espera el empleado | tomada |
| Aguinaldo y liquidación | Son corridas, con los saldos de apertura sumados | Un solo modelo de estados, bitácora y asiento; y quien migra no pierde lo devengado | tomada |
| Importación | Una ruta con `dry_run`; la vista previa es el ensayo | La validación vive en un solo lugar | tomada 2026-09-27 |
| Identificación del empleado | Palabras, no códigos | Hacienda, la CCSS y el INS numeran distinto | tomada 2026-09-27 |
| Archivo bancario | Fuera | Un formato por banco; sin cliente que lo pida | tomada |
| Salario por hora | Fuera | Pide un tipo «horas ordinarias» cada periodo | tomada 2026-09-27 |
| Caja | La planilla no mueve la caja (RN-74) | Nómina y arqueo se descuadran juntos | tomada |
| ¿Quién edita las tasas? | Soporte, para todos; la compañía las ve | Una tasa mal escrita por un cliente es un reclamo laboral; una fila con vigencia de soporte es un dato con fuente | tomada |
| Archivo de la CCSS | Un **informe** con lo que pide el formulario de Autogestión (JSON y CSV), no un archivo de texto | La CCSS no publica el trazado del archivo de grandes clientes y el formato no se supone (§14.8); el 98 % de los patronos presenta por el formulario. El escritor queda como T-1222 para cuando la Dirección SICERE entregue la estructura | tomada 2026-10-02 |
| Archivo del INS | El trazado V08D del generador público que reproduce la plantilla del INS, pendiente de cotejar (T-1223) | El INS publica la estructura solo dentro de RT-Virtual; el trazado es concreto y documentado (`docs/ins/README.md`) y un rechazo del INS se corrige en un sitio | tomada 2026-10-02 |
| Ajuste | Recalcula el periodo con los datos de hoy sobre los **mismos tramos** que la pagada aplicó y escribe la diferencia rubro por rubro | Lo que la pagada no aplicó entra en la regular siguiente (RN-91); si el ajuste lo tomara, se pagaría dos veces. La renta se proyecta con el mes abierto y se liquida con el mes cerrado | tomada 2026-10-02 |
| La liquidación sabe de quién es por su línea | Nace con una línea vacía del empleado | La corrida no tiene columna de empleado porque las demás son de muchos; la línea es el enlace y el cálculo la llena | tomada 2026-10-02 |
| Lo devengado que cuenta | `EARNED_CONCEPTS` = lo que paga renta: sin subsidios de incapacidad | El subsidio no es salario (DAJ-AE-201-12). La maternidad cuenta lo que pagó el patrono; si el art. 95 pide el salario entero, se cambia en un sitio (pendiente con el usuario) | tomada 2026-10-02 |

### 14.7 Costes medidos antes de empezar

- `test_esquema.py`: quince tablas (`019`).
- `test_tenancy.py`: cuatro tablas globales sin `TenantMixin`, declaradas como
  excepción explícita, como `cabys_cache`.
- `test_aislamiento.py`: unas treinta rutas, y una bajo `/support`.
- `test_error_codes.py`: diecisiete códigos, con los dos de las tasas.
- `test_ports.py`: siete puertos.
- `company_dump.py`: once tablas **viajan**; las cuatro globales, **no**.
- Cobertura: el dominio de planilla supera a `ledger.py`; la tabla de casos es
  larga a propósito.
- El simulado: unos treinta endpoints; dos empleados, dos jornadas, dos
  puestos, una póliza y un juego de tasas en el seed.
- Catálogo `payroll.json`, declarado. La boleta como cuarta plantilla, en los
  tres idiomas del documento.
- El asiento de planilla necesita el mapeo `payroll` de §13.8 sembrado desde
  F11, aunque no se use hasta acá. Las deducciones que no son de la CCSS ni de
  Hacienda —pensión, embargo, préstamos— van a 2.1.06.

### 14.8 Datos de referencia

**Nada de esta sección es una verdad del sistema: es lo que se siembra, con su
fuente y su fecha, y se comprueba contra la fuente oficial antes de
sembrarlo.** Las cifras concretas de porcentajes y tramos **no se escriben
acá**: cambian con decreto y se copiarían viejas. Se toman de `ccss.sa.cr`
(cuotas obrero-patronales), `hacienda.go.cr` (tramos y créditos del periodo
fiscal vigente) y el decreto de salarios mínimos del MTSS, el día que se
siembra, y esa fecha va en `verified_at`.

| Concepto | Pagador | Tabla | Fuente |
|---|---|---|---|
| SEM, IVM, Banco Popular | obrero y patrono | `payroll_rates` | CCSS. El IVM trae aumentos programados: varias filas con `valid_from` |
| Asignaciones Familiares, IMAS, INA, FCL, ROP, aporte patronal Banco Popular | patrono | `payroll_rates` | CCSS / Ley de Protección al Trabajador |
| Riesgos del trabajo | patrono, por póliza | `ins_policies.rt_rate` | INS, la póliza de cada compañía. El subsidio de una incapacidad del INS lo paga el INS desde la fecha del riesgo (art. 236): `ins_employer_days` = 0 |
| Uno por ciento al INS de la LPT | patrono | `payroll_rates` (`ins_lpt`) | Ley 7983, recaudado por la CCSS. Sin él la suma patronal da 25,83 y no el 26,83 publicado |
| INA | patrono, salvo exento | `payroll_rates` y la configuración de la compañía | El patrono no agrícola con menos de cinco trabajadores permanentes no lo paga (`INA_CONCEPT`) |
| Base mínima contributiva | — | `payroll_rates` (`rule`) | CCSS: SEM ₡346 789 e IVM ₡324 590 en 2026. Sembrada; su efecto en la boleta está por decidir (T-1204) |
| Total obrero ≈ 10,67 %, total patronal ≈ 26,67 % | — | — | **Aproximados, de referencia**: la prueba de la siembra suma los rubros y compara contra lo publicado ese día |
| Tramos del impuesto al salario y créditos por hijo y cónyuge | obrero | `income_tax_brackets`, `income_tax_credits` | Hacienda, decreto del periodo fiscal; se renuevan cada año |
| Salario mínimo inembargable | — | `payroll_rates` (`rule`, monto) | Código de Trabajo art. 172 y el decreto de salarios mínimos vigente |
| Preaviso | — | dominio (`notice_days`) | Código de Trabajo art. 28: 3–6 meses → 1 semana; 6–12 → 15 días; > 1 año → 1 mes |
| Cesantía | — | `severance_table` | art. 29: 3–6 meses → 7 días; 6–12 → 14; 1 año → 19,5; 2 → 20; 3 → 20,5; 4 → 21; 5 → 21,24; 6 → 21,5; 7 a 9 → 22; 10 → 21,5; 11 → 21; 12 → 20,5; 13 o más → 20; **tope de 8 años**. Verificar el texto vigente antes de sembrar |
| Aguinaldo | — | dominio | Ley 2412: 1 dic – 30 nov, ÷ 12, antes del 20 de diciembre, exento |
| Vacaciones | — | dominio | art. 153: dos semanas por cincuenta trabajadas |
| Horas extra y feriados | — | dominio | art. 139 (tiempo y medio) y arts. 148–149 (feriados de pago obligatorio, doble) |
| Jornadas | — | `work_schedules` | art. 136: diurna 8 h y 48 semanales, mixta 7 y 42, nocturna 6 y 36; art. 152: descanso pagado en comercio |
| Incapacidad por enfermedad | patrono los primeros días, CCSS después | `payroll_rates` (`rule`) | Reglamento del Seguro de Salud, art. 35 (la CCSS desde el cuarto día) y jurisprudencia sobre el art. 79: el patrono, al menos medio salario los tres primeros. **Es subsidio y no salario**: sin cargas, sin renta, sin embargos (MTSS, DAJ-AE-201-12) |
| Licencia de maternidad | patrono y CCSS, por mitades | `payroll_rates` (`rule`) | art. 95: y se cotiza sobre la totalidad del salario durante la licencia |
| Salario mínimo inembargable | — | `payroll_rates` (`rule`) | art. 172: el menor salario **mensual** del decreto; en el 45303-MTSS de 2026, el del servicio doméstico, ₡268 731,31 |
| Licencia de maternidad | patrono y CCSS | `payroll_rates` (`rule`) | art. 95 y el reglamento de la CCSS |
| Archivo de planilla para la CCSS | — | `domain/payroll_files.ccss_report` | Se buscó (2026-10-02) y **no está publicada**: solo la guía del formulario de Autogestión (GF-DSCR-F004) y el formulario de ajuste (F071), en `docs/ccss/`. Por eso es un informe con los datos del formulario y no un archivo (§14.6); el archivo, cuando la Dirección SICERE lo entregue (T-1222) |
| Archivo de planilla para el INS | — | `domain/payroll_files.ins_file` | Trazado V08D del generador público de la plantilla del INS más la charla oficial sobre identificaciones, en `docs/ins/README.md`; el documento del INS vive dentro de RT-Virtual y falta cotejarlo (T-1223) |

Lo que el ERP muestra de los dos archivos sirve para saber **qué** piden, no
**cómo** se escriben: el de la CCSS lleva un encabezado con el número
patronal y el mes, una línea por movimiento del empleado —ingreso, salario,
cambio de ocupación, incapacidad (SEM, INS, maternidad), permiso con o sin
goce, exclusión— con sus fechas, y un cierre con los conteos; el del INS, un
encabezado con la póliza y el mes, y por empleado su identificación, nombre,
nacimiento, género, estado civil, nacionalidad, salario, días, horas, si
ingresó o salió en el mes y el código de ocupación del INS. Por eso el
empleado lleva esos datos (RN-72) y el puesto sus dos códigos (RN-95).
