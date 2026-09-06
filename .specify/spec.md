# VentaSys — Especificación

> **Qué es este documento.** Define *qué* es VentaSys y *por qué*, no cómo se
> construye. El cómo está en [plan.md](plan.md) y el trabajo concreto en
> [task.md](task.md).
>
> Actualizado: 2026-09-06 · Estado: vigente

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

**RN-31.** El vencimiento lo pone **el calendario, no una tarea manual**. Una
compañía `activa` cuya fecha ya pasó está vencida, y el sistema la trata como
tal aunque nadie haya tocado la columna. El estado guardado sigue siendo el que
puso soporte —el panel muestra los dos—, pero el que manda es el efectivo. La
alternativa es que el producto deje de cobrar el día que nadie mire.

Sin fecha de vencimiento no hay gracia que calcular, y entonces no hay gracia:
falla cerrado. Que una compañía marcada `vencida` sin fecha quede en solo
lectura es lo peor que le puede pasar a quien olvidó escribir un dato; vender
gratis para siempre es lo peor que le puede pasar al negocio.

**RN-32.** *Entrar como* es de **solo lectura**. Soporte entra a diagnosticar
(§3), así que su visita ve todo y no escribe nada. Si hay que cambiarle algo a
un cliente se le pide a su administrador, o se le crea una membresía de verdad
—que se ve en la lista de usuarios y no depende de que nadie se acuerde—.

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
- Certificado (.p12) y PIN del emisor, cifrados, **por ambiente**.
- **Credenciales del API de Hacienda (usuario y contraseña de ATV)**, también por
  ambiente, y la elección del ambiente en el que se trabaja.
- Sucursales y terminales, con su numeración, **continuando la que el negocio ya
  traía** si viene de otro sistema.
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
- Certificado `.p12` y PIN por compañía **y por ambiente**, cifrados en reposo,
  que **nunca** vuelven al navegador.
- **Credenciales del API de Hacienda** —usuario y contraseña de ATV— también por
  ambiente. Son un secreto distinto del certificado y sirven para otra cosa.
- **El ambiente elegido**: pruebas o producción.
- Actividad económica del emisor, consultable contra el API de Hacienda.
- Sucursal y terminal (§5.3).
- Datos obligatorios del receptor: tipo y número de identificación, correo.
- Unidad de medida por producto, del catálogo de Hacienda.

#### Son dos secretos, no uno

Firmar y transmitir son cosas separadas y cada una tiene su credencial:

| | Para qué | De dónde sale |
|---|---|---|
| `.p12` + PIN | **Firmar** el XML (XAdES-EPES) | ATV → Llave Criptográfica |
| Usuario + contraseña ATV | **Transmitir**: obtener el token OIDC del IdP de Hacienda | ATV → Obtener credenciales API |

El certificado no autentica contra el API y las credenciales no firman nada. Con
solo uno de los dos no se emite. Está en `docs/hacienda/costa-rica/README.md` §7.

**RN-16.** **La llave privada, el PIN y la contraseña de ATV** no se muestran,
no se registran en bitácora y no salen del servidor. La pantalla solo dice si
hay certificado cargado, cuándo se subió y cuándo vence.

Lo que sí sale es la **parte pública** del certificado, y tiene que salir: viaja
dentro de cada XML firmado, que es como el receptor y Hacienda verifican la
firma. Llamar «el certificado» a las dos mitades es lo que hacía que esta regla
pareciera prohibir lo que el formato exige.
**RN-17.** Mientras no se emita, el documento impreso lo dice en su leyenda. Y
**lo emitido en el ambiente de pruebas también lo dice**: son comprobantes que
no tienen efecto fiscal, y entregar uno sin distintivo es entregar un papel que
parece una factura y no lo es.
**RN-33.** Cada compañía tiene **un juego de credenciales por ambiente**, no
uno solo. Los de pruebas no sirven contra producción y viceversa —Hacienda los
emite en registros separados—, así que una compañía que está integrando tiene
los dos a la vez: pasar a producción no puede significar borrar lo de pruebas y
quedarse sin poder volver. Siguen siendo datos **de la compañía**, con el mismo
aislamiento que todo lo demás (RNF-1).
**RN-34.** **La numeración también es por ambiente.** Un comprobante de pruebas
nunca consume un número de producción. Si el consecutivo fuera uno solo, cinco
facturas de prueba se comerían los números 1 al 5 de los reales y dejarían un
hueco — y el consecutivo tiene que ir sin huecos.
**RN-35.** **Pasar a producción se confirma y queda en bitácora.** Es el momento
en que los documentos dejan de ser un ensayo y pasan a tener efecto fiscal, y no
puede ocurrir por haber tocado un desplegable sin querer.

#### El negocio que ya venía facturando

Casi ningún cliente llega en cero: viene de otro sistema y **su numeración tiene
que continuar**, no volver a empezar. Un consecutivo repetido lo rechaza
Hacienda, y dos sistemas contando desde uno es la forma más rápida de repetirlo.

**RN-36.** Al configurarse, el cliente indica **su oficina y el último
consecutivo que emitió**. El resto de la clave —país, fecha, identificación,
terminal, tipo de comprobante, situación y código de seguridad— lo arma el
sistema: son datos que ya tiene o que le tocan a él calcular, y pedírselos sería
pedirle que haga de sistema.

**RN-37.** El último consecutivo **es uno por tipo de comprobante**, no uno
solo. La numeración de Hacienda es secuencial *dentro del tipo*: las facturas
llevan su serie y los tiquetes la suya, y un negocio que emitió 4 200 facturas y
15 300 tiquetes tiene que poder decir las dos.

**RN-38.** El arranque **solo se puede subir, nunca bajar**, y cambiarlo queda en
bitácora. Bajarlo significa volver a emitir números ya usados: rechazo seguro y
un desorden que no se limpia. Una vez que el sistema emitió, el contador es suyo.

### 5.4b Emisión (§7.2 del plan)

Emitir no es un momento sino **un recorrido**, y lo que decide si el negocio
puede trabajar es poder ver en qué punto va cada documento y qué hacer cuando se
atasca.

**RN-39.** Cada comprobante tiene un **estado visible** en la pantalla de
facturas: numerado, firmado, enviado, aceptado, rechazado, reintentando o
detenido. Los tres últimos son los que importan: una falla que no se ve es una
falla que nadie atiende.

**RN-40.** El estado se **consulta**, no se supone. Hacienda responde al envío
con un «recibido» que no es una aceptación; el veredicto llega después y hay que
ir a buscarlo.

**RN-41.** **No todo lo que falla se reintenta.** Un rechazo es una respuesta y
se detiene ahí. Una falla nuestra —certificado vencido, credenciales rotadas—
también se detiene, en el primer intento y avisando: reintentar tres días para
llegar a la misma conclusión no es tolerancia a fallos, es demorar el aviso.
Solo lo transitorio se reintenta, espaciando los intentos.

**RN-42.** **Agotar los reintentos no es rendirse.** Hacienda da un plazo para
transmitir lo emitido en contingencia; cuando el sistema deja de reintentar
solo, el documento sigue estando ahí, transmitible a mano y **contando el
tiempo a la vista**. Lo que no puede pasar es que se pierda en silencio.

**RN-43.** La **contingencia es un modo del negocio, no una corazonada por
venta**. El comprobante declara en su clave si se emitió en contingencia, y esa
clave se imprime y se entrega en el mostrador — o sea que se decide al vender,
no al transmitir. Se decide por el estado de las transmisiones recientes, no
preguntándole al cajero.

**RN-44.** El **XML firmado se conserva tal como se envió**, byte por byte. La
firma cubre esos bytes: regenerarlo produce otra firma y deja de ser el
documento. Junto a él se conserva la respuesta de Hacienda, que va firmada por
ella y es la prueba de la aceptación. **Cinco años**, los dos.


**RN-45.** La **identificación del emisor es la de la compañía**, no un campo de
su configuración. Vive en `companies` con su tipo, la fija soporte al dar de alta
y el administrador del negocio la ve pero **no la edita**.

No es burocracia: el certificado de firma se emite **a esa identificación** y el
usuario de ATV la lleva dentro de su propio nombre
(`cpf-01-1234-5678@comprobanteselectronicos.go.cr`). Un campo editable ahí deja
que el negocio la haga discrepar de su propio certificado, y entonces **todos**
sus comprobantes se rechazan. Corregir un error del alta pasa por soporte, que es
la fricción correcta para el dato que identifica al contribuyente.

**RN-46.** El paso a producción **avisa de lo que Hacienda exige y no lo impide**:
una factura, un tiquete y una nota de crédito emitidos en pruebas. Mientras no
existan comprobantes que contar —antes de la emisión— el aviso es lo único
comprobable; la puerta dura entra cuando hay qué contar. Un candado que solo
puede abrirse en una fase posterior nace cerrado y sin forma de probar que abre.

**RN-47.** El respaldo por compañía se lleva **lo público del certificado y no
sus secretos**: viajan el certificado público, el usuario de ATV y las fechas; no
viajan el `.p12`, el PIN ni la contraseña. Al restaurar, la pantalla dice qué hay
que volver a cargar.

Llevarse el `.p12` cifrado sería correcto respecto de RNF-5 —la llave no viaja—
y aun así el peor caso: en otra instalación, con otra `FE_CRYPTO_KEY`, es un
archivo indescifrable que nadie distingue de uno bueno hasta el día de facturar.
Un respaldo que parece completo y no lo es solo se descubre cuando hace falta.

**RN-48.** El catálogo CABYS **vive en la base**, completo, y es lo que contesta
las búsquedas. La tarifa que se **asigna**, en cambio, se confirma contra Hacienda
cuando hay internet.

Son dos cosas distintas y por eso se separan: buscar entre 19 000 entradas tiene
que ser instantáneo y funcionar sin red (RNF-4), pero una tarifa local
desactualizada se emite y vuelve como rechazo —«el IVA no coincide con el
definido para ese CABYS»—. La velocidad sale de la base; la verdad, del catálogo,
cuando se le puede preguntar.

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

**RN-30.** **Ninguna capa que no sea la interfaz escribe texto para una
persona.** El backend, el dominio de las dos aplicaciones y los adaptadores
devuelven un código y los datos —`{"code": "insufficient_stock", "product":
"Arroz", "available": 2}`— y la interfaz arma la frase.

El caso que la motivó es el backend: producía en español todos sus «no», y el
POS los mostraba tal cual, así que un cajero brasileño vería media aplicación en
su idioma y los errores en español, que es justo cuando más necesita entender.
Pero la regla no cierra si se detiene en el borde HTTP —el dominio le entregaba
la frase al adaptador y el adaptador la reenviaba— ni si se detiene en el
backend: el dominio del POS devolvía frases, los lectores de archivos escribían
las suyas y la capa de servidor las propias. Una capa que arma la oración tiene
que saber el idioma de la pantalla, y entonces no es dominio.

Vale también para los **valores por omisión** que acaban impresos —el mensaje de
agradecimiento del tiquete, la leyenda legal—: un texto que se manda de fábrica
en español sale en español en la factura de una compañía brasileña. Se siembran
al dar de alta la compañía, que es cuando se conoce su idioma (RF-6).

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
- **RF-29** Guardar el usuario y la contraseña de ATV. **La contraseña se cifra
  y no vuelve al navegador; el usuario sí se muestra**, porque es un
  identificador y no un secreto: sin verlo, nadie puede comprobar que escribió
  el que era.
- **RF-30** Elegir el ambiente —pruebas o producción— y ver, para cada uno, si
  ya tiene su certificado y sus credenciales. Cambiar a producción se confirma.
- **RF-31** Comprobar que las credenciales del ambiente sirven, **sin emitir
  nada**. Es la única forma de saberlo antes de que haga falta.

  Son **tres** desenlaces y hay que distinguirlos: sirven, **no** sirven, y no
  se pudo comprobar. El tercero no es el segundo: decirle a un cliente que su
  contraseña está mal el día que Hacienda está en mantenimiento lo lleva a rotar
  una credencial buena. Es RNF-4 aplicado acá — lo que necesita internet degrada
  con aviso.
- **RF-32** Indicar la oficina y el último consecutivo emitido por tipo, para
  continuar la numeración de un negocio que viene de otro sistema. RN-36 a RN-38.
- **RF-37** La identificación del emisor y su tipo se ven en Configuración **sin
  poder editarse**, con quién la puede cambiar. RN-45.
- **RF-38** Buscar en el catálogo CABYS **por código además de por descripción**,
  y filtrar por prefijo sin depender de internet. RN-48.

### Emisión

- **RF-33** La pantalla de facturas muestra el estado de cada comprobante y,
  cuando está esperando, cuándo fue el último intento y cuándo es el próximo.
- **RF-34** Descargar el XML firmado y la respuesta de Hacienda.
- **RF-35** Una lista de lo **detenido**: lo que necesita a una persona, con el
  motivo y el tiempo que lleva esperando.
- **RF-36** Reintentar a mano un documento detenido, después de arreglar lo que
  lo detuvo.

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
- **RNF-5 Secretos.** **Llaves privadas, PIN y contraseñas de ATV** cifrados en
  reposo, con la llave de cifrado **fuera de la base de datos**: un respaldo
  robado no alcanza para firmar ni para transmitir. La parte pública del
  certificado no es un secreto y queda fuera de esta regla. Dónde vive la llave
  privada es una decisión de despliegue —ver plan §7.1— y no la cambia.
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

**Por construir**: lo marcado **RF-22 a RF-26 y RF-29 a RF-38**. De RF-1 a
RF-21 y RF-27 y RF-28 ya están construidos —F2 a F5 y F8—; el detalle de qué
cerró cada fase está en `progress.json`.

**Deuda conocida**: en `progress.json` → `pendientes`.
