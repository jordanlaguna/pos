-- ============================================================================
--  VentaSys · 010 — Contabilidad (F11, T-1101)
--
--  El sistema ya sabe todo lo que hace falta para llevar un libro: qué se
--  vendió y a qué tarifa, qué se compró y cuánto IVA se pagó, qué entró y qué
--  salió de la caja, y —desde la 009— cuánto cuesta cada producto. Lo que
--  faltaba era el libro. Hoy ese trabajo sale del sistema como un reporte y el
--  contador lo vuelve a escribir en otro programa.
--
--  EL ASIENTO VA EN LA MISMA TRANSACCIÓN (plan §13.1, RN-59)
--
--  La alternativa era una proyección posterior que leyera los eventos y
--  escribiera el libro. Se descartó por una sola razón: admite el estado «venta
--  sin asiento», que es exactamente lo que un libro no puede tener. Un cajero
--  que vende a las 11:59 y un contador que cierra el mes a las 12:00 no pueden
--  depender de que una tarea de fondo haya corrido.
--
--  La objeción —un mapeo incompleto detendría la venta— la resuelve el esquema,
--  no un `try`: la cuenta 1.9.99 «por clasificar» es de sistema y existe desde
--  la activación, así que todo papel sin cuenta asignada tiene dónde caer. El
--  asiento siempre balancea y siempre existe; lo que falta se ve en rojo en la
--  pantalla del contador, no en la caja (RNF-4).
--
--  CORRERLA
--     docker exec -i mysql_db_api sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" posdb' \
--         < backend/migrations/010-contabilidad.sql
--
--  NO ES IDEMPOTENTE: `ADD COLUMN` sobre una columna que ya está falla.
--
--  NO TOCA NINGUNA FILA EXISTENTE. Las cinco tablas nacen vacías y se llenan al
--  activar contabilidad; `sale_details.unit_cost` queda en NULL para todo lo
--  vendido hasta hoy, que es lo cierto: esas ventas no tienen costo congelado y
--  por eso no entran al libro (RN-60).
-- ============================================================================

SET NAMES utf8mb4;


-- ----------------------------------------------------------------------------
-- 1. El catálogo de cuentas
--
--    La jerarquía va **por el texto del código** —'1.1.01' cuelga de '1.1'— y
--    `parent_id` la hace explícita para poder recorrerla sin interpretar
--    cadenas. Las dos dicen lo mismo a propósito: el contador lee códigos y el
--    programa recorre el árbol.
--
--    `is_system` es RN-64: una cuenta que el mapeo necesita no se borra ni se
--    desactiva. No es una preferencia del usuario, es lo que impide que un
--    asiento automático se quede sin dónde caer.
-- ----------------------------------------------------------------------------

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


-- ----------------------------------------------------------------------------
-- 2. Qué cuenta usa cada papel de cada evento
--
--    Un evento tiene varios papeles: la venta en efectivo usa 'cash',
--    'sales_13', 'vat_payable', 'cogs' e 'inventory'. El mapeo es la tabla que
--    traduce el negocio a contabilidad, y es lo único que el contador ajusta
--    para que los asientos automáticos hablen su idioma.
--
--    El UNIQUE (compañía, evento, papel) es la regla: un papel tiene una cuenta
--    y solo una. Lo que **no** está en esta tabla no es un error del esquema —es
--    la cuenta por clasificar, y se resuelve en el dominio (RN-59).
-- ----------------------------------------------------------------------------

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


-- ----------------------------------------------------------------------------
-- 3. Los periodos
--
--    Mensuales, y cerrado no se reabre (RN-61). Reabrir es la puerta por donde
--    un balance ya entregado deja de coincidir con el libro; lo que quedó mal se
--    ajusta en el siguiente, que es lo que un contador hace de todos modos.
--
--    Por eso `closed_at` y `closed_by` no son adorno: cerrar es un acto de
--    alguien, no un estado que aparece.
-- ----------------------------------------------------------------------------

CREATE TABLE accounting_periods (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    company_id INT         NOT NULL,
    `year`     SMALLINT    NOT NULL,
    -- SMALLINT y no el TINYINT del boceto: el byte que se ahorra no paga un tipo
    -- que solo existe en MySQL, y el modelo tiene que decir lo mismo que esto.
    `month`    SMALLINT    NOT NULL,
    status     VARCHAR(10) NOT NULL DEFAULT 'open',   -- 'open' | 'closed'
    closed_at  DATETIME    NULL,
    closed_by  INT         NULL,
    UNIQUE KEY uq_accounting_periods (company_id, `year`, `month`),
    CONSTRAINT fk_ap_company FOREIGN KEY (company_id) REFERENCES companies (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;


-- ----------------------------------------------------------------------------
-- 4. El asiento
--
--    `entry_number` es correlativo por compañía y sin huecos: es lo que pide un
--    libro diario y lo que un auditor cuenta.
--
--    El UNIQUE (compañía, origen, tipo) es la regla de que **un evento deja un
--    asiento automático y solo uno**. Anular una venta no edita su asiento:
--    escribe uno de ajuste que lo revierte, y por eso `kind` entra en la llave
--    —el 'auto' y el 'adjustment' del mismo origen conviven—.
-- ----------------------------------------------------------------------------

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


-- ----------------------------------------------------------------------------
-- 5. Las líneas
--
--    Débito y crédito en dos columnas y no un monto con signo: es como se lee un
--    libro y como se cuadra a ojo. Que una de las dos sea cero lo vigila el
--    dominio y no un CHECK, igual que el resto de las reglas de plata (plan §5):
--    la regla se escribe una vez, en Python, con su prueba.
--
--    `tax_rate` vive en la línea de IVA para que el D-104 sea una consulta sobre
--    el libro y no un cálculo aparte que pueda discrepar (RN-65).
-- ----------------------------------------------------------------------------

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


-- ----------------------------------------------------------------------------
-- 6. El costo se congela al vender (RN-63)
--
--    El costo de ventas de una línea es el costo promedio del producto **al
--    momento de venderse**. Vender hoy 3 unidades con costo ₡110 y comprar
--    mañana a ₡150 no cambia el costo de lo que ya se vendió, y por eso el
--    número vive en la línea y no se lee de `products.cost` al armar el asiento.
--
--    NULL —y no 0— en lo anterior a F11: 0 diría «costó cero», que es falso.
--    NULL dice «no se sabe», y una línea sin costo simplemente no asienta el par
--    costo / inventario.
-- ----------------------------------------------------------------------------

ALTER TABLE sale_details
    ADD COLUMN unit_cost DECIMAL(12,2) NULL;


-- ----------------------------------------------------------------------------
-- 7. Comprobación
--
--    Las cinco tablas nuevas y la columna agregada. Tiene que devolver 6 filas.
-- ----------------------------------------------------------------------------

SELECT 'tabla' AS que, TABLE_NAME AS nombre
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN ('accounts', 'account_mappings', 'accounting_periods',
                     'journal_entries', 'journal_lines')
UNION ALL
SELECT 'columna', CONCAT(TABLE_NAME, '.', COLUMN_NAME)
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'sale_details'
  AND COLUMN_NAME = 'unit_cost'
ORDER BY que, nombre;
