-- ============================================================================
--  VentaSys · 022 — Cada sección es un módulo y los planes son paquetes (QA-01)
--
--  Hasta acá, `plans` decía tres módulos —compras, contabilidad y planilla— y el
--  resto del POS lo tenía todo el mundo. El usuario quiere vender paquetes: un
--  restaurante no necesita caja ni inventario, y un comercio que compra a
--  crédito necesita compras. Así que cada sección del POS pasa a ser una
--  bandera del plan (spec RN-49 a RN-51, `domain/modules.py`). Configuración no:
--  sin ella no hay negocio.
--
--  NADIE PIERDE NADA AL ACTUALIZAR. Las secciones que el POS tuvo siempre
--  (`BASE`: ventas, caja, facturas, devoluciones, reportes, inventario,
--  clientes y usuarios) nacen ENCENDIDAS en los planes que ya existen, y
--  `suppliers` copia a `purchases`, porque los proveedores colgaban de compras.
--  Después el valor por omisión pasa a 0, que es lo que declara el modelo: un
--  plan del que no se dice nada no incluye nada.
--
--  LOS CUATRO PAQUETES (decididos con el usuario el 2026-10-03) se dan de alta
--  si no hay un plan con ese nombre. Uno que ya existía —«Comercio» en una base
--  vieja— conserva lo suyo, y se ajusta desde Planes. **El precio y los límites
--  van en 0 y 1/3/10 a propósito: son una decisión comercial que no tomó
--  nadie todavía**, y se escriben en la base como los de cualquier plan.
--
--  CORRERLA
--     docker exec -i mysql_db_api sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" posdb' --         < backend/migrations/022-paquetes-de-modulos.sql
--
--  NO ES IDEMPOTENTE: `ADD COLUMN` sobre una columna que ya está falla.
-- ============================================================================

SET NAMES utf8mb4;

-- 1. Las nueve banderas nuevas. Las de la base, encendidas para lo que ya existe.
ALTER TABLE plans
    ADD COLUMN sales      TINYINT(1) NOT NULL DEFAULT 1,
    ADD COLUMN cash       TINYINT(1) NOT NULL DEFAULT 1,
    ADD COLUMN invoices   TINYINT(1) NOT NULL DEFAULT 1,
    ADD COLUMN returns    TINYINT(1) NOT NULL DEFAULT 1,
    ADD COLUMN reports    TINYINT(1) NOT NULL DEFAULT 1,
    ADD COLUMN inventory  TINYINT(1) NOT NULL DEFAULT 1,
    ADD COLUMN suppliers  TINYINT(1) NOT NULL DEFAULT 0,
    ADD COLUMN clients    TINYINT(1) NOT NULL DEFAULT 1,
    ADD COLUMN users      TINYINT(1) NOT NULL DEFAULT 1;

-- 2. Los proveedores eran parte de compras.
UPDATE plans SET suppliers = purchases;

-- 3. De acá en adelante, un plan nuevo no incluye nada que no se diga.
ALTER TABLE plans
    ALTER COLUMN sales      SET DEFAULT 0,
    ALTER COLUMN cash       SET DEFAULT 0,
    ALTER COLUMN invoices   SET DEFAULT 0,
    ALTER COLUMN returns    SET DEFAULT 0,
    ALTER COLUMN reports    SET DEFAULT 0,
    ALTER COLUMN inventory  SET DEFAULT 0,
    ALTER COLUMN clients    SET DEFAULT 0,
    ALTER COLUMN users      SET DEFAULT 0;

-- 4. Los cuatro paquetes.
INSERT INTO plans (nombre, precio_mensual, max_sucursales, max_terminales, max_usuarios, sales, cash, invoices, returns, reports, inventory, purchases, suppliers, accounting, payroll, clients, users)
SELECT 'Restaurante', 0, 1, 3, 10, 1, 0, 1, 0, 0, 0, 0, 0, 0, 0, 1, 1
FROM DUAL WHERE NOT EXISTS (SELECT 1 FROM plans WHERE nombre = 'Restaurante');

INSERT INTO plans (nombre, precio_mensual, max_sucursales, max_terminales, max_usuarios, sales, cash, invoices, returns, reports, inventory, purchases, suppliers, accounting, payroll, clients, users)
SELECT 'Comercio', 0, 1, 3, 10, 1, 1, 1, 1, 0, 1, 0, 1, 0, 0, 1, 1
FROM DUAL WHERE NOT EXISTS (SELECT 1 FROM plans WHERE nombre = 'Comercio');

INSERT INTO plans (nombre, precio_mensual, max_sucursales, max_terminales, max_usuarios, sales, cash, invoices, returns, reports, inventory, purchases, suppliers, accounting, payroll, clients, users)
SELECT 'Comercio con compras', 0, 1, 3, 10, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 1, 1
FROM DUAL WHERE NOT EXISTS (SELECT 1 FROM plans WHERE nombre = 'Comercio con compras');

INSERT INTO plans (nombre, precio_mensual, max_sucursales, max_terminales, max_usuarios, sales, cash, invoices, returns, reports, inventory, purchases, suppliers, accounting, payroll, clients, users)
SELECT 'Completo', 0, 1, 3, 10, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1
FROM DUAL WHERE NOT EXISTS (SELECT 1 FROM plans WHERE nombre = 'Completo');

-- 5. Comprobación: las doce banderas de cada plan.
SELECT nombre, sales, cash, invoices, returns, reports, inventory, purchases, suppliers, accounting, payroll, clients, users
FROM plans ORDER BY id;
