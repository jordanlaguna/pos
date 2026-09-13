"""Compras y cuentas por pagar (T-1006, RN-53 a RN-57).

La tabla de casos de plan §12.3. Sin base, sin reloj y sin red: la fecha de hoy
entra como argumento, que es lo que permite pararse en el día que haga falta.
"""

from datetime import date

import pytest

from app.domain.errors import InvalidPayment, PaymentExceedsBalance
from app.domain.money import Money
from app.domain.purchases import (
    CASH,
    PAYMENT_METHODS,
    PurchaseLine,
    aging_bucket,
    apply_payment,
    check_payment,
    purchase_totals,
    remaining_balance,
    weighted_average_cost,
)
from app.domain.tax import TaxRate

TRECE = TaxRate.percent(13)
UNO = TaxRate.percent(1)
CERO = TaxRate.zero()


class TestCostoPromedio:
    def test_el_caso_del_plan(self):
        # 10 a 100 más 10 a 120 son 2 200 entre 20.
        assert weighted_average_cost(10, Money(100), 10, Money(120)) == Money(110)

    def test_pondera_por_cantidad_y_no_promedia_los_precios(self):
        # 90 a 100 más 10 a 200: el promedio simple daría 150 y el correcto 110.
        assert weighted_average_cost(90, Money(100), 10, Money(200)) == Money(110)

    def test_sin_existencia_el_costo_es_el_de_la_compra(self):
        # El primer ingreso de un producto, que nace en cero.
        assert weighted_average_cost(0, Money(0), 5, Money(80)) == Money(80)

    def test_con_existencia_negativa_tambien(self):
        # Pasa con un producto que se vendió de más. Promediar daría un costo
        # negativo, y eso se arrastraría a todos los asientos siguientes.
        assert weighted_average_cost(-3, Money(50), 10, Money(50)) == Money(50)

    def test_el_costo_anterior_no_importa_si_no_hay_existencia(self):
        assert weighted_average_cost(0, Money(999), 1, Money(10)) == Money(10)

    def test_redondea_a_dos_decimales(self):
        # 1 a 100 más 2 a 101 son 302 entre 3 = 100,666… → 100,67.
        assert weighted_average_cost(1, Money(100), 2, Money(101)) == Money("100.67")

    def test_comprar_al_mismo_precio_no_lo_mueve(self):
        assert weighted_average_cost(7, Money("1450.00"), 3, Money("1450.00")) == Money(1450)


class TestTotalesDeLaCompra:
    def test_una_sola_tarifa(self):
        totales = purchase_totals([PurchaseLine(10, Money(1000), TRECE)])
        assert totales.subtotal == Money(10000)
        assert totales.tax == Money(1300)
        assert totales.total == Money(11300)

    def test_suma_linea_por_linea_y_desglosa_por_tarifa(self):
        # El documento de un abarrotes: canasta básica al 1 %, el resto al 13 %
        # y algo exento. El promedio no es ninguna de las tres.
        totales = purchase_totals(
            [
                PurchaseLine(1, Money(1000), TRECE),
                PurchaseLine(1, Money(1000), UNO),
                PurchaseLine(1, Money(1000), CERO),
            ]
        )
        assert totales.subtotal == Money(3000)
        assert totales.tax == Money(140)  # 130 + 10 + 0
        assert totales.total == Money(3140)
        assert totales.by_rate == (
            (CERO, Money(1000), Money(0)),
            (UNO, Money(1000), Money(10)),
            (TRECE, Money(1000), Money(130)),
        )

    def test_agrupa_las_lineas_de_la_misma_tarifa(self):
        totales = purchase_totals(
            [PurchaseLine(1, Money(500), TRECE), PurchaseLine(2, Money(250), TRECE)]
        )
        assert len(totales.by_rate) == 1
        tarifa, base, impuesto = totales.by_rate[0]
        assert (tarifa, base, impuesto) == (TRECE, Money(1000), Money(130))

    def test_el_desglose_sale_siempre_en_el_mismo_orden(self):
        # Sin ordenar, el orden lo decidiría en qué fila del documento apareció
        # cada tarifa, y el reporte del mes saldría distinto cada vez.
        primero = purchase_totals(
            [PurchaseLine(1, Money(100), TRECE), PurchaseLine(1, Money(100), UNO)]
        )
        segundo = purchase_totals(
            [PurchaseLine(1, Money(100), UNO), PurchaseLine(1, Money(100), TRECE)]
        )
        assert [t for t, _, _ in primero.by_rate] == [t for t, _, _ in segundo.by_rate]

    def test_una_compra_sin_lineas_da_cero(self):
        totales = purchase_totals([])
        assert (totales.subtotal, totales.tax, totales.total) == (
            Money.zero(),
            Money.zero(),
            Money.zero(),
        )
        assert totales.by_rate == ()


class TestSaldo:
    def test_sin_abonos_se_debe_todo(self):
        assert remaining_balance(Money(1000), []) == Money(1000)

    def test_resta_los_abonos(self):
        assert remaining_balance(Money(1000), [Money(300), Money(200)]) == Money(500)

    def test_pagada_queda_en_cero(self):
        assert remaining_balance(Money(1000), [Money(1000)]).is_zero

    def test_nunca_es_negativo(self):
        # Red por si una fila vieja trae un abono de más: un saldo negativo se
        # sumaría al del proveedor y le rebajaría lo que sí debe en otra factura.
        assert remaining_balance(Money(1000), [Money(1500)]) == Money.zero()


class TestAbonar:
    def test_deja_el_resto(self):
        assert apply_payment(Money(1000), Money(800)) == Money(200)

    def test_abonar_todo_deja_cero(self):
        assert apply_payment(Money(1000), Money(1000)).is_zero

    def test_abonar_de_mas_no_se_ajusta_en_silencio(self):
        with pytest.raises(PaymentExceedsBalance) as excepcion:
            apply_payment(Money(1000), Money("1000.01"))
        # Los dos montos viajan como datos para que el POS arme la frase (RN-30).
        assert excepcion.value.balance == "1000.00"
        assert excepcion.value.requested == "1000.01"

    def test_un_centimo_de_menos_si_pasa(self):
        assert apply_payment(Money(1000), Money("999.99")) == Money("0.01")


class TestElAbonoAntesDeMirarElSaldo:
    """Lo que se comprueba antes de saber cuánto se debe (T-1010)."""

    @pytest.mark.parametrize("metodo", PAYMENT_METHODS)
    def test_los_tres_metodos_que_existen(self, metodo):
        check_payment(Money(1000), metodo)

    @pytest.mark.parametrize("malo", ["efectivo", "CASH", "tarjeta", "", None])
    def test_cualquier_otro_no(self, malo):
        # No es formalismo: el `if` del efectivo compara contra 'cash', así que
        # un método mal escrito pasaría de largo y el turno cerraría con un
        # sobrante igual a lo que se pagó.
        with pytest.raises(InvalidPayment) as excepcion:
            check_payment(Money(1000), malo)
        assert excepcion.value.code == "invalid_method"

    @pytest.mark.parametrize("monto", [Money.zero(), Money(-1)])
    def test_un_abono_de_cero_o_negativo_no(self, monto):
        # Cero pasa la prueba del saldo —nunca es mayor que nada— y dejaría una
        # fila en el estado de cuenta que no significa nada.
        with pytest.raises(InvalidPayment) as excepcion:
            check_payment(monto, "cash")
        assert excepcion.value.code == "amount_not_positive"

    def test_el_monto_se_mira_antes_que_el_metodo(self):
        # Con los dos malos gana el monto: es el que decide si hay algo que
        # registrar, y decir «método inválido» de un abono de cero manda a
        # corregir lo que no está mal.
        with pytest.raises(InvalidPayment) as excepcion:
            check_payment(Money.zero(), "efectivo")
        assert excepcion.value.code == "amount_not_positive"

    def test_solo_el_efectivo_mueve_la_gaveta(self):
        # La constante que sostiene RN-56, escrita para que se note si cambia.
        assert CASH == "cash"
        assert PAYMENT_METHODS == ("cash", "transfer", "other")


class TestAntiguedad:
    HOY = date(2026, 9, 12)

    @pytest.mark.parametrize(
        "vence, tramo",
        [
            (date(2026, 10, 1), 0),  # todavía no vence
            (date(2026, 9, 12), 0),  # vence hoy
            (date(2026, 8, 20), 0),  # 23 días
            # Los bordes exactos caen en el tramo de abajo: «0 a 30» incluye el
            # día 30. Es donde se equivoca quien escribe la tabla de memoria.
            (date(2026, 8, 13), 0),  # 30 justos → todavía 0-30
            (date(2026, 8, 12), 30),  # 31 días → 31-60
            (date(2026, 7, 14), 30),  # 60 justos → todavía 31-60
            (date(2026, 7, 13), 60),  # 61 días → 61-90
            (date(2026, 6, 14), 60),  # 90 justos → todavía 61-90
            (date(2026, 6, 13), 90),  # 91 días → más de 90
            (date(2025, 1, 1), 90),  # más de un año
        ],
    )
    def test_los_cuatro_tramos(self, vence, tramo):
        assert aging_bucket(vence, self.HOY) == tramo

    def test_sin_vencimiento_cae_en_el_primer_tramo(self):
        # Una compra de contado no tiene vencimiento y no es morosa. Es al revés
        # que la suscripción sin fecha, y a propósito: allá lo caro es vender
        # gratis, acá lo caro sería marcar de morosa a quien ya pagó.
        assert aging_bucket(None, self.HOY) == 0
