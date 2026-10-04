"""
De una venta a un comprobante electrónico 4.4 (T-714 y T-720, RF-65 a RF-71).

**Es dominio porque no depende de nada**: entra una estructura de datos y sale
texto. No abre la base, no sale a la red y no firma —la firma es del adaptador
de Vault, que ya existe—. Si para probarlo hiciera falta levantar algo, estaría
en la capa equivocada.

LOS SIETE COMPROBANTES SON EL MISMO CON PIEZAS DE MENOS
--------------------------------------------------------

FE, ND, NC, TE, FEC, FEE y REP comparten la secuencia y se diferencian en qué
elementos tienen. El recibo de pago es el extremo: su línea son siete campos y
su resumen no lleva baldes. **Esas diferencias son datos, no ramas**: viven en
`PERFILES`, sacadas de los siete XSD uno por uno, y el armador las consulta con
`Perfil.tiene`. Con un `if tipo == "10"` repartido por el archivo, agregar un
tipo sería releerlo entero.

LO QUE ESTE MÓDULO DECIDE Y LO QUE NO
--------------------------------------

Decide **el orden y el formato**, que es donde el XSD no perdona: la secuencia
es fija, y un `PlazoCredito` después de `DetalleServicio` es un rechazo aunque
el dato esté bien. Decide también **la aritmética del resumen**, que el anexo
define campo por campo y que nadie más puede recalcular sin repetirla.

No decide **qué** va adentro. La tarifa llega con su código ya resuelto, la
exoneración con sus puntos, el protocolo del comprador con sus textos. Es
deliberado y es RN-80: lo que el sistema deduce es lo que después nadie puede
explicar cuando el comprador rechaza la factura.

La única excepción es **si la línea es servicio o mercancía**, y no es una
excepción de verdad: lo dice el CABYS. Los códigos que empiezan con 5 a 9 son
servicios y los de 0 a 4 mercancías (anexo pp. 50-52, en la validación de cada
balde). Tenerlo además como campo sería dejar que alguien emitiera un
comprobante donde el código y el balde se contradicen.

LA ARITMÉTICA, QUE ES LA PARTE QUE SE EQUIVOCA SOLA
----------------------------------------------------

Del anexo, pp. 45-47 y 50-55, verificada contra los comprobantes reales de
`docs/hacienda/costa-rica/`:

* ``MontoExoneracion``  = tarifa exonerada × base imponible.
* ``ImpuestoNeto``      = monto del impuesto − exonerado − asumido en fábrica.
* ``MontoTotalLinea``   = subtotal + impuesto neto.
* **Los baldes se llenan con `MontoTotal`, no con el subtotal**: van *antes* del
  descuento. Dos comprobantes aceptados lo enseñan —``MontoTotal`` 100 000,
  descuento 2 500, ``TotalGravado`` **100 000** y ``TotalVentaNeta`` 97 500—.
* **Una línea exonerada se reparte**, no se muda entera: la proporción es
  ``exonerado / impuesto`` y lo que no está exonerado sigue siendo gravado. Con
  9 puntos de 13, de 100 000 van 69 230.76923 al balde exonerado y 30 769.23077
  al gravado. Mandarla entera al exonerado es lo que Hacienda rechaza sin decir
  por qué.
* ``TotalVenta``        = gravado + exento + exonerado + no sujeto.
* ``TotalVentaNeta``    = total venta − descuentos.
* ``TotalComprobante``  = venta neta + impuesto + otros cargos **− IVA
  devuelto**. Ese último término es fácil de olvidar y descuadra justo los
  comprobantes de salud pagados con tarjeta.

LOS DECIMALES NO SON COSMÉTICA
-------------------------------

El XSD declara ``18,5`` para los montos y el anexo repite «13 enteros y 5
decimales» en cada campo. Se emite con cinco **siempre**, incluso cuando sobran:
`113000.00000`, no `113000`. Las cantidades van con tres y las tarifas con dos,
como los ejemplos reales.

Se trabaja en ``Decimal`` de punta a punta. Con ``float``, el 13 % de 8 500 da
1 104.9999999999998 y el resumen deja de cuadrar contra sí mismo por un céntimo,
que es exactamente el rechazo más difícil de leer.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Final, Iterable, Iterator

from .hacienda import FOREIGN, NAMESPACES, RAICES

#: Las condiciones de venta que **no llevan medio de pago** (anexo p. 55, RN-77):
#: crédito, servicios al Estado a crédito y venta a crédito con IVA a 90 días.
SIN_MEDIO_DE_PAGO: Final = ("02", "08", "10")

#: Los códigos de tarifa que no cobran nada. Una línea con uno de estos no es
#: «gravada con cero»: es exenta o no sujeta, y va a otro balde del resumen.
TARIFA_EXENTA: Final = "10"
TARIFA_NO_SUJETA: Final = ("01", "11")

#: Un CABYS que empieza con uno de estos es un servicio (anexo pp. 50-52).
CABYS_DE_SERVICIO: Final = "56789"
#: El código de la factura de exportación, que es la que pide partida y receptor
#: del extranjero.
EXPORTACION: Final = "09"


def is_merchandise(cabys: str | None) -> bool:
    """Mercancía salvo que el CABYS diga servicio: los de 5 a 9 lo son. Sin
    CABYS, mercancía: es lo que vende un mostrador, y de todos modos la línea
    se detiene por el CABYS. (`"" in "56789"` es cierto en Python; por eso la
    vacía se mira aparte.)"""
    primera = (cabys or "")[:1]
    return not primera or primera not in CABYS_DE_SERVICIO

_CENTAVOS = Decimal("0.00001")
_MILESIMAS = Decimal("0.001")
_CENTESIMAS = Decimal("0.01")

_MAXIMOS: Final = {
    "LineaDetalle": 1000,
    "CodigoComercial": 5,
    "Descuento": 5,
    "LineaDetalleSurtido": 20,
    "MedioPago": 4,
    "OtrosCargos": 15,
    "InformacionReferencia": 10,
}


class ComprobanteInvalido(Exception):
    """Lo que el armador no puede construir, con el motivo como código."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


# ------------------------------------------------------------------ el perfil


@dataclass(frozen=True)
class Perfil:
    """Qué lleva cada tipo de comprobante, sacado de su XSD.

    `sin` son los elementos que ese tipo **no tiene**; `exige`, los que en la
    factura son opcionales y ahí no. Un nombre puede ir calificado —
    `"Receptor/Ubicacion"`— cuando la diferencia es de una parte y no de las dos:
    la factura de exportación le quita la ubicación al receptor y se la deja al
    emisor.
    """

    condiciones: tuple[str, ...]
    sin: frozenset[str] = frozenset()
    exige: frozenset[str] = frozenset()

    def tiene(self, elemento: str, dentro: str = "") -> bool:
        return elemento not in self.sin and f"{dentro}/{elemento}" not in self.sin

    def obliga(self, elemento: str, dentro: str = "") -> bool:
        return elemento in self.exige or f"{dentro}/{elemento}" in self.exige


_CV_FACTURA: Final = (
    "01", "02", "03", "04", "05", "06", "07", "08", "10", "12", "13", "14", "15", "99",
)
#: Las notas admiten además la 09 y la 11, que son los pagos de un crédito.
_CV_NOTA: Final = tuple(sorted(_CV_FACTURA + ("09", "11")))
#: El tiquete, la de compra y la de exportación no admiten la 12 (mercancía no
#: nacionalizada) ni las dos de pago.
_CV_SIMPLE: Final = tuple(c for c in _CV_FACTURA if c != "12")
#: El recibo de pago **solo** existe para pagar un crédito.
_CV_RECIBO: Final = ("09", "11")

#: Lo que el emisor tiene que traer siempre que el tipo lo admita.
_EMISOR_COMPLETO: Final = frozenset(
    {"CodigoActividadEmisor", "Emisor/Ubicacion", "CorreoElectronico"}
)

#: Lo que ninguna venta nuestra usa y el tipo tampoco admite. Se listan uno por
#: uno y no por descarte: así el día que Hacienda mueva algo, el `diff` contra
#: el XSD nuevo señala la línea.
_SIN_EXPORTACION: Final = frozenset({"PartidaArancelaria", "MontoExportacion"})

PERFILES: Final[dict[str, Perfil]] = {
    "01": Perfil(
        condiciones=_CV_FACTURA,
        sin=_SIN_EXPORTACION | {"Emisor/OtrasSenasExtranjero"},
        exige=_EMISOR_COMPLETO | {"Receptor"},
    ),
    "02": Perfil(
        condiciones=_CV_NOTA,
        sin=frozenset({"Emisor/OtrasSenasExtranjero"}),
        exige=frozenset({"InformacionReferencia"}),
    ),
    "03": Perfil(
        condiciones=_CV_NOTA,
        sin=frozenset({"Emisor/OtrasSenasExtranjero"}),
        exige=frozenset({"InformacionReferencia"}),
    ),
    "04": Perfil(
        condiciones=_CV_SIMPLE,
        sin=_SIN_EXPORTACION
        | {"CodigoActividadReceptor", "TipoTransaccion", "Emisor/OtrasSenasExtranjero"},
        exige=_EMISOR_COMPLETO,
    ),
    "08": Perfil(
        condiciones=_CV_SIMPLE,
        sin=_SIN_EXPORTACION
        | {
            "Receptor/OtrasSenasExtranjero",
            "DetalleSurtido",
            "IVACobradoFabrica",
            "DatosImpuestoEspecifico",
            "ImpuestoAsumidoEmisorFabrica",
            "TotalImpAsumEmisorFabrica",
            "TotalIVADevuelto",
        },
        exige=frozenset({"CodigoActividadReceptor", "Receptor", "InformacionReferencia"}),
    ),
    "09": Perfil(
        condiciones=_CV_SIMPLE,
        sin=frozenset(
            {
                "CodigoActividadReceptor",
                "Emisor/OtrasSenasExtranjero",
                "Receptor/Ubicacion",
                "BaseImponible",
                "BaseImponibleSurtido",
                "IVACobradoFabrica",
                "IVACobradoFabricaSurtido",
                "DatosImpuestoEspecifico",
                "DatosImpuestoEspecificoSurtido",
                "ImpuestoAsumidoEmisorFabrica",
                "ImpuestoNeto",
                "Exoneracion",
                "TotalImpAsumEmisorFabrica",
                "TotalIVADevuelto",
                "TotalServExonerado",
                "TotalServNoSujeto",
                "TotalMercExonerada",
                "TotalMercNoSujeta",
                "TotalExonerado",
                "TotalNoSujeto",
            }
        ),
        exige=_EMISOR_COMPLETO,
    ),
    "10": Perfil(
        condiciones=_CV_RECIBO,
        # El recibo de pago no describe una venta: la referencia. Por eso se
        # queda sin casi todo, y por eso la lista es tan larga.
        sin=_SIN_EXPORTACION
        | {
            "CodigoActividadEmisor",
            "CodigoActividadReceptor",
            "Registrofiscal8707",
            "NombreComercial",
            "Ubicacion",
            "OtrasSenasExtranjero",
            "Telefono",
            "CondicionVentaOtros",
            "PlazoCredito",
            "CodigoCABYS",
            "CodigoComercial",
            "Cantidad",
            "UnidadMedida",
            "TipoTransaccion",
            "UnidadMedidaComercial",
            "NumeroVINoSerie",
            "RegistroMedicamento",
            "FormaFarmaceutica",
            "DetalleSurtido",
            "PrecioUnitario",
            "Descuento",
            "IVACobradoFabrica",
            "BaseImponible",
            "DatosImpuestoEspecifico",
            "Exoneracion",
            "ImpuestoAsumidoEmisorFabrica",
            "OtrosCargos",
            "Otros",
            "TotalServGravados",
            "TotalServExentos",
            "TotalServExonerado",
            "TotalServNoSujeto",
            "TotalMercanciasGravadas",
            "TotalMercanciasExentas",
            "TotalMercExonerada",
            "TotalMercNoSujeta",
            "TotalGravado",
            "TotalExento",
            "TotalExonerado",
            "TotalNoSujeto",
            "TotalDescuentos",
            "TotalImpAsumEmisorFabrica",
            "TotalIVADevuelto",
            "TotalOtrosCargos",
        },
        exige=frozenset(
            {"Receptor", "CorreoElectronico", "InformacionReferencia", "MedioPago", "Numero"}
        ),
    ),
}

#: Los tipos que este armador sabe construir, por su código en el consecutivo.
#:
#: **El tipo es el código y no una sigla**: es el mismo dato que ocupa las
#: posiciones 9 y 10 del consecutivo, así que tener además un `"FE"` sería tener
#: dos vocabularios para lo mismo y un sitio donde se pueden separar.
ARMABLES: Final = tuple(sorted(PERFILES))


# ----------------------------------------------------------------- las piezas


@dataclass(frozen=True)
class Identificacion:
    tipo: str
    numero: str


@dataclass(frozen=True)
class Ubicacion:
    """Provincia, cantón, distrito y **las otras señas**.

    `OtrasSenas` es obligatorio y `Barrio` no —al revés de lo que parece—. Se
    comprueba acá y no al armar porque una ubicación a medias no es válida en
    ningún contexto: es el mismo criterio que `BranchCode`, que tampoco deja
    existir un código de cuatro dígitos.
    """

    provincia: str
    canton: str
    distrito: str
    otras_senas: str = ""
    barrio: str = ""

    def __post_init__(self) -> None:
        if not self.otras_senas:
            raise ComprobanteInvalido("ubicacion_sin_senas")


@dataclass(frozen=True)
class Parte:
    """Emisor o receptor. El tiquete puede no llevar receptor."""

    nombre: str
    identificacion: Identificacion
    ubicacion: Ubicacion | None = None
    nombre_comercial: str = ""
    telefono: str = ""
    correo: str = ""
    #: Para el receptor de una exportación y el emisor de una de compra.
    otras_senas_extranjero: str = ""
    #: El registro de la ley 8707, solo para quien vende licores.
    registro_fiscal: str = ""


@dataclass(frozen=True)
class Exoneracion:
    """Los puntos de tarifa perdonados, no una tarifa (RN-78)."""

    tipo_documento: str
    numero_documento: str
    nombre_institucion: str
    fecha: str
    puntos: Decimal
    articulo: int | None = None
    inciso: int | None = None
    tipo_documento_otro: str = ""
    nombre_institucion_otros: str = ""


@dataclass(frozen=True)
class ImpuestoEspecifico:
    """El cálculo de un impuesto que no se saca de un porcentaje.

    Combustibles, bebidas alcohólicas, envasadas, jabón, cemento y tabaco se
    cobran por unidad de medida, no sobre el precio.
    """

    cantidad_unidad_medida: Decimal
    impuesto_unidad: Decimal
    porcentaje: Decimal | None = None
    proporcion: Decimal | None = None
    volumen_unidad_consumo: Decimal | None = None


@dataclass(frozen=True)
class Impuesto:
    """Un impuesto de una línea. El código de tarifa llega resuelto (RN-76).

    Una línea lleva de uno a mil: una cerveza paga IVA **y** el específico a las
    bebidas alcohólicas, y los dos van como hermanos dentro de la misma línea.

    Con `tarifa` el monto se calcula sobre la base; sin ella hay que darlo,
    porque un impuesto específico no sale de un porcentaje del precio.
    """

    codigo: str = "01"
    codigo_tarifa: str = ""
    tarifa: Decimal | None = None
    codigo_otro: str = ""
    factor_calculo_iva: Decimal | None = None
    especifico: ImpuestoEspecifico | None = None
    monto: Decimal | None = None
    monto_exportacion: Decimal | None = None
    exoneracion: Exoneracion | None = None

    def __post_init__(self) -> None:
        if self.tarifa is None and self.monto is None:
            raise ComprobanteInvalido("impuesto_sin_monto", self.codigo)

    def monto_sobre(self, base: Decimal) -> Decimal:
        if self.tarifa is None:
            return _redondear(self.monto or Decimal(0))
        return _redondear(base * self.tarifa / 100)

    def exonerado_sobre(self, base: Decimal) -> Decimal:
        if self.exoneracion is None:
            return Decimal(0)
        return _redondear(base * self.exoneracion.puntos / 100)


@dataclass(frozen=True)
class Descuento:
    monto: Decimal
    codigo: str = "01"
    codigo_otro: str = ""
    naturaleza: str = ""


@dataclass(frozen=True)
class CodigoComercial:
    """El código del vendedor, del comprador o del fabricante para el artículo."""

    tipo: str
    codigo: str


@dataclass(frozen=True)
class LineaSurtido:
    """Una de las partes de un surtido: un combo que agrupa varios CABYS.

    Su impuesto **no se suma solo** al de la línea que lo contiene: el surtido
    detalla la composición y la línea declara lo suyo. Deducirlo sería inventar
    justo donde el anexo deja el monto editable.
    """

    cabys: str
    cantidad: Decimal
    unidad: str
    detalle: str
    precio_unitario: Decimal
    impuestos: tuple[Impuesto, ...]
    codigos_comerciales: tuple[CodigoComercial, ...] = ()
    unidad_comercial: str = ""
    descuentos: tuple[Descuento, ...] = ()
    iva_cobrado_fabrica: str = ""

    @property
    def monto_total(self) -> Decimal:
        return _redondear(self.cantidad * self.precio_unitario)

    @property
    def subtotal(self) -> Decimal:
        return _redondear(self.monto_total - _suma(d.monto for d in self.descuentos))


@dataclass(frozen=True)
class Linea:
    """Una línea de detalle.

    En el recibo de pago son siete campos —número, detalle, montos e impuesto—
    y el resto no existe; por eso casi todo tiene valor por omisión. Lo que cada
    tipo exige de verdad lo comprueba `_revisar_lineas`, no la firma de la clase.
    """

    numero: int
    detalle: str
    cabys: str = ""
    cantidad: Decimal = Decimal(1)
    unidad: str = ""
    precio_unitario: Decimal = Decimal(0)
    impuestos: tuple[Impuesto, ...] = ()
    descuentos: tuple[Descuento, ...] = ()
    codigos_comerciales: tuple[CodigoComercial, ...] = ()
    surtido: tuple[LineaSurtido, ...] = ()
    partida_arancelaria: str = ""
    tipo_transaccion: str = ""
    unidad_comercial: str = ""
    series: tuple[str, ...] = ()
    registro_medicamento: str = ""
    forma_farmaceutica: str = ""
    iva_cobrado_fabrica: str = ""
    impuesto_asumido: Decimal = Decimal(0)

    # ---- lo que se calcula, y se calcula una sola vez, acá

    @property
    def es_servicio(self) -> bool:
        """Lo dice el CABYS: 5 a 9 son servicios, 0 a 4 mercancías."""
        return not is_merchandise(self.cabys)

    @property
    def monto_total(self) -> Decimal:
        return _redondear(self.cantidad * self.precio_unitario)

    @property
    def descuento(self) -> Decimal:
        return _suma(d.monto for d in self.descuentos)

    @property
    def subtotal(self) -> Decimal:
        return _redondear(self.monto_total - self.descuento)

    @property
    def base_imponible(self) -> Decimal:
        return self.subtotal

    @property
    def monto_impuesto(self) -> Decimal:
        return _suma(i.monto_sobre(self.base_imponible) for i in self.impuestos)

    @property
    def monto_exonerado(self) -> Decimal:
        return _suma(i.exonerado_sobre(self.base_imponible) for i in self.impuestos)

    @property
    def impuesto_neto(self) -> Decimal:
        return _redondear(self.monto_impuesto - self.monto_exonerado - self.impuesto_asumido)

    @property
    def total_linea(self) -> Decimal:
        return _redondear(self.subtotal + self.impuesto_neto)

    @property
    def proporcion_exonerada(self) -> Decimal:
        """Qué parte de la línea está exonerada: exonerado / impuesto.

        No es la tarifa exonerada sobre la tarifa: con dos impuestos en la misma
        línea, el que manda es cuánto dinero se perdonó de cuánto se cobraba.
        """
        impuesto = self.monto_impuesto
        if not impuesto:
            return Decimal(0)
        return self.monto_exonerado / impuesto

    @property
    def tarifa_iva(self) -> str:
        """El código de tarifa que clasifica la línea, o vacío."""
        for impuesto in self.impuestos:
            if impuesto.codigo_tarifa:
                return impuesto.codigo_tarifa
        return ""


@dataclass(frozen=True)
class MedioPago:
    tipo: str
    monto: Decimal
    detalle: str = ""


@dataclass(frozen=True)
class OtroCargo:
    """Un cargo que no es una línea: servicio de un tercero, timbre, propina."""

    tipo_documento: str
    detalle: str
    monto: Decimal
    tipo_documento_otros: str = ""
    identificacion_tercero: Identificacion | None = None
    nombre_tercero: str = ""
    porcentaje: Decimal | None = None


@dataclass(frozen=True)
class Referencia:
    """A qué documento se refiere este. Obligatoria en NC, ND, FEC y REP."""

    tipo_documento: str
    fecha: str
    numero: str = ""
    tipo_documento_otro: str = ""
    codigo: str = ""
    codigo_otro: str = ""
    razon: str = ""


@dataclass(frozen=True)
class Otro:
    """Un dato de protocolo de comprador. Se copia, no se deduce (RN-80)."""

    texto: str
    codigo: str = ""
    #: `OtroTexto` u `OtroContenido`. El XSD exige todos los primeros antes de
    #: cualquiera de los segundos.
    elemento: str = "OtroTexto"


@dataclass(frozen=True)
class Comprobante:
    tipo: str
    clave: str
    consecutivo: str
    fecha: str
    emisor: Parte
    condicion_venta: str
    lineas: tuple[Linea, ...]
    actividad_emisor: str = ""
    receptor: Parte | None = None
    actividad_receptor: str = ""
    proveedor_sistemas: str = ""
    plazo_credito: int | None = None
    condicion_venta_otros: str = ""
    medios_pago: tuple[MedioPago, ...] = ()
    otros_cargos: tuple[OtroCargo, ...] = ()
    referencias: tuple[Referencia, ...] = ()
    moneda: str = "CRC"
    tipo_cambio: Decimal = Decimal(1)
    otros: tuple[Otro, ...] = ()
    #: RN-79. Se pasa ya calculado: quién sabe cuánto se pagó con tarjeta es la
    #: venta, no el armador. Cuáles CABYS cuentan como salud lo resuelve T-718.
    iva_devuelto: Decimal = Decimal(0)


# ------------------------------------------------------------------- formato


def _redondear(valor: Decimal) -> Decimal:
    return Decimal(valor).quantize(_CENTAVOS, rounding=ROUND_HALF_UP)


def _suma(valores: Iterable[Decimal]) -> Decimal:
    return _redondear(sum(valores, Decimal(0)))


def _monto(valor: Decimal) -> str:
    """Cinco decimales siempre, como pide el anexo."""
    return f"{_redondear(valor):.5f}"


def _cantidad(valor: Decimal) -> str:
    return f"{Decimal(valor).quantize(_MILESIMAS, rounding=ROUND_HALF_UP):.3f}"


def _tarifa(valor: Decimal) -> str:
    return f"{Decimal(valor).quantize(_CENTESIMAS, rounding=ROUND_HALF_UP):.2f}"


def _puntos(valor: Decimal) -> str:
    """Los puntos exonerados van como número, no como porcentaje formateado.

    El anexo lo dice con ejemplos: «la tarifa del 13 % se debe reflejar como 13,
    la del 1 % como 1, o bien la del 0.5 % como 0.5». Así que 4 sale «4» y no
    «4.00».

    El formato `f` es obligatorio y no decoración: `Decimal("10.00").normalize()`
    vale `1E+1`, y diez puntos exonerados saldrían escritos «1E+1».
    """
    return f"{Decimal(valor).quantize(_CENTESIMAS, rounding=ROUND_HALF_UP).normalize():f}"


def _texto(padre: ET.Element, nombre: str, valor: str) -> ET.Element:
    hijo = ET.SubElement(padre, nombre)
    hijo.text = valor
    return hijo


def _escribir_en(nodo: ET.Element, perfil: Perfil, dentro: str = ""):
    """Un escritor que omite lo que el tipo no tiene y lo que no trae dato.

    Llamarlo en el orden del XSD es lo que garantiza la secuencia, y que cada
    elemento se pregunte por sí mismo es lo que evita el `if tipo ==` repartido.
    """

    def va(nombre: str, valor: str) -> None:
        if valor and perfil.tiene(nombre, dentro):
            _texto(nodo, nombre, valor)

    return va


# ------------------------------------------------------------------- totales


@dataclass(frozen=True)
class _Baldes:
    """Los ocho baldes del resumen, más lo que se deriva de ellos."""

    serv_gravados: Decimal = Decimal(0)
    serv_exentos: Decimal = Decimal(0)
    serv_exonerado: Decimal = Decimal(0)
    serv_no_sujeto: Decimal = Decimal(0)
    merc_gravadas: Decimal = Decimal(0)
    merc_exentas: Decimal = Decimal(0)
    merc_exonerada: Decimal = Decimal(0)
    merc_no_sujeta: Decimal = Decimal(0)

    @property
    def gravado(self) -> Decimal:
        return _redondear(self.serv_gravados + self.merc_gravadas)

    @property
    def exento(self) -> Decimal:
        return _redondear(self.serv_exentos + self.merc_exentas)

    @property
    def exonerado(self) -> Decimal:
        return _redondear(self.serv_exonerado + self.merc_exonerada)

    @property
    def no_sujeto(self) -> Decimal:
        return _redondear(self.serv_no_sujeto + self.merc_no_sujeta)

    @property
    def venta(self) -> Decimal:
        return _redondear(self.gravado + self.exento + self.exonerado + self.no_sujeto)


def _reparto_de(linea: Linea) -> dict[str, Decimal]:
    """Cuánto del monto de la línea va a cada estado.

    Devuelve un reparto y no un balde porque **una línea puede estar en dos**:
    la exonerada parcialmente deja en gravado lo que no se le perdonó. La resta
    en vez de un segundo producto es para que las dos partes sumen el monto
    exacto y el resumen no se descuadre por un céntimo.
    """
    monto = linea.monto_total
    if linea.tarifa_iva == TARIFA_EXENTA:
        return {"exento": monto}
    if linea.tarifa_iva in TARIFA_NO_SUJETA:
        return {"no_sujeto": monto}
    exonerado = _redondear(monto * linea.proporcion_exonerada)
    if not exonerado:
        return {"gravado": monto}
    return {"exonerado": exonerado, "gravado": _redondear(monto - exonerado)}


def _sumar_baldes(lineas: Iterable[Linea]) -> _Baldes:
    acumulado = {
        (clase, tipo): Decimal(0)
        for clase in ("gravado", "exento", "exonerado", "no_sujeto")
        for tipo in ("serv", "merc")
    }
    for linea in lineas:
        tipo = "serv" if linea.es_servicio else "merc"
        for clase, monto in _reparto_de(linea).items():
            acumulado[(clase, tipo)] += monto
    return _Baldes(
        serv_gravados=acumulado[("gravado", "serv")],
        serv_exentos=acumulado[("exento", "serv")],
        serv_exonerado=acumulado[("exonerado", "serv")],
        serv_no_sujeto=acumulado[("no_sujeto", "serv")],
        merc_gravadas=acumulado[("gravado", "merc")],
        merc_exentas=acumulado[("exento", "merc")],
        merc_exonerada=acumulado[("exonerado", "merc")],
        merc_no_sujeta=acumulado[("no_sujeto", "merc")],
    )


def _desglose(lineas: Iterable[Linea]) -> list[tuple[str, str, Decimal]]:
    """Un renglón por par (código de impuesto, código de tarifa), con su neto.

    Se suma el **impuesto neto** y no el monto: el anexo lo dice en la p. 53 y es
    lo que hace que una factura toda exonerada declare cero y no el impuesto que
    no se cobró.

    El impuesto asumido en fábrica es de la línea y no de un impuesto, así que
    se le resta al primero. Repartirlo sería inventar; dejarlo fuera haría que
    la suma de los renglones no diera `TotalImpuesto`, y eso Hacienda sí lo
    comprueba.

    **Un impuesto que no cobró nada no tiene renglón, pero uno exonerado sí.**
    Los dos dan cero y la diferencia es real: la línea exenta nunca estuvo
    gravada y la exonerada sí, con el perdón aparte. Los dos comprobantes reales
    lo enseñan —la exportación exenta no trae el nodo y la factura de servicios
    médicos exonerada lo trae en cero— y es la lectura de «obligatorio cuando
    existen productos gravados con algún impuesto» del anexo p. 53.
    """
    orden: list[tuple[str, str]] = []
    montos: dict[tuple[str, str], Decimal] = {}
    cobrado: dict[tuple[str, str], Decimal] = {}
    for linea in lineas:
        for cuantos, impuesto in enumerate(linea.impuestos):
            llave = (impuesto.codigo, impuesto.codigo_tarifa)
            if llave not in montos:
                orden.append(llave)
                montos[llave] = cobrado[llave] = Decimal(0)
            bruto = impuesto.monto_sobre(linea.base_imponible)
            neto = bruto - impuesto.exonerado_sobre(linea.base_imponible)
            if cuantos == 0:
                neto -= linea.impuesto_asumido
            cobrado[llave] += bruto
            montos[llave] += _redondear(neto)
    return [
        (codigo, tarifa, montos[(codigo, tarifa)])
        for codigo, tarifa in orden
        if cobrado[(codigo, tarifa)]
    ]


# -------------------------------------------------------------------- guardas


@dataclass(frozen=True)
class _Cuentas:
    """El resumen ya calculado. Lo usan la guarda y el armado, y por eso existe.

    Comprobar que los medios de pago suman el total exige el total, que se
    calcula al final; tenerlo en una función aparte es lo que evita armar medio
    comprobante para después negarse.
    """

    baldes: _Baldes
    venta: Decimal
    descuentos: Decimal
    renglones: list[tuple[str, str, Decimal]]
    impuesto: Decimal
    asumido: Decimal
    cargos: Decimal
    total: Decimal


def _cuentas(c: Comprobante, p: Perfil) -> _Cuentas:
    baldes = _sumar_baldes(c.lineas)
    # El recibo de pago no tiene baldes: su venta es la suma de las líneas.
    venta = (
        baldes.venta
        if p.tiene("TotalGravado")
        else _suma(linea.monto_total for linea in c.lineas)
    )
    descuentos = _suma(linea.descuento for linea in c.lineas)
    renglones = _desglose(c.lineas)
    impuesto = _suma(monto for _, _, monto in renglones)
    return _Cuentas(
        baldes=baldes,
        venta=venta,
        descuentos=descuentos,
        renglones=renglones,
        impuesto=impuesto,
        asumido=_suma(linea.impuesto_asumido for linea in c.lineas),
        cargos=_suma(cargo.monto for cargo in c.otros_cargos),
        total=_redondear(venta - descuentos + impuesto + _suma(
            cargo.monto for cargo in c.otros_cargos
        ) - c.iva_devuelto),
    )


def _perfil_de(comprobante: Comprobante) -> Perfil:
    perfil = PERFILES.get(comprobante.tipo)
    if perfil is None:
        raise ComprobanteInvalido("tipo_desconocido", comprobante.tipo)
    return perfil


def _cabe(cuantos: int, elemento: str) -> None:
    if cuantos > _MAXIMOS[elemento]:
        raise ComprobanteInvalido("demasiados", elemento)


def _revisar_encabezado(c: Comprobante, p: Perfil) -> None:
    if not c.proveedor_sistemas:
        # Es obligatorio en el XSD, no opcional: la cédula de quien hace el
        # software. Lo destapó el validador, que es para lo que está.
        raise ComprobanteInvalido("falta_proveedor_sistemas")
    if c.condicion_venta not in p.condiciones:
        raise ComprobanteInvalido("condicion_venta_no_valida", c.condicion_venta)
    if c.condicion_venta == "99" and not c.condicion_venta_otros:
        raise ComprobanteInvalido("falta_condicion_venta_otros")
    if p.obliga("CodigoActividadEmisor") and not c.actividad_emisor:
        raise ComprobanteInvalido("falta_actividad_emisor")
    if p.obliga("CodigoActividadReceptor") and not c.actividad_receptor:
        raise ComprobanteInvalido("falta_actividad_receptor")
    if p.obliga("Receptor") and c.receptor is None:
        raise ComprobanteInvalido("falta_receptor")
    # La exportación es para el extranjero no domiciliado (RF-78, T-727): su
    # receptor es un `05` y lleva sus señas de afuera en lugar de la ubicación
    # del país. Se exige acá, para cualquier origen, y no en quien arma el dato.
    if c.tipo == EXPORTACION and c.receptor is not None:
        if c.receptor.identificacion.tipo != FOREIGN:
            raise ComprobanteInvalido("receptor_no_extranjero", c.receptor.identificacion.tipo)
        if not c.receptor.otras_senas_extranjero:
            raise ComprobanteInvalido("receptor_sin_senas_extranjeras")

    # **El emisor y el receptor no piden lo mismo, y la asimetría es del XSD.**
    # De la factura son obligatorios del emisor nombre, identificación,
    # **ubicación y correo**; del receptor, solo nombre e identificación. Tiene
    # sentido: la dirección y el correo del emisor son lo que Hacienda cruza
    # contra el RUT, y del receptor de un tiquete no se sabe ni el nombre.
    if p.obliga("Ubicacion", "Emisor") and c.emisor.ubicacion is None:
        raise ComprobanteInvalido("falta_ubicacion_emisor")
    if p.obliga("CorreoElectronico") and not c.emisor.correo:
        raise ComprobanteInvalido("falta_correo_emisor")

    _cabe(len(c.otros_cargos), "OtrosCargos")
    _cabe(len(c.referencias), "InformacionReferencia")
    if p.obliga("InformacionReferencia") and not c.referencias:
        raise ComprobanteInvalido("falta_referencia", c.tipo)
    if p.obliga("Numero") and any(not r.numero for r in c.referencias):
        raise ComprobanteInvalido("falta_numero_de_referencia")


def _revisar_pago(c: Comprobante, p: Perfil) -> None:
    _cabe(len(c.medios_pago), "MedioPago")
    if c.condicion_venta in SIN_MEDIO_DE_PAGO and c.medios_pago:
        # RN-77. Es más útil negarse acá que mandarlo y leer el rechazo.
        raise ComprobanteInvalido("medio_de_pago_en_credito", c.condicion_venta)
    if p.obliga("MedioPago") and not c.medios_pago:
        raise ComprobanteInvalido("faltan_medios_de_pago")
    if len(c.medios_pago) < 2:
        # Con uno solo Hacienda no lo comprueba, y el monto es opcional.
        return
    total = _cuentas(c, p).total
    if _suma(medio.monto for medio in c.medios_pago) != total:
        # Anexo p. 55: «se verificará que el cálculo coincida con la sumatoria
        # de los montos de los totales por Medio de Pago cuando se utilicen dos
        # o más. Caso contrario se rechazará el comprobante».
        raise ComprobanteInvalido("los_medios_no_suman_el_total", _monto(total))


def _revisar_lineas(c: Comprobante, p: Perfil) -> None:
    if not c.lineas:
        raise ComprobanteInvalido("sin_lineas")
    _cabe(len(c.lineas), "LineaDetalle")
    for linea in c.lineas:
        _cabe(len(linea.codigos_comerciales), "CodigoComercial")
        _cabe(len(linea.descuentos), "Descuento")
        _cabe(len(linea.surtido), "LineaDetalleSurtido")
        if p.tiene("CodigoCABYS") and not linea.cabys:
            raise ComprobanteInvalido("linea_sin_cabys", str(linea.numero))
        # En la exportación cada mercancía lleva su partida arancelaria (RF-78);
        # los servicios no la tienen, y el XSD la deja opcional por eso.
        if c.tipo == EXPORTACION and not linea.es_servicio and not linea.partida_arancelaria:
            raise ComprobanteInvalido("linea_sin_partida", str(linea.numero))
        if p.tiene("UnidadMedida") and not linea.unidad:
            raise ComprobanteInvalido("linea_sin_unidad", str(linea.numero))
        if p.tiene("BaseImponible") and not linea.impuestos:
            # Solo el recibo de pago admite una línea sin impuesto; en los demás
            # el XSD pide uno como mínimo aunque sea de tarifa cero.
            raise ComprobanteInvalido("linea_sin_impuestos", str(linea.numero))


def _lo_que_no_cabe(c: Comprobante) -> Iterator[tuple[str, bool]]:
    """Cada elemento con si el comprobante trae dato para él.

    Es una lista y no un `if` por caso para que agregar un campo nuevo sea
    agregar un renglón: lo que se olvida es siempre la comprobación, no el campo.
    """
    impuestos = [i for linea in c.lineas for i in linea.impuestos]
    yield "CodigoActividadReceptor", bool(c.actividad_receptor)
    yield "CondicionVentaOtros", bool(c.condicion_venta_otros)
    yield "PlazoCredito", c.plazo_credito is not None
    yield "OtrosCargos", bool(c.otros_cargos)
    yield "Otros", bool(c.otros)
    yield "TotalIVADevuelto", bool(c.iva_devuelto)
    yield "PartidaArancelaria", any(l.partida_arancelaria for l in c.lineas)
    yield "TipoTransaccion", any(l.tipo_transaccion for l in c.lineas)
    yield "Descuento", any(l.descuentos for l in c.lineas)
    yield "DetalleSurtido", any(l.surtido for l in c.lineas)
    yield "IVACobradoFabrica", any(l.iva_cobrado_fabrica for l in c.lineas)
    yield "ImpuestoAsumidoEmisorFabrica", any(l.impuesto_asumido for l in c.lineas)
    yield "Exoneracion", any(i.exoneracion is not None for i in impuestos)
    yield "DatosImpuestoEspecifico", any(i.especifico is not None for i in impuestos)
    yield "MontoExportacion", any(i.monto_exportacion is not None for i in impuestos)


def _revisar_lo_que_no_va(c: Comprobante, p: Perfil) -> None:
    for elemento, hay_dato in _lo_que_no_cabe(c):
        if hay_dato and not p.tiene(elemento):
            raise ComprobanteInvalido("no_va_en_este_tipo", elemento)
    baldes = _sumar_baldes(c.lineas)
    # La exportación no tiene balde de no sujeto: una línea con tarifa 01 u 11
    # desaparecería del resumen y `TotalVenta` dejaría de cuadrar.
    if baldes.no_sujeto and not p.tiene("TotalNoSujeto"):
        raise ComprobanteInvalido("no_va_en_este_tipo", "TotalNoSujeto")


# -------------------------------------------------------------------- armado


def construir(comprobante: Comprobante) -> str:
    """El XML del comprobante, sin firmar, listo para que lo firme Vault."""
    perfil = _perfil_de(comprobante)
    _revisar_encabezado(comprobante, perfil)
    # Las líneas antes del pago: comprobar que los medios suman el total exige
    # que los totales se puedan calcular.
    _revisar_lineas(comprobante, perfil)
    _revisar_pago(comprobante, perfil)
    _revisar_lo_que_no_va(comprobante, perfil)

    espacio = NAMESPACES[comprobante.tipo]
    ET.register_namespace("", espacio)
    raiz = ET.Element(f"{{{espacio}}}{RAICES[comprobante.tipo]}")
    va = _escribir_en(raiz, perfil)

    va("Clave", comprobante.clave)
    va("ProveedorSistemas", comprobante.proveedor_sistemas)
    va("CodigoActividadEmisor", comprobante.actividad_emisor)
    va("CodigoActividadReceptor", comprobante.actividad_receptor)
    va("NumeroConsecutivo", comprobante.consecutivo)
    va("FechaEmision", comprobante.fecha)

    _parte(raiz, "Emisor", comprobante.emisor, perfil)
    if comprobante.receptor is not None:
        _parte(raiz, "Receptor", comprobante.receptor, perfil)

    va("CondicionVenta", comprobante.condicion_venta)
    va("CondicionVentaOtros", comprobante.condicion_venta_otros)
    if comprobante.plazo_credito is not None:
        va("PlazoCredito", str(comprobante.plazo_credito))

    detalle = ET.SubElement(raiz, "DetalleServicio")
    for linea in comprobante.lineas:
        _linea(detalle, linea, perfil)

    for cargo in comprobante.otros_cargos:
        _otro_cargo(raiz, cargo)

    _resumen(raiz, comprobante, perfil)

    for referencia in comprobante.referencias:
        _referencia(raiz, referencia)

    _otros(raiz, comprobante.otros)

    return ET.tostring(raiz, encoding="unicode", xml_declaration=True)


def _parte(padre: ET.Element, nombre: str, parte: Parte, perfil: Perfil) -> None:
    nodo = ET.SubElement(padre, nombre)
    va = _escribir_en(nodo, perfil, nombre)

    va("Nombre", parte.nombre)
    ident = ET.SubElement(nodo, "Identificacion")
    _texto(ident, "Tipo", parte.identificacion.tipo)
    _texto(ident, "Numero", parte.identificacion.numero)
    va("Registrofiscal8707", parte.registro_fiscal)
    va("NombreComercial", parte.nombre_comercial)

    if parte.ubicacion is not None and perfil.tiene("Ubicacion", nombre):
        ubi = ET.SubElement(nodo, "Ubicacion")
        _texto(ubi, "Provincia", parte.ubicacion.provincia)
        _texto(ubi, "Canton", parte.ubicacion.canton)
        _texto(ubi, "Distrito", parte.ubicacion.distrito)
        if parte.ubicacion.barrio:
            _texto(ubi, "Barrio", parte.ubicacion.barrio)
        _texto(ubi, "OtrasSenas", parte.ubicacion.otras_senas)

    va("OtrasSenasExtranjero", parte.otras_senas_extranjero)
    if parte.telefono and perfil.tiene("Telefono", nombre):
        tel = ET.SubElement(nodo, "Telefono")
        _texto(tel, "CodigoPais", "506")
        _texto(tel, "NumTelefono", parte.telefono)
    va("CorreoElectronico", parte.correo)


def _linea(padre: ET.Element, linea: Linea, perfil: Perfil) -> None:
    nodo = ET.SubElement(padre, "LineaDetalle")
    va = _escribir_en(nodo, perfil)

    va("NumeroLinea", str(linea.numero))
    va("PartidaArancelaria", linea.partida_arancelaria)
    va("CodigoCABYS", linea.cabys)
    for comercial in linea.codigos_comerciales:
        _codigo_comercial(nodo, "CodigoComercial", comercial.tipo, comercial.codigo)
    va("Cantidad", _cantidad(linea.cantidad))
    va("UnidadMedida", linea.unidad)
    va("TipoTransaccion", linea.tipo_transaccion)
    va("UnidadMedidaComercial", linea.unidad_comercial)
    va("Detalle", linea.detalle)
    for serie in linea.series:
        _texto(nodo, "NumeroVINoSerie", serie)
    va("RegistroMedicamento", linea.registro_medicamento)
    va("FormaFarmaceutica", linea.forma_farmaceutica)

    if linea.surtido:
        surtido = ET.SubElement(nodo, "DetalleSurtido")
        for pedazo in linea.surtido:
            _surtido(surtido, pedazo, perfil)

    va("PrecioUnitario", _monto(linea.precio_unitario))
    va("MontoTotal", _monto(linea.monto_total))
    for descuento in linea.descuentos:
        _descuento(nodo, descuento, "")
    va("SubTotal", _monto(linea.subtotal))
    va("IVACobradoFabrica", linea.iva_cobrado_fabrica)
    va("BaseImponible", _monto(linea.base_imponible))
    for impuesto in linea.impuestos:
        _impuesto(nodo, impuesto, linea.base_imponible, perfil)
    if perfil.tiene("ImpuestoAsumidoEmisorFabrica"):
        _texto(nodo, "ImpuestoAsumidoEmisorFabrica", _monto(linea.impuesto_asumido))
    va("ImpuestoNeto", _monto(linea.impuesto_neto))
    va("MontoTotalLinea", _monto(linea.total_linea))


def _codigo_comercial(padre: ET.Element, nombre: str, tipo: str, codigo: str) -> None:
    nodo = ET.SubElement(padre, nombre)
    _texto(nodo, f"Tipo{'Surtido' if nombre.endswith('Surtido') else ''}", tipo)
    _texto(nodo, f"Codigo{'Surtido' if nombre.endswith('Surtido') else ''}", codigo)


def _descuento(padre: ET.Element, descuento: Descuento, sufijo: str) -> None:
    nodo = ET.SubElement(padre, f"Descuento{sufijo}")
    _texto(nodo, f"MontoDescuento{sufijo}", _monto(descuento.monto))
    _texto(nodo, f"CodigoDescuento{sufijo}", descuento.codigo)
    if descuento.codigo_otro:
        # El XSD lo llama `CodigoDescuentoOTRO` en la línea y
        # `DescuentoSurtidoOtros` en el surtido. Dos nombres para lo mismo son
        # de Hacienda, no nuestros.
        _texto(
            nodo,
            "DescuentoSurtidoOtros" if sufijo else "CodigoDescuentoOTRO",
            descuento.codigo_otro,
        )
    if descuento.naturaleza and not sufijo:
        _texto(nodo, "NaturalezaDescuento", descuento.naturaleza)


def _surtido(padre: ET.Element, parte: LineaSurtido, perfil: Perfil) -> None:
    nodo = ET.SubElement(padre, "LineaDetalleSurtido")
    va = _escribir_en(nodo, perfil)

    _texto(nodo, "CodigoCABYSSurtido", parte.cabys)
    for comercial in parte.codigos_comerciales:
        _codigo_comercial(nodo, "CodigoComercialSurtido", comercial.tipo, comercial.codigo)
    _texto(nodo, "CantidadSurtido", _cantidad(parte.cantidad))
    _texto(nodo, "UnidadMedidaSurtido", parte.unidad)
    va("UnidadMedidaComercialSurtido", parte.unidad_comercial)
    _texto(nodo, "DetalleSurtido", parte.detalle)
    _texto(nodo, "PrecioUnitarioSurtido", _monto(parte.precio_unitario))
    _texto(nodo, "MontoTotalSurtido", _monto(parte.monto_total))
    for descuento in parte.descuentos:
        _descuento(nodo, descuento, "Surtido")
    _texto(nodo, "SubTotalSurtido", _monto(parte.subtotal))
    va("IVACobradoFabricaSurtido", parte.iva_cobrado_fabrica)
    va("BaseImponibleSurtido", _monto(parte.subtotal))
    for impuesto in parte.impuestos:
        _impuesto(nodo, impuesto, parte.subtotal, perfil, sufijo="Surtido")


def _impuesto(
    padre: ET.Element,
    impuesto: Impuesto,
    base: Decimal,
    perfil: Perfil,
    sufijo: str = "",
) -> None:
    nodo = ET.SubElement(padre, f"Impuesto{sufijo}")
    va = _escribir_en(nodo, perfil)

    _texto(nodo, f"Codigo{'Impuesto' if sufijo else ''}{sufijo}", impuesto.codigo)
    if impuesto.codigo_otro:
        _texto(nodo, f"CodigoImpuestoOTRO{sufijo}", impuesto.codigo_otro)
    if impuesto.codigo_tarifa:
        _texto(nodo, f"CodigoTarifaIVA{sufijo}", impuesto.codigo_tarifa)
    if impuesto.tarifa is not None:
        _texto(nodo, f"Tarifa{sufijo}", _tarifa(impuesto.tarifa))
    if impuesto.factor_calculo_iva is not None and not sufijo:
        # El surtido no lo tiene: su impuesto es una versión corta del de la
        # línea, no el mismo tipo.
        _texto(nodo, "FactorCalculoIVA", _tarifa(impuesto.factor_calculo_iva))
    if impuesto.especifico is not None:
        _especifico(nodo, impuesto.especifico, sufijo)
    _texto(nodo, f"Monto{'Impuesto' if sufijo else ''}{sufijo}", _monto(impuesto.monto_sobre(base)))
    if impuesto.monto_exportacion is not None:
        va("MontoExportacion", _monto(impuesto.monto_exportacion))
    if impuesto.exoneracion is not None:
        _exoneracion(nodo, impuesto.exoneracion, impuesto.exonerado_sobre(base))


def _especifico(padre: ET.Element, datos: ImpuestoEspecifico, sufijo: str) -> None:
    nodo = ET.SubElement(padre, f"DatosImpuestoEspecifico{sufijo}")
    _texto(nodo, f"CantidadUnidadMedida{sufijo}", _tarifa(datos.cantidad_unidad_medida))
    if datos.porcentaje is not None:
        _texto(nodo, f"Porcentaje{sufijo}", _tarifa(datos.porcentaje))
    if datos.proporcion is not None:
        _texto(nodo, f"Proporcion{sufijo}", _tarifa(datos.proporcion))
    if datos.volumen_unidad_consumo is not None:
        _texto(nodo, f"VolumenUnidadConsumo{sufijo}", _tarifa(datos.volumen_unidad_consumo))
    _texto(nodo, f"ImpuestoUnidad{sufijo}", _monto(datos.impuesto_unidad))


def _exoneracion(padre: ET.Element, exo: Exoneracion, monto: Decimal) -> None:
    nodo = ET.SubElement(padre, "Exoneracion")
    _texto(nodo, "TipoDocumentoEX1", exo.tipo_documento)
    if exo.tipo_documento_otro:
        _texto(nodo, "TipoDocumentoOTRO", exo.tipo_documento_otro)
    _texto(nodo, "NumeroDocumento", exo.numero_documento)
    if exo.articulo is not None:
        _texto(nodo, "Articulo", str(exo.articulo))
    if exo.inciso is not None:
        _texto(nodo, "Inciso", str(exo.inciso))
    _texto(nodo, "NombreInstitucion", exo.nombre_institucion)
    if exo.nombre_institucion_otros:
        _texto(nodo, "NombreInstitucionOtros", exo.nombre_institucion_otros)
    _texto(nodo, "FechaEmisionEX", exo.fecha)
    _texto(nodo, "TarifaExonerada", _puntos(exo.puntos))
    _texto(nodo, "MontoExoneracion", _monto(monto))


def _otro_cargo(padre: ET.Element, cargo: OtroCargo) -> None:
    nodo = ET.SubElement(padre, "OtrosCargos")
    _texto(nodo, "TipoDocumentoOC", cargo.tipo_documento)
    if cargo.tipo_documento_otros:
        _texto(nodo, "TipoDocumentoOTROS", cargo.tipo_documento_otros)
    if cargo.identificacion_tercero is not None:
        ident = ET.SubElement(nodo, "IdentificacionTercero")
        _texto(ident, "Tipo", cargo.identificacion_tercero.tipo)
        _texto(ident, "Numero", cargo.identificacion_tercero.numero)
    if cargo.nombre_tercero:
        _texto(nodo, "NombreTercero", cargo.nombre_tercero)
    _texto(nodo, "Detalle", cargo.detalle)
    if cargo.porcentaje is not None:
        _texto(nodo, "PorcentajeOC", _monto(cargo.porcentaje))
    _texto(nodo, "MontoCargo", _monto(cargo.monto))


def _resumen(padre: ET.Element, comprobante: Comprobante, perfil: Perfil) -> None:
    nodo = ET.SubElement(padre, "ResumenFactura")
    va = _escribir_en(nodo, perfil)

    moneda = ET.SubElement(nodo, "CodigoTipoMoneda")
    _texto(moneda, "CodigoMoneda", comprobante.moneda)
    _texto(moneda, "TipoCambio", _monto(comprobante.tipo_cambio))

    cuentas = _cuentas(comprobante, perfil)
    baldes = cuentas.baldes

    # **Un balde en cero no se emite.** Los doce son opcionales en el XSD y los
    # comprobantes reales traen tanto los doce como solo los que tienen algo.
    # Emitir doce ceros valida igual, pero hace ilegible la parte del
    # comprobante que una persona sí lee cuando algo no cuadra.
    for nombre, valor in (
        ("TotalServGravados", baldes.serv_gravados),
        ("TotalServExentos", baldes.serv_exentos),
        ("TotalServExonerado", baldes.serv_exonerado),
        ("TotalServNoSujeto", baldes.serv_no_sujeto),
        ("TotalMercanciasGravadas", baldes.merc_gravadas),
        ("TotalMercanciasExentas", baldes.merc_exentas),
        ("TotalMercExonerada", baldes.merc_exonerada),
        ("TotalMercNoSujeta", baldes.merc_no_sujeta),
        ("TotalGravado", baldes.gravado),
        ("TotalExento", baldes.exento),
        ("TotalExonerado", baldes.exonerado),
        ("TotalNoSujeto", baldes.no_sujeto),
    ):
        if valor:
            va(nombre, _monto(valor))

    _texto(nodo, "TotalVenta", _monto(cuentas.venta))
    if cuentas.descuentos:
        va("TotalDescuentos", _monto(cuentas.descuentos))
    _texto(nodo, "TotalVentaNeta", _monto(cuentas.venta - cuentas.descuentos))

    for codigo, tarifa, monto in cuentas.renglones:
        bloque = ET.SubElement(nodo, "TotalDesgloseImpuesto")
        _texto(bloque, "Codigo", codigo)
        if tarifa:
            _texto(bloque, "CodigoTarifaIVA", tarifa)
        _texto(bloque, "TotalMontoImpuesto", _monto(monto))
    if cuentas.renglones:
        # Ya viene con el asumido en fábrica descontado: el desglose lo restó
        # renglón por renglón, y `TotalImpuesto` es su suma. Va aunque sume
        # cero —una factura toda exonerada lo declara en cero— y no va cuando
        # no hubo renglones, que es cuando nada estuvo gravado.
        _texto(nodo, "TotalImpuesto", _monto(cuentas.impuesto))
    if cuentas.asumido:
        va("TotalImpAsumEmisorFabrica", _monto(cuentas.asumido))

    if comprobante.iva_devuelto:
        va("TotalIVADevuelto", _monto(comprobante.iva_devuelto))

    if cuentas.cargos:
        va("TotalOtrosCargos", _monto(cuentas.cargos))

    for medio in comprobante.medios_pago:
        bloque = ET.SubElement(nodo, "MedioPago")
        _texto(bloque, "TipoMedioPago", medio.tipo)
        if medio.detalle:
            _texto(bloque, "MedioPagoOtros", medio.detalle)
        _texto(bloque, "TotalMedioPago", _monto(medio.monto))

    _texto(nodo, "TotalComprobante", _monto(cuentas.total))


def _referencia(padre: ET.Element, referencia: Referencia) -> None:
    nodo = ET.SubElement(padre, "InformacionReferencia")
    _texto(nodo, "TipoDocIR", referencia.tipo_documento)
    if referencia.tipo_documento_otro:
        _texto(nodo, "TipoDocRefOTRO", referencia.tipo_documento_otro)
    if referencia.numero:
        _texto(nodo, "Numero", referencia.numero)
    _texto(nodo, "FechaEmisionIR", referencia.fecha)
    if referencia.codigo:
        _texto(nodo, "Codigo", referencia.codigo)
    if referencia.codigo_otro:
        _texto(nodo, "CodigoReferenciaOTRO", referencia.codigo_otro)
    if referencia.razon:
        _texto(nodo, "Razon", referencia.razon)


def _otros(padre: ET.Element, otros: tuple[Otro, ...]) -> None:
    # Que el recibo de pago no los admita ya lo negó `_revisar_lo_que_no_va`.
    if not otros:
        return
    nodo = ET.SubElement(padre, "Otros")
    # Todos los `OtroTexto` antes de cualquier `OtroContenido`: lo exige la
    # secuencia del XSD y es de los errores que solo aparecen al validar.
    for elemento in ("OtroTexto", "OtroContenido"):
        for otro in otros:
            if otro.elemento != elemento:
                continue
            hijo = _texto(nodo, elemento, otro.texto)
            if otro.codigo:
                hijo.set("codigo", otro.codigo)


__all__ = [
    "ARMABLES",
    "CodigoComercial",
    "Comprobante",
    "ComprobanteInvalido",
    "Descuento",
    "Exoneracion",
    "Identificacion",
    "Impuesto",
    "ImpuestoEspecifico",
    "Linea",
    "LineaSurtido",
    "MedioPago",
    "Otro",
    "OtroCargo",
    "PERFILES",
    "Parte",
    "Perfil",
    "Referencia",
    "SIN_MEDIO_DE_PAGO",
    "Ubicacion",
    "construir",
]
