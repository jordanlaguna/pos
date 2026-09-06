"""El proxy de CABYS por HTTP (T-502, T-503).

Lo que se comprueba acá es el **borde**: que pida sesión, que valide el formato
antes de salir a la red y que la forma de la respuesta sea la que el POS espera.
La lógica de «sin internet, la caché y decilo» se prueba sin Docker en
`tests/application/test_search_cabys.py`, que es donde vive.

**Casi nada de acá toca internet**, y es deliberado: una batería que dependa de
que Hacienda esté arriba falla por la razón equivocada y enseña a ignorarla.
"""

from __future__ import annotations

import pytest

from .conftest import Api, codigo

pytestmark = pytest.mark.characterization


class TestPideSesion:
    """Buscar no cambia nada, pero el catálogo no es público: va detrás del
    token como el resto del API."""

    def test_buscar_sin_token(self, api: Api):
        assert codigo(api.call("GET", "/cabys/buscar?q=arroz", token=None), 401)

    def test_por_codigo_sin_token(self, api: Api):
        assert codigo(api.call("GET", "/cabys/2312000000300", token=None), 401)


class TestValidaAntesDeSalirALaRed:
    """Trece dígitos es una regla del catálogo, no algo que haya que preguntar.

    Que se valide acá tiene dos efectos: no se gasta un viaje a internet en un
    código imposible, y el «no» distingue el error de quien pide del de la red.
    """

    @pytest.mark.parametrize(
        "malo, razon",
        [
            pytest.param("231200000030", "bad_length", id="doce dígitos"),
            pytest.param("23120000003000", "bad_length", id="catorce dígitos"),
            pytest.param("2312-00000030", "not_digits", id="con guion"),
            pytest.param("abcdefghijklm", "not_digits", id="letras"),
        ],
    )
    def test_un_codigo_que_el_catalogo_no_podria_tener(self, api: Api, malo, razon):
        respuesta = api.call("GET", f"/cabys/{malo}")
        assert codigo(respuesta, 400) == "cabys_invalid_code"
        assert respuesta[1]["detail"]["reason"] == razon


class TestLaFormaDeLaRespuesta:
    def test_buscar_sin_texto_no_consulta_y_devuelve_vacio(self, api: Api):
        """Cada búsqueda es un viaje a internet: no se gasta uno en nada. Esta
        prueba además es la que corre sin red, siempre."""
        estado, cuerpo = api.call("GET", "/cabys/buscar?q=")
        assert estado == 200
        assert cuerpo["items"] == []
        # `source` viaja siempre: es la diferencia entre «esto dice Hacienda hoy»
        # y «esto decía la última vez que hubo internet» (RNF-4).
        assert cuerpo["source"] in ("hacienda", "cache")

    def test_el_top_se_acota(self, api: Api):
        """Un `top` de mil sería un viaje enorme a Hacienda por un desplegable."""
        assert api.call("GET", "/cabys/buscar?q=arroz&top=0")[0] == 422
        assert api.call("GET", "/cabys/buscar?q=arroz&top=999")[0] == 422
