# Archivo de planilla para el INS (RT-Virtual)

Lo que genera `GET /payroll/exports/ins?year=&month=&policy=` y escribe
`backend/app/domain/payroll_files.py` (`ins_file`, T-1219, RF-85, RN-96).

## De dónde sale el trazado

El INS publica la estructura del archivo **dentro** de RT-Virtual (opción
«Estructura del archivo», que pide la sesión de la póliza) y no en una página
abierta. Lo que se encontró en fuentes públicas el 2026-10-02:

- **El generador de referencia**, `RTVirtual.html` del repositorio
  `multiwebinc/RTVirtual` (GitHub), una reimplementación de la plantilla que el
  INS da a los patronos para armar la planilla fuera de línea. Su código escribe
  el archivo campo por campo, con la versión **V08D**, el nombre
  `PL<póliza><tipo><año><mes>-V08D (Texto).txt` y la codificación ISO-8859-1.
  El trazado de abajo es ese.
- **La charla oficial del INS** sobre RT-Virtual (Isabel Rodríguez Solís,
  Seguro Obligatorio de Riesgos del Trabajo, 2023; la publicó el corredor
  Comercial de Seguros), con las reglas de identificación: CN cédula nacional
  (9 dígitos), DU documento único (DIMEX, DIDI, salvoconductos, régimen
  excepcional, permiso de trabajo; 12 dígitos), NP pasaporte (11 caracteres),
  SD sin documentos; «el número de asegurado de los nacionales es igual al
  número de cédula (no debe incluir en txt)» y el de los extranjeros «es un
  número asignado por la CCSS (se debe incluir)». Y los tipos de planilla:
  mensual, adicional, inclusión y sustituida.
- La página «Presentación de planillas RT» de grupoins.com: salario mensual,
  horas y días por periodo, plazo de diez días hábiles desde el corte, topes de
  horas por jornada (tiempo completo 372, medio tiempo 120).

**Falta cotejarlo contra el documento del INS.** Quien tenga la póliza puede
bajar «Estructura del archivo» desde RT-Virtual y compararlo con esta página;
si difiere, se corrige `ins_record`/`ins_header` y la prueba
`tests/domain/test_payroll_files.py`, no la planilla.

## El archivo

Texto de ancho fijo, una línea por registro, fin de línea `CR LF`, codificación
ISO-8859-1. Tres líneas de encabezado y una por trabajador.

### Encabezado

| Línea | Posiciones | Contenido |
|---|---|---|
| 1 | 1–7 | Número de póliza, siete dígitos con ceros adelante |
| 1 | 8 | Tipo de planilla: `M` mensual (`A` adicional, `N` sin actividad, `E` especial) |
| 1 | 9–12 | Año |
| 1 | 13–14 | Mes |
| 1 | 15 | Espacio |
| 1 | 16–35 | Identificación del patrono: un dígito de tipo (`0` cédula física, `1` residencia, `2` a `4` jurídica, `6` documento único, `9` pasaporte) y el número, a la izquierda |
| 1 | 36–43 | Teléfono, ocho dígitos |
| 1 | 44–51 | Fax, ocho dígitos (ceros) |
| 1 | 52 | Espacio |
| 1 | 53–56 | Versión: `V08D` |
| 2 | 1–6 | `Email ` |
| 2 | 7–56 | Correo del patrono, a la izquierda |
| 3 | 1–10 | `Domicilio ` |
| 3 | 11–181 | Dirección, en mayúsculas, a la izquierda |

### Registro de trabajador (114 posiciones)

| Posiciones | Contenido |
|---|---|
| 1 | Tipo de identificación: `0` cédula nacional, `1` residencia, `6` documento único (DIMEX, NITE), `8` permiso de trabajo, `9` pasaporte, `5` sin documentos |
| 2–20 | Número de identificación, a la izquierda |
| 21–40 | Número de asegurado de la CCSS: solo extranjeros; el de los nacionales es la cédula y va en blanco |
| 41–55 | Nombre, mayúsculas |
| 56–70 | Primer apellido, mayúsculas |
| 71–85 | Segundo apellido, mayúsculas; `...` si no tiene |
| 86–98 | Salario del periodo con dos decimales y ceros adelante (`0000600000.00`) |
| 99–101 | Días trabajados |
| 102–105 | Horas trabajadas |
| 106–107 | Jornada: `01` tiempo completo, `02` medio tiempo, `03` ocasional por día, `04` ocasional por hora |
| 108–109 | Observación: `00` ninguna, `01` ingresó en el periodo, `02` salió, `03` incapacitado por la CCSS, `04` incapacitado por el INS, `05` ingresó y salió, `06` permiso sin goce, `07` licencia de maternidad, `08` ajustes anteriores |
| 110 | `0` |
| 111–114 | Código de ocupación del INS, cuatro dígitos |

## Cómo lo llena VentaSys

- El mes es el de las **corridas pagadas** —regulares y ajustes— cuyo corte cae
  en él (RN-96): el salario es la suma de lo devengado que cuenta como salario
  (`EARNED_CONCEPTS`: sin subsidios de incapacidad), los días son los que pagó el
  salario base y las horas, esos días por las horas de la jornada.
- La jornada es `01` si la jornada del contrato tiene seis horas o más por día
  y `02` si no. Las ocasionales no existen: el salario por hora quedó fuera de
  la primera versión (plan §14.1).
- La observación es una sola, la que más pesa: ingresó y salió, ingresó, salió,
  maternidad, incapacidad de la CCSS, del INS, permiso sin goce.
- Un trabajador va en el archivo de **su** póliza: la del contrato o, si no dice,
  la de la compañía por omisión. Un trabajador extranjero sin número de
  asegurado, un puesto sin código del INS o una compañía sin cédula detienen la
  exportación con `export_data_incomplete`, que lista a quién le falta qué.
- La identificación del patrono sale de `companies` (la misma del comprobante
  electrónico); el teléfono, el correo y la dirección, de la configuración del
  negocio.
