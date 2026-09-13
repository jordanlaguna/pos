#!/usr/bin/env python3
"""Da de alta una compañía y su primer administrador, o una cuenta de soporte.

Es el único guion que habla con la base directamente, y tiene que ser así: ni
una compañía nueva ni la primera cuenta de soporte se pueden crear por la API,
porque no hay sesión sin membresía, no hay membresía sin compañía, y no hay
panel de soporte sin alguien marcado como soporte. Es el huevo y la gallina, y
esto es el arranque manual.

    python bootstrap.py --nombre "Abastecedor La Esquina" \
        --email admin@ventasys.cr --password admin123

    python bootstrap.py --afiliado 2 --compania 1 --nombre "Repuestos Yamaha" \
        --email dueno@yamaha.cr --password otra123

    python bootstrap.py --soporte --email soporte@ventasys.cr --password soporte123

Desde F3 el alta de compañías **también** se hace desde el panel de soporte
(RF-6), y las dos usan el mismo código: `app/services/crud_company.py`. Este
guion queda para instalaciones nuevas y para el día que el panel no esté
disponible, que es justo el día en que uno quiere una herramienta que no
dependa de nada.

Es repetible: si la compañía ya existe la reutiliza, y si la persona ya existe
le agrega la membresía en vez de crear otra cuenta —que es exactamente el caso
del contador que atiende varios locales (RN-3)—.
"""

import argparse
import sys
from datetime import datetime

from app.database.database import SessionLocal
from app.domain.modules import MODULES
from app.models.model_person import Person
from app.models.model_user import User
from app.services import crud_company
from app.utils.security import hash_password
from app.utils.tenancy import compania, sin_filtro


def _ahora() -> datetime:
    return datetime.now().replace(microsecond=0)


def _cuenta_de_soporte(db, args) -> list[str]:
    """Crea —o marca— la cuenta que administra la plataforma (T-301, RN-4).

    No lleva compañía ni membresía: soporte no pertenece a ninguna, y por eso su
    token no lleva `cid` y el filtro de `tenancy.py` le hace fallar cerrado
    cualquier consulta a una tabla de negocio. Para ver los datos de un cliente
    tiene que *entrar como* esa compañía, y eso queda en la bitácora.

    Si el correo ya existe, lo marca como soporte en vez de fallar. Es lo que
    hace falta para promover una cuenta que ya estaba, y es idempotente: correrlo
    dos veces no hace nada la segunda.
    """
    user = sin_filtro(db.query(User).filter(User.email == args.email)).first()
    if user is None:
        persona = Person(
            birth_date=args.nacimiento,
            identification=args.cedula or args.email,
            name=args.nombre_persona,
            lastName=args.apellido,
            secondName=args.segundo_apellido,
            telephone=args.telefono,
        )
        db.add(persona)
        db.flush()

        user = User(
            email=args.email,
            password=hash_password(args.password),
            id_person=persona.id_person,
            is_support=True,
        )
        db.add(user)
        db.flush()
        creado = True
    else:
        creado = False
        user.is_support = True

    membresias = crud_company.membresias_de(db, user.id_user)
    aviso = []
    if membresias:
        # Tener las dos cosas no rompe nada pero deja membresías inservibles: el
        # login manda a soporte al panel y nunca le ofrece elegir compañía. Se
        # avisa en vez de borrarlas, porque borrar filas no es tarea de un guion
        # de arranque.
        aviso = [
            f"AVISO      esta cuenta tiene {membresias} membresía(s) de compañía, "
            "que quedan sin uso: soporte no elige compañía."
        ]

    return [
        f"Soporte    {user.email} (id {user.id_user}) "
        f"{'creado' if creado else 'ya existía, marcado como soporte'}",
        *aviso,
    ]


def _modulos(crudo: str) -> tuple[str, ...]:
    """«purchases,payroll» → los módulos del plan (RN-49).

    Vacío es ninguno, que es lo correcto: un plan del que no se dijo nada no
    incluye nada. Un nombre que no existe **detiene el guion** en vez de
    ignorarse: quien escribió `purchase` en singular quiso dar compras, y
    enterarse al mes siguiente —cuando el cliente reclama— es el peor momento.
    """
    nombres = tuple(p.strip() for p in crudo.split(",") if p.strip())
    desconocidos = [n for n in nombres if n not in MODULES]
    if desconocidos:
        raise SystemExit(
            f"Módulos que no existen: {', '.join(desconocidos)}. "
            f"Los que hay son: {', '.join(MODULES)}."
        )
    return nombres


def _compania(db, args) -> list[str]:
    plan = crud_company.plan_por_nombre(
        db,
        args.plan,
        crear=True,
        limites=(args.plan_max_sucursales, args.plan_max_terminales, args.plan_max_usuarios),
        modulos=_modulos(args.plan_modulos),
    )
    ya_estaba = crud_company.por_par(db, args.afiliado, args.compania) is not None

    alta = crud_company.dar_de_alta(
        db,
        crud_company.DatosDeAlta(
            afiliado=args.afiliado,
            compania=args.compania,
            nombre=args.nombre,
            email=args.email,
            password=args.password,
            plan_id=plan.id,
            estado=args.estado,
            locale=args.idioma,
            document_locale=args.idioma_documento,
            rol=args.rol,
            nombre_persona=args.nombre_persona,
            apellido=args.apellido,
            segundo_apellido=args.segundo_apellido,
            cedula=args.cedula,
            telefono=args.telefono,
            nacimiento=args.nacimiento,
            # Ver `DatosDeAlta.aceptar_membresia`: acá no hay a quién pedirle
            # permiso, y una invitación que nadie puede aceptar dejaría la
            # instalación sin poder entrar.
            aceptar_membresia=True,
        ),
        plan,
    )

    # El resumen se arma ANTES del commit, y no es un capricho de estilo. Al
    # confirmar, SQLAlchemy expira los objetos; leer `sucursal.codigo` después
    # dispara una relectura de `branches`, que es tabla de negocio, y en este
    # guion el contexto no tiene compañía. O sea: el filtro haría fallar un
    # `print`. Es exactamente lo que tiene que pasar —leer una tabla de negocio
    # sin compañía es un error— y la respuesta correcta no es aflojar el filtro
    # sino no leer después de confirmar. Por eso `dar_de_alta` devuelve un
    # objeto con los datos ya copiados y no las filas.
    return [
        f"Plan       {alta.plan_nombre} (id {alta.plan_id})",
        f"Compañía   afiliado {alta.afiliado} · compañía {alta.compania} — "
        f"{alta.nombre} (id {alta.company_id}) {'ya existía' if ya_estaba else 'creada'}",
        f"Sucursal   {alta.branch_codigo} (id {alta.branch_id})",
        f"Terminal   {alta.terminal_codigo} (id {alta.terminal_id})",
        f"Usuario    {alta.email} (id {alta.user_id}) "
        f"{'creado' if alta.usuario_nuevo else 'ya existía'}",
        f"Membresía  rol {args.rol} en la compañía {alta.company_id} "
        f"{'pendiente de aceptar' if alta.membresia_pendiente else 'otorgada'}",
    ]


def main() -> None:
    ap = argparse.ArgumentParser(description="Da de alta una compañía y su administrador.")
    ap.add_argument(
        "--soporte",
        action="store_true",
        help="crea (o marca) una cuenta de soporte, sin compañía ni membresía",
    )
    ap.add_argument("--afiliado", type=int, default=1)
    ap.add_argument("--compania", type=int, default=1)
    ap.add_argument("--nombre", default="Compañía inicial", help="nombre comercial")
    ap.add_argument("--plan", default="Comercio")
    # Los límites solo se usan si el plan hay que crearlo; uno que ya existe no
    # se toca. −1 es «sin techo» (ver `app/domain/limits.py`).
    ap.add_argument("--plan-max-sucursales", type=int, default=1)
    ap.add_argument("--plan-max-terminales", type=int, default=3)
    ap.add_argument("--plan-max-usuarios", type=int, default=10)
    ap.add_argument(
        "--plan-modulos",
        default="",
        help="módulos del plan, separados por coma: purchases,accounting,payroll",
    )
    ap.add_argument("--estado", default="activa", help="prueba | activa | vencida | …")
    ap.add_argument("--idioma", default="es", help="idioma de la pantalla")
    ap.add_argument("--idioma-documento", default="es", help="idioma de la factura")
    ap.add_argument("--email", required=True, help="correo del administrador")
    ap.add_argument("--password", default="admin123")
    ap.add_argument("--rol", default="admin", choices=("admin", "cajero"))
    ap.add_argument("--nombre-persona", default="Administrador")
    ap.add_argument("--apellido", default="Inicial")
    ap.add_argument("--segundo-apellido", default="")
    ap.add_argument("--cedula", default=None)
    ap.add_argument("--telefono", default="")
    ap.add_argument("--nacimiento", default="1990-01-01")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        # Todo este guion crea filas de una compañía que a veces todavía no
        # existe, así que el contexto va en `None` y cada fila dice su
        # `company_id` explícitamente. El sellado automático no aplica acá
        # justamente porque acá es donde se decide cuál es la compañía.
        with compania(None):
            resumen = _cuenta_de_soporte(db, args) if args.soporte else _compania(db, args)
            db.commit()
            print("\n".join(resumen))
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        print(f"\nNo se pudo completar el alta: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
