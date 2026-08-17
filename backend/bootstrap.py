#!/usr/bin/env python3
"""Da de alta una compañía y su primer administrador.

Es el único guion que habla con la base directamente, y tiene que ser así: una
compañía nueva no se puede crear por la API porque no hay sesión sin membresía y
no hay membresía sin compañía. Es el huevo y la gallina que T-903 tiene que
resolver bien; mientras tanto, esto es el arranque manual.

Cuando exista el panel de soporte (F3, RF-6) esto será un formulario y el guion
quedará solo para instalaciones nuevas.

    python bootstrap.py --nombre "Abastecedor La Esquina" \
        --email admin@ventasys.cr --password admin123

    python bootstrap.py --afiliado 2 --compania 1 --nombre "Repuestos Yamaha" \
        --email dueno@yamaha.cr --password otra123

Es repetible: si la compañía ya existe la reutiliza, y si la persona ya existe
le agrega la membresía en vez de crear otra cuenta —que es exactamente el caso
del contador que atiende varios locales (RN-3)—.
"""

import argparse
import sys
from datetime import datetime

from app.database.database import SessionLocal
from app.models.model_company import Branch, Company, Plan, Terminal, UserCompany
from app.models.model_person import Person
from app.models.model_settings import Settings
from app.models.model_user import User
from app.utils.security import hash_password
from app.utils.tenancy import compania, sin_filtro


def _ahora() -> datetime:
    return datetime.now().replace(microsecond=0)


def _plan(db, nombre: str) -> Plan:
    plan = sin_filtro(db.query(Plan).filter(Plan.nombre == nombre)).first()
    if plan:
        return plan
    plan = Plan(
        nombre=nombre,
        precio_mensual=25000,
        max_sucursales=1,
        max_terminales=3,
        max_usuarios=10,
        factura_electronica=0,
    )
    db.add(plan)
    db.flush()
    return plan


def _compania(db, afiliado: int, compania_num: int, nombre: str, plan: Plan) -> tuple[Company, bool]:
    existente = sin_filtro(
        db.query(Company).filter(Company.afiliado == afiliado, Company.compania == compania_num)
    ).first()
    if existente:
        return existente, False

    company = Company(
        afiliado=afiliado,
        compania=compania_num,
        nombre=nombre,
        plan_id=plan.id,
        estado="activa",
        creada_el=_ahora(),
        locale="es",
        document_locale="es",
    )
    db.add(company)
    db.flush()
    return company, True


def _sucursal_y_terminal(db, company: Company) -> tuple[Branch, Terminal]:
    """Sucursal 001 y terminal 00001. Los formatos son los que pide Hacienda."""
    sucursal = sin_filtro(
        db.query(Branch).filter(Branch.company_id == company.id, Branch.codigo == "001")
    ).first()
    if not sucursal:
        sucursal = Branch(company_id=company.id, codigo="001", nombre="Casa matriz", activa=True)
        db.add(sucursal)
        db.flush()

    terminal = sin_filtro(
        db.query(Terminal).filter(
            Terminal.company_id == company.id,
            Terminal.branch_id == sucursal.id,
            Terminal.codigo == "00001",
        )
    ).first()
    if not terminal:
        terminal = Terminal(
            company_id=company.id,
            branch_id=sucursal.id,
            codigo="00001",
            nombre="Caja 1",
            activa=True,
        )
        db.add(terminal)
        db.flush()

    return sucursal, terminal


def _configuracion(db, company: Company) -> None:
    """La fila de configuración, vacía. El POS aplica sus valores por omisión."""
    existente = sin_filtro(db.query(Settings).filter(Settings.company_id == company.id)).first()
    if not existente:
        db.add(Settings(company_id=company.id, data="{}"))


def _persona_y_usuario(db, args) -> tuple[User, bool]:
    user = sin_filtro(db.query(User).filter(User.email == args.email)).first()
    if user:
        return user, False

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
    )
    db.add(user)
    db.flush()
    return user, True


def _membresia(db, user: User, company: Company, rol: str) -> bool:
    existente = sin_filtro(
        db.query(UserCompany).filter(
            UserCompany.user_id == user.id_user, UserCompany.company_id == company.id
        )
    ).first()
    # Las membresías que crea este guion nacen **aceptadas**, a diferencia de
    # las que concede un administrador desde el POS (T-229). Acá no hay a quién
    # pedirle permiso: quien corre `bootstrap.py` es el operador del sistema,
    # con acceso a la base, dando de alta a alguien con una contraseña que él
    # mismo eligió. Una invitación que nadie puede aceptar dejaría la
    # instalación sin poder entrar.
    if existente:
        if existente.rol != rol or not existente.activa or existente.aceptada_el is None:
            existente.rol = rol
            existente.activa = True
            existente.aceptada_el = existente.aceptada_el or _ahora()
            return True
        return False

    db.add(
        UserCompany(
            user_id=user.id_user,
            company_id=company.id,
            rol=rol,
            activa=True,
            creada_el=_ahora(),
            aceptada_el=_ahora(),
        )
    )
    return True


def main() -> None:
    ap = argparse.ArgumentParser(description="Da de alta una compañía y su administrador.")
    ap.add_argument("--afiliado", type=int, default=1)
    ap.add_argument("--compania", type=int, default=1)
    ap.add_argument("--nombre", default="Compañía inicial", help="nombre comercial")
    ap.add_argument("--plan", default="Comercio")
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
            plan = _plan(db, args.plan)
            company, nueva = _compania(db, args.afiliado, args.compania, args.nombre, plan)
            sucursal, terminal = _sucursal_y_terminal(db, company)
            _configuracion(db, company)
            user, usuario_nuevo = _persona_y_usuario(db, args)
            cambio = _membresia(db, user, company, args.rol)

            # El resumen se arma ANTES del commit, y no es un capricho de
            # estilo. Al confirmar, SQLAlchemy expira los objetos; leer
            # `sucursal.codigo` después dispara una relectura de `branches`, que
            # es tabla de negocio, y en este guion el contexto no tiene
            # compañía. O sea: el filtro haría fallar un `print`. Es
            # exactamente lo que tiene que pasar —leer una tabla de negocio sin
            # compañía es un error— y la respuesta correcta no es aflojar el
            # filtro sino no leer después de confirmar.
            resumen = [
                f"Plan       {plan.nombre} (id {plan.id})",
                f"Compañía   afiliado {company.afiliado} · compañía {company.compania} — "
                f"{company.nombre} (id {company.id}) {'creada' if nueva else 'ya existía'}",
                f"Sucursal   {sucursal.codigo} {sucursal.nombre} (id {sucursal.id})",
                f"Terminal   {terminal.codigo} {terminal.nombre} (id {terminal.id})",
                f"Usuario    {user.email} (id {user.id_user}) "
                f"{'creado' if usuario_nuevo else 'ya existía'}",
                f"Membresía  rol {args.rol} en la compañía {company.id} "
                f"{'otorgada' if cambio else 'ya la tenía'}",
            ]

            db.commit()
            print("\n".join(resumen))
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        print(f"\nNo se pudo dar de alta la compañía: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
