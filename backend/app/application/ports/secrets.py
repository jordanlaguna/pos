"""
Cifrado en reposo de lo que hay que poder volver a leer (T-602a, plan §7.1).

Le queda **un solo cliente**: la contraseña de ATV. Todo lo demás que era
secreto en esta fase se fue a Vault, y ahí no se guarda nada que se pueda leer
de vuelta — se le manda un digest y devuelve una firma.

La contraseña no puede hacer eso: el IdP de Hacienda pide `grant_type=password`,
así que hay que **reenviarla entera** cada vez que se saca un token. No es un
digest que se firme sino un valor que se guarda y se lee, y para eso hace falta
cifrado simétrico.

**La compañía y el ambiente van explícitos**, y no son adorno: entran como dato
asociado del AES-GCM, así que una fila copiada a otra compañía —o al otro
ambiente de la misma— **no descifra**. Es la misma frase que rige el nombre de
la llave de Vault y la ruta del almacén de documentos: la identidad la fija el
servidor.
"""

from __future__ import annotations

from typing import Protocol


class SecretUnreadable(Exception):
    """No se pudo descifrar, y hay exactamente tres formas de llegar acá.

    Las tres significan cosas distintas para quien opera y ninguna es un error
    del usuario:

    1. **La llave cambió.** `FE_CRYPTO_KEY` se rotó o se perdió, y lo guardado
       con la anterior no vuelve. Hay que escribir la contraseña otra vez.
    2. **La fila es de otra compañía o de otro ambiente.** Alguien copió filas
       entre instalaciones o entre clientes: el dato asociado no coincide y el
       AES-GCM se niega. Es la protección funcionando, no una falla.
    3. **El valor está dañado.** Un `UPDATE` a mano, una restauración a medias.

    No se distinguen a propósito: para quien llama las tres significan «esto no
    sirve, hay que volver a cargarlo», y decir cuál de las tres es contarle a
    quien esté mirando cómo está construido el cifrado.
    """


class SecretBox(Protocol):
    """Guarda un secreto de forma que solo esta compañía y este ambiente lo abran."""

    def encrypt(self, plaintext: str, *, company_id: int, environment: str) -> str:
        """Devuelve el valor cifrado, listo para guardar en una columna de texto."""
        ...

    def decrypt(self, sealed: str, *, company_id: int, environment: str) -> str:
        """El valor original, o `SecretUnreadable`."""
        ...
