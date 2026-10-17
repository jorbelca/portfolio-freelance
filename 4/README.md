# Demo 4 — Extracción y validación de facturas

Pipeline en Python y LangGraph que extrae campos de facturas PDF, valida los datos con reglas deterministas y deriva a una cola de revisión los registros incompletos o inconsistentes. PostgreSQL conserva las facturas, la cola y el log de extracción.

## Demostración en vídeo

[![Extracción de datos de facturas con IA y validaciones](https://img.youtube.com/vi/jP3DWl4V5No/hqdefault.jpg)](https://www.youtube.com/watch?v=jP3DWl4V5No)

## Flujo de procesamiento

```text
PDF → extracción de campos → validaciones deterministas → gate → PostgreSQL
                                                         └→ cola de revisión
```

El modelo extrae los campos y aporta una puntuación de confianza. El código valida NIF/CIF, aritmética, fechas y duplicados; los casos que no superan las comprobaciones quedan registrados con el motivo de revisión. El panel SQL resume la cola, sus motivos, el importe retenido y la tasa de revisión.

## Componentes

- Python y **LangGraph** para el grafo de ingesta, extracción, validación y persistencia.
- PostgreSQL compartido con la demo 1 mediante `../1/docker-compose.yml`.
- OpenRouter para la extracción con modelo; la API de Google es una alternativa de respaldo.
- `pdfplumber` para leer texto; `fpdf2` y `Pillow` para generar los documentos sintéticos.
- `eval/` contiene el dataset etiquetado y el runner de evaluación.

El entorno Python necesita `langgraph`, `psycopg2-binary`, `openai`, `pdfplumber`, `requests`, `fpdf2` y `Pillow`. El repositorio no incluye un `requirements.txt`.

## Verificación

El dataset tiene 30 facturas sintéticas en tres layouts. En modo `--sin-llm`, la extracción inyectada permite evaluar el grafo y las reglas por separado de la calidad del modelo: cobertura **30/30**, decisión **30/30** y motivo **7/7**.

En una segunda corrida registrada con modelo real, el resultado fue **30/30 decisiones** y **6/7 motivos**. La primera corrida había dado 25/30 decisiones. Son medidas de ejecuciones concretas sobre datos sintéticos; la variabilidad del modelo impide interpretarlas como garantía de rendimiento.

## Ejecución local

Requiere Python 3, PostgreSQL y las dependencias del pipeline. La base puede levantarse con el Compose compartido. Desde `4/`:

```bash
docker compose -f ../1/docker-compose.yml up -d
psql -h 127.0.0.1 -U n8n_user -d n8n -f init-facturas-tables.sql
psql -h 127.0.0.1 -U n8n_user -d n8n -f panel/panel.sql
python3 generar_facturas.py
python3 procesar_facturas.py --sin-llm
python3 eval/run_eval.py --dry-run
python3 eval/run_eval.py
```

Configura las credenciales de PostgreSQL en las variables `PG*`. Para procesar con modelo, configura `OPENROUTER_API_KEY` y/o `GEMINI_API_KEY` según la implementación de `grafo_facturas.py`, y ejecuta `python3 procesar_facturas.py` sin `--sin-llm`. Consulta el script de evaluación antes de repetir una corrida: los registros anteriores deben limpiarse para evitar contar facturas duplicadas.

## Límites conocidos

- El caso de escaneo rasterizado no tiene OCR ni ruta multimodal. `pdfplumber` no obtiene texto de ese documento; su extracción requiere incorporar una de esas capacidades.
- Los documentos son sintéticos y el conjunto de prueba no representa la distribución de facturas de una organización real.
- El modo sin modelo mide reglas y persistencia, no la calidad de extracción del LLM.
