# Casos de emisión — lo que el XML tiene que saber hacer

**Fecha:** 2026-09-19 (§6 al día el 2026-09-20) · **Fuente primaria:** `normativa/ANEXOS_Y_ESTRUCTURAS_V4.4.pdf` (98 pp.) y los
23 XML de `XML-Ejemplos/` y `normativa/protocolos/` · **Para:** quien implemente F7 en VentaSys.

Este documento es el tercero de la carpeta y no repite a los otros dos:

| Documento | Qué guarda |
|---|---|
| [`README.md`](README.md) | El marco: versiones, clave numérica, firma XAdES, API REST, flujo asíncrono. |
| [`protocolos-especiales-matriz.md`](protocolos-especiales-matriz.md) | Qué exige cada gran comprador. **Escrito contra DetCore**, no contra VentaSys. |
| **este** | **Los casos**: qué situación de venta produce qué XML, con la regla citada y el ejemplo que la demuestra. Incluye los 25 protocolos de comprador de SWS con sus códigos (§5). |

Todo lo que sigue está contrastado contra el anexo o contra un XML real. Donde no, lo dice.

---

## 1. La regla que más cara sale: servicios médicos pagados con tarjeta

Es la que hay que implementar **antes** de emitir la primera factura de una clínica, porque no
degrada: Hacienda rechaza el comprobante.

> **`TotalIVADevuelto`** (ResumenFactura) — *«Este campo será de condición obligatoria cuando se
> facturen **servicios de salud** y cuyo método de pago sea **"Tarjeta"**. Se obtiene de la sumatoria
> del Monto de los Impuestos pagado por los servicios de salud en tarjetas. **Validación:** Se
> verificará que el monto indicado corresponda a líneas de detalle con códigos CABYS de servicios
> médicos y el medio de pago sea tarjeta. **Caso contrario se rechazará el comprobante.»**
> — Anexo p. 54

Lo que eso obliga a tener en el POS, y hoy no existe:

1. **Saber qué CABYS es «servicio médico».** La validación de Hacienda cruza el CABYS de la línea
   contra su propia lista. El POS tiene el CABYS por producto desde F5 pero no sabe cuáles son de
   salud.
2. **Saber que se pagó con tarjeta**, y con cuánto. VentaSys ya guarda `payment_method` por venta
   (`Tarjeta de crédito`, etc.), así que el dato está; lo que falta es traducirlo al código `02` y,
   cuando hay pago mixto, **prorratear**: el campo es «el impuesto pagado **en tarjeta**», no el
   impuesto de las líneas de salud.
3. Aplica a **FE, TE, NC y ND**. No a FEE, FEC ni REP.

La tarifa de esos servicios es la **reducida del 4 %** (`CodigoTarifaIVA=04`), confirmada en los tres
XML de emisores de salud de `protocolos/` (actividades 8690.9 y 8620.1, CABYS 93101…).

> **Ojo con el nombre.** «IVA devuelto» no es un descuento ni una exoneración: el cliente paga el 4 %
> y el Estado se lo devuelve después por el canal de la tarjeta. En el XML el impuesto **se cobra**;
> el campo solo lo declara. Tratarlo como exoneración da un total distinto.

---

## 2. Exoneraciones: son **puntos de tarifa**, no una tarifa

La pregunta «¿y si se le exonera un 9 % de IVA?» tiene una respuesta que conviene fijar, porque el
modelo obvio es el equivocado: **no hay ninguna tarifa del 9 %** en el catálogo. Un 9 % exonerado es
una línea al 13 % con nueve puntos perdonados.

> **`TarifaExonerada`** — *«Debe de indicarse **los puntos de la tarifa** otorgado de exoneración.
> Debe expresarse el porcentaje como número entero (Ejemplo: la tarifa del 13 % se debe reflejar
> como 13, la tarifa del 1 % como 1, o bien la tarifa del 0.5 % como 0.5).»* — Anexo p. 45
>
> **`MontoExoneracion`** = `TarifaExonerada` × `SubTotal` (o `BaseImponible` si la hay) — p. 46
> **`ImpuestoNeto`** = `Monto` − `MontoExoneracion` — p. 46
> **`MontoTotalLinea`** = `SubTotal` + `ImpuestoNeto` — p. 47

El 9 %, trabajado sobre una base de ₡100 000:

| Campo | Valor | De dónde sale |
|---|---:|---|
| `CodigoTarifaIVA` | `08` | la tarifa general: 13 % |
| `Tarifa` | `13.00` | |
| `Monto` | `13 000.00` | 13 % de la base |
| `TarifaExonerada` | `9` | **los puntos perdonados**, no la tarifa resultante |
| `MontoExoneracion` | `9 000.00` | 9 % de la base |
| `ImpuestoNeto` | `4 000.00` | 13 000 − 9 000 |
| `MontoTotalLinea` | `104 000.00` | 100 000 + 4 000 |

Y en el `ResumenFactura` la línea **no va al balde de gravado**: va a `TotalServExonerado` /
`TotalMercanciasExoneradas` → `TotalExonerado`. El ejemplo
`50605022600310115499800100001010000516363…xml` lo muestra con la exoneración completa (4 de 4
puntos): `TotalGravado = 0`, `TotalExonerado = 187 884.62`, `TotalImpuesto = 0`.

### Catálogo de tipo de documento de exoneración (nota 10.1, p. 74)

| Código | Tipo | Nota |
|---|---|---|
| 01 | Compras autorizadas por la DGT | **solo NC/ND** |
| 02 | Ventas exentas a diplomáticos | exige `Articulo`; en `NumeroDocumento` va el número de ley |
| 03 | Autorizado por ley especial | ídem |
| 04 | Exenciones DGH — autorización local genérica | **Hacienda valida el número y su vigencia** |
| 05 | Transitorio V (ingeniería, arquitectura, topografía, obra civil) | solo NC/ND |
| 06 | Servicios turísticos inscritos ante el ICT | solo NC/ND; exige `Articulo` |
| 07 | Transitorio XVII (reciclaje) | solo NC/ND; exige `Articulo` |
| **08** | **Exoneración a Zona Franca** | exige `Articulo`; en `NumeroDocumento` va la ley (ej. «LEY 7210 REGIMEN DE ZONAS FRANCAS») |
| 09 | Servicios complementarios para la exportación (art. 11 RLIVA) | |
| 10 | Órgano de las corporaciones municipales | |
| 11 | Exenciones DGH — autorización de impuesto local concreta | **Hacienda valida número, vigencia y que la tarifa exonerada no exceda la autorizada** |
| 99 | Otros | exige `NombreInstitucionOtros` |

Dos validaciones que el anexo declara y que conviene replicar **antes** de transmitir, porque el
rechazo llega minutos después y con el cliente ya ido:

- Con los códigos **04 y 11**, Hacienda comprueba que el número de autorización exista y esté
  vigente, y que la **tarifa exonerada no sea mayor** que la autorizada.
- `Articulo` es obligatorio con **02, 03, 06, 07 y 08**; e `Inciso` lo es en cuanto el artículo
  remita a uno.

---

## 2 bis. La aritmética del resumen: cuatro reglas que el XSD no valida

**Un comprobante puede ser válido contra el esquema y estar mal.** El XSD comprueba la forma; las
cuentas las comprueba Hacienda contra sí mismas, y ahí es donde un XML bien armado se rechaza sin
decir por qué. Las cuatro salieron de las pp. 45-47 y 50-55 del anexo y de comparar contra dos
comprobantes aceptados de `XML-Ejemplos/`.

### a) Los baldes van **antes** del descuento (pp. 51-52)

> «Este campo se obtiene de la sumatoria de los campos de **Monto Total** de cada línea de detalle
> que contenga IVA»

No del subtotal. Lo enseñan dos comprobantes reales:

| Campo | `…0500083123103142.xml` | `…0004940100004940.xml` |
|---|---:|---:|
| `MontoTotal` | 100 000 | 10 800 |
| `MontoDescuento` | 2 500 | 1 080 |
| `SubTotal` | 97 500 | 9 720 |
| **`TotalGravado`** | **100 000** | **10 800** |
| `TotalVenta` | 100 000 | 10 800 |
| `TotalDescuentos` | 2 500 | 1 080 |
| `TotalVentaNeta` | 97 500 | 9 720 |

Llenarlos con el subtotal —que es lo que uno escribe primero— da `TotalGravado` 97 500 y un resumen
que no cuadra contra su propio `TotalVenta`.

### b) Una exoneración **parcial reparte** la línea (pp. 50-52)

> «En el caso que exista una exoneración, este campo se obtiene de la multiplicación
> (1 − porcentaje de exoneración) por el monto total de la venta […] Porcentaje de exoneración:
> (Suma de los montos exonerados / Suma de los montos de impuesto)»

Con 100 000 al 13 % y nueve puntos exonerados, la proporción es 9 000 / 13 000 = 0.6923:

* `TotalMercExonerada` = 69 230.76923
* `TotalMercanciasGravadas` = 30 769.23077

Mandar la línea entera al balde exonerado —que es lo que parece razonable— descuadra el resumen. La
factura de servicios médicos de `normativa/protocolos/` es el caso límite: exonerada al 100 %, y ahí
sí va entera.

### c) `TotalComprobante` **resta** el IVA devuelto (p. 55)

> «se obtiene de la suma de los campos "total venta neta", "monto total del impuesto" y "total otros
> cargos" **menos "total IVA devuelto"**»

Es el único término que resta y el que se olvida. Una consulta médica de 100 000 con 4 % de IVA
pagada con tarjeta totaliza **100 000**, no 104 000.

### d) Con **dos o más** medios de pago, la suma tiene que dar el total (p. 55)

> «Se verificará que el cálculo coincida con la sumatoria de los montos de los totales por "Medio de
> Pago" cuando se utilicen dos o más. Caso contrario se rechazará el comprobante.»

Con uno solo no lo comprueba —el monto es hasta opcional—, así que una guarda que exija la igualdad
siempre inventaría una regla que Hacienda no tiene.

### Y dos más, del desglose

* **`TotalDesgloseImpuesto` va aunque sume cero, si la línea estuvo gravada.** La factura exonerada
  real lo trae en cero; la de exportación exenta no lo trae. La diferencia no es el monto: es si
  hubo impuesto que perdonar.
* **El servicio o la mercancía los decide el CABYS**, no un campo aparte: los códigos que empiezan
  con 5 a 9 son servicios y los de 0 a 4 mercancías (la validación de cada balde lo repite).

---

## 3. Los catálogos, completos

Transcritos del anexo. Son los que el POS tiene que ofrecer en una pantalla o deducir de la venta;
ninguno existe hoy en el código.

### Condición de venta (nota 5, p. 69)

| Cód. | Condición | Lo que arrastra |
|---|---|---|
| 01 | Contado | exige `MedioPago` |
| 02 | Crédito | exige `PlazoCredito` > 0; **no** lleva `MedioPago` |
| 03 | Consignación | |
| 04 | Apartado | |
| 05 | Arrendamiento con opción de compra | |
| 06 | Arrendamiento en función financiera | |
| 07 | Cobro a favor de un tercero | |
| **08** | **Servicios prestados al Estado** | cuando el pago no es inmediato; **no** lleva `MedioPago` |
| **09** | **Pago de servicios prestados al Estado** | **solo en REP**, y solo para cancelar una FE con condición 08 |
| **10** | **Venta a crédito en IVA hasta 90 días (art. 27 LIVA)** | exige `PlazoCredito`; **no** lleva `MedioPago` |
| **11** | **Pago de venta a crédito IVA 90 días** | **solo en REP**, y solo para cancelar una FE con condición 10 |
| 12 | Venta de mercancía no nacionalizada | |
| 13 | Venta de bienes usados a no contribuyente | **solo FEC** |
| 14 | Arrendamiento operativo | |
| 15 | Arrendamiento financiero | |
| 99 | Otros | exige `CondicionVentaOtros` (5–100 car.) |

> **Los pares 08/09 y 10/11 son el mecanismo del REP.** La factura se emite con 08 o 10 y el IVA
> queda diferido; cuando entra la plata se emite un REP con 09 u 11. Y cualquier corrección va
> **contra la factura original**, no contra el REP.

### Medio de pago (nota 6, p. 70)

| Cód. | Medio |
|---|---|
| 01 | Efectivo |
| **02** | **Tarjeta** ← el que dispara `TotalIVADevuelto` |
| 03 | Cheque |
| 04 | Transferencia / depósito bancario |
| 05 | Recaudado por terceros |
| 06 | SINPE Móvil |
| 07 | Plataforma digital |
| 99 | Otros (exige detalle) |

`MedioPago` admite **hasta 4** y es obligatorio **salvo** con condición de venta 02, 08 o 10 (p. 55).
VentaSys hoy guarda un solo método por venta, con nombres propios (`Efectivo`, `Tarjeta de crédito`,
`Transferencia bancaria`, `Pago móvil`): hay que mapearlos, y el pago mixto no está modelado.

### Código de impuesto (nota 8, p. 70)

01 IVA · 02 Selectivo de consumo · 03 Único a los combustibles · 04 Específico de bebidas
alcohólicas · 05 Específico de bebidas envasadas sin alcohol y jabones · 06 Tabaco ·
**07 IVA (cálculo especial)** · 08 IVA régimen de bienes usados (factor) · 12 Específico al cemento ·
99 Otros.

### Tarifa del IVA (nota 8.1, p. 71)

| Cód. | Tarifa | Cuándo |
|---|---|---|
| 01 | 0 % | art. 32 num. 1 RLIVA, **con derecho a crédito pleno** — «por ejemplo ventas a la CCSS o a municipalidades» |
| 02 | 1 % | |
| 03 | 2 % | el caso de la UCR |
| 04 | 4 % | **servicios de salud privados** |
| 05 / 06 / 07 | transitorios 0 % / 4 % / 8 % | **solo NC y ND** |
| 08 | 13 % | la general |
| 09 | 0.5 % | |
| 10 | Exenta | Ley 9635 art. 8; es la de exportación (FEE) |
| 11 | 0 % **sin** derecho a crédito | no sujeto que no da crédito |

> **No existe el 9 %.** Ver §2.
>
> **Corrección a la matriz:** ahí se dice que la venta a la CCSS es «no sujeción». La nota 28 del
> anexo dice otra cosa: es **tarifa 01, 0 % con derecho a crédito pleno**, y nombra a la CCSS
> textualmente. La diferencia importa porque 01 y 11 se parecen y dan derechos opuestos.

### Códigos de referencia (nota 9, p. 72) y tipo de documento de referencia (nota 10, p. 73)

Referencia: 01 anula · 02 corrige monto · 04 referencia a otro documento · 05 sustituye provisional
por contingencia · 06 devolución de mercancía · 07 sustituye comprobante electrónico · 08 factura
endosada · 09 NC financiera · 10 ND financiera · 11 proveedor no domiciliado · **12 crédito por
exoneración posterior a la facturación** · 99 otros. *(El 03 no está en el catálogo.)*

Tipo de documento: 01 FE · 02 ND · 03 NC · 04 TE · 05 nota de despacho · 06 contrato ·
07 procedimiento · 08 comprobante de contingencia · 09 devolución de mercadería · 10 rechazado por
Hacienda · 11 sustituye factura rechazada por el receptor · 12 sustituye factura de exportación ·
**13 facturación mes vencido** · 14 régimen especial · 15 sustituye una FEC · 16 proveedor no
domiciliado (solo FEC) · 17 NC a FEC · 18 ND a FEC · 99 otros.

### Tipo de código comercial (nota 12, p. 75)

01 del vendedor · 02 del comprador · **03 del fabricante — SKU/GTIN de la industria** · 04 uso
interno · 99 otros. Hasta 5 por línea.

### Unidad de medida (nota 15, pp. 76 ss.)

El catálogo vive ahí y **es el que le falta a T-620**. No son solo unidades del SI: incluye `Os`
(otro tipo de servicio), `Al` (alquiler habitacional), `Alc` (alquiler comercial), `Acv` (activo
virtual), `Sp`, `Unid`. El XML de servicios médicos usa `Os` con
`UnidadMedidaComercial = "Otro tipo Servicio"`.

---

## 4. Qué demuestra cada ejemplo

23 archivos. Los de `XML-Ejemplos/` son del proveedor de sistemas 3101702934 y recorren los tipos de
documento; los de `protocolos/` son facturas reales a compradores grandes.

### Por tipo de documento (`XML-Ejemplos/`)

| Archivo (cola) | Tipo | Qué prueba |
|---|---|---|
| …0000099501150191589 | FE | la mínima: 1 línea, tarifa 08, contado, medio 01 |
| …0000000004158429681 | **FEE** | exportación: **USD**, `TipoCambio`, tarifa **10** (exenta), condición 02 |
| …0000500153170510022 | NC | nota de crédito con `InformacionReferencia` |
| …4305109281159873549 | NC | **Walmart**: `TipoNota=NCCLAIM` + `WMNumeroReclamo` |
| …1784596161176325178 / …62167800510 | NC | `NumeroProveedor` + `NumerodeAviso` |
| …1784595311187680807 | TE | `OtroTexto` sin código: «Agrupamiento FEBN-0001-0225.» |
| …1784595520149160302 | TE | **BCCR**: `BCCR_CUENTA_CLIENTE`, `BCCR_ORDEN_PEDIDO`, `BCCR_CODIGO_FACTURA`, `BCCR_PERIODO` |
| …1784595522183274674 | TE | `OrdenCompra` + `NumeroRecepcion` + observación libre |
| …0000500176110774932 | ND | nota de débito con referencia y `CodigoActividadReceptor` |
| …0000900062144311739 | **FEC** | factura de compra: emisor y receptor con actividad |
| …0000500100113703685 | **REP** | recibo de pago: **condición 11**, sin CABYS, con referencia |

### Por protocolo de comprador (`normativa/protocolos/`)

| Emisor (actividad) | Receptor | Tarifa | `Otros` | Caso |
|---|---|---|---|---|
| 8690.9 salud | 4711.1 supermercados | **04** | `NumeroVendedor`, `NumeroOrden`, `EnviarGLN`, `FechaOrden`, `NumeroRecepcion` | **servicios médicos** a cadena, protocolo tipo Walmart |
| 8690.9 salud | 4669.9 | **04** | `PO:` | servicios médicos, orden de compra |
| 8690.9 salud | 7020.0 | **04** | `OC`, `NoRecepcion` | **salud + exoneración Zona Franca (08)** |
| 8620.1 consulta médica | 4630.9 | **04** | `NumeroPedido` | servicios médicos |
| 8549.0 enseñanza | **6419.0 banca** | **03** (2 %) | texto libre «CODIGO DE AGRUPAMIENTO: FEBN…» | **BNCR**: agrupamiento |
| 2396.0 concreto | 4752.1 | **02** (1 %) | `OrdenCompra` | tarifa reducida 1 % |
| 2220.9 plástico | 3510.0 electricidad | 08 | — | USD con 2 líneas y referencia |
| 4669.9 | 2022.0 | 08 | — | 2 líneas, CRC |
| 2220.9 | — | 08 | `OrdenCompra` | USD |

**Todos** los de `protocolos/` van con condición **02 (crédito)** y por eso **ninguno lleva
`MedioPago`**. Es la confirmación práctica de la regla de la p. 55.

---

## 5. Los 25 protocolos de SWS, con sus códigos

`normativa/protocolos/SWS-Procolols_XML.docx` es el catálogo interno de SWS y trae **los códigos
exactos**, que es justo lo que la matriz marca una y otra vez como *unknown — private*. Con esto se
cierra la pregunta del BCCR: **`009` no es un `codigo` del XML, es el número de protocolo de SWS
para el Banco Central**. Lo que va en el XML son códigos con nombre.

| # | Comprador | Dónde | `codigo` → dato |
|---|---|---|---|
| 001 | **Walmart** | Otros | `WMNumeroVendedor`, `WMNumeroOrden`, `WMEnviarGLN`, `WMFechaOrden`, `WMNumeroRecepcion`. En NC/ND: `WMNumeroVendedor`, `WMNumeroReclamos`, `WMEnviarGLN`, `WMFechaReclamo` |
| 002 | Automercado | Otros | `NumeroProveedor`, `NumeroOrden`, `EnviarGLN`, `NumeroRecepcion`, `FechaRecepcion`. En NC/ND: `NumeroProveedor`, `NumerodeAviso` |
| 003 | Gessa | Otros | **`retail:Complemento` anidado** — ver el aviso de abajo |
| 004 | CMI | Otros | `NumeroProveedor`, `NumeroOrden`, `NumeroRecepcion`, `FechaRecepcion`. NC/ND: `NumeroProveedor`, `NumerodeAviso` |
| 005 / 105 | PriceSmart (mercancías / servicios) | Otros | **`retail:Complemento` anidado** — ver el aviso |
| 006 | Sigma y Grupo Q | Otros | `OC` |
| 007 / 107 / 207 / 307 | Femsa · El Colono · Bilco · Active Motors | Otros | `OrdenCompra` |
| 008 | Unilever | Otros | `PurchaseOrderNumber` |
| **009** | **Banco Central de Costa Rica** | Otros | `BCCR_CUENTA_CLIENTE`, `BCCR_ORDEN_PEDIDO`, `BCCR_CODIGO_FACTURA` |
| 010 | La Nación | Otros | `EC` (correo), `OC`, `AG` |
| 011 | ICE — Factura Financiera | **Referencia** | `Razon` = «Venta al Ice - Factura Financiera»; `Numero` = código de proveedor del ICE |
| 012 | ICE — Cadena de Abastecimiento | **Referencia** | `Razon` = «Venta al Ice - Cadena de Abastecimiento»; `Numero` = orden de compra |
| 013 | ICE — Fondos de Trabajo | **Referencia** | `Razon` = «Venta al Ice - Fondos de Trabajo»; `Numero` = orden de compra |
| 014 | Grupo Pelón | Otros | igual que Walmart |
| **015** | **Banco Nacional de Costa Rica** | Otros | **un `OtroTexto` sin atributo**, con el texto `Agrupamiento <código de proveedor>` |
| 016 | Nutresa | Otros | `NumeroPedido` |
| 017 | Millicom — Tigo | Otros | `OC`, `GRN` |
| 018 | Kimberly Clark | Otros | `OC`, `NoRecepcion` |
| 019 | Grupo Numar | Otros | `NumeroOrden` |
| 020 | Sur Química | **Referencia** | `Numero` = `PCo_<orden de compra>`; `Razon` = «Venta a SUR Química» |
| 020/021 | Grupo DHL | Otros | `Shipment` = número de envío |

Los cuatro de **referencia** (ICE ×3 y Sur Química) usan todos `TipoDoc=99` y `Codigo=99`: no son
documentos fiscales de referencia sino el hueco de texto libre que da el catálogo. Los demás van en
`Otros`.

Lo que cada protocolo exige tener capturado antes de facturar es la otra mitad, y es trabajo de
pantalla: **código de proveedor por cliente**, **GLN por cliente**, **orden de compra y su fecha por
documento**, **número y fecha de recepción**. Sin eso el protocolo no se puede armar.

### Tres avisos sobre ese documento

**1. Gessa y PriceSmart, como están escritos, ya no son válidos.** Los tres protocolos meten un
`retail:Complemento` **como hijo de `OtroContenido`**, y en el XSD 4.4 `OtroContenido` es
`simpleContent`: extiende `restrictedString` y solo admite el atributo `codigo`. No admite
elementos hijos. La matriz registra la prueba en vivo contra el sandbox de Hacienda el 2026-07-20:
rechazado con `cvc-complex-type.2.2: Element 'OtroContenido' must have no element [children]`. Esos
complementos tienen que llegarle al comprador **por fuera** del XML fiscal (ekomercio B2B), no
adentro.

**2. El documento es de la época de 4.3 y los nombres cambiaron.** Los cuatro protocolos de
referencia escriben `TipoDoc` y `FechaEmision`; en 4.4 el XSD pide **`TipoDocIR`** y
**`FechaEmisionIR`**. `Numero`, `Codigo` y `Razon` siguen igual. Copiar el código tal cual produce un
XML que no valida.

**3. El 020 está usado dos veces**: la tabla del encabezado dice «020 Sur Química / 021 DHL», y el
cuerpo titula «020 – Grupo DHL». Hay que resolverlo antes de convertir esa tabla en datos.

---

## 6. Qué de esto tiene VentaSys

Al escribirse este documento (2026-09-19) no había nada del XML. Al día siguiente se hizo la mayor
parte; esta lista queda como el mapa, con lo hecho marcado.

1. ✅ **Los catálogos como dominio**, con sus reglas cruzadas: `fe_tax_codes.py` (nota 8.1),
   `fe_exemptions.py` (notas 10.1 y 23), `fe_payment_methods.py` (nota 6), y las cruzadas
   —condición de venta → `MedioPago` / `PlazoCredito`— en `fe_xml.py`.
2. ✅ **La tarifa por línea**: `products.tax_code`, congelado en `sale_details.tax_code` (T-715).
3. 🟡 **`TotalIVADevuelto`**: la regla y el prorrateo están en `fe_vat_refund.py` con el grupo
   CABYS `931` (T-718); falta que el armador de la venta la llame.
4. ✅ **Exoneración por cliente**, con su documento, artículo, inciso y puntos (T-717).
5. 🟡 **Medios de pago múltiples**: el armador ya los emite y comprueba la suma, y el mapeo desde
   `payment_method` está hecho; falta que una venta pueda guardar más de uno (T-716).
6. ⬜ **Unidad de medida** por producto, del catálogo de la nota 15: es T-620, y el catálogo es este.
7. 🟡 **FEE, FEC y REP**: los siete tipos se arman y validan contra su XSD (T-720); falta su
   consecutivo y desde dónde se emiten.
8. 🟡 **`Otros` y `InformacionReferencia` como datos por cliente**: el armador de protocolos está en
   `fe_protocols.py` y expresa los 25 de §5 como datos (T-719). Falta capturar lo que alimentan:
   código de proveedor y GLN por cliente, orden de compra con su fecha y número de recepción por
   documento. El POS **nunca los inventa** — se copian tal cual, y lo que falta se reporta.

## 7. Lo que queda por confirmar

- **Qué CABYS cuentan como «servicios médicos»** para la validación de `TotalIVADevuelto`. El anexo
  dice que Hacienda lo valida pero no publica la lista en este PDF. Los ejemplos usan `93101…`.
- **El prorrateo del IVA devuelto con pago mixto** (mitad tarjeta, mitad efectivo): el anexo dice
  «el impuesto pagado en tarjetas» y no da la fórmula.
- **El 020 duplicado** entre Sur Química y DHL en el catálogo de SWS (§5, aviso 3).
- **Por dónde van los complementos de Gessa y PriceSmart** ahora que no caben en el XML (§5,
  aviso 1). Es una decisión comercial, no técnica: hay que preguntarle al comprador.
- Si **TRIBU-CR** cambia URLs o credenciales (ya anotado en el README §12).
