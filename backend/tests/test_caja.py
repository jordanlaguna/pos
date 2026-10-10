"""
La sesión elige su caja (F15, T-1505, RN-102; plan §15.3).

Contra la pila de verdad, en una compañía propia con dos cajas: el login deja
de entrar directo y ofrece las cajas, `POST /auth/company` abre en la elegida
—y solo si es de esa compañía y está activa—, cambiar de idioma la conserva, y
sin elegir se abre en la de siempre.
"""

from __future__ import annotations

import pytest

from .conftest import API, Api, codigo
from .test_sucursales import compania_propia, por_codigo, sucursales, terminales


@pytest.fixture
def dos_cajas() -> tuple[Api, str, dict, dict]:
    """Una compañía propia con su caja de siempre y una segunda, recién abierta."""
    dueno = compania_propia("caja")
    sucursal = sucursales(dueno)[0]
    _, cuerpo = dueno.call(
        "POST",
        "/offices/terminals",
        {"branch_id": sucursal["id"], "codigo": "2", "nombre": "Caja dos"},
    )
    segunda = por_codigo(cuerpo["terminals"], "00002")
    primera = por_codigo(terminales(dueno), "00001")
    yo = dueno.ok("GET", "/users/me")
    return dueno, yo["email"], primera, segunda


def login(email: str) -> tuple[Api, dict]:
    cliente = Api(API)
    cuerpo = cliente.ok("POST", "/auth/login", {"email": email, "password": "prueba123"})
    cliente.token = cuerpo["access_token"]
    return cliente, cuerpo


def abrir_en(cliente: Api, company_id: int, terminal_id: int | None):
    cuerpo = {"company_id": company_id}
    if terminal_id is not None:
        cuerpo["terminal_id"] = terminal_id
    return cliente.call("POST", "/auth/company", cuerpo)


def caja_de(cliente: Api) -> dict:
    yo = cliente.ok("GET", "/users/me")
    return {
        "terminal_id": yo["terminal_id"],
        "terminal_code": yo["terminal_code"],
        "terminal_name": yo["terminal_name"],
        "terminals_available": yo["terminals_available"],
    }


class TestElLogin:
    def test_con_dos_cajas_ya_no_entra_directo_y_las_ofrece(self, dos_cajas):
        _, email, primera, segunda = dos_cajas
        _, cuerpo = login(email)
        assert cuerpo["tipo"] == "transito"
        [opcion] = [c for c in cuerpo["companies"] if c["puede_entrar"]]
        cajas = {t["codigo"]: t for t in opcion["terminals"]}
        assert set(cajas) == {"00001", "00002"}
        assert cajas["00002"]["nombre"] == "Caja dos"
        assert cajas["00002"]["branch_codigo"] == "001" and cajas["00002"]["branch_id"] == primera["branch_id"]

    def test_la_lista_de_companias_tambien_las_trae(self, dos_cajas):
        dueno, _, _, _ = dos_cajas
        [opcion] = dueno.ok("GET", "/auth/companies")
        assert len(opcion["terminals"]) == 2

    def test_con_una_sola_caja_sigue_entrando_directo(self):
        """Una compañía propia nace con una caja: su dueña no ve ninguna pantalla
        y el menú no le ofrece cambiar de caja."""
        dueno = compania_propia("una-caja")
        _, cuerpo = login(dueno.ok("GET", "/users/me")["email"])
        assert cuerpo["tipo"] == "sesion"
        assert caja_de(dueno)["terminals_available"] == 1


class TestElegirLaCaja:
    def test_abre_en_la_elegida(self, dos_cajas):
        _, email, _, segunda = dos_cajas
        cliente, cuerpo = login(email)
        [opcion] = [c for c in cuerpo["companies"] if c["puede_entrar"]]
        estado, sesion = abrir_en(cliente, opcion["id"], segunda["id"])
        assert estado == 200 and sesion["terminal_id"] == segunda["id"]
        cliente.token = sesion["access_token"]
        assert caja_de(cliente) == {
            "terminal_id": segunda["id"],
            "terminal_code": "00002",
            "terminal_name": "Caja dos",
            "terminals_available": 2,
        }

    def test_sin_elegir_abre_en_la_de_siempre(self, dos_cajas):
        _, email, primera, _ = dos_cajas
        cliente, cuerpo = login(email)
        [opcion] = [c for c in cuerpo["companies"] if c["puede_entrar"]]
        estado, sesion = abrir_en(cliente, opcion["id"], None)
        assert estado == 200 and sesion["terminal_id"] == primera["id"]
        cliente.token = sesion["access_token"]
        assert caja_de(cliente)["terminal_code"] == "00001"

    def test_una_caja_ajena_o_apagada_no(self, dos_cajas, api: Api):
        """Elegir entre las propias no es elegir desde afuera (RN-14): lo que no
        se puede es inventarse una, y el «no» es el mismo que si no existiera."""
        dueno, email, _, segunda = dos_cajas
        cliente, cuerpo = login(email)
        [opcion] = [c for c in cuerpo["companies"] if c["puede_entrar"]]

        # La caja 1 de la compañía principal: existe, pero no es de esta.
        ajena = api.ok("GET", "/users/me")["terminal_id"]
        assert codigo(abrir_en(cliente, opcion["id"], ajena), 404) == "terminal_not_found"
        assert codigo(abrir_en(cliente, opcion["id"], 99_999_999), 404) == "terminal_not_found"

        # Apagada: tampoco. Y vuelve a encenderse para no dejar la fixture coja.
        dueno.ok("PUT", f"/offices/terminals/{segunda['id']}", {"activa": False})
        try:
            assert codigo(abrir_en(cliente, opcion["id"], segunda["id"]), 404) == "terminal_not_found"
        finally:
            dueno.ok("PUT", f"/offices/terminals/{segunda['id']}", {"activa": True})

    def test_cambiar_de_idioma_conserva_la_caja(self, dos_cajas):
        """`token_de_sesion` se reemite con la caja del token vigente (plan §15.3):
        sin eso, elegir inglés devolvería a la cajera a la caja 1 sin aviso."""
        _, email, _, segunda = dos_cajas
        cliente, cuerpo = login(email)
        [opcion] = [c for c in cuerpo["companies"] if c["puede_entrar"]]
        _, sesion = abrir_en(cliente, opcion["id"], segunda["id"])
        cliente.token = sesion["access_token"]

        try:
            nuevo = cliente.ok("POST", "/auth/locale", {"locale": "en"})
            cliente.token = nuevo["access_token"]
            assert caja_de(cliente)["terminal_code"] == "00002"

            # Y el de la compañía, que también reemite (`PUT /settings/locales`).
            nuevo = cliente.ok(
                "PUT", "/settings/locales", {"locale": "es", "document_locale": "es"}
            )
            cliente.token = nuevo["access_token"]
            assert caja_de(cliente)["terminal_code"] == "00002"
        finally:
            cliente.ok("POST", "/auth/locale", {"locale": None})

    def test_cambiar_de_caja_es_elegir_de_nuevo(self, dos_cajas):
        """Desde la sesión, con el token vigente: la caja conserva el idioma."""
        _, email, primera, segunda = dos_cajas
        cliente, cuerpo = login(email)
        [opcion] = [c for c in cuerpo["companies"] if c["puede_entrar"]]
        _, sesion = abrir_en(cliente, opcion["id"], segunda["id"])
        cliente.token = sesion["access_token"]

        estado, otra = abrir_en(cliente, opcion["id"], primera["id"])
        assert estado == 200
        cliente.token = otra["access_token"]
        assert caja_de(cliente)["terminal_code"] == "00001"
