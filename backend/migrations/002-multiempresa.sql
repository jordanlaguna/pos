-- ============================================================================
--  VentaSys · 002 — Multiempresa (F2)
--
--  Convierte una base de un solo negocio en una base compartida por muchas
--  compañías. Es la migración de la que dependen todas las fases siguientes:
--  cualquier tabla que se cree después ya nace con `company_id`.
--
--  Corresponde a task.md T-201 a T-205, T-204b y T-218; plan.md §3.
--
--  ANTES DE CORRERLA
--     mysqldump -uroot -pCLAVE --single-transaction --databases posdb > respaldo.sql
--
--  CORRERLA
--     docker exec -i mysql_db_api sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" posdb' \
--         < backend/migrations/002-multiempresa.sql
--
--  NO ES IDEMPOTENTE. MySQL 8 no tiene `ADD COLUMN IF NOT EXISTS`, así que
--  correrla dos veces falla en el primer ALTER. Falla, no corrompe: la §11
--  comprueba el resultado y se puede consultar cuando haya duda.
-- ============================================================================

-- El cliente `mysql` negocia latin1 si nadie le dice otra cosa, y entonces
-- «Compañía inicial» entra a la base como «CompaÃ±Ã­a inicial». Las tablas son
-- utf8mb4; lo que faltaba era declararlo en la CONEXIÓN.
SET NAMES utf8mb4;

SET @@session.foreign_key_checks = 1;   -- explícito: nada entra sin integridad


-- ----------------------------------------------------------------------------
-- 1. Tablas nuevas (T-201, plan §3.1)
-- ----------------------------------------------------------------------------

CREATE TABLE plans (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    nombre              VARCHAR(60)   NOT NULL,
    precio_mensual      DECIMAL(10,2) NOT NULL DEFAULT 0,
    max_sucursales      INT           NOT NULL DEFAULT 1,
    max_terminales      INT           NOT NULL DEFAULT 1,
    max_usuarios        INT           NOT NULL DEFAULT 3,
    factura_electronica TINYINT(1)    NOT NULL DEFAULT 0
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

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

    -- Idioma (T-204b). Entra acá y no en F8 porque un ALTER sobre tablas con
    -- datos es caro y estas dos columnas ya se saben necesarias. Plan §8.3.
    --
    -- `locale` es el de la pantalla; `document_locale` el de la factura, y son
    -- distintos a propósito: la factura es para el cliente y para Hacienda, no
    -- para el cajero. Una compañía costarricense emite en español aunque su
    -- cajero prefiera usar el POS en portugués.
    locale          VARCHAR(10) NOT NULL DEFAULT 'es',
    document_locale VARCHAR(10) NOT NULL DEFAULT 'es',

    -- La identidad del cliente es el par (afiliado, compañía), no el `id`. El
    -- `id` existe para que las claves foráneas y los índices sean de 4 bytes.
    UNIQUE KEY uq_companies_afiliado_compania (afiliado, compania),
    INDEX idx_companies_estado (estado),
    CONSTRAINT fk_companies_plan FOREIGN KEY (plan_id) REFERENCES plans (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

CREATE TABLE branches (                       -- sucursales
    id         INT AUTO_INCREMENT PRIMARY KEY,
    company_id INT          NOT NULL,
    codigo     CHAR(3)      NOT NULL,         -- 001, formato Hacienda
    nombre     VARCHAR(120) NOT NULL,
    activa     TINYINT(1)   NOT NULL DEFAULT 1,
    UNIQUE KEY uq_branches (company_id, codigo),
    CONSTRAINT fk_branches_company FOREIGN KEY (company_id) REFERENCES companies (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

CREATE TABLE terminals (                      -- cajas
    id         INT AUTO_INCREMENT PRIMARY KEY,
    company_id INT          NOT NULL,
    branch_id  INT          NOT NULL,
    codigo     CHAR(5)      NOT NULL,         -- 00001, formato Hacienda
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

-- Bitácora. `company_id` es NULL cuando la acción no es sobre ninguna compañía
-- —soporte entrando, un intento de login fallido—. Sin clave foránea a
-- propósito: la bitácora tiene que sobrevivir al borrado de aquello que narra.
CREATE TABLE audit_log (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    user_id    INT          NOT NULL,
    company_id INT          NULL,
    accion     VARCHAR(60)  NOT NULL,
    detalle    VARCHAR(500) NULL,
    ip         VARCHAR(45)  NULL,
    creado_el  DATETIME     NOT NULL,
    INDEX idx_audit_company (company_id, creado_el)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;


-- ----------------------------------------------------------------------------
-- 2. La compañía que ya existe (T-203, plan §3.4)
--
--    Lo que hay hoy pasa a ser afiliado 1, compañía 1, activa. No se pierde
--    nada y el negocio que está usando el POS no se entera.
-- ----------------------------------------------------------------------------

INSERT INTO plans (id, nombre, precio_mensual, max_sucursales, max_terminales, max_usuarios, factura_electronica)
     VALUES (1, 'Comercio', 25000.00, 1, 3, 10, 0);

INSERT INTO companies (id, afiliado, compania, nombre, plan_id, estado, creada_el, locale, document_locale)
     VALUES (1, 1, 1, 'Compañía inicial', 1, 'activa', NOW(), 'es', 'es');

INSERT INTO branches (id, company_id, codigo, nombre, activa)
     VALUES (1, 1, '001', 'Casa matriz', 1);

INSERT INTO terminals (id, company_id, branch_id, codigo, nombre, activa)
     VALUES (1, 1, 1, '00001', 'Caja 1', 1);


-- ----------------------------------------------------------------------------
-- 3. Membresías de los usuarios actuales (T-218)
--
--    Se hace ANTES de borrar `users.role`: el rol que cada quien tiene hoy es
--    el que se conserva en su membresía. Después, `users.role` deja de existir
--    (§9) porque el rol pasa a ser por compañía: la misma persona puede ser
--    administradora en su negocio y cajera en el de un socio.
-- ----------------------------------------------------------------------------

INSERT INTO user_companies (user_id, company_id, rol, activa, creada_el)
     SELECT id_user, 1, role, 1, NOW() FROM users;


-- ----------------------------------------------------------------------------
-- 4. `company_id` en las tablas de negocio (T-202)
--
--    Son DOCE, no catorce. `users` y `persons` quedan fuera porque son
--    identidad, no negocio:
--
--      · `users` guarda un correo y una contraseña. Es global por decisión de
--        T-216: un contador que atiende tres locales tiene UNA cuenta y tres
--        membresías.
--      · `persons` es 1 a 1 con `users` —`/persons/register` crea las dos filas
--        juntas y nadie más la referencia—, o sea que es el nombre y la cédula
--        de esa misma identidad. Ponerle `company_id` obligaría a inventar a
--        qué compañía «pertenece» el contador, que es justo el problema que
--        T-216 resolvió. Los datos de los CLIENTES viven en `clients`, que sí
--        lleva `company_id`.
--
--    El DEFAULT 1 hace que las filas que ya existen queden en la compañía 1 sin
--    un UPDATE por tabla; se quita en la §8 para que las filas nuevas estén
--    obligadas a decir a quién pertenecen.
-- ----------------------------------------------------------------------------

ALTER TABLE clients             ADD COLUMN company_id INT NOT NULL DEFAULT 1;
ALTER TABLE categories          ADD COLUMN company_id INT NOT NULL DEFAULT 1;
ALTER TABLE products            ADD COLUMN company_id INT NOT NULL DEFAULT 1;
ALTER TABLE sales               ADD COLUMN company_id INT NOT NULL DEFAULT 1;
ALTER TABLE sale_details        ADD COLUMN company_id INT NOT NULL DEFAULT 1;
ALTER TABLE returns             ADD COLUMN company_id INT NOT NULL DEFAULT 1;
ALTER TABLE return_details      ADD COLUMN company_id INT NOT NULL DEFAULT 1;
ALTER TABLE cash_sessions       ADD COLUMN company_id INT NOT NULL DEFAULT 1;
ALTER TABLE cash_movements      ADD COLUMN company_id INT NOT NULL DEFAULT 1;
ALTER TABLE stock_entries       ADD COLUMN company_id INT NOT NULL DEFAULT 1;
ALTER TABLE stock_entry_details ADD COLUMN company_id INT NOT NULL DEFAULT 1;
ALTER TABLE settings            ADD COLUMN company_id INT NOT NULL DEFAULT 1;

-- `company_id` en las tablas de detalle es desnormalización deliberada: ya se
-- sabe por la cabecera. Se paga un INT por fila a cambio de que el filtro
-- automático de plan §3.3 cubra TODA consulta, incluidas las que entran por el
-- detalle sin pasar por la cabecera —un `SELECT ... FROM sale_details WHERE
-- product_id = ?` no toca `sales` y sin esta columna se leería sin filtrar—.


-- ----------------------------------------------------------------------------
-- 5. Sucursal y terminal (T-210, RN-14)
--
--    Dónde y en qué caja ocurrió cada hecho. Hacienda los pide en el
--    consecutivo del comprobante (sucursal de 3 dígitos, terminal de 5), así
--    que sellarlos ahora evita tener que inventarlos en F6.
--
--    `cash_movements` NO lleva `terminal_id`: un movimiento pertenece a un
--    turno y el turno ya dice en qué caja fue. La redundancia de `company_id`
--    de la §4 tiene una razón —el filtro automático—; esta no tendría ninguna.
-- ----------------------------------------------------------------------------

ALTER TABLE sales         ADD COLUMN branch_id   INT NOT NULL DEFAULT 1,
                          ADD COLUMN terminal_id INT NOT NULL DEFAULT 1;
ALTER TABLE returns       ADD COLUMN branch_id   INT NOT NULL DEFAULT 1,
                          ADD COLUMN terminal_id INT NOT NULL DEFAULT 1;
ALTER TABLE cash_sessions ADD COLUMN terminal_id INT NOT NULL DEFAULT 1;
ALTER TABLE stock_entries ADD COLUMN branch_id   INT NOT NULL DEFAULT 1;


-- ----------------------------------------------------------------------------
-- 6. Los UNIQUE globales pasan a ser por compañía
--
--    Este es el punto donde la base deja de ser de un solo negocio. Hoy dos
--    compañías no podrían tener las dos una categoría «Bebidas», ni un cliente
--    con la misma cédula, ni empezar su numeración de facturas en 0001.
--
--    `persons.identification` y `users.email` NO se tocan: son identidad y
--    siguen siendo únicos en todo el sistema. Dos personas distintas no
--    comparten cédula aunque trabajen en compañías distintas.
-- ----------------------------------------------------------------------------

ALTER TABLE categories DROP INDEX name,
                       ADD UNIQUE KEY uq_categories_company_name (company_id, name);

ALTER TABLE clients DROP INDEX identification,
                    DROP INDEX email,
                    ADD UNIQUE KEY uq_clients_company_identification (company_id, identification),
                    ADD UNIQUE KEY uq_clients_company_email (company_id, email);

ALTER TABLE sales DROP INDEX sale_number,
                  ADD UNIQUE KEY uq_sales_company_number (company_id, sale_number);

-- `products.barcode` no era único ni siquiera antes: solo tenía índice. Se
-- vuelve único POR COMPAÑÍA, que es lo que el escáner necesita —una lectura,
-- un producto—. Los nulos no chocan entre sí en MySQL, así que los productos
-- sin código de barras siguen conviviendo.
ALTER TABLE products ADD UNIQUE KEY uq_products_company_barcode (company_id, barcode);

-- `settings` deja de ser «la fila 1» y pasa a ser «la fila de cada compañía»
-- (T-204). El UNIQUE es lo que impide que aparezcan dos.
ALTER TABLE settings ADD UNIQUE KEY uq_settings_company (company_id);


-- ----------------------------------------------------------------------------
-- 7. Idioma de cada persona (T-204b, plan §8.3)
--
--    NULL significa «lo que diga la compañía». Es la diferencia entre no haber
--    elegido y haber elegido español: si mañana la compañía cambia a portugués,
--    quien nunca tocó el ajuste se va con ella y quien eligió se queda.
-- ----------------------------------------------------------------------------

ALTER TABLE users ADD COLUMN locale VARCHAR(10) NULL;


-- ----------------------------------------------------------------------------
-- 8. Se quitan los DEFAULT
--
--    Cumplieron su función en la §4: llenar las filas que ya existían. A partir
--    de acá, una fila nueva que no diga a qué compañía pertenece es un error de
--    programación, y tiene que fallar en la base y no quedar en la compañía 1.
-- ----------------------------------------------------------------------------

ALTER TABLE clients             ALTER COLUMN company_id DROP DEFAULT;
ALTER TABLE categories          ALTER COLUMN company_id DROP DEFAULT;
ALTER TABLE products            ALTER COLUMN company_id DROP DEFAULT;
ALTER TABLE sales               ALTER COLUMN company_id DROP DEFAULT;
ALTER TABLE sale_details        ALTER COLUMN company_id DROP DEFAULT;
ALTER TABLE returns             ALTER COLUMN company_id DROP DEFAULT;
ALTER TABLE return_details      ALTER COLUMN company_id DROP DEFAULT;
ALTER TABLE cash_sessions       ALTER COLUMN company_id DROP DEFAULT;
ALTER TABLE cash_movements      ALTER COLUMN company_id DROP DEFAULT;
ALTER TABLE stock_entries       ALTER COLUMN company_id DROP DEFAULT;
ALTER TABLE stock_entry_details ALTER COLUMN company_id DROP DEFAULT;
ALTER TABLE settings            ALTER COLUMN company_id DROP DEFAULT;

ALTER TABLE sales         ALTER COLUMN branch_id   DROP DEFAULT,
                          ALTER COLUMN terminal_id DROP DEFAULT;
ALTER TABLE returns       ALTER COLUMN branch_id   DROP DEFAULT,
                          ALTER COLUMN terminal_id DROP DEFAULT;
ALTER TABLE cash_sessions ALTER COLUMN terminal_id DROP DEFAULT;
ALTER TABLE stock_entries ALTER COLUMN branch_id   DROP DEFAULT;


-- ----------------------------------------------------------------------------
-- 9. `users.role` desaparece (T-218, RN-3)
--
--    El rol dejó de ser una propiedad de la persona. Ya está copiado en
--    `user_companies` (§3); acá se borra la columna vieja para que nadie pueda
--    leerla por costumbre y obtener una respuesta que ya no significa nada.
-- ----------------------------------------------------------------------------

ALTER TABLE users DROP COLUMN role;


-- ----------------------------------------------------------------------------
-- 10. Claves foráneas
--
--     Van al final, cuando las columnas ya tienen valores válidos. Cada una
--     crea su índice sobre `company_id`, que es el que usa el filtro
--     automático en cada consulta.
--
--     Además de la integridad, sirven para T-217: al borrar o restaurar una
--     compañía, las foráneas obligan a hacerlo en el orden correcto en vez de
--     confiar en que el script lo recuerde.
-- ----------------------------------------------------------------------------

ALTER TABLE clients             ADD CONSTRAINT fk_clients_company             FOREIGN KEY (company_id) REFERENCES companies (id);
ALTER TABLE categories          ADD CONSTRAINT fk_categories_company          FOREIGN KEY (company_id) REFERENCES companies (id);
ALTER TABLE products            ADD CONSTRAINT fk_products_company            FOREIGN KEY (company_id) REFERENCES companies (id);
ALTER TABLE sales               ADD CONSTRAINT fk_sales_company               FOREIGN KEY (company_id) REFERENCES companies (id);
ALTER TABLE sale_details        ADD CONSTRAINT fk_sale_details_company        FOREIGN KEY (company_id) REFERENCES companies (id);
ALTER TABLE returns             ADD CONSTRAINT fk_returns_company             FOREIGN KEY (company_id) REFERENCES companies (id);
ALTER TABLE return_details      ADD CONSTRAINT fk_return_details_company      FOREIGN KEY (company_id) REFERENCES companies (id);
ALTER TABLE cash_sessions       ADD CONSTRAINT fk_cash_sessions_company       FOREIGN KEY (company_id) REFERENCES companies (id);
ALTER TABLE cash_movements      ADD CONSTRAINT fk_cash_movements_company      FOREIGN KEY (company_id) REFERENCES companies (id);
ALTER TABLE stock_entries       ADD CONSTRAINT fk_stock_entries_company       FOREIGN KEY (company_id) REFERENCES companies (id);
ALTER TABLE stock_entry_details ADD CONSTRAINT fk_stock_entry_details_company FOREIGN KEY (company_id) REFERENCES companies (id);
ALTER TABLE settings            ADD CONSTRAINT fk_settings_company            FOREIGN KEY (company_id) REFERENCES companies (id);

ALTER TABLE sales         ADD CONSTRAINT fk_sales_branch           FOREIGN KEY (branch_id)   REFERENCES branches (id),
                          ADD CONSTRAINT fk_sales_terminal         FOREIGN KEY (terminal_id) REFERENCES terminals (id);
ALTER TABLE returns       ADD CONSTRAINT fk_returns_branch         FOREIGN KEY (branch_id)   REFERENCES branches (id),
                          ADD CONSTRAINT fk_returns_terminal       FOREIGN KEY (terminal_id) REFERENCES terminals (id);
ALTER TABLE cash_sessions ADD CONSTRAINT fk_cash_sessions_terminal FOREIGN KEY (terminal_id) REFERENCES terminals (id);
ALTER TABLE stock_entries ADD CONSTRAINT fk_stock_entries_branch   FOREIGN KEY (branch_id)   REFERENCES branches (id);


-- ----------------------------------------------------------------------------
-- 11. Verificación
--
--     Se corre después de la migración. Las tres consultas tienen que dar lo
--     que dice el comentario; si alguna no, algo quedó a medias.
-- ----------------------------------------------------------------------------

-- Ninguna fila de negocio puede haber quedado sin compañía. Esperado: 0 filas.
SELECT 'huerfanas' AS control, t.tabla, t.sin_compania
  FROM (
        SELECT 'clients'             AS tabla, COUNT(*) AS sin_compania FROM clients             WHERE company_id IS NULL OR company_id = 0
  UNION SELECT 'categories',          COUNT(*) FROM categories          WHERE company_id IS NULL OR company_id = 0
  UNION SELECT 'products',            COUNT(*) FROM products            WHERE company_id IS NULL OR company_id = 0
  UNION SELECT 'sales',               COUNT(*) FROM sales               WHERE company_id IS NULL OR company_id = 0
  UNION SELECT 'sale_details',        COUNT(*) FROM sale_details        WHERE company_id IS NULL OR company_id = 0
  UNION SELECT 'returns',             COUNT(*) FROM returns             WHERE company_id IS NULL OR company_id = 0
  UNION SELECT 'return_details',      COUNT(*) FROM return_details      WHERE company_id IS NULL OR company_id = 0
  UNION SELECT 'cash_sessions',       COUNT(*) FROM cash_sessions       WHERE company_id IS NULL OR company_id = 0
  UNION SELECT 'cash_movements',      COUNT(*) FROM cash_movements      WHERE company_id IS NULL OR company_id = 0
  UNION SELECT 'stock_entries',       COUNT(*) FROM stock_entries       WHERE company_id IS NULL OR company_id = 0
  UNION SELECT 'stock_entry_details', COUNT(*) FROM stock_entry_details WHERE company_id IS NULL OR company_id = 0
  UNION SELECT 'settings',            COUNT(*) FROM settings            WHERE company_id IS NULL OR company_id = 0
       ) t
 WHERE t.sin_compania > 0;

-- Cada usuario tiene su membresía con el rol que tenía. Esperado: tantas
-- membresías como usuarios.
SELECT 'membresias' AS control,
       (SELECT COUNT(*) FROM users)          AS usuarios,
       (SELECT COUNT(*) FROM user_companies) AS membresias;

-- Las cifras de referencia de progress.json no se movieron.
SELECT 'invariantes' AS control,
       (SELECT COUNT(*) FROM sales)      AS ventas,
       (SELECT SUM(total) FROM sales)    AS total_vendido,
       (SELECT COUNT(*) FROM products)   AS productos;
