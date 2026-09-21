"""
El medio de pago en el código de Hacienda (nota 6, T-716, RN-77).

La prueba que importa es la segunda: **ningún medio de pago del POS se queda sin
código**. Es lo que hace que agregar una forma de cobrar obligue a decidir cómo
se declara, el día que se agrega y no el día de emitir.
"""

from __future__ import annotations

import pytest

from app.domain.errors import InvalidSalePaymentMethod
from app.domain.fe_payment_methods import (
    CARD,
    CASH,
    CODES,
    FROM_SALE_METHOD,
    SIN_CODIGO,
    check_code,
    code_for,
)
from app.domain.sale import CASH_METHOD, PAYMENT_METHODS


def test_son_los_ocho_de_la_nota_6():
    assert CODES == ("01", "02", "03", "04", "05", "06", "07", "99")


def test_ningun_medio_del_POS_se_queda_sin_codigo():
    """Si esta prueba falla es porque se agregó una forma de cobrar.

    Lo que hay que hacer no es cambiarla: es decidir con qué código de la nota 6
    se declara ese cobro y ponerlo en `FROM_SALE_METHOD`.
    """
    assert SIN_CODIGO == ()
    assert set(FROM_SALE_METHOD) == set(PAYMENT_METHODS)


def test_el_que_cuenta_el_arqueo_es_el_efectivo_de_Hacienda():
    assert code_for(CASH_METHOD) == CASH


def test_la_tarjeta_es_la_que_devuelve_el_IVA_de_salud():
    assert code_for("Tarjeta de crédito") == CARD


@pytest.mark.parametrize("malo", ["Efectvo", "", None, "01"])
def test_un_medio_que_el_POS_no_conoce_no_tiene_codigo(malo):
    """Adivinarle uno sería emitir un cobro que nadie eligió."""
    with pytest.raises(InvalidSalePaymentMethod):
        code_for(malo)


def test_los_codigos_se_comprueban_contra_la_nota():
    assert check_code("06") == "06"
    with pytest.raises(InvalidSalePaymentMethod):
        check_code("08")
