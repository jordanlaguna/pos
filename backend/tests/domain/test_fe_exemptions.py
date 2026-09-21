"""
La exoneración del cliente (T-717, RF-67, RN-78).

Lo que se prueba acá son las reglas que hacen que un comprobante se acepte o se
rechace: el tipo que solo vale en notas, el artículo que unos tipos exigen y
otros no, el `99` que obliga a escribir la institución, y los puntos, que son
puntos y no una tarifa.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.domain.errors import DomainError
from app.domain.fe_exemptions import (
    DOCUMENT_TYPES,
    INSTITUTIONS,
    ONLY_IN_NOTES,
    SELLABLE_TYPES,
    Exemption,
    InvalidExemption,
    check_document_type,
    check_institution,
    needs_article,
)

ZONA_FRANCA = dict(
    document_type="08",
    document_number="LEY 7210 REGIMEN DE ZONAS FRANCAS",
    institution="99",
    institution_other="PROCOMER",
    date="2023-01-13T00:00:00-06:00",
    points=Decimal("9"),
    article=17,
    subsection=1,
)


def exoneracion(**cambios) -> Exemption:
    return Exemption(**{**ZONA_FRANCA, **cambios})


class TestLosCatalogos:
    def test_los_doce_tipos_de_la_nota_10_1(self):
        assert list(DOCUMENT_TYPES) == [
            "01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "99",
        ]

    def test_las_trece_instituciones_de_la_nota_23(self):
        assert len(INSTITUTIONS) == 13
        assert INSTITUTIONS[-1] == "99"

    def test_cuatro_tipos_solo_valen_en_notas(self):
        assert ONLY_IN_NOTES == ("01", "05", "06", "07")

    def test_y_los_otros_ocho_se_le_pueden_poner_a_un_cliente(self):
        assert SELLABLE_TYPES == ("02", "03", "04", "08", "09", "10", "11", "99")

    @pytest.mark.parametrize("tipo, exige", [("02", True), ("08", True), ("09", False)])
    def test_hay_tipos_que_exigen_el_articulo_de_la_ley(self, tipo, exige):
        assert needs_article(tipo) is exige

    def test_hacienda_cruza_dos_de_ellos_contra_su_registro(self):
        """Con el 04 y el 11 comprueba que exista, esté vigente y no exceda."""
        assert exoneracion(document_type="04", article=None).verified_by_hacienda
        assert not exoneracion().verified_by_hacienda

    @pytest.mark.parametrize("malo", ["", "00", "12", None, 8])
    def test_un_tipo_que_no_esta_en_la_nota(self, malo):
        with pytest.raises(InvalidExemption) as e:
            check_document_type(malo)
        assert e.value.code == "unknown_document_type"
        assert isinstance(e.value, DomainError)

    def test_una_institucion_que_no_esta_en_la_nota(self):
        with pytest.raises(InvalidExemption) as e:
            check_institution("13")
        assert e.value.code == "unknown_institution"

    def test_y_las_del_catalogo_pasan(self):
        assert check_institution("05") == "05"
        assert check_document_type("09") == "09"


class TestLoQueNoSePuedeGuardar:
    def test_un_tipo_que_solo_vale_en_notas(self):
        """Ponérselo a un cliente para facturarle es guardar un rechazo."""
        with pytest.raises(InvalidExemption) as e:
            exoneracion(document_type="01")
        assert (e.value.code, e.value.value) == ("document_type_only_in_notes", "01")

    def test_un_tipo_que_no_existe(self):
        with pytest.raises(InvalidExemption) as e:
            exoneracion(document_type="77")
        assert e.value.code == "unknown_document_type"

    @pytest.mark.parametrize("numero", ["", "   "])
    def test_sin_numero_de_documento(self, numero):
        with pytest.raises(InvalidExemption) as e:
            exoneracion(document_number=numero)
        assert e.value.code == "missing_document_number"

    def test_una_institucion_que_no_existe(self):
        with pytest.raises(InvalidExemption) as e:
            exoneracion(institution="13")
        assert e.value.code == "unknown_institution"

    def test_la_institucion_99_sin_decir_cual(self):
        with pytest.raises(InvalidExemption) as e:
            exoneracion(institution_other="")
        assert e.value.code == "missing_institution_name"

    def test_sin_fecha(self):
        with pytest.raises(InvalidExemption) as e:
            exoneracion(date="")
        assert e.value.code == "missing_date"

    def test_un_tipo_que_exige_articulo_y_no_lo_trae(self):
        with pytest.raises(InvalidExemption) as e:
            exoneracion(article=None)
        assert (e.value.code, e.value.value) == ("missing_article", "08")

    @pytest.mark.parametrize("puntos", ["0", "-1", "100"])
    def test_puntos_fuera_de_rango(self, puntos):
        """Cero puntos no es una exoneración: es no tenerla.

        Y el tope es 99.99 porque el campo del XSD es `decimal 4,2`.
        """
        with pytest.raises(InvalidExemption) as e:
            exoneracion(points=Decimal(puntos))
        assert e.value.code == "points_out_of_range"


class TestLaQueSiSePuede:
    def test_la_de_zona_franca_del_ejemplo_real(self):
        """La de `docs/…/protocolos/`: ley 7210, PROCOMER, artículo 17."""
        exo = exoneracion()
        assert exo.points == Decimal("9")
        assert exo.institution_other == "PROCOMER"

    def test_un_tipo_que_no_exige_articulo_puede_no_traerlo(self):
        assert exoneracion(document_type="09", article=None).article is None

    def test_una_institucion_del_catalogo_no_necesita_detalle(self):
        assert exoneracion(institution="01", institution_other="").institution == "01"

    def test_los_puntos_pueden_tener_decimales(self):
        """El anexo: «la tarifa del 0.5 % como 0.5»."""
        assert exoneracion(points=Decimal("0.5")).points == Decimal("0.5")
