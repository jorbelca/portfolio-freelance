# Plan Demo A — Intake y consulta documental para despachos

Demo self-hosted de n8n: triage automático del correo de entrada y consulta del archivo
documental con citas verificables `[documento, página]`.

## Hecho

- [x] Infra en `docker-compose.yml`: n8n + Postgres (pgvector) + GreenMail (SMTP 3025 / IMAP 3143) + Roundcube (8081).
- [x] Postgres con `healthcheck` (`pg_isready`) y n8n arrancando con `condition: service_healthy`.
- [x] `init-pgvector.sql` e `init-triage-tables.sql` montados en `/docker-entrypoint-initdb.d/` (orden alfabético correcto):
      extensión `vector` + tablas `expedientes`, `expediente_notas`, `revision_humana`, `errores`.
- [x] Autenticación de n8n: cuenta de propietario en el primer arranque (las `N8N_BASIC_AUTH_*` ya no existen en n8n 2.x).
- [x] Workflow A `Tarea 1 - Triage.json`: IMAP → agente (Gemini + Postgres Chat Memory) → Switch → acción por rama.
- [x] Workflow B `Tarea 2 - RAG Citas.json`: ingesta de PDF → chunking → embeddings → pgvector; chat con citas o "no tengo información suficiente".
- [x] `Error Handler.json`: Error Trigger → log en Postgres → aviso.
- [x] Corpus `corpus-demo/`: 4 documentos en `.md` y los 4 `.pdf` correspondientes.
- [x] `.env.example` coherente con GreenMail (SMTP/IMAP) + `TRIAGE_CONFIANZA_UMBRAL`; `.gitignore` al día.
- [x] Material de origen del curso archivado en `practica-8.1-original/`.

## En curso en esta ronda (lo llevan otros agentes)

- [ ] Rúbrica de intake (`rubrica-intake-legal.md`) y corpus de 28 correos etiquetados. (en curso)
- [ ] Campo `confianza`, tabla `triage_log` e idempotencia por `message_id` en el workflow de triage. (en curso)
- [ ] Arnés de evaluación en `eval/` (precisión por categoría, tasa de derivación a revisión humana). (en curso)
- [ ] Aviso de interacción con IA en las respuestas automáticas, por el Art. 50 del AI Act. (en curso)

## Pendiente — no automatizable desde aquí

- [ ] Crear la cuenta de propietario en el primer arranque de la UI de n8n.
- [ ] Importar los 3 JSON en la UI de n8n y activarlos.
- [ ] Cablear credenciales reales: IMAP, SMTP, Gemini y Postgres.
- [ ] Crear la tabla `documentos_despacho` (pgvector, Workflow B): ningún SQL montado la crea todavía.
- [ ] Subir el corpus por el Workflow B y comprobar que las citas apuntan a la página correcta.
- [ ] Grabar el vídeo de demo de 90 s.

## Notas conocidas

- Los PDF de Modelo B, escritura y poder notarial son de **una sola página**: una cita contra ellos
  no demuestra la precisión por página. Solo el Modelo A tiene 2 páginas. Conviene regenerarlos
  más largos antes de grabar el vídeo.
- `.env` conserva `SMTP_HOST`/`SMTP_PORT` con los valores antiguos de MailHog; hay que corregirlos a mano
  (no se tocan los valores ya presentes en `.env`).
