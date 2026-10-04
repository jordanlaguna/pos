# Planilla del mes para la CCSS (SICERE)

Lo que entrega `GET /payroll/exports/ccss?year=&month=` y arma
`backend/app/domain/payroll_files.py` (`ccss_report`, T-1211, RF-62, RN-96), y
por qué **no es un archivo de texto**.

## Lo que se encontró (2026-10-02)

La CCSS recibe la planilla de dos maneras:

- **Autogestión Planilla en Línea**, el formulario de la Oficina Virtual con el
  que la presenta el 98 % de los patronos. La guía oficial está acá:
  `GF-DSCR-F004 guia autogestion planilla en linea.pdf` (Dirección SICERE,
  «Guía para realizar la presentación y cambios en la planilla»). Describe lo
  que se teclea por trabajador: el salario del mes (con punto para los
  céntimos), la jornada (diurna 8 horas, parcial 4, mixta 7, vespertina 7,
  nocturna 6), la ocupación de la lista de la CCSS, las incapacidades con fecha
  de inicio y fin y su tipo (SEM, INS, IVM, maternidad), los permisos con o sin
  goce de salario, la pensión y la clase de seguro, la exclusión con fecha,
  motivo y salario hasta la salida, y la inclusión con tipo de identificación
  —cédula del Registro Civil a nueve posiciones con cero adelante, o número de
  asegurado de ocho o diez dígitos para extranjeros—, fecha de ingreso, salario,
  clase de seguro, jornada y ocupación. El periodo va del 26 de cada mes al
  cuarto día hábil del siguiente.
- **Carga por archivo**, para «grandes clientes» (unos mil patronos: la propia
  CCSS, el MEP, grandes empresas). Su estructura técnica **no está publicada**:
  no aparece en ccss.sa.cr ni en ningún documento abierto que se haya podido
  encontrar; los proveedores de planilla que la generan tampoco la describen.
  Se pide a la Dirección SICERE (`plautogestion@ccss.sa.cr`).

El formulario de ajuste de planilla, `GF-DSCR-F071 solicitud ajuste de
planilla.xlsx`, confirma los mismos datos y tipos de cambio: cambio de salario,
exclusión, inclusión, incapacidad (SEM, INS, maternidad), permiso, ocupación y
jornada (diurna, parcial, nocturna, mixta).

## Lo que hace VentaSys

Como el trazado del archivo no se supone (plan §14.8), el módulo entrega **el
informe del mes con exactamente lo que el formulario pide**, por trabajador, y
la pantalla lo muestra y lo deja descargar para teclearlo o cotejarlo:

- la identificación como la pide la CCSS (cédula a nueve dígitos; a los demás,
  su número de asegurado), el nombre completo, el código de ocupación del
  puesto y la jornada (`diurna`, `parcial`, `mixta`, `nocturna`);
- el salario que cotiza en el mes y los días que pagó el salario base, de las
  **corridas pagadas** —regulares y ajustes— cuyo corte cae en el mes;
- cada movimiento con sus fechas: inclusión (fecha de ingreso), exclusión (fecha
  y causa), incapacidad por SEM, por INS o por maternidad (desde y hasta, de los
  tramos que las corridas aplicaron, juntando los de una misma acción), permiso
  con o sin goce, y cambio de ocupación (fecha y código nuevo).

Un trabajador extranjero sin número de asegurado, un puesto sin código o una
compañía sin número patronal detienen la exportación con
`export_data_incomplete`, que lista a quién le falta qué.

El día que la Dirección SICERE entregue la estructura del archivo de grandes
clientes, el escritor va en `payroll_files.py` al lado del del INS, con su
prueba contra el ejemplo que venga con la especificación; los datos ya están.

## La renta retenida

`GET /payroll/exports/income-tax?year=&month=` suma, por trabajador, lo
gravable y lo retenido en las corridas pagadas del mes (los rubros
`income_tax`), que es lo que se declara a Hacienda (RN-73).
