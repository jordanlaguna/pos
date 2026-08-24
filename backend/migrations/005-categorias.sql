-- ============================================================================
--  VentaSys · 005 — Categorías de dos niveles (F4)
--
--  Hoy `categories` es una lista plana. Queda como un árbol de dos niveles:
--  «Bebidas → Cervezas», «Yamaha → Llantas». Las categorías que ya existen
--  quedan como raíces sin hijas, así que nada se rompe: un producto que apunta
--  a «Abarrotes» sigue apuntando a «Abarrotes», que ahora es una raíz.
--
--  Corresponde a task.md T-401; plan.md §5; spec.md RF-13 a RF-16, RN-5 a RN-8.
--
--  CORRERLA
--     docker exec -i mysql_db_api sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" posdb' \
--         < backend/migrations/005-categorias.sql
--
--  NO ES IDEMPOTENTE: correrla dos veces falla en el primer ALTER. Falla, no
--  corrompe.
-- ============================================================================

SET NAMES utf8mb4;


-- ----------------------------------------------------------------------------
-- 1. Las columnas del árbol (T-401)
--
--    `parent_id` en nulo es una raíz. La columna admite un tercer nivel que la
--    regla no permite (RN-5, validada en el servicio): la profundidad se
--    limita con código, que se puede cambiar, y no con el esquema, que hay que
--    migrar. Un `CHECK` no alcanza —tendría que consultar otra fila—.
--
--    `sort_order` es el orden que el dueño elige para la grilla de ventas
--    (RF-13). No se ordena por nombre: quien vende pone primero lo que más
--    vende, no lo que empieza con «A».
--
--    `is_active` es lo que permite RN-7: una categoría con productos o con
--    hijas no se borra, se desactiva. Borrarla dejaría productos apuntando a
--    una fila que no existe, y desactivarla los deja donde están.
-- ----------------------------------------------------------------------------

ALTER TABLE categories
    ADD COLUMN parent_id  INT         NULL     AFTER name,
    ADD COLUMN sort_order INT         NOT NULL DEFAULT 0 AFTER parent_id,
    ADD COLUMN is_active  TINYINT(1)  NOT NULL DEFAULT 1 AFTER sort_order;


-- ----------------------------------------------------------------------------
-- 2. Dos hermanas no se pueden llamar igual — y las raíces son hermanas
--
--    El UNIQUE que pide la tarea es (company_id, parent_id, name), y escrito
--    tal cual **no protege el caso más común**: MySQL no considera iguales dos
--    nulos, así que dos raíces «Bebidas» entran las dos sin que el índice diga
--    nada. El mismo hueco que en `products.barcode` es ahí una ventaja —los
--    productos sin código de barras conviven— y acá es un defecto.
--
--    Se cierra con una columna generada: `parent_key` es el padre o 0 si es
--    raíz, y el UNIQUE va sobre ella. STORED y no VIRTUAL porque un índice
--    único sobre una columna virtual obliga a MySQL a recalcularla en cada
--    lectura del índice.
--
--    El nombre lo compara la colación de la tabla, `utf8mb4_0900_ai_ci`, que
--    ignora tildes y mayúsculas: «Lácteos» y «lacteos» chocan, que es lo que
--    conviene en un catálogo escrito a mano por gente distinta.
-- ----------------------------------------------------------------------------

-- El orden de las palabras importa y no es el que uno escribiría: en una columna
-- generada, `NOT NULL` va DESPUÉS de la expresión y del STORED. Escrito como
-- `INT NOT NULL AS (…) STORED`, MySQL responde un 1064 señalando la expresión,
-- que es donde no está el problema.
ALTER TABLE categories
    ADD COLUMN parent_key INT AS (IFNULL(parent_id, 0)) STORED NOT NULL;

ALTER TABLE categories
    DROP INDEX uq_categories_company_name,
    ADD UNIQUE KEY uq_categories_company_parent_name (company_id, parent_key, name);


-- ----------------------------------------------------------------------------
-- 3. Una hija no puede colgar de otra compañía
--
--    La clave foránea lleva la compañía adentro: (parent_id, company_id) contra
--    (id, company_id). Con `parent_id` solo, el esquema aceptaría una
--    subcategoría de la compañía A colgada de una raíz de la compañía B; hoy no
--    puede pasar porque el filtro de `tenancy.py` no deja ni ver esa raíz, pero
--    eso es el cinturón, no el muro.
--
--    InnoDB no comprueba una foránea compuesta cuando alguna de sus columnas es
--    nula, así que las raíces —`parent_id` nulo— pasan sin más.
--
--    Sin ON DELETE: el borrado se queda en RESTRICT, que es justo RN-7 escrito
--    en el esquema. Con CASCADE, borrar «Bebidas» se llevaría «Cervezas» y sus
--    productos quedarían apuntando al vacío.
-- ----------------------------------------------------------------------------

ALTER TABLE categories
    ADD UNIQUE KEY uq_categories_id_company (id, company_id);

ALTER TABLE categories
    ADD CONSTRAINT fk_categories_parent
        FOREIGN KEY (parent_id, company_id) REFERENCES categories (id, company_id);


-- ----------------------------------------------------------------------------
-- 4. Las que ya existen quedan ordenadas
--
--    Nacen todas en `sort_order = 0`, y un orden donde todo empata es el orden
--    que devuelva la base. Se numeran por nombre, que es como se venían
--    mostrando, y desde ahí el dueño las reordena.
--
--    El JOIN va contra una derivada a propósito: MySQL no deja leer en una
--    subconsulta la misma tabla que se está actualizando, pero sí materializar
--    una derivada primero.
-- ----------------------------------------------------------------------------

UPDATE categories c
  JOIN (SELECT id,
               ROW_NUMBER() OVER (PARTITION BY company_id ORDER BY name) AS n
          FROM categories) orden ON orden.id = c.id
   SET c.sort_order = orden.n;


-- ----------------------------------------------------------------------------
-- 5. Verificación
-- ----------------------------------------------------------------------------

-- Esperado: todas raíces (parent_id nulo), todas activas, y `sort_order`
-- numerado de 1 hacia arriba dentro de cada compañía.
SELECT 'categorias' AS control,
       company_id,
       id,
       name,
       parent_id,
       sort_order,
       is_active
  FROM categories
 ORDER BY company_id, sort_order;

-- Esperado: uq_categories_company_parent_name sobre (company_id, parent_key,
-- name), uq_categories_id_company sobre (id, company_id), y ninguna huella de
-- uq_categories_company_name.
SELECT 'indices' AS control, INDEX_NAME, SEQ_IN_INDEX, COLUMN_NAME
  FROM information_schema.STATISTICS
 WHERE TABLE_SCHEMA = DATABASE()
   AND TABLE_NAME = 'categories'
 ORDER BY INDEX_NAME, SEQ_IN_INDEX;

-- Esperado: fk_categories_company (company_id) y fk_categories_parent con sus
-- dos columnas (parent_id, company_id).
SELECT 'foraneas' AS control,
       k.CONSTRAINT_NAME,
       k.ORDINAL_POSITION,
       k.COLUMN_NAME,
       k.REFERENCED_TABLE_NAME,
       k.REFERENCED_COLUMN_NAME
  FROM information_schema.KEY_COLUMN_USAGE k
 WHERE k.TABLE_SCHEMA = DATABASE()
   AND k.TABLE_NAME = 'categories'
   AND k.REFERENCED_TABLE_NAME IS NOT NULL
 ORDER BY k.CONSTRAINT_NAME, k.ORDINAL_POSITION;
