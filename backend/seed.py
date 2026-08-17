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

PRODUCTOS = [
    ("Arroz Tío Pelón 1kg", "Arroz blanco 80% grano entero", 1450, 120, "7441000100015", 1),
    ("Frijoles negros 900g", "Frijol negro seleccionado", 1690, 84, "7441000100022", 1),
    ("Aceite Sabemas 900ml", "Aceite vegetal de girasol", 2350, 46, "7441000100039", 1),
    ("Azúcar Doña María 1kg", "Azúcar blanca refinada", 1250, 95, "7441000100046", 1),
    ("Sal Sol 1kg", "Sal refinada yodada", 620, 140, "7441000100053", 1),
    ("Pasta espagueti 400g", "Pasta de sémola de trigo", 890, 72, "7441000100060", 1),
    ("Café 1820 500g", "Café molido tueste medio", 4250, 38, "7441000200014", 2),
    ("Coca-Cola 2L", "Refresco de cola", 1790, 64, "7441000200021", 2),
    ("Agua Cristal 600ml", "Agua purificada sin gas", 690, 180, "7441000200038", 2),
    ("Jugo Del Valle 1L", "Néctar de naranja", 1390, 52, "7441000200045", 2),
    ("Cerveza Imperial 350ml", "Cerveza lager, lata", 1150, 96, "7441000200052", 2),
    ("Té helado Lipton 500ml", "Té negro con limón", 950, 7, "7441000200069", 2),
    ("Leche Dos Pinos 1L", "Leche entera UHT", 1290, 58, "7441000300013", 3),
    ("Queso Turrialba 400g", "Queso fresco artesanal", 3450, 22, "7441000300020", 3),
    ("Yogurt natural 1kg", "Yogurt sin azúcar añadida", 2290, 31, "7441000300037", 3),
    ("Natilla Dos Pinos 200g", "Crema agria", 1180, 9, "7441000300044", 3),
    ("Pan cuadrado Bimbo", "Pan blanco de molde 680g", 1850, 40, "7441000400012", 4),
    ("Tortillas de maíz 20u", "Tortilla de maíz nixtamalizado", 1090, 55, "7441000400029", 4),
    ("Pan dulce surtido", "Bolsa de 6 unidades", 1650, 18, "7441000400036", 4),
    ("Detergente Irex 1kg", "Detergente en polvo multiusos", 2790, 44, "7441000500011", 5),
    ("Jabón de baño Protex", "Jabón antibacterial 110g", 890, 76, "7441000500028", 5),
    ("Papel higiénico Scott 4u", "Papel higiénico doble hoja", 2450, 5, "7441000500035", 5),
    ("Cloro Magia Blanca 1L", "Blanqueador desinfectante", 1120, 62, "7441000500042", 5),
    ("Galletas Chiky 12u", "Galleta con chispas de chocolate", 1590, 68, "7441000600010", 6),
    ("Tostitos original 200g", "Tortilla chips de maíz", 1950, 34, "7441000600027", 6),
    ("Maní salado 150g", "Maní tostado con sal", 1150, 3, "7441000600034", 6),
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
    for nombre, desc, precio, stock, barcode, cat in PRODUCTOS:
        status, _ = api.call("POST", "/products/add_product", {
            "name": nombre, "description": desc, "price": precio, "stock": stock,
            "barcode": barcode, "created_at": ahora, "category_id": cat,
        })
        creados += status == 200
    print(f"  {creados} creados, {len(PRODUCTOS) - creados} ya existían")

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
