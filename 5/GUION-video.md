# Guion de vídeo — Demo 5 (~90 s, 2 actos)

Mismo principio que las demos 1-4: se enseña **la discrepancia, no el acierto**. El lead que
se paró y esperó a un humano vale más que los 20 que se clasificaron solos.

## Antes de grabar

- `docker compose up -d` en `../1/` (Postgres + GreenMail + Roundcube + Adminer).
- `psql ... -f init-leads-tables.sql -f panel/panel.sql`
- `TRUNCATE leads, cola_leads, cualificacion_log RESTART IDENTITY;`
- Decidir el modo de Act 1 (ver nota abajo).
- Pestañas abiertas: terminal · Roundcube (`:8081`, login `borradores@nubeforge.local`) ·
  Adminer (`:8082`) o `./ver.sh`.

**Nota — investigación en vivo vs. inyectada.** Las 22 empresas de `fichas.json` son ficticias,
así que `buscar_señales` (DuckDuckGo real) no devuelve nada útil sobre ellas. Dos opciones para
Act 1:

- **A (recomendada):** un `video_leads.jsonl` aparte con 3 empresas UK **reales** (ronda +
  hiring verificables), sus fichas añadidas a `fichas.json`. El bucle ReAct busca de verdad en
  cámara. Riesgo: la búsqueda web es inestable — hacer 2-3 tomas y quedarse con una real, sin
  forzar (misma disciplina que `4/README.md`).
- **B:** `SALTAR_INVESTIGACION=1` con el dataset actual; se narra el bucle desde
  `investigacion_pasos` en el log en vez de mostrarlo corriendo. Más seguro, menos vistoso.

---

## Acto 1 — V1: clasifica con evidencia (≈40 s)

| # | Dur | En pantalla | Narración / subtítulo |
|---|---|---|---|
| 1 | 8 s | Terminal: `python3 procesar_leads.py` con un lead nuevo entrando | "Entra un lead. Antes de clasificar, un agente lo investiga." |
| 2 | 14 s | El bucle ReAct: `ficha_empresa` → `buscar_señales("… funding")` → `buscar_señales("… hiring")` → `parar`. Fragmentos reales apareciendo. | "Consulta el registro, busca señales de que *ahora* es el momento — ronda, contratación, dolor con el coste de nube. Y decide cuándo tiene bastante." |
| 3 | 10 s | Resultado: `tibio · R11 · una sola señal (S2) — no basta para caliente`. La fila en `leads` con el motivo y la URL de la señal. | "Una sola señal no es un lead caliente. La etiqueta la pone una regla escrita, no el modelo — y queda el porqué, con la fuente." |
| 4 | 8 s | `rubrica-cualificacion-leads.md` en el editor, la tabla de reglas R1–R16 | "El criterio vive en un fichero versionado. Cuando el cliente afina qué es 'caliente', se ve en el diff." |

## Discrepancia — cuando no hay con qué decidir (≈18 s)

| # | Dur | En pantalla | Narración |
|---|---|---|---|
| 5 | 10 s | Segundo lead. El agente busca, no encuentra ficha, `buscar_señales` vuelve vacío. | "Segunda empresa. Sin rastro en el registro, sin señales públicas." |
| 6 | 8 s | `sin_cualificar` → `cola_leads`, motivo `sin evidencia para cualificar`. **No** se marca `frío`. | "No la descarta: la manda a una persona. Ausencia de datos no es una señal negativa." |

## Acto 2 — V2: asigna y redacta el primer contacto (≈25 s)

| # | Dur | En pantalla | Narración |
|---|---|---|---|
| 7 | 8 s | Tercer lead, caliente: `R10 · encaje ICP + 2 señales: S1, S2`. Se asigna: `asignado_a = Marco Vidal` (dict por sector). | "Tercer lead. Ronda reciente y contratando plataforma: caliente. Se asigna al comercial de su territorio." |
| 8 | 10 s | Roundcube: aparece el borrador `[BORRADOR — revisar antes de enviar] Nubestack Ltd …`, dirigido a `borradores@nubeforge.local`. Se abre: cita el motivo de encaje. | "Se redacta el primer email, citando por qué encaja. Va a la bandeja de borradores — nunca al prospecto." |
| 9 | 7 s | `v_leads_borradores` en `./ver.sh`: la fila esperando visto bueno. | "Nada se envía solo. Un humano lo aprueba." |

## Cierre + conexión al precio (≈10 s)

| # | Dur | En pantalla | Narración |
|---|---|---|---|
| 10 | 6 s | `python3 eval/run_eval.py` — acierto de etiqueta, acierto de **regla**, cola con motivos | "Se mide: acierta X de 30, y manda los dudosos a revisión con motivo. No '100 %'." |
| 11 | 4 s | Tarjeta de cierre | "Clasifica con evidencia, redacta el primer contacto, y para cuando no está seguro." |

**Conexión al precio (para la descripción de Malt/LinkedIn, no en cámara).** Oferta 3 del
estudio, 250–2.500 $. Lo que se cobra no es el grafo — se copia en una tarde — es la **rúbrica
calibrada contra los leads reales del cliente y el corpus etiquetado** (§7). El entregable que
un comprador puede auditar sin fiarse de mí: *queda registrado por qué cada lead se clasificó
como frío*.

## Qué NO grabar

- El dataset fácil "porque queda más limpio". Los casos difíciles (`l15`–`l26`) existen para
  tener discrepancia que enseñar.
- El número del modo `--sin-llm` (100 %) como si fuera el acierto real. El número del vídeo
  sale del modo `SALTAR_INVESTIGACION` con modelo real.
