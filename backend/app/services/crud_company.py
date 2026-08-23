"""Dar de alta una compañía (T-304, RF-6).

Una compañía nueva no es una fila: son seis. La compañía, su sucursal, su
terminal, su fila de configuración, la identidad de su primer administrador y la
membresía que los une. Si falta una, el resultado es una compañía a la que no se
puede entrar o en la que no se puede vender.

**Este módulo es el único que sabe cuáles son las seis**, y por eso existe.
Antes la lista vivía en `bootstrap.py`; cuando el panel de soporte tuvo que
hacer lo mismo por HTTP, copiar el guion habría dejado dos altas que se parecen
—y que el día que se agregue una séptima fila dejarán de parecerse—. Ahora
`bootstrap.py` y `POST /support/companies` llaman a lo mismo.

Se ejecuta **sin compañía en el contexto**: es justo el código que decide cuál
es la compañía, así que cada fila lleva su `company_id` escrito y cada lectura
va con `sin_filtro`. El sellado automático de `tenancy.py` no aplica acá porque
no hay nada que sellar todavía.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.domain.limits import SIN_LIMITE, hay_lugar
from app.models.model_company import Branch, Company, Plan, Terminal, UserCompany
from app.models.model_person import Person
from app.models.model_settings import Settings
from app.models.model_user import User
from app.utils.security import hash_password
from app.utils.tenancy import sin_filtro

#: La sucursal y la caja con las que nace una compañía. Los formatos son los que
#: pide Hacienda en el consecutivo del comprobante: 3 dígitos y 5 dígitos.
SUCURSAL_INICIAL = ("001", "Casa matriz")
TERMINAL_INICIAL = ("00001", "Caja 1")

#: Tope de la configuración que se puede sembrar al dar de alta. Es el mismo de
#: `crud_settings.MAX_DATA_BYTES`, escrito acá para no importar un servicio
#: desde otro por una constante: son unas decenas de campos y cualquier cosa
#: más grande significa que algo se está usando mal.
MAX_SETTINGS_BYTES = 20_000


def _ahora() -> datetime:
    return datetime.now().replace(microsecond=0)


@dataclass
class DatosDeAlta:
    """Lo que hace falta para dar de alta una compañía.

    Va en un objeto y no en quince argumentos porque son quince y porque la
    mitad tiene valor por omisión razonable. Los campos de la persona repiten
    los nombres que ya usa `persons` —incluidos los `camelCase` heredados del
    WinForms— para que el JSON del API viaje sin traducción.
    """

    afiliado: int
    compania: int
    nombre: str
    email: str
    password: str
    identificacion: str | None = None
    plan_id: int | None = None
    estado: str = "prueba"
    vence_el: date | None = None
    locale: str = "es"
    document_locale: str = "es"
    rol: str = "admin"

    #: La configuración inicial, tal como la manda el POS. Trae los textos del
    #: documento en el idioma de la compañía, y tiene que venir de allá: el
    #: backend no escribe texto para personas (RN-30) y el catálogo lo tiene el
    #: POS. Vacía es válido —el POS aplica sus valores por omisión—.
    settings: dict = field(default_factory=dict)

    nombre_persona: str = "Administrador"
    apellido: str = "Inicial"
    segundo_apellido: str = ""
    cedula: str | None = None
    telefono: str = ""
    nacimiento: str = "1990-01-01"

    #: Aceptar la membresía sin preguntar, aunque la identidad ya existiera.
    #:
    #: Lo pide `bootstrap.py` y no lo pide el panel, y la diferencia es quién
    #: está del otro lado (plan §3.8). Quien corre `bootstrap.py` es el operador
    #: del sistema, con acceso a la base, dando de alta a alguien con una
    #: contraseña que él mismo eligió: no hay a quién pedirle permiso, y una
    #: invitación que nadie puede aceptar dejaría la instalación sin poder
    #: entrar. Desde el panel, en cambio, el correo puede ser de una persona que
    #: ya trabaja en otra compañía, y ahí sí hay a quién preguntarle (T-229).
    aceptar_membresia: bool = False


@dataclass(frozen=True)
class Alta:
    """Qué quedó creado. Se arma **antes** del commit.

    Después de confirmar, SQLAlchemy expira los objetos y leer `branch.codigo`
    dispara una relectura de una tabla de negocio; sin compañía en el contexto,
    esa relectura falla. Es exactamente lo que tiene que pasar, y la respuesta
    correcta no es aflojar el filtro sino no leer después de confirmar.
    """

    company_id: int
    afiliado: int
    compania: int
    nombre: str
    plan_id: int
    plan_nombre: str
    estado: str
    branch_id: int
    branch_codigo: str
    terminal_id: int
    terminal_codigo: str
    user_id: int
    email: str
    #: Si la identidad se creó ahora o ya existía en el sistema.
    usuario_nuevo: bool
    #: Una membresía sobre una identidad que ya existía nace **pendiente**
    #: (T-229): nadie le puede dar acceso a nombre de otro. La del usuario que
    #: se acaba de crear nace aceptada, porque quien eligió su contraseña es
    #: quien está dando de alta la compañía y no hay a quién preguntarle.
    membresia_pendiente: bool
    company_nueva: bool


# --------------------------------------------------------------------------
# Las piezas. Cada una es idempotente: si ya está, la devuelve.
# --------------------------------------------------------------------------


def plan_por_id(db: Session, plan_id: int) -> Plan | None:
    return sin_filtro(db.query(Plan).filter(Plan.id == plan_id)).first()


def plan_por_nombre(
    db: Session,
    nombre: str,
    *,
    crear: bool = False,
    limites: tuple[int, int, int] = (1, 3, 10),
) -> Plan | None:
    """El plan que se llama así. Lo crea si se pide y no existe.

    `crear` existe para `bootstrap.py`, que corre sobre una base recién hecha
    donde puede no haber ningún plan. El panel de soporte nunca lo pide: elegir
    un plan que no está en el catálogo es un error, no una invitación a
    inventarlo con precio cero.

    `limites` son las sucursales, las terminales y los usuarios que ese plan
    permite, y solo se usan **al crearlo**: un plan que ya existe no se toca,
    porque cambiarle los límites le cambia lo que puede hacer a todos los
    clientes que lo tienen. El precio nace en 0 a propósito: cuánto se cobra es
    una decisión comercial y un guion de arranque no la puede tomar.
    """
    plan = sin_filtro(db.query(Plan).filter(Plan.nombre == nombre)).first()
    if plan or not crear:
        return plan

    sucursales, terminales, usuarios = limites
    plan = Plan(
        nombre=nombre,
        precio_mensual=0,
        max_sucursales=sucursales,
        max_terminales=terminales,
        max_usuarios=usuarios,
        factura_electronica=False,
    )
    db.add(plan)
    db.flush()
    return plan


def planes(db: Session) -> list[Plan]:
    """El catálogo de planes, para que el panel pueda ofrecerlo."""
    return sin_filtro(db.query(Plan).order_by(Plan.precio_mensual, Plan.id)).all()


def por_par(db: Session, afiliado: int, compania: int) -> Company | None:
    """La compañía por su par (afiliado, compañía), que es su identidad real."""
    return sin_filtro(
        db.query(Company).filter(Company.afiliado == afiliado, Company.compania == compania)
    ).first()


def por_id(db: Session, company_id: int) -> Company | None:
    return sin_filtro(db.query(Company).filter(Company.id == company_id)).first()


def siguiente_par(db: Session, afiliado: int) -> int:
    """El próximo número de compañía libre para ese afiliado.

    Un afiliado agrupa las compañías de un mismo cliente comercial, y el caso
    normal es que tenga una sola. Cuando abre la segunda —el mismo dueño con
    otra cédula— hay que darle el número siguiente, y calcularlo acá evita que
    el formulario tenga que adivinarlo.
    """
    usados = [c.compania for c in sin_filtro(
        db.query(Company).filter(Company.afiliado == afiliado)
    ).all()]
    return max(usados) + 1 if usados else 1


def siguiente_afiliado(db: Session) -> int:
    """El próximo afiliado libre. Un cliente nuevo es un afiliado nuevo."""
    ultimo = sin_filtro(db.query(Company).order_by(Company.afiliado.desc())).first()
    return (ultimo.afiliado + 1) if ultimo else 1


def membresias_de(db: Session, user_id: int) -> int:
    """Cuántas membresías activas tiene una identidad.

    Lo pregunta `bootstrap.py --soporte` para avisar cuando está marcando como
    soporte a alguien que además pertenece a compañías: no rompe nada, pero esas
    membresías quedan sin uso porque el login manda a soporte al panel.
    """
    return (
        sin_filtro(
            db.query(func.count(UserCompany.id)).filter(
                UserCompany.user_id == user_id, UserCompany.activa.is_(True)
            )
        ).scalar()
        or 0
    )


def cabe_otro_usuario(db: Session, company_id: int) -> tuple[bool, int, int]:
    """¿Cabe otra persona en el plan de esta compañía? (RF-12, T-309).

    Devuelve `(cabe, actuales, máximo)`: la pantalla necesita los tres para
    poder decir «ya tiene 10 y el plan permite 10» en vez de un «no» pelado.

    Se cuenta con `func.count(...)` y no con el `count` de `Query`. No es
    estilo: el segundo envuelve la consulta en una subconsulta donde el criterio
    de compañía no entra, y devolvería los usuarios de **todas** —la trampa que
    vigila `tests/test_tenancy.py`, que por eso no tolera esas cuatro letras ni
    en una explicación—. Acá el filtro va escrito a mano igual, porque
    `user_companies` no es tabla de negocio, pero la forma se mantiene para que
    no haya dos maneras de contar.

    Sin plan no hay límite que aplicar y se deja pasar: es un dato roto en la
    base, y negarle un usuario a un cliente por eso sería castigarlo por un
    error nuestro. El panel lo muestra como compañía sin plan.
    """
    company = por_id(db, company_id)
    plan = plan_por_id(db, company.plan_id) if company else None
    if plan is None:
        return True, 0, SIN_LIMITE

    actuales = (
        sin_filtro(
            db.query(func.count(UserCompany.id)).filter(
                UserCompany.company_id == company_id, UserCompany.activa.is_(True)
            )
        ).scalar()
        or 0
    )
    return hay_lugar(actuales, plan.max_usuarios), actuales, plan.max_usuarios


def _compania(db: Session, datos: DatosDeAlta, plan: Plan) -> tuple[Company, bool]:
    existente = por_par(db, datos.afiliado, datos.compania)
    if existente:
        return existente, False

    company = Company(
        afiliado=datos.afiliado,
        compania=datos.compania,
        nombre=datos.nombre,
        identificacion=datos.identificacion,
        plan_id=plan.id,
        estado=datos.estado,
        vence_el=datos.vence_el,
        creada_el=_ahora(),
        locale=datos.locale,
        document_locale=datos.document_locale,
    )
    db.add(company)
    db.flush()
    return company, True


def _sucursal_y_terminal(db: Session, company: Company) -> tuple[Branch, Terminal]:
    codigo_sucursal, nombre_sucursal = SUCURSAL_INICIAL
    sucursal = sin_filtro(
        db.query(Branch).filter(
            Branch.company_id == company.id, Branch.codigo == codigo_sucursal
        )
    ).first()
    if not sucursal:
        sucursal = Branch(
            company_id=company.id,
            codigo=codigo_sucursal,
            nombre=nombre_sucursal,
            activa=True,
        )
        db.add(sucursal)
        db.flush()

    codigo_terminal, nombre_terminal = TERMINAL_INICIAL
    terminal = sin_filtro(
        db.query(Terminal).filter(
            Terminal.company_id == company.id,
            Terminal.branch_id == sucursal.id,
            Terminal.codigo == codigo_terminal,
        )
    ).first()
    if not terminal:
        terminal = Terminal(
            company_id=company.id,
            branch_id=sucursal.id,
            codigo=codigo_terminal,
            nombre=nombre_terminal,
            activa=True,
        )
        db.add(terminal)
        db.flush()

    return sucursal, terminal


def _configuracion(db: Session, company: Company, valores: dict) -> None:
    """La fila de configuración, con lo que haya mandado el POS.

    Vacía también sirve: el POS aplica sus valores por omisión sobre un objeto
    vacío. Lo que **no** puede hacer el POS es adivinar los textos del
    documento, porque nacen vacíos a propósito (T-816) y quien sabe en qué
    idioma escribirlos es quien conoce el catálogo. De ahí que vengan de allá.
    """
    existente = sin_filtro(
        db.query(Settings).filter(Settings.company_id == company.id)
    ).first()
    if existente:
        return

    serializada = json.dumps(valores or {}, ensure_ascii=False)
    if len(serializada.encode("utf-8")) > MAX_SETTINGS_BYTES:
        # No debería llegar: el POS manda unas decenas de campos. Se recorta a
        # vacío en vez de fallar el alta entera, porque una compañía sin textos
        # de tiquete se arregla en Configuración y una compañía que no se creó
        # hay que crearla de nuevo.
        serializada = "{}"

    db.add(Settings(company_id=company.id, data=serializada))


def _persona_y_usuario(db: Session, datos: DatosDeAlta) -> tuple[User, bool]:
    user = sin_filtro(db.query(User).filter(User.email == datos.email)).first()
    if user:
        return user, False

    persona = Person(
        birth_date=datos.nacimiento,
        # La cédula es única y el correo lo es también, así que sirve de relleno
        # cuando no se pide: es el mismo criterio de `bootstrap.py`.
        identification=datos.cedula or datos.email,
        name=datos.nombre_persona,
        lastName=datos.apellido,
        secondName=datos.segundo_apellido,
        telephone=datos.telefono,
    )
    db.add(persona)
    db.flush()

    user = User(
        email=datos.email,
        password=hash_password(datos.password),
        id_person=persona.id_person,
    )
    db.add(user)
    db.flush()
    return user, True


def _membresia(
    db: Session, user: User, company: Company, rol: str, *, aceptada: bool
) -> bool:
    """Une la identidad con la compañía. Devuelve si la membresía queda pendiente."""
    ahora = _ahora()
    existente = sin_filtro(
        db.query(UserCompany).filter(
            UserCompany.user_id == user.id_user, UserCompany.company_id == company.id
        )
    ).first()

    if existente:
        existente.rol = rol
        existente.activa = True
        if aceptada and existente.aceptada_el is None:
            existente.aceptada_el = ahora
        return existente.aceptada_el is None

    db.add(
        UserCompany(
            user_id=user.id_user,
            company_id=company.id,
            rol=rol,
            activa=True,
            creada_el=ahora,
            aceptada_el=ahora if aceptada else None,
        )
    )
    return not aceptada


def dar_de_alta(db: Session, datos: DatosDeAlta, plan: Plan) -> Alta:
    """Las seis filas, en una sola transacción. **No hace commit.**

    Lo hace quien llama, y así el alta entra completa o no entra: una compañía
    sin terminal es una compañía en la que no se puede vender, y descubrirlo
    después es peor que no haberla creado.

    Es repetible. Si la compañía ya existe la reutiliza y si la persona ya
    existe le agrega la membresía en vez de crear otra cuenta —que es el caso
    del contador que atiende varios locales (RN-3)—. Quien necesita que un alta
    duplicada sea un error lo comprueba antes de llamar; acá no se puede
    decidir, porque `bootstrap.py` se apoya justamente en que sea repetible.
    """
    company, company_nueva = _compania(db, datos, plan)
    sucursal, terminal = _sucursal_y_terminal(db, company)
    _configuracion(db, company, datos.settings)
    user, usuario_nuevo = _persona_y_usuario(db, datos)
    pendiente = _membresia(
        db,
        user,
        company,
        datos.rol,
        aceptada=usuario_nuevo or datos.aceptar_membresia,
    )

    return Alta(
        company_id=company.id,
        afiliado=company.afiliado,
        compania=company.compania,
        nombre=company.nombre,
        plan_id=plan.id,
        plan_nombre=plan.nombre,
        estado=company.estado,
        branch_id=sucursal.id,
        branch_codigo=sucursal.codigo,
        terminal_id=terminal.id,
        terminal_codigo=terminal.codigo,
        user_id=user.id_user,
        email=user.email,
        usuario_nuevo=usuario_nuevo,
        membresia_pendiente=pendiente,
        company_nueva=company_nueva,
    )
