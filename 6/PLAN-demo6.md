# Plan Demo 6 — Agente de reclamaciones de consumo (ejemplo EU261)

**Elegido el 2026-09-07 (W37)** como proyecto nuevo distinto a la Demo 5. Supera la idea previa
de "Demo 6 = reporting periódico" (§14.5 de `demos-portfolio-exposicion-2026`): esa era una pieza
de criterio, no de demanda. Esta ataca un cluster grande y en alcance del feed de Upwork
(chatbots / agentes verticales) desde un ángulo que **ninguna de las 5 demos previas cubre**.

Agente del lado del consumidor que calcula la indemnización máxima a la que tiene derecho, arma
el argumento legal, refuta las excusas típicas de la aerolínea y redacta la reclamación en PDF.

---

## 0. Por qué este y no otro

Recorrido de descarte (tarea `[K1]` de la W37):

1. **Repetir el patrón del portfolio con otro dataset** (chatbot de cualificación, extracción a
   otro dominio) — descartado: las 5 piezas publicadas son todas *ingesta → juicio LLM →
   validación determinista → cola de revisión → log*. Otra igual no añade señal.
2. **Bot de soporte post-venta e-commerce/SaaS** — descartado: es el proyecto de IA más clonado
   que existe, se compite con miles idénticos a tarifa de suelo, cero diferenciación.
3. **Arnés de red-team para agentes** y **agente conversacional sobre sistema legacy sin API vía
   Playwright** — aparcados como alternativas; más lejos del moat real (fluidez jurídica) o con
   peor vídeo de 90 s.
4. **Agente de reclamaciones de consumo** — elegido. Extiende el único moat verificado del perfil
   (Derecho, fluidez de dominio, no credencial — ver `Freelance/Realidad.md` en el vault) a un
   vertical nuevo, sin rehacer el intake de despachos de la Demo 1.

---

## 1. Encuadre: demo de capacidad B2B, NO producto B2C

**El error que NO se repite.** §11 de `demos-portfolio-exposicion-2026` descartó tres candidatas
por lo mismo: *"era MRR de un negocio de captación outbound que no existe. Aunque la pieza fuera
perfecta, no había canal para venderla en 3-6 meses."* Un "DoNotPay de vuelos" dirigido al
pasajero final es producto, no entregable freelance: necesita tráfico, marca y captación que el
perfil no tiene.

**Cómo sí funciona.** Se construye el agente como pieza de portfolio. El comprador es quien ya
tiene el canal de clientes y el cuello de botella operativo.

**Compradores — hipótesis sin verificar** (mismo estándar que el ancla de precio ausente del
Sistema 2; se contrasta en el gate del §12):

| Comprador candidato | Dolor que *quizá* resuelve | Objeción conocida |
|---|---|---|
| Legal-tech / despachos de consumo pequeños | Ofrecer el servicio sin poner un abogado a cada expediente de 250-600 € | ¿Lo externalizan o ya tienen su flujo? |
| Asociaciones de consumidores (tipo OCU) | Herramienta de autoservicio para socios | Ciclo de compra lento, presupuesto limitado |
| Agencias de viaje / OTAs | Perk de fidelización post-incidencia | ¿Prioridad real o "nice to have"? |
| Agencias de claims pequeñas / regionales | Cualificación e intake manual | Ver aviso ↓ |

**Aviso — no apuntar a los incumbentes.** AirHelp, Flightright, Reclamio y similares tienen la
cualificación de elegibilidad EU261 como producto central, ya automatizado en casa. Venderles
esto es la misma premisa que la nota de demos tuvo que retractar en su registro §5.1 ("refutada
la premisa 'nadie lo hace' — IESA ya lanzó Gesfincas IA"). El mercado real, si existe, es la
cola larga que no es un incumbente: el despacho de consumo que lo hace a mano, la asociación, la
OTA. El gate del §12 sirve para averiguar si esa cola larga paga.

**Forma de la demanda observada (2026-09-08, ~30 posts del feed de Upwork "AI agent" — señal de
DEMANDA, no de venta cerrada; el gate del §12 sigue ABIERTO).** El feed se parte en dos:

- *Commodity*: "build a chatbot / integrate OpenAI", $0–1K gastados por el cliente, briefs de 3
  líneas, 50+ propuestas. Carrera a suelo.
- *Premium*: clientes con **$7K–100K+ gastados** y specs con constraint de arquitectura escrito
  por ellos mismos. Piden exactamente el reparto de esta demo. Ejemplos literales del feed:
  - *"Backend Developer for Scoring Service"* ($20K+ gastado): su regla dura y único
    descalificador — *"The AI never calculates anything. Every number is computed in code…
    If your plan is to let the model do the arithmetic, we are not a fit."* Es la tesis de
    esta demo restablecida por un comprador con historial de gasto.
  - *"AI / Agentic Automation Expert for Medical Billing"* ($100K+): eligibility / claims /
    denials / QA — misma forma que EU261 en otro vertical.
  - *"AI Agent / Autonomous AI System Developer"*: *"think through where AI should be
    autonomous, where deterministic logic is required… not a simple chatbot"*.
  - *"Head of Automation Engineering"*, *"Payment Platform Reviewer"*: obsesión con el fallo
    silencioso y con tests que fallan si alguien deshace el fix — encaja la disciplina de eval
    y las actas de bugs (Demo 4 ×5, Demo 5 freemium, `pais_reclamacion` nulo de Demo 6).

**Corrección al comprador candidato de arriba.** El discriminador real NO es la tarifa publicada
(el de scoring paga $30/h). Es **el historial de gasto del cliente + lo específico que es el
encargo**. Y el comprador no es solo "despacho de consumo / asociación / OTA": es *cualquiera
que automatice decisiones / scoring / elegibilidad donde equivocarse cuesta dinero* — billing
médico, plataformas de assessment, lead-gen a escala, servicing de préstamos. EU261 es el
ejemplo trabajado, no el mercado.

El vídeo y el repo enseñan **lo que a ese comprador le cuesta construir**: el razonamiento de
elegibilidad con cita de artículo, la refutación de las excusas de la aerolínea, y un eval que
prueba que acierta los umbrales. No una web de captación.

---

## 2. Qué demuestra — y en qué se diferencia del portfolio

| Eje | Demos 1-5 | Demo 6 |
|---|---|---|
| Dominio | despachos legales / fincas / gestoría / leads B2B | derecho de consumo / transporte aéreo (nuevo) |
| Trabajo del sistema | clasificar o recuperar | aplicar un reglamento y **computar un resultado** (€ + elegible sí/no + artículo) |
| Lógica | Q&A sobre documentos, clasificación contra rúbrica | **adversaria**: refuta contraargumentos ("circunstancia extraordinaria", oferta a la baja) |
| Interacción | job batch, one-shot sobre una fila | multi-turno, recoge hechos del relato libre del usuario |
| RAG / pgvector | núcleo de Demo 1 | **no se usa** |
| Rúbrica de clasificación | núcleo de Demo 5 | **no se usa** — aquí es motor de reglas EU261 |
| Salida | filas en Postgres + panel SQL | **carta de reclamación en PDF** con artículos citados + dictamen |
| Sustrato | n8n / LangGraph (grafo) | bucle de function-calling (no es un grafo) |

**Filosofía que SÍ se traslada** (higiene, no el artefacto): el importe y la elegibilidad los
produce el motor de reglas determinista, **nunca el modelo**; el modelo solo extrae hechos del
relato y redacta prosa; toda decisión computada queda en `decision_log` con el artículo/regla
que la produjo (mismo principio de reproducibilidad que `aplicar_rubrica` en la Demo 5).

---

## 3. Alcance del MVP (disciplina de recorte)

**Dentro:** EU261, **un** escenario — retraso de vuelo de 3 h o más a la llegada al destino
final. Cálculo de compensación del art. 7, reducción del art. 7(2), y análisis de "circunstancia
extraordinaria" del art. 5(3) contra una tabla de precedentes del TJUE.

**Fuera del MVP (ampliación posterior, no ahora):** cancelación, denegación de embarque, equipaje
(Convenio de Montreal), derecho de asistencia del art. 9, vuelos con conexión múltiple,
reclamación efectivamente presentada ante la aerolínea o el organismo nacional.

**Generaliza a** (mismo patrón, otra norma): derecho de desistimiento e-commerce (14 días),
cláusulas suelo, cancelación de eventos, retrasos de tren. Se menciona en el vídeo; no se
construye.

---

## 4. Arquitectura

```
Chat UI (HTML + SSE)   ó   webhook (Telegram/WhatsApp)
        │
   Agente (LLM + function-calling, bucle)
        │
   ┌────┴──────────────────────────────────────────┐
   │ tools                                          │
   │  calcular_distancia(origen_iata, destino_iata) │  haversine sobre tabla de coords, determinista
   │  evaluar_elegibilidad(hechos)                  │  motor de reglas EU261 → {elegible, importe, articulo, reduccion}
   │  clasificar_causa(texto_libre) → categoria     │  LLM mapea relato → categoría cerrada (única llamada de "juicio")
   │  analizar_circunstancia(categoria)             │  lookup determinista en tabla de precedentes TJUE → {exime, sentencia}
   │  redactar_reclamacion(caso)                    │  1 llamada LLM, plantilla + citas
   │  generar_pdf(carta)                            │  reportlab
   └───────────────────────────────────────────────┘
        │
   Postgres: aeropuertos, precedentes_tjue, casos, decision_log
   (reutiliza ../1/docker-compose.yml, como las Demos 4 y 5; SIN pgvector)
```

- **Bucle de agente**, no grafo: `while` con historial + lista de tools. No LangGraph (es un
  bucle, no topología con ramas). No n8n.
- El único punto donde el modelo "juzga" es `clasificar_causa` (relato libre → una de ~12
  categorías: fallo técnico, meteorología, huelga de controladores, huelga de personal propio,
  ave, seguridad, decisión ATC…). Todo lo demás es código.
- **Gate de datos**: antes de redactar, el agente exige nº de vuelo, fecha y aeropuertos. Sin eso
  no llama a `redactar_reclamacion`.

---

## 5. Motor de reglas EU261 (BORRADOR DE MEMORIA — VERIFICAR antes de grabar, §13)

> Reglas redactadas de memoria. **Antes de grabar el vídeo** (miércoles/jueves, §10), verificar
> contra el texto consolidado del Reglamento (CE) nº 261/2004 en EUR-Lex y contra las sentencias
> clave del TJUE. Fechar la revisión, igual que se hizo con el BOE en la Demo 2.

**Compensación (art. 7(1)):**
- 250 € — vuelos de hasta 1500 km
- 400 € — vuelos intracomunitarios de más de 1500 km, y todos los demás vuelos entre 1500 y 3500 km
- 600 € — vuelos de más de 3500 km no intracomunitarios

**Umbral de retraso para compensación:** 3 h o más a la llegada al destino final — no está en el
texto del Reglamento, viene de la sentencia *Sturgeon* (C-402/07 y C-432/07), confirmada en
*Nelson* (C-581/10). Citar como jurisprudencia, no como articulado.

**Reducción del 50 % (art. 7(2)):** si la aerolínea ofrece transporte alternativo con una
diferencia de llegada limitada (2 h / 3 h / 4 h según banda de distancia).

**Distancia:** gran círculo (haversine). Para vuelos con conexión, *Bossen* (C-559/16): gran
círculo entre el primer punto de salida y el destino final, no la suma de tramos. (El MVP asume
vuelo directo; la regla se deja escrita para la ampliación.)

**Circunstancias extraordinarias (art. 5(3)) — tabla de precedentes:**

| Causa | ¿Exime de compensación? | Referencia |
|---|---|---|
| Fallo técnico / problema de mantenimiento | **No** (salvo defecto oculto de fábrica o sabotaje) | *Wallentin-Hermann* C-549/07; *van der Lans* C-257/14 |
| Meteorología adversa | Sí | considerando 14 |
| Huelga de controladores aéreos / ATC | Sí | considerando 14 |
| Huelga del propio personal de la aerolínea ("huelga salvaje") | **No** | *Krüsemann* C-195/17 |
| Colisión con ave | Sí | *Pešková* C-315/15 |
| Riesgo de seguridad / amenaza | Sí | considerando 14 |
| Decisión de gestión del tráfico aéreo | Sí | art. 5(3) explícito |

**Derecho de asistencia (art. 9):** comida, refrescos, alojamiento y comunicaciones se deben
**siempre**, incluso con circunstancia extraordinaria. (Fuera del MVP como cálculo, pero el
agente lo menciona en la carta.)

**Plazo para reclamar:** lo fija el Derecho nacional (*Moré* C-139/11: el Reglamento no establece
plazo). España: 5 años (art. 1964 CC tras la reforma de 2015). El agente pregunta el país y
avisa si el caso está fuera de plazo.

---

## 6. Datos sintéticos

- **Tabla de aeropuertos**: ~200 IATA con lat/lon (dataset abierto, OpenFlights). Determinista.
- **30 casos de prueba** con ground truth etiquetado: `elegible`, `importe`, `articulo`,
  `reduccion_aplica`, `circunstancia_exime`, `motivo`. Distribución obligatoria:
  - 8 elegibles claros (una por banda de distancia × con/sin reducción)
  - 6 no elegibles por circunstancia extraordinaria válida (meteo, ATC, ave, seguridad)
  - 4 elegibles pese a la excusa de la aerolínea (fallo técnico, huelga de personal propio) — **los casos del vídeo**
  - 4 retraso inferior a 3 h → no elegible
  - 3 fuera de plazo
  - 3 frontera: distancia justo en 1500 / 3500 km, retraso de 2 h 55 min
- Relatos en lenguaje libre (español e inglés), 2-3 estilos, para que `clasificar_causa` tenga
  algo que resolver.

---

## 7. Arnés de eval

Patrón de `4/eval/run_eval.py` (psycopg2 contra `decision_log`, `assert` final, `--dry-run`
estructural separado de la corrida real). **Dos métricas, dos números, no se promedian** (como en
la Demo 5):

- **`--sin-llm`** (hechos inyectados por caso): mide el motor de reglas. Objetivo 30/30 — si
  falla, hay un bug en el articulado.
- **modelo real** sobre los 30 relatos: mide `clasificar_causa` + extracción de hechos. Es **el
  número del vídeo** (p. ej. "acierta la elegibilidad en 28/30 y el importe en 30/30").
- Calidad de la carta: revisión manual de 5, checklist (cita el artículo correcto, importe
  coherente con el dictamen, refuta la excusa concreta).

---

## 8. Guion de vídeo (90 s) — versión "discrepancia"

No se enseña el camino feliz. Se enseña **el caso que la aerolínea rebajaría**:

1. (0-15 s) Pasajero: *"Vuelo Madrid-Nueva York, 4 horas de retraso, me dijeron que fue un
   problema técnico del avión y me ofrecieron un bono de 250 €."*
2. (15-45 s) El agente pregunta lo que importa (fecha, nº de vuelo, hora real de llegada),
   calcula distancia (>3500 km, no intracomunitario → banda de 600 €), clasifica la causa como
   "fallo técnico".
3. (45-70 s) **La discrepancia**: `analizar_circunstancia` devuelve *no exime* citando
   *Wallentin-Hermann*. Dictamen: **600 € en efectivo, no un bono**. El bono de 250 € era menos
   de la mitad de lo que corresponde.
4. (70-90 s) Genera la carta en PDF con los artículos y la sentencia. Cierre: *"Grabado, no
   animado. Mismo patrón para desistimiento, equipaje, cancelación de eventos."*

---

## 9. Stack

- Python, function-calling directo (SDK de Anthropic/OpenAI o pool de OpenRouter/Gemini como en
  la Demo 5). **No LangGraph, no n8n.**
- FastAPI + Postgres (reutiliza `../1/docker-compose.yml`: Postgres ya expuesto en
  `127.0.0.1:5432`, `.env` con la clave de modelo). **No pgvector.**
- `reportlab` para el PDF.
- UI: 1 HTML con Server-Sent Events, ~80 líneas. Sin framework.

---

## 10. Plan de la semana W37

Alineado con las filas `[K1]` de `Agenda/DAILY.md` del vault (2026-09-07 = lunes):

| Día | `[K1]` en DAILY | Entregable |
|---|---|---|
| **L 2026-09-07** | elegir proyecto: alcance + PLAN + stack | Esta carpeta + este `PLAN-demo6.md`. **Hecho hoy.** |
| **M 2026-09-08** | construir | Tabla de aeropuertos (OpenFlights) + motor de reglas EU261 determinista + tabla de precedentes TJUE. `test_reglas.py` con asserts por banda. |
| **X 2026-09-09** | seguir construcción | Bucle de agente + tools + extracción de hechos + `--sin-llm` end-to-end. **Empezar la verificación de las reglas del §5 contra EUR-Lex + sentencias.** |
| **J 2026-09-10** | cerrar build y **grabar** | UI de chat SSE + `decision_log` + `redactar_reclamacion` + `generar_pdf` + arnés de eval (30 casos) + calibrar. **Cerrar y fechar la verificación del §5 — antes de grabar.** Grabar. |
| **V 2026-09-11** | publicar (vídeo + Malt/LinkedIn/Upwork) | Montar y publicar el vídeo de 90 s. Además: publicar la Demo 5 en LinkedIn y Upwork si sigue pendiente (§13.8). |

**Sábado 2026-09-12 no se toca** — DAILY lo tiene comprometido con el batch de OralPrep/IELTS +
reserva.

**Escape hatch:** si el jueves va justo, se recorta el análisis de circunstancia extraordinaria
(art. 5(3)) y pasa a la W38. El núcleo — "calcula el máximo del art. 7 y lo redacta en carta" —
cierra el proyecto y es grabable; la refutación de la excusa es brillo, nunca al revés.

---

## 11. Qué NO reutilizar a propósito

pgvector / RAG, la rúbrica de clasificación de la Demo 5, el runner batch, el panel SQL,
LangGraph. Si aparecen, se ha vuelto a hacer una de las Demos 1-5 con otra etiqueta.

---

## 12. Gate de validación (lanzable desde el día uno, no depende de tener nada construido)

Dos o tres conversaciones con perfiles de la cola larga (§1), **no** con incumbentes:

1. Un despacho de consumo pequeño o una asociación: *"¿Cuál es hoy vuestro cuello de botella —
   captar casos, cualificarlos, o redactar? ¿Pagaríais por automatizar la cualificación +
   primera carta?"*
2. **La pregunta que la nota de demos tuvo que añadir a posteriori (§5.12, cuarta pregunta):**
   *"¿Ya tenéis cualificación automática de casos, o alguna herramienta que lo haga? ¿Qué parte
   no os fiais de que haga sola?"* — sin esto el gate puede pasar por educación y dejar sin
   probar la diferenciación.
3. Un freelance o pequeña consultora que ya venda automatización a legal-tech: *"¿Habéis visto
   demanda de esto? ¿A qué precio se mueve?"*

Si ninguna da señal, el proyecto se queda como pieza de portfolio (señal de perfil) y no se
invierte en ampliarlo.

**Estado del gate (2026-09-08): NO SE PERSIGUE (decisión K).** Sin Connects y sin outreach: no se
harán ni conversaciones ni propuestas. La demo se queda como pieza de portfolio (señal de
perfil) y no se invierte en ampliarla — que es la salida que este mismo §12 ya contemplaba.
Evidencia de mercado recogida (demanda, NO venta): forma de demanda del feed de Upwork, ~30
posts, el tier premium ($7K–100K+ gastados) pide el reparto modelo/determinista de forma
explícita (ver §1). Si en el futuro se reabre: la vía sería aplicar a *Scoring Service* /
*Medical Billing* con Demo 5 como enlace público y Demo 6 como precedente, y antes cerrar
`G-NUMEROS` (una propuesta es copy hacia fuera; sin redacción autorizada del §4 no salen cifras).

---

## 13. Riesgos y limitaciones honestas

1. **Las reglas del §5 son borrador de memoria, no verificadas.** Verificar contra el texto
   consolidado del Reglamento (CE) nº 261/2004 en EUR-Lex y contra *Sturgeon*,
   *Wallentin-Hermann*, *Krüsemann*, *Pešková*, *Bossen*, *van der Lans* — cerrado y fechado
   **antes de grabar el jueves**, no en paralelo al vídeo.
2. **Compradores sin verificar** — la tabla del §1 es hipótesis. De ahí el gate del §12. Los
   incumbentes (AirHelp/Flightright) están explícitamente fuera: la elegibilidad EU261 es su
   producto central ya automatizado.
3. **Sin ancla de precio verificada** para este servicio concreto. Mismo estándar que la Demo 2.
4. **Actividad potencialmente regulada** (asesoramiento jurídico) si se dirigiera al consumidor
   final. Como herramienta B2B vendida a una agencia/despacho, el encuadre y la responsabilidad
   son del comprador; dejarlo dicho en el README y en la propuesta.
5. **El dataset sintético no prueba conversión** a esos compradores. Prueba la capacidad
   técnica, nada más.
6. **Distancia con conexiones**: el MVP asume vuelo directo. La regla *Bossen* queda escrita
   pero no implementada.
7. **`clasificar_causa` es el punto frágil**: un relato ambiguo ("hubo una tormenta pero el
   avión también tenía una avería") puede caer en la categoría equivocada. Mitigación: cuando el
   modelo duda entre "exime" y "no exime", el dictamen sale como *provisional, a confirmar con la
   documentación de la aerolínea* — nunca afirma un importe firme sobre una causa dudosa.
8. **Demo 5 en LinkedIn/Upwork**: `Agenda/DONE.md` deja la línea `2026-09-04: Demo 5 — publicar
   en LinkedIn y Upwork` sin `— hecho`. Confirmar si está publicada antes de arrastrarla al plan
   del viernes.

---

## 14. Verificación pendiente

- [ ] Reglas EU261 §5 contra EUR-Lex consolidado + 6 sentencias del TJUE — cerrado y fechado antes de grabar (J 2026-09-10).
- [ ] Plazo de reclamación por país (mínimo ES, UK, DE, FR).
- [ ] Gate del §12 — 2-3 conversaciones.
- [ ] Ancla de precio: buscar en Upwork/Malt postings de "flight claim automation" / "EU261" / "legal claim assistant" y anotar rango observado.
- [ ] Confirmar estado de publicación de la Demo 5 en LinkedIn/Upwork.
