# Demo 10 — CSV Guard

Herramienta local en Python para revisar exportaciones de pedidos antes de importarlas en otro sistema. Produce un informe HTML con problemas concretos y su línea de origen. Es una demo nueva e independiente de las otras carpetas del portfolio; funciona sin IA, servicios externos, credenciales ni dependencias adicionales.

## Ejecutar

Desde la raíz del repositorio, con Python 3.10 o superior:

```bash
python3 -m unittest discover -s 10 -v
python3 10/csv_guard.py 10/examples/orders.csv --report /tmp/csv-guard-report.html
open /tmp/csv-guard-report.html
```

El destino debe ser nuevo: no se sobrescriben informes. El código de salida es `0` si no se detectan incidencias, `1` si hay incidencias y `2` si falla la lectura o escritura. Un resultado `1` con el dataset de ejemplo es el comportamiento esperado.

También se incluye `demo-report.html`, generado por la herramienta a partir del ejemplo.

## Alcance implementado

- CSV UTF-8, con o sin BOM; separador coma y comillas estándar.
- Columnas obligatorias: `order_id,date,quantity,unit_price,total`. Se permiten columnas adicionales, pero no cabeceras repetidas.
- IDs obligatorios y únicos, fechas YYYY-MM-DD válidas, cantidades enteras positivas y precios/importes no negativos con hasta dos decimales.
- Cantidad máxima: un millón; precio y total máximos: mil millones. Son límites explícitos de esta demo.
- Comparación decimal exacta de cantidad × precio frente al total.
- Informe escapado, sin recursos externos, que no copia el contenido de los pedidos.
- El archivo fuente no se modifica.

El ejemplo contiene ocho pedidos inventados y cinco incidencias: un total incorrecto, un ID repetido, una fecha imposible, una cantidad negativa y un precio no finito. Son incidencias, no necesariamente filas distintas en cualquier dataset.

## Recorrido de demostración — 90 segundos

1. Mostrar `examples/orders.csv` y explicar el problema: descubrir errores antes de importar.
2. Ejecutar las pruebas y el comando de validación.
3. Abrir el informe: resumen → campo afectado → línea y motivo.
4. Copiar el CSV a un archivo temporal y corregir: total 50.00, segundo DEMO-002 a DEMO-004, fecha 2026-02-28, cantidad 2 y precio 25.00.
5. Validar la copia en otro informe: ocho filas, cero incidencias.
6. Enseñar una mejora pendiente de las siguientes como trabajo real por desarrollar.

## Trabajo pendiente para sesiones de desarrollo

Estas tareas todavía NO están implementadas; ofrecen sesiones concretas de funcionalidad, depuración y refactorización:

| Tarea | Criterio de aceptación |
|---|---|
| Separador configurable | Leer CSV con punto y coma sin romper campos entrecomillados ni la numeración de líneas. |
| Reglas configurables | Cargar un esquema JSON local; rechazar configuraciones inválidas con errores claros. |
| Informe JSON para automatizaciones | Mismas incidencias que HTML, con versión de esquema y códigos estables. |
| Procesar archivos grandes | Limitar el detalle del informe y mantener contadores exactos; medir memoria con datos sintéticos. |
| Rangos de líneas | Mostrar inicio y fin de registros con campos multilínea. |

No es un sistema de evaluación de modelos ni infraestructura ML. Las pruebas son pruebas de software de una herramienta de calidad de datos.

## Límites

No concilia varias fuentes, no interpreta impuestos o descuentos y no verifica la veracidad comercial de los pedidos. Un CSV mal formado aborta con error; no se publica un informe parcial. Los IDs y las incidencias se mantienen en memoria, por lo que esta versión no está optimizada para archivos enormes. La interfaz es un informe estático, no un editor.

## Encaje con LBLX135

La oferta aportada pide un proyecto propio en Git sobre el que realizar trabajo normal con un asistente. Esta demo muestra Python, terminal, pruebas, reglas deterministas y trazabilidad, áreas presentes en este portfolio, sin requerir datos personales ni APIs.

Antes de presentarla como proyecto elegible, confirma que puedes declarar titularidad exclusiva y que no corresponde a trabajo de cliente, empresa o universidad. La carpeta está dentro de este repositorio Git; si el cliente pide un repositorio dedicado, prepara uno únicamente con estos archivos y revisa su contenido antes de compartir. No se ha creado un repositorio remoto ni elegido una licencia en tu nombre. Si lo presentas como open source, la oferta exige una licencia aprobada.

La aceptación final depende del cliente. No se ha enviado ninguna propuesta ni formulario. Las valoraciones y razones de preferencia durante sus sesiones deben escribirlas exclusivamente el participante, sin ayuda de IA, según la oferta.
