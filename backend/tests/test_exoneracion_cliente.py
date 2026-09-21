"""La exoneración del cliente contra la base de verdad (T-717, RF-67, RN-78).

Lo que se comprueba acá y no se puede comprobar sin base:

* que los ocho campos **se guardan y se leen juntos**, que es la única forma de
  que la exoneración se pueda quitar;
* que **una a medias no entra**, con el motivo de cada falta;
* que los puntos son puntos —9 y no 0.09— y sobreviven al viaje de ida y vuelta.
"""

from __future__ import annotations

import pytest

from .conftest import Api, marca_unica

pytestmark = pytest.mark.characterization

#: La del ejemplo real de `docs/…/protocolos/`: ley 7210, PROCOMER, artículo 17.
ZONA_FRANCA = {
    "exo_document_type": "08",
    "exo_document_number": "LEY 7210 REGIMEN DE ZONAS FRANCAS",
    "exo_institution": "99",
    "exo_institution_other": "PROCOMER",
    "exo_article": 17,
    "exo_subsection": 1,
    "exo_date": "2023-01-13",
    "exo_points": 9,
}


@pytest.fixture
def cliente(api: Api):
    """Un cliente nuevo por prueba, con cédula y correo únicos."""
    creados: list[int] = []

    def crear(**campos) -> dict:
        marca = marca_unica()
        cuerpo = {
            "identification": marca[-9:],
            "name": "Zona",
            "last_name": "Franca",
            "second_name": "S.A.",
            "email": f"zf{marca}@ejemplo.cr",
            "telephone": 22334455,
            "address": "La Ribera de Belén",
            "register_date": "2026-01-01",
            **campos,
        }
        hecho = api.ok("POST", "/clients/register_client", cuerpo)
        creados.append(hecho["id_client"])
        return leer(api, hecho["id_client"])

    return crear


def leer(api: Api, id_client: int) -> dict:
    return next(
        c for c in api.ok("GET", "/clients/clients_list") if c["id_client"] == id_client
    )


def guardar(api: Api, id_client: int, **campos) -> tuple[int, object]:
    return api.call("PUT", f"/clients/update_client/{id_client}", campos)


class TestSeGuardaEntera:
    def test_los_ocho_campos_van_y_vuelven(self, api: Api, cliente):
        guardado = cliente(**ZONA_FRANCA)

        assert guardado["exo_document_type"] == "08"
        assert guardado["exo_document_number"] == "LEY 7210 REGIMEN DE ZONAS FRANCAS"
        assert guardado["exo_institution"] == "99"
        assert guardado["exo_institution_other"] == "PROCOMER"
        assert guardado["exo_article"] == 17
        assert guardado["exo_subsection"] == 1
        assert guardado["exo_date"] == "2023-01-13"
        assert guardado["exo_points"] == pytest.approx(9.0)

    def test_los_puntos_son_puntos_y_no_una_tarifa(self, api: Api, cliente):
        """RN-78: nueve puntos sobre el 13 % dejan la línea pagando 4 %.

        Si alguien guardara `0.09` o `4`, el monto exonerado saldría mal y el
        comprobante no cuadraría contra su propio resumen.
        """
        assert cliente(**ZONA_FRANCA)["exo_points"] == pytest.approx(9.0)

    def test_un_cliente_nace_sin_exoneracion(self, api: Api, cliente):
        pelado = cliente()
        assert pelado["exo_document_type"] is None
        assert pelado["exo_points"] is None

    def test_se_le_puede_poner_después(self, api: Api, cliente):
        pelado = cliente()
        estado, _ = guardar(api, pelado["id_client"], **ZONA_FRANCA)
        assert estado == 200
        assert leer(api, pelado["id_client"])["exo_document_type"] == "08"

    def test_y_se_le_puede_quitar(self, api: Api, cliente):
        """Los ocho vacíos es «no tiene», y es cómo se le quita la que tenía."""
        con_exo = cliente(**ZONA_FRANCA)
        estado, _ = guardar(api, con_exo["id_client"], **dict.fromkeys(ZONA_FRANCA, ""))
        assert estado == 200

        quitada = leer(api, con_exo["id_client"])
        assert all(quitada[campo] is None for campo in ZONA_FRANCA)

    def test_guardar_otra_cosa_no_la_toca(self, api: Api, cliente):
        """Un cambio de dirección no puede borrarle la exoneración."""
        con_exo = cliente(**ZONA_FRANCA)
        estado, _ = guardar(api, con_exo["id_client"], address="Otra dirección")
        assert estado == 200
        assert leer(api, con_exo["id_client"])["exo_document_type"] == "08"


class TestLoQueNoEntra:
    @pytest.mark.parametrize(
        "cambio, motivo",
        [
            ({"exo_document_type": "77"}, "unknown_document_type"),
            ({"exo_document_type": "01"}, "document_type_only_in_notes"),
            ({"exo_document_number": ""}, "missing_document_number"),
            ({"exo_institution": "13"}, "unknown_institution"),
            ({"exo_institution_other": ""}, "missing_institution_name"),
            ({"exo_date": ""}, "missing_date"),
            ({"exo_article": ""}, "missing_article"),
            ({"exo_points": 0}, "points_out_of_range"),
            ({"exo_points": 100}, "points_out_of_range"),
        ],
    )
    def test_una_exoneracion_a_medias_no_se_guarda(self, api: Api, cliente, cambio, motivo):
        pelado = cliente()
        estado, cuerpo = guardar(api, pelado["id_client"], **{**ZONA_FRANCA, **cambio})

        assert estado == 400
        assert cuerpo["detail"]["code"] == "invalid_exemption"
        assert cuerpo["detail"]["reason"] == motivo

    def test_y_el_cliente_se_queda_como_estaba(self, api: Api, cliente):
        con_exo = cliente(**ZONA_FRANCA)
        guardar(api, con_exo["id_client"], **{**ZONA_FRANCA, "exo_points": 0})

        assert leer(api, con_exo["id_client"])["exo_points"] == pytest.approx(9.0)

    def test_una_fecha_que_no_es_una_fecha(self, api: Api, cliente):
        pelado = cliente()
        estado, cuerpo = guardar(
            api, pelado["id_client"], **{**ZONA_FRANCA, "exo_date": "el martes"}
        )
        assert (estado, cuerpo["detail"]["reason"]) == (400, "bad_date")

    def test_un_articulo_que_no_es_un_numero_es_un_cuerpo_mal_armado(self, api: Api, cliente):
        """422 y no 400: eso no es una exoneración incompleta, es basura.

        El POS nunca lo manda —el campo es numérico y lo convierte antes— así
        que un texto ahí es un cliente de API escribiendo mal el cuerpo, y esa
        es exactamente la conversación que tiene el 422.
        """
        pelado = cliente()
        estado, _ = guardar(
            api, pelado["id_client"], **{**ZONA_FRANCA, "exo_article": "diecisiete"}
        )
        assert estado == 422


class TestLosTiposQueNoExigenArticulo:
    def test_el_09_no_lo_pide(self, api: Api, cliente):
        """Solo 02, 03, 06, 07 y 08 remiten a un artículo de ley."""
        sin_articulo = {
            **ZONA_FRANCA,
            "exo_document_type": "09",
            "exo_article": "",
            "exo_subsection": "",
        }
        guardado = cliente(**sin_articulo)
        assert guardado["exo_document_type"] == "09"
        assert guardado["exo_article"] is None
