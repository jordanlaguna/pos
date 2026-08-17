"""
Andamiaje de las pruebas.

Las de caracterización hablan con la API por HTTP, igual que lo hace el POS, y
contra MySQL de verdad. No se usa SQLite: la venta toma `SELECT ... FOR UPDATE`
para que dos cajas no vendan la misma última unidad, y SQLite no lo entiende.
Una prueba que pasa sobre un motor que no es el de producción no prueba lo que
uno cree.

La pila es la de `docker-compose.test.yml`, desechable y en el puerto 8002. Si
no está arriba, las pruebas se **omiten** con el motivo en pantalla en vez de
fallar: un fallo rojo por no haber levantado Docker enseña a ignorar el rojo.
"""

from __future__ import annotations

import itertools
import os
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest
import requests

# `app/database/database.py` arma la URL de MySQL **al importarse**, y sin las
# variables de entorno el puerto queda en la cadena "None" y `create_engine`
# revienta antes de que ninguna prueba corra. Ninguna prueba usa ese motor
# —`test_tenancy.py` crea el suyo en memoria y las demás hablan por HTTP— pero
# importar un modelo arrastra el módulo igual. Valores de relleno, nunca se
# conectan:
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "3306")
os.environ.setdefault("DB_USER", "sin_usar")
os.environ.setdefault("DB_PASS", "sin_usar")
os.environ.setdefault("DB_NAME", "sin_usar")

_secuencia = itertools.count(1)


def marca_unica() -> str:
    """
    Sufijo distinto en cada llamada, y distinto entre corridas.

    El reloj solo no alcanza: en Windows `time.time_ns()` avanza a saltos de
    unos 15 ms, así que devuelve el mismo valor a ocho llamadas seguidas. Con la
    suite tardando minutos eso no se notaba; ahora que corre en menos de dos
    segundos, dos productos creados uno detrás del otro recibían el mismo código
    de barras y el segundo se pisaba con el primero. El contador da la unicidad
    dentro de la corrida y el reloj la da entre corridas.
    """
    return f"{time.time():.0f}{next(_secuencia):04d}"

# 127.0.0.1 y no «localhost» a propósito. En Windows, `localhost` resuelve
# primero a ::1, el puerto solo escucha en IPv4, y cada conexión paga el intento
# fallido antes de reintentar: unos dos segundos por petición, que con seis
# peticiones por prueba son doce. Con la IP literal la suite baja de dos minutos
# y medio a unos segundos.
API = os.environ.get("VENTASYS_TEST_API", "http://127.0.0.1:8002")
TIMEOUT = 15

#: Administrador de la compañía A. Desde F2 no basta con registrarse: quien se
#: registra queda sin compañía a la que entrar. El alta la hace `bootstrap.py`,
#: que es el mismo camino que se usa en una instalación de verdad.
ADMIN = {
    "name": "Ana",
    "lastName": "Prueba",
    "secondName": "Caracterizacion",
    "identification": "100000001",
    "birth_date": "1990-01-01",
    "telephone": "80000001",
    "email": "admin@pruebas.ventasys.cr",
    "password": "prueba123",
}

#: Administrador de la compañía B. Existe para poder probar lo único que de
#: verdad importa de F2: que con el token de A no se vea nada de B (T-214).
ADMIN_B = {
    "email": "admin.b@pruebas.ventasys.cr",
    "password": "prueba123",
}

#: La contadora que atiende los dos locales. Una identidad, dos membresías, dos
#: roles distintos: es el caso que motivó separar `users` de `user_companies`
#: (RN-3, T-216) y sin él la decisión no queda comprobada.
CONTADORA = {
    "email": "contadora@pruebas.ventasys.cr",
    "password": "prueba123",
}

BACKEND = Path(__file__).resolve().parent.parent


def bootstrap(**opciones: str) -> None:
    """Da de alta una compañía en la pila de pruebas.

    Corre `bootstrap.py` dentro del contenedor porque la base de la pila de
    pruebas no publica puerto —vive en tmpfs y muere con ella—. Se usa el mismo
    guion que en una instalación real, así que si el arranque se rompe, se rompe
    también acá y no solo el día de instalar.
    """
    orden = [
        "docker", "compose", "-f", "docker-compose.test.yml",
        "exec", "-T", "fastapi", "python", "bootstrap.py",
    ]
    for clave, valor in opciones.items():
        orden += [f"--{clave.replace('_', '-')}", str(valor)]

    resultado = subprocess.run(
        orden, cwd=BACKEND, capture_output=True, text=True, encoding="utf-8", timeout=120
    )
    if resultado.returncode != 0:
        pytest.skip(
            "No se pudo dar de alta la compañía de pruebas con bootstrap.py:\n"
            f"{resultado.stdout}\n{resultado.stderr}"
        )


def entrar(
    cliente: "Api", email: str, password: str, *, aceptando_invitaciones: bool = False
) -> dict:
    """Login de dos pasos: autentica y, si hace falta, elige compañía.

    Devuelve el cuerpo del paso que dejó la sesión abierta. La contadora pasa
    siempre por el segundo paso —tiene dos compañías—; el resto entra directo.

    `aceptando_invitaciones` responde que sí a las que estén pendientes antes de
    elegir. Es lo que hace una persona recién agregada a una compañía (T-229), y
    está explícito en el parámetro y no metido siempre: si aceptar fuera
    automático, ninguna prueba notaría que la invitación dejó de existir.
    """
    cuerpo = cliente.ok("POST", "/auth/login", {"email": email, "password": password})

    if aceptando_invitaciones and cuerpo.get("tipo") == "transito":
        cliente.token = cuerpo["access_token"]
        for pendiente in [c for c in cuerpo["companies"] if c["pendiente"]]:
            cuerpo["companies"] = cliente.ok(
                "POST",
                "/auth/invitation",
                {"company_id": pendiente["id"], "accion": "aceptar"},
            )

    if cuerpo.get("tipo") == "transito":
        disponibles = [c for c in cuerpo["companies"] if c["puede_entrar"]]
        assert disponibles, f"{email} no tiene ninguna compañía disponible"
        cliente.token = cuerpo["access_token"]
        cuerpo = cliente.ok("POST", "/auth/company", {"company_id": disponibles[0]["id"]})

    cliente.token = cuerpo["access_token"]
    return cuerpo


class Api:
    """Cliente mínimo. Devuelve (estado, cuerpo) y nunca lanza por un 4xx."""

    def __init__(self, base: str) -> None:
        self.base = base
        self.token: str | None = None
        # Una sola sesión para toda la corrida: mantiene viva la conexión en vez
        # de abrir y cerrar un socket por petición.
        self.http = requests.Session()

    def call(
        self, method: str, path: str, body: Any = None, token: str | None = ...
    ) -> tuple[int, Any]:
        headers = {"Content-Type": "application/json"}
        # `token=...` significa «el de la sesión»; `token=None`, explícitamente
        # sin credenciales, que es como se prueba que un endpoint responde 401.
        usado = self.token if token is ... else token
        if usado:
            headers["Authorization"] = f"Bearer {usado}"

        r = self.http.request(
            method, f"{self.base}{path}", json=body, headers=headers, timeout=TIMEOUT
        )
        try:
            return r.status_code, r.json()
        except ValueError:
            return r.status_code, r.text

    def ok(self, method: str, path: str, body: Any = None) -> Any:
        """Igual, pero exige que haya salido bien. Para los pasos de preparación."""
        estado, cuerpo = self.call(method, path, body)
        assert estado == 200, f"{method} {path} respondió {estado}: {cuerpo}"
        return cuerpo

    def registrar(self, persona: dict) -> None:
        """
        Alta de una persona, tolerante a que ya exista.

        Distingue el duplicado (400) de un cuerpo mal armado (422). Sin esa
        distinción, un cambio en el esquema de la API haría que la prueba se
        saltara el registro en silencio y fallara mucho después, en el login,
        con «credenciales incorrectas» —que apunta al lado equivocado—.
        """
        estado, cuerpo = self.call("POST", "/persons/register", persona)
        assert estado in (200, 400), (
            f"el alta de {persona['email']} respondió {estado}: {cuerpo}"
        )


def _stack_arriba(base: str) -> bool:
    try:
        return requests.get(f"{base}/health", timeout=3).status_code == 200
    except requests.RequestException:
        return False


@pytest.fixture(scope="session")
def api() -> Api:
    """Sesión de administrador de la compañía A contra la pila de pruebas."""
    if not _stack_arriba(API):
        pytest.skip(
            f"No hay backend en {API}. Levantalo con:\n"
            "  docker compose -f docker-compose.test.yml up -d --build"
        )

    bootstrap(
        afiliado=1,
        compania=1,
        nombre="Compañía A de pruebas",
        email=ADMIN["email"],
        password=ADMIN["password"],
        rol="admin",
        nombre_persona=ADMIN["name"],
        apellido=ADMIN["lastName"],
        cedula=ADMIN["identification"],
    )

    cliente = Api(API)
    sesion = entrar(cliente, ADMIN["email"], ADMIN["password"])

    yo = cliente.ok("GET", "/users/me")
    assert yo["role"] == "admin", f"{ADMIN['email']} tenía que entrar como administrador"
    cliente.user_id = yo["id_user"]  # type: ignore[attr-defined]
    cliente.company_id = sesion["company_id"]  # type: ignore[attr-defined]
    return cliente


@pytest.fixture(scope="session")
def api_b(api: Api) -> Api:
    """Sesión de administrador de una **segunda** compañía (T-213).

    Depende de `api` a propósito: la compañía A tiene que existir primero. Si B
    fuera la única, su primer producto tendría el id 1 igual que el de A y una
    prueba de aislamiento pasaría sin haber probado nada.
    """
    bootstrap(
        afiliado=2,
        compania=1,
        nombre="Compañía B de pruebas",
        email=ADMIN_B["email"],
        password=ADMIN_B["password"],
        rol="admin",
        nombre_persona="Beto",
        apellido="Segundo",
        cedula="200000001",
    )

    cliente = Api(API)
    sesion = entrar(cliente, ADMIN_B["email"], ADMIN_B["password"])
    cliente.user_id = cliente.ok("GET", "/users/me")["id_user"]  # type: ignore[attr-defined]
    cliente.company_id = sesion["company_id"]  # type: ignore[attr-defined]
    assert cliente.company_id != api.company_id  # type: ignore[attr-defined]
    return cliente


@pytest.fixture(scope="session")
def contadora(api: Api, api_b: Api) -> dict:
    """Una sola cuenta con membresía en las dos compañías, con roles distintos.

    Administradora en A y cajera en B. Que el rol cambie al cambiar de compañía
    es la prueba de que el rol pertenece a la membresía y no a la persona
    (RN-3): es el caso que motivó separar `users` de `user_companies`.
    """
    bootstrap(
        afiliado=1,
        compania=1,
        email=CONTADORA["email"],
        password=CONTADORA["password"],
        rol="admin",
        nombre_persona="Carmen",
        apellido="Contadora",
        cedula="300000001",
    )
    bootstrap(
        afiliado=2,
        compania=1,
        email=CONTADORA["email"],
        password=CONTADORA["password"],
        rol="cajero",
    )
    return CONTADORA


@pytest.fixture(scope="session")
def categoria(api: Api) -> int:
    """Una categoría donde colgar los productos de prueba."""
    api.call("POST", "/categories/register_category", {"name": "Pruebas"})
    for c in api.ok("GET", "/categories/categories_list"):
        if c["name"] == "Pruebas":
            return c["id"]
    raise AssertionError("no se pudo crear ni encontrar la categoría de pruebas")


@pytest.fixture
def producto(api: Api, categoria: int):
    """
    Fábrica de productos con precio y existencias a la medida de cada prueba.

    Cada uno lleva un código de barras único derivado del reloj, para que dos
    corridas seguidas contra la misma base no choquen entre sí.
    """
    creados: list[dict] = []

    def crear(nombre: str, precio: float, stock: int) -> dict:
        marca = marca_unica()
        cuerpo = {
            "name": f"{nombre} {marca}",
            "description": "producto de prueba",
            "price": precio,
            "stock": stock,
            "barcode": f"T{marca}",
            "created_at": "2026-01-01T00:00:00",
            "category_id": categoria,
        }
        api.ok("POST", "/products/add_product", cuerpo)
        creado = api.ok("GET", f"/products/product/{cuerpo['barcode']}")
        creados.append(creado)
        return creado

    return crear


@pytest.fixture
def cajero(api: Api) -> Api:
    """
    Un cajero recién creado, con su propia sesión.

    Las pruebas de arqueo lo necesitan porque el turno se delimita por ventana
    de tiempo sobre `sales.created_at`, que es `DATETIME` **sin fracción de
    segundo**: el filtro es `created_at >= opened_at`, así que una venta hecha
    en el mismo segundo en que se abre la caja entra en el turno nuevo. Entre
    personas eso no pasa nunca —nadie cobra y abre caja dentro del mismo
    segundo—, pero las pruebas corren en milisegundos y sí lo alcanzan.

    Se resuelve con aislamiento y no con un `sleep`: `build_report` filtra
    también por `user_id`, así que un cajero propio por prueba deja el arqueo
    limpio y la suite rápida.
    """
    marca = marca_unica()
    persona = {
        "name": "Caja",
        "lastName": "Turno",
        "secondName": marca,
        "identification": f"9{marca}",
        "birth_date": "1995-05-05",
        "telephone": "80000000",
        "email": f"turno.{marca}@pruebas.ventasys.cr",
        "password": "prueba123",
    }
    api.registrar(persona)
    # Registrarse ya no alcanza: crea la identidad, no la pertenencia. El
    # administrador invita, y la persona acepta —la membresía nace pendiente
    # (T-229) y no autoriza nada hasta entonces—.
    api.ok("POST", "/users/membership", {"email": persona["email"], "role": "cajero"})

    suyo = Api(api.base)
    entrar(suyo, persona["email"], persona["password"], aceptando_invitaciones=True)
    suyo.user_id = suyo.ok("GET", "/users/me")["id_user"]  # type: ignore[attr-defined]
    return suyo


def cerrar_caja_abierta(api: Api) -> None:
    """Deja el turno cerrado, pase lo que pase antes."""
    estado, actual = api.call("GET", "/cash/current")
    if estado == 200 and actual:
        api.call(
            "POST",
            "/cash/close",
            {
                "user_id": api.user_id,  # type: ignore[attr-defined]
                "closing_amount": actual["expected_amount"],
                "notes": "cierre de limpieza",
            },
        )
