# Eval de la Demo 5

`dataset.jsonl` — 30 leads etiquetados a mano. Cada fila:

- `lead` — lo que entra al grafo (empresa + contacto).
- `senales_crudas` — lo que `buscar_señales` habría devuelto. Sustituye SOLO la mitad web en
  los dos modos de abajo. La **ficha** nunca se inyecta: sale siempre de `ficha_empresa()`
  (mock sobre `fichas.json`) para que el eval y el vídeo no puedan divergir. Las 6 empresas de
  las filas R14 (`l15`–`l20`) **no están en `fichas.json`** a propósito → `{}` → R14.
- `hallazgos` — el juicio "verdad" del modelo (señales con `ref`, encaje, decisor, confianza,
  etiqueta rival). Se inyecta solo en `--sin-llm`.
- `esperado` — `{etiqueta, regla, resultado_log, en_cola, motivo_contiene?}`. `en_cola` es
  "la clasificación mandó el lead a revisión", **no** "existe una fila en `cola_leads`": un
  `caliente` tiene `en_cola: false` aunque V2 le cree una fila `tipo='borrador'` (esa cola es
  otra cosa — el borrador de email esperando visto bueno, no una duda).

## Cómo correrlo

```bash
python3 eval/run_eval.py --dry-run          # estructural, sin Postgres
# tras procesar_leads.py contra Postgres:
python3 eval/run_eval.py                     # lee cualificacion_log y compara
# antes de re-medir, vaciar (si no, corridas apiladas -> run_eval aborta):
psql ... -c "TRUNCATE leads, cola_leads, cualificacion_log RESTART IDENTITY;"
```

## Dos modos, dos números — no se promedian

| Modo | Qué se inyecta | Qué mide |
|---|---|---|
| `procesar_leads.py --sin-llm` | `senales_crudas` + `hallazgos` | **El código.** `aplicar_rubrica` + gate + persistencia + log, con el juicio fijado. Debe dar 30/30 — si no, hay un bug en las reglas. |
| `SALTAR_INVESTIGACION=1 procesar_leads.py` | solo `senales_crudas` | **El modelo.** Clasifica sobre evidencia fija y reproducible; el número (acierto de etiqueta, acierto de regla) es el que va al vídeo. Por debajo de 100 % porque es un modelo gratis. |

El modo sin ninguna variable corre el bucle ReAct real (`buscar_señales` en vivo) — para la
grabación, no para medir.

**`regla` es la métrica que más importa**, más que el acierto de etiqueta: tres reglas
distintas (R8, R11, R12) producen `tibio`, y solo `regla` las distingue. `run_eval.py` la
reporta en su propio bucket (mismo criterio que "fundamento equivocado con imputación
correcta" en la Demo 3).

**Pendiente antes de grabar:** los `hallazgos` del dataset son "verdad" asumida. Falta una
corrida `SALTAR_INVESTIGACION=1` sobre `l06` (encaje débil → R8) y `l07` (contacto junior →
R9) con modelo real: si el modelo no deriva `encaje_producto: "debil"` / `contacto_decisor:
false` de los snippets escritos, hay que reforzar el snippet, no la regla.

## Distribución del dataset

- 8 con encaje claro y señales → `caliente`/`tibio` (`l01`–`l07`, `l28`, `l29`)
- 7 descalificados → `frio`, uno por regla R1–R7 (`l08`–`l14`, `l30`)
- 6 sin ficha → cola `sin_cualificar` / R14 (`l15`–`l20`)
- 4 en frontera → cola: R13 rival (`l21`, `l22`), R15 confianza baja (`l23`, `l24`)
- 2 duplicados → cola: email (`l25`), empresa (`l26`)
- relleno: `l27`

Sin los casos difíciles etiquetados, el eval solo mide el camino feliz y el vídeo no tiene
discrepancia que enseñar.
