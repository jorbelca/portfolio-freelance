# Demos 1 y 2 — Intake de correo y consulta documental

Dos workflows de n8n para un despacho: clasificación auditable del correo entrante y consulta de documentos con referencias a la fuente. Ambos usan datos y documentos de demostración.

## Vídeos de demostración

### Demo 1 — Triage de correo

[![Triage de email con IA para despachos](https://img.youtube.com/vi/qgV2_4dWfp4/hqdefault.jpg)](https://www.youtube.com/watch?v=qgV2_4dWfp4)

### Demo 2 — Consulta documental con RAG

[![Consulta documental con recuperación y citas](https://img.youtube.com/vi/Ex0AMjs_mW8/hqdefault.jpg)](https://www.youtube.com/watch?v=Ex0AMjs_mW8)

## Demo 1: clasificación del correo

El workflow clasifica cada correo según una rúbrica versionada y registra la categoría y el motivo. Los casos ambiguos se derivan a revisión humana. La ejecución de prueba usa GreenMail como servidor SMTP/IMAP local.

## Demo 2: consulta documental

El workflow recupera fragmentos del corpus del despacho y devuelve respuestas con el documento y la página citados. Si el corpus no contiene evidencia suficiente, debe indicarlo en vez de completar la respuesta con información inventada.

## Componentes

- **n8n:** orquestación de los workflows incluidos en `Tarea 1 - Triage.json` y `Tarea 2 - RAG Citas.json`.
- **PostgreSQL y pgvector:** persistencia del registro de triage y recuperación de fragmentos.
- **OpenRouter:** acceso a los modelos configurados para la demo.
- **GreenMail y Roundcube:** correo de prueba y su interfaz web.
- **Corpus:** documentos de ejemplo en `corpus-demo/`.

La infraestructura compartida se define en `docker-compose.yml`. Los servicios locales se publican en n8n `:5678`, Roundcube `:8081` y Adminer `:8082`.

## Evaluación

El triage se contrasta con 28 correos etiquetados manualmente. La consulta RAG tiene 12 preguntas de prueba manual, incluidas dos preguntas sin respuesta en el corpus. Los datos, pasos y límites de evaluación están en [eval/README.md](eval/README.md).

## Ejecución local

Desde `1/`, inicia la infraestructura:

```bash
docker compose up -d
```

Importa los workflows en n8n y configura las credenciales necesarias. Para ejecutar el conjunto de triage y evaluar sus resultados, sigue el orden de [eval/README.md](eval/README.md); la carga de correos presupone que el workflow está habilitado.

## Límites

El corpus y los correos son sintéticos. Las etiquetas de evaluación son humanas, pero no constituyen una verdad jurídica objetiva. La demo no sustituye revisión profesional ni está conectada a correo o documentos reales.
