"""La membresía se acepta, no se impone (T-229).

Antes, un administrador podía agregar a su compañía cualquier correo que
existiera en el sistema, y esa compañía le aparecía a la otra persona en la
lista al entrar. No podía hacerle daño —tenía que elegirla para que pasara
algo— pero tampoco le había preguntado.

Con base compartida eso importa más de lo que parece. La lista de compañías de
alguien es información sobre con quién trabaja; llenársela de invitados ajenos
es ruido, y además una superficie de engaño: basta con dar de alta una compañía
que se llame parecido a la suya para que aparezca ahí, junto a la de verdad.

Lo que estas pruebas fijan es la frontera: **crear** una cuenta y **sumar** una
cuenta ajena no son la misma operación, aunque las dos terminen en una fila de
`user_companies`.
"""

from __future__ import annotations

import pytest

from .conftest import API, Api, entrar, marca_unica

pytestmark = pytest.mark.characterization


def _persona_nueva() -> dict:
    marca = marca_unica()
    return {
        "name": "Invitada",
        "lastName": "Prueba",
        "secondName": marca,
        "identification": f"8{marca}",
        "birth_date": "1992-02-02",
        "telephone": "80000009",
        "email": f"invitada.{marca}@pruebas.ventasys.cr",
        "password": "prueba123",
    }


def _companias_de(cliente: Api, persona: dict) -> tuple[str, list[dict]]:
    """Autentica y devuelve (token, lista). No elige compañía."""
    cuerpo = cliente.ok(
        "POST", "/auth/login", {"email": persona["email"], "password": persona["password"]}
    )
    return cuerpo["access_token"], cuerpo["companies"]


class TestInvitacionPendiente:
    def test_sumar_una_cuenta_ajena_la_deja_pendiente_y_sin_acceso(self, api: Api):
        persona = _persona_nueva()
        api.registrar(persona)
        api.ok("POST", "/users/membership", {"email": persona["email"], "role": "cajero"})

        suyo = Api(API)
        token, companias = _companias_de(suyo, persona)

        assert len(companias) == 1
        invitacion = companias[0]
        assert invitacion["pendiente"] is True
        assert invitacion["puede_entrar"] is False, (
            "una invitación sin responder no puede abrir la compañía"
        )
        assert invitacion["motivo"] == "invitacion_pendiente"

    def test_con_la_invitacion_sin_aceptar_no_se_puede_elegir_esa_compania(self, api: Api):
        """El intento directo, saltándose la pantalla.

        Responde 404 y no 403 por la misma razón que el resto del aislamiento: un
        403 confirmaría que la compañía existe.
        """
        persona = _persona_nueva()
        api.registrar(persona)
        api.ok("POST", "/users/membership", {"email": persona["email"], "role": "cajero"})

        suyo = Api(API)
        token, companias = _companias_de(suyo, persona)
        suyo.token = token

        estado, _ = suyo.call("POST", "/auth/company", {"company_id": companias[0]["id"]})
        assert estado == 404

    def test_al_aceptarla_se_puede_entrar_y_con_el_rol_que_le_ofrecieron(self, api: Api):
        persona = _persona_nueva()
        api.registrar(persona)
        api.ok("POST", "/users/membership", {"email": persona["email"], "role": "cajero"})

        suyo = Api(API)
        token, companias = _companias_de(suyo, persona)
        suyo.token = token
        company_id = companias[0]["id"]

        actualizada = suyo.ok(
            "POST", "/auth/invitation", {"company_id": company_id, "accion": "aceptar"}
        )
        assert actualizada[0]["pendiente"] is False
        assert actualizada[0]["puede_entrar"] is True

        sesion = suyo.ok("POST", "/auth/company", {"company_id": company_id})
        suyo.token = sesion["access_token"]
        assert suyo.ok("GET", "/users/me")["role"] == "cajero"

    def test_al_rechazarla_la_compania_desaparece_de_su_lista(self, api: Api):
        """Rechazar no es dejarla pendiente para siempre.

        Si la compañía siguiera apareciendo, rechazar no serviría de nada: la
        lista quedaría llena de invitaciones muertas y el ruido volvería.
        """
        persona = _persona_nueva()
        api.registrar(persona)
        api.ok("POST", "/users/membership", {"email": persona["email"], "role": "cajero"})

        suyo = Api(API)
        token, companias = _companias_de(suyo, persona)
        suyo.token = token

        quedan = suyo.ok(
            "POST", "/auth/invitation", {"company_id": companias[0]["id"], "accion": "rechazar"}
        )
        assert quedan == []
        assert suyo.ok("GET", "/auth/companies") == []

    def test_volver_a_invitar_a_quien_rechazo_no_lo_mete_de_una(self, api: Api):
        """Haber dicho que no una vez no es haber dicho que sí."""
        persona = _persona_nueva()
        api.registrar(persona)
        api.ok("POST", "/users/membership", {"email": persona["email"], "role": "cajero"})

        suyo = Api(API)
        token, companias = _companias_de(suyo, persona)
        suyo.token = token
        suyo.ok("POST", "/auth/invitation", {"company_id": companias[0]["id"], "accion": "rechazar"})

        api.ok("POST", "/users/membership", {"email": persona["email"], "role": "admin"})

        _, de_nuevo = _companias_de(Api(API), persona)
        assert len(de_nuevo) == 1
        assert de_nuevo[0]["pendiente"] is True, (
            "reinvitar a quien rechazó no puede dar acceso sin volver a preguntar"
        )

    def test_aceptar_dos_veces_no_pasa_desapercibido(self, api: Api):
        persona = _persona_nueva()
        api.registrar(persona)
        api.ok("POST", "/users/membership", {"email": persona["email"], "role": "cajero"})

        suyo = Api(API)
        token, companias = _companias_de(suyo, persona)
        suyo.token = token
        company_id = companias[0]["id"]

        suyo.ok("POST", "/auth/invitation", {"company_id": company_id, "accion": "aceptar"})
        estado, _ = suyo.call("POST", "/auth/invitation", {"company_id": company_id, "accion": "aceptar"})
        assert estado == 409

    def test_no_se_puede_responder_por_la_invitacion_de_otro(self, api: Api, api_b: Api):
        """La invitación es de quien la recibe, no de quien la manda."""
        persona = _persona_nueva()
        api.registrar(persona)
        api.ok("POST", "/users/membership", {"email": persona["email"], "role": "cajero"})

        # El administrador que invitó intenta aceptarla en nombre de la persona.
        estado, _ = api.call(
            "POST", "/auth/invitation", {"company_id": api.company_id, "accion": "aceptar"}  # type: ignore[attr-defined]
        )
        assert estado in (404, 409), (
            "un administrador no puede aceptar la invitación que él mismo mandó"
        )


class TestCuandoNoHayQueInvitar:
    def test_la_cuenta_que_crea_el_administrador_nace_aceptada(self, api: Api):
        """No es una excepción a la regla: es que no hay a quién preguntarle.

        Acá el administrador no está sumando la cuenta de otro —la está
        creando, le puso el correo y la contraseña—. Pedirle a esa cuenta que
        acepte una invitación a sí misma no protegería a nadie.
        """
        persona = _persona_nueva()
        creada = api.ok("POST", "/persons/register", persona)
        # `/persons/register` ya creó la identidad; para provocar el camino de
        # «el administrador crea la cuenta» hace falta una persona sin usuario,
        # así que se usa el id_person recién creado con otro correo.
        marca = marca_unica()
        nueva = api.ok(
            "POST",
            "/users/",
            {
                "email": f"creada.{marca}@pruebas.ventasys.cr",
                "password": "prueba123",
                "id_person": creada["id_person"],
                "role": "cajero",
            },
        )

        suyo = Api(API)
        cuerpo = suyo.ok(
            "POST", "/auth/login", {"email": nueva["email"], "password": "prueba123"}
        )
        assert cuerpo["tipo"] == "sesion", (
            "una cuenta creada por el administrador tiene que entrar sin aceptar nada"
        )

    def test_bootstrap_deja_la_membresia_aceptada(self, api: Api):
        """Si no, una instalación nueva quedaría sin poder entrar.

        `api` sale de `bootstrap.py`: que esta sesión exista ya lo demuestra,
        pero conviene decirlo en voz alta —es la razón por la que el guion no
        crea invitaciones—.
        """
        companias = api.ok("GET", "/auth/companies")
        assert companias, "el administrador inicial no tiene compañía"
        assert all(not c["pendiente"] for c in companias)
