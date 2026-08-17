-- ============================================================================
--  VentaSys · 003 — La membresía se acepta, no se impone (T-229)
--
--  Hasta ahora, un administrador podía agregar a su compañía cualquier correo
--  que existiera en el sistema, y esa compañía le aparecía a la otra persona en
--  la lista al entrar. No podía hacerle daño —tenía que elegirla para que
--  pasara algo— pero tampoco había pedido permiso.
--
--  Con base compartida eso importa más de lo que parece: la lista de compañías
--  de alguien es información sobre con quién trabaja, y llenársela de invitados
--  ajenos es a la vez ruido y una superficie de engaño («entrá a esta compañía
--  que se llama igual que la suya»).
--
--  Corresponde a task.md T-229; plan.md §3.8.
--
--  CORRERLA
--     docker exec -i mysql_db_api sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" posdb' \
--         < backend/migrations/003-invitaciones.sql
-- ============================================================================

SET NAMES utf8mb4;


-- ----------------------------------------------------------------------------
-- 1. Cuándo se aceptó
--
--    NULL significa «invitada, sin aceptar todavía». Es distinto de una fecha
--    antigua: la ausencia de fecha es la ausencia de consentimiento, y por eso
--    la columna es nullable en vez de tener un valor por omisión.
--
--    Los tres estados de una fila de `user_companies`:
--
--      activa = 1, aceptada_el NULL   → invitación pendiente
--      activa = 1, aceptada_el fecha  → membresía en uso
--      activa = 0                     → revocada por el administrador,
--                                        o rechazada por la persona
-- ----------------------------------------------------------------------------

ALTER TABLE user_companies ADD COLUMN aceptada_el DATETIME NULL;


-- ----------------------------------------------------------------------------
-- 2. Lo que ya existe queda aceptado
--
--    Las membresías actuales no se inventaron a espaldas de nadie: salieron de
--    los usuarios que ya trabajaban en la compañía 1 (migración 002) o de un
--    `bootstrap.py` que corrió el dueño. Dejarlas pendientes obligaría a todo el
--    mundo a aceptar una invitación a su propio negocio.
-- ----------------------------------------------------------------------------

UPDATE user_companies SET aceptada_el = creada_el WHERE aceptada_el IS NULL;


-- ----------------------------------------------------------------------------
-- 3. Verificación
-- ----------------------------------------------------------------------------

-- Esperado: 0 pendientes, y tantas aceptadas como membresías hay.
SELECT 'membresias' AS control,
       COUNT(*)                                    AS total,
       SUM(aceptada_el IS NULL AND activa = 1)     AS pendientes,
       SUM(aceptada_el IS NOT NULL)                AS aceptadas
  FROM user_companies;
