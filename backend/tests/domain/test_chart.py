"""La plantilla de cuentas y el mapeo por omisión (T-1107, plan §13.8).

La prueba que importa acá es la última: **ningún papel se queda sin cuenta**. No
se comprueba leyendo la tabla del mapeo —eso solo diría que la tabla se copió
bien— sino corriendo los seis `post_*` de verdad contra el catálogo sembrado y
mirando que ninguna línea caiga en «por clasificar», salvo las tres que caen ahí
a propósito y están declaradas con su razón.

Es la diferencia entre comprobar lo que alguien escribió y comprobar lo que el
sistema va a hacer el primer día.
"""

from datetime import date

import pytest

from app.domain.chart import (
    CHART,
    COMMERCE,
    SALES_ACCOUNTS,
    TEMPLATES,
    UNMAPPED_ON_PURPOSE,
    default_mapping,
)
from app.domain.ledger import (
    ACCOUNT_KINDS,
    AccountMap,
    ClosedSession,
    DrawerMovement,
    PurchasedDocument,
    PurchasedLine,
    ReturnDocument,
    SoldDocument,
    SoldLine,
    SupplierPaymentRef,
    post_cash_close,
    post_cash_movement,
    post_purchase,
    post_return,
    post_sale,
    post_supplier_payment,
)
from app.domain.money import Money
from app.domain.sale import PAYMENT_METHODS
from app.domain.tax import TaxRate

HOY = date(2026, 9, 12)
POR_CLASIFICAR = 99999


def cuentas() -> dict[str, int]:
    """`código → id`, como quedan después de sembrar la plantilla."""
    return {plantilla.code: indice for indice, plantilla in enumerate(CHART, start=1)}


def mapeo_sembrado() -> AccountMap:
    ids = cuentas()
    return AccountMap(
        accounts={papel: ids[codigo] for papel, codigo in default_mapping().items()},
        unclassified=POR_CLASIFICAR,
    )


def sin_clasificar(asiento) -> list:
    if asiento is None:
        return []
    return [linea for linea in asiento.lines if linea.account_id == POR_CLASIFICAR]


class TestLaPlantilla:
    def test_no_hay_dos_cuentas_con_el_mismo_codigo(self):
        codigos = [plantilla.code for plantilla in CHART]

        assert len(codigos) == len(set(codigos))

    def test_todos_los_tipos_son_de_los_seis(self):
        # Un tipo inventado no rompería nada al sembrar y haría que la cuenta
        # desapareciera de los tres estados, que suman por tipo.
        assert {plantilla.kind for plantilla in CHART} <= set(ACCOUNT_KINDS)

    def test_la_cuenta_por_clasificar_existe_y_es_de_sistema(self):
        # Es la que sostiene RN-59. Si se pudiera borrar, un mapeo incompleto
        # volvería a poder detener una venta.
        por_clasificar = next(p for p in CHART if p.code == "1.9.99")

        assert por_clasificar.is_system

    def test_hay_una_cuenta_de_ingresos_por_tarifa(self):
        assert len(SALES_ACCOUNTS) == 5
        for codigo, _ in SALES_ACCOUNTS:
            assert any(plantilla.code == codigo for plantilla in CHART)

    def test_comercio_es_una_plantilla(self):
        assert COMMERCE in TEMPLATES


class TestElMapeo:
    def test_toda_cuenta_del_mapeo_esta_en_la_plantilla(self):
        # Sin esto, sembrar reventaría con un KeyError a mitad, dejando el
        # catálogo escrito y el mapeo a medias.
        codigos = {plantilla.code for plantilla in CHART}

        assert set(default_mapping().values()) <= codigos

    def test_toda_cuenta_que_el_mapeo_usa_es_de_sistema(self):
        # RN-64: si se pudiera borrar, el papel quedaría sin cuenta y el saldo se
        # iría a 1.9.99 sin que nadie lo hubiera decidido.
        usadas = set(default_mapping().values())
        de_sistema = {p.code for p in CHART if p.is_system}

        assert usadas <= de_sistema

    def test_los_eventos_son_los_siete(self):
        assert {evento for evento, _ in default_mapping()} == {
            "sale",
            "return",
            "cash_close",
            "cash_movement",
            "purchase",
            "supplier_payment",
            "payroll",
        }


class TestNingunPapelSeQuedaSinCuenta:
    """La verificación de T-1107, corriendo los `post_*` de verdad."""

    @pytest.mark.parametrize("metodo", PAYMENT_METHODS)
    def test_la_venta_con_cualquiera_de_los_cuatro_metodos(self, metodo):
        asiento = post_sale(
            SoldDocument(id=1, date=HOY, payment_method=metodo),
            [
                SoldLine(
                    Money(4350), Money("565.50"), TaxRate.percent(13), 3, Money(900)
                )
            ],
            mapeo_sembrado(),
        )

        assert sin_clasificar(asiento) == []

    @pytest.mark.parametrize("codigo,tarifa", SALES_ACCOUNTS)
    def test_la_venta_a_cualquiera_de_las_cinco_tarifas(self, codigo, tarifa):
        asiento = post_sale(
            SoldDocument(id=2, date=HOY, payment_method="Efectivo"),
            [SoldLine(Money(1000), tarifa.apply(Money(1000)), tarifa, 1)],
            mapeo_sembrado(),
        )

        assert sin_clasificar(asiento) == []
        # Y en la cuenta que le toca, no en cualquiera que exista.
        ingreso = next(linea for linea in asiento.lines if linea.credit == Money(1000))
        assert ingreso.account_id == cuentas()[codigo]

    def test_la_devolucion(self):
        asiento = post_return(
            ReturnDocument(id=1, date=HOY),
            [SoldLine(Money(1450), Money("188.50"), TaxRate.percent(13), 1, Money(900))],
            mapeo_sembrado(),
        )

        assert sin_clasificar(asiento) == []

    @pytest.mark.parametrize("contado", [Money(49000), Money(51000)])
    def test_el_cierre_de_caja_con_faltante_y_con_sobrante(self, contado):
        asiento = post_cash_close(
            ClosedSession(id=1, date=HOY), Money(50000), contado, mapeo_sembrado()
        )

        assert sin_clasificar(asiento) == []

    def test_la_compra(self):
        asiento = post_purchase(
            PurchasedDocument(id=1, date=HOY),
            [PurchasedLine(Money(100000), Money(13000), TaxRate.percent(13))],
            mapeo_sembrado(),
        )

        assert sin_clasificar(asiento) == []

    @pytest.mark.parametrize("metodo", ["cash", "transfer"])
    def test_el_abono_en_efectivo_y_por_transferencia(self, metodo):
        asiento = post_supplier_payment(
            SupplierPaymentRef(id=1, date=HOY, amount=Money(50000), method=metodo),
            mapeo_sembrado(),
        )

        assert sin_clasificar(asiento) == []


class TestLoQueCaeEnPorClasificarAProposito:
    """Las tres excepciones, que están declaradas y tienen su porqué."""

    def test_la_contrapartida_de_un_movimiento_de_caja(self):
        # El sistema sabe que entraron ₡5 000, no de dónde salieron.
        asiento = post_cash_movement(
            DrawerMovement(id=1, date=HOY, type="entrada", amount=Money(5000)),
            mapeo_sembrado(),
        )

        assert len(sin_clasificar(asiento)) == 1
        assert "counterpart" in UNMAPPED_ON_PURPOSE["cash_movement"]

    def test_un_abono_por_otro_medio(self):
        # Suponer banco dejaría el saldo del libro en desacuerdo con el del banco.
        asiento = post_supplier_payment(
            SupplierPaymentRef(id=2, date=HOY, amount=Money(1000), method="other"),
            mapeo_sembrado(),
        )

        assert len(sin_clasificar(asiento)) == 1
        assert "unclassified" in UNMAPPED_ON_PURPOSE["supplier_payment"]

    def test_una_venta_con_un_metodo_anterior_a_t_1104(self):
        asiento = post_sale(
            SoldDocument(id=3, date=HOY, payment_method="Cheque"),
            [SoldLine(Money(1000), Money(130), TaxRate.percent(13), 1)],
            mapeo_sembrado(),
        )

        assert len(sin_clasificar(asiento)) == 1
        assert "unclassified" in UNMAPPED_ON_PURPOSE["sale"]
