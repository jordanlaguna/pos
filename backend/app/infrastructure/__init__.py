"""
Infraestructura: los adaptadores.

Acá vive lo que sabe de MySQL, de bcrypt, del reloj del sistema y del API de
Hacienda. Implementa los puertos de `application/ports/` y es la única capa a la
que se le permite importar bibliotecas de fuera.
"""
