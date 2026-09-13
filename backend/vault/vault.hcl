# Vault de la pila de trabajo (T-622, plan §7.1).
#
# Guarda una sola cosa: la llave privada de firma de cada compañía, importada al
# motor `transit`. La aplicación le manda un digest y recibe la firma; la llave
# no vuelve a salir de acá.
#
# Se monta de solo lectura en /vault/config. La carpeta tiene que existir aunque
# quede vacía: un bind mount de un archivo que no está hace que Docker cree un
# DIRECTORIO con ese nombre, que es la misma trampa que ya documenta `initdb`.

ui = true

# Disco y no memoria: lo que hay acá tiene que sobrevivir a un reinicio. El
# precio es que Vault arranca SELLADO cada vez, y sellado no firma. Ver el
# README (§«Abrir Vault al arrancar»).
storage "file" {
  path = "/vault/file"
}

# Sin TLS a propósito, y solo es defendible por dónde escucha: el puerto está
# publicado en 127.0.0.1 y el único que le habla es `fastapi`, por la red
# interna de Compose. En un despliegue donde Vault quede alcanzable desde otra
# máquina, esto se cambia — no se discute.
listener "tcp" {
  address     = "0.0.0.0:8200"
  tls_disable = 1
}

api_addr     = "http://vault:8200"
cluster_addr = "http://vault:8201"
