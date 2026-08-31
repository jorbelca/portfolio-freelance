# Plan Demo 5 — Cualificación de leads → asignación → primer contacto

**No son dos proyectos.** V2 = V1 + una cola de 2 nodos. Un solo repo, un solo grafo, un solo
vídeo con dos actos. Reutiliza casi entero el grafo de la Demo 4 y el `docker-compose.yml` de
`../1/`. Semana W36 (2026-08-31 → 2026-09-05).

## Arquitectura — un grafo, cola opcional

```
ingesta_lead
  → investigacion_agente        [V1: bucle ReAct]
        loop: ficha_empresa → buscar_señales → ¿bastante? → sigue | para
  → cualificacion_llm (rúbrica versionada, rubrica-cualificacion-leads.md)
  → validacion_determinista (campos, email, dedup SQL, trazabilidad de señales)
  → gate_confianza
      ├─ cola_revision  ───────────────────────────────┐
      └─ persistir_ok → Postgres                       │
            → enrutado (dict estático)     [V2 cola]    │
            → redaccion_outreach (1 llamada LLM)        │
            → cola_revision (tipo='borrador') ──────────┤
            → email_borrador (GreenMail, sin enviar)    │
                                                        ↓
                              log de motivos en TODOS los caminos
```

`SALTAR_INVESTIGACION=1` inyecta una `ficha_empresa` y unos fragmentos de `buscar_señales`
predefinidos por caso (patrón `canned_extraccion` de la Demo 4) — el eval mide la
clasificación con evidencia fija. Única perilla.

Tools de `investigacion_agente` (2, no más):
1. `ficha_empresa(nombre)` → mock sobre dataset sintético etiquetado como tal (hechos de registro)
2. `buscar_señales(nombre)` → búsqueda web real, 1 API pública gratis (señales de timing; el dato "en vivo" del vídeo)

## V2 reducida — qué se corta

| Cortado | Sustituto |
|---|---|
| Integración de calendario / `programar_followup` | Campo `followup_sugerido: "3 días"` en el log. Sin API. |
| Enrutado por carga / round-robin | Dict estático `{territorio/producto → comercial}`. ~10 líneas. |
| Notificación multicanal (Slack + tarea CRM + email) | Solo el email borrador en GreenMail. |
| Secuencia de outreach (varios emails) | Solo el primer email. |

## Hecho

- [x] **Lun 31** — Alcance escrito (`README.md`). Rúbrica v0.1 (`rubrica-cualificacion-leads.md`):
      16 reglas R1–R16, prelación first-match-wins en 4 bloques (descalificadores → gates de
      encaje → conteo de señales → comprobaciones sobre la etiqueta elegida). ICP ficticio
      "Nubeforge" (SaaS de observabilidad de coste/pipelines cloud → startups de producto UK
      post-PMF). Esquema (`init-leads-tables.sql`): `leads` / `cola_revision` /
      `cualificacion_log`, mismo reparto que la Demo 4, dedup por email y empresa en SQL,
      verificado con Postgres efímero (idempotente, CHECK y UNIQUE disparan).
- [x] **Lun 31 (adelantado el core de Mar)** — `grafo_leads.py`: 8 nodos
      (ingesta → investigación → cualificación → aplicar_rúbrica → validación → gate →
      {persistir | cola}), log en todo camino. R1–R12 en Python (`aplicar_rubrica` /
      `_descalificar`), el modelo solo devuelve juicio sin etiqueta. `validaciones.py`
      (email, trazabilidad de señales, `normalizar_empresa`). `procesar_leads.py`
      (`--sin-llm` + `SALTAR_INVESTIGACION`). `test_rubrica.py` (alcanzabilidad R8/R9/R11/R12,
      regla dura, R13–R15). `langgraph.json`, `.env.example`, `diagrama.py`, `grafo_leads.mmd`.
      Verificado end-to-end contra Postgres efímero.
- [x] **Lun 31 (adelantado Mié)** — `tools.py` (`ficha_empresa` mock sobre `fichas.json` /
      `buscar_senales` DuckDuckGo real, fallo→[]). `investigacion_agente` real: `ficha_empresa`
      siempre; la parte web es el bucle ReAct (modelo elige query o `parar`, hasta
      `LEADS_MAX_BUSQUEDAS`). `canned_ficha` eliminado — `SALTAR_INVESTIGACION` solo sustituye
      la mitad web. `fichas.json` (22 empresas). `eval/dataset.jsonl` (30 leads con `esperado`;
      8 encaje claro / 7 frío 1-por-regla / 6 sin ficha R14 / 4 frontera / 2 dup).
      `eval/README.md` (dos modos, dos números). `test_rubrica.py::test_dataset_replay` 30/30.
      Verificado `--sin-llm` completo contra Postgres efímero: 30/30 (leads 18, cola 12).
- [x] **Lun 31 (adelantado Jue)** — Cola V2: `enrutado` (dict sector→comercial + followup
      "3 días") → `redaccion_borrador` (1 llamada al modelo, o plantilla marcada; email a
      `borradores@nubeforge.local`, nunca al prospecto; sin SMTP → `borrador_message_id` NULL
      pero la fila de cola `tipo='borrador'` igual se crea). `_rama_persistir`: solo `caliente`
      pasa a redacción (R16). `panel/panel.sql` (6 vistas; `v_cola_pendiente` filtra
      `tipo='cualificacion'`, `v_borradores_pendientes` aparte). `eval/run_eval.py` (patrón
      `1/eval`; `--dry-run` + real; bucket propio para `regla`; aborta si hay corridas
      apiladas). Verificado e2e: `--sin-llm` 30/30, `run_eval` 100 %/100 %, 4 caliente →
      borrador + asignación.

## Pendiente W36

- [ ] **Mar–Jue** — buffer (todo el build adelantado). Pendiente real:
      **medir el modo `SALTAR_INVESTIGACION` con `OPENROUTER_API_KEY`** (modelo sobre evidencia
      fija) y anotar el número del vídeo; falsar los `hallazgos` de `l06`/`l07`; probar el
      bucle ReAct en vivo contra GreenMail levantado.
- [ ] **Sáb 5** — 1 vídeo, 2 actos + subir a Malt/LinkedIn.

**Escape hatch.** Si el jueves va justo: se publica V1 solo el sábado, la cola V2 pasa a W37.
V1 cierra el hueco de perfil (tool-loop LangGraph); V2 es brillo. Nunca al revés.

## Vídeo — ~90 s, 2 actos

1. (35 s) **Acto V1**: entra un lead. El agente investiga en vivo — ficha, señales de hiring,
   ronda de financiación. Clasifica `tibio` con la evidencia y las fuentes citadas.
2. (20 s) **La discrepancia**: segundo lead, empresa sin rastro. El agente busca, no encuentra,
   manda a cola. "Cuando no hay con qué decidir, no decide."
3. (25 s) **Acto V2**: tercer lead, `caliente`. Se asigna a la comercial de su territorio, se
   redacta el primer email citando por qué encaja, aparece en GreenMail como borrador. Nada se
   envía solo.
4. (10 s) **Cierre**: "Clasifica con evidencia, redacta el primer contacto, y para cuando no
   está seguro."
