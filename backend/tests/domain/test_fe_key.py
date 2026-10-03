"""El consecutivo de 20 dígitos y la clave de 50 (nota 3 del anexo; T-704, T-705)."""

from datetime import date

import pytest

from app.domain.errors import InvalidKeyPart
from app.domain.fe_key import (
    CONSECUTIVE_LENGTH,
    COUNTRY_CODE,
    MAX_SEQUENCE,
    SITUATION_CONTINGENCY,
    SITUATION_NORMAL,
    SITUATIONS,
    build_clave,
    consecutive,
    issuer_digits,
    next_sequence,
)
from app.domain.office import BranchCode, TerminalCode

#: La factura de referencia del usuario, `docs/invoice/50624…346.pdf`. Es un
#: comprobante que Hacienda aceptó: si esto la reproduce, el formato es el suyo.
CLAVE_REAL = "50624092600310170293400100001010001819201163700346"
CONSECUTIVO_REAL = "00100001010001819201"


class TestLaFacturaDeReferencia:
    def test_el_consecutivo_sale_igual(self):
        assert consecutive(BranchCode("1"), TerminalCode("1"), "01", 1819201) == CONSECUTIVO_REAL

    def test_la_clave_sale_igual(self):
        assert (
            build_clave(
                issued_on=date(2026, 9, 24),
                issuer_identification="3101702934",
                consecutive=CONSECUTIVO_REAL,
                situation=SITUATION_NORMAL,
                security_code="63700346",
            )
            == CLAVE_REAL
        )

    def test_la_cedula_con_guiones_da_la_misma_clave(self):
        # Así se escribe una cédula jurídica, y así puede estar guardada.
        assert (
            build_clave(
                issued_on=date(2026, 9, 24),
                issuer_identification="3-101-702934",
                consecutive=CONSECUTIVO_REAL,
                situation=SITUATION_NORMAL,
                security_code="63700346",
            )
            == CLAVE_REAL
        )


class TestLasPiezasDeLaClave:
    """Cada tramo en su posición, de la nota 3."""

    CLAVE = build_clave(
        issued_on=date(2026, 3, 5),
        issuer_identification="115670987",
        consecutive="00200003040000000042",
        situation=SITUATION_CONTINGENCY,
        security_code="00000007",
    )

    def test_son_cincuenta(self):
        assert len(self.CLAVE) == 50 and self.CLAVE.isdigit()

    def test_el_pais(self):
        assert self.CLAVE[0:3] == COUNTRY_CODE == "506"

    def test_dia_mes_y_anio_con_dos_digitos(self):
        assert self.CLAVE[3:9] == "050326"

    def test_la_fisica_lleva_tres_ceros_delante(self):
        # Nota 4.1: la física tiene nueve dígitos y se completa a doce.
        assert self.CLAVE[9:21] == "000115670987"

    def test_el_consecutivo(self):
        assert self.CLAVE[21:41] == "00200003040000000042"

    def test_la_situacion_en_la_posicion_42(self):
        assert self.CLAVE[41] == SITUATION_CONTINGENCY

    def test_el_codigo_de_seguridad_al_final(self):
        assert self.CLAVE[42:] == "00000007"


class TestElConsecutivo:
    def test_son_veinte(self):
        numero = consecutive(BranchCode("2"), TerminalCode("3"), "04", 42)
        assert numero == "00200003040000000042"
        assert len(numero) == CONSECUTIVE_LENGTH

    @pytest.mark.parametrize("tipo", ["01", "02", "03", "04", "08", "09", "10"])
    def test_cada_tipo_lleva_su_codigo_en_las_posiciones_9_y_10(self, tipo):
        assert consecutive(BranchCode("1"), TerminalCode("1"), tipo, 1)[8:10] == tipo

    @pytest.mark.parametrize("tipo", ["00", "11", "1", "FE", None])
    def test_un_tipo_que_no_tiene_serie(self, tipo):
        with pytest.raises(InvalidKeyPart) as e:
            consecutive(BranchCode("1"), TerminalCode("1"), tipo, 1)
        assert e.value.part == "document_type"

    @pytest.mark.parametrize("secuencia", [0, -1, MAX_SEQUENCE + 1, True, "1", 1.0])
    def test_una_secuencia_que_no_cabe(self, secuencia):
        with pytest.raises(InvalidKeyPart) as e:
            consecutive(BranchCode("1"), TerminalCode("1"), "01", secuencia)
        assert e.value.part == "sequence"

    def test_la_mas_alta_cabe(self):
        assert consecutive(BranchCode("1"), TerminalCode("1"), "01", MAX_SEQUENCE).endswith(
            "9999999999"
        )


class TestLaSiguiente:
    def test_la_primera_de_una_serie_nueva_es_uno(self):
        assert next_sequence(0) == 1

    def test_sigue_de_a_uno(self):
        assert next_sequence(41) == 42

    def test_al_tope_vuelve_a_uno(self):
        # Nota 3, inciso d: «se podrá volver a empezar desde el número 1».
        assert next_sequence(MAX_SEQUENCE) == 1

    @pytest.mark.parametrize("malo", [-1, MAX_SEQUENCE + 1, None, True, "3", 2.0])
    def test_lo_que_no_es_una_ultima_secuencia(self, malo):
        with pytest.raises(InvalidKeyPart) as e:
            next_sequence(malo)
        assert e.value.part == "sequence"


class TestLaCedulaDelEmisor:
    @pytest.mark.parametrize(
        "cedula, esperada",
        [
            ("115670987", "000115670987"),  # física: tres ceros
            ("3101702934", "003101702934"),  # jurídica: dos
            ("12345678901", "012345678901"),  # DIMEX de once: uno
            ("123456789012", "123456789012"),  # DIMEX de doce: ninguno
            (" 3-101-702934 ", "003101702934"),
        ],
    )
    def test_se_completa_a_doce(self, cedula, esperada):
        assert issuer_digits(cedula) == esperada

    @pytest.mark.parametrize("mala", ["", "  ", "31017O2934", "1234567890123", None, 3101702934, "٣"])
    def test_lo_que_no_cabe_no_se_recorta(self, mala):
        with pytest.raises(InvalidKeyPart) as e:
            issuer_digits(mala)
        assert e.value.part == "issuer"


class TestLoQueNoArmaUnaClave:
    BASE = dict(
        issued_on=date(2026, 9, 24),
        issuer_identification="3101702934",
        consecutive=CONSECUTIVO_REAL,
        situation=SITUATION_NORMAL,
        security_code="63700346",
    )

    @pytest.mark.parametrize(
        "campo, valor",
        [
            ("consecutive", "0010000101000181920"),  # diecinueve
            ("consecutive", "0010000101000181920X"),
            ("consecutive", None),
            ("situation", "4"),
            ("situation", 1),
            ("security_code", "6370034"),
            ("security_code", "6370034a"),
            ("security_code", 63700346),
            ("issuer_identification", "abc"),
        ],
    )
    def test_cada_pieza_se_comprueba(self, campo, valor):
        with pytest.raises(InvalidKeyPart) as e:
            build_clave(**{**self.BASE, campo: valor})
        assert e.value.part == {"issuer_identification": "issuer"}.get(campo, campo)

    def test_las_tres_situaciones_del_anexo(self):
        assert SITUATIONS == ("1", "2", "3")
