# Demo 4 — Extracción de facturas → cola de revisión → panel

Grafo de agentes (LangGraph, Python) que extrae los datos de una factura PDF, los contrasta
contra validaciones deterministas (NIF/CIF, aritmética, fecha, deduplicación) y manda a revisión
humana lo que no cuadra. Igual que las demos 1-3: el LLM decide solo donde hace falta juicio, la
validación es determinista y vive fuera del modelo, los casos dudosos van a cola con motivo.

Construido con LangGraph, Postgres (reutiliza la infraestructura de `../1/docker-compose.yml`)
y modelos vía OpenRouter. Por qué LangGraph y no n8n como las demos 1-3: ver §14.2 de
`demos-portfolio-exposicion-2026` (sustrato de implementación / hueco de aprendizaje del perfil,
no una carencia de n8n — n8n también puede hacer llamadas agénticas, ver AI Agent node).

## Estado actual: pipeline + dataset + eval completos, probado con `--sin-llm` y con LLM real

Lo que YA funciona de punta a punta contra Postgres real:
- 30 facturas sintéticas (`generar_facturas.py`), 3 layouts distintos (estándar/compacta/tabla): 2 con aritmética rota, 2 con NIF inválido, 1 sin número, 1 duplicado, 1 IVA 10% normal, 1 IVA 4% normal, 1 escaneo ruidoso, 1 multipágina, 19 de relleno limpias variadas
- Las 4 validaciones deterministas (`validaciones.py`), con autocheck (`python3 validaciones.py`)
- El grafo completo (`grafo_facturas.py`): ingesta → extracción → validación → gate → persistir/cola, con log de motivos en todo camino
- Panel SQL (`panel/panel.sql`): cola pendiente, motivos más frecuentes, importe retenido, tasa de revisión por día
- `eval/run_eval.py` (patrón `2/eval/run_eval.py`): cobertura, acierto de decisión, acierto de motivo, con `--dry-run` estructural (asserts, exit 0) separado de la corrida real

Verificado con `--sin-llm` (extracción inyectada, mide solo grafo/validación/gate/persistencia,
no la calidad del LLM): **30/30 cobertura, 30/30 decisión, 7/7 motivo correcto.**

Verificado con LLM real, primera pasada (2026-08-25, `google/gemma-4-31b-it:free` vía
OpenRouter, fallback directo a la API de Google si OpenRouter falla): **30/30 cobertura, 25/30
(83.3%) acierto de decisión, 6/7 motivo correcto** — por debajo del umbral 85% de `run_eval.py`
(falla a propósito, no se bajó el umbral para que pasara). Root cause de los 5 fallos: el modelo
devolvió confianza 1.0 pero valores vacíos/cero en varias facturas limpias (visto con texto de
entrada perfectamente legible, confirmado con `pdfplumber` aparte) — no reproducible entre
corridas (fallaban invoices distintas cada vez), ruido de fiabilidad del modelo gratis, no un
bug del pipeline. No se relanzó buscando una corrida con suerte que pasara el 85% -- sería
maquillar la métrica.

Verificado con LLM real, segunda pasada (2026-08-25, tras cambiar a
`dots-studio/dots-3-note-preview:free` vía OpenRouter + los 5 arreglos de abajo): **30/30
cobertura, 30/30 (100%) acierto de decisión, 6/7 motivo correcto** (el único motivo distinto
sigue siendo f10, ver más abajo -- no es un fallo nuevo). Umbral 85% superado por primera vez.
No se puede prometer 100% estable en cada corrida (sigue siendo un modelo gratis, con la misma
varianza de fondo que la primera pasada), pero confirma que los 5 bugs de abajo eran una parte
real y corregible del 83.3%, no solo ruido.

Seis bugs reales encontrados y arreglados en el camino, los seis en `grafo_facturas.py`:
1. `resp.choices[0]` fuera del `try/except` -- una respuesta de API sin `choices` tumbaba el
   script entero en vez de ir a cola (mismo espíritu que la lección i21 de Demo 3, pero con un
   hueco real).
2. Cadena vacía `""` del modelo pasada tal cual a una columna `DATE`/`NUMERIC` -- Postgres la
   rechaza antes de que la validación importe. Se normaliza a `None` al parsear la extracción
   (`_sanear_numerico`).
3. El modelo devuelve `tipo_iva` como `"21%"` de forma sistemática (no aislada) pese a que el
   prompt pide número puro -- se quita el `%` antes de parsear (normalización de formato
   inequívoca, no juicio sobre un valor dudoso; mismo `_sanear_numerico`).
4. Distintos modelos devuelven las claves del JSON con variaciones de formato -- tildes espurias
   (`clienté_nif`) o sin guion bajo (`clientenif`) en vez de `cliente_nif` -- que con `.get()`
   perdían el campo en silencio sin que ninguna validación lo detectara (`cliente_nif`/
   `cliente_nombre` no pasan por `validar_nif`). Se normalizan tildes/guiones antes de leer el
   dict (`_sanear_claves`); una clave que cambia de PALABRA (`clientename` en vez de
   `cliente_nombre`) no se cubre a propósito -- adivinar el significado sería juicio, no formato.
5. `persistir_ok` indexaba el dict de extracción con `e["campo"]` en vez de `e.get("campo")` --
   un campo no validado (`cliente_nombre`/`cliente_nif`) ausente por el bug 4 rompía con
   `KeyError` sin capturar, y el caso ni siquiera quedaba en `extraccion_log` (viola "todo camino
   escribe extraccion_log", ver docstring del módulo). Visto en vivo con `dots-3` en r16.
6. El modelo devuelve `tipo_iva` como fracción (`"0.21"`) en vez de puntos porcentuales enteros
   (`"21"`), pese a que el prompt pide el número de puntos -- provoca un falso positivo de
   aritmética (`validar_aritmetica` espera `base×tipo/100`, con tipo=0.21 la cuota esperada sale
   ~100x menor que la real). En este dominio el IVA nunca es <1 punto (4/10/21), así que un valor
   entre 0 y 1 exclusive es inequívocamente la misma cifra mal escalada, no un tipo real distinto
   -- se reescala (`×100`) antes de validar (`_sanear_tipo_iva`), misma lógica de normalización de
   formato que el bug 3. Visto en vivo en r18 durante grabación del vídeo.

**Hallazgo real del caso "escaneo ruidoso" (f10):** se generó como imagen rasterizada + ruido
(sin capa de texto), no como PDF con texto degradado — confirmado que `pdfplumber.extract_text()`
devuelve cadena vacía sobre él. El grafo actual **no tiene fallback de OCR**: con un LLM real,
este caso dependería de que el modelo acepte imagen directamente (algunos de OpenRouter lo
hacen vía input multimodal; el prompt actual de `extraccion_llm` solo manda texto). Es un hueco
real del pipeline, no simulado — pendiente decidir si se resuelve con OCR (Tesseract/similar)
o mandando la imagen al modelo multimodal en vez del texto extraído.

## Buscado y descartado: facturas PDF españolas reales públicas

No existen en abierto. El canal oficial a la administración (FACe) exige XML Facturae, no PDF;
los portales de transparencia municipal publican datos agregados (proveedor/importe/concepto en
CSV) por Ley 19/2013, no el documento factura; los "portales del proveedor" municipales son de
subida, no de descarga pública. Decisión (2026-08-24): seguir solo con sintéticas.

## Lo que falta para cerrar §14.3

- Decidir el hueco de OCR/multimodal para escaneos ruidosos (arriba)
- Decidir si 83.3% es aceptable para el vídeo tal cual (con nota de fiabilidad de modelo gratis)
  o si se prueba un modelo de pago para la corrida de referencia
- Guion de vídeo / conexión al precio (§14.3 lo pide, aún no escrito)

## Para el vídeo: 3 ganchos visuales, cero UI nueva

- **Diagrama del grafo**: `python3 diagrama.py` escribe `grafo_facturas.mmd` (Mermaid). Pégalo en
  mermaid.live, Obsidian o un README de GitHub para abrir el vídeo con el pipeline dibujado. Se
  usó `draw_mermaid()` y no `draw_mermaid_png()` porque esta última pide red (mermaid.ink) o
  graphviz local; la de texto ya viene con langgraph.
- **Cola/panel en vivo**: Adminer ya corre en `../1/docker-compose.yml` (http://127.0.0.1:8082,
  servidor `postgres`, usuario/clave de `../1/.env`). Apunta a las vistas de `panel/panel.sql`
  (`v_cola_pendiente`, `v_importe_retenido`) y navega/graba ahí — no se construyó panel HTML
  propio, mismo criterio que las demos 1-3.
- **Escaneo ruidoso**: `generar_facturas.py` ahora conserva `facturas_pdf/f10.png` (antes se
  borraba tras montarlo en el PDF). Enséñalo junto a la fila de `f10` en `v_cola_pendiente`
  (motivo "confianza baja") — imagen con ruido → extracción degradada, el hueco de OCR en vivo.

## Cómo correrlo

```bash
# 1. Infraestructura ya debe estar arriba (docker compose de ../1/)
docker ps | grep 1-postgres-1

# 2. Esquema (una vez; docker-entrypoint-initdb.d no lo aplica solo, el volumen ya existe)
export PGPASSWORD=$(grep -m1 '^DB_POSTGRESDB_PASSWORD=' ../1/.env | cut -d= -f2-)
psql -h 127.0.0.1 -U n8n_user -d n8n -f init-facturas-tables.sql
psql -h 127.0.0.1 -U n8n_user -d n8n -f panel/panel.sql

# 3. Generar las facturas sintéticas (regenerable, semilla fija en generar_facturas.py)
python3 generar_facturas.py

# 4. Procesar. Sin clave (grafo/validación/gate/persistencia, sin llamar a ningún LLM):
export PGHOST=127.0.0.1 PGPORT=5432 PGDATABASE=n8n PGUSER=n8n_user
python3 procesar_facturas.py --sin-llm

# Con OPENROUTER_API_KEY y/o GEMINI_API_KEY reales en ../1/.env (prueba OpenRouter primero,
# cae a la API de Google directa si falla -- ver extraccion_llm en grafo_facturas.py):
python3 procesar_facturas.py

# Para repetir la medición de acierto real desde limpio (si no, los duplicados de una corrida
# anterior falsean el resultado -- solo datos demo, recreables con generar_facturas.py):
psql -h 127.0.0.1 -U n8n_user -d n8n -c "TRUNCATE TABLE facturas, cola_revision, extraccion_log RESTART IDENTITY;"

# 5. Evaluar contra la verdad de eval/dataset.jsonl
python3 eval/run_eval.py --dry-run   # smoke test estructural, sin tocar Postgres
python3 eval/run_eval.py             # contra los datos reales de Postgres
```

Dependencias nuevas sobre lo que ya usaban 1/2: `fpdf2` (generación de PDF sintético), `Pillow`
(rasterizado del escaneo ruidoso). `psycopg2-binary`, `langgraph`, `openai`, `pdfplumber`,
`requests` (fallback a la API de Google) ya estaban instalados. Sin `requirements.txt` a propósito —
mismo convenio que el resto del repo (falta de import → mensaje con el `pip install` exacto).
