#!/usr/bin/env python3
"""Carga inicial de VentaSys.

Deja el sistema listo para usar: usuarios, categorías, catálogo, clientes y —si
se le pide— algunas ventas para que los reportes no salgan vacíos.

Va contra la API, no contra la base, así que las contraseñas se hashean por el
mismo camino que las de producción y no hace falta escribir hashes a mano en un
.sql. Solo usa la biblioteca estándar: se puede correr en la VM sin instalar nada.

    python3 seed.py                                  # contra localhost:8001
    python3 seed.py --url http://192.168.1.50:8001   # contra otra máquina
    python3 seed.py --ventas 40                      # además, 40 ventas de hoy

Es repetible: lo que ya existe se salta, no se duplica.

Necesita que la compañía exista antes. Crearla no se puede por API —no hay
sesión sin membresía y no hay membresía sin compañía—, así que primero:

    python bootstrap.py --email admin@ventasys.cr --password admin123
"""

import argparse
import collections
import json
import random
import sys
import urllib.error
import urllib.request
from datetime import datetime

ADMIN = {
    "birth_date": "1990-04-12", "identification": "113450678",
    "name": "Jordan", "lastName": "Laguna", "secondName": "Mora",
    "telephone": "88451230", "email": "admin@ventasys.cr", "password": "admin123",
}

CAJEROS = [
    {"birth_date": "1996-11-03", "identification": "118920345", "name": "María",
     "lastName": "Rojas", "secondName": "Vargas", "telephone": "87123344",
     "email": "cajero@ventasys.cr", "password": "cajero123"},
    {"birth_date": "1988-07-25", "identification": "109887654", "name": "Carlos",
     "lastName": "Jiménez", "secondName": "Solano", "telephone": "89905512",
     "email": "carlos@ventasys.cr", "password": "cajero123"},
]

CATEGORIAS = ["Abarrotes", "Bebidas", "Lácteos", "Panadería", "Limpieza", "Snacks"]

# El último campo es el código CABYS, y **no lleva la tarifa al lado a
# propósito**: la tarifa la define el catálogo, y escribirla acá sería una
# segunda fuente de verdad que se desactualiza sola. El seed la pregunta
# (`clasificar`), que además es el mismo camino que recorre una persona.
#
# Los códigos son reales, consultados el 2026-09-06. La mezcla no es casual:
# arroz, frijoles, leche, pan y papel higiénico son canasta básica al 1 % y
# cerveza, jabón y refrescos van al 13 %. Sin esta mezcla el demo enseña un
# catálogo entero al 13 % y F5 parece no existir.
PRODUCTOS = [
    ("Arroz Tío Pelón 1kg", "Arroz blanco 80% grano entero", 1450, 120, "7441000100015", 1, "2316100000100"),
    ("Frijoles negros 900g", "Frijol negro seleccionado", 1690, 84, "7441000100022", 1, "0170102000400"),
    ("Aceite Sabemas 900ml", "Aceite vegetal de girasol", 2350, 46, "7441000100039", 1, "2163200000000"),
    ("Azúcar Doña María 1kg", "Azúcar blanca refinada", 1250, 95, "7441000100046", 1, "2352001010000"),
    ("Sal Sol 1kg", "Sal refinada yodada", 620, 140, "7441000100053", 1, "2399908000200"),
    ("Pasta espagueti 400g", "Pasta de sémola de trigo", 890, 72, "7441000100060", 1, "2371000000200"),
    ("Café 1820 500g", "Café molido tueste medio", 4250, 38, "7441000200014", 2, "2391102010200"),
    ("Coca-Cola 2L", "Refresco de cola", 1790, 64, "7441000200021", 2, "2449003000100"),
    ("Agua Cristal 600ml", "Agua purificada sin gas", 690, 180, "7441000200038", 2, "2441002020000"),
    ("Jugo Del Valle 1L", "Néctar de naranja", 1390, 52, "7441000200045", 2, "2449002000100"),
    ("Cerveza Imperial 350ml", "Cerveza lager, lata", 1150, 96, "7441000200052", 2, "2431000000000"),
    ("Té helado Lipton 500ml", "Té negro con limón", 950, 7, "7441000200069", 2, "2449002000200"),
    ("Leche Dos Pinos 1L", "Leche entera UHT", 1290, 58, "7441000300013", 3, "2211001030000"),
    ("Queso Turrialba 400g", "Queso fresco artesanal", 3450, 22, "7441000300020", 3, "2225101010200"),
    ("Yogurt natural 1kg", "Yogurt sin azúcar añadida", 2290, 31, "7441000300037", 3, None),
    ("Natilla Dos Pinos 200g", "Crema agria", 1180, 9, "7441000300044", 3, None),
    ("Pan cuadrado Bimbo", "Pan blanco de molde 680g", 1850, 40, "7441000400012", 4, "2349002010700"),
    ("Tortillas de maíz 20u", "Tortilla de maíz nixtamalizado", 1090, 55, "7441000400029", 4, "2349001010100"),
    ("Pan dulce surtido", "Bolsa de 6 unidades", 1650, 18, "7441000400036", 4, "2349002010600"),
    ("Detergente Irex 1kg", "Detergente en polvo multiusos", 2790, 44, "7441000500011", 5, "3532201060000"),
    ("Jabón de baño Protex", "Jabón antibacterial 110g", 890, 76, "7441000500028", 5, "3532101010199"),
    ("Papel higiénico Scott 4u", "Papel higiénico doble hoja", 2450, 5, "7441000500035", 5, "3219301000000"),
    ("Cloro Magia Blanca 1L", "Blanqueador desinfectante", 1120, 62, "7441000500042", 5, "3532201010000"),
    ("Galletas Chiky 12u", "Galleta con chispas de chocolate", 1590, 68, "7441000600010", 6, "2342001009900"),
    ("Tostitos original 200g", "Tortilla chips de maíz", 1950, 34, "7441000600027", 6, "2314000990300"),
    ("Maní salado 150g", "Maní tostado con sal", 1150, 3, "7441000600034", 6, None),
]

CLIENTES = [
    ("115670987", "Ana", "Castro", "Núñez", "ana.castro@correo.cr", 88012233, "San José, Curridabat"),
    ("107654321", "Luis", "Fernández", "Alpízar", "luis.f@correo.cr", 87334455, "Heredia, San Francisco"),
    ("119870654", "Gabriela", "Méndez", "Quirós", "gaby.mendez@correo.cr", 86220099, "Cartago, El Carmen"),
    ("112233445", "Roberto", "Salas", "Ureña", "rsalas@correo.cr", 83445566, "Alajuela, centro"),
]

METODOS = ["Efectivo"] * 3 + ["Tarjeta de crédito"] * 2 + ["Transferencia bancaria", "Pago móvil"]
IVA = 0.13


class Api:
    def __init__(self, base):
        self.base = base.rstrip("/")
        self.token = None

    def call(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method)
        req.add_header("Accept", "application/json")
        if data:
            req.add_header("Content-Type", "application/json")
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode()
                return resp.status, (json.loads(raw) if raw else None)
        except urllib.error.HTTPError as e:
            raw = e.read().decode()
            try:
                return e.code, json.loads(raw)
            except json.JSONDecodeError:
                return e.code, raw
        except urllib.error.URLError as e:
            print(f"\n  No se pudo conectar con {self.base}: {e.reason}")
            print("  ¿Está levantado?  docker compose ps")
            sys.exit(1)


def clasificar(api):
    """Le pone su CABYS a cada producto, con la tarifa que diga el catálogo.

    La tarifa **se pregunta, no se escribe**. Es la misma regla que RN-11 le
    aplica a la persona que clasifica desde la pantalla, y saltársela acá sería
    dejar en el repositorio una tabla de tarifas que envejece sin que nadie se
    entere — y el catálogo cambia: Hacienda estrenó el CABYS 2025.

    Sin catálogo no se clasifica y se dice. Inventarse la tarifa sería peor que
    dejar los productos sin clasificar, porque un IVA que no concuerda con el
    CABYS es causa de rechazo del comprobante y acá quedaría escrito como si
    alguien lo hubiera comprobado.
    """
    print("\nCABYS")
    _, productos = api.call("GET", "/products/products_list")
    por_barcode = {p["barcode"]: p["id_product"] for p in (productos or [])}

    tarifas, sin_catalogo = {}, []
    for codigo in dict.fromkeys(p[6] for p in PRODUCTOS if p[6] is not None):
        status, body = api.call("GET", f"/cabys/{codigo}")
        entrada = (body or {}).get("items", [None])[0] if status == 200 else None
        if entrada is None:
            sin_catalogo.append(codigo)
        else:
            tarifas[codigo] = entrada["tax_rate"]

    if sin_catalogo:
        print(f"  {len(sin_catalogo)} códigos sin respuesta del catálogo: se dejan sin clasificar.")
        print(f"  El primero es {sin_catalogo[0]}. ¿Hay salida a internet?")

    # Un `PUT` por código y no uno por producto: es el mismo endpoint de la
    # asignación en lote (T-506), así que el seed recorre el camino que recorre
    # una persona en vez de uno propio que podría divergir sin que nadie lo note.
    asignados, reparto = 0, collections.Counter()
    for codigo, tarifa in tarifas.items():
        ids = [por_barcode[p[4]] for p in PRODUCTOS if p[6] == codigo and p[4] in por_barcode]
        if not ids:
            continue
        status, _ = api.call("PUT", "/products/assign_cabys", {
            "product_ids": ids, "cabys_code": codigo, "tax_rate": tarifa,
        })
        if status == 200:
            asignados += len(ids)
            reparto[tarifa] += len(ids)

    detalle = ", ".join(f"{n} al {t * 100:g} %" for t, n in sorted(reparto.items()))
    print(f"  {asignados} productos clasificados con {len(tarifas)} códigos ({detalle})")

    faltan = sum(1 for p in PRODUCTOS if p[6] is None)
    print(f"  {faltan} quedan sin clasificar **a propósito**: es lo que un catálogo")
    print("  heredado tiene el primer día, y sin eso la asignación en lote no tiene")
    print("  nada que hacer y el aviso del carrito no se ve nunca.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8001", help="URL del backend")
    ap.add_argument("--ventas", type=int, default=0, help="ventas de ejemplo a generar")
    args = ap.parse_args()

    api = Api(args.url)

    status, _ = api.call("GET", "/health")
    if status != 200:
        print(f"El backend respondió {status} en /health.")
        sys.exit(1)
    print(f"Backend accesible en {args.url}\n")

    # --- el administrador entra primero. Los cajeros se crean desde adentro,
    # con membresía en esta compañía: `/persons/register` por sí solo crea una
    # identidad sin ninguna compañía a la que entrar.
    status, body = api.call("POST", "/auth/login",
                            {"email": ADMIN["email"], "password": ADMIN["password"]})
    if status != 200:
        print(f"\n  No se pudo iniciar sesión como {ADMIN['email']}: {body}")
        print(f"  ¿Corriste bootstrap.py?\n"
              f"    python bootstrap.py --email {ADMIN['email']} "
              f"--password {ADMIN['password']}")
        sys.exit(1)
    api.token = body["access_token"]

    # Con varias compañías el login devuelve un token de tránsito y hay que
    # elegir. El seed toma la primera disponible: es un guion de datos de
    # prueba, no una persona decidiendo.
    if body.get("tipo") == "transito":
        disponibles = [c for c in body.get("companies", []) if c["puede_entrar"]]
        if not disponibles:
            print(f"\n  {ADMIN['email']} no tiene ninguna compañía disponible.")
            sys.exit(1)
        status, body = api.call("POST", "/auth/company",
                                {"company_id": disponibles[0]["id"]})
        if status != 200:
            print(f"\n  No se pudo entrar a la compañía: {body}")
            sys.exit(1)
        api.token = body["access_token"]

    _, sesion = api.call("GET", "/users/me")
    print(f"Sesión     {sesion['email']} · compañía {sesion['company_id']} "
          f"· rol {sesion['role']}\n")

    print("Usuarios")
    for persona in CAJEROS:
        status, body = api.call("POST", "/persons/register", persona)
        creado = status == 200
        # La identidad puede existir ya —de otra compañía, o de una corrida
        # anterior—; lo que hay que asegurar es la membresía acá.
        status, _ = api.call("POST", "/users/membership",
                             {"email": persona["email"], "role": "cajero"})
        if status != 200:
            print(f"  {persona['email']:24} no se pudo dar de alta")
            continue
        print(f"  {persona['email']:24} {'creado' if creado else 'ya existía'}, con membresía")

    # --- catálogo
    print("\nCategorías")
    for nombre in CATEGORIAS:
        status, _ = api.call("POST", "/categories/register_category", {"name": nombre})
        print(f"  {nombre:24} {'creada' if status == 200 else 'ya existía'}")

    print("\nProductos")
    creados = 0
    ahora = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    for nombre, desc, precio, stock, barcode, cat, _cabys in PRODUCTOS:
        status, _ = api.call("POST", "/products/add_product", {
            "name": nombre, "description": desc, "price": precio, "stock": stock,
            "barcode": barcode, "created_at": ahora, "category_id": cat,
        })
        creados += status == 200
    print(f"  {creados} creados, {len(PRODUCTOS) - creados} ya existían")

    clasificar(api)

    print("\nClientes")
    creados = 0
    hoy = datetime.now().strftime("%Y-%m-%d")
    for ident, nombre, ap1, ap2, email, tel, dir_ in CLIENTES:
        status, _ = api.call("POST", "/clients/register_client", {
            "identification": ident, "name": nombre, "last_name": ap1,
            "second_name": ap2, "email": email, "telephone": tel,
            "address": dir_, "register_date": hoy,
        })
        creados += status == 200
    print(f"  {creados} creados, {len(CLIENTES) - creados} ya existían")

    # --- ventas de ejemplo
    if args.ventas:
        print(f"\nVentas de ejemplo ({args.ventas})")
        _, productos = api.call("GET", "/products/products_list")
        _, yo = api.call("GET", "/users/me")
        disponibles = [p for p in productos if p["stock"] > 5]
        hechas = 0

        for i in range(args.ventas):
            elegidos = random.sample(disponibles, k=min(random.randint(1, 4), len(disponibles)))
            lineas, subtotal = [], 0.0
            for p in elegidos:
                cant = random.randint(1, 3)
                lineas.append({"id_product": p["id_product"], "stock": cant})
                subtotal += p["price"] * cant

            subtotal = round(subtotal, 2)
            impuesto = round(subtotal * IVA, 2)
            total = round(subtotal + impuesto, 2)
            metodo = random.choice(METODOS)
            recibido = float(-(-total // 1000) * 1000) if metodo == "Efectivo" else total

            status, _ = api.call("POST", "/sales/add_sale", {
                "sale_number": datetime.now().strftime("%Y%m%d%H%M%S") + f"{i:03d}",
                "client_id": None, "user_id": yo["id_user"],
                "subtotal": subtotal, "tax": impuesto, "total": total,
                "payment_method": metodo, "cash_received": recibido,
                "change_given": round(recibido - total, 2),
                "products": lineas,
            })
            hechas += status == 200

        print(f"  {hechas} registradas")
        # La hora la sella el servidor, así que todas quedan con fecha de hoy:
        # por API no se puede fabricar historial de días anteriores.
        print("  (todas con fecha de hoy: el backend sella la hora, no el cliente)")

    print("\n" + "-" * 52)
    print("Listo. Entrá con:")
    print(f"  administrador   {ADMIN['email']} / {ADMIN['password']}")
    print(f"  cajero          {CAJEROS[0]['email']} / {CAJEROS[0]['password']}")
    print("\nCambiá esas contraseñas antes de usarlo de verdad.")


if __name__ == "__main__":
    main()
