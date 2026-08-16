-- ============================================================================
--  VentaSys — migración de base de datos
--  Aplicar sobre el esquema actual de `backend-python` (MySQL).
--
--  Hacé un respaldo antes:
--     mysqldump -u USUARIO -p NOMBRE_BD > respaldo.sql
--
--  Ejecutar:
--     mysql -u USUARIO -p NOMBRE_BD < migration.sql
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. Roles de usuario
--    La tabla `users` no distinguía administrador de cajero: cualquiera podía
--    todo. Los usuarios existentes quedan como cajeros salvo el primero.
-- ----------------------------------------------------------------------------
ALTER TABLE users
    ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'cajero';

-- El usuario más antiguo pasa a administrador para no quedar sin nadie que
-- pueda gestionar el sistema. La subconsulta anidada evita el error 1093 de
-- MySQL (no se puede leer la misma tabla que se actualiza).
UPDATE users
SET role = 'admin'
WHERE id_user = (SELECT id FROM (SELECT MIN(id_user) AS id FROM users) AS t);

-- ----------------------------------------------------------------------------
-- 2. Fecha y hora en ventas y productos
--    `Column(Date)` guardaba solo el día. Sin la hora es imposible saber si una
--    venta ocurrió antes o después de abrir la caja, así que el arqueo por
--    turno no puede funcionar. DATETIME conserva los datos existentes: las
--    fechas viejas quedan a las 00:00:00.
-- ----------------------------------------------------------------------------
ALTER TABLE sales    MODIFY COLUMN created_at DATETIME NOT NULL;
ALTER TABLE products MODIFY COLUMN created_at DATETIME NOT NULL;

-- ----------------------------------------------------------------------------
-- 3. Ventas sin cliente
--    `client_id` era NOT NULL, y por eso el cliente WinForms mandaba siempre
--    `client_id = 1`. En un punto de venta la mayoría de las compras son de
--    contado y no llevan cliente asociado.
-- ----------------------------------------------------------------------------
ALTER TABLE sales MODIFY COLUMN client_id INT NULL;

-- ----------------------------------------------------------------------------
-- 4. Turnos de caja
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cash_sessions (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    user_id        INT            NOT NULL,
    opened_at      DATETIME       NOT NULL,
    closed_at      DATETIME       NULL,
    opening_amount DECIMAL(10, 2) NOT NULL DEFAULT 0.00,
    -- Efectivo contado por el cajero al cerrar. NULL mientras siga abierta.
    closing_amount DECIMAL(10, 2) NULL,
    status         VARCHAR(20)    NOT NULL DEFAULT 'abierta',
    notes          VARCHAR(255)   NULL,
    CONSTRAINT fk_cash_sessions_user FOREIGN KEY (user_id) REFERENCES users (id_user),
    INDEX idx_cash_sessions_user_status (user_id, status),
    INDEX idx_cash_sessions_opened (opened_at)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

-- Entradas y salidas de efectivo que no son ventas (cambio del banco, pagos a
-- proveedores, retiros).
CREATE TABLE IF NOT EXISTS cash_movements (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    session_id INT            NOT NULL,
    type       VARCHAR(10)    NOT NULL,
    amount     DECIMAL(10, 2) NOT NULL,
    reason     VARCHAR(255)   NOT NULL,
    created_at DATETIME       NOT NULL,
    CONSTRAINT fk_cash_movements_session
        FOREIGN KEY (session_id) REFERENCES cash_sessions (id) ON DELETE CASCADE,
    INDEX idx_cash_movements_session (session_id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

-- ----------------------------------------------------------------------------
-- 5. Devoluciones
--    El sistema solo sabía descontar stock. Con esto una venta puede revertirse
--    total o parcialmente y las unidades regresan al inventario.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS returns (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    sale_id    INT            NOT NULL,
    user_id    INT            NOT NULL,
    created_at DATETIME       NOT NULL,
    reason     VARCHAR(255)   NOT NULL,
    total      DECIMAL(10, 2) NOT NULL,
    CONSTRAINT fk_returns_sale FOREIGN KEY (sale_id) REFERENCES sales (id),
    CONSTRAINT fk_returns_user FOREIGN KEY (user_id) REFERENCES users (id_user),
    INDEX idx_returns_sale (sale_id),
    INDEX idx_returns_created (created_at)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

CREATE TABLE IF NOT EXISTS return_details (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    return_id  INT            NOT NULL,
    product_id INT            NOT NULL,
    quantity   INT            NOT NULL,
    unit_price DECIMAL(10, 2) NOT NULL,
    subtotal   DECIMAL(10, 2) NOT NULL,
    CONSTRAINT fk_return_details_return
        FOREIGN KEY (return_id) REFERENCES returns (id) ON DELETE CASCADE,
    CONSTRAINT fk_return_details_product
        FOREIGN KEY (product_id) REFERENCES products (id_product),
    INDEX idx_return_details_return (return_id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

-- ----------------------------------------------------------------------------
-- 6. Índices que faltaban
--    Los reportes agrupan por fecha y el escáner busca por código de barras.
-- ----------------------------------------------------------------------------
CREATE INDEX idx_sales_created      ON sales (created_at);
CREATE INDEX idx_sales_user         ON sales (user_id);
CREATE INDEX idx_sale_details_sale  ON sale_details (sale_id);
CREATE INDEX idx_products_barcode   ON products (barcode);

-- ----------------------------------------------------------------------------
-- 7. Entradas de mercadería
--    Antes solo se podía subir el stock editando cada producto a mano, sin
--    dejar rastro de quién lo hizo ni de dónde vino la mercadería.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS stock_entries (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    -- Factura del proveedor o consecutivo del XML de Hacienda.
    document_number VARCHAR(100)   NULL,
    supplier        VARCHAR(150)   NULL,
    source          VARCHAR(20)    NOT NULL DEFAULT 'manual',
    user_id         INT            NOT NULL,
    created_at      DATETIME       NOT NULL,
    notes           VARCHAR(255)   NULL,
    status          VARCHAR(20)    NOT NULL DEFAULT 'aplicada',
    total_cost      DECIMAL(12, 2) NOT NULL DEFAULT 0.00,
    CONSTRAINT fk_stock_entries_user FOREIGN KEY (user_id) REFERENCES users (id_user),
    INDEX idx_stock_entries_created (created_at),
    INDEX idx_stock_entries_document (document_number)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

CREATE TABLE IF NOT EXISTS stock_entry_details (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    entry_id   INT            NOT NULL,
    product_id INT            NOT NULL,
    quantity   INT            NOT NULL,
    unit_cost  DECIMAL(10, 2) NOT NULL DEFAULT 0.00,
    subtotal   DECIMAL(12, 2) NOT NULL DEFAULT 0.00,
    CONSTRAINT fk_stock_entry_details_entry
        FOREIGN KEY (entry_id) REFERENCES stock_entries (id) ON DELETE CASCADE,
    CONSTRAINT fk_stock_entry_details_product
        FOREIGN KEY (product_id) REFERENCES products (id_product),
    INDEX idx_stock_entry_details_entry (entry_id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

-- ----------------------------------------------------------------------------
-- 8. Configuración del negocio
--    Una sola fila. Guarda moneda, impuesto, datos del emisor, plantilla del
--    documento y colores. Antes todo eso estaba escrito en el código: el IVA al
--    13 %, el colón, y el nombre "VentaSys" impreso en cada tiquete.
--
--    `data` es JSON en texto en vez de una columna por opción, para que agregar
--    una casilla no exija otra migración. El logo va aparte porque es lo único
--    voluminoso y no tiene por qué viajar en cada lectura.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS settings (
    id         INT PRIMARY KEY,
    data       TEXT        NOT NULL,
    logo_mime  VARCHAR(60) NULL,
    -- LONGTEXT y no TEXT: un PNG de 250 KB en base64 ocupa ~340 KB y un TEXT
    -- (64 KB) lo truncaría sin avisar.
    logo_data  LONGTEXT    NULL,
    updated_at DATETIME    NULL,
    updated_by INT         NULL
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

-- La fila nace vacía: el POS aplica sus valores por omisión sobre `{}`, así que
-- el sistema funciona sin que nadie entre a Configuración.
INSERT INTO settings (id, data) VALUES (1, '{}')
ON DUPLICATE KEY UPDATE id = id;
