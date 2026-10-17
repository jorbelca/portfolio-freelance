# Demo 3 — Triage de incidencias para administradores de fincas

Workflows de n8n para clasificar incidencias recibidas por correo, recuperar las cláusulas o normas comunitarias relevantes y registrar la decisión y sus plazos asociados. Los casos ambiguos se derivan al administrador para revisión.

## Demostración en vídeo

[![Triage de incidencias con n8n y RAG de estatutos](https://img.youtube.com/vi/42BNbbwtvfA/hqdefault.jpg)](https://www.youtube.com/watch?v=42BNbbwtvfA)

## Flujo

1. El workflow recibe una incidencia por el correo de pruebas.
2. La clasifica según la rúbrica de imputación documentada en [`rubrica-imputacion-fincas.md`](rubrica-imputacion-fincas.md).
3. Recupera estatutos de la comunidad correspondiente en pgvector y registra el fundamento disponible.
4. Registra la decisión, los plazos detectados y la ruta de revisión en PostgreSQL.

La clasificación puede ser `comun`, `privativo`, `mixto` o `no_aplica`. La automatización no fuerza una respuesta cuando falta evidencia o la decisión requiere revisión humana.

## Componentes

- **n8n:** workflow de triage (`Tarea B1 - Triage Incidencias.json`) y workflow de ingesta de estatutos (`Tarea B2 - Carga Estatutos.json`).
- **PostgreSQL y pgvector:** persistencia de incidencias, eventos y fragmentos documentales.
- **OpenRouter:** modelo usado por los nodos de clasificación.
- **GreenMail y Roundcube:** correo de prueba y su interfaz web, compartidos con la infraestructura de `../1/`.
- **Corpus:** estatutos sintéticos en `comunidades/`.

## Evaluación

El dataset contiene 45 incidencias etiquetadas manualmente. La evaluación RAG incluye 12 preguntas y mide recuperación e aislamiento entre comunidades; no mide la calidad de respuestas redactadas por el modelo. Consulta [eval/README.md](eval/README.md) para los comandos y el detalle de lo que mide cada prueba.

## Ejecución local

La infraestructura se comparte con las demos 1 y 2. Desde `2/`:

```bash
docker compose -f ../1/docker-compose.yml up -d
```

Importa los workflows en n8n, carga el esquema y los datos de ejemplo y configura las credenciales del modelo. Los pasos reproducibles de evaluación están en [eval/README.md](eval/README.md).

## Límites

Los correos y estatutos son datos sintéticos. La evaluación contrasta las salidas con una rúbrica escrita para la demo, no con una determinación jurídica universal. Las respuestas no son asesoramiento jurídico y los casos dependientes de interpretación humana deben revisarse.
