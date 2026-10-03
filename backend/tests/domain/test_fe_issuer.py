"""Lo que el emisor tiene que tener para poder emitir (T-722, RN-83, RN-45)."""

import pytest

from app.domain.errors import (
    EInvoicingNeedsIssuer,
    InvalidIdentificationType,
    IssuerIdentificationRequired,
)
from app.domain.fe_issuer import (
    EMAIL_MAX,
    check_issuer_identity,
    check_ready_to_emit,
    is_valid_email,
    missing_for_einvoicing,
)

UBICACION = {"province": "1", "canton": "01", "district": "05", "otherSigns": "frente al Archivo"}
LISTO = dict(identification="3101702934", email="facturas@negocio.cr", location=UBICACION)


class TestLoQueFaltaParaEmitir:
    def test_con_todo_no_falta_nada(self):
        assert missing_for_einvoicing(**LISTO) == ()
        check_ready_to_emit(**LISTO)

    def test_sin_nada_faltan_los_tres_en_orden(self):
        assert missing_for_einvoicing(identification=None, email="", location=None) == (
            "identification",
            "email",
            "location",
        )

    @pytest.mark.parametrize("cedula", [None, "", "  ", "sin cédula", 3101702934])
    def test_la_identificacion(self, cedula):
        assert missing_for_einvoicing(**{**LISTO, "identification": cedula}) == ("identification",)

    @pytest.mark.parametrize("correo", [None, "", "facturas", "a@b", "a b@c.cr", "x" * EMAIL_MAX + "@a.cr"])
    def test_el_correo(self, correo):
        assert missing_for_einvoicing(**{**LISTO, "email": correo}) == ("email",)

    def test_una_ubicacion_a_medias_cuenta_como_que_falta(self):
        # El XML la pide entera: sin distrito no valida.
        media = {**UBICACION, "district": ""}
        assert missing_for_einvoicing(**{**LISTO, "location": media}) == ("location",)

    def test_se_dice_todo_de_una_vez(self):
        with pytest.raises(EInvoicingNeedsIssuer) as e:
            check_ready_to_emit(identification="3101702934", email="", location={})
        assert e.value.missing == ("email", "location")


class TestElCorreo:
    @pytest.mark.parametrize("bueno", ["a@b.cr", " facturas@negocio.co.cr ", "jordan.laguna@sws-software.com"])
    def test_uno_que_sirve(self, bueno):
        assert is_valid_email(bueno)

    def test_uno_que_no_es_texto(self):
        assert not is_valid_email(42)


class TestLaCedulaQueFijaSoporte:
    def test_se_guarda_sin_guiones(self):
        emisor = check_issuer_identity("3-101-702934", None)
        assert emisor.identification == "3101702934"

    def test_el_tipo_sale_de_la_cedula_si_no_se_da(self):
        assert check_issuer_identity("3101702934", None).identification_type == "02"
        assert check_issuer_identity("115670987", "").identification_type == "01"

    def test_el_elegido_manda(self):
        # El NITE son diez dígitos como la jurídica: solo se sabe si se dice.
        assert check_issuer_identity("4000123456", "04").identification_type == "04"

    @pytest.mark.parametrize("vacia", [None, "", "  "])
    def test_una_que_falta(self, vacia):
        with pytest.raises(IssuerIdentificationRequired) as e:
            check_issuer_identity(vacia, None)
        assert e.value.reason == "missing"

    @pytest.mark.parametrize("mala", ["12345678", "1234567890123", "31017O2934", "٣١٠١٧٠٢٩٣٤"])
    def test_una_que_no_cabe_en_la_clave(self, mala):
        with pytest.raises(IssuerIdentificationRequired) as e:
            check_issuer_identity(mala, None)
        assert e.value.reason == "invalid"

    def test_un_tipo_que_no_existe(self):
        with pytest.raises(InvalidIdentificationType):
            check_issuer_identity("3101702934", "07")
