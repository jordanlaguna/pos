#!/usr/bin/env python3
"""Siembra las tasas de planilla del país (T-1204, RN-67).

    docker compose exec fastapi python seed_payroll_rates.py

Carga lo que dice `app/infrastructure/payroll_rates_cr.py` —cargas de la CCSS,
tramos y créditos de renta, cesantía y las reglas de incapacidad y embargo—,
cada fila con su fuente y la fecha en que se comprobó. Es repetible: lo que ya
está no se toca, ni siquiera si la cifra difiere, porque eso sería editar una
tasa. La que cambia se agrega con su vigencia desde el panel de soporte
(`PUT /support/payroll/rates`) o con una fila nueva en ese archivo.

La API hace lo mismo al arrancar, así que en una instalación normal este guion
no hace falta: sirve para ver qué entró y para correrlo a mano después de
editar el archivo de datos.

Habla con la base directamente, como `bootstrap.py`: las tasas no son de
ninguna compañía y no hay sesión que las pueda sembrar por HTTP.
"""

from app.database.database import SessionLocal
from app.services import crud_payroll_rates


def main() -> None:
    db = SessionLocal()
    try:
        nuevas = crud_payroll_rates.sembrar(db)
        db.commit()
    finally:
        db.close()
    total = sum(nuevas.values())
    if total == 0:
        print("Nada nuevo: todas las tasas del archivo ya estaban.")
        return
    print(
        f"Sembradas {nuevas['rates']} tasas, {nuevas['brackets']} tramos de renta, "
        f"{nuevas['credits']} créditos y {nuevas['severance']} filas de cesantía."
    )


if __name__ == "__main__":
    main()
