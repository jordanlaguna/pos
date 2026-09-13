-- ============================================================================
--  VentaSys · 011 — Preparación de factura electrónica (F6, T-601)
--
--  Lo que hace falta ANTES de poder emitir: dónde van las credenciales de los
--  dos ambientes, desde qué número sigue la numeración de un negocio que ya
--  facturaba, y el tipo de identificación —del emisor y del receptor— que el
--  XML exige y que hoy no está en ninguna parte.
--
--  SON DOS SECRETOS Y LOS DOS SON POR AMBIENTE (plan §7.1, RN-33)
--
--  Firmar y transmitir son operaciones distintas con credenciales distintas, y
--  Hacienda las emite por separado para pruebas y para producción. Por eso la
--  llave primaria es `(company_id, environment)` y no `company_id`: con lo
--  segundo, «pasar a producción» significaba borrar lo de pruebas y quedarse
--  sin poder volver, y un cliente en integración tiene los dos a la vez.
--
--  LA LLAVE PRIVADA NO ESTÁ ACÁ (decidido el 2026-09-13)
--
--  Se importa a Vault al subir el `.p12` y no vuelve a salir. Por eso esta
--  tabla NO tiene `p12_encrypted`, NO tiene `pin_encrypted` y NO tiene
--  `key_version`: el PIN solo sirve para abrir el `.p12` y eso pasa una sola
--  vez, así que después no hay nada que volver a abrir ni nada que guardar.
--  De firma queda solo `certificate_pem`, que es la parte PÚBLICA y viaja sin
--  cifrar dentro de cada XML firmado.
--
--  El único secreto que sigue en la base es la contraseña de ATV, y es porque
--  hay que poder reenviarla al IdP en cada token: no es un digest que se firme
--  sino un valor que se guarda y se lee. Va cifrada con AES-256-GCM y
--  `(company_id, environment)` como dato asociado (T-602a), así que una fila
--  copiada a otra compañía —o al otro ambiente— no descifra.
--
--  LOS NOMBRES VAN EN INGLÉS
--
--  plan §3.9: la excepción de las columnas en español es de las que ya existen,
--  «no una licencia para las nuevas». Es la tercera vez que el proyecto tropieza
--  con lo mismo —T-401 en F4, la 006 en F5— y acá el diseño lo inducía.
--
--  CORRERLA
--     docker exec -i mysql_db_api sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" posdb' \
--         < backend/migrations/011-factura-electronica.sql
--
--  NO ES IDEMPOTENTE: `ADD COLUMN` sobre una columna que ya está falla.
--
--  TOCA FILAS EXISTENTES EN UN SOLO SITIO, y a propósito: el tipo de
--  identificación de los clientes que ya están se deduce de la longitud de su
--  cédula. Ver el punto 4.
-- ============================================================================

SET NAMES utf8mb4;


-- ----------------------------------------------------------------------------
-- 1. Credenciales de Hacienda, por ambiente
--
--    Las marcas de tiempo son DOS PARES porque son dos secretos con vidas
--    distintas: rotar la contraseña de ATV en marzo no puede hacer que la
--    pantalla diga que el certificado se subió en marzo.
--
--    `atv_user` NO es secreto y se muestra: es un identificador, y sin verlo
--    nadie puede comprobar que escribió el que era (RN-16).
--
--    `expires_at` es DATETIME y no DATE: el `notAfter` del certificado tiene
--    hora, y un certificado que vence a las 10:00 no sirve a las 11:00.
-- ----------------------------------------------------------------------------

CREATE TABLE fe_credentials (
    company_id  INT          NOT NULL,
    environment VARCHAR(12)  NOT NULL,     -- 'sandbox' | 'production'

    -- Firma ------------------------------------------------------------------
    -- TEXT y no LONGTEXT: un certificado PEM son unos 2 KB y en 64 KB caben de
    -- sobra. LONGTEXT solo existe en MySQL, y el proyecto ya decidió en la 010
    -- que un tipo propietario no se paga por unos bytes.
    certificate_pem  TEXT         NULL,    -- parte pública, sin cifrar
    key_custody      VARCHAR(12)  NULL,    -- 'vault'; NULL = sin certificado
    certificate_name VARCHAR(160) NULL,
    expires_at       DATETIME     NULL,
    cert_uploaded_at DATETIME     NULL,
    cert_uploaded_by INT          NULL,

    -- Transmisión ------------------------------------------------------------
    atv_user               VARCHAR(160)   NULL,
    -- El AES-GCM en base64 y no en VARBINARY: guardarlo como texto deja que
    -- el modelo y la migración digan lo mismo sin un tipo de MySQL, que es lo
    -- que esta prueba (`test_esquema.py`) exige desde T-915. Nonce + cifrado +
    -- etiqueta de una contraseña larga no pasa de 200 caracteres.
    atv_password_encrypted VARCHAR(512)   NULL,
    atv_updated_at         DATETIME       NULL,
    atv_updated_by         INT            NULL,
    atv_verified_at        DATETIME       NULL,   -- última vez que el IdP dio token

    PRIMARY KEY (company_id, environment),
    CONSTRAINT fk_fe_credentials_company
        FOREIGN KEY (company_id) REFERENCES companies (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;


-- ----------------------------------------------------------------------------
-- 2. El contador del consecutivo
--
--    Cinco dimensiones y no menos (plan §7.2). El consecutivo son 20 dígitos
--    —sucursal (3) + terminal (5) + tipo (2) + secuencia (10)— y la secuencia
--    es DENTRO DEL TIPO.
--
--    Con un contador por terminal, la serie nace con huecos: se emite un
--    tiquete, luego una factura, luego otro tiquete, y los tiquetes van 1, 3, 5
--    mientras las facturas van 2, 4. Las dos series quedan con saltos, que es
--    exactamente lo que Hacienda rechaza («consecutivo fuera de orden»).
--
--    El ambiente entra en la llave porque pruebas y producción se numeran
--    aparte: son dos series, no una.
--
--    `last_number` es BIGINT y no INT: son diez dígitos, y 9 999 999 999 no
--    cabe en un INT con signo. El techo se alcanzaría de verdad solo en un
--    negocio enorme, pero el desbordamiento silencioso de MySQL no avisa.
--
--    Nace vacío. La fila la crea T-616 cuando un negocio declara desde dónde
--    sigue, o la primera emisión de esa combinación.
-- ----------------------------------------------------------------------------

CREATE TABLE fe_sequences (
    company_id    INT         NOT NULL,
    branch_id     INT         NOT NULL,
    terminal_id   INT         NOT NULL,
    document_type CHAR(2)     NOT NULL,     -- 01 factura, 02 ND, 03 NC, 04 tiquete…
    environment   VARCHAR(12) NOT NULL,
    last_number   BIGINT      NOT NULL DEFAULT 0,
    updated_at    DATETIME    NULL,
    updated_by    INT         NULL,

    PRIMARY KEY (company_id, branch_id, terminal_id, document_type, environment),
    CONSTRAINT fk_fe_sequences_branch
        FOREIGN KEY (branch_id) REFERENCES branches (id),
    CONSTRAINT fk_fe_sequences_terminal
        FOREIGN KEY (terminal_id) REFERENCES terminals (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;


-- ----------------------------------------------------------------------------
-- 3. El tipo de identificación del EMISOR (T-621, RN-45)
--
--    Manda `companies` y no la configuración del negocio. El argumento no es de
--    orden sino de consecuencia: el `.p12` se emite A ESA identificación y el
--    usuario de ATV la lleva dentro de su nombre. Un campo que el negocio pueda
--    editar deja que discrepe de su propio certificado, y ahí no se rechaza un
--    comprobante: se rechazan todos.
--
--    Queda al lado de `identificacion`, en español. Es la mezcla que T-916
--    describe y que sigue sin resolverse; escribirla acá no la decide, la hace
--    visible.
-- ----------------------------------------------------------------------------

ALTER TABLE companies
    ADD COLUMN identification_type VARCHAR(2) NULL;   -- '01'|'02'|'03'|'04'


-- ----------------------------------------------------------------------------
-- 4. El tipo de identificación del RECEPTOR (T-617)
--
--    Está en spec §5.4 desde el principio y nunca tuvo tarea. El XML lo exige
--    para el receptor y hoy `clients` tiene la identificación pero no el tipo.
--
--    A los que ya están se les deduce por la longitud de la cédula, que es lo
--    único que se puede saber sin preguntarle a nadie:
--
--        9 dígitos        → 01 física
--        10 dígitos       → 02 jurídica
--        11 o 12 dígitos  → 03 DIMEX
--        cualquier otra   → NULL, que es «no se sabe» y hay que preguntarlo
--
--    El 04 (NITE) también son 10 dígitos y no hay forma de distinguirlo del 02
--    mirando el número. Se elige jurídica porque es órdenes de magnitud más
--    común; quien tenga un NITE lo corrige una vez. NULL sería más honesto pero
--    dejaría a todos los clientes de empresa sin tipo el día de facturar.
--
--    Se limpian los separadores antes de contar: la columna es VARCHAR(100) y
--    hay cédulas guardadas como «1-0234-0567».
-- ----------------------------------------------------------------------------

ALTER TABLE clients
    ADD COLUMN identification_type VARCHAR(2) NULL;

UPDATE clients
SET identification_type = CASE CHAR_LENGTH(REGEXP_REPLACE(identification, '[^0-9]', ''))
        WHEN 9  THEN '01'
        WHEN 10 THEN '02'
        WHEN 11 THEN '03'
        WHEN 12 THEN '03'
        ELSE NULL
    END
WHERE identification IS NOT NULL;


-- ----------------------------------------------------------------------------
-- 5. Comprobación
--
--    Las dos tablas nuevas y las dos columnas. Tiene que devolver 4 filas.
-- ----------------------------------------------------------------------------

SELECT 'tabla' AS que, TABLE_NAME AS nombre
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN ('fe_credentials', 'fe_sequences')
UNION ALL
SELECT 'columna', CONCAT(TABLE_NAME, '.', COLUMN_NAME)
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN ('companies', 'clients')
  AND COLUMN_NAME = 'identification_type'
ORDER BY que, nombre;
