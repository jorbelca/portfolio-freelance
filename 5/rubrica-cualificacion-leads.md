# Rúbrica de cualificación de leads — Demo 5

**Versión:** 0.1 · **Fecha:** 2026-08-31 · **Ámbito:** Demo 5 — Cualificación de leads → asignación → primer contacto

---

## 1. Alcance y frontera

Criterio con el que el nodo `cualificacion_llm` asigna a cada lead entrante una de tres
etiquetas —`caliente`, `tibio`, `frio`— y el motivo que la produjo, citando la regla concreta
de esta rúbrica. La etiqueta y el motivo se escriben en `leads`, o en `cola_revision` si el
caso es dudoso; un humano revisa antes de que salga ningún correo.

**Esto es criterio comercial inventado para la demo.** No hay fuente externa que lo valide
—no es Derecho, no es una norma—: es el tipo de criterio que un cliente real afinaría contra
sus propios datos de conversión. Lo que la demo demuestra no es que la clasificación acierte,
sino que **queda registrado por qué cada lead se clasificó como frío** y que los casos sin
evidencia suficiente se paran en vez de forzar una respuesta. El acierto se mide contra un
ground truth etiquetado a mano (`eval/`); el número de venta es *"acierta X de N y manda los
dudosos a revisión con motivo"*, no "100 %".

**Empresa modelada.** Vendedor ficticio: **Nubeforge**, plataforma SaaS de observabilidad de
coste y fiabilidad de pipelines de datos en la nube; precio indicativo £1–2k/mes; motion
self-serve con asistencia comercial. ICP: empresas de producto software registradas en UK, con
tracción (post product-market fit) y escalando ingeniería. Todo el dataset es sintético y está
etiquetado como tal.

## 2. Dos fuentes de evidencia, y qué aporta cada una

| Fuente | Qué aporta | En el grafo |
|---|---|---|
| `ficha_empresa(nombre)` | Hechos de registro: país de constitución, estado (activa / disuelta / *dormant*), tipo de negocio (producto vs servicios), antigüedad, tamaño estimado, pertenencia a grupo | **Mock sobre dataset sintético**, etiquetado como tal. Es lo que en producción vendría de un registro mercantil |
| `buscar_señales(nombre)` | Señales de *timing* e intención: ronda de financiación reciente, vacantes de ingeniería abiertas, menciones públicas de dolor (coste cloud, fiabilidad de datos) | **Búsqueda web real** (1 API pública gratis). Es el dato "en vivo" del vídeo |

Regla de reparto: **los descalificadores (R1–R7) se evalúan contra `ficha_empresa`; los gates
de encaje (R8–R9) y el conteo de señales (R10–R12) se evalúan contra `buscar_señales`.** Única
excepción: **R6 cruza las dos fuentes** (tamaño de `ficha_empresa` + ausencia de S1 de
`buscar_señales`) y es deliberado — una empresa de cinco personas que acaba de levantar ronda
sí es lead. Si `ficha_empresa` no devuelve datos suficientes, ver R14 — no se fuerza `frio`.

**`SALTAR_INVESTIGACION=1` no salta estas fuentes: inyecta una `ficha_empresa` y unos
fragmentos de `buscar_señales` predefinidos por caso** (igual que `canned_extraccion` en
`4/grafo_facturas.py`), para que el eval mida la clasificación con evidencia fija y
reproducible. Cada fila del dataset lleva su payload de ficha + señales junto a la etiqueta
esperada.

## 3. Prelación — lista ordenada, gana la primera regla que encaja

El nodo recorre R1–R12 **en orden** y para en la primera que aplica; R13–R16 son
comprobaciones que se aplican **después**, sobre la etiqueta ya elegida. La etiqueta y el
motivo salen de una sola regla, citada por su identificador (`R6`, `R11`…). §14.4 lo pide
explícito — *la etiqueta más el motivo citando la regla que la produjo*, en singular.

### 3.1 Descalificadores → `frio` (contra `ficha_empresa`)

| # | Condición | Motivo registrado |
|---|---|---|
| R1 | País de constitución ≠ UK | `fuera de territorio` |
| R2 | Estado del registro: disuelta, en liquidación o *dormant* en el último ejercicio | `sociedad inactiva` |
| R3 | Negocio de servicios a cliente (agencia, consultora, integrador) sin producto propio | `no es empresa de producto` |
| R4 | Sector en la lista de exclusión comercial (defensa, juego, adulto, crypto pura) | `sector excluido` |
| R5 | > 250 empleados, o filial de un grupo cotizado | `cuenta enterprise — fuera del motion self-serve` |
| R6 | < 8 empleados **y** ninguna señal de financiación (S1) — *única regla que cruza ficha + web* | `demasiado pronto, sin presupuesto` |
| R7 | Competidor directo conocido (lista mantenida aparte) | `competidor` |

### 3.2 Gates de encaje → `tibio` (se evalúan antes de contar señales)

Un lead que pasó R1–R7 pero falla el encaje cualitativo es `tibio` **aunque tenga señales de
timing** — por eso van antes del conteo, no como una fila más de la tabla de conteo.

| # | Condición | Motivo |
|---|---|---|
| R8 | Producto no cloud-native, o dominio solo adyacente al de Nubeforge | `encaje de producto débil` |
| R9 | Contacto claramente junior / sin capacidad de decisión aparente y sin S1 | `contacto sin poder de decisión` |

### 3.3 Conteo de señales de timing (contra `buscar_señales`)

Señales, cada una vale 1:

- **S1** — Ronda de financiación (Seed ≥ £1M, Serie A o Serie B) anunciada en los últimos 12 meses
- **S2** — ≥ 2 vacantes abiertas de ingeniería / plataforma / data, o mención explícita de "scaling the team"
- **S3** — Stack cloud-native visible (AWS/GCP/Azure + orquestación de datos o Kubernetes)
- **S4** — Mención pública de dolor en el dominio de Nubeforge: coste de nube, fiabilidad de pipelines, observabilidad de datos

| # | Condición (pasó R1–R9) | Etiqueta | Motivo |
|---|---|---|---|
| R10 | ≥ 2 señales | `caliente` | `encaje ICP + N señales: <listadas>` |
| R11 | Exactamente 1 señal | `tibio` | `una sola señal (<cuál>) — no basta para caliente` |
| R12 | 0 señales, ICP encaja (UK, producto, tamaño 8–250) | `tibio` | `encaja perfil, sin disparador de timing` |

### 3.4 Comprobaciones sobre la etiqueta elegida (R13–R16)

| # | Condición | Resultado |
|---|---|---|
| R13 | El modelo nombra una **etiqueta rival defendible** con la misma evidencia | Se toma la más baja de las dos y va a `cola_revision` con ambas lecturas. El recorte lo hace el nodo — no se le pide al prompt una "confianza" (lección de la Demo 3, `2/README-detallado.md`: preguntar confianza directa la saturó arriba en 27/28 casos, los 4 errores incluidos) |
| R14 | `ficha_empresa` no da datos suficientes para evaluar R1–R7, o `buscar_señales` no devuelve nada | `sin_cualificar` → `cola_revision`, motivo `sin evidencia para cualificar`. **Ausencia de datos no es señal negativa** |
| R15 | Confianza declarada del modelo < `LEADS_CONFIANZA_UMBRAL` (def. 0.7) en la etiqueta elegida | `cola_revision`, motivo `confianza baja (<valor>)`. Débil por sí sola (ver R13); es el umbral duro mínimo, no la salvaguarda principal |
| R16 | Etiqueta final = `caliente` | Asignación de comercial (dict estático) + redacción del primer email (V2). El borrador **siempre** queda en `cola_revision` (`tipo = 'borrador'`) para revisión humana antes de enviarse — nada sale solo |

## 4. Qué es determinista y vive fuera de esta rúbrica

Lo comprueba `validaciones.py`, no el modelo. Su fallo manda a cola **pase lo que pase con la
confianza** (misma regla dura que la Demo 4):

1. **Campos obligatorios**: nombre de empresa + email de contacto. Sin ellos no hay lead que cualificar, hay ruido.
2. **Email sintácticamente válido.**
3. **Deduplicación** por email y por empresa, en SQL (`UNIQUE` en `leads`). Segundo contacto de una empresa ya conocida → `cola_revision`, para que el comercial ya asignado decida — no es un lead nuevo.
4. **Trazabilidad de las señales**: cada señal que el modelo cite en el motivo debe referenciar un fragmento realmente recuperado por `buscar_señales` (`snippet` + `url` + `recuperado_en`, guardados en `señales`). Una señal sin respaldo en la evidencia → `sin_cualificar` / cola. El modelo no se vigila a sí mismo desde el prompt (lección de la Demo 3, `2/README-detallado.md`): lo comprueba el nodo.

## 5. Zona gris declarada

- **"Producto vs servicios" (R3)** no siempre es nítido: una empresa puede vender un SaaS y además hacer implantación a medida. Criterio operativo: si el SaaS es el negocio principal y la fuente de ingresos recurrente, es producto. En la frontera → R13 (tibio + cola).
- **Los umbrales de tamaño (R5, R6)** son números redondos sin calibrar. En producción salen de los datos de conversión del cliente; aquí son un punto de partida, no una frontera verificada.
- **"Competidor" (R7)** depende de una lista que el cliente mantiene y que cambia. La rúbrica no la fija.
- **Recencia de las señales web**: `buscar_señales` puede devolver una noticia de financiación de hace tres años como si fuera actual. La ventana de 12 meses de S1 depende de que el fragmento recuperado lleve fecha; si no la lleva, la señal no cuenta.
- **La antigüedad de constitución no es un descalificador propio.** Se consideró (empresa demasiado madura → probablemente ya tiene solución, demasiado nueva → sin presupuesto), pero solo entra indirectamente vía R5/R6 (tamaño) y S1 (financiación). Una regla de antigüedad aislada descartaría empresas correctas que llevan años en un plateau y acaban de levantar ronda.

## 6. Vocabulario de salida

`caliente` · `tibio` · `frio` — las tres etiquetas de cualificación.

`sin_cualificar` — estado de error, no una cuarta etiqueta: el sistema no reunió evidencia
para decidir. Equivale a `error_extraccion` de la Demo 4 — el fallo no puede hacer desaparecer
el lead.
