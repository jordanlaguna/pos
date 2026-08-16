"""Hasheo y verificación de contraseñas.

CORRECCIÓN: antes esto usaba passlib (`CryptContext(schemes=["bcrypt"])`).
passlib 1.7.4 es de 2020 y no conoce las versiones nuevas de la librería
`bcrypt`: al arrancar intenta leer `bcrypt.__about__.__version__`, que ya no
existe, y su rutina de detección le pasa a bcrypt un secreto de más de 72 bytes.
bcrypt ≥ 4.1 dejó de truncar en silencio y lanza ValueError, así que
`hash_password()` reventaba y con ella el registro y el login.

Como `requirements.txt` no fijaba versiones, bastaba con instalar en una máquina
nueva para que el sistema dejara de dejar entrar a nadie.

Se usa `bcrypt` directamente. El formato del hash es el mismo (`$2b$...`), así
que **las contraseñas ya guardadas siguen funcionando**: passlib solo era una
envoltura sobre esta misma librería.
"""

import bcrypt

# bcrypt solo considera los primeros 72 bytes de la contraseña; a partir de la
# versión 4.1 se niega a recibir más en vez de recortar por su cuenta. El
# recorte se hace aquí, sobre los BYTES en UTF-8 y no sobre los caracteres,
# porque una tilde ocupa dos bytes y cortar por caracteres se pasaría del límite.
MAX_BCRYPT_BYTES = 72

# Coste de trabajo. 12 son ~0,3 s por hash en hardware normal: suficiente para
# que probar contraseñas a lo bruto sea caro y poco para que el cajero lo note.
ROUNDS = 12


def _encode(password: str) -> bytes:
    return password.encode("utf-8")[:MAX_BCRYPT_BYTES]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_encode(password), bcrypt.gensalt(rounds=ROUNDS)).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    if not plain_password or not hashed_password:
        return False
    try:
        return bcrypt.checkpw(_encode(plain_password), hashed_password.encode("utf-8"))
    except (ValueError, TypeError):
        # Hash con formato inválido en la base: se trata como contraseña errónea
        # en vez de dejar que la excepción tumbe el login.
        return False
