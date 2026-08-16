# Reemplaza tu Dockerfile.
#
# Cambios respecto del original:
#   1. Ya no hace falta `apt install netcat`: la espera de la base se resuelve
#      con el healthcheck del compose y un chequeo en Python, así la imagen no
#      arrastra un gestor de paquetes ni sus listas.
#   2. Se quita `--reload`. Sin bind mount del código no detecta nada —el código
#      entra con COPY— y deja un vigilante de archivos consumiendo CPU.
#   3. La app corre como usuario sin privilegios, no como root.

FROM python:3.11-slim

# PYTHONDONTWRITEBYTECODE: sin .pyc, que en un contenedor solo ocupan espacio.
# PYTHONUNBUFFERED: los logs salen al instante, no cuando se llena el buffer;
# sin esto `docker compose logs` va siempre por detrás de lo que pasa.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Las dependencias van antes que el código: mientras requirements.txt no cambie,
# Docker reutiliza esta capa y el build no reinstala nada.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ./app ./app
COPY wait-for-db.sh /wait-for-db.sh
RUN chmod +x /wait-for-db.sh

# Sin privilegios: si alguien logra ejecutar código a través de la API, no lo
# hace como root dentro del contenedor.
RUN useradd --create-home --shell /bin/bash appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 80

CMD ["/wait-for-db.sh"]
