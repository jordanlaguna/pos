# Costa Rica — Factura Electrónica v4.4

**Versión investigada:** 4.4 | **Fecha:** 2026-04-17 | **Autoridad:** Dirección General de Tributación (Ministerio de Hacienda CR)

## Artefactos locales

- [esquemas/](esquemas/) — 9 XSDs oficiales de Hacienda v4.4 (FE, TE, NC, ND, FEC, FEE, REP, MR, MensajeHacienda) + `xmldsig-core-schema.xsd` del W3C. Listos para validación estructural.
- [normativa/](normativa/) — documentos regulatorios oficiales de Hacienda. Actualmente incluye `ANEXOS_Y_ESTRUCTURAS_V4.4.pdf` (Dirección General de Tributación, noviembre 2024) — bitácora oficial de los 146 cambios 4.3→4.4, estructura del XML, Anexo 2 (firma XAdES-EPES) y Anexo 3 (API REST).

---

## 1. Marco regulatorio y fechas clave

La versión 4.4 de los comprobantes electrónicos fue introducida por la **Resolución General MH-DGT-RES-0027-2024** ("Disposiciones Técnicas de los Comprobantes Electrónicos para Efectos Tributarios"), emitida por la Dirección General de Tributación del Ministerio de Hacienda y publicada en *La Gaceta* el 19 de noviembre de 2024.

La resolución introdujo aproximadamente 146 ajustes al esquema XML respecto a la versión 4.3, incluidos cambios estructurales (nuevos nodos, supresión de otros), un nuevo tipo de comprobante (REP — Recibo Electrónico de Pago), actualización del catálogo CABYS y nuevos códigos de medios de pago.

### Calendario oficial

| Fecha | Evento |
|-------|--------|
| 1 de diciembre de 2024 | Publicación de la resolución técnica |
| 1 de abril de 2025 | Inicio de período de **uso voluntario / transición** — coexistencia de 4.3 y 4.4 |
| 1 de septiembre de 2025 | **Uso obligatorio de 4.4** — desactivación de 4.3 |

Tras el 1 de septiembre de 2025, la versión 4.3 dejó de ser aceptada por el sistema de recepción de Hacienda. Durante el período de transición (abril–septiembre 2025) ambas versiones podían emitirse.

**Autoridad tributaria:** Dirección General de Tributación (DGT), Ministerio de Hacienda de Costa Rica.

**Norma conexa vigente:** Reglamento de la Ley del Impuesto sobre el Valor Agregado, Ley N° 9635 (Fortalecimiento de las Finanzas Públicas), Resoluciones DGT sobre emisores, receptores y confirmación de comprobantes.

## 2. Tipos de documento electrónico en 4.4

La versión 4.4 mantiene los tipos heredados de 4.3 e **incorpora un nuevo tipo: REP (Recibo Electrónico de Pago)**. Los códigos y nombres de los tipos en circulación:

| Código | Nombre | Propósito |
|--------|--------|-----------|
| FE | Factura Electrónica | Documento primario de venta de bienes o servicios |
| ND | Nota de Débito Electrónica | Aumenta el monto de un comprobante previo |
| NC | Nota de Crédito Electrónica | Reduce o anula el monto de un comprobante previo |
| TE | Tiquete Electrónico | Venta al consumidor final sin datos fiscales del receptor |
| FEC | Factura Electrónica de Compra | Emitida por un contribuyente que compra a un no contribuyente / régimen simplificado |
| FEE | Factura Electrónica de Exportación | Ventas al exterior (exportaciones) |
| REP | **Recibo Electrónico de Pago** (nuevo en 4.4) | Comprobante obligatorio para ventas a crédito con IVA diferido y cobros a entidades públicas; reporta el IVA en el momento de percibir el pago |
| MR | Mensaje Receptor (Confirmación) | Respuesta del receptor: aceptación, aceptación parcial o rechazo. No es un comprobante de venta sino un mensaje de confirmación del receptor electrónico |

### REP — Recibo Electrónico de Pago

- **Escenarios obligatorios:** ventas a crédito con IVA diferido, facturas a entidades públicas cuando se percibe el pago, cobros parciales de ventas a crédito.
- **Efecto fiscal:** permite reportar el IVA en el momento de recibir el dinero (criterio de caja para esos casos) en lugar de al momento de emitir la factura.
- **Obliga:** a quienes presten servicios/bienes al sector público o manejen cartera de crédito con cobros parciales.

Los **tiquetes (TE)** se emiten típicamente por dispositivos POS para consumidor final; no requieren identificación del receptor y tienen estructura simplificada.

El **MR (Mensaje Receptor / Mensaje de Confirmación)** no es un comprobante de venta: es el documento XML que el receptor electrónico envía a Hacienda para aceptar total o parcialmente, o rechazar, una factura recibida. Usa un esquema y namespace distinto del de los comprobantes de venta.

## 3. Estructura del XML v4.4 — diferencias contra 4.3

### Namespaces y esquemas

Namespaces confirmados directamente contra los XSDs oficiales descargados (ver `esquemas/`):

| Documento | Namespace 4.4 (targetNamespace del XSD) |
|-----------|-----------------------------------------|
| FacturaElectronica | `https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.4/facturaElectronica` |
| TiqueteElectronico | `https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.4/tiqueteElectronico` |
| NotaCreditoElectronica | `https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.4/notaCreditoElectronica` |
| NotaDebitoElectronica | `https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.4/notaDebitoElectronica` |
| FacturaElectronicaCompra | `https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.4/facturaElectronicaCompra` |
| FacturaElectronicaExportacion | `https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.4/facturaElectronicaExportacion` |
| ReciboElectronicoPago (REP) | `https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.4/reciboElectronicoPago` (nuevo) |
| MensajeReceptor | `https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.4/mensajeReceptor` |
| MensajeHacienda (respuesta firmada) | `https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.4/mensajeHacienda` |

Todos los XSDs importan el esquema estándar W3C `xmldsig-core-schema.xsd` (namespace `http://www.w3.org/2000/09/xmldsig#`) vía ruta relativa `../../xmldsig-core-schema.xsd` — replicable o redirigible vía `XmlResolver` custom al integrar a `.NET`.

XSD de referencia oficial: `https://www.hacienda.go.cr/docs/FacturaElectronica_V4.4.xsd.xml` y anexos publicados en `https://atv.hacienda.go.cr/ATV/ComprobanteElectronico/frmAnexosyEstructuras.aspx`.

### Principales diferencias respecto a 4.3 (146 ajustes técnicos)

1. **Nuevo comprobante REP** — se añade `ReciboElectronicoPago` con su propio XSD y namespace.
2. **`CodigoActividadEmisor` y `CodigoActividadReceptor`** — la actividad económica del receptor se vuelve obligatoria cuando los bienes/servicios corresponden a crédito o gasto deducible; permite cruce fiscal por sector.
3. **Nuevos tipos de identificación** — se añaden códigos para:
   - Extranjero no domiciliado
   - No contribuyente
4. **Catálogo de medios de pago ampliado** — se añaden códigos para:
   - **SINPE Móvil**
   - **Plataformas digitales (PayPal y similares)**
5. **Desglose obligatorio de combos/paquetes** — cada producto dentro de un combo debe listarse individualmente con su código CABYS 2025.
6. **CABYS 2025** — nueva versión del catálogo de bienes y servicios obligatoria desde junio 2025; nuevos códigos para medicamentos y categorías actualizadas.
7. **Condiciones de venta ampliadas** — nuevas condiciones relacionadas al manejo de pagos diferidos y REP.
8. **Campos específicos para sector farmacéutico** — nuevos nodos de información regulatoria.
9. **Cierre/resumen mejorado** — mejoras en `ResumenFactura` para claridad del desglose de impuestos y descuentos.
10. **Compatibilidad CABYS ↔ actividad** — validaciones más estrictas de que el CABYS del ítem sea coherente con la actividad económica del emisor.

El listado exhaustivo de los 146 cambios se encuentra en [`normativa/ANEXOS_Y_ESTRUCTURAS_V4.4.pdf`](normativa/ANEXOS_Y_ESTRUCTURAS_V4.4.pdf), sección "Bitácora 4.4.0" (p. 3-22). Los 10 puntos anteriores son los más relevantes para la implementación del pipeline; para cambios puntuales consultar la bitácora.

## 4. Clave numérica

La **clave numérica** es un identificador único de 50 dígitos generado por el sistema del obligado tributario al momento de emitir cada comprobante electrónico. Debe ser consecutiva, única y no alterable.

### Estructura de la clave (50 dígitos)

| Posición | Longitud | Campo | Descripción |
|----------|----------|-------|-------------|
| 1–3 | 3 | Código de país | Siempre `506` (Costa Rica) |
| 4–5 | 2 | Día | Día de emisión (DD) |
| 6–7 | 2 | Mes | Mes de emisión (MM) |
| 8–9 | 2 | Año | Año de emisión (YY, dos dígitos) |
| 10–21 | 12 | Identificación del emisor | Número de identificación del emisor rellenado con ceros a la izquierda hasta 12 posiciones |
| 22–41 | 20 | Consecutivo | Número consecutivo interno del comprobante |
| 42 | 1 | Situación del comprobante | `1` = normal, `2` = contingencia, `3` = sin internet |
| 43–50 | 8 | Código de seguridad | Código aleatorio de 8 dígitos generado por el sistema del emisor |

### Estructura del consecutivo (20 dígitos)

El campo consecutivo dentro de la clave es a su vez un identificador compuesto que debe reproducirse también en el nodo `NumeroConsecutivo` del XML:

| Posición | Longitud | Campo | Descripción |
|----------|----------|-------|-------------|
| 1–3 | 3 | Casa matriz / sucursal | Código del establecimiento (001 = casa matriz) |
| 4–8 | 5 | Terminal / punto de venta | Código del terminal emisor (00001 = principal) |
| 9–10 | 2 | Tipo de comprobante | 01=FE, 02=ND, 03=NC, 04=TE, 05–07=MR, 08=FEC, 09=FEE, 10=REP |
| 11–20 | 10 | Consecutivo del comprobante | Numeración secuencial dentro del tipo |

### Código de seguridad

Los últimos 8 dígitos son un **código aleatorio** que el emisor genera libremente; Hacienda no lo valida pero exige que esté presente y que forme parte de la clave única. Debe ser impredecible para proteger la integridad de la numeración. Normalmente se genera con un generador de números aleatorios seguro.

### Códigos de tipo de comprobante (posiciones 9–10 del consecutivo)

| Código | Tipo |
|--------|------|
| 01 | Factura Electrónica (FE) |
| 02 | Nota de Débito (ND) |
| 03 | Nota de Crédito (NC) |
| 04 | Tiquete Electrónico (TE) |
| 05 | Confirmación de aceptación (MR) |
| 06 | Confirmación de aceptación parcial (MR) |
| 07 | Confirmación de rechazo (MR) |
| 08 | Factura Electrónica de Compra (FEC) |
| 09 | Factura Electrónica de Exportación (FEE) |
| 10 | Recibo Electrónico de Pago (REP) |

> El XSD **no valida** el tipo dentro del consecutivo: `NumeroConsecutivoType` es simplemente el patrón `\d{20,20}`. Los códigos listados se confirman contra la **Nota 3 del Anexo V4.4** ([`normativa/ANEXOS_Y_ESTRUCTURAS_V4.4.pdf`](normativa/ANEXOS_Y_ESTRUCTURAS_V4.4.pdf), p. 65), que los enumera textualmente.

## 5. Identificación tributaria

En Costa Rica, todo emisor o receptor de comprobantes electrónicos se identifica con uno de los siguientes tipos. Los 6 códigos están confirmados contra el XSD oficial (`IdentificacionType.Tipo` en `FacturaElectronica_V4.4.xsd`). El XSD sólo restringe `Numero` a `maxLength=20` sin patrón por tipo — las longitudes específicas por tipo son regla de negocio, no de XSD.

| Código | Tipo | Longitud (regla de negocio) | Formato | Descripción |
|--------|------|-----------------------------|---------|-------------|
| 01 | Cédula física | 9 dígitos | numérico | Costarricense nacional. Ej: `101230456` |
| 02 | Cédula jurídica | 10 dígitos | numérico | Persona jurídica registrada en CR. Ej: `3101123456` |
| 03 | DIMEX | 11 o 12 dígitos | numérico | Documento de Identidad Migratorio para Extranjeros (residentes con estatus migratorio aprobado) |
| 04 | NITE | 10 dígitos | numérico | Número de Identificación Tributario Especial, asignado por DGT a extranjeros/entidades sin cédula que tengan obligaciones tributarias en CR |
| 05 | **Extranjero no domiciliado** (nuevo en 4.4) | ≤20 (XSD no restringe por tipo) | alfanumérico | Para receptores extranjeros que no tienen identificación costarricense y no están domiciliados en el país |
| 06 | **No contribuyente** (nuevo en 4.4) | ≤20 (XSD no restringe por tipo) | alfanumérico | Para identificar compras a personas no inscritas como contribuyentes |

### Reglas específicas

- **Cédula física (tipo 01):** siempre 9 dígitos **sin ceros a la izquierda en el XML** cuando es emisor; en algunos sistemas se rellena, verificar el XSD.
- **Cédula jurídica (tipo 02):** siempre 10 dígitos, comienza con `3` (indicador de persona jurídica) seguido de dos dígitos que indican el tipo de entidad (101=S.A., 102=S.R.L., 004=gobierno, etc.).
- **DIMEX (tipo 03):** actualmente se admiten 11 o 12 dígitos. Formato sin guiones ni espacios.
- **NITE (tipo 04):** 10 dígitos asignados por Tributación a extranjeros no residentes con obligaciones fiscales en CR.
- **Extranjero no domiciliado (tipo 05):** usado típicamente en exportaciones (FEE) donde el receptor no tiene identificación CR.
- **No contribuyente (tipo 06):** aplicable en Factura Electrónica de Compra (FEC) para capturar transacciones con personas físicas no inscritas.

Para tiquete electrónico (TE) **no es obligatorio** identificar al receptor.

## 6. Firma digital XAdES-EPES

Todo comprobante electrónico (FE, NC, ND, TE, FEC, FEE, REP) y Mensaje Receptor debe ir firmado digitalmente con una firma **XAdES-EPES enveloped** según **ETSI TS 101 903 v1.3.2** o superior, basada en el estándar XMLDSig (`http://www.w3.org/2000/09/xmldsig#`).

### Certificado de firma

- **Tipo:** certificado de firma digital emitido por una **Autoridad Certificadora** bajo la jerarquía del Sistema Nacional de Certificación Digital de Costa Rica (SINPE/BCCR), o certificado de **llave criptográfica** emitido por Hacienda específicamente para facturación electrónica de personas jurídicas.
- **Uso de llave criptográfica:** Hacienda permite descargar desde ATV un certificado PKCS#12 (`.p12`) protegido por PIN, que se usa exclusivamente para firmar comprobantes electrónicos.
- **Algoritmo de llave:** RSA 2048 bits.
- **Algoritmo hash:** SHA-256.

### Ubicación y empaquetado

- **Empaquetado:** `ENVELOPED` obligatorio. No se acepta `DETACHED` ni `ENVELOPING`.
- **XPath destino de la firma:** `/FacturaElectronica/ds:Signature` (y análogos por tipo de documento).
- Debe firmarse el XML completo, usando la transformación `enveloped-signature` para excluir el nodo `ds:Signature` del cálculo del digest.

### Algoritmos requeridos

Valores confirmados contra ejemplos oficiales del Anexo 2 ([`normativa/ANEXOS_Y_ESTRUCTURAS_V4.4.pdf`](normativa/ANEXOS_Y_ESTRUCTURAS_V4.4.pdf), pp. 85-87):

| Uso | Algoritmo |
|-----|-----------|
| Digest de referencias | `http://www.w3.org/2001/04/xmlenc#sha256` |
| Canonicalización | `http://www.w3.org/2001/10/xml-exc-c14n#` (**Exclusive C14N**) |
| SignatureMethod | `http://www.w3.org/2001/04/xmldsig-more#rsa-sha256` |
| Transformación para excluir la firma | `http://www.w3.org/TR/1999/REC-xpath-19991116` con XPath `not(ancestor-or-self::ds:Signature)` |
| Llave | RSA 2048 o RSA 4096 |
| Hash permitidos | SHA-256 o SHA-512 |

Notas:
- Hacienda usa **Exclusive C14N** (`xml-exc-c14n#`), no Inclusive. Es un error común pensar que aplica `xml-c14n-20010315`.
- El ejemplo oficial usa `<ds:Transform Algorithm="http://www.w3.org/TR/1999/REC-xpath-19991116">` + XPath, en lugar de `enveloped-signature`. Ambos excluyen la firma del digest; seguir el ejemplo oficial por compatibilidad exacta.

### Elementos XAdES-EPES obligatorios

Se debe incluir el bloque `QualifyingProperties` (namespace `http://uri.etsi.org/01903/v1.3.2#`) con:

- `SignedProperties` con:
  - `SigningTime` — timestamp ISO-8601 de la firma.
  - `SigningCertificate` — `CertDigest` (SHA-256 o SHA-512 del certificado X.509) e `IssuerSerial`.
  - **`SignaturePolicyIdentifier`** (lo que lo hace EPES, no BES) — ver "Política de firma vigente" abajo.
  - `SignedDataObjectProperties` con `DataObjectFormat` declarando `MimeType` = `application/octet-stream` (no `text/xml`, según ejemplos oficiales).
- Para firmas adicionales (receptor, endosante, endosatario), añadir `<xades:ClaimedRole>` con el valor correspondiente (`Receptor`, `Endosante1`, `Endosatario1`, etc.).

### Política de firma vigente (actualizada en 4.4)

Hacienda actualizó la URL de la política de firma para 4.4. La política ya **no apunta al PDF de la resolución DGT-R-48-2016** sino al documento consolidado:

- **`xades:SigPolicyId/xades:Identifier`:**
  `https://cdn.comprobanteselectronicos.go.cr/xml-schemas/Resolución_General_sobre_disposiciones_técnicas_comprobantes_electrónicos_para_efectos_tributarios.pdf`
- **`xades:SigPolicyHash`:** `DigestMethod = xmlenc#sha256`, `DigestValue = DWxin1xWOeI8OuWQXazh4VjLWAaCLAA954em7DMh0h8=` (valor del ejemplo oficial; debe recalcularse cada vez que Hacienda actualice el PDF).

Cualquier comprobante sin firma, con firma mal formada o con política de firma incorrecta es **rechazado** por la recepción de Hacienda con error a nivel de validación estructural.

Cualquier comprobante sin firma, con firma mal formada o con política de firma incorrecta es **rechazado** por la recepción de Hacienda con error a nivel de validación estructural.

## 7. API REST de Hacienda (ATV) — endpoints y flujo

La recepción de comprobantes se realiza contra la API REST de Hacienda. La autenticación usa **OpenID Connect / OAuth 2.0** contra un IdP basado en Keycloak hospedado por el Ministerio de Hacienda.

### URLs oficiales

| Ambiente | Endpoint base API | Endpoint token IdP (OIDC) | Realm | client_id |
|----------|-------------------|--------------------------|-------|-----------|
| **Producción** | `https://api.comprobanteselectronicos.go.cr/recepcion/v1/` | `https://idp.comprobanteselectronicos.go.cr/auth/realms/rut/protocol/openid-connect/token` | `rut` | `api-prod` |
| **Sandbox (staging)** | `https://api.comprobanteselectronicos.go.cr/recepcion-sandbox/v1/` | `https://idp.comprobanteselectronicos.go.cr/auth/realms/rut-stag/protocol/openid-connect/token` | `rut-stag` | `api-stag` |

- `client_secret` siempre **vacío** (la autenticación es por usuario/contraseña dentro del grant, no por secret del cliente).
- `scope` también **vacío**.
- `grant_type=password` (Resource Owner Password Credentials).
- **Formato de username** (confirmado por Anexo 3, p. 97): `{tipoId}-{número-dividido-por-guiones}@comprobanteselectronicos.go.cr`, por ejemplo `cpf-01-1234-5678@comprobanteselectronicos.go.cr`.
- Usuario y contraseña se obtienen en ATV ("Administración Tributaria Virtual"), sección "Comprobantes Electrónicos → Obtener credenciales API".

### Obtención del token (OIDC password grant)

```
POST https://idp.comprobanteselectronicos.go.cr/auth/realms/rut/protocol/openid-connect/token
Content-Type: application/x-www-form-urlencoded

grant_type=password
&client_id=api-prod
&client_secret=
&username=<usuario ATV>
&password=<contraseña ATV>
```

Respuesta: `access_token` (Bearer, vida corta ~5 minutos) y `refresh_token` (~30 minutos).

### Recursos REST

Confirmados contra Anexo 3 del Anexo oficial ([`normativa/ANEXOS_Y_ESTRUCTURAS_V4.4.pdf`](normativa/ANEXOS_Y_ESTRUCTURAS_V4.4.pdf), p. 97):

| Método | Ruta | Propósito |
|--------|------|-----------|
| `POST` | `/recepcion` | Envía un comprobante firmado (FE/ND/NC/TE/FEC/FEE/REP) o MR |
| `GET`  | `/recepcion/{clave}` | Consulta estado por clave. **⚠️ MR:** el MensajeReceptor **NO tiene clave propia** — el XSD `MensajeReceptor_V4.4.xsd` tiene un único `Clave` (= la del comprobante **recibido**) y su identidad es `Clave` + `NumeroConsecutivoReceptor` (20 díg.). Por tanto una `GET /recepcion/{clave}` con la clave desnuda colisionaría con el comprobante ORIGINAL del proveedor (ya aceptado). DetCore consulta el MR por el **compuesto `{clave}-{consecutivoReceptor}`** (`HaciendaApiClient`), derivado del XSD + Anexo 3 (el Anexo confirma `GET /recepcion/{clave}` genérico y remite el formato exacto al **Portal de Hacienda**, no incluido en este repo). **Confirmar el separador exacto contra el sandbox en F13.10** — un separador equivocado falla seguro (404 → sigue Pending → age-out 72h), nunca un falso-Accept. |
| `GET`  | `/comprobantes` | Resumen de todos los comprobantes enviados por el obligado tributario, orden descendente por fecha |
| `GET`  | `/comprobantes/{clave}` | Recupera un comprobante específico por clave |

### Formato del payload de envío (POST /recepcion)

Body JSON:

```json
{
  "clave": "50630072500310112345600001010000000001123456781",
  "fecha": "2026-04-17T10:30:00-06:00",
  "emisor": {
    "tipoIdentificacion": "02",
    "numeroIdentificacion": "3101123456"
  },
  "receptor": {
    "tipoIdentificacion": "02",
    "numeroIdentificacion": "3101234567"
  },
  "comprobanteXml": "<base64 del XML firmado>",
  "callbackUrl": "opcional"
}
```

### Headers obligatorios

- `Authorization: Bearer <access_token>`
- `Content-Type: application/json`
- `Accept: application/json`

### Respuestas esperadas

| HTTP | Significado |
|------|-------------|
| `202 Accepted` | Comprobante recibido para procesamiento (NO confirmado aún) |
| `400 Bad Request` | Error de estructura, clave duplicada, firma inválida |
| `401 Unauthorized` | Token inválido o expirado |
| `403 Forbidden` | Sin permisos para el emisor |
| `404 Not Found` | Clave no existe (en GET) |

### Flujo completo recomendado

1. Construir XML según XSD v4.4.
2. Firmar con XAdES-EPES (ver §6).
3. Obtener token OIDC si no se tiene uno vigente.
4. `POST /recepcion` con el XML en Base64.
5. Si `202`, iniciar polling con `GET /recepcion/{clave}` hasta obtener `aceptado` o `rechazado`.
6. Persistir el `xml-respuesta-mh` (respuesta firmada por Hacienda) junto al XML original.

## 8. Modelo asíncrono — implicaciones de polling

El modelo de Costa Rica es **asíncrono en dos fases**:

### Fase 1 — Recepción (inmediata)

El `POST /recepcion` NO valida la factura contra reglas de negocio. Sólo valida:

- Autenticación OIDC correcta.
- Clave numérica bien formada y no duplicada.
- XML presente y estructurado (Base64 decodificable).

Respuesta típica: **HTTP 202 Accepted** con el comprobante en estado `recibido`. Esto NO significa que Hacienda haya aceptado la factura.

### Fase 2 — Validación y respuesta definitiva (asincrónica)

Hacienda procesa el XML en cola: valida XSD, firma XAdES-EPES, política de firma, CABYS vs actividad económica, consistencia de impuestos, existencia de receptor, etc. El resultado se obtiene únicamente por **polling** al GET:

```
GET /recepcion/{clave}
Authorization: Bearer <token>
```

Respuesta (JSON):

```json
{
  "clave": "506...",
  "fecha": "2026-04-17T10:30:00-06:00",
  "ind-estado": "aceptado" | "rechazado" | "procesando" | "recibido",
  "respuesta-xml": "<base64 del XML-respuesta firmado por Hacienda>"
}
```

### Estados

| ind-estado | Significado |
|------------|-------------|
| `recibido` | Aceptado estructuralmente; pendiente de validación |
| `procesando` | En cola interna de validación |
| `aceptado` | Aprobado por Hacienda — factura válida fiscalmente |
| `rechazado` | Rechazado — el `respuesta-xml` contiene los motivos |

### Implicaciones de implementación

1. **Polling con backoff.** Tras el `202`, esperar al menos 5–10 segundos antes del primer `GET`. Luego polling exponencial (ej. 10s → 30s → 1min → 2min → 5min). En condiciones normales la validación toma segundos; en picos o mantenimientos puede tomar minutos u horas.
2. **Timeouts largos.** El sistema puede demorar en darse de baja o responder durante ventanas de mantenimiento. **No asumir un timeout corto**: diseñar el pipeline con reintentos persistentes durante al menos 24 h.
3. **Idempotencia por clave.** Enviar el mismo XML dos veces con la misma clave devuelve HTTP 409 o indica duplicado. La clave actúa como idempotency key natural.
4. **El `respuesta-xml` es firmado por Hacienda.** Debe conservarse junto al XML original como prueba documental del estado de la factura (requisito fiscal de archivo por 5 años).
5. **El receptor puede responder con MR (Mensaje Receptor).** Aceptación, aceptación parcial o rechazo. Esto es independiente del estado de Hacienda: una factura `aceptado` por Hacienda puede ser `rechazada` por el receptor (y viceversa).
6. **Callbacks HTTP sí funcionan.** El Anexo 3 (p. 98) confirma que el `callbackUrl` en el payload del `POST /recepcion` recibe un `POST application/json` con el mismo cuerpo que devuelve el `GET /recepcion/{clave}`. El endpoint del emisor debe responder `HTTP 200`; si no responde o hay timeout, Hacienda reintenta hasta **3 veces** y luego registra el fallo en bitácora (no se reenvía más). El polling por `GET` sigue disponible como mecanismo primario o de respaldo.
7. **Contingencia.** Si Hacienda está caída, la factura se emite con `situacion=2` (contingencia) y se transmite cuando el servicio se restablezca, con un plazo máximo (usualmente 8 días hábiles según la resolución).

## 9. Mensaje Receptor (MR)

El **Mensaje Receptor (MR)** es un documento XML separado que el receptor electrónico de una factura envía a Hacienda para manifestar su posición respecto a dicho comprobante. **Es obligatorio** cuando el receptor es un contribuyente del IVA que desea respaldar la compra para propósitos de crédito o gasto deducible.

### Tipos de MR

| Código | Tipo | Cuándo se usa |
|--------|------|---------------|
| 1 | **Aceptación** | El receptor acepta totalmente la factura, reconoce el crédito IVA y la compra queda respaldada |
| 2 | **Aceptación parcial** | El receptor acepta solo parcialmente el contenido; se requiere emitir una **Nota de Crédito** por la diferencia. Uso exclusivo del contribuyente para ajustar el monto original |
| 3 | **Rechazo** | El receptor rechaza la factura (por ejemplo, porque no le corresponde o contiene errores no corregibles). El IVA no se reconoce como crédito |

### Consecutivo del MR

En el consecutivo de 20 dígitos, el tipo de comprobante MR usa **05 (aceptación), 06 (aceptación parcial), 07 (rechazo)**.

### Plazos

- El MR debe enviarse dentro de los **primeros 8 días hábiles del mes siguiente** al que se generó la operación.
- Hacienda valida y responde al envío del MR dentro de un plazo de aproximadamente **3 horas**.
- Si se envió un MR de rechazo por error, puede corregirse enviando un nuevo MR mientras se esté dentro del plazo.

### Estructura del XML de MR

El MR tiene su propio XSD y namespace:
- Namespace 4.4: `https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.4/mensajeReceptor`

Nodos principales:
- `Clave` — clave del comprobante original (50 dígitos)
- `NumeroCedulaEmisor` — emisor de la factura original
- `FechaEmisionDoc` — fecha de emisión de **la confirmación (el MR)**, NO de la factura original. Así lo define el XSD (`MensajeReceptor_V4.4.xsd:33`: *"Fecha de emision de la confirmación"*); DetCore la fija al instante de la confirmación (`now`)
- `Mensaje` — 1=aceptado, 2=aceptado parcial, 3=rechazado
- `DetalleMensaje` — texto libre explicativo
- `MontoTotalImpuesto` — total de impuestos reconocidos
- `TotalFactura` — total aceptado
- `NumeroCedulaReceptor` — cédula del receptor que emite el MR
- `NumeroConsecutivoReceptor` — consecutivo propio del receptor para el MR
- `ds:Signature` — firma XAdES-EPES del receptor

### Proceso

1. Receptor recibe factura (XML) del emisor (directamente o vía sistema externo).
2. Receptor construye su MR con su propia clave numérica y consecutivo.
3. Firma el MR con su certificado digital (misma política XAdES-EPES que los comprobantes).
4. POST a `/recepcion` con el MR (mismo endpoint que los comprobantes).
5. Polling para confirmar aceptación del MR por Hacienda.

### Obligatoriedad

- **Obligatorio** para: contribuyentes del IVA que vayan a reconocer crédito fiscal por la compra.
- **No obligatorio** para: consumidores finales, no contribuyentes, o compras no deducibles (aunque se recomienda confirmar siempre).
- Si no se envía MR dentro del plazo, la operación **no puede sustentar** crédito fiscal ni gasto deducible.

## 10. Representación impresa (PDF)

La **representación impresa** (también llamada "representación gráfica") es el PDF legible para humanos que acompaña al XML. NO reemplaza al XML como documento fiscal — el XML firmado es el documento legal —, pero es obligatorio entregarlo al receptor en operaciones donde se pacte.

### Contenido obligatorio de la representación impresa

- Título del tipo de comprobante: "Factura Electrónica", "Tiquete Electrónico", "Nota de Crédito Electrónica", etc.
- Identificación completa del **emisor**: nombre/razón social, cédula, actividad económica, dirección, teléfono, correo.
- Identificación del **receptor** (cuando aplique).
- **Clave numérica** (50 dígitos) del comprobante, visible.
- **Consecutivo** del comprobante.
- **Fecha y hora** de emisión.
- Detalle de líneas con CABYS, cantidad, precio unitario, descuentos, impuestos.
- Totales: subtotal, descuentos, impuestos desglosados, total.
- **Condición de venta** y **medio de pago**.
- Leyenda obligatoria: **"Autorizada mediante resolución MH-DGT-RES-0027-2024 del [fecha]"** (o la resolución vigente al momento).
- Leyenda informativa sobre cómo consultar la validez del comprobante en el portal de Hacienda.

### Código QR — SUSPENDIDO

Originalmente la resolución 4.4 contemplaba la obligatoriedad del **código QR** en el PDF (en la esquina inferior derecha, tamaño mínimo 2.5 cm × 2.5 cm) con el enlace al XML o una URL de consulta pública.

Sin embargo, **Hacienda suspendió la obligatoriedad del código QR** mediante comunicado oficial (octubre 2025). Queda suspendida hasta que la autoridad tributaria lo disponga de nuevo. Los PDFs pueden incluirlo opcionalmente.

### Cambios en 4.4 respecto a 4.3 en la representación

1. **Desglose obligatorio de combos/paquetes:** cada producto dentro de un combo debe aparecer como línea separada con su CABYS individual, tanto en el XML como en el PDF.
2. **Actividad económica del receptor** visible cuando sea obligatoria.
3. **Nueva leyenda REP:** el REP debe identificarse claramente como "Recibo Electrónico de Pago" y hacer referencia a la(s) factura(s) original(es) cuyo pago documenta.
4. **Nuevos medios de pago en la leyenda:** SINPE Móvil y plataformas digitales (PayPal) deben imprimirse con su texto descriptivo.
5. **Nuevos tipos de identificación:** Extranjero no domiciliado y No contribuyente deben identificarse correctamente en la impresión.

### Formato e idioma

- **Idioma:** español (o español+inglés para FEE de exportación).
- **Formato:** PDF (habitualmente A4 o carta).
- **Conservación:** el emisor debe conservarlo por 5 años junto con el XML.

El Anexo V4.4 **no impone** una URL específica de consulta pública en la representación impresa. Su Nota 1 sólo exige que los campos "Tipo de documento electrónico", "Clave" y "Numeración consecutiva" queden agrupados. La URL y el QR (hoy suspendido) son elementos adicionales opcionales.

## 11. Errores comunes de Hacienda

Los rechazos más frecuentes por parte del servicio de recepción de Hacienda se agrupan en cuatro familias:

### Familia 1 — Firma digital

| Causa | Descripción |
|-------|-------------|
| Certificado expirado | La llave criptográfica de Hacienda tiene vigencia de 2 años; tras expirar, todos los comprobantes son rechazados |
| Firma XAdES mal formada | Falta `SigningCertificate`, falta `SignaturePolicyIdentifier`, hash de política incorrecto |
| Algoritmo no válido | Uso de SHA-1 en lugar de SHA-256, RSA < 2048 bits |
| Canonicalización incorrecta | No usar `c14n-20010315`, olvidar `enveloped-signature` transform |

### Familia 2 — Clave y consecutivo

| Causa | Descripción |
|-------|-------------|
| Clave duplicada | Se reenvió un comprobante ya recibido (misma clave 50 dígitos) |
| Clave mal formada | Estructura incorrecta (país != 506, fecha inconsistente, checksum) |
| Consecutivo fuera de orden | Salto o retroceso en la numeración consecutiva del emisor para el punto de venta |
| Situación incorrecta | Uso de `situacion=2` (contingencia) cuando Hacienda sí estaba disponible |

### Familia 3 — CABYS y actividad económica

| Causa | Descripción |
|-------|-------------|
| CABYS no coincide con actividad | El código CABYS del ítem no corresponde a las actividades económicas registradas del emisor |
| CABYS inexistente | Código no está en el catálogo CABYS 2025 |
| IVA incorrecto | El porcentaje de IVA aplicado no coincide con el definido para ese CABYS |
| Falta `CodigoActividadReceptor` | En ventas a contribuyentes cuando es obligatorio en 4.4 |

### Familia 4 — Receptor e identificación

| Causa | Descripción |
|-------|-------------|
| Tipo de identificación inválido | Uso de código de tipo obsoleto o no admitido en 4.4 |
| Longitud incorrecta | Cédula física con != 9 dígitos, jurídica con != 10, DIMEX fuera de 11–12 |
| Receptor no existe en registro | El número de identificación del receptor no está inscrito en Tributación |
| Correo electrónico del receptor mal formado | Campo `CorreoElectronico` con formato inválido |

### Familia 5 — Estructura XML y totales

| Causa | Descripción |
|-------|-------------|
| XSD inválido | Nodos obligatorios faltantes, orden incorrecto, tipos de datos no coinciden |
| Totales descuadrados | Suma de líneas != total, impuestos mal calculados, redondeo inconsistente |
| Fecha fuera de rango | Fecha de emisión en el futuro o demasiado antigua (> 30 días) |
| Tipo de cambio ausente | En FEE (exportación) sin tipo de cambio cuando la moneda no es CRC |

### Familia 6 — Operación

| Causa | Descripción |
|-------|-------------|
| Token expirado | `Authorization: Bearer` con token OIDC vencido (>5 min) |
| Permisos insuficientes | El usuario API no tiene permiso para el emisor declarado |
| Emisor no habilitado | El contribuyente no está inscrito como Emisor-Receptor Electrónico |

**Estructura del `respuesta-xml` (confirmada contra `MensajeHacienda_V4.4.xsd`):**
- `Mensaje` — enum: `1` (Aceptado) o `3` (Rechazado). No existe valor para "aceptado parcial" a nivel de Hacienda (ese sólo aplica a MR).
- `DetalleMensaje` — texto libre con los motivos del rechazo.
- `EstadoMensaje`, `MontoTotalImpuesto`, `TotalFactura` — datos de respaldo.

**Confirmado:** el Anexo V4.4 no publica un catálogo numérico estructurado de códigos de error. El XSD `MensajeHacienda` confirma que `DetalleMensaje` es `string` libre y que `Mensaje` solo enumera `1` (Aceptado) y `3` (Rechazado). Cualquier parseo estructurado del motivo de rechazo es por inspección de texto, no por código tabulado.

## 12. Sandbox / ambiente de pruebas

Hacienda provee un ambiente de certificación (staging/sandbox) paralelo a producción para pruebas de integración. Es **obligatorio** emitir al menos una factura, un tiquete y una nota de crédito en sandbox antes de pasar a producción.

### URLs del ambiente de pruebas

| Recurso | URL |
|---------|-----|
| API recepción sandbox | `https://api.comprobanteselectronicos.go.cr/recepcion-sandbox/v1/` |
| IdP OIDC sandbox | `https://idp.comprobanteselectronicos.go.cr/auth/realms/rut-stag/protocol/openid-connect/token` |
| Realm | `rut-stag` |
| client_id | `api-stag` |
| client_secret | (vacío) |
| Portal ATV | `https://atv.hacienda.go.cr/ATV/Login.aspx` (mismo portal para gestión de credenciales) |

### Pasos para habilitar pruebas

1. **Inscripción en ATV:** el contribuyente debe registrarse como **Emisor-Receptor Electrónico** en el Registro Único Tributario (RUT) dentro de ATV. Sin esta inscripción no se habilitan los servicios API.
2. **Generar llave criptográfica:** dentro de ATV, sección "Comprobantes Electrónicos → Llave Criptográfica → Generar nueva contraseña". Esto produce un PKCS#12 (`.p12`) descargable + PIN para firmar. Existen llaves separadas para **sandbox** y **producción**.
3. **Credenciales API (OIDC):** en ATV se genera un usuario y contraseña específicos para API. Estos son los `username`/`password` del password grant.
4. **Certificado de prueba:** Hacienda emite un certificado PKCS#12 **de pruebas** distinto del de producción. Tiene cadena de certificación emitida por Hacienda (CA de sandbox).
5. **Emisión de comprobantes de prueba:** cualquier clave con `situacion=1` se considera válida; los datos de facturación en sandbox no tienen efecto fiscal real.
6. **Paso a producción:** una vez validada la integración, repetir la generación de llave y credenciales en el entorno productivo y apuntar al endpoint `https://api.comprobanteselectronicos.go.cr/recepcion/v1/`.

### Datos de prueba útiles

- **CABYS de prueba:** cualquier código válido del catálogo CABYS 2025 aplicable a la actividad económica registrada del emisor sandbox.
- **Cédulas receptor:** en sandbox se pueden usar cédulas ficticias siempre que respeten el formato (9 dígitos físicas, 10 dígitos jurídicas empezando por `3`).
- **Tipo de cambio:** consultar en el BCCR (Banco Central de Costa Rica) `https://www.bccr.fi.cr/indicadores-economicos` para valor oficial; en sandbox puede usarse cualquier valor razonable.

### Limitaciones del sandbox

- Los comprobantes emitidos en sandbox **no** son documentos fiscales reales; no se archivan para efectos tributarios.
- El sandbox puede experimentar **más latencia** que producción, especialmente durante mantenimientos.
- Las claves de emisores sandbox son completamente independientes de las de producción.
- Las credenciales OIDC de sandbox **no** funcionan contra el realm de producción (`rut`), y viceversa.

⚠️ PENDIENTE DE CONFIRMAR si tras el lanzamiento de la plataforma **TRIBU-CR** (nueva plataforma tributaria que reemplaza gradualmente a ATV desde octubre 2025) las credenciales y URLs de sandbox han cambiado o si coexisten los dos sistemas.

## 13. Fuentes consultadas

### Fuentes oficiales (Ministerio de Hacienda CR)

- [Resolución General MH-DGT-RES-000-2024 — Disposiciones Técnicas de Comprobantes Electrónicos](https://www.hacienda.go.cr/docs/DGT-R-000-2024DisposicionesTecnicasDeComprobantesElectronicosCP.pdf) — Resolución que introduce la versión 4.4.
- [FacturaElectronica_V4.4.xsd.xml](https://www.hacienda.go.cr/docs/FacturaElectronica_V4.4.xsd.xml) — XSD oficial v4.4 de la factura electrónica.
- [Anexos y Estructuras v4.4 — ATV](https://atv.hacienda.go.cr/ATV/ComprobanteElectronico/frmAnexosyEstructuras.aspx) — Repositorio oficial de XSDs, anexos y documentación técnica v4.4.
- [Comprobantes Electrónicos API v4.4](https://atv.hacienda.go.cr/ATV/ComprobanteElectronico/docs/esquemas/2024/v4.4/comprobantes-electronicos-api.html) — Documentación oficial de la API REST.
- [Comprobantes Electrónicos API (página general)](https://www.hacienda.go.cr/docs/ComprobantesElectronicosAPI.html) — Referencia de endpoints y payload.
- [Guía de uso para IdP Comprobantes Electrónicos](https://www.hacienda.go.cr/docs/Guia_IdP.pdf) — Guía oficial para autenticación OIDC.
- [Resolución DGT-R-48-2016 (política de firma)](https://oaf.ucr.ac.cr/system/files/Resolucion%20Comprobantes%20Electronicos%20%20DGT-R-48-2016.pdf) — Política de firma XAdES-EPES vigente.
- [Portal ATV — login](https://atv.hacienda.go.cr/ATV/Login.aspx) — Administración Tributaria Virtual.

### Recursos comunitarios y de integradores

- [CRLibre — URL de API de comprobantes electrónicos](https://crlibre.org/preguntas/url-de-api-de-comprobantes-electronicos/) — Recopilación comunitaria de URLs sandbox/producción.
- [CRLibre — fe-hacienda-cr-dotnet (issue XAdES-EPES)](https://github.com/CRLibre/fe-hacienda-cr-dotnet/issues/2) — Ejemplo de firma XAdES-EPES en .NET.
- [GitHub — royrojas/FacturaElectronicaCR](https://github.com/royrojas/FacturaElectronicaCR) — Ejemplo en VB.NET y C# de la factura electrónica CR.
- [GitHub — apokalipto/facturacr](https://github.com/apokalipto/facturacr) — Librería Ruby para CR.

### Análisis técnico de cambios 4.3 → 4.4

- [Deloitte — Comprobante electrónico 4.4: cinco cambios relevantes](https://www.deloitte.com/latam/es/services/tax/perspectives/cr-comprobante-electronico-4-4-cinco-cambios-relevantes.html) — Análisis profesional de los cambios técnicos.
- [Softland — Facturación electrónica 4.4: cambios clave](https://softland.com/cr/nuevos-cambios-de-la-facturacion-electronica-4-4/) — Resumen de cambios.
- [Facturele — Factura Electrónica 4.4, CABYS y REP: Cambios para 2025](https://www.facturele.com/2025/06/03/cambios-factura-version-4-4/) — Serie de artículos técnicos sobre cambios.
- [Facturele — 146 Ajustes XML](https://www.facturele.com/2025/10/20/ajustes-xml-facturacion-electronica/) — Detalle de los cambios XML.
- [Facturele — Código QR suspendido](https://www.facturele.com/2025/10/24/suspension-del-codigo-qr-factura-4-4/) — Noticia de la suspensión del QR obligatorio.
- [Facturele — Nuevos tipos de identificación](https://www.facturele.com/2025/07/18/nuevos-tipos-de-identificacion-4-4/) — Extranjero no domiciliado y No contribuyente.
- [Siempre al día — Recibo Electrónico de Pago (REP)](https://siemprealdia.co/costa-rica/impuestos/recibo-electronico-de-pago-rep/) — Detalle del REP.
- [Siempre al día — Firma digital en la factura electrónica 4.4](https://siemprealdia.co/costa-rica/impuestos/firma-digital-en-la-factura-electronica/) — Requisitos de firma en 4.4.
- [Gosocket — Nuevos Códigos CAByS 2025](https://gosocket.net/centro-de-recursos/nuevos-codigos-cabys-2025/) — Catálogo CABYS 2025.
- [Alegra — Guía facturación electrónica 4.4](https://blog.alegra.com/costa-rica/facturacion-electronica-en-costa-rica/) — Guía de implementación.
- [Alegra — Errores factura electrónica 2026](https://blog.alegra.com/costa-rica/errores-factura-electronica/) — Errores comunes y soluciones.
- [Nimetrix — Prórroga de Facturación Electrónica 4.4](https://www.nimetrixcostarica.com/blog/noticias-7/prorroga-de-facturacion-electronica-4-4-en-costa-rica-nueva-fecha-y-cambios-clave-23) — Detalles del calendario.

### Legislación y catálogos

- [facturaelectronica.cr — Leyes y Reglamentos](https://www.facturaelectronica.cr/LeyesyReglamentos) — Compilación de normativa CR.
- [Sistema Costarricense de Información Jurídica (SCIJ)](https://pgrweb.go.cr/scij/) — Consulta de normativa vigente.
- [OECD — Costa Rica TIN information](https://www.oecd.org/content/dam/oecd/en/topics/policy-issue-focus/aeoi/costa-rica-tin.pdf) — Formatos oficiales de identificación tributaria CR.

### Referencias sobre clave numérica y consecutivo

- [Roy Rojas — Número Consecutivo y Clave](https://royrojas.com/numero-consecutivo-y-clave-en-la-factura-electronica-en-costa-rica/) — Desglose de la estructura de 50 y 20 dígitos.
- [HuliPractice — Cómo funciona la clave numérica](https://blog.hulipractice.com/que-es-y-como-funciona-la-clave-numerica-en-la-factura-electronica-de-costa-rica/) — Explicación detallada.

