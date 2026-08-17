# VentaSys — Especificación

> **Qué es este documento.** Define *qué* es VentaSys y *por qué*, no cómo se
> construye. El cómo está en [plan.md](plan.md) y el trabajo concreto en
> [task.md](task.md).
>
> Actualizado: 2026-08-16 · Estado: vigente

---

## 1. Qué es

VentaSys es un **punto de venta que se vende por suscripción**, no un sistema
instalado para un negocio. Un mismo despliegue atiende a muchos negocios a la
vez, cada uno con su catálogo, su caja, sus usuarios y sus facturas, sin verse
entre sí.

Nació como migración de un POS en C#/WinForms para un abarrotes. Ese origen dejó
supuestos que hoy estorban y que esta especificación desarma: un solo negocio,
una sola moneda, un solo impuesto, categorías planas.

**Verticales que debe cubrir sin cambios de código:** abarrotes y supermercados,
repuestos, ferreterías, tiendas de ropa, farmacias. La diferencia entre ellos no
está en la lógica de venta sino en **cómo organizan su catálogo** y **qué
impuesto lleva cada producto**.

---

## 2. Modelo de negocio

Suscripción mensual por compañía. El sistema **no cobra**: sabe si una compañía
está al día y actúa en consecuencia. El cobro se hace por fuera (SINPE,
transferencia, factura).

### Afiliado y compañía

La identidad de un cliente es el par **(afiliado, compañía)**. Ambos son números.

```
afiliado 1 · compañía 1  →  Anónimos S.A.
afiliado 1 · compañía 2  →  Anónimos Sucursal Norte S.A.   (mismo dueño, otra cédula)
afiliado 2 · compañía 1  →  Repuestos Yamaha CR
```

Un afiliado agrupa compañías que pertenecen al mismo cliente comercial. En el
caso simple —el que va a ser la mayoría— un afiliado tiene una sola compañía y
el par se lee como un número de cliente.

**Todos comparten una misma base de datos.** El aislamiento es lógico, por
`company_id`, y se aplica en el servidor (ver [plan.md §3](plan.md)).

### Estados de suscripción

| Estado | Qué puede hacer la compañía |
|---|---|
| `prueba` | Todo. Con aviso del día en que vence. |
| `activa` | Todo. |
| `vencida` | **Gracia de 7 días**: todo, con aviso rojo permanente. Pasados los 7, solo lectura: se puede consultar y cerrar la caja abierta, no se puede vender. |
| `suspendida` | Solo entra el administrador, y solo ve el aviso de pago. |
| `cancelada` | Nadie entra. Los datos se conservan 90 días. |

**RN-1.** Una caja abierta siempre se puede cerrar, en cualquier estado. Dejar
efectivo contado sin poder cuadrarlo es peor que perder una venta.

**RN-2.** El bloqueo por vencimiento nunca ocurre a mitad de una venta en curso:
se evalúa al abrir la pantalla de ventas, no al cobrar.

---

## 3. Actores

| Actor | Alcance | Qué hace |
|---|---|---|
| **Soporte** (vos) | Todas las compañías | Da de alta compañías, cambia el estado de la suscripción, entra a una compañía para diagnosticar. Toda acción queda en bitácora. |
| **Administrador** | Su compañía | Configura el negocio, el catálogo, los usuarios, ve reportes, factura. |
| **Cajero** | Su compañía, su terminal | Vende, abre y cierra caja, hace devoluciones. |

**RN-3.** Una persona puede pertenecer a **varias** compañías. El correo
identifica a la persona y sigue siendo único en todo el sistema; lo que se
repite es la **membresía**: una fila por (persona, compañía) con **su propio
rol**. El contador que atiende tres locales entra a los tres con la misma clave,
y puede ser administrador en el suyo y cajero en otro.

**RN-4.** Soporte no tiene compañía. Para ver los datos de una tiene que
*entrar como* esa compañía, y eso queda registrado con fecha, usuario y motivo.

**RN-24.** La compañía se elige **después** de autenticarse, nunca antes. La
lista de compañías de un correo no se le muestra a quien todavía no probó ser
esa persona: es la cartera de clientes del producto.

**RN-25.** Con una sola compañía disponible no se pregunta nada: se entra
directo. Un cajero abre caja todos los días a la misma hora y no puede pagar un
clic diario por una posibilidad que no tiene. La pantalla aparece solo cuando
hay de dónde escoger.

**RN-26.** Entre autenticarse y elegir compañía la sesión **no lee ni escribe
datos de negocio**. Es un estado intermedio, corto y sin permisos: solo sirve
para listar las compañías propias y elegir una.

**RN-27.** Cambiar de compañía sin cerrar sesión **descarta el estado de la
anterior**: ventas en espera, carrito y configuración en memoria. Un producto de
una compañía no puede terminar en la factura de otra.

---

## 4. Alcance

### Entra

- Multiempresa por (afiliado, compañía), con control de suscripción.
- Panel de soporte para dar de alta y administrar compañías.
- Categorías de **dos niveles**: categoría → subcategoría.
- Impuesto **por producto**, tomado del catálogo CABYS.
- Búsqueda de CABYS contra el API de Hacienda, con copia local.
- Certificado (.p12) y PIN del emisor, cifrados.
- Sucursales y terminales, con su numeración.
- Lo ya construido: ventas, caja, devoluciones, inventario y entradas,
  clientes, usuarios, reportes, configuración, tres plantillas de documento.

### No entra (todavía)

- **Emisión de comprobantes electrónicos.** Se prepara el terreno (CABYS,
  tarifas, certificado, numeración, sucursal/terminal) pero no se firma ni se
  transmite. Es una fase aparte, con su propia decisión de fondo (ver
  [plan.md §7](plan.md)).
- Cobro automático de la suscripción con pasarela de pagos.
- Categorías de más de dos niveles.
- Aplicación móvil.
- Múltiples bodegas por compañía.
- Compras y cuentas por pagar.

### Nunca

- Que una compañía vea datos de otra. Es el único requisito cuyo incumplimiento
  termina el negocio.

---

## 5. Dominio

### 5.1 Categorías de dos niveles

Un catálogo plano no sirve para ninguno de los verticales objetivo.

```
Bebidas                 Yamaha
├── Cervezas            ├── Llantas
├── Gaseosas            ├── Focos
└── Jugos               └── Frenos
```

**RN-5.** Exactamente dos niveles. Una subcategoría no puede tener hijas.
**RN-6.** Un producto se asigna a una subcategoría; si la categoría raíz no
tiene hijas, se asigna a la raíz.
**RN-7.** No se borra una categoría con productos ni con hijas: se desactiva.
**RN-8.** Las categorías son de la compañía. Dos compañías pueden tener
«Bebidas» sin relación entre sí.

En la pantalla de ventas: las raíces son pestañas y las subcategorías, fichas
debajo. Es la navegación que ya existe, con un nivel más.

### 5.2 Impuesto por producto

Hoy hay una sola tasa para todo el negocio. Es incorrecto incluso sin factura
electrónica: **un abarrotes vende canasta básica al 1 %** mientras cobra 13 % en
el resto. Verificado contra el catálogo de Hacienda el 2026-08-16:

| Producto | CABYS | Impuesto |
|---|---|---|
| Harina de arroz | 2312000000300 | 13 % |
| Medicamentos uterotónicos | — | 2 % |
| Libros infantiles impresos | — | 0 % |

**RN-9.** Cada producto lleva su tarifa. La tasa de Configuración pasa a ser
**el valor por omisión de un producto nuevo**, no la del sistema.
**RN-10.** El impuesto de una venta es la **suma de los impuestos de sus
líneas**, no el subtotal por una tasa.
**RN-11.** Al asignarle un CABYS a un producto se copia la tarifa del catálogo.
El usuario puede cambiarla —hay exoneraciones y casos especiales— pero se le
avisa que difiere de la oficial.
**RN-12.** Las ventas ya registradas conservan su impuesto tal como se cobró.
Una devolución usa la tasa de su venta, nunca la vigente.

### 5.3 Sucursales y terminales

**RN-13.** Toda compañía nace con «Sucursal 001» y «Terminal 00001».
**RN-14.** Cada venta, turno de caja y entrada de inventario pertenece a una
sucursal y a una terminal. Sin eso no hay arqueo por local ni numeración de
comprobantes.
**RN-15.** Los códigos son los de Hacienda: sucursal de 3 dígitos, terminal de
5. Se definen ahora aunque la emisión venga después, para no migrar el
histórico.

### 5.4 Facturación electrónica (preparación)

> **Material oficial disponible en el repositorio.** En
> `docs/hacienda/costa-rica/` están los 10 esquemas XSD de la versión 4.4
> (factura, tiquete, notas, mensaje de Hacienda, mensaje de receptor, recibo de
> pago y `xmldsig-core`), 9 comprobantes reales de ejemplo, la política de
> seguridad de PIN y llaves criptográficas, y los anexos y estructuras. La
> estructura del XML **no hay que deducirla**: está ahí.

Lo que esta fase deja listo:

- Código CABYS y tarifa por producto (§5.2).
- Certificado `.p12` y PIN por compañía, cifrados en reposo, que **nunca**
  vuelven al navegador.
- Actividad económica del emisor, consultable contra el API de Hacienda.
- Sucursal y terminal (§5.3).
- Datos obligatorios del receptor: tipo y número de identificación, correo.
- Unidad de medida por producto, del catálogo de Hacienda.

**RN-16.** El PIN y el certificado no se muestran, no se registran en bitácora
y no salen del servidor. La pantalla solo dice si hay uno cargado, cuándo se
subió y cuándo vence.
**RN-17.** Mientras no se emita, el documento impreso lo dice en su leyenda.

---

### 5.5 Arquitectura limpia

El sistema se organiza en capas con las dependencias apuntando hacia adentro. No
es una preferencia de estilo: se sigue de lo que el producto tiene que aguantar.

- Se vende a negocios distintos y va a cambiar de proveedor de factura
  electrónica, quizá de base de datos y algún día de framework de interfaz. Lo
  que no puede cambiar son las reglas: cómo se calcula un total, cuándo cuadra
  un arqueo, qué es una devolución válida.
- **RNF-6 exige prueba por función en dominio y casos de uso.** Esa regla solo
  es sostenible si esas capas se pueden ejecutar sin levantar nada. Una regla de
  negocio que necesita una base de datos para probarse ya está mal ubicada.

```
interfaces ──┐
             ├──> application ──> domain
infrastructure┘                   (no importa nada)
```

| Capa | Qué vive ahí |
|---|---|
| **domain** | Entidades, objetos de valor (`Money`, `TaxRate`), reglas puras. No importa nada externo, ni siquiera el reloj. |
| **application** | Casos de uso (`CreateSale`, `CloseCashSession`) y los **puertos** que necesitan (`SaleRepository`, `Clock`, `CabysCatalog`). |
| **infrastructure** | Adaptadores que implementan los puertos: SQLAlchemy, JWT, bcrypt, el cliente de Hacienda, el backend simulado. |
| **interfaces** | Entrada: routers de FastAPI, `load` y `actions` de SvelteKit. Traducen y delegan; no deciden. |

**RN-18.** El dominio no importa nada de fuera. Se comprueba con una búsqueda,
no con revisión de código.
**RN-19.** La hora entra por el puerto `Clock`, nunca con `datetime.now()` dentro
de una regla o un caso de uso. Es el defecto 9 —ventas que desaparecían del
arqueo por segundos de desfase— convertido en restricción estructural.
**RN-20.** Si probar un caso de uso obliga a montar una base, le falta un puerto.

Vale para los dos lados: `backend/app/` y `frontend/src/lib/`. Lo custodia el
agente `architect`.

### 5.6 Idioma

**RN-21.** El **código** va en inglés: identificadores, nombres de archivo,
tablas, columnas, rutas de API. Es lo que ya hacía el código heredado
(`products`, `sales`, `cash_sessions`) y mezclarlo obliga a traducir mentalmente
en cada línea.

**RN-22.** La **interfaz** se traduce: español, inglés y portugués. Ningún
texto que ve una persona se escribe dentro de un componente; todos viven en
catálogos.

El español va en **usted**, no en voseo. La versión anterior de esta regla decía
«español de Costa Rica, con voseo», y eso era una suposición mía sobre el
mercado: en Costa Rica el ustedeo es más común, y además «Cobrá rápido» le suena
extranjero a un usuario mexicano o colombiano. Un solo español en usted sirve a
toda la región y ahorra un catálogo.

**RN-23.** La **documentación y los comentarios** van en español, como el resto
de `.specify/`, `CLAUDE.md` y `progress.json`.

**RN-28.** El idioma tiene dos niveles: la **compañía** fija el suyo al darse de
alta y cada **persona** puede elegir otro para su sesión. Sin el primero, el
administrador de una compañía nueva arranca en el idioma equivocado; sin el
segundo, un negocio costarricense no puede contratar a una cajera nicaragüense
que prefiera otra cosa.

**RN-29.** El idioma del **documento impreso no es el de la pantalla**. La
factura es para el cliente y para Hacienda, no para el cajero: una compañía
costarricense emite en español aunque su cajero use el POS en portugués. Son dos
ajustes distintos y el del documento vive en Configuración.

**RN-30.** El **backend no escribe texto para una persona**. Devuelve un código
y los datos —`{"code": "insufficient_stock", "product": "Arroz", "available": 2}`—
y el POS arma la frase. Hoy produce 68 mensajes en español que el POS muestra
tal cual, y con eso un cajero brasileño vería media aplicación en su idioma y
los errores en español, que es justo cuando más necesita entender.

## 6. Requisitos funcionales

### Multiempresa

- **RF-1** Toda tabla de negocio pertenece a una compañía y toda consulta se
  filtra por ella en el servidor.
- **RF-2** El `company_id` sale de la sesión, nunca de lo que manda el cliente.
- **RF-3** Los identificadores únicos lo son *dentro de* la compañía: código de
  barras, número de factura, nombre de categoría.
- **RF-4** Los datos existentes pasan a ser la compañía (afiliado 1, compañía 1)
  sin pérdida.
- **RF-27** Pantalla de selección de compañía después del login. Lista las
  compañías de la persona con su estado; las bloqueadas se muestran **con el
  motivo**, no se ocultan —quien no puede entrar tiene que saber por qué—. Se
  salta cuando hay una sola disponible (RN-25).
- **RF-28** Cambiar de compañía desde el menú, sin volver a escribir la
  contraseña y sin arrastrar nada de la anterior (RN-27).

### Panel de soporte

- **RF-5** Listar compañías con su afiliado, estado, plan, vencimiento y uso
  (usuarios, terminales, productos, ventas del mes).
- **RF-6** Dar de alta una compañía: datos, plan, administrador inicial. Al
  crearse quedan su sucursal, su terminal y su configuración por omisión.
- **RF-7** Cambiar el estado de la suscripción y la fecha de vencimiento.
- **RF-8** *Entrar como* una compañía, con motivo obligatorio y bitácora.
- **RF-9** Bitácora consultable: quién, qué, cuándo, sobre qué compañía.

### Suscripción

- **RF-10** Cada carga de pantalla conoce el estado y lo aplica (§2).
- **RF-11** Aviso visible desde 7 días antes del vencimiento.
- **RF-12** Los límites del plan se validan al crear: terminales, sucursales,
  usuarios.

### Categorías

- **RF-13** Crear, renombrar, reordenar y desactivar categorías y subcategorías.
- **RF-14** Mover una subcategoría de una raíz a otra sin tocar los productos.
- **RF-15** La grilla de ventas navega por los dos niveles.
- **RF-16** El inventario filtra por categoría y subcategoría.

### Catálogo e impuesto

- **RF-17** Buscar CABYS por texto desde la ficha del producto y asignarlo.
- **RF-18** Al asignarlo se copia la tarifa; si el usuario la cambia, se avisa.
- **RF-19** Los totales se calculan sumando el impuesto línea por línea.
- **RF-20** Asignación de CABYS en lote, para catálogos ya cargados.
- **RF-21** El documento impreso desglosa el impuesto por tarifa cuando hay más
  de una en la misma venta.

### Facturación electrónica (preparación)

- **RF-22** Subir el `.p12` y el PIN; se guardan cifrados.
- **RF-23** Mostrar estado del certificado: cargado, fecha, vencimiento. Nunca
  el contenido.
- **RF-24** Reemplazar o quitar el certificado.
- **RF-25** Consultar la actividad económica por cédula contra Hacienda.
- **RF-26** Administrar sucursales y terminales con sus códigos.

---

## 7. Requisitos no funcionales

- **RNF-1 Aislamiento.** Ninguna respuesta contiene datos de otra compañía. Se
  verifica con pruebas automatizadas que intentan cruzarse a propósito. **Sin
  compañía en la sesión no se responde nada**: la ausencia de filtro es un
  error, no un permiso (ver plan §3.3).
- **RNF-2 Idioma.** Español, inglés y portugués (de Brasil). El español en
  **usted**. Ningún texto visible queda escrito dentro de un componente: se
  verifica con una prueba que recorre las plantillas buscando cadenas sueltas.
- **RNF-3 Rendimiento.** La grilla de ventas responde en menos de 100 ms con
  5 000 productos. La búsqueda por código de barras es instantánea.
- **RNF-4 Sin internet.** El POS funciona en LAN sin salida a internet. Lo que
  necesita internet —CABYS, Hacienda— degrada con aviso, nunca bloquea la venta.
- **RNF-5 Secretos.** Certificados y PIN cifrados en reposo, con la llave fuera
  de la base de datos.
- **RNF-6 Cada función tiene su prueba.** Es regla del proyecto, y se aplica por
  capa porque cada capa se prueba distinto:

  | Capa | Prueba | Exigencia |
  |---|---|---|
  | `domain/` | Unitaria, sin dobles: es código puro | **100 %**, la build se cae por debajo |
  | `application/` | Unitaria con puertos simulados | **100 %**, la build se cae por debajo |
  | `infrastructure/` | Integración contra la pieza real (MySQL, API de Hacienda) | Cada adaptador, con su caso de fallo |
  | `interfaces/`, `ui/` | Flujo de punta a punta, no una prueba por componente | Los recorridos que dan plata: cobrar, arquear, devolver, entrar mercadería |

  Una función nueva en `domain/` o `application/` **sin su prueba está
  incompleta**, igual que si no compilara. Nada de «después le agrego pruebas».
- **RNF-7 Verificación estática.** `npm run check` en 0 errores y 0
  advertencias.

---

## 8. Reglas que no cambian

Vienen de defectos reales, ya corregidos. Están en `progress.json` con su
historia.

1. **El dinero se calcula en el servidor**, releyendo los precios del backend.
2. **La hora la pone el servidor.** Dos relojes no se pueden comparar.
3. **Los permisos se aplican en el servidor.** Esconder un botón no es control
   de acceso.
4. **El modo mock se mantiene sincronizado** con el backend real.
5. **No se vende con la caja cerrada.**
6. **Nada toca el inventario hasta que se confirma la vista previa.**

Y tres que se adoptaron el 2026-08-16, con el mismo rango:

7. **El dominio no depende de nada** (§5.5). Se comprueba con una búsqueda.
8. **Toda función de dominio y de caso de uso tiene su prueba** (RNF-6). Sin
   ella el código está incompleto.
9. **Código en inglés, interfaz en español, documentación en español** (§5.6).

---

## 9. Glosario

| Término | Qué es |
|---|---|
| **Afiliado** | Número que agrupa las compañías de un mismo cliente comercial. |
| **Compañía** | El negocio suscrito. Junto con el afiliado forma la identidad del inquilino. |
| **Sucursal** | Local físico. Código de 3 dígitos (Hacienda). |
| **Terminal** | Caja registradora. Código de 5 dígitos (Hacienda). |
| **CABYS** | Catálogo de Bienes y Servicios de Hacienda. 13 dígitos, define la tarifa. |
| **Soporte** | Rol sin compañía que administra la plataforma. |
| **Entrar como** | Que soporte tome la vista de una compañía, con bitácora. |
| **BFF** | El servidor de SvelteKit, que habla con FastAPI. El navegador nunca lo hace. |

---

## 10. Estado actual

**Construido y verificado** (single-tenant): ventas con ventas en espera, caja
con arqueo, devoluciones con reposición, inventario, entradas por manual/Excel/
XML de Hacienda, clientes, usuarios, reportes, configuración con moneda,
impuesto, marca y tres plantillas de documento.

**Por construir**: todo lo de este documento marcado RF-1 a RF-26.

**Deuda conocida**: en `progress.json` → `pendientes`.
