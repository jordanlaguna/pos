-- ============================================================================
--  VentaSys · 023 — Inventario a fondo (F15, T-1502; spec §5.10, plan §15)
--
--  LA EXISTENCIA DEJA DE SER UNA COLUMNA Y PASA A SER UNA SUMA
--
--  Hasta acá `products.stock` era la única verdad y cinco sitios la escribían
--  sin dejar constancia de cuánto había antes. Desde F15 cada variación deja
--  un movimiento en el KÁRDEX (`stock_movements`), con antes y después, por
--  sucursal; la existencia por sucursal vive en `stock_levels`, y
--  `products.stock` se conserva como la suma de las sucursales, mantenida en
--  la misma transacción con `UPDATE … stock = stock + :delta`. Si discrepan,
--  manda el kárdex (RN-98).
--
--  ONCE TABLAS, TODAS DE LA COMPAÑÍA
--
--  Las de toda la fase, aunque T-1502 use cuatro: el modelo y la migración
--  tienen que decir lo mismo (test_esquema.py), y partirla dejaría dos
--  esquemas según cuándo la aplique cada quien. Los estados van en inglés,
--  como los de planilla; `stock_entries` conserva los suyos en español porque
--  ya existen.
--
--  EL KÁRDEX EMPIEZA HOY (RN-105)
--
--  La existencia que cada producto tenía se reparte a la sucursal ACTIVA DE
--  MENOR CÓDIGO —la misma que `sucursal_y_terminal` le da hoy a toda sesión—
--  como un movimiento de apertura con la fecha de la migración. No se
--  reconstruye la historia: lo anterior no guardó antes y después. Una
--  existencia negativa no puede ser una apertura: queda en cero y se lista
--  ANTES de tocarla, para contarla a mano.
--
--  GUARDAS ANTES DEL DDL
--
--  Toda compañía con existencias necesita un administrador activo y aceptado
--  que firme la apertura, y una sucursal activa adonde ponerla. Se comprueba
--  ANTES de crear ninguna tabla: MySQL confirma el DDL solo, así que una
--  guarda que corriera después dejaría la migración a medias.
--
--  IDEMPOTENTE, COMO LA 019: todo CREATE lleva IF NOT EXISTS, las columnas
--  van por `ventasys_add_column` (013) y los INSERT de datos se protegen con
--  NOT EXISTS. Hace falta justamente porque la guarda puede detenerla.
--
--  CORRERLA
--     docker exec -i mysql_db_api sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" posdb' \
--         < backend/migrations/023-inventario.sql
--  Y DESPUÉS REINICIAR LA API: el modelo nuevo contra la tabla vieja da
--  `Unknown column 'products.min_stock'` en cada petición.
-- ============================================================================

SET NAMES utf8mb4;

-- ---------------------------------------------------------------- guardas

DROP PROCEDURE IF EXISTS ventasys_check_inventory;
DELIMITER //
CREATE PROCEDURE ventasys_check_inventory()
BEGIN
    DECLARE sin_admin INT;
    DECLARE sin_sucursal INT;
    -- Hoy una compañía cuyo único admin es una invitación pendiente es legal
    -- (`last_admin` no mira `aceptada_el`); si la hay, la salida es aceptar la
    -- invitación o correr bootstrap, y volver a aplicar.
    SELECT COUNT(*) INTO sin_admin
      FROM (SELECT DISTINCT company_id FROM products WHERE stock > 0) p
     WHERE NOT EXISTS (SELECT 1 FROM user_companies uc
                        WHERE uc.company_id = p.company_id AND uc.rol = 'admin'
                          AND uc.activa = 1 AND uc.aceptada_el IS NOT NULL);
    IF sin_admin > 0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'companies without an active admin: run bootstrap first';
    END IF;
    SELECT COUNT(*) INTO sin_sucursal
      FROM (SELECT DISTINCT company_id FROM products WHERE stock > 0) p
     WHERE NOT EXISTS (SELECT 1 FROM branches b WHERE b.company_id = p.company_id AND b.activa = 1);
    IF sin_sucursal > 0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'companies with stock and no active branch';
    END IF;
END //
DELIMITER ;
CALL ventasys_check_inventory();
DROP PROCEDURE ventasys_check_inventory;

-- Lo que no puede ser apertura, listado ANTES de tocarlo (RN-105).
SELECT company_id, id_product, name, stock AS negative_stock
  FROM products WHERE stock < 0;

-- `ventasys_add_column` como en la 013 y la 016, y su hermana para una
-- foránea. Las dos se borran al final.
DROP PROCEDURE IF EXISTS ventasys_add_column;
DELIMITER //
CREATE PROCEDURE ventasys_add_column(
    IN tabla VARCHAR(64), IN columna VARCHAR(64), IN definicion TEXT
)
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = tabla AND COLUMN_NAME = columna
    ) THEN
        SET @sql := CONCAT('ALTER TABLE ', tabla, ' ADD COLUMN ', columna, ' ', definicion);
        PREPARE stmt FROM @sql;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END IF;
END //
DELIMITER ;

-- `CONSTRAINT_SCHEMA = DATABASE()` y no solo el nombre: en una instancia con
-- `posdb` y `posdb_test` vería la foránea de la otra base y se la saltaría.
DROP PROCEDURE IF EXISTS ventasys_add_constraint;
DELIMITER //
CREATE PROCEDURE ventasys_add_constraint(
    IN tabla VARCHAR(64), IN nombre VARCHAR(64), IN definicion TEXT
)
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.TABLE_CONSTRAINTS
        WHERE CONSTRAINT_SCHEMA = DATABASE() AND TABLE_NAME = tabla AND CONSTRAINT_NAME = nombre
    ) THEN
        SET @sql := CONCAT('ALTER TABLE ', tabla, ' ADD CONSTRAINT ', nombre, ' ', definicion);
        PREPARE stmt FROM @sql;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END IF;
END //
DELIMITER ;

-- -------------------------------------------------------------- esquema

-- Marca, lote y vencimiento (RN-104). Van primero: los referencian los demás.
CREATE TABLE IF NOT EXISTS brands (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    company_id INT         NOT NULL,
    name       VARCHAR(80) NOT NULL,
    is_active  TINYINT(1)  NOT NULL DEFAULT 1,
    UNIQUE KEY uq_brands_name (company_id, name),
    CONSTRAINT fk_brands_company FOREIGN KEY (company_id) REFERENCES companies (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

CREATE TABLE IF NOT EXISTS stock_lots (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    company_id INT         NOT NULL,
    product_id INT         NOT NULL,
    code       VARCHAR(40) NOT NULL,
    expires_at DATE        NULL,
    created_at DATETIME    NOT NULL,
    UNIQUE KEY uq_stock_lots (product_id, code),
    INDEX idx_stock_lots_expiry (company_id, expires_at),
    CONSTRAINT fk_lots_company FOREIGN KEY (company_id) REFERENCES companies (id),
    CONSTRAINT fk_lots_product FOREIGN KEY (product_id) REFERENCES products (id_product)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

-- El mínimo propio (RN-101; NULL usa el general de Configuración) y la marca.
CALL ventasys_add_column('products', 'min_stock', 'INT NULL');
CALL ventasys_add_column('products', 'brand_id', 'INT NULL');
CALL ventasys_add_constraint('products', 'fk_products_brand',
     'FOREIGN KEY (brand_id) REFERENCES brands (id)');

-- El kárdex (RN-98). Una fila por variación, nunca se edita ni se borra: la
-- anulación de una entrada es otro movimiento, con signo contrario.
CREATE TABLE IF NOT EXISTS stock_movements (
    id             BIGINT        AUTO_INCREMENT PRIMARY KEY,
    company_id     INT           NOT NULL,
    product_id     INT           NOT NULL,
    branch_id      INT           NOT NULL,
    kind           VARCHAR(16)   NOT NULL,   -- 'opening' | 'sale' | 'sale_void' | 'return' | 'entry' | 'entry_void'
                                             -- | 'exit' | 'exit_void' | 'count' | 'transfer_out' | 'transfer_in'
    quantity       INT           NOT NULL,   -- con signo: negativo baja
    before_qty     INT           NOT NULL,   -- en ESTA sucursal
    after_qty      INT           NOT NULL,
    unit_cost      DECIMAL(12,2) NOT NULL DEFAULT 0,   -- con el que se valoró (RN-98)
    avg_cost_after DECIMAL(12,2) NOT NULL DEFAULT 0,   -- el promedio del producto DESPUÉS de este movimiento (RN-103)
    lot_id         INT           NULL,       -- RN-104; NULL es «sin lote»
    source_type    VARCHAR(16)   NOT NULL,   -- 'product' | 'sale' | 'return' | 'stock_entry' | 'stock_exit' | 'stock_count' | 'stock_transfer'
    source_id      INT           NOT NULL,
    source_line    INT           NULL,       -- la línea del documento: una línea con lotes deja varios movimientos
    user_id        INT           NOT NULL,
    moved_at       DATETIME      NOT NULL,   -- la pone el servidor
    INDEX idx_stock_movements_product (company_id, product_id, moved_at),
    INDEX idx_stock_movements_branch  (company_id, branch_id, moved_at),
    INDEX idx_stock_movements_source  (source_type, source_id),
    -- La venta con lotes pregunta «cuánto hay de cada lote de ESTE producto en
    -- ESTA sucursal»; un índice solo por lote no la sirve.
    INDEX idx_stock_movements_lot     (company_id, product_id, branch_id, lot_id),
    CONSTRAINT fk_sm_company FOREIGN KEY (company_id) REFERENCES companies (id),
    CONSTRAINT fk_sm_product FOREIGN KEY (product_id) REFERENCES products (id_product),
    CONSTRAINT fk_sm_branch  FOREIGN KEY (branch_id)  REFERENCES branches (id),
    CONSTRAINT fk_sm_lot     FOREIGN KEY (lot_id)     REFERENCES stock_lots (id),
    CONSTRAINT fk_sm_user    FOREIGN KEY (user_id)    REFERENCES users (id_user)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

-- La existencia por sucursal (RN-102): la caché que el kárdex mantiene.
CREATE TABLE IF NOT EXISTS stock_levels (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    company_id INT NOT NULL,
    product_id INT NOT NULL,
    branch_id  INT NOT NULL,
    quantity   INT NOT NULL DEFAULT 0,
    UNIQUE KEY uq_stock_levels (product_id, branch_id),
    INDEX idx_stock_levels_branch (company_id, branch_id),
    CONSTRAINT fk_sl_company FOREIGN KEY (company_id) REFERENCES companies (id),
    CONSTRAINT fk_sl_product FOREIGN KEY (product_id) REFERENCES products (id_product),
    CONSTRAINT fk_sl_branch  FOREIGN KEY (branch_id)  REFERENCES branches (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

-- Los motivos de salida (RN-99). Catálogo de la compañía, como las categorías:
-- se desactivan, no se borran, porque las salidas viejas los referencian.
CREATE TABLE IF NOT EXISTS stock_reasons (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    company_id INT          NOT NULL,
    code       VARCHAR(20)  NOT NULL,   -- 'shrinkage' | 'damage' | 'expired' | 'internal_use' | 'sample' | 'count' | libre
    name       VARCHAR(80)  NOT NULL,   -- lo escribe la compañía; los sembrados llegan con el nombre de la plantilla
    is_system  TINYINT(1)   NOT NULL DEFAULT 0,   -- 'count' lo usa la toma física y no se desactiva (RN-100)
    is_active  TINYINT(1)   NOT NULL DEFAULT 1,
    UNIQUE KEY uq_stock_reasons_code (company_id, code),
    CONSTRAINT fk_sr_company FOREIGN KEY (company_id) REFERENCES companies (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

-- La salida (RN-99). Espejo de stock_entries, sin proveedor ni impuesto.
CREATE TABLE IF NOT EXISTS stock_exits (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    company_id    INT           NOT NULL,
    branch_id     INT           NOT NULL,
    reason_id     INT           NOT NULL,
    user_id       INT           NOT NULL,
    created_at    DATETIME      NOT NULL,
    notes         VARCHAR(255)  NULL,
    status        VARCHAR(20)   NOT NULL DEFAULT 'applied',   -- 'applied' | 'voided'
    total_cost    DECIMAL(12,2) NOT NULL DEFAULT 0,
    voided_at     DATETIME      NULL,
    void_reason   VARCHAR(255)  NULL,
    INDEX idx_stock_exits_branch (company_id, branch_id, created_at),
    CONSTRAINT fk_sx_company FOREIGN KEY (company_id) REFERENCES companies (id),
    CONSTRAINT fk_sx_branch  FOREIGN KEY (branch_id)  REFERENCES branches (id),
    CONSTRAINT fk_sx_reason  FOREIGN KEY (reason_id)  REFERENCES stock_reasons (id),
    CONSTRAINT fk_sx_user    FOREIGN KEY (user_id)    REFERENCES users (id_user)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

CREATE TABLE IF NOT EXISTS stock_exit_details (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    company_id INT           NOT NULL,
    exit_id    INT           NOT NULL,
    product_id INT           NOT NULL,
    quantity   INT           NOT NULL,
    unit_cost  DECIMAL(12,2) NOT NULL DEFAULT 0,   -- el promedio al salir (RN-99)
    lot_id     INT           NULL,                 -- NULL es «sin lote», elegido a propósito (RN-104)
    INDEX idx_stock_exit_details_exit (exit_id),
    CONSTRAINT fk_sxd_company FOREIGN KEY (company_id) REFERENCES companies (id),
    CONSTRAINT fk_sxd_exit    FOREIGN KEY (exit_id)    REFERENCES stock_exits (id),
    CONSTRAINT fk_sxd_product FOREIGN KEY (product_id) REFERENCES products (id_product),
    CONSTRAINT fk_sxd_lot     FOREIGN KEY (lot_id)     REFERENCES stock_lots (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

-- El traslado (RN-102). Sin estado: no se anula, se hace otro al revés.
CREATE TABLE IF NOT EXISTS stock_transfers (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    company_id     INT          NOT NULL,
    from_branch_id INT          NOT NULL,
    to_branch_id   INT          NOT NULL,
    user_id        INT          NOT NULL,
    created_at     DATETIME     NOT NULL,
    notes          VARCHAR(255) NULL,
    INDEX idx_stock_transfers_company (company_id, created_at),
    CONSTRAINT fk_st_company FOREIGN KEY (company_id)     REFERENCES companies (id),
    CONSTRAINT fk_st_from    FOREIGN KEY (from_branch_id) REFERENCES branches (id),
    CONSTRAINT fk_st_to      FOREIGN KEY (to_branch_id)   REFERENCES branches (id),
    CONSTRAINT fk_st_user    FOREIGN KEY (user_id)        REFERENCES users (id_user)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

CREATE TABLE IF NOT EXISTS stock_transfer_details (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    company_id  INT NOT NULL,
    transfer_id INT NOT NULL,
    product_id  INT NOT NULL,
    quantity    INT NOT NULL,
    lot_id      INT NULL,
    INDEX idx_stock_transfer_details_transfer (transfer_id),
    CONSTRAINT fk_std_company  FOREIGN KEY (company_id)  REFERENCES companies (id),
    CONSTRAINT fk_std_transfer FOREIGN KEY (transfer_id) REFERENCES stock_transfers (id),
    CONSTRAINT fk_std_product  FOREIGN KEY (product_id)  REFERENCES products (id_product),
    CONSTRAINT fk_std_lot      FOREIGN KEY (lot_id)      REFERENCES stock_lots (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

-- La toma física (RN-100).
CREATE TABLE IF NOT EXISTS stock_counts (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    company_id  INT          NOT NULL,
    branch_id   INT          NOT NULL,
    category_id INT          NULL,         -- NULL: toda la sucursal; una raíz incluye sus hijas (RN-100)
    status      VARCHAR(20)  NOT NULL DEFAULT 'open',   -- 'open' | 'applied' | 'discarded'
    opened_by   INT          NOT NULL,
    opened_at   DATETIME     NOT NULL,
    closed_by   INT          NULL,
    closed_at   DATETIME     NULL,
    notes       VARCHAR(255) NULL,
    INDEX idx_stock_counts_branch (company_id, branch_id, status),
    CONSTRAINT fk_sc_company  FOREIGN KEY (company_id)  REFERENCES companies (id),
    CONSTRAINT fk_sc_branch   FOREIGN KEY (branch_id)   REFERENCES branches (id),
    CONSTRAINT fk_sc_category FOREIGN KEY (category_id) REFERENCES categories (id),
    CONSTRAINT fk_sc_opened   FOREIGN KEY (opened_by)   REFERENCES users (id_user),
    CONSTRAINT fk_sc_closed   FOREIGN KEY (closed_by)   REFERENCES users (id_user)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

CREATE TABLE IF NOT EXISTS stock_count_lines (
    id          INT      AUTO_INCREMENT PRIMARY KEY,
    company_id  INT      NOT NULL,
    count_id    INT      NOT NULL,
    product_id  INT      NOT NULL,
    lot_id      INT      NULL,
    -- En MySQL dos NULL no chocan en un UNIQUE, y «sin lote» es NULL: la
    -- columna generada vuelve 0 ese caso para que la clave sí lo cuide
    -- (mismo truco que `parent_key` en la 005).
    lot_key     INT AS (IFNULL(lot_id, 0)) STORED NOT NULL,
    system_qty  INT      NOT NULL,   -- lo que decía el sistema AL CONTAR (RN-100)
    counted_qty INT      NOT NULL,
    counted_at  DATETIME NOT NULL,
    counted_by  INT      NOT NULL,
    UNIQUE KEY uq_stock_count_lines (count_id, product_id, lot_key),
    CONSTRAINT fk_scl_company FOREIGN KEY (company_id) REFERENCES companies (id),
    CONSTRAINT fk_scl_count   FOREIGN KEY (count_id)   REFERENCES stock_counts (id),
    CONSTRAINT fk_scl_product FOREIGN KEY (product_id) REFERENCES products (id_product),
    CONSTRAINT fk_scl_lot     FOREIGN KEY (lot_id)     REFERENCES stock_lots (id),
    CONSTRAINT fk_scl_user    FOREIGN KEY (counted_by) REFERENCES users (id_user)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

-- ------------------------------------------------------------------ datos

-- La existencia que había, a la sucursal ACTIVA DE MENOR CÓDIGO, como
-- apertura con la fecha de la migración (RN-105). Un producto en cero no deja
-- fila: el kárdex empieza cuando algo pasa. Lo negativo se listó arriba.
INSERT INTO stock_levels (company_id, product_id, branch_id, quantity)
SELECT p.company_id, p.id_product, b.id, p.stock
FROM products p
JOIN branches b ON b.company_id = p.company_id
WHERE b.id = (SELECT id FROM branches
               WHERE company_id = p.company_id AND activa = 1
               ORDER BY codigo, id LIMIT 1)
  AND p.stock > 0
  AND NOT EXISTS (SELECT 1 FROM stock_levels l WHERE l.product_id = p.id_product);

INSERT INTO stock_movements (company_id, product_id, branch_id, kind, quantity, before_qty, after_qty,
                             unit_cost, avg_cost_after, source_type, source_id, user_id, moved_at)
SELECT l.company_id, l.product_id, l.branch_id, 'opening', l.quantity, 0, l.quantity,
       p.cost, p.cost, 'product', p.id_product,
       (SELECT MIN(user_id) FROM user_companies
         WHERE company_id = l.company_id AND rol = 'admin' AND activa = 1 AND aceptada_el IS NOT NULL),
       NOW()
FROM stock_levels l JOIN products p ON p.id_product = l.product_id
WHERE NOT EXISTS (SELECT 1 FROM stock_movements m
                   WHERE m.kind = 'opening' AND m.source_type = 'product' AND m.source_id = p.id_product);

UPDATE products SET stock = 0 WHERE stock < 0;

-- Los motivos de uso común, por compañía, como la plantilla de cuentas.
INSERT INTO stock_reasons (company_id, code, name, is_system)
SELECT c.id, r.code, r.name, r.is_system
FROM companies c
JOIN (SELECT 'shrinkage' code, 'Merma' name, 0 is_system
      UNION ALL SELECT 'damage',       'Daño',            0
      UNION ALL SELECT 'expired',      'Vencido',         0
      UNION ALL SELECT 'internal_use', 'Consumo interno', 0
      UNION ALL SELECT 'sample',       'Muestra',         0
      UNION ALL SELECT 'count',        'Toma física',     1) r
WHERE NOT EXISTS (SELECT 1 FROM stock_reasons x WHERE x.company_id = c.id AND x.code = r.code);

-- El mínimo general nace con el 10 que el POS usaba (RN-101). `settings.data`
-- es JSON en TEXT; una compañía sin fila no tiene qué actualizar y la cubre
-- el respaldo del lector.
UPDATE settings
   SET data = JSON_SET(CAST(data AS JSON), '$.inventory', JSON_OBJECT('lots_enabled', FALSE, 'min_stock', 10))
 WHERE JSON_EXTRACT(CAST(data AS JSON), '$.inventory') IS NULL;

-- Las dos cuentas y los cinco mapeos, para las compañías que ya activaron la
-- contabilidad. Lo que ya exista se salta: la plantilla manda solo en lo que
-- falta. (Ninguna migración anterior lo hizo; T-1508 repara igual lo de
-- planilla.)
INSERT INTO accounts (company_id, code, name, kind, is_system, is_active)
SELECT a.company_id, t.code, t.name, t.kind, 1, 1
FROM (SELECT DISTINCT company_id FROM accounts) a
JOIN (SELECT '6.3.01' code, 'Mermas y ajustes de inventario' name, 'expense' kind
      UNION ALL SELECT '4.9.02', 'Sobrantes de inventario', 'income') t
WHERE NOT EXISTS (SELECT 1 FROM accounts x WHERE x.company_id = a.company_id AND x.code = t.code);

INSERT INTO account_mappings (company_id, event, role, account_id)
SELECT a.company_id, m.event, m.role, a.id
FROM (SELECT 'stock_exit'  event, 'shrinkage' role, '6.3.01' code
      UNION ALL SELECT 'stock_exit',  'inventory', '1.2.01'
      UNION ALL SELECT 'stock_count', 'shrinkage', '6.3.01'
      UNION ALL SELECT 'stock_count', 'overage',   '4.9.02'
      UNION ALL SELECT 'stock_count', 'inventory', '1.2.01') m
JOIN accounts a ON a.code = m.code
WHERE NOT EXISTS (SELECT 1 FROM account_mappings x
                   WHERE x.company_id = a.company_id AND x.event = m.event AND x.role = m.role);

DROP PROCEDURE ventasys_add_column;
DROP PROCEDURE ventasys_add_constraint;

-- Comprobación: la ficha y la suma de sus sucursales dicen lo mismo.
SELECT p.id_product, p.stock, COALESCE(SUM(l.quantity), 0) AS en_sucursales
  FROM products p LEFT JOIN stock_levels l ON l.product_id = p.id_product
 GROUP BY p.id_product, p.stock
HAVING p.stock <> COALESCE(SUM(l.quantity), 0);
-- Esperado: ninguna fila.
