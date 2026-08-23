-- ============================================================================
--  VentaSys · 004 — Soporte y suscripción (F3)
--
--  Agrega lo único que el panel de soporte necesita en el esquema: una marca
--  que diga quién es soporte. Todo lo demás —compañías, planes, estados,
--  bitácora— ya existe desde la 002.
--
--  Corresponde a task.md T-301 a T-310; plan.md §4.
--
--  CORRERLA
--     docker exec -i mysql_db_api sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" posdb' \
--         < backend/migrations/004-soporte.sql
--
--  NO ES IDEMPOTENTE: correrla dos veces falla en el primer ALTER. Falla, no
--  corrompe.
-- ============================================================================

SET NAMES utf8mb4;


-- ----------------------------------------------------------------------------
-- 1. Quién es soporte (T-301)
--
--    El plan decía «soporte es una persona sin ninguna membresía», y como
--    definición no sirve: quien rechaza la única invitación que tenía también
--    se queda sin ninguna, y se convertiría en administrador de la plataforma
--    por descarte. La ausencia de algo no puede ser un permiso.
--
--    Así que la marca es positiva y vive en `users`, al lado del correo y la
--    contraseña, porque es una propiedad de la identidad y no de una
--    membresía: soporte no pertenece a ninguna compañía (RN-4).
--
--    Nace en 0 para todo el mundo. La primera cuenta de soporte se crea con
--    `bootstrap.py --soporte`, que es el mismo camino por el que se creó la
--    primera compañía y por la misma razón: no hay API que pueda otorgar un
--    permiso que todavía nadie tiene.
-- ----------------------------------------------------------------------------

ALTER TABLE users ADD COLUMN is_support TINYINT(1) NOT NULL DEFAULT 0;


-- ----------------------------------------------------------------------------
-- 2. La bitácora se consulta por fecha (T-307)
--
--    La 002 le dejó `idx_audit_company (company_id, creado_el)`, que sirve para
--    «qué se hizo en esta compañía». El panel abre con la otra pregunta —«qué
--    se hizo, en cualquier compañía, en los últimos días»— y esa ordena por
--    fecha sin filtrar por compañía: sin índice es un recorrido de toda la
--    tabla, que crece con cada login del sistema entero.
-- ----------------------------------------------------------------------------

ALTER TABLE audit_log ADD INDEX idx_audit_creado (creado_el);


-- ----------------------------------------------------------------------------
-- 3. Verificación
-- ----------------------------------------------------------------------------

-- Esperado: la columna existe, en 0 para todos.
SELECT 'soporte' AS control,
       COUNT(*)          AS usuarios,
       SUM(is_support)   AS de_soporte
  FROM users;

-- Esperado: los dos índices de la bitácora.
SELECT 'indices' AS control, INDEX_NAME, SEQ_IN_INDEX, COLUMN_NAME
  FROM information_schema.STATISTICS
 WHERE TABLE_SCHEMA = DATABASE()
   AND TABLE_NAME = 'audit_log'
 ORDER BY INDEX_NAME, SEQ_IN_INDEX;
