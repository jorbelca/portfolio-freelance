# Demo 6 — Agente de reclamaciones de consumo (ejemplo EU261)

Agente del lado del pasajero que calcula la indemnización máxima a la que tiene derecho por un
retraso de vuelo, refuta la excusa de la aerolínea citando la jurisprudencia del TJUE y redacta
la reclamación. **El importe y la elegibilidad salen de un motor de reglas determinista, nunca
del modelo** — el LLM solo lee el relato libre del usuario y elige una categoría de causa.

Distinta a las Demos 1-5: no clasifica ni recupera, **aplica un reglamento y computa un
resultado** (€ + artículo). Sin RAG, sin pgvector, sin LangGraph — es un bucle de
function-calling. Ver `PLAN-demo6.md` para el porqué y el encuadre comercial (demo B2B, no
producto B2C).

---

## 0. Cómo usar este README (contrato para agentes)

Este fichero es el documento de trabajo. Reglas de operación, no decorado:

1. **Antes de tocar código**, lee §2 (defectos abiertos) y §3 (gates). Si tu tarea colisiona con
   un defecto abierto, arregla el defecto o anota por qué no.
2. **Los gates del §3 son bloqueantes.** Un gate `ABIERTO` prohíbe la acción que bloquea. No se
   cierra por criterio propio: se cierra escribiendo evidencia (fuente + fecha) en su fila.
3. **Nunca cierres un gate jurídico sin fuente primaria.** EUR-Lex (texto consolidado) o el texto
   de la sentencia en curia.europa.eu. "Lo recuerdo así" no es evidencia; esa es exactamente la
   deuda que abrió §2.
4. **Al cerrar cualquier ítem**, edita su fila aquí mismo (estado + fecha + fuente) en el mismo
   commit que el código. README desincronizado = ítem no cerrado.
5. **Números públicos** (vídeo, LinkedIn, propuesta): solo los que §4 autoriza, con la redacción
   literal que allí se indica. Un número sin gate cerrado detrás no sale del repo.
6. **Alcance**: si vas a añadir pgvector, RAG, rúbrica de clasificación, LangGraph o n8n, para.
   §11 de `PLAN-demo6.md` los excluye a propósito.
7. Marca simplificaciones deliberadas con comentario `ponytail:` que nombre el techo y la vía de
   ampliación, como en `aeropuertos.py`.

---

## 1. Estado

**2026-09-08 — núcleo determinista + eval + verificación jurídica: hecho. `D1`–`D6`
cerrados/mitigados. `G-EVAL-REAL` cerrado (94 / 91 / 100). `G-JURIDICO` cerrado: Reglamento y 9
sentencias cotejados contra su texto en EUR-Lex (§6). `G-CODIGO` cerrado. Quedan gates no
técnicos: `G-NUMEROS` (redacción del copy), `G-MERCADO` (conversaciones con compradores) y el
entregable en sí (guion, grabación, publicación).**

- `aeropuertos.py` — ~65 aeropuertos IATA con coordenadas, país y ámbito territorial del
  Reglamento (Canarias/Madeira/Islandia/Suiza dentro; UK fuera).
- `reglas.py` — motor EU261: **ámbito del art. 3(1)** (salida UE / entrante de 3.er país solo
  con transportista comunitario / UK fuera), distancia gran círculo, bandas del art. 7(1),
  reducción del art. 7(2), umbral de 3 h (Sturgeon), plazo por país. Autocheck: `python3 reglas.py`.
- `precedentes.py` — tabla del art. 5(3) contra 13 categorías de causa. **D2**: las alegaciones
  típicas de la aerolínea (meteo, huelga ATC, seguridad, cierre) van `exime=None` → reclamación
  provisional con exigencia de prueba, no concesión de oficio.
- `test_reglas.py` — 9 bloques de asserts (incluye ámbito del art. 3). `python3 test_reglas.py`.
- `eval/generar_dataset.py` → `eval/dataset.jsonl` — **33** casos con ground truth escrito a
  mano (no deriva del motor; ver la advertencia de §4). +3 casos de ámbito del art. 3.
- `eval/run_eval.py --sin-llm` — inyecta los hechos del dataset en el motor: **33/33**.

**Día X (2026-09-09) — bucle de agente + carta + log + eval real: hecho.**

- `llm.py` — cliente de modelo (patrón de la Demo 5). `entorno.py` carga `../1/.env`.
- `interpretar.py` — **único punto de juicio del modelo**: relato libre → hechos + categoría
  de causa (lista cerrada). No ve importes ni artículos.
- `carta.py` — **`D3` cerrado**: `clasificar_plantilla()` elige el tipo de carta de forma
  determinista; un dictamen `provisional` produce la plantilla que pide acreditación primero,
  nunca una exigencia de pago firme. El modelo solo redacta 2 párrafos de prosa.
- `decision_log.py` — JSONL append-only, una línea por caso en todos los caminos.
- `agente.py` — glue lineal (no grafo). `python3 agente.py "<relato>" [--html|--pdf]`. Autocheck sin modelo.
- `test_carta.py` — 6 bloques, cierra `D3` con check ejecutable.
- `eval/run_eval.py` **modo real** — 3 números sin promediar (categoría / elegibilidad / importe).
- `vista.py` **hecho 2026-09-08** — `render_html()` (UI del §5: burbujas de chat + carta con
  `@media print`) y `generar_pdf()` (Chrome headless, sin dependencia nueva; el importe lo pone
  `carta.py`, no la vista). Autocheck `python3 vista.py`. Cierra los dos pendientes de PDF y UI.
- `servidor.py` **hecho 2026-09-08** — UI: `http.server` de la stdlib, sin framework ni build.
  `./correr.sh --ui` → http://127.0.0.1:8060. Enseña el reparto en 3 etapas: **1 Relato** →
  **2 Hechos extraídos** (badge «modelo · único punto de juicio») → **3 Dictamen** (badge «motor
  determinista · 0 llamadas al modelo»): veredicto, derivación auditable (distancia → banda →
  importe → déficit vs. oferta) y tarjeta de refutación de la excusa con la sentencia. Dos
  entradas: «Relato libre» (modelo) y «Datos del vuelo» (se inyectan al motor → render
  instantáneo, funciona con el proveedor caído). Cabecera con el modelo configurado
  (`RECLAMACIONES_MODELO` · host); sin clave → solo modo «Datos del vuelo». Carta con **copiar**
  (`navigator.clipboard`), imprimir/PDF (patrón `@media print` de `vista.py`, `display:none`, sin
  `visibility:hidden`) y **huecos entre `[corchetes]`** resaltados que rellena el usuario (nombre,
  localizador, IBAN…). Autocheck `python3 servidor.py --check` (asserts sobre `payload()`, sin red).
  - Cambios de apoyo: `carta.py` mete los datos personales como `[corchetes]` (cabecera + firma;
    `_ensamblar()` en vez de `textwrap.dedent`) y el prompt del cuerpo tiene instrucción de no
    inventarlos; `reglas.py` expone `nota_precedente`/`causa_categoria` en el dictamen;
    `llm.ultimo_modelo()`/`proveedor()` para que la UI no mienta sobre qué respondió (reserva
    incluida); `agente.procesar(carta_llm=…)` para saltar la redacción con modelo; `agente._a_hechos`
    descarta `pais_reclamacion` nulo del modelo (pisaba el «ES» por defecto y disparaba
    `plazo_incierto`).

**Pendiente (entregable + gates no técnicos):**

- ~~Anotar el número del modo real en §4~~ — hecho 2026-09-08, `G-EVAL-REAL` cerrado (94 / 91 / 100).
- ~~Verificación jurídica del §6 (`G-JURIDICO`)~~ — hecho 2026-09-08, cotejado contra EUR-Lex.
- Guion + grabación del vídeo (§8 de `PLAN-demo6.md`); publicar en LinkedIn + Upwork (`G-NUMEROS`).
- `G-MERCADO`: 2-3 conversaciones con compradores de cola larga.

---

## 2. Defectos del motor

Ordenados por lo que rompen. `D1`–`D3` bloqueaban el gate `G-CODIGO` (§3).
Estado a 2026-09-08: `D1`–`D6` corregidos en código; `G-JURIDICO` confirma que la aritmética no
cambia; `G-CODIGO` **cerrado**.

### D1 — Art. 3: ámbito de aplicación no comprobado · CERRADO (código, 2026-09-08) · pendiente V2 en §6

`reglas.py` no comprueba dirección del vuelo ni nacionalidad del transportista. El Reglamento
cubre **salidas desde un aeropuerto UE con cualquier compañía**, pero **llegadas a la UE desde un
tercer país solo si el transportista operador es comunitario** (art. 3(1)). Hoy `en_ue()` solo
alimenta la banda de distancia, y `Hechos` no tiene campo de transportista: **JFK→MAD operado por
Delta devuelve importe pagable**, que es falso.

Por qué importa más de lo que parece: el caso del vídeo (MAD→JFK) sale de la UE, así que el fallo
**no se ve en la demo** — sobrevive hasta la primera prueba real de un comprador del vertical, que
es el peor sitio donde puede aparecer.

Arreglo (~10 líneas): campo `transportista_comunitario: bool | None` en `Hechos`; gate de
elegibilidad antes de calcular banda; motivo explícito cuando queda fuera de ámbito; si el dato
falta en un vuelo entrante desde tercer país, tratar como **dato obligatorio que el agente debe
preguntar**, no asumir. Añadir al dataset ≥1 caso entrante no-UE no cubierto y ≥1 entrante con
transportista comunitario sí cubierto.

**Cerrado 2026-09-08** (`reglas.py`): función `en_ambito_261()` como paso 0 de
`evaluar_elegibilidad`; salida `en_ambito: True|False|None` + `falta_dato`; `None` en vuelos
entrantes sin dato de transportista (el agente lo preguntará). Dataset: c31 (entrante no
comunitario → fuera), c32 (entrante comunitario → 600 €), c33 (sin dato → `falta_dato`).
`test_reglas.py` bloque 9. Pendiente: verificar la redacción exacta del art. 3(1) contra
EUR-Lex (§6 V2).

### D2 — Meteorología concede la excusa de la aerolínea por defecto · CERRADO (código, 2026-09-08)

`precedentes.py` mapea `meteorologia → exime=True`. Una herramienta **del lado del pasajero** está
concediendo automáticamente la excusa más usada por la aerolínea. El art. 5(3) pone la carga de la
prueba en el transportista, y la propia nota de la entrada ya dice "si la aerolínea acredita el
nexo causal y que adoptó medidas razonables" — es decir, el código afirma lo que su propia nota
condiciona.

Arreglo: `meteorologia → exime=None` (provisional, carga en la aerolínea), con nota que exija la
documentación acreditativa. Revisar con el mismo criterio `huelga_atc`, `riesgo_seguridad` y
`restriccion_administrativa`: son alegaciones del transportista, no hechos probados. Esto cambia
el producto (lo hace coherente con el encuadre adversarial del §2 de `PLAN-demo6.md`), no una fila
de tabla.

**Cerrado 2026-09-08** (`precedentes.py`): `exime=None` para `meteorologia`, `huelga_atc`,
`riesgo_seguridad`, `restriccion_administrativa`, `problema_medico_pasajero` (esta además con
cita frágil, ver §6). Se conserva `exime=True` solo para hechos puntuales y verificables
(`decision_atc` ATFM, `colision_ave`, `sabotaje`, `defecto_fabrica_oculto`) y el motivo de esos
casos invita igualmente a exigir la prueba. Dataset: c09/c10/c12/c14 pasan a provisional con
importe completo; c11/c13 siguen no elegibles.

Citas revisadas el 2026-09-08 (detalle y arreglos en §6): `huelga_atc` → Krüsemann/C-28/20 *a
contrario* para huelgas externas; `problema_medico_pasajero` → sin cita al TJUE (C-74/19 es
sobre pasajero violento, no médico); `restriccion_administrativa` → C-159/18 (Moens) / C-12/11
(McDonagh); `defecto_fabrica_oculto`/`sabotaje` → excepción expresa de van der Lans, no "a
contrario".

### D3 — `provisional` no bloquea nada · CERRADO (código, 2026-09-09)

Con causa `desconocida`, `evaluar_elegibilidad` devuelve `elegible=True` con importe completo; la
cautela vive solo en la prosa de `motivo`. §13.7 de `PLAN-demo6.md` promete que el dictamen nunca
afirma un importe firme sobre una causa dudosa: hoy esa promesa es un string.

Arreglo: `clasificar_plantilla()` decide el tipo antes de redactar; `provisional` → plantilla que
pide documentación, nunca exigencia firme. `vista.generar_pdf` imprime esa carta tal cual (no
reescribe importes), así que hereda la garantía. Assert en `test_carta.py` que falla si un
dictamen provisional produce carta con `EXIGENCIA_FIRME`.

**Cerrado 2026-09-09** (`carta.py`): `clasificar_plantilla(dictamen)` → uno de
`{fuera_ambito, falta_dato, sin_derecho, provisional, firme}`, determinista. La línea de
petición la construye el código (no el modelo); la frase de exigencia firme
(`"le requiero el abono de"`) solo existe en la plantilla `firme`. `test_carta.py` bloque 2
recorre las 5 categorías provisionales y verifica que la carta NO contiene esa frase y SÍ pide
la acreditación primero. El modelo solo redacta 2 párrafos de prosa y tiene prohibido mencionar
cifras en el prompt.

### D4 — Art. 9 medido sobre la variable equivocada · CERRADO (código, 2026-09-08)

`asistencia_art9 = retraso_llegada_h >= 2.0`. El art. 6 fija el derecho de asistencia por retraso
**en la salida**, con umbrales por banda de distancia (2 h / 3 h / 4 h), no por retraso a la
llegada y no plano. Dos errores en un solo campo.

Arreglo: usar retraso en salida y umbral por banda, o —si el MVP no recoge la hora de salida— dejar
el campo fuera del dictamen y mencionar el art. 9 solo cualitativamente en la carta. No inventar.

**Cerrado 2026-09-08** (`reglas.py`): campo `asistencia_art9` eliminado del dictamen. El MVP no
recoge la hora de salida; la carta mencionará el art. 6/9 cualitativamente. `test_reglas.py`
comprueba que el campo ya no aparece.

### D5 — Art. 7(2): la reducción se aplica sin verificar que hubo reruteo del art. 8 · MITIGADO (2026-09-08); base jurídica cerrada

`_aplicar_reduccion` se dispara con el flag `hubo_reruteo`. El art. 7(2) exige oferta de transporte
alternativo bajo el art. 8; un vuelo simplemente retrasado (mismo vuelo, más tarde) no es reruteo.
Riesgo: rebajar al pasajero un 50 % regalándole a la aerolínea un argumento que no le corresponde
— mismo vicio que `D2`, en la otra dirección.

Arreglo: documentar en el docstring qué cuenta como reruteo, y que el agente lo pregunte de forma
que distinga "me pusieron en otro vuelo" de "el mismo vuelo salió tarde".

**Mitigado 2026-09-08** (`reglas.py`): docstring de `_aplicar_reduccion` explícito sobre qué es
reruta (art. 8) y qué no; comentario en `Hechos.hubo_reruteo`.

**Base jurídica cerrada** (`G-JURIDICO`, §6): Sturgeon C-402/07 § 63 confirma expresamente que la
reducción del 7(2) se aplica *mutatis mutandis* al retraso (banda (c): ventana de 3 a 4 h). No es
un forzamiento. Lo que queda abierto NO es jurídico sino de captación de datos: el agente debe
preguntar el reruteo de forma que distinga "me pusieron en otro vuelo" de "el mismo vuelo salió
tarde". El motor ya solo aplica la reducción con el flag `hubo_reruteo` activo.

### D6 — Sin UK261 · MANEJADO (2026-09-08, fuera de MVP)

UK aplica desde el Brexit su propio régimen (importes en libras). `aeropuertos.py` marca los
aeropuertos GB como fuera de la UE, que es correcto para el art. 3, pero el sistema no dice nada
del régimen británico. Decisión: **fuera del MVP**, declarado aquí y en la carta cuando el vuelo
toque UK. No implementar sin decidirlo explícitamente.

**Manejado 2026-09-08** (`reglas.py`): `en_ambito_261()` devuelve `False` para vuelos con
salida desde UK y el motivo nombra UK261 explícitamente. Vuelos con **salida desde la UE con
destino UK** siguen cubiertos por 261/2004 (correcto). UK261 no se implementa. `test_reglas.py`
bloque 9.

---

## 3. Gates

Bloqueantes. Estado, quién lo cierra y con qué evidencia. **No cerrar sin escribir la fuente y la
fecha en la fila.**

| Gate | Bloquea | Condición de cierre | Estado |
|---|---|---|---|
| `G-CODIGO` | grabar el vídeo | `D1`, `D2` y `D3` cerrados; `python3 test_reglas.py` y `eval/run_eval.py --sin-llm` en verde tras el cambio | **CERRADO 2026-09-08** — `D1`+`D2`+`D3` cerrados; `G-JURIDICO` confirma que la aritmética del motor no cambia; `test_reglas.py` 9 bloques, `test_carta.py` 7 bloques, `--sin-llm` 33/33 tras los arreglos de cita y de plazos |
| `G-JURIDICO` | grabar el vídeo | todas las filas del §6 con fuente primaria + fecha | **CERRADO 2026-09-08** — V1–V3 contra el texto del Reglamento en EUR-Lex (CELEX 32004R0261); V4–V9 contra el texto de cada sentencia en EUR-Lex (parte dispositiva). Detalle fila por fila en §6, con 4 caveats residuales documentados (medical sin TJUE, plazos por ley nacional, conexiones no implementadas, inciso art. 3(1)(b) in fine) |
| `G-EVAL-REAL` | anunciar el número del vídeo | `eval/run_eval.py` modo real ejecutado sobre los 33 relatos SIN errores de proveedor, con los tres números anotados en §4 | **CERRADO 2026-09-08** — corrida limpia vía OpenRouter (`nvidia/nemotron-3-super-120b-a12b:free`, reserva `openrouter/free`): 33/33, 0 errores de proveedor. **categoría 31/33 (94 %) · elegibilidad 30/33 (91 %) · importe 33/33 (100 %, condicionado a elegible=True)**. Hizo falta: retry ante JSON no parseable en `interpretar.py`, retry+backoff ante cualquier `APIError` y modelo de reserva en `llm.py`, y nombrar los hubs en el prompt. Corrida en `eval/corrida_2026-09-08d_openrouter.txt`. Repetible: la corrida (b) dio 94/91/100 idéntico |
| `G-NUMEROS` | publicar (vídeo, LinkedIn, Upwork, propuesta) | toda cifra pública usa la redacción autorizada del §4 | **ABIERTO** |
| `G-MERCADO` | invertir más allá de la pieza de portfolio | gate del §12 de `PLAN-demo6.md`: evidencia fechada de que un comprador **paga** | **NO SE PERSIGUE (2026-09-08)** — decisión K: sin Connects, sin outreach. La demo queda como pieza de portfolio (señal de perfil); no se invierte en ampliarla. Evidencia de mercado recogida (no de venta): forma de demanda del feed de Upwork, ~30 posts, el tier premium ($7K–100K+ gastados) pide el reparto modelo/determinista de forma explícita — ver `PLAN-demo6.md` §1. |

Regla de escape (§10 de `PLAN-demo6.md`): si el jueves va justo, se recorta el análisis del
art. 5(3), **nunca** `G-JURIDICO` ni `G-NUMEROS`. Se graba con menos alcance, no con menos verdad.

---

## 4. Qué se puede afirmar en público (y cómo)

El `33/33` de `--sin-llm` mide **consistencia interna** (motor vs ground truth escrito por la
misma persona). La **corrección jurídica** se verifica aparte: §6, cerrado el 2026-09-08 contra
el texto del Reglamento y de las 9 sentencias en EUR-Lex.

| Afirmación | Autorizada | Redacción |
|---|---|---|
| `--sin-llm` 33/33 | sí, con matiz | "el motor coincide con el ground truth en 33/33; la base jurídica se verifica aparte (§6)" |
| "las reglas del motor se apoyan en el texto del Reglamento y de la jurisprudencia del TJUE" | **sí** (`G-JURIDICO` cerrado) | "art. 7 (bandas e importes), art. 3 (ámbito), art. 5(3) y el umbral de 3 h (Sturgeon C-402/07) cotejados contra su texto en EUR-Lex — ver §6. Alcance: vuelo directo, sin conexiones; los plazos de prescripción los fija el Derecho nacional" |
| "cumple EU261" / "acierta la ley" a secas | **no** | demasiado absoluto: hay 4 caveats en §6 (medical sin TJUE, plazos nacionales, conexiones, art. 3(1)(b) in fine). Usar la redacción de la fila anterior |
| número del modo real | sí (`G-EVAL-REAL` cerrado), con matiz | tres números SIN promediar: "sobre 33 relatos libres, el modelo clasifica la causa bien en 31 (94 %), acierta la elegibilidad en 30 (91 %) y, cuando hay derecho, el importe en 33/33". Matiz obligatorio: (a) mide extracción del modelo, no corrección jurídica (eso es `G-JURIDICO`); (b) el 100 % de importe está condicionado a los casos elegibles; (c) los 3 fallos de elegibilidad son casos de prescripción donde el modelo no extrajo la fecha del vuelo. Modelo: `nvidia/nemotron-3-super-120b-a12b:free` (nombrarlo) |
| "no lo hace nadie" | **no** | §5.1 de la nota de demos ya obligó a retractar una premisa así |
| compradores del §1 del PLAN | como hipótesis | "hipótesis sin verificar; gate del §12 abierto" |

---

## 5. Recortes de alcance decididos

Para que `G-JURIDICO` —la única tarea que no se puede fingir— no quede detrás de infraestructura:

- **`decision_log` en JSONL, no en Postgres.** Se conserva el principio (toda decisión computada
  queda registrada con el artículo/regla que la produjo, como `aplicar_rubrica` en la Demo 5); se
  quita Docker y `psycopg2`. Declarado aquí para que no se lea como descuido.
- **UI**: `servidor.py` — chat local sobre `http.server` de la stdlib (`./correr.sh --ui`,
  http://127.0.0.1:8060). Envías el relato, ves el dictamen (importe + artículo del motor,
  distancia gran círculo, motivo, sentencia) y la carta con botón de imprimir/PDF. Sin framework
  ni build. `vista.render_html()` sigue existiendo para el HTML estático embebible. El vídeo
  enseña el motor, la cita y el eval — no el chat.
- **El PDF no se recorta**: es el desenlace del guion del §8. `vista.generar_pdf()` imprime la
  carta con Chrome headless — el mismo `.html` de la UI, con `@media print`. Sin dependencia
  nueva (se descartó `reportlab`).

Encuadre del vídeo (riesgo real, no estético): EU261 es el ejemplo de juguete más repetido del
legal-tech con IA. Ventaja: cero educación del comprador en 90 s. Riesgo: que la pieza se lea como
marketing de AirHelp, que es el modo de fallo que §11 de la nota de demos tuvo que retractar. Por
eso el beat de discrepancia debe enseñar en pantalla `analizar_circunstancia` devolviendo *no
exime* con la cita y el eval, no una burbuja de chat con un número.

---

## 6. Verificación jurídica (`G-JURIDICO`)

**Estado 2026-09-08: CERRADO.** Cada ítem cotejado contra fuente primaria: el texto de la
sentencia en EUR-Lex (parte dispositiva / *operative part*) y el texto del Reglamento en EUR-Lex
(CELEX 32004R0261, `legal-content/EN/TXT/HTML/?uri=CELEX:32004R0261`). 261/2004 no ha tenido
reforma sustantiva de los arts. 3/5/6/7 a nivel UE, así que ese texto es el vigente.

| # | Ítem | Fuente primaria (EUR-Lex) | Resultado — coincide con el motor |
|---|---|---|---|
| V1 | Art. 7(1) bandas / 7(2) reducción / 7(4) gran círculo | CELEX 32004R0261, art. 7 | **Literal.** 250 € ≤1500 km; 400 € intra >1500 km y demás 1500–3500; 600 € resto. Umbrales 7(2): 2/3/4 h por banda. 7(4): "great circle route method". Sturgeon § 63: la reducción del 7(2) se aplica *mutatis mutandis* al retraso. |
| V2 | Art. 3(1)(a)/(b) ámbito (`D1`) | CELEX 32004R0261, art. 3(1) + C-257/14 §§ 21-28 | **Literal.** (a) salida de un Estado miembro → cubierto con cualquier compañía; (b) entrada desde tercer país → solo si el transportista operador es comunitario. Gap conocido, favorable al pasajero: el motor no aplica el inciso "salvo que recibiera compensación/asistencia en el tercer país" (C-257/14 § 28 lo interpreta de forma estricta contra la aerolínea). |
| V3 | Art. 5(3) + considerandos 14 y 15 | CELEX 32004R0261 | **Literal.** Considerando 14 enumera: inestabilidad política, meteo incompatible con el vuelo, riesgos para la seguridad, deficiencias inesperadas de seguridad del vuelo, huelgas que afecten a la operación del transportista. Considerando 15: decisión de gestión de tráfico aéreo (ATFM) sobre una aeronave concreta un día concreto. El art. 5(3) dice "cancelación"; su aplicación al retraso pasa por Sturgeon (C-402/07 § 69) y Nelson. |
| V4 | Umbral 3 h a la llegada | **C-402/07 y C-432/07** (Sturgeon), CELEX 62007CJ0402, fallo 2 | **Confirmado.** "loss of time equal to or in excess of three hours, that is, where they reach their final destination three hours or more after the arrival time originally scheduled". Corroborado en Nelson C-581/10 (citado en C-315/15 § 19, C-559/16 §§ 20-22). |
| V5 | Fallo técnico / defecto oculto de fábrica / sabotaje | **C-549/07** (Wallentin-Hermann) §§ 24-26 + fallo 1; **C-257/14** (van der Lans) §§ 37-38, 44 + fallo | **Confirmado.** Mantenimiento / avería prematura NO es extraordinario. C-549/07 § 26 y C-257/14 § 38 **enuncian expresamente** las excepciones: (i) defecto oculto de fábrica revelado por el fabricante o una autoridad competente; (ii) daño por sabotaje o terrorismo. |
| V6 | Huelga de personal propio / huelga externa (ATC) | **C-195/17** (Krüsemann) §§ 40-45 + fallo; **C-28/20** (Airhelp/SAS) §§ 28-44 + fallo | **Confirmado.** Huelga salvaje tras anuncio de reestructuración (C-195/17) y huelga sindical lícita por demandas salariales (C-28/20) = inherentes a la actividad, NO eximen. C-28/20 §§ 42-43: las huelgas "externas" (controladores aéreos, personal de aeropuerto) SÍ pueden ser circunstancia extraordinaria. |
| V7 | Colisión con ave | **C-315/15** (Pešková) §§ 24-26 + fallos 1, 2 y 4 | **Confirmado.** Colisión con ave = extraordinaria, cause o no daño (fallo 1). Una segunda inspección innecesaria no cuenta (fallo 2). Del retraso total solo se descuenta la parte imputable a la circunstancia (fallo 4). |
| V8 | Distancia con conexión | **C-559/16** (Bossen) §§ 29-33 + fallo | **Confirmado.** "the distance calculated between the first point of departure and the final destination on the basis of the 'great circle' method, regardless of the distance actually flown". |
| V9 | Plazo = Derecho nacional | **C-139/11** (Cuadrench Moré) §§ 25-29 + fallo | **Confirmado.** "the time-limits for bringing actions for compensation under Articles 5 and 7 ... are determined in accordance with the rules of each Member State on the limitation of actions". Varsovia/Montreal (plazo bienal) NO se aplican (§§ 28-29). |

**Arreglos hechos en esta verificación (2026-09-08, mismo commit que este README):**

- `precedentes.py` — `problema_medico_pasajero`: **retirada la cita a C-74/19**. C-74/19 (TAP) es
  sobre un **pasajero violento** (mordió y agredió a la tripulación), no urgencia médica. No hay
  holding del TJUE sobre desvío médico; queda `exime=None` con nota honesta. **Caveat residual
  aceptado**: esta categoría se apoya en jurisprudencia nacional dividida, no en el TJUE.
- `precedentes.py` — `defecto_fabrica_oculto` / `sabotaje`: la excepción está **enunciada
  expresamente** en C-549/07 § 26 y C-257/14 § 38, no "a contrario". Reformuladas.
- `precedentes.py` — `huelga_atc`: citada ahora **C-28/20 §§ 42-43** (huelga externa SÍ puede
  eximir). Sigue `exime=None` porque la aerolínea conserva la carga de probar el nexo con este
  vuelo y las medidas razonables.
- `precedentes.py` — `restriccion_administrativa`: citada ahora C-159/18 (Moens), C-501/17
  (Germanwings), C-12/11 (McDonagh) en vez del considerando 14, que no menciona cierres.
- `reglas.py` — **plazos**: solo `PLAZO_FIABLE = {ES, FR, DE, GB}` (Derecho nacional + práctica
  asentada) emiten dictamen firme de "fuera de plazo". El resto **no descarta la reclamación**:
  `dentro_plazo=None`, `plazo_incierto=True` y aviso en el `motivo`. Antes IT/BE se apoyaban en un
  plazo de Montreal que C-139/11 declara inaplicable, y `PLAZO_ANOS_DEFECTO=2` cortaba de raíz
  20+ países. Tests: `test_reglas.py` bloque 7, `test_carta.py` bloque 5b (la carta a la
  aerolínea NO menciona la posible prescripción).

**Caveats residuales aceptados (documentados, no bloqueantes):**

1. `problema_medico_pasajero` — sin sentencia TJUE; `exime=None` (provisional) es la postura
   conservadora del lado del pasajero.
2. Plazos ES/FR/DE/GB — se apoyan en ley nacional + jurisprudencia nacional asentada, **no en el
   TJUE** (el TJUE solo dice "lo fija el Derecho nacional"). GB = Inglaterra y Gales (Limitation
   Act 1980 s.5, 6 años); Escocia son 5 (Prescription and Limitation (Scotland) Act 1973) — el
   motor usa un único valor de 6.
3. El motor asume vuelo directo. Para conexiones hay que llamar a `distancia_km` con
   (primer_origen, destino_final) — C-559/16. No implementado en el MVP.
4. `en_ambito_261` no modela el inciso in fine del art. 3(1)(b) (ver V2).

Pendientes no jurídicos que siguen abiertos: ancla de precio (postings de "EU261" / "flight claim
automation" en Upwork/Malt, anotar rango observado) y el estado de publicación de la Demo 5 en
LinkedIn/Upwork.

---

## 7. Ejecutar

```bash
python3 reglas.py                    # autocheck del motor
python3 test_reglas.py               # tests del motor (9 bloques)
python3 test_carta.py                # tests de la redacción (cierra D3)
python3 agente.py                    # autocheck del glue (modo inyectado, sin modelo)
python3 eval/generar_dataset.py      # regenera dataset.jsonl (determinista)
python3 eval/run_eval.py --sin-llm   # mide el motor contra el ground truth (33/33)
python3 agente.py "Madrid-Nueva York, 4h de retraso, problema técnico, me ofrecen 250€"
python3 eval/run_eval.py             # modo real: necesita clave de modelo (../1/.env)
python3 eval/run_eval.py --limite 5  # modo real, primeros 5 (prueba rápida)
```

Dependencias: `openai` (cliente de modelo, ya instalado). El PDF sale de `vista.generar_pdf()`
vía Chrome headless (sin dependencia Python). `agente.py --html` deja `cartas/<id>.html`,
`--pdf` deja también `cartas/<id>.pdf`; sin flags, la carta se escribe en texto plano.
Variables de entorno: `entorno.py` carga `../1/.env` automáticamente; ver `.env.example`.

---

## 8. Avisos

- **El articulado está verificado, con caveats.** `reglas.py` y `precedentes.py` se cotejaron el
  2026-09-08 contra el texto del Reglamento (CE) nº 261/2004 y de 9 sentencias del TJUE en EUR-Lex
  (§6). Quedan 4 caveats residuales documentados (medical sin TJUE, plazos por Derecho nacional,
  conexiones no implementadas, art. 3(1)(b) in fine). Ninguna salida de este repo es asesoramiento
  jurídico: es una demo de capacidad técnica.
- **Actividad potencialmente regulada.** Dirigido al consumidor final sería asesoramiento jurídico.
  Como herramienta B2B vendida a un despacho o agencia, el encuadre y la responsabilidad son del
  comprador. Debe quedar dicho también en la propuesta comercial, no solo aquí.
- **Datos sintéticos.** El dataset prueba capacidad técnica. No prueba demanda ni conversión: eso
  es `G-MERCADO`.
