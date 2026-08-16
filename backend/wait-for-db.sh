#!/bin/sh
# Reemplaza tu wait-for-db.sh.
#
# El original hacía `nc -z db 3306`, que solo comprueba que el puerto acepte
# conexiones. MySQL abre el 3306 varios segundos ANTES de poder autenticar, así
# que FastAPI arrancaba a veces contra una base que todavía rechazaba el login y
# moría en el primer create_all(). Acá se intenta una conexión real con las
# mismas credenciales que usará la aplicación.
#
# Con el healthcheck del docker-compose esto ya casi nunca espera; queda como
# red de seguridad para cuando se levanta el contenedor suelto.

set -e

echo "Esperando a que la base de datos acepte conexiones..."

python - <<'PY'
import os
import sys
import time

import pymysql

host = os.getenv("DB_HOST", "db")
port = int(os.getenv("DB_PORT", "3306"))
user = os.getenv("DB_USER", "posuser")
password = os.getenv("DB_PASS", "")
database = os.getenv("DB_NAME", "posdb")

DEADLINE = time.time() + 120
last_error = None

while time.time() < DEADLINE:
    try:
        pymysql.connect(
            host=host, port=port, user=user, password=password,
            database=database, connect_timeout=3,
        ).close()
        print(f"Base de datos lista en {host}:{port}.")
        sys.exit(0)
    except Exception as exc:      # noqa: BLE001
        last_error = exc
        time.sleep(2)

print(f"La base no respondió en 120 s. Último error: {last_error}", file=sys.stderr)
sys.exit(1)
PY

echo "Iniciando FastAPI..."

# Sin --reload: el código entra por COPY, no hay nada que vigilar.
exec uvicorn app.main:app --host 0.0.0.0 --port 80
