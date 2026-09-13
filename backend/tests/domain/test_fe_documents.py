"""Dónde va cada comprobante dentro del almacén (T-623)."""

import pytest

from app.domain.errors import InvalidClave, InvalidDocumentKind, InvalidEnvironment
from app.domain.fe_documents import (
    GOV_RESPONSE,
    KINDS,
    PRODUCTION,
    RECEIVED_PDF,
    SANDBOX,
    SIGNED_PAYLOAD,
    DocumentRef,
    company_prefix,
)


def clave(*, dia="13", mes="09", anio="26") -> str:
    """Una clave numérica armada por pedazos, para poder torcer uno solo.

    506 país + ddmmaa + 12 de identificación + 20 de consecutivo + 1 de
    situación + 8 de código de seguridad = 50.
    """
    return f"506{dia}{mes}{anio}" + "003101234567" + "00100001010000000123" + "1" + "12345678"


CLAVE = clave()


class TestLaRuta:
    def test_lleva_compania_ambiente_clase_fecha_y_clave(self):
        ref = DocumentRef(7, PRODUCTION, SIGNED_PAYLOAD, CLAVE)
        assert ref.key == f"7/production/signed-payload/2026/09/{CLAVE}.xml"

    def test_la_fecha_sale_de_la_clave_y_no_de_un_parametro(self):
        # Pedirla aparte sería admitir que no coincidan: el mismo documento
        # archivado en dos meses distintos según quién lo guarde.
        ref = DocumentRef(1, SANDBOX, GOV_RESPONSE, clave(dia="01", mes="12", anio="31"))
        assert (ref.year, ref.month) == (2031, 12)
        assert "/2031/12/" in ref.key

    def test_el_pdf_de_un_recibido_no_se_llama_xml(self):
        ref = DocumentRef(1, SANDBOX, RECEIVED_PDF, CLAVE)
        assert ref.key.endswith(".pdf")
        assert ref.content_type == "application/pdf"

    @pytest.mark.parametrize("kind", KINDS)
    def test_las_cinco_clases_tienen_dónde_guardarse(self, kind):
        ref = DocumentRef(1, SANDBOX, kind, CLAVE)
        assert ref.extension in {"xml", "pdf"}
        assert ref.content_type

    def test_dos_companias_no_se_pisan(self):
        # Es la razón de que `company_id` vaya primero y lo ponga el servidor.
        uno = DocumentRef(1, PRODUCTION, SIGNED_PAYLOAD, CLAVE)
        otro = DocumentRef(2, PRODUCTION, SIGNED_PAYLOAD, CLAVE)
        assert uno.key != otro.key

    def test_el_ensayo_no_pisa_la_factura_de_verdad(self):
        # La clave se arma con el consecutivo, y pruebas y producción se
        # numeran aparte: la MISMA clave puede ser dos documentos distintos.
        ensayo = DocumentRef(1, SANDBOX, SIGNED_PAYLOAD, CLAVE)
        real = DocumentRef(1, PRODUCTION, SIGNED_PAYLOAD, CLAVE)
        assert ensayo.key != real.key

    def test_se_imprime_como_su_ruta(self):
        assert str(DocumentRef(7, PRODUCTION, SIGNED_PAYLOAD, CLAVE)) == (
            f"7/production/signed-payload/2026/09/{CLAVE}.xml"
        )

    def test_es_un_valor_y_no_se_puede_cambiar(self):
        ref = DocumentRef(7, PRODUCTION, SIGNED_PAYLOAD, CLAVE)
        with pytest.raises(Exception):
            ref.company_id = 8  # type: ignore[misc]


class TestLoQueSeRechaza:
    @pytest.mark.parametrize("mala", [None, 7, "", "506", "5" * 49, "5" * 51])
    def test_una_clave_que_no_mide_cincuenta(self, mala):
        with pytest.raises(InvalidClave) as e:
            DocumentRef(1, SANDBOX, SIGNED_PAYLOAD, mala)
        assert e.value.code == "length"

    def test_una_clave_con_letras(self):
        with pytest.raises(InvalidClave) as e:
            DocumentRef(1, SANDBOX, SIGNED_PAYLOAD, "X" + CLAVE[1:])
        assert e.value.code == "not_digits"

    @pytest.mark.parametrize("mes", ["00", "13"])
    def test_un_mes_que_no_existe(self, mes):
        # Un mes «00» produce una carpeta que nadie va a volver a encontrar.
        with pytest.raises(InvalidClave) as e:
            DocumentRef(1, SANDBOX, SIGNED_PAYLOAD, clave(mes=mes))
        assert e.value.code == "month"

    @pytest.mark.parametrize("dia", ["00", "32"])
    def test_un_dia_que_no_existe(self, dia):
        with pytest.raises(InvalidClave) as e:
            DocumentRef(1, SANDBOX, SIGNED_PAYLOAD, clave(dia=dia))
        assert e.value.code == "day"

    def test_el_31_de_febrero_se_acepta(self):
        # A propósito: la clave la emitió otro y validar el calendario acá
        # dejaría comprobantes legítimos sin poder archivarse. Lo que se
        # comprueba es que la RUTA tenga sentido, no que la fecha exista.
        assert DocumentRef(1, SANDBOX, SIGNED_PAYLOAD, clave(dia="31", mes="02"))

    @pytest.mark.parametrize("ambiente", ["produccion", "PRODUCTION", "", None])
    def test_un_ambiente_que_no_es_ninguno_de_los_dos(self, ambiente):
        with pytest.raises(InvalidEnvironment):
            DocumentRef(1, ambiente, SIGNED_PAYLOAD, CLAVE)

    @pytest.mark.parametrize("clase", ["factura", "", None, "signed_payload"])
    def test_una_clase_que_el_almacen_no_sabe_guardar(self, clase):
        with pytest.raises(InvalidDocumentKind):
            DocumentRef(1, SANDBOX, clase, CLAVE)

    @pytest.mark.parametrize("cid", [0, -1, None, "1"])
    def test_una_compania_que_no_es_un_numero_positivo(self, cid):
        with pytest.raises(InvalidClave) as e:
            DocumentRef(cid, SANDBOX, SIGNED_PAYLOAD, CLAVE)
        assert e.value.code == "company"


class TestElPrefijoDeUnaCompania:
    def test_es_lo_que_se_copia_o_se_entrega(self):
        assert company_prefix(7) == "7/"

    def test_contiene_todo_lo_de_esa_compania(self):
        assert DocumentRef(7, PRODUCTION, SIGNED_PAYLOAD, CLAVE).key.startswith(
            company_prefix(7)
        )

    def test_y_nada_de_otra(self):
        assert not DocumentRef(2, PRODUCTION, SIGNED_PAYLOAD, CLAVE).key.startswith(
            company_prefix(7)
        )

    @pytest.mark.parametrize("cid", [0, -1, None, "7"])
    def test_no_admite_cualquier_cosa(self, cid):
        with pytest.raises(InvalidClave):
            company_prefix(cid)
