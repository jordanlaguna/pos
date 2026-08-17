"""
Aplicación: los casos de uso.

Orquesta el dominio y habla con el mundo exterior **solo a través de puertos**
(`ports/`). No importa SQLAlchemy ni FastAPI: no sabe si los datos vienen de
MySQL o de un diccionario, ni si la petición llegó por HTTP o por una prueba.
"""
