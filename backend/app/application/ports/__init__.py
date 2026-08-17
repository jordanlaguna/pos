"""
Puertos: lo que la aplicación necesita del exterior, dicho por ella.

Son `Protocol` y no clases base a propósito. Con `Protocol`, quien implementa no
tiene que importar nada de acá: un repositorio de SQLAlchemy cumple el contrato
por tener los métodos, no por heredar. La dependencia sigue apuntando hacia
adentro, que es la regla entera de esta arquitectura.
"""
