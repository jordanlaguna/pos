"""
El protocolo de comprador (T-719, RF-70, RN-80).

QUÉ ES UN PROTOCOLO
--------------------

Los grandes compradores exigen que la factura traiga datos suyos —el número de
proveedor que le asignaron a uno, la orden de compra, un GLN— en un sitio
concreto del XML. No los pide Hacienda: los pide el comprador, y si no van, la
factura se acepta en Hacienda y **la rechaza el comprador** semanas después,
cuando no encuentra contra qué conciliarla.

Cada comprador los quiere en su sitio y con su formato:

* Walmart, en `Otros/OtroTexto` con `codigo="WMNumeroVendedor"`.
* El ICE, en `InformacionReferencia` con `TipoDocIR=99` y un número `MM-45000…`.
* El BCCR, en `Otros/OtroContenido` con un texto `BCCR_ORDEN_PEDIDO=…`.

ES DATO Y NO CÓDIGO
--------------------

Un `if cliente.es_walmart` por comprador es una versión nueva cada vez que un
cliente cambia su portal de proveedores. Acá el protocolo es una lista de
**entradas**: dónde va, con qué código, y una plantilla con marcadores. Los
veinticinco protocolos relevados en `docs/…/protocolos-especiales-matriz.md` se
expresan así, sin tocar código.

EL SISTEMA NO INVENTA NINGUNO (RN-80)
--------------------------------------

Una plantilla pide marcadores; si alguno no tiene valor, **esa entrada no se
emite y el marcador se reporta**. Las dos mitades importan: emitir
`BCCR_ORDEN_PEDIDO=` vacío es mandar un dato falso, y callarse que faltó es
emitir una factura que el comprador va a rechazar sin que nadie se enterara. Lo
que hace quien llama con esa lista —negarse a emitir o avisar— es decisión suya;
acá se le dice qué falta.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final, Mapping

from .errors import DomainError
from .fe_xml import Otro, Referencia

#: Dónde puede ir un dato de protocolo dentro del comprobante.
#:
#: Son los tres sitios que el XSD deja para información no tributaria. No hay un
#: cuarto: el complemento anidado que pedían Gessa y PriceSmart **no es válido**
#: —`OtroContenido` es `simpleContent` y Hacienda rechaza cualquier elemento
#: hijo—, y ese camino se probó contra el sandbox y se descartó.
EN_OTRO_TEXTO: Final = "otro_texto"
EN_OTRO_CONTENIDO: Final = "otro_contenido"
EN_REFERENCIA: Final = "referencia"
DESTINOS: Final = (EN_OTRO_TEXTO, EN_OTRO_CONTENIDO, EN_REFERENCIA)

#: Los datos que una plantilla puede pedir.
#:
#: Los dos primeros son del cliente —se los asigna el comprador una vez—; los
#: tres siguientes, del documento, y cambian en cada venta. Los dos últimos los
#: pone el propio comprobante.
MARCADORES: Final = (
    "codigo_proveedor",
    "gln",
    "orden_compra",
    "fecha_orden",
    "numero_recepcion",
    "clave",
    "consecutivo",
)

_MARCADOR = re.compile(r"\{([a-z_]+)\}")


class InvalidProtocol(DomainError):
    """Una entrada de protocolo que no se puede armar."""

    def __init__(self, code: str, value: object = None) -> None:
        super().__init__(f"protocolo no válido ({code}): {value!r}")
        self.code = code
        self.value = value


@dataclass(frozen=True)
class Entrada:
    """Un dato que este comprador exige, con dónde va y cómo se escribe.

    `plantilla` es texto con marcadores entre llaves:
    `"BCCR_ORDEN_PEDIDO={orden_compra}"`. Un marcador que no esté en
    `MARCADORES` es un error **al guardar el protocolo**, no al emitir: un dedazo
    en el nombre no puede descubrirse con el cliente esperando la factura.
    """

    destino: str
    plantilla: str
    codigo: str = ""
    #: Solo en `referencia`: el `TipoDocIR` y el `Codigo` del nodo.
    tipo_documento: str = ""
    codigo_referencia: str = ""
    razon: str = ""

    def __post_init__(self) -> None:
        if self.destino not in DESTINOS:
            raise InvalidProtocol("unknown_destination", self.destino)
        if not self.plantilla.strip():
            raise InvalidProtocol("empty_template")
        for marcador in _MARCADOR.findall(self.plantilla):
            if marcador not in MARCADORES:
                raise InvalidProtocol("unknown_placeholder", marcador)
        if self.destino == EN_REFERENCIA and not self.tipo_documento:
            # Una referencia sin tipo de documento no valida contra el XSD, y
            # el que se usa para esto es el 99 («Otros»).
            raise InvalidProtocol("reference_without_type")

    @property
    def marcadores(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(_MARCADOR.findall(self.plantilla)))


@dataclass(frozen=True)
class Armado:
    """Lo que el protocolo aporta al comprobante, y lo que le faltó."""

    otros: tuple[Otro, ...] = ()
    referencias: tuple[Referencia, ...] = ()
    #: Los marcadores que ninguna entrada pudo llenar, sin repetir.
    faltantes: tuple[str, ...] = ()


def armar(
    entradas: tuple[Entrada, ...], datos: Mapping[str, str], fecha: str = ""
) -> Armado:
    """Las piezas del comprobante que pide este protocolo.

    `fecha` es la del comprobante, y se usa como `FechaEmisionIR` de las
    referencias que el protocolo genere: son referencias a un documento del
    comprador que no tiene fecha propia en el sistema. Sale del comprobante y no
    de un reloj porque dos llamadas al reloj dan dos fechas distintas.
    """
    otros: list[Otro] = []
    referencias: list[Referencia] = []
    faltantes: list[str] = []

    for entrada in entradas:
        sin_valor = [m for m in entrada.marcadores if not (datos.get(m) or "").strip()]
        if sin_valor:
            # **No se emite a medias.** Un `BCCR_ORDEN_PEDIDO=` vacío es un dato
            # falso, y el comprador lo rechaza igual que si faltara entero.
            faltantes.extend(m for m in sin_valor if m not in faltantes)
            continue

        texto = _MARCADOR.sub(lambda m: datos[m.group(1)].strip(), entrada.plantilla)
        if entrada.destino == EN_REFERENCIA:
            referencias.append(
                Referencia(
                    tipo_documento=entrada.tipo_documento,
                    numero=texto,
                    fecha=fecha,
                    codigo=entrada.codigo_referencia,
                    razon=entrada.razon,
                )
            )
        else:
            otros.append(
                Otro(
                    texto=texto,
                    codigo=entrada.codigo,
                    elemento=(
                        "OtroTexto"
                        if entrada.destino == EN_OTRO_TEXTO
                        else "OtroContenido"
                    ),
                )
            )

    return Armado(tuple(otros), tuple(referencias), tuple(faltantes))


__all__ = [
    "DESTINOS",
    "EN_OTRO_CONTENIDO",
    "EN_OTRO_TEXTO",
    "EN_REFERENCIA",
    "MARCADORES",
    "Armado",
    "Entrada",
    "InvalidProtocol",
    "armar",
]
