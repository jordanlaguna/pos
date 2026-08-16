---
name: pos-deploy
description: Despliegue y diagnóstico de infraestructura de VentaSys — Docker, variables de entorno, red, base de datos, respaldos. Úsalo cuando algo no levanta, no conecta o hay que ponerlo en la VM. Ejemplos: "el POS no ve el backend", "no puedo entrar desde otra máquina", "cómo respaldo la base", "actualizá la VM con los cambios".
---

Te encargás de que VentaSys corra en la máquina virtual. La mayoría de los
problemas de despliegue de este proyecto ya se diagnosticaron una vez; empezá
por ahí antes de investigar de cero.

## Cómo está armado

```
backend/                    ← se copia a la VM tal cual; se levanta sola
├── app/                    ← FastAPI
├── docker-compose.yml      ← db (MySQL 8) + adminer + fastapi
├── .env                    ← credenciales, SECRET_KEY, TZ  (NO se versiona)
├── initdb/                 ← .sql que se cargan al crear la base
├── migration.sql           ← para una base que YA tiene datos
└── seed.py                 ← carga inicial vía API

frontend/                   ← el POS, corre fuera de Docker
└── .env                    ← API_BASE_URL, ORIGIN, POS_MOCK
```

El compose fija `name: ventasys` y el volumen `ventasys_db_data`. Sin eso el
nombre de la carpeta sería el prefijo del volumen y mover el directorio dejaría
a MySQL arrancando contra una base vacía.

## Las cinco trampas conocidas

Cuando algo no funciona, descartá estas primero. Todas costaron una tarde:

**1. El puerto es 8001, no 8000.** El compose publica `"8001:80"`: FastAPI
escucha en el 80 dentro del contenedor. `API_BASE_URL=http://IP_VM:8001`.

**2. `node build/index.js` no lee el `.env`.** Vite lo carga en desarrollo; el
build de producción es Node a secas. Sin `--env-file=.env`, `API_BASE_URL` cae
al valor por defecto y el POS busca el backend en `localhost:8000` aunque el
archivo diga otra cosa. Síntoma: «No se pudo conectar con el backend en
http://localhost:8000» con el `.env` bien puesto.

**3. `ORIGIN` es obligatoria en producción.** adapter-node la usa para validar
el origen de los formularios. Sin ella, todo POST responde
`403 Cross-site POST form submissions are forbidden` y no se puede ni iniciar
sesión. Tiene que ser exactamente la URL por la que entran los cajeros.

**4. Los contenedores corren en UTC si no se les dice `TZ`.** El backend sella
ventas, turnos y devoluciones con `datetime.now()`. Con UTC−6, toda venta
después de las 18:00 se registra como del día siguiente y el arqueo del turno de
noche se parte en dos. Comprobalo:

```bash
date; docker compose exec -T fastapi date; docker compose exec -T db date
```

Los tres tienen que coincidir.

**5. `SECRET_KEY` tiene que llegar al contenedor.** Sin ella el backend firma
los JWT con `"clave_por_defecto_insegura"`, que está publicada en el
repositorio: cualquiera puede firmarse un token de administrador. Si aparece el
aviso en `docker compose logs fastapi`, no se está leyendo el `.env`.

## Diagnóstico en orden

```bash
docker compose ps                       # ¿los tres arriba? ¿db healthy?
docker compose logs fastapi --tail 40   # ¿arrancó? ¿avisos?
curl http://localhost:8001/health       # ¿responde la API?
curl http://IP_DE_LA_VM:8001/health     # ¿responde desde afuera?
```

Si responde en localhost pero no desde afuera, es el cortafuegos:

```bash
sudo ufw allow 8001/tcp
```

## ¿Hay que correr `migration.sql`?

| Situación | Qué hacer |
|---|---|
| Base nueva (primer arranque o tras `down -v`) | **Nada.** `create_all()` deja las 11 tablas correctas. |
| Base con datos del esquema viejo | Correrla: `docker compose exec -T db mysql -u USER -pPASS posdb < migration.sql` |

`create_all()` crea tablas nuevas pero **nunca altera las existentes**: sobre una
base vieja, `role` y los `DATETIME` no aparecen solos.

Los `.sql` de `initdb/` se ejecutan **solo** la primera vez que se crea el
volumen. Sobre una base ya inicializada, MySQL los ignora.

## Operación

```bash
docker compose up -d --build    # aplicar cambios de código
docker compose restart fastapi  # reiniciar solo la API
docker compose down             # parar, conservando datos
docker compose down -v          # parar y BORRAR la base

# Respaldo y restauración
docker compose exec -T db mysqldump -u root -pROOT_PASS posdb > respaldo.sql
docker compose exec -T db mysql -u root -pROOT_PASS posdb < respaldo.sql
```

## Antes de dar por bueno un despliegue

No basta con que los contenedores estén «Up». Comprobá:

1. `/health` responde desde la máquina donde corre el POS, no solo desde la VM.
2. Los tres relojes coinciden.
3. No hay aviso de `SECRET_KEY` en los logs.
4. Se puede iniciar sesión **desde el navegador** (eso valida `ORIGIN`).
5. Una venta de prueba queda registrada y aparece en el arqueo de caja.

## Al terminar

Nunca dejes credenciales reales en un archivo versionado. `.env` está en
`.gitignore` y tiene que seguir así. Si generás contraseñas o `SECRET_KEY`,
usá `python -c "import secrets; print(secrets.token_urlsafe(48))"` y decile al
usuario dónde quedaron, sin volcarlas en el chat salvo que las pida.
