-- ============================================================================
--  VentaSys · 009 — Compras y cuentas por pagar (F10, T-1005)
--
--  Hoy una entrada de mercadería sabe qué entró, cuánto costó y quién la cargó,
--  y hasta guarda el nombre del proveedor y el número de su factura como texto.
--  Lo que no sabe es lo que el negocio necesita a fin de mes: **a quién le debe,
--  cuánto y desde cuándo**, y cuánto IVA pagó en esas compras. Sin eso no hay
--  crédito fiscal, y sin crédito fiscal el D-104 sale mal.
--
--  LA COMPRA ES LA ENTRADA, NO UNA TABLA NUEVA (plan.md §12.1, RN-52)
--
--  `stock_entries` se extiende en vez de crear `purchases`, por tres razones:
--
--   1. El lector de XML de Hacienda ya produce una entrada a partir de la
--      factura del proveedor, y el invariante «entrada XML 79 800» la fija. Con
--      una tabla nueva habría que mantener dos caminos que hacen lo mismo.
--   2. La anulación ya existe y recorre las líneas para revertir el stock. Una
--      compra anulada revierte lo mismo más la cuenta por pagar.
--   3. Dos tablas son dos verdades: «una entrada con compra» y «una compra sin
--      entrada» son estados que no significan nada y que alguien tendría que
--      impedir.
--
--  Una entrada con `supplier_id` nulo sigue siendo una entrada —las que ya
--  existen, las de ajuste— y no genera cuenta por pagar ni crédito fiscal.
--
--  CORRERLA
--     docker exec -i mysql_db_api sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" posdb' \
--         < backend/migrations/009-compras.sql
--
--  NO ES IDEMPOTENTE: `ADD COLUMN` sobre una columna que ya está falla.
--
--  NO TOCA NINGUNA FILA EXISTENTE. Las entradas que ya hay quedan con
--  `supplier_id` nulo, `payment_terms` en 'cash' y subtotal e impuesto en cero,
--  que es exactamente lo que son: entradas, no compras. `total_cost` conserva su
--  valor y su significado.
-- ============================================================================

SET NAMES utf8mb4;


-- ----------------------------------------------------------------------------
-- 1. Proveedores
--
--    `identification` admite NULL —un proveedor informal no tiene cédula— y el
--    UNIQUE no choca entre nulos, que es justo lo que hace falta: dos
--    proveedores sin identificación conviven, y la misma identificación es el
--    mismo proveedor. Es lo que permite reconocerlo desde el XML sin preguntar.
-- ----------------------------------------------------------------------------

CREATE TABLE suppliers (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    company_id          INT          NOT NULL,
    identification_type CHAR(2)      NULL,       -- 01/02/03/04, lista de Hacienda
    identification      VARCHAR(30)  NULL,
    name                VARCHAR(160) NOT NULL,
    email               VARCHAR(160) NULL,
    phone               VARCHAR(30)  NULL,
    payment_terms_days  INT          NOT NULL DEFAULT 0,   -- 0 = contado
    is_active           TINYINT(1)   NOT NULL DEFAULT 1,
    created_at          DATETIME     NOT NULL,
    UNIQUE KEY uq_suppliers_identification (company_id, identification),
    INDEX idx_suppliers_name (company_id, name),
    CONSTRAINT fk_suppliers_company FOREIGN KEY (company_id) REFERENCES companies (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;


-- ----------------------------------------------------------------------------
-- 2. La entrada se vuelve compra
--
--    `total_cost` ya existe y pasa a valer subtotal + impuesto. El nombre se
--    queda: lo leen el lector de XML, la anulación y una prueba de
--    caracterización, y renombrarlo no compra nada.
-- ----------------------------------------------------------------------------

ALTER TABLE stock_entries
    ADD COLUMN supplier_id   INT           NULL,
    ADD COLUMN document_key  CHAR(50)      NULL,   -- clave de Hacienda, si hay XML
    ADD COLUMN document_date DATE          NULL,
    ADD COLUMN payment_terms VARCHAR(10)   NOT NULL DEFAULT 'cash',   -- 'cash'|'credit'
    ADD COLUMN due_date      DATE          NULL,
    ADD COLUMN subtotal      DECIMAL(12,2) NOT NULL DEFAULT 0,
    ADD COLUMN tax           DECIMAL(12,2) NOT NULL DEFAULT 0,
    ADD INDEX idx_stock_entries_supplier (company_id, supplier_id, status),
    ADD INDEX idx_stock_entries_due (company_id, due_date),
    ADD CONSTRAINT fk_stock_entries_supplier
        FOREIGN KEY (supplier_id) REFERENCES suppliers (id);


-- ----------------------------------------------------------------------------
-- 3. El impuesto por línea: el crédito fiscal (RN-53)
--
--    Es el que dice el documento del proveedor, no el que tendría el producto.
--    El crédito fiscal es lo que se pagó, no lo que se habría cobrado.
-- ----------------------------------------------------------------------------

ALTER TABLE stock_entry_details
    ADD COLUMN tax_rate   DECIMAL(5,2)  NOT NULL DEFAULT 0,
    ADD COLUMN tax_amount DECIMAL(12,2) NOT NULL DEFAULT 0;


-- ----------------------------------------------------------------------------
-- 4. El costo del producto (RN-54)
--
--    El producto no sabía cuánto costó: tenía precio de venta y nada más.
--    Promedio ponderado móvil, a dos decimales como toda la plata del sistema.
--    En cero para lo que ya existe, que es lo cierto: no se sabe.
-- ----------------------------------------------------------------------------

ALTER TABLE products
    ADD COLUMN cost DECIMAL(12,2) NOT NULL DEFAULT 0;


-- ----------------------------------------------------------------------------
-- 5. Abonos a proveedor
--
--    El abono es a **una compra** y no «a cuenta» (RN-55). Un abono a cuenta que
--    se reparte entre facturas necesita una regla de reparto, y la regla de
--    reparto es lo primero que un proveedor discute. Atado al documento, el
--    saldo de cada factura es un hecho y el del proveedor es una suma.
--
--    `cash_movement_id` enlaza con la salida de caja cuando el pago fue en
--    efectivo (RN-56): sin ese enlace, el asiento de F11 contaría dos veces la
--    misma plata.
-- ----------------------------------------------------------------------------

CREATE TABLE supplier_payments (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    company_id       INT           NOT NULL,
    supplier_id      INT           NOT NULL,
    entry_id         INT           NOT NULL,
    amount           DECIMAL(12,2) NOT NULL,
    method           VARCHAR(20)   NOT NULL,     -- 'cash' | 'transfer' | 'other'
    reference        VARCHAR(100)  NULL,
    cash_movement_id INT           NULL,
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


-- ----------------------------------------------------------------------------
-- 6. Comprobación
--
--    Las diez columnas agregadas: siete en `stock_entries`, dos en
--    `stock_entry_details` y una en `products`. Tiene que devolver 10 filas.
--    Las dos tablas nuevas no salen acá; si `CREATE TABLE` falla, la migración
--    se detiene antes de llegar a esta consulta.
-- ----------------------------------------------------------------------------

SELECT TABLE_NAME, COLUMN_NAME
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND (
      (TABLE_NAME = 'stock_entries'
       AND COLUMN_NAME IN ('supplier_id', 'document_key', 'document_date',
                           'payment_terms', 'due_date', 'subtotal', 'tax'))
   OR (TABLE_NAME = 'stock_entry_details' AND COLUMN_NAME IN ('tax_rate', 'tax_amount'))
   OR (TABLE_NAME = 'products' AND COLUMN_NAME = 'cost')
  )
ORDER BY TABLE_NAME, COLUMN_NAME;
