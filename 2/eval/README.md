# eval/ — arnés de evaluación (Demo B, triage jurídico de fincas)

- `dataset.jsonl` — 45 incidencias etiquetadas a mano contra `rubrica-imputacion-fincas.md`.
- `run_eval.py` — compara la tabla `incidencias` (Postgres) contra `dataset.jsonl`.
- `rag_casos.jsonl` — 12 preguntas para probar el RAG de estatutos (aislamiento entre
  comunidades, sobre todo). `run_rag_eval.py` las ejecuta contra pgvector.
- `run_rag_eval.py` — consulta `documentos_comunidad` (pgvector) replicando el nodo `Cargar
  Estatutos de la Comunidad` de B1 y comprueba las 12 preguntas de `rag_casos.jsonl`. Mide
  **recuperación, no generación**: no hay ningún LLM redactando una respuesta, así que esto no
  dice nada sobre la calidad de la respuesta en prosa ni sobre si el sistema declara
  correctamente "no tengo información" ante una trampa — ver la cabecera del propio script para
  el detalle completo de qué mide y qué no, y de cómo replica la consulta real de B1.

## Orden de ejecución (triage)

1. `docker compose up -d` y cargar `init-fincas-tables.sql` + `seed-comunidades.sql`.
2. `python3 seed_incidencias.py` (envía los 45 correos por SMTP a `incidencias@fincas.local`).
   Usa `--delay 15` en una tirada completa (cuota 16.000 tokens/min, ~3.000 por caso).
3. Esperar a que n8n procese los correos (revisar la tabla `incidencias`).
4. `python3 eval/run_eval.py` — opciones: `--umbral-acierto` (0.85), `--dataset`, `--dsn`, `--dry-run`.
5. `python3 eval/calibrar_umbrales.py` — no evalúa, calibra: cruza la misma tirada con las etiquetas para responder si
   la confianza separa lo correcto de lo incorrecto, cuánto cierra el sistema con cada corte y quién causa de verdad
   los escalados de más. Se ejecuta después de `run_eval.py`, sobre los mismos datos.
6. `python3 eval/run_rag_eval.py` — independiente de los tres anteriores: no necesita ninguna tirada de correos, solo
   que B2 haya cargado los estatutos al índice.

## Qué mide cada sección

1. **Cobertura** — de los 45 casos, cuántos aparecen en `incidencias`. Falta = fallo, sin
   excepciones: **ninguna rama del sistema queda fuera de la tabla**. Los 3 correos sin
   comunidad identificable se registran con `comunidad_id` vacío y `decidido_por='compuerta'`,
   y los 5 no técnicos con `imputacion='no_aplica'`. Que una rama no dejara rastro era un fallo,
   no un diseño.
2. **Acierto de imputación** — global, y no ambiguos frente a ambiguos por separado; el
   segundo importa, porque cualquier sistema acierta lo fácil.
3. **Fundamento equivocado con imputación correcta** — bucket propio: acertar quién paga
   citando el artículo equivocado es un fallo, la cita es lo que cierra la discusión.
4. **Recall de plazos**, separado de falsos positivos — un plazo perdido es una derrama
   potencial; uno de más es solo una revisión de sobra. No se promedian.
5. **Escalados y discrepancias** — lo que decide si un caso acaba en una persona es la
   **acción**, no la vía. Se cuenta como escalado todo lo que sale con
   `accion='revision_administrador'`, más cualquier `decidido_por` que pare el automatismo
   (`umbral` / `estatutos` / `compuerta` / `humano`). Las dos correcciones que hicieron falta:
   contar solo `umbral`/`humano` marcaba i40–i42 como escaladas perdidas cuando el sistema había
   hecho justo lo que debía; y contar solo por vía marcaba i14, i36 e i39 como perdidas cuando
   las tres estaban en la cola con `decidido_por='sistema'` —el modelo no dudaba y no había
   cláusula, pero su imputación (`no_aplica`) no tiene automatismo asociado. Luego, escaladas de
   más y de menos contra `revision_esperada` (eje propio, no derivado
   de `ambiguo`: hay casos que exigen revisión sin ser ambiguos —una consulta administrativa,
   una humedad con antecedentes— y no hay forma de expresarlo con un solo campo), y la lista
   de discrepancias con su sección de rúbrica.

El `assert` final exige cobertura del 100 % de los 45 y acierto en no-ambiguos por encima del
umbral. Verificado con `--dry-run` (exit 0) y `--dry-run --umbral-acierto 0.999` (exit 1), y
contra el Postgres real con la tabla vacía: reporta 0 de 45 y sale distinto de cero en vez de
romperse con el conjunto vacío. Este arnés no lee `.env`; la contraseña se le pasa por entorno:

```bash
PGPASSWORD="$(grep -m1 '^DB_POSTGRESDB_PASSWORD=' ../1/.env | cut -d= -f2-)" python3 eval/run_eval.py
```

## Qué NO demuestra esta evaluación

- Las 45 etiquetas las puso una sola persona leyendo la rúbrica una vez, sin segunda revisión.
- 45 casos sintéticos no son la distribución real de ~350 incidencias/mes: aquí los casos
  difíciles están sobrerrepresentados a propósito, así que el acierto "global" no predice el
  acierto en producción.
- La evaluación mide acierto contra esta rúbrica, no contra la verdad jurídica absoluta: ella
  misma declara puntos discutibles (sección 7) defendibles con otro criterio igual de sólido.
- Un modelo que genera sus propias etiquetas y se evalúa contra ellas mide consistencia, no
  corrección — por eso el etiquetado es manual y anterior a cualquier ejecución del clasificador.

## RAG de estatutos (`run_rag_eval.py`)

Consulta `documentos_comunidad` (pgvector) replicando el nodo `Cargar Estatutos de la
Comunidad` de B1: misma tabla, mismo `topK=12`, mismo filtro de metadata por `comunidad_id`,
mismo operador de distancia coseno. No genera ninguna respuesta con LLM — mide retrieval, no
generación (ver la cabecera del script para el porqué y para el detalle exacto de la
replicación, incluida la reconstrucción del SQL real leído dentro del contenedor de n8n).

```bash
PGPASSWORD="$(grep -m1 '^DB_POSTGRESDB_PASSWORD=' ../1/.env | cut -d= -f2-)" python3 eval/run_rag_eval.py
```

Necesita embeddings de consulta (mismo modelo que usa B1, `gemini-embedding-001`) solo para la
comprobación adicional 3c (contraste sin filtro); el resto de aserciones —incluida la de
aislamiento, la que de verdad importa— funcionan sin ella porque `topK=12` ya cubre el 100% de
los fragmentos de cualquier comunidad en este corpus (12/8/11). Si quieres esa comprobación
extra, exporta `GEMINI_API_KEY` (documentada en `1/.env.example`); el script nunca lee `.env` ni
imprime la clave.

Qué comprueba cada aserción:

1. **Documento correcto** — la metadata ingerida no guarda nombre de fichero (solo
   `comunidad_id`/`documento`/`pagina`/`loc`), así que se reduce a "la consulta filtrada por
   `comunidad_id` devolvió al menos un fragmento", con la correspondencia comunidad↔fichero ya
   validada al cargar el dataset.
2. **Fragmento clave** — el texto de `fragmento_clave` (normalizado: minúsculas, sin tildes,
   espacios colapsados) aparece en algún fragmento recuperado. Los casos con `...` en
   `fragmento_clave` (elisión de quien escribió el caso, no texto literal) se parten en
   segmentos y se exige que todos aparezcan en el mismo fragmento.
3. **Aislamiento — la que importa.** Dos partes: 3a replica el filtro SQL de B1 (guardia de
   regresión: por construcción no debería poder fallar si el filtro sigue puesto); 3b busca cada
   `fragmento_clave` en las 31 filas de las tres comunidades SIN filtro y comprueba en qué
   comunidad(es) aparece de verdad — esta es la que puede detectar una fuga real, y no necesita
   embeddings. Un fallo aquí en los pares de fuga (r01/r02, r03/r04) se reporta como fallo grave
   explícitamente.
4. **Trampas** (`respondible: false`) — `documento_esperado`/`clausula_esperada`/
   `fragmento_clave` son `null` en los dos casos trampa (r11, r12), así que no hay contenido
   específico que comprobar como ausente. Lo que sí se comprueba es que la *premisa* de la
   trampa sigue siendo cierta: que términos como "aseguradora"/"póliza" (r11) o "decenal" (r12)
   —extraídos de la propia `pregunta`— siguen ausentes del corpus.

El `assert` final exige cobertura de los 12 casos, cero fallos de aislamiento (3a y 3b, sin
umbral: es zero-tolerance) y acierto documento+fragmento por encima de `--umbral-acierto`
(0.85 por defecto). Verificado con `--dry-run` (exit 0) y `--dry-run --umbral-acierto 0.95`
(exit 1); contra el Postgres real con un `comunidad_id` inexistente y con una tabla vacía
(temporal, sin tocar `documentos_comunidad`): reporta 0 resultados y no lanza excepción.

### Qué NO demuestra esta evaluación

- No mide la calidad de la respuesta redactada por el LLM del chat: no hay generación en este
  arnés, solo retrieval directo contra pgvector.
- No mide si el sistema declara correctamente "no tengo información suficiente" ante una
  trampa — eso también es generación. Solo comprueba que la trampa sigue siendo trampa (la
  respuesta no está en el corpus).
- Con el corpus actual (12/8/11 fragmentos por comunidad, `topK=12`), la consulta filtrada
  devuelve siempre el 100% de los fragmentos de la comunidad, haya o no relevancia semántica: las
  aserciones 1/2/3a no ejercitan la calidad del ranking, solo existencia y etiquetado. Si el
  corpus crece por encima de 12 fragmentos en alguna comunidad, esto deja de ser cierto y la
  fidelidad del embedding real empieza a importar de verdad.
- El fixture asume que cada `fragmento_clave` es texto exclusivo de su comunidad, y r06 no lo
  es: la frase de contacto de la administradora ("Gestión Ficticia de Fincas, S.L., con
  domicilio a efectos de notificaciones en administracion@ejemplo.com") es byte-idéntica en las
  tres comunidades (comprobado con grep sobre `comunidades/*.md`). r06 no es un par de fuga
  diseñado, pero para ese caso concreto "el fragmento correcto volvió" no distingue aislamiento
  correcto de una fuga: el mismo texto habría vuelto igual con el filtro apuntando a la
  comunidad equivocada. `run_rag_eval.py` lo señala en su salida como hallazgo del fixture, no
  como fallo — el filtro SQL sigue haciendo su trabajo, es la pregunta la que no es exclusiva.
