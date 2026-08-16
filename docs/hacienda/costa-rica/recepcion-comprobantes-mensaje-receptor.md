# Recepción y confirmación de comprobantes recibidos (Mensaje Receptor) — CR

> Diseño de la **Fase 13**. Fuente de verdad técnica del feature. La spec (qué/por qué) vive en
> `.specify/spec.md` §6.7 y RF-41..44; el plan (cómo) en `.specify/plan.md` §22; las tareas en
> `.specify/tasks.md` (Fase 13). Este documento sostiene el detalle: contrato JSON, mapa del XSD,
> reuso vs. nuevo y decisiones.

## Alcance

Un `account` (o su ERP), a través de un issuer que actúa como **receptor**, quiere **confirmar a
Hacienda** un comprobante que *recibió* de un proveedor: aceptarlo (1), aceptarlo parcialmente (2) o
rechazarlo (3). DetCore construye, firma y transmite el `MensajeReceptor` (MR) a partir de un **JSON
con los campos obligatorios** — **sin ingerir el XML del proveedor**, igual que hoy hace para la
emisión (JSON-in / XML-out). Al final entrega el acuse al proveedor por correo.

**Hallazgo que valida el planteamiento JSON-in:** Hacienda **no** expone un buzón de "recibidos".
`GET /comprobantes` devuelve solo lo que el obligado *emitió*; `GET /recepcion/{clave}` presupone que
ya se conoce la clave. El receptor obtiene la factura del proveedor **out-of-band** (`README.md:411`).
Por lo tanto los datos del comprobante recibido los aporta el ERP, no un pull a Hacienda.

## Decisiones tomadas

- **Ubicación SDD:** Fase 13 dedicada (F12 = despliegue a prod, ya hecha).
- **DetCore solo transmite, no calcula:** relaya los montos que manda el ERP (`MontoTotalImpuesto`,
  `MontoTotalImpuestoAcreditar`, `TotalFactura`, …); no computa ni verifica aritmética fiscal,
  obligatoriedad ni plazos. Ver principio del proyecto "DetCore relays, never infers".
- **Entrega del acuse al proveedor:** obligatoria al aceptar Hacienda, **reutilizando la maquinaria de
  entrega existente** (`EmailDelivery` / SMTP con reintentos y estado en panel). La dirección del
  proveedor la aporta el ERP en el JSON (DetCore no la tiene).
- **Consecutivo del receptor (`NumeroConsecutivoReceptor`):** lo aporta el **ERP**. DetCore no lleva
  estado de numeración (mismo criterio que en emisión, donde `officialId.consecutive` es del ERP).
- **`NumeroCedulaReceptor`:** se **deriva del `X-Issuer-Id`** (identidad fiscal no falsificable por
  documento), no del JSON.
- **Aceptación parcial (2):** DetCore solo transmite `Mensaje=2`; no exige ni relaciona la Nota de
  Crédito subsecuente (relay, no cálculo).
- **La decisión la toma el ERP, no un humano:** aceptar/parcial/rechazar lo decide el **sistema
  facturador** y entra por API; no hay confirmación manual en el portal. DetCore es facilitador de la
  transmisión.
- **Frontend:** solo **consulta**, con el **mismo diseño que el módulo de documentos** (listado con
  filtros + detalle con el MR, la respuesta de Hacienda y el estado de entrega). Sin formulario de
  captura. Operator-only en fase 1.
- **Aditivo:** no toca el pipeline de emisión ya probado.

---

## 1. Qué exige Hacienda del receptor

### 1.0 ⚠️ Las cédulas del Mensaje Receptor son SOLO DÍGITOS (asimetría con la emisión)

Los dos campos de identificación del MR llevan un facet que la emisión **no** tiene:

| Esquema | Campo | Restricción |
|---------|-------|-------------|
| `FacturaElectronica_V4.4.xsd` | `IdentificacionType/Numero` | `xs:string`, `maxLength=20`, **sin `pattern`** |
| `MensajeReceptor_V4.4.xsd` | `NumeroCedulaEmisor` | `maxLength=12`, **`pattern="\d{9,12}"`** |
| `MensajeReceptor_V4.4.xsd` | `NumeroCedulaReceptor` | `maxLength=20`, **`pattern="\d{9,12}"`** |

**Consecuencia:** la cédula jurídica **alfanumérica** (Decreto 44648-MJ, obligatoria para entidades
nuevas desde el 01-nov-2026) sirve para **emitir** pero **no puede aparecer en un Mensaje Receptor**,
ni como emisor ni como receptor. Hacienda habilitó el formato en un esquema y no en el otro.

Un contribuyente con cédula alfanumérica, por lo tanto, **no puede confirmar electrónicamente ningún
comprobante recibido** hasta que Hacienda amplíe el facet del MR. Tampoco se le puede confirmar un
comprobante *a él* cuando es el proveedor. No hay forma de sortearlo del lado del emisor: es una
validación de esquema en el receptor de Hacienda.

**Verificado en vivo el 2026-07-29** (STAG): un MR con receptor `3101A00001` fue transmitido y
rechazado con

```
cvc-pattern-valid: Value '3101A00001' is not facet-valid with respect to
pattern '\d{9,12}' for type '#AnonType_NumeroCedulaReceptorMensajeReceptor'
```

**En DetCore** la regla vive en `CrIdentification.IsMensajeReceptorCedula` y se aplica en dos puntos:
`CrReceptionIntentComposer` (corre en el API, así el operador recibe un 400 al apretar Procesar) y
`CrReceptionTransformer` (cubre además el camino F13 de ERP con JSON). Deliberadamente **no** reusa
`ClassifyIssuer`, que sí acepta la alfanumérica porque modela las reglas de **emisión**.

### 1.1 Los 3 tipos de mensaje y su efecto fiscal

`Mensaje` (`xs:integer`, obligatorio) es la decisión del receptor. El XSD enumera exactamente tres
valores (`MensajeReceptor_V4.4.xsd:36-59`):

| `Mensaje` | Significado | Efecto fiscal | Tipo en el consecutivo (pos. 9-10) |
|-----------|-------------|---------------|-------------------------------------|
| `1` | Aceptado | Reconoce el comprobante como crédito/gasto según `CondicionImpuesto` | `05` |
| `2` | Aceptado parcialmente | Habilita una **Nota de Crédito** que ajusta la operación al valor neto real (PDF p.75, Nota 44) | `06` |
| `3` | Rechazado | Rechaza el comprobante | `07` |

**Doble sistema de códigos:** el valor de `Mensaje` (1/2/3) **no** es el mismo que el tipo de
documento en las posiciones 9-10 del consecutivo del receptor (05/06/07) (PDF p.65, Nota 3). Ambos
deben ser coherentes; como el consecutivo lo aporta el ERP, es el ERP quien debe usar el tipo correcto.

### 1.2 Campos de crédito IVA

`CondicionImpuesto` (opcional, `MensajeReceptor_V4.4.xsd:91-104`; PDF p.80, Nota 18):

| Código | Significado |
|--------|-------------|
| `01` | Genera crédito IVA (crédito completo) |
| `02` | Genera crédito parcial del IVA (actividad mixta) |
| `03` | Bienes de capital |
| `04` | Gasto corriente, no genera crédito (IVA como gasto deducible) |
| `05` | Proporcionalidad |

Reglas condicionales (PDF p.61): `MontoTotalImpuestoAcreditar` y `MontoTotalDeGastoAplicable` **no se
usan** si `CondicionImpuesto = 05` ni si el mensaje es rechazo; `CodigoActividad` no se usa si aplica
proporcionalidad. DetCore **relaya** estos montos; no los calcula.

### 1.3 Firma y transmisión — idénticas a la emisión

- **Firma:** `ds:Signature` obligatoria (`MensajeReceptor_V4.4.xsd:148`). **XAdES-EPES** ENVELOPED,
  RSA-2048/4096, SHA-256/512. Para dar título ejecutivo (Ley 8454) la firma del receptor debe llevar
  `xades:ClaimedRole = 'Receptor'` (PDF p.84). **La emisión actual no fija `ClaimedRole`** → delta.
- **Transmisión:** **mismo endpoint** que los comprobantes — `POST /recepcion/v1/` (sandbox
  `/recepcion-sandbox/v1/`) (`README.md:414`).
- **Auth:** OIDC/OAuth2 ROPC contra el Keycloak de Hacienda, idéntica a emisión.
- **Respuesta:** Hacienda devuelve un `MensajeHacienda` firmado para la clave del MR; `Mensaje` solo
  enumera `1`=Aceptado / `3`=Rechazado (no hay "parcial" a nivel Hacienda —
  `MensajeHacienda_V4.4.xsd:140-158`). El poller y el parser de `MensajeHacienda` sirven verbatim.

### 1.4 Obligatoriedad, plazos y corrección — fuera del XSD y del anexo técnico

- **Obligatoriedad** (quién/cuándo) **no** figura en el PDF de anexos ni en el XSD; solo referencia el
  Decreto 44739-H art. 21 sin citarlo (PDF p.84). La afirmación del dossier ("obligatorio para
  contribuyentes IVA que reclaman crédito", `README.md:370-421`) **no tiene respaldo de cita normativa**
  dentro de las fuentes del repo.
- **Plazos:** el único límite temporal en el PDF es que `FechaEmisionDoc` no exceda **10 años** de
  antigüedad (PDF p.60) — no es un plazo de envío. Los "8 días hábiles del mes siguiente"
  (`README.md`) vienen del dossier, sin cita a la resolución. (El mismo "8 días hábiles" aparece
  también para contingencia — posible conflación; confirmar.)
- **Corrección de un MR erróneo:** **sí** está documentada en el dossier (`README.md:390`): se envía un
  MR nuevo dentro del plazo. Igual que arriba, viene del dossier, sin cita a la resolución.

> **Consecuencia de diseño:** por el principio "DetCore relays, never infers", DetCore **no** valida
> obligatoriedad ni plazos; solo relaya. Si el negocio quisiera enforcement, hay que sacar la letra del
> Decreto 44739-H / resolución vigente primero.

---

## 2. El contrato JSON (campos obligatorios)

Un MR tiene 13 elementos. DetCore **firma** (`ds:Signature`) y **deriva** `NumeroCedulaReceptor` del
issuer; **todo lo demás lo aporta el ERP** (incluidos consecutivo y fecha).

| Campo JSON | XSD | Oblig./Cond. | Quién lo aporta | Constraint |
|---|---|---|---|---|
| `clave` | `Clave` | **Obligatorio** | ERP | 50 díg (`\d{50}`) — clave del comprobante recibido |
| `supplierTaxId` | `NumeroCedulaEmisor` | **Obligatorio** | ERP | `\d{9,12}` — cédula del proveedor/emisor |
| `message` | `Mensaje` | **Obligatorio** | ERP | enum `1`/`2`/`3` |
| `messageDetail` | `DetalleMensaje` | **Condicional** — obligatorio si `message ∈ {2,3}` | ERP | `maxLength 160` (el mín-5 es regla del PDF, **no** del XSD — a confirmar) |
| `totalTaxAmount` | `MontoTotalImpuesto` | **Condicional** — si el comprobante tiene impuesto | ERP | decimal 18/5 |
| `economicActivityCode` | `CodigoActividad` | Opcional — no usar si hay proporcionalidad | ERP | `maxLength 6` |
| `taxCondition` | `CondicionImpuesto` | Opcional | ERP | enum `01`–`05` |
| `creditableTaxAmount` | `MontoTotalImpuestoAcreditar` | **Condicional** — no si `taxCondition=05` ni si `message=3` | ERP | decimal 18/5 |
| `applicableExpenseAmount` | `MontoTotalDeGastoAplicable` | **Condicional** — mismas exclusiones | ERP | decimal 18/5 |
| `invoiceTotal` | `TotalFactura` | **Obligatorio** | ERP | decimal 18/5 |
| `consecutiveReceptor` | `NumeroConsecutivoReceptor` | **Obligatorio** | ERP | 20 díg (`\d{20}`); tipo `05/06/07` en pos. 9-10 según `message` |
| `emissionDate` | `FechaEmisionDoc` | **Obligatorio** | ERP | `xs:dateTime`. Ver ⚠️ conflicto abajo |
| `supplierEmail` | — (no va en el MR) | **Obligatorio** para la entrega | ERP | correo del proveedor al que se entrega el acuse |
| — | `NumeroCedulaReceptor` | Obligatorio | **DetCore deriva del `X-Issuer-Id`** | `\d{9,12}` |
| — | `ds:Signature` | Obligatorio | **DetCore firma** (Vault, PKCS#1 v1.5, XAdES-EPES, `ClaimedRole=Receptor`) | — |

**✅ `FechaEmisionDoc` — resuelto: es la fecha de la confirmación (el MR), no la de la factura original.**
El XSD lo dice explícito (`MensajeReceptor_V4.4.xsd:33`: *"Fecha de emision de la confirmación"*) — contrato
vinculante. El `README.md:400` decía "fecha de la factura original"; **corregido (2026-07-13)**. El código
ya es correcto: fija `FechaEmisionDoc` al instante de la confirmación (`now`) en ambos flujos
(`ProcessReceivedDocumentHandler` F14 y `ConfirmReceivedDocumentHandler` F13, vía `ReceptionConfirmation.Create(…, now)`).
La `FechaEmision` del comprobante recibido (`ParsedReceivedComprobante.IssueDate`) alimenta **solo el display
del portal** (`GetReceivedDocumentQuery`), nunca el MR.

### 2.1 Sample — aceptación (1)

```json
{
  "clave": "50601071500310170293400100001010000000123199999999",
  "supplierTaxId": "3101123456",
  "message": 1,
  "totalTaxAmount": "13000.00000",
  "invoiceTotal": "113000.00000",
  "taxCondition": "01",
  "creditableTaxAmount": "13000.00000",
  "applicableExpenseAmount": "100000.00000",
  "economicActivityCode": "620100",
  "consecutiveReceptor": "00100001050000000001",
  "emissionDate": "2026-07-05T09:15:00-06:00",
  "supplierEmail": "facturacion@proveedor.cr"
}
```

### 2.2 Sample — rechazo (3)

`messageDetail` obligatorio; se omiten `creditableTaxAmount` / `applicableExpenseAmount`.

```json
{
  "clave": "50601071500310170293400100001010000000123199999999",
  "supplierTaxId": "3101123456",
  "message": 3,
  "messageDetail": "Mercaderia no recibida; se rechaza la totalidad del comprobante.",
  "totalTaxAmount": "13000.00000",
  "invoiceTotal": "113000.00000",
  "consecutiveReceptor": "00100001070000000002",
  "emissionDate": "2026-07-05T09:20:00-06:00",
  "supplierEmail": "facturacion@proveedor.cr"
}
```

---

## 3. Cómo encaja en DetCore

### 3.1 Reutilizable tal cual

| Componente | Reutilización |
|---|---|
| `HaciendaApiClient` → `POST /recepcion` + `GET /recepcion/{clave}` | Mismo endpoint. **Pero** hoy un guard excluye el namespace del MR (`HaciendaApiClient.cs:33-35`, `TransmittableNamespaces` no lo incluye) — hay que levantarlo conscientemente. |
| `HaciendaTokenProvider` / OIDC ROPC / `HaciendaTransmitterOptions` / resolver de credenciales | Mismo IdP/realm/client. |
| `ISigningVault` + Vault transit PKCS#1 v1.5 XAdES-EPES | Mismo estándar. Delta: `xades:ClaimedRole='Receptor'`. |
| `PendingResponsePollerService` + parser de `MensajeHacienda` | El MR obtiene su propia clave y Hacienda responde con el **mismo sobre**. |
| Idempotencia por clave (409/duplicado) | Aplica igual. |
| `MensajeReceptor_V4.4.xsd` (ya en el repo, catalogado en `CrSchemaCatalog`) | Contrato para validar la salida XML. |
| Maquinaria `EmailDelivery` (SMTP + reintentos + estado) | Para la entrega del acuse al proveedor (§B). |

### 3.2 Nuevo

| Componente | Por qué |
|---|---|
| Schema canónico de confirmación (JSON-in) | El canónico actual es de emisión (`InvoiceDocument`). No hay slot para un "confirmation intent". |
| Validador + transformer del MR | Emite el XML del MR en orden XSD (namespace `.../v4.4/mensajeReceptor`), aplica la condicionalidad. El generador de emisión no cubre la forma disjunta del MR. |
| Agregado persistido de "confirmación recibida" | Traza clave del MR / message / estado / respuesta de Hacienda / consecutivo. |
| Command + endpoint (`ConfirmReceivedDocumentCommand`) | Nueva superficie de recepción; hoy la ingesta es solo emisión. |
| Delta de firma `ClaimedRole='Receptor'` | Aditivo al signer. |
| Levantar guards | `HaciendaApiClient.cs:35` (namespace MR excluido) y `CrDocumentTypes.All` (no incluye `MR`). |

### 3.3 Pipeline

Es un **pipeline paralelo más corto** que el de emisión (omite Represent — un acuse no lleva PDF):

```
Validate(MR) → Transform(MR) → Sign(ClaimedRole=Receptor) → Transmit(/recepcion) → poll → Deliver(acuse→proveedor)
```

Reutiliza `Sign` / `Transmit` / `poll` / `EmailDelivery`; aporta `Validate` / `Transform` propios.
Con el registro por **keyed services**, lo natural es que `CostaRicaProvider` exponga una capacidad MR
adicional, no forzar el MR por el `ICountryProvider` de emisión. El disparo de la entrega del acuse
debe engancharse **tanto en el worker como en el poller** (lección del flujo async de CR: los efectos
post-aceptación viven en ambos).

---

## 4. Preguntas abiertas contra la norma (a resolver antes o durante la implementación)

- **Obligatoriedad y plazos:** confirmar contra el Decreto 44739-H / resolución vigente (no están en las
  fuentes del repo). Mientras tanto, DetCore solo relaya.
- ~~**`FechaEmisionDoc`:** resolver el conflicto XSD (fecha de confirmación) vs. README (fecha factura
  original).~~ ✅ **Resuelto (2026-07-13):** es la fecha de la confirmación (anotación del XSD); README
  corregido y código correcto (ver §2).
- **`DetalleMensaje` mín. 5 caracteres:** el PDF lo menciona, el XSD no. ¿Se valida como regla de
  negocio o solo el `maxLength 160`?
- **Migración TRIBU-CR** (`README.md:564`): confirmar que las URLs/credenciales de `/recepcion` siguen
  vigentes post-Oct-2025 antes de construir.
- **Certificado firmante:** confirmar que el modelo per-issuer cubre el rol de receptor (mismo cert que
  el issuer usa para emitir).

## Referencias

- `src/DetCore.Countries.CostaRica/Schemas/MensajeReceptor_V4.4.xsd` — contrato del MR.
- `docs/paises/costa-rica/esquemas/MensajeHacienda_V4.4.xsd:140-158` — respuesta de Hacienda (sin "parcial").
- `docs/paises/costa-rica/README.md:264-269` (endpoints), `:370-421` (§9 MR).
- `docs/paises/costa-rica/normativa/ANEXOS_Y_ESTRUCTURAS_V4.4.pdf` — pp. 60-65, 75, 80, 83-84, 96-97.
- `src/DetCore.Countries.CostaRica/Transmission/HaciendaApiClient.cs:33-44` — guard que hoy excluye el MR.
