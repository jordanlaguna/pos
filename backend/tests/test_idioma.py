"""El idioma viaja en el token (T-809, plan §8.4).

Lo que se comprueba acá es el **contrato**: que el token de sesión traiga el
idioma resuelto, por los dos caminos que emiten uno —el login directo y la
elección de compañía— y que el de tránsito no lo traiga, porque todavía no se
sabe en qué compañía se entra y el idioma depende de eso.

La regla de resolución —lo de la persona, si no lo de la compañía, si no `es`—
se prueba sin base en `tests/domain/test_locale.py`. Acá no se puede cambiar el
idioma de nadie: la pila de pruebas no publica la base y todavía no hay endpoint
para elegirlo (es T-810). Cuando lo haya, esta prueba es donde se cierra el
círculo.
"""

from __future__ import annotations

import base64
import json

import pytest

from tests.conftest import ADMIN, CONTADORA, Api, entrar


def payload(token: str) -> dict:
    """El cuerpo del JWT, sin verificar la firma: acá interesa qué dice."""
    cuerpo = token.split(".")[1]
    relleno = "=" * (-len(cuerpo) % 4)
    return json.loads(base64.urlsafe_b64decode(cuerpo + relleno))


class TestElTokenTraeElIdioma:
    def test_el_login_directo_lo_trae(self, api: Api):
        cuerpo = entrar(Api(api.base), ADMIN["email"], ADMIN["password"])
        assert payload(cuerpo["access_token"])["loc"] == "es"

    def test_elegir_compania_lo_trae(self, api: Api, contadora: dict):
        # La contadora tiene dos compañías, así que pasa por `/auth/company`:
        # es el otro sitio que emite un token de sesión, y el que se usa para
        # cambiar de compañía sin volver a escribir la contraseña (RF-28).
        cliente = Api(api.base)
        cuerpo = entrar(
            cliente, CONTADORA["email"], CONTADORA["password"], aceptando_invitaciones=True
        )
        assert payload(cuerpo["access_token"])["loc"] == "es"

    def test_el_de_transito_no_lo_trae(self, api: Api, contadora: dict):
        # Sin compañía elegida no hay idioma que resolver: el de tránsito solo
        # dice quién es la persona. La pantalla de selección sale en el idioma
        # base, que es lo único que se puede saber en ese momento.
        cliente = Api(api.base)
        cuerpo = cliente.ok(
            "POST",
            "/auth/login",
            {"email": CONTADORA["email"], "password": CONTADORA["password"]},
        )
        if cuerpo.get("tipo") != "transito":
            pytest.skip("la contadora entró directo: no hay token de tránsito que revisar")
        assert "loc" not in payload(cuerpo["access_token"])


class TestCambiarElIdiomaDeLaPersona:
    """`POST /auth/locale` (T-810).

    Cada prueba deja el idioma como estaba: la pila de pruebas es compartida y
    una compañía que se quede en portugués haría fallar a la siguiente por una
    razón que no tiene nada que ver con lo que prueba.
    """

    def test_elegir_uno_emite_un_token_nuevo_con_ese_idioma(self, api: Api):
        cliente = Api(api.base)
        entrar(cliente, ADMIN["email"], ADMIN["password"])
        try:
            cuerpo = cliente.ok("POST", "/auth/locale", {"locale": "en"})
            assert cuerpo["locale"] == "en"
            assert cuerpo["user_locale"] == "en"
            assert payload(cuerpo["access_token"])["loc"] == "en"

            # Y el token nuevo sirve: con él, /users/me también dice inglés.
            cliente.token = cuerpo["access_token"]
            assert cliente.ok("GET", "/users/me")["locale"] == "en"
        finally:
            cliente.ok("POST", "/auth/locale", {"locale": None})

    def test_borrar_la_preferencia_vuelve_a_heredar(self, api: Api):
        cliente = Api(api.base)
        entrar(cliente, ADMIN["email"], ADMIN["password"])
        cliente.ok("POST", "/auth/locale", {"locale": "pt"})

        cuerpo = cliente.ok("POST", "/auth/locale", {"locale": None})
        # Nulo no es «español»: es «como esté la compañía», que hoy es español.
        assert cuerpo["user_locale"] is None
        assert cuerpo["locale"] == "es"

    def test_un_idioma_sin_catalogo_se_rechaza(self, api: Api):
        cliente = Api(api.base)
        entrar(cliente, ADMIN["email"], ADMIN["password"])
        estado, cuerpo = cliente.call("POST", "/auth/locale", {"locale": "fr"})
        assert estado == 400
        assert cuerpo["detail"]["code"] == "unsupported_locale"


class TestCambiarElIdiomaDeLaCompania:
    """`PUT /settings/locales` (T-810, T-811)."""

    def test_el_de_la_compania_lo_hereda_quien_no_eligio(self, api: Api):
        cliente = Api(api.base)
        entrar(cliente, ADMIN["email"], ADMIN["password"])
        try:
            cuerpo = cliente.ok(
                "PUT", "/settings/locales", {"locale": "pt", "document_locale": "es"}
            )
            assert cuerpo["locale"] == "pt"
            assert payload(cuerpo["access_token"])["loc"] == "pt"

            # El del documento no es el de la pantalla y no se movió (RN-29).
            assert cuerpo["document_locale"] == "es"
            cliente.token = cuerpo["access_token"]
            yo = cliente.ok("GET", "/users/me")
            assert (yo["locale"], yo["document_locale"]) == ("pt", "es")
        finally:
            cliente.ok("PUT", "/settings/locales", {"locale": "es", "document_locale": "es"})

    def test_lo_que_eligio_la_persona_le_gana_a_la_compania(self, api: Api):
        cliente = Api(api.base)
        entrar(cliente, ADMIN["email"], ADMIN["password"])
        try:
            cliente.ok("POST", "/auth/locale", {"locale": "en"})
            cuerpo = cliente.ok(
                "PUT", "/settings/locales", {"locale": "pt", "document_locale": "pt"}
            )
            # La compañía pasó a portugués y esta persona sigue en inglés.
            assert cuerpo["locale"] == "en"
            assert payload(cuerpo["access_token"])["loc"] == "en"
            # El del documento sí es de la compañía, no de la persona.
            assert cuerpo["document_locale"] == "pt"
        finally:
            cliente.ok("POST", "/auth/locale", {"locale": None})
            cliente.ok("PUT", "/settings/locales", {"locale": "es", "document_locale": "es"})

    def test_un_cajero_no_puede_cambiarlo(self, api: Api, cajero: Api):
        # Es configuración del negocio: el cajero cambia el suyo, no el de todos.
        estado, cuerpo = cajero.call(
            "PUT", "/settings/locales", {"locale": "en", "document_locale": "en"}
        )
        assert estado == 403
        assert cuerpo["detail"]["code"] == "admin_only"

    def test_un_idioma_sin_catalogo_se_rechaza(self, api: Api):
        cliente = Api(api.base)
        entrar(cliente, ADMIN["email"], ADMIN["password"])
        estado, cuerpo = cliente.call(
            "PUT", "/settings/locales", {"locale": "es", "document_locale": "de"}
        )
        assert estado == 400
        assert cuerpo["detail"]["code"] == "unsupported_locale"
