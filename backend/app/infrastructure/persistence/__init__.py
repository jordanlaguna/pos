"""
Persistencia: los repositorios de SQLAlchemy.

Implementan los puertos de `application/ports/repositories.py` sin heredar de
ellos —son `Protocol`—, así que la dependencia sigue apuntando hacia adentro:
esta carpeta conoce la aplicación, la aplicación no conoce esta carpeta.
"""
