# VentaSys — Plan técnico

> **Qué es este documento.** Cómo se construye lo que define
> [spec.md](spec.md). Las tareas concretas y su orden están en
> [task.md](task.md).
>
> Actualizado: 2026-08-16

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
│   ├── entities/           Sale, Product, CashSession, StockEntry
│   ├── values/             Money, TaxRate, Barcode, Consecutive
│   └── services/           reglas: totales, arqueo, validez de devolución
├── application/
│   ├── use_cases/          CreateSale, CloseCashSession, RegisterStockEntry
│   └── ports/              SaleRepository, ProductRepository, Clock,
│                           CabysCatalog, PasswordHasher, TokenIssuer
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

---

## 4. Panel de soporte (F3)

Grupo de rutas `/admin` en el mismo despliegue, no una aplicación aparte:
duplicar autenticación y despliegue para cinco pantallas no se paga.

- Solo rol `soporte`, verificado en el servidor en cada `load` y cada acción.
- Su sesión **no tiene compañía**: las pantallas del POS le responden 403.
- *Entrar como* emite un token con el `company_id` de la compañía destino, con
  vencimiento corto y motivo obligatorio, y escribe en `audit_log`. La interfaz
  muestra una franja permanente mientras dure.
- Toda acción de soporte se registra: alta, cambio de estado, entrada.

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

### 7.1 Certificado y PIN (entra en F6)

```sql
CREATE TABLE fe_credentials (
    company_id     INT PRIMARY KEY,
    archivo        LONGTEXT     NOT NULL,   -- .p12 cifrado, base64
    pin            VARBINARY(512) NOT NULL, -- cifrado
    nombre_archivo VARCHAR(160) NULL,
    vence_el       DATE         NULL,
    subido_el      DATETIME     NOT NULL,
    subido_por     INT          NOT NULL,
    CONSTRAINT fk_fe_credentials_company FOREIGN KEY (company_id) REFERENCES companies (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;
```

- **AES-256-GCM** con llave de 32 bytes en la variable de entorno
  `FE_CRYPTO_KEY`, con el `company_id` como dato asociado: un registro copiado a
  otra compañía no descifra.
- La llave vive **fuera de la base**. Un respaldo robado no alcanza para firmar.
- El `.p12` se descifra en memoria, solo al firmar, y no se escribe a disco.
- `GET` devuelve `{ configurado, nombre_archivo, vence_el, subido_el }`. El
  archivo y el PIN **no tienen** endpoint de lectura. No existe el camino.
- No se registran en bitácora ni en trazas de error.

**Consecuencia asumida:** si se pierde `FE_CRYPTO_KEY`, cada compañía tiene que
volver a subir su certificado. Es preferible a la alternativa, que es que la
llave viaje con los datos que protege.

### 7.2 Emisión (F7 — decisión pendiente)

No se programa hasta decidir la ruta. Lo que hay que resolver:

| | Directo | Vía proveedor autorizado |
|---|---|---|
| Firma XAdES-EPES | nuestra | del proveedor |
| Cambios de esquema de Hacienda | los seguimos nosotros | los sigue el proveedor |
| Costo | cero por documento | mensual o por documento |
| Salir a producción | lento | rápido |
| Dependencia | ninguna | fuerte |

**Diseño que no obliga a decidir hoy:** la emisión se define como una interfaz
(`EmisorFE`: `emitir(venta) → {clave, consecutivo, estado}`, `consultar(clave)`)
con dos implementaciones posibles. Todo lo demás —CABYS, tarifas, numeración,
sucursal, terminal, datos del receptor, cola de reintentos, contingencia— es
igual en ambos casos y es lo que se construye en F5 y F6.

Piezas que faltarían en cualquiera de las dos rutas: clave de 50 dígitos,
consecutivo de 20 sin huecos (con bloqueo de fila por terminal), envío
asíncrono con consulta de estado, entrega al receptor por correo con XML y PDF,
y modo contingencia para poder cobrar con Hacienda caída.

---

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
| **F6** Preparación FE | Certificado cifrado, sucursales, terminales, actividad | Se sube un `.p12`, se ve su estado y no hay forma de leerlo de vuelta |
| **F7** Emisión | (decisión pendiente) | — |
| **F8** Multi-idioma | Español, inglés y portugués; el backend deja de escribir texto | Los tres catálogos tienen las mismas claves y la build se cae si alguien escribe una cadena dentro de un componente |

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

---

## 10. Riesgos

| Riesgo | Mitigación |
|---|---|
| Una consulta sin filtro filtra datos entre compañías | Filtro automático en el ORM + pruebas de cruce en todos los endpoints |
| `with_loader_criteria` no cubre el SQL agregado de reportes ni los UPDATE masivos | Filtro escrito a mano en `crud_report.py`, con prueba propia. Revisar en cada agregado nuevo |
| El refactor de F2 toca todos los archivos y puede romper lo que ya funciona | Las pruebas de F1 son la red. Por eso F1 va antes: los invariantes de `progress.json` dejan de comprobarse a mano y pasan a correr solos |
| Reorganizar por capas (F1) es mover mucho código sin cambiar comportamiento, que es donde se cuelan los errores silenciosos | Pruebas de caracterización **antes** de mover nada, y se mueve capa por capa, no todo junto |
| La cobertura del 100 % empuja a escribir pruebas de relleno para pasar el umbral | El umbral cubre solo dominio y aplicación, que son código puro y de reglas. Ahí una función sin prueba es una regla sin verificar, no burocracia |
| `FE_CRYPTO_KEY` se pierde | Documentado: hay que volver a subir los certificados. Se guarda fuera del repositorio y fuera de la base |
| El API de CABYS no responde | Caché local; la venta nunca depende de él |
| Borrar los clones de referencia | Están en GitHub y el análisis quedó escrito en `progress.json` y en `backend/README.md` |
| El impuesto por línea toca dinero ya verificado | Los invariantes de `progress.json` se recalculan y se documentan de nuevo |
