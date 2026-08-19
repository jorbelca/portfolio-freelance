# Práctica 8.1 — workflows originales del curso

`Tarea 1.json` y `Tarea 2.json` son los workflows tal cual salieron de la Práctica 8.1, sin modificar.
Se conservan aquí para poder comparar el antes y el después frente a los workflows de la demo
(`Tarea 1 - Triage.json` y `Tarea 2 - RAG Citas.json`, en la raíz del proyecto).

Qué se sustituyó exactamente:

- Schedule Trigger → IMAP Trigger (el flujo reacciona a correos reales, no a un reloj).
- Wikipedia, OpenWeatherMap y HTTP Request → eliminados (herramientas de juguete, sin uso en un despacho).
- Simple Memory (buffer en memoria) → Postgres Chat Memory (persistente entre reinicios).
- Vector store en memoria → Postgres + pgvector (el corpus sobrevive al reinicio y admite citas por documento y página).
