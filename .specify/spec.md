# VentaSys — Especificación

> **Qué es este documento.** Define *qué* es VentaSys y *por qué*, no cómo se
> construye. El cómo está en [plan.md](plan.md) y el trabajo concreto en
> [task.md](task.md).
>
> Actualizado: 2026-09-11 · Estado: vigente

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

### Módulos

**Cada sección del POS es un módulo** que un plan incluye o no —ventas, caja,
facturas, devoluciones, reportes, inventario, compras, proveedores,
contabilidad, planilla, clientes y usuarios—, y **los planes son paquetes** de
ellos (QA-01, decidido con el usuario el 2026-10-03). Configuración no es un
módulo: sin ella no hay negocio. Un restaurante no necesita caja ni
inventario, un abarrotes que solo quiere cobrar no tiene por qué ver un libro
mayor, y el producto tiene que poder venderlos por separado. Los paquetes de
fábrica son **Restaurante** (ventas, facturas, clientes, usuarios),
**Comercio** (más caja, devoluciones, inventario y proveedores), **Comercio con
compras** (más reportes y compras) y **Completo** (todo). Hasta QA-01 los
módulos eran solo compras, contabilidad y planilla, y el resto lo tenía todo el
mundo; los planes que ya existían conservan esas secciones.

**RN-49.** Un módulo se activa **por plan** y se aplica **en el servidor**. Una
compañía cuyo plan no incluye el módulo recibe un código —no un redirect— en
cualquier escritura de sus rutas. En la navegación del POS **se muestra con
candado, no se esconde**: es la misma regla que ya rige para lo que un rol no
puede abrir, y acá vale por una razón más —un «Compras 🔒» es lo único que le
dice al dueño que el producto tiene ese módulo, y escondiéndolo lo que se
quiere vender queda invisible justo para quien lo compraría—. Que se vea no es
un permiso: el control de acceso está en el servidor (§8, regla 3).

**RN-50.** Apagar un módulo **no borra nada**: lo deja en solo lectura. Los
libros de una compañía que bajó de plan siguen siendo su respaldo ante Hacienda
y las boletas de una planilla siguen siendo la prueba de lo pagado; el plan
decide qué se puede seguir escribiendo, no qué existió. Lo que se lee y se
exporta, se lee y se exporta siempre.

**RN-51.** El plan dice qué módulos incluye; quién lo cambia es soporte, y el
cambio ya queda en bitácora (RF-7). No hay un interruptor por compañía aparte
del plan: dos sitios para la misma verdad es donde se separan.

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
- **Compras y cuentas por pagar** (F10, módulo por plan): proveedores, la
  compra desde el XML de Hacienda con su impuesto por línea, condición de
  pago, abonos y saldos.
- **Contabilidad** (F11, módulo por plan): partida doble con asientos
  automáticos desde lo que el POS ya registra, periodos, libros y borrador
  del D-104.
- **Planilla** (F12, módulo por plan): empleados, puestos, jornadas mensuales,
  quincenales, bisemanales y semanales, acciones de personal, corridas con las
  tasas congeladas, aguinaldo, vacaciones, liquidación, los archivos para la
  CCSS y el INS, y la importación desde Excel de quien viene de otro sistema.
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
- Devoluciones a proveedor y notas de crédito recibidas. F10 deja la compra
  con su documento, que es lo que una nota de crédito necesita referenciar.
- Compras de servicios y gastos sin mercadería. Van como asiento manual en
  contabilidad hasta que haya un caso que pida más.
- Activos fijos y depreciación, conciliación bancaria, presupuestos y
  consolidación entre las compañías de un afiliado.
- Planilla de servicios profesionales, pago de planilla desde la caja del
  POS, y planilla de otro país: las tasas se modelan por país (RN-67), pero
  solo se siembra Costa Rica.
- De planilla, lo que el ERP de origen tiene y la primera versión no: los
  archivos de pago de cada banco, el envío de boletas por correo, las
  vacaciones por régimen y los bonos de cumpleaños o aniversario, la renta
  con otros patronos, las constancias salariales, los centros de costo y los
  departamentos, los contratos en otra moneda, varios contratos a la vez para
  el mismo empleado, el salario por hora, la pensión voluntaria como rebajo de
  la renta, el
  expediente del empleado (amonestaciones y notas) y la planilla del INSS de
  Nicaragua. Se decidió el 2026-09-27, al comparar F12 con ese ERP; cada una
  vuelve cuando un cliente la pida.

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

**RN-9.** Cada producto lleva su tarifa, la de su CABYS. Uno sin tarifa paga
**la general del IVA, el 13 % de ley**, que **no se configura**: la tasa de
Configuración se quitó el 2026-10-03 (QA-05) porque con la tarifa por CABYS
solo servía para equivocarse —un 10 % escrito ahí se cobraba en todo producto
sin clasificar—.
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
preguntándole al cajero. Y solo cuenta que **Hacienda** no haya contestado: una
falla del propio sistema no es una caída de Hacienda y no se declara como tal.
Lo que la clave dice en ese caso es «sin internet» (anexo 4.4, nota 3): el
comprobante se generó electrónicamente y no se pudo transmitir. «Contingencia»
es otra cosa —el comprobante que sustituye uno físico hecho a mano— y VentaSys
no la emite.

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

### 5.7 Compras y cuentas por pagar

Hoy una entrada de mercadería sabe qué entró, cuánto costó y quién la cargó
(`stock_entries`), y hasta guarda el nombre del proveedor y el número de su
factura como texto. Lo que no sabe es lo que un negocio necesita al final del
mes: **a quién le debe, cuánto y desde cuándo**, y cuánto IVA pagó en esas
compras. Sin eso no hay crédito fiscal, y sin crédito fiscal el D-104 sale mal
y el estado de resultados no tiene lado de costos. Por eso compras deja de
estar en «no entra todavía»: es el prerrequisito de contabilidad.

**RN-52.** Una compra **es** una entrada de mercadería que sabe tres cosas
más: a quién se le compró, con qué documento y en qué condición de pago. Una
entrada sin proveedor sigue siendo una entrada —las que ya existen, las de
ajuste— y no genera cuenta por pagar ni crédito fiscal.

**RN-53.** El impuesto de una compra es **el que dice el documento del
proveedor**, línea por línea. No se recalcula desde la tarifa del producto: el
crédito fiscal es lo que se pagó, no lo que se habría cobrado. Cuando la tarifa
del documento difiere de la del producto se avisa, como hace RN-11 con el
catálogo, porque suele ser un CABYS mal asignado de un lado o del otro.

**RN-54.** El costo de un producto es el **promedio ponderado móvil** de sus
compras, recalculado al confirmar cada una. Con 10 unidades a ₡100 en
existencia, comprar 10 a ₡120 deja el costo en ₡110; con existencias en cero o
negativas, el costo pasa a ser el de la compra. Hoy el producto no tiene costo:
la columna nace acá.

**RN-55.** Un abono se aplica a **una compra** y no supera su saldo. El saldo
de un proveedor es la suma de los saldos de sus compras, no un número aparte
que haya que mantener cuadrado.

**RN-56.** Un pago en efectivo a un proveedor **sale de la caja abierta** y
queda como movimiento de caja. Sin caja abierta no hay pago en efectivo: se
paga por transferencia o se abre la caja. Es la regla 5 de §8 vista desde la
salida de plata: lo que no está en ningún turno no aparece en ningún arqueo.

**RN-57.** Una compra confirmada **no se edita**. Se anula con motivo y
bitácora mientras no tenga abonos, y la anulación revierte las existencias y
la cuenta por pagar. El costo promedio **no se deshace**: recalcularlo hacia
atrás exige rehacer todas las compras posteriores del producto, y la siguiente
compra lo corrige sola. Está explicado en plan.md §12.

### 5.8 Contabilidad

El POS ya sabe todo lo que un asiento necesita: cuánto se vendió y con qué
impuesto por tarifa, cómo se pagó, qué se devolvió, cuánto faltó o sobró al
cerrar la caja, qué entró y a quién se le debe. Hoy eso sale del sistema como
un reporte y el contador lo vuelve a escribir. Contabilidad es que **el evento
se convierta en asiento solo**, por un mapeo, y que el libro exista adentro.
La partida doble es universal; la plantilla de cuentas y las declaraciones son
de Costa Rica y viven como datos.

**RN-58.** Todo asiento **balancea**: la suma de débitos es igual a la de
créditos, a dos decimales, y se comprueba en el dominio antes de guardarlo. Un
asiento que no cuadra no es un asiento con error: no existe.

**RN-59.** Los asientos automáticos los genera **el servidor, en la misma
transacción** del evento que los origina. Si el asiento no se puede escribir,
la venta no se confirma. Y para que eso nunca pase por un mapeo incompleto, lo
que no tiene cuenta asignada va a **«por clasificar»**: el asiento siempre
balancea y siempre existe; el error se ve en rojo en la pantalla del contador,
no detiene al cajero (RNF-4).

**RN-60.** La contabilidad **empieza en una fecha**, elegida al activarla, con
un asiento de apertura de saldos iniciales. Lo anterior no se reconstruye: las
ventas viejas no tienen costo congelado ni mapeo, y rehacerlas sería inventar
datos.

**RN-61.** Un periodo cerrado es **inmutable**. Nada se escribe con fecha
dentro de un periodo cerrado; lo que hay que corregir se corrige con un asiento
de ajuste en el periodo abierto, que referencia al que corrige. Cerrar queda en
bitácora y no se deshace.

**RN-62.** Un asiento usa las cuentas del mapeo **vigente al momento del
evento** y las guarda. Cambiar el mapeo afecta lo que venga, nunca lo que ya
está en el libro. Es RN-12 aplicada a las cuentas.

**RN-63.** El costo de ventas de una línea es el costo promedio del producto
**al momento de venderse**, congelado en la línea. Vender hoy 3 unidades con
costo ₡110 y comprar mañana a ₡150 no cambia el costo de lo que ya se vendió.

**RN-64.** Las cuentas que el mapeo necesita son **de sistema**: no se borran
ni se desactivan. El resto se desactiva si tiene movimientos y se borra solo si
nunca los tuvo.

**RN-65.** El IVA se lleva **por tarifa**, como ya se cobra (RN-10): el débito
fiscal sale de las ventas por tarifa y el crédito fiscal de las compras por
tarifa (RN-53). El borrador del D-104 es una consulta sobre eso, no un cálculo
aparte que pueda discrepar.

Lo que el POS **no** hace es adivinar: una venta con tarjeta va a «tarjetas por
cobrar» por su monto bruto, y la retención y la comisión del adquirente se
registran cuando el banco las liquida, porque es entonces cuando se saben.
Estimarlas al vender es asentar un número que después no coincide.

### 5.9 Planilla

Planilla no es una pantalla más del POS: no toca productos, ventas ni caja.
Comparte la compañía, los usuarios y la suscripción, y tiene su propio reloj
—la CCSS, Hacienda y el Código de Trabajo cambian las reglas con fecha— y su
propio modo de fallar: un error en una venta se devuelve; un error en una
boleta es un reclamo laboral del cliente. Por eso todo lo que sigue gira
alrededor de una idea: **una corrida es reproducible**.

**RN-66.** La planilla se calcula **en el servidor** con las tasas vigentes a
la fecha de corte, y la corrida **las congela**: reimprimir la boleta de julio
en diciembre da lo mismo aunque las tasas hayan cambiado. Es RN-12 sobre una
superficie más grande.

**RN-67.** Las tasas, los tramos y los topes son **datos con vigencia y país**,
nunca constantes del código. Una tasa nueva es una fila con fecha, no un
despliegue. Se siembran con fuente y fecha, y la pantalla dice de cuándo son.
El país existe para no cerrar la puerta (F8 ya habla portugués), no para
construir otro: solo se siembra Costa Rica.

**RN-68.** Una corrida pasa por **borrador → aprobada → pagada**. Pagada no se
edita: se corrige con una corrida de ajuste que referencia a la original. Pagar
queda en bitácora, con quién y cuándo.

**RN-69.** El aguinaldo se calcula sobre lo devengado del 1 de diciembre al 30
de noviembre, entre doce, y **no lleva cargas ni renta**. Es la exención que
más se olvida; el dominio la conoce y la prueba.

**RN-70.** Las vacaciones se **acumulan** por tiempo trabajado y el saldo es
visible por empleado. Se pagan al salario del momento del disfrute, no al de
cuando se ganaron.

**RN-71.** La liquidación **depende de la causa**: preaviso y cesantía solo
cuando la ley los debe; vacaciones y aguinaldo proporcionales, siempre. La
tabla de cesantía es un dato con vigencia (RN-67), y la causa queda escrita.

**RN-72.** Un empleado **no es un usuario**. Existe aparte y puede enlazarse a
uno: la cajera es las dos cosas, el bodeguero suele ser solo empleado. Un ex
empleado no se borra: se da de baja con fecha y causa, que es lo que la
liquidación y la planilla de la CCSS necesitan. Tiene los datos que piden los
informes de la CCSS y del INS: el nombre y **los dos apellidos por separado**,
el tipo y el número de identificación —cédula, DIMEX, NITE, pasaporte o
permiso de trabajo—, el número de asegurado, la fecha de nacimiento, el género,
el estado civil, la nacionalidad y si es pensionado.

**RN-73.** El impuesto al salario se retiene **por tramos mensuales** sobre el
salario del **mes calendario**, menos los créditos fiscales. Las corridas que
no cierran el mes retienen sobre la proyección, y la última del mes **liquida
la diferencia**: lo retenido en el mes es exactamente el impuesto de lo
devengado en el mes, que es lo que se declara. Proyectar y partir sin liquidar
descuadra el mes en cuanto las horas extra de una quincena no son las de la
otra. Los tramos y los créditos son datos con vigencia.

**RN-74.** La planilla **no mueve la caja del POS**. Se paga por transferencia
o se marca pagada; lo que salga de la gaveta para pagarla se anota como retiro
con motivo, como hoy. Mezclar la nómina con el arqueo es la forma más rápida de
que ninguno de los dos cuadre.

**RN-75.** Con contabilidad activa, pagar una corrida **genera su asiento**:
gasto de salarios, gasto de cargas patronales, retenciones por pagar a la CCSS
y a Hacienda, y salarios por pagar. Sin contabilidad, no pasa nada más.

Lo que sigue se agregó el 2026-09-27, después de comparar F12 con el ERP del
que viene VentaSys: es lo que separa una calculadora de salarios de una
planilla que se puede presentar a la CCSS y al INS.

**RN-90.** Todo lo que cambia el pago o la situación de un empleado es una
**acción de personal**: tiene tipo, fechas, cantidad o monto, quién la
registró y cuándo. **Vive en el empleado, no en la corrida**: cada corrida toma
las que caen en su periodo, y una que cruza dos periodos —una incapacidad del
10 al 20 en quincenas— se parte por el calendario, no a mano. Es el historial
del empleado y la fuente de los informes: la CCSS pide las fechas de cada
incapacidad, de cada permiso y de cada cambio de puesto. Los tipos son estos, y
la lista es cerrada —cada tipo tiene su efecto en el cálculo y en los
informes, y uno inventado por la compañía no sabría qué decirle a la CCSS—:

| Grupo | Tipos |
|---|---|
| Devengos | horas extra, horas dobles (feriado o descanso trabajado), bonificación |
| Ausencias | incapacidad de la CCSS, incapacidad del INS, licencia de maternidad, permiso con goce, permiso sin goce, ausencia injustificada, vacaciones |
| Deducciones | deducción, pensión alimentaria, embargo |
| Del contrato | aumento de salario, cambio de puesto, baja |

**RN-91.** Una acción que ya entró en una corrida pagada **no se edita ni se
borra: se anula**, y la anulación entra en la corrida siguiente con el efecto
contrario. Una acción que cae en un periodo ya pagado —la incapacidad que llegó
tarde— se aplica en la corrida siguiente, con sus fechas. La corrida pagada no
cambia nunca (RN-68).

**RN-92.** Una deducción puede ser **recurrente**: se aplica en cada corrida
mientras esté vigente, hasta su fecha final o hasta agotar su saldo si tiene
monto total —un préstamo de ₡300 000 a ₡25 000 por quincena—. Se puede
**suspender**, con motivo, y queda quién y cuándo; lo ya aplicado no se toca.
El saldo es lo pactado menos lo aplicado en corridas pagadas, nunca una columna
que alguien edita.

**RN-93.** El **embargo** respeta el art. 172 del Código de Trabajo: es
inembargable el menor salario mensual del decreto de salarios mínimos —un dato
con vigencia, RN-67— y del resto se embarga un octavo hasta tres veces ese
monto y un cuarto de lo que lo supere, sobre el salario del mes menos cargas y
renta, y nunca más que el saldo. Ese monto es **del salario y no de cada
embargo**: dos embargos se lo reparten, el más viejo primero. La **pensión
alimentaria** puede tomar hasta la mitad del salario. **El neto nunca es
negativo**: si las deducciones no caben se aplican en orden —cargas, renta,
pensión alimentaria, embargo y las demás— y lo que no cupo queda en su saldo
para la corrida siguiente; no se inventa como deuda del empleado.

**RN-94.** El pago es **mensual, quincenal, bisemanal o semanal**, y cada
compañía define sus **jornadas**: la periodicidad, la clase —diurna, mixta o
nocturna, con sus horas por día—, si el día de descanso se paga
(establecimientos comerciales, art. 152) y las **fechas de corte**: el día en
que corta la primera quincena, el día de la semana o el inicio de la serie
bisemanal. Una corrida es de una jornada y de una fecha de corte válida para
ella, y el periodo sale del corte: no se escribe. El salario del contrato es el
del periodo de su jornada, y el mensual se deriva: por dos, por veintiséis
doceavos, por cincuenta y dos doceavos. En mensual y quincenal el día vale el
mensual entre treinta, tenga el mes los días que tenga, y una ausencia nunca
rebaja más que el salario del periodo.

**RN-95.** Cada compañía tiene su catálogo de **puestos**, y cada puesto lleva
su **código de ocupación de la CCSS** y su **código del INS**: los dos
informes lo piden por empleado. El contrato dice el puesto; cambiarlo es una
acción de personal con fecha (RN-90), y la CCSS la recibe como cambio de
ocupación.

**RN-96.** Cada mes salen **dos archivos**: la planilla para la CCSS (SICERE) y
la del INS por póliza de riesgos del trabajo (RT-Virtual). Los dos se arman de
las corridas pagadas del mes y de las acciones con sus fechas, y **el formato
se toma de la especificación oficial** de cada institución, guardada en el
repositorio como los XSD de Hacienda. Un archivo que no coincide con lo pagado
es peor que ninguno: la diferencia la cobra la institución con recargos.

**RN-97.** Una compañía que viene de otro sistema **no empieza de cero**:
importa desde Excel sus puestos, sus empleados con su contrato y sus **saldos
de apertura** —los días de vacaciones a una fecha, lo devengado desde el 1 de
diciembre para el aguinaldo, los salarios de los últimos seis meses para una
liquidación y las deducciones recurrentes con lo que les queda—. Se importa con
**vista previa**: nada se escribe hasta confirmar, una fila con error no entra
y se dice por qué, y lo confirmado entra entero o no entra. Los saldos de
apertura quedan marcados como importados, con su fecha, y el aguinaldo y la
liquidación los suman como si fueran corridas pagadas.

### Lo que Hacienda exige del contenido del comprobante

Cada una está citada, con su página del anexo v4.4 y el ejemplo que la
demuestra, en `docs/hacienda/costa-rica/casos-de-emision.md`.

**RN-76.** **La tarifa se declara con su código, no con su porcentaje.** El
catálogo tiene once códigos para nueve porcentajes: el 0 % con derecho a crédito
pleno (`01`) y el 0 % sin derecho a crédito (`11`) son el mismo número y dan
derechos opuestos, y los transitorios `05`, `06` y `07` solo valen en notas de
crédito y de débito. Deducir el código desde el porcentaje es perder esa
diferencia.

**RN-77.** **El medio de pago no va cuando la venta es a crédito.** Es
obligatorio en todos los casos **salvo** con las condiciones de venta `02`
(crédito), `08` (servicios prestados al Estado) y `10` (crédito con IVA a 90
días). Y admite hasta cuatro, con su monto cada uno: **desde el segundo,
Hacienda comprueba que los montos sumen el total del comprobante** y rechaza si
no. Con uno solo no lo comprueba, y el monto es hasta opcional.

**RN-78.** **Una exoneración son puntos de tarifa, no una tarifa.** Lo que se
declara es cuántos puntos se perdonan: una línea al 13 % con nueve puntos
exonerados paga 4 %. No existe ninguna tarifa del 9 %, así que modelarla como
tarifa da un total equivocado. El monto exonerado es esos puntos por la base, y
el impuesto neto es el monto menos el exonerado.

Y **en el resumen la línea se reparte, no se muda**: la proporción es «monto
exonerado entre monto del impuesto», y lo que no se perdonó sigue contando como
gravado. De 100 000 al 13 % con nueve puntos exonerados, 69 230.76923 van al
balde exonerado y 30 769.23077 al gravado. Mandarla entera al exonerado —que es
lo que parece razonable— descuadra el resumen contra sí mismo.

**RN-79.** **Servicios de salud pagados con tarjeta declaran el IVA devuelto**, y
Hacienda lo valida cruzando el CABYS de la línea contra su lista de servicios
médicos y el medio de pago contra `02`. Si no cuadra, **rechaza el
comprobante**. No es una exoneración ni un descuento: el impuesto se cobra y el
campo solo declara cuánto se le devuelve a quien pagó — y por eso **el total del
comprobante lo resta**.

**RN-84.** **Los baldes del resumen los decide el CABYS y se llenan antes del
descuento.** Un código que empieza con 5 a 9 es un servicio y uno de 0 a 4 una
mercancía: el catálogo ya lo dice, así que guardarlo aparte sería abrir la
puerta a un comprobante donde el código y el balde se contradicen. Y el monto
que va al balde es el de la línea **sin descontar**: dos comprobantes aceptados
declaran `TotalGravado` 100 000 con 2 500 de descuento y `TotalVentaNeta`
97 500. Llenarlos con el subtotal es un resumen que no cuadra contra su propio
`TotalVenta`.

**RN-80.** **El sistema nunca inventa un dato de protocolo de comprador.** Lo
que cada gran comprador exige —un número de proveedor, un GLN, una orden de
compra— se copia tal como lo dio quien vende. Un código inventado no lo rechaza
Hacienda: lo rechaza el comprador, semanas después, cuando no encuentra contra
qué conciliar la factura.

**RN-82.** **El documento fiscal es el XML; el PDF se puede volver a hacer.**
Por eso los dos XML —el enviado y la respuesta firmada de Hacienda— se guardan
**byte por byte** y se muestran tal cual, y el PDF se genera cada vez que se
pide. Guardar el PDF sería guardar una copia que puede contradecir al original
sin que nadie se entere; regenerarlo garantiza que lo que se imprime es lo que
se emitió. Lo que sí no se puede regenerar es la firma: el XML enviado se
devuelve idéntico o la firma deja de verificar (RN-44).

**RN-83.** **La dirección del emisor son códigos, no una frase.** Hacienda pide
provincia, cantón y distrito **numerados**, más **otras señas** —esas sí en
texto, obligatorias y de al menos cinco caracteres; el barrio es el opcional, al
revés de lo que parece— y los cruza contra el Registro Único Tributario. La
dirección de texto libre que se usa para el tiquete no sirve para el XML, así
que son dos datos distintos y los dos se piden. El correo del emisor deja de ser
opcional por lo mismo: el XSD lo exige.

**RN-81.** **El REP no se corrige: se corrige la factura.** Las condiciones de
venta van en pares —`08` con `09`, `10` con `11`—: la factura difiere el IVA y
el recibo de pago lo reconoce al cobrar. Cualquier nota de crédito o de débito
va **contra la factura original**, nunca contra el recibo.

**RN-85.** **El tipo de comprobante se decide al vender, y lo decide el
receptor.** Sin cliente identificado solo cabe un **tiquete** (TE): la
**factura** (FE) exige un receptor con nombre e identificación, y el cliente de
contado de un supermercado no los tiene. Con cliente, la venta sale como factura
salvo que el cajero la deje en tiquete —un cliente frecuente que compra para su
casa no necesita la factura a su nombre—. El cajero **ve el tipo antes de
cobrar**: emitir sin saber qué se emite es enterarse cuando el cliente ya se fue
con el papel equivocado.

El tipo **queda en la venta y no cambia después**. Es parte del consecutivo, que
va por tipo (RN-37), y de la clave, así que el documento reimpreso dentro de un
año dice lo que se emitió aunque la compañía haya activado o apagado la
facturación electrónica entre medio. Con la facturación electrónica apagada, la
venta no lleva tipo y el documento es el de siempre.

**RN-86.** **Todas las representaciones impresas dicen lo mismo de Hacienda.**
El tipo de comprobante, el consecutivo y la clave van **juntos** —la Nota 1 del
anexo lo exige— en las tres plantillas, y cada una dice en qué punto está el
documento: todavía sin clave, emitido en pruebas y sin efecto fiscal (RN-17), o
autorizado. El dueño elige la plantilla por cómo se ve, no por lo que lleva, así
que lo fiscal no puede depender de cuál eligió.

Y **hay un solo molde**. El PDF que el backend dibujaba por su cuenta era un
cuarto documento que no llevaba nada de esto; se quitó (T-922), y el PDF sale de
imprimir la plantilla. Dos moldes para el mismo comprobante terminan diciendo dos
cosas distintas, y el que se entrega es justo el que nadie revisó.

**Lo que lleva un comprobante impreso** es lo de la factura de referencia del
usuario (`docs/invoice/50624092600310170293400100001010001819201163700346.pdf`,
un comprobante real aceptado), en las tres plantillas:

- **Cabecera**: el tipo, el número —el consecutivo cuando lo hay— y la fecha y
  hora de emisión.
- **Emisor**: nombre, razón social, identificación **con su tipo** («Cédula
  jurídica»), actividad económica, dirección, teléfono y correo.
- **Receptor**: nombre, identificación con su tipo, dirección, teléfono y correo.
- **Condición de venta, medio de pago y moneda**, con el tipo de cambio cuando se
  sabe.
- **Por línea**: número, CABYS, detalle, cantidad, unidad, precio unitario,
  subtotal, impuesto y total. El CABYS y la unidad son **los de la venta**, no
  los que tenga hoy el producto (RN-12).
- **Resumen**: total venta, descuentos, venta neta, impuesto por tarifa, total
  del impuesto y total del comprobante; y el **monto en letras**.
- **Al pie**, autorizado: la resolución que lo autoriza y dónde se verifica.

Lo que no es de Hacienda —el logo, los colores, las notas del dueño— es de la
plantilla. Un documento sin tipo no lleva nada de esto: es el de siempre, y sirve
en cualquier país.

**RN-87.** **Cada comprobante nace de su flujo, no de un desplegable.** Son
siete y solo tres son una venta: el tiquete, la factura y la factura de
exportación. Los otros cuatro nacen de algo que ya pasó o de otro lado del
negocio:

| Tipo | Nace de | Lo que necesita y una venta nueva no tiene |
|---|---|---|
| TE, FE | Cobrar | — (RN-85) |
| FEE | Cobrar a un cliente del extranjero | La partida arancelaria de cada producto y la dirección extranjera del cliente |
| NC | Devolver o corregir un comprobante emitido | El comprobante original, al que tiene que referirse |
| ND | Aumentar un comprobante emitido | Lo mismo |
| FEC | Comprarle a quien no es contribuyente | Es una compra: la emite el negocio como comprador |
| REP | Cobrar una venta a crédito con el IVA diferido | Una venta a crédito, que el POS todavía no hace |

Ofrecerlos todos al cobrar sería ofrecer siete opciones de las cuales cuatro
Hacienda rechaza siempre: una nota sin el documento que modifica, o un recibo de
pago sin la venta a crédito que cobra, no tienen con qué armarse.

**RN-88.** **Cada compañía elige qué comprobantes emite.** El sistema es para
cualquier negocio y no para uno: un supermercado no exporta, una distribuidora
no emite tiquetes, una ferretería le compra a quien no factura. Los siete se ven
en Configuración y cada flujo muestra solo los que la compañía encendió. Nacen
encendidos los cuatro que Hacienda pide para certificarse y para operar —TE,
FE, NC y ND—, y apagados la FEE y la FEC.

Tres límites, y los tres son para que la configuración no pueda dejar al negocio
sin salida:

- **Al menos uno de TE y FE.** Con los dos apagados no se podría vender.
- **La NC no se apaga.** Devolver una venta emitida tiene que pasar por una nota
  de crédito; sin ella, la devolución no tendría respaldo fiscal.
- **Lo que todavía no tiene flujo se ve pero no se mueve**, con el motivo.
  Desde F7 es solo el REP, hasta que exista la venta a crédito: la ND, la FEE y
  la FEC ya tienen el suyo. Moverlo antes sería una casilla que promete algo que
  no pasa.

**RN-89.** **Una nota siempre referencia un comprobante emitido**, y lo que
decide si hay nota es **el comprobante original, no la configuración de hoy**.
Devolver algo de una venta que salió como tiquete o factura emite una NC aunque
después se haya apagado la facturación; devolver algo de una venta que no fue
comprobante no emite nada, porque no hay qué referenciar.

El motivo es el del catálogo de Hacienda y lo pone el flujo, no el cajero:

- **Devolver mercadería** es el `06` —devolución de mercancía—, entera o parcial.
- **Anular** es el `01`, y solo existe entero: se anula el comprobante completo,
  y solo si todavía no tiene devoluciones. Un comprobante a medio devolver ya no
  se puede anular; lo que quede se devuelve.

Anular y devolver todo reponen lo mismo y reembolsan lo mismo; lo que cambia es
lo que se le dice a Hacienda. Anular es «este comprobante no debió existir»
—el cliente equivocado, el tipo equivocado—; devolver es «la venta existió y la
mercadería volvió».

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

### Lo que el comprobante tiene que poder decir

Sale de leer el anexo y los 23 comprobantes de ejemplo; el detalle, con la cita
de cada regla, está en
[`docs/hacienda/costa-rica/casos-de-emision.md`](../docs/hacienda/costa-rica/casos-de-emision.md).
Son los campos sin los cuales hay negocios enteros que no se pueden facturar.

- **RF-65** Cada línea declara **el código de tarifa de Hacienda**, no solo el
  porcentaje. El 4 % de un servicio de salud y el 4 % transitorio de una nota de
  crédito son el mismo número y códigos distintos (`04` y `06`), y el POS hoy
  solo guarda el número. RN-76.
- **RF-66** Un comprobante lleva **hasta cuatro medios de pago** con su monto
  cada uno. Hoy la venta guarda uno solo. RN-77.
- **RF-67** Un cliente puede tener una **exoneración** con su tipo de documento,
  número, institución, artículo e inciso, fecha y **puntos de tarifa
  exonerados**; al facturarle, la línea la aplica. RN-78.
- **RF-68** Cuando se facturan **servicios de salud pagados con tarjeta**, el
  comprobante declara el **IVA devuelto**. RN-79.
- **RF-69** Cada producto tiene su **unidad de medida** del catálogo de Hacienda,
  que no son solo unidades del SI: incluye `Os` (otro tipo de servicio), `Al` y
  `Alc` (alquileres) y `Acv` (activo virtual). Ya es T-620; acá queda su
  requisito.
- **RF-70** Un cliente puede tener un **protocolo de comprador**: los datos que
  ese comprador exige en el comprobante —código de proveedor, GLN, orden de
  compra, número de recepción— y dónde van. El sistema los **copia**, no los
  deduce. RN-80.
- **RF-71** Además de FE, TE, NC y ND, el sistema emite **FEE** (exportación),
  **FEC** (compra a no contribuyente) y **REP** (recibo de pago). RN-81.
- **RF-72** La pantalla de facturas muestra, de cada comprobante: **el XML que
  se envió**, **la respuesta de Hacienda**, **por dónde va** —numerado, firmado,
  enviado, aceptado o rechazado, con la hora de cada paso— y un botón que
  **genera la representación impresa al vuelo**. Los dos XML se ven y se
  descargan; el PDF no se guarda. RN-82.
- **RF-73** La ubicación del emisor se registra **con los códigos de Hacienda**
  —provincia, cantón y distrito numerados, otras señas obligatorias y barrio
  opcional—, en Configuración y en el alta de una compañía. Y el **correo del
  emisor es obligatorio**. RN-83.
- **RF-74** La pantalla de cobro **muestra y deja elegir el tipo de
  comprobante** —tiquete o factura electrónica— antes de cobrar. La factura no se
  ofrece sin cliente, y el servidor la rechaza si llega sin él. El historial de
  facturas muestra el tipo de cada venta. RN-85.
- **RF-75** Las tres plantillas imprimen el **bloque fiscal**: el tipo, el
  consecutivo y la clave juntos, la actividad económica del emisor y la leyenda
  que corresponda —pendiente de emisión, pruebas sin efecto fiscal, o la
  resolución que autoriza y dónde se verifica—, y el resto de lo que RN-86 lista:
  la condición de venta, la moneda, el CABYS y la unidad de cada línea, la
  identificación con su tipo, el resumen de Hacienda y el monto en letras. No hay
  otro documento impreso fuera de las plantillas. RN-86, RN-17.
- **RF-76** Devolver mercadería de una venta que se emitió como comprobante
  **emite una nota de crédito** con motivo «devolución de mercancía» que la
  referencia, y **anular** desde la factura abierta emite una con motivo
  «anula». Las dos se imprimen con la referencia al original. Una venta sin
  comprobante no emite nota. RN-87, RN-89.
- **RF-77** Desde la factura abierta se puede emitir una **nota de débito** —y una
  nota de crédito por un monto, sin mercadería de por medio— sobre ese
  comprobante, con su motivo del catálogo de Hacienda y su monto. **La plata se
  mueve en el momento**: la nota de débito se cobra al emitirla, con su medio de
  pago, y la de crédito se reembolsa de la gaveta, como una devolución. Las dos
  aparecen en el arqueo del turno, en las ventas netas y en el asiento. Decidido
  por el usuario el 2026-09-26: sin venta a crédito no hay saldo del cliente
  donde dejarlas. RN-87, RN-89.
- **RF-78** Al cobrar a un **cliente del extranjero** se ofrece la **factura de
  exportación**, y no se emite mientras alguna **mercancía** de la venta no tenga
  su partida arancelaria o el cliente su dirección extranjera: se dice cuál
  falta. Los servicios no llevan partida, y por eso el XSD la deja opcional.
  RN-87.
- **RF-79** Registrar una compra a un proveedor **no contribuyente** emite la
  **factura electrónica de compra**, con el negocio como comprador. RN-87.
- **RF-80** Cobrar una venta a crédito con el IVA diferido emite el **recibo
  electrónico de pago**. Depende de que exista la venta a crédito, que hoy no
  está en el alcance. RN-81, RN-87.
- **RF-81** En Configuración, **«Comprobantes que emite este negocio»**: los siete,
  con los límites de RN-88. El cobro, la factura abierta y las compras muestran
  solo los encendidos. RN-88.

### Módulos por plan

- **RF-39** Soporte ve y edita qué módulos incluye cada plan, y el listado de
  compañías (RF-5) muestra los de cada una.
- **RF-40** El POS muestra en la navegación solo los módulos del plan, y toda
  escritura de un módulo fuera del plan responde con el código
  `module_not_in_plan`. Las lecturas siguen (RN-50).

### Compras y cuentas por pagar

- **RF-41** Proveedores: alta y edición con tipo y número de identificación de
  Hacienda, correo, teléfono y condición de pago habitual. Se desactivan, no
  se borran.
- **RF-42** Registrar una compra desde el XML de Hacienda —proveedor,
  documento, condición de pago y líneas con su impuesto salen del archivo, y
  el proveedor se crea si no existe—, desde Excel o a mano, con vista previa
  antes de confirmar (§8, regla 6).
- **RF-43** Aviso cuando la tarifa de una línea del documento difiere de la del
  producto. RN-53.
- **RF-44** Cuentas por pagar: saldo por proveedor y por compra, abonos con
  método y fecha del servidor, y antigüedad de saldos (0–30, 31–60, 61–90, más
  de 90 días).
- **RF-45** Reporte de compras por periodo con base e impuesto **por tarifa**:
  el crédito fiscal del mes.
- **RF-46** Anular una compra sin abonos, con motivo y bitácora. RN-57.

### Contabilidad

- **RF-47** Activar contabilidad: elegir la plantilla de catálogo, la fecha de
  inicio y los saldos iniciales. Siembra el catálogo y el mapeo por omisión y
  escribe el asiento de apertura. RN-60.
- **RF-48** Catálogo de cuentas: ver, crear, renombrar, desactivar; las de
  sistema se distinguen. RN-64.
- **RF-49** Mapeo evento → cuentas, editable, con lo que falta en rojo y el
  saldo de «por clasificar» a la vista.
- **RF-50** Asientos automáticos por venta —según su método de pago—,
  devolución, cierre de caja con su diferencia, movimiento de caja, compra y
  abono a proveedor. Cada asiento enlaza al documento que lo originó.
- **RF-51** Asientos manuales y de ajuste, con quién y cuándo; los de ajuste
  referencian al asiento que corrigen. RN-61.
- **RF-52** Cerrar el mes, con el resumen del periodo a la vista, confirmación
  y bitácora. El siguiente queda abierto.
- **RF-53** Libro diario, mayor por cuenta, balance de comprobación, estado de
  resultados y balance general por periodo, exportables a CSV.
- **RF-54** Borrador del D-104: base e impuesto por tarifa de ventas y compras
  del mes, y el saldo a pagar o a favor. RN-65.

### Planilla

- **RF-55** Empleados: alta con los datos que piden la CCSS y el INS (RN-72) y
  cuenta bancaria, contrato (salario del periodo, jornada, puesto y póliza),
  enlace opcional a un usuario, y baja con fecha y causa. RN-72.
- **RF-56** Tablas de tasas, tramos y créditos con vigencia, visibles para la
  compañía con su fecha y fuente. Las actualiza soporte para todos; la compañía
  solo edita lo que es suyo: su número patronal de la CCSS, la póliza y la prima
  de riesgos del trabajo del INS y el aporte a la asociación solidarista. RN-67.
- **RF-57** Corrida: crear para una jornada y una fecha de corte, tomar las
  acciones de personal del periodo, calcular, ver por empleado el bruto, cada
  rubro obrero, la renta, cada deducción, el neto y el costo patronal, aprobar
  y pagar. RN-66, RN-68, RN-90.
- **RF-58** Boleta de pago imprimible por empleado, con la plantilla de
  documento de la compañía.
- **RF-59** Aguinaldo: corrida especial con el cálculo por empleado y lo
  devengado que lo respalda. RN-69.
- **RF-60** Vacaciones: saldo por empleado y registro de días disfrutados o
  pagados. RN-70.
- **RF-61** Liquidación al dar de baja: desglose por rubro según la causa, e
  impresión. RN-71.
- **RF-62** Archivo de la planilla del mes para la CCSS —ingresos, salarios,
  incapacidades, permisos, cambios de ocupación y exclusiones— y resumen de
  renta retenida, insumo de la declaración mensual. RN-96.
- **RF-63** Corrida de ajuste sobre una pagada. RN-68.
- **RF-64** Asiento de la corrida pagada cuando contabilidad está activa.
  RN-75.
- **RF-82** Acciones de personal: registrarlas por empleado con sus fechas,
  verlas en su historial con lo que cada corrida aplicó, anular una aplicada y
  suspender una recurrente con motivo. El saldo de cada deducción, a la vista.
  RN-90 a RN-93.
- **RF-83** Jornadas de la compañía: periodicidad, clase, horas por día, día
  de descanso pagado y fechas de corte. Una jornada con corridas pagadas no
  cambia de periodicidad ni de cortes: se crea otra. RN-94.
- **RF-84** Puestos con su código de ocupación de la CCSS y su código del INS.
  RN-95.
- **RF-85** Archivo mensual de la planilla para el INS, uno por póliza. RN-96.
- **RF-86** Importar desde Excel, con vista previa y una plantilla
  descargable: puestos, empleados con su contrato y saldos de apertura.
  RN-97.

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
| **Módulo** | Compras, contabilidad o planilla: lo que un plan incluye o no. Se aplica en el servidor. |
| **Proveedor** | A quién se le compra. Con identificación de Hacienda, porque su factura la lleva. |
| **Cuenta por pagar** | El saldo de una compra a crédito: total menos abonos. |
| **Asiento** | Un movimiento contable: líneas al débito y al crédito que suman igual. |
| **Mapeo** | Qué cuentas usa cada evento del POS al convertirse en asiento. |
| **Por clasificar** | La cuenta a la que va lo que no tiene cuenta en el mapeo. Su saldo es una alerta. |
| **Periodo** | Un mes contable. Abierto se escribe; cerrado, no. |
| **Corrida** | Un cálculo de planilla para un periodo, con las tasas que usó congeladas. |
| **Acción de personal** | Lo que cambia el pago o la situación de un empleado, con fechas: horas extra, incapacidad, deducción, aumento. Vive en el empleado y la corrida la toma (RN-90). Reemplaza a la «novedad» del primer diseño de F12. |
| **Jornada** | Cómo y cuándo se le paga a un grupo de empleados: periodicidad, clase, horas y fechas de corte (RN-94). |
| **Corte** | La fecha en que cierra un periodo de pago. El periodo de una corrida sale de su corte. |
| **Puesto** | El cargo, con su código de ocupación de la CCSS y su código del INS (RN-95). |
| **Saldo de apertura** | Lo que una compañía trae de su sistema anterior: días de vacaciones, devengado para el aguinaldo, salarios para una liquidación, deducciones pendientes (RN-97). |
| **Boleta** | El comprobante de pago que recibe el empleado. |
| **SICERE** | El sistema de la CCSS donde se presenta la planilla. |
| **RT-Virtual** | El sistema del INS donde se presenta la planilla de la póliza de riesgos del trabajo. |
| **D-104** | La declaración mensual del IVA. |

---

## 10. Estado actual

**Construido y verificado** (single-tenant): ventas con ventas en espera, caja
con arqueo, devoluciones con reposición, inventario, entradas por manual/Excel/
XML de Hacienda, clientes, usuarios, reportes, configuración con moneda,
impuesto, marca y tres plantillas de documento.

**Por construir**: lo marcado **RF-22 a RF-26 y RF-29 a RF-38** (F6 y F7), y
los tres módulos por plan, **RF-39 a RF-64** (F10 a F12) y la ampliación de
planilla, **RF-82 a RF-86**. De RF-1 a RF-21 y
RF-27 y RF-28 ya están construidos —F2 a F5 y F8—; el detalle de qué cerró
cada fase está en `progress.json`.

Compras salió de «no entra todavía» el 2026-09-11, no porque cambiara de
prioridad sino porque es **prerrequisito de contabilidad**: el débito fiscal
del IVA ya existe desde F5 y el crédito fiscal sale de las compras.

El **orden de ejecución** es F10 → F11 → F6 → F7 → F12, que no es el de los
números; está argumentado en [plan.md §9](plan.md). Emitir es obligatorio y
por eso mismo todos los prospectos ya lo resolvieron antes de conocernos:
gana ventas lo que nadie está obligado a tener.

**Deuda conocida**: en `progress.json` → `pendientes`.
