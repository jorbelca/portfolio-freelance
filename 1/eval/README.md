# eval/ — arnés de evaluación

- `dataset.jsonl` — 28 correos etiquetados a mano para el triage (Tarea 1). Solo lectura.
- `run_eval.py` — compara `triage_log` (Postgres) contra `dataset.jsonl` y da veredicto.
- `rag_casos.jsonl` — 12 preguntas para probar el chat RAG (Tarea 2), a mano, sin runner.

## Orden de ejecución (Tarea 1 — triage)

1. `docker compose up -d`
2. Cargar `seed-expedientes.sql` en Postgres.
3. `python3 seed_emails.py` (envía los 28 correos vía SMTP/IMAP de prueba).
4. Esperar a que el workflow de n8n procese los 28 correos (revisar `triage_log`).
5. `python3 eval/run_eval.py`
   Opciones: `--umbral-acierto` (default 0.85), `--dataset`, `--dsn`, `--dry-run`
   (valida el informe sin Postgres, con datos sintéticos en memoria).

## Cómo leer la salida

Siete secciones: cobertura, acierto global, matriz de confusión, desglose
fácil/ambiguo, discrepancias (material para el vídeo), errores por tramo de
confianza, y escalados a revisión (y cuántos de más). El `assert` final exige
cobertura 100% y acierto >umbral en los **no ambiguos**; si falla, código de
salida distinto de cero (test de regresión al tocar el prompt o cambiar de modelo).

## Tarea 2 — RAG (`rag_casos.jsonl`)

Sin runner: el chat RAG es interactivo y automatizarlo exige webhook, así que estos
12 casos son un **guion de prueba manual** — se pegan uno a uno en el chat y se
compara contra `documento_esperado`/`fragmento_clave`. Exactamente 2 son preguntas
trampa (`respondible: false`): aprueban si el sistema dice que no tiene información
suficiente, no si contesta. Solo `Contrato de arrendamiento - Modelo A.pdf` tiene
2 páginas (los otros 3 son de una); la evaluación de citas por página solo puede
demostrarse con r02/r03 contra ese documento.

## Qué NO demuestra esta evaluación

- Vale lo que valgan las etiquetas: las puso una persona, no son verdad objetiva.
- Un modelo evaluado con preguntas/etiquetas generadas por él mismo mide su
  consistencia, no su corrección — por eso el etiquetado es manual.
- No sustituye un despliegue real con datos y usuarios de verdad.
