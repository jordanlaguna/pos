import os
import warnings
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
from jose import JWTError, jwt

# CORRECCIÓN: antes era `load_dotenv()` sin ruta, que busca el .env en el
# directorio DESDE EL QUE SE LANZA uvicorn. Como el .env vive en `app/.env`
# (así lo carga database.py), al arrancar con `uvicorn app.main:app` desde la
# raíz del repo no se encontraba y SECRET_KEY caía en el valor por defecto.
# Mientras ningún endpoint verificaba el token eso no se notaba; ahora que sí
# lo verifican, la clave es lo único que separa a un extraño de una sesión de
# administrador. Se usa la misma ruta explícita que database.py.
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

DEFAULT_SECRET = "clave_por_defecto_insegura"
SECRET_KEY = os.getenv("SECRET_KEY", DEFAULT_SECRET)
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "480"))

if SECRET_KEY == DEFAULT_SECRET:
    warnings.warn(
        "SECRET_KEY no está definida en app/.env: se está usando la clave por "
        "defecto, que es pública. Cualquiera puede firmar un token válido y "
        "entrar como administrador. Generá una con:\n"
        '  python -c "import secrets; print(secrets.token_urlsafe(48))"',
        RuntimeWarning,
        stacklevel=2,
    )


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    # datetime.utcnow() está obsoleto desde Python 3.12 y devuelve un datetime
    # sin zona horaria, que es fácil de comparar mal. Se usa UTC explícito.
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def verify_access_token(token: str):
    """Devuelve el payload, o None si la firma no valida o el token venció."""
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None
