# Rúbrica de triage de correo entrante — despacho civil y mercantil

**Versión:** 1.0 · **Fecha de redacción:** 2026-08-15 · **Ámbito:** Demo A — Intake y consulta documental

---

## 1. Alcance y supuestos

**Qué es este documento.** Un criterio operativo para decidir a qué cola va cada correo que
entra en la bandeja general del despacho. Nada más. **No es asesoramiento jurídico**, no
contiene opinión sobre el fondo de ningún asunto y no prejuzga la viabilidad de ninguna
reclamación. Clasificar un correo como `plazo` no es afirmar que exista un plazo: es afirmar
que el correo contiene señales suficientes para que un humano lo mire antes que los demás.

**Qué no sustituye.** La clasificación no sustituye la lectura del expediente. Un correo
etiquetado `expediente_existente` y anotado en la ficha sigue necesitando que alguien lea el
expediente completo antes de contestar. El sistema ordena la bandeja; no decide.

**Supuestos del despacho modelado.**

- Despacho pequeño español (2-4 profesionales), sin departamento de admisión.
- Materia: civil y mercantil general — contratos, arrendamientos, reclamaciones de cantidad,
  societario no cotizado, propiedad horizontal, consumo, sucesiones sencillas.
- Fuera de materia: penal, laboral, contencioso-administrativo, fiscal, extranjería y
  cualquier asunto sujeto a derecho no español.
- Jurisdicción atendida: partidos judiciales de la Comunidad Valenciana, orden civil y
  mercantil. Fuera de ese perímetro se deriva.
- Una sola bandeja de entrada compartida. El mismo buzón recibe leads, clientes, proveedores,
  publicidad y correo interno.

**Supuesto técnico que condiciona el criterio.** El sistema devuelve **una sola categoría** de
una taxonomía cerrada de cinco valores, más un `motivo` en texto libre y una `confianza`
numérica. No hay etiquetas múltiples. Toda la sección 3 existe por esa restricción: si el
sistema admitiera varias etiquetas, la mitad de esta rúbrica sobraría.

**Consecuencia de cada rama (importa para justificar las prioridades).**

| Categoría | Qué hace el sistema | ¿Deja rastro? | ¿Es reversible? |
|---|---|---|---|
| `cliente_nuevo` | Crea ficha + borrador de acuse | Sí | Sí, borrando la ficha |
| `expediente_existente` | Añade nota al expediente | Sí | Sí, borrando la nota |
| `plazo` | Marca urgente + avisa al abogado | Sí | Sí |
| `ruido` | Archiva sin acción | **No** | **No, en la práctica** |
| `duda` | Cola de revisión humana + aviso | Sí | Sí |

`ruido` es la única rama sin rastro: nadie revisa lo archivado. Esa asimetría es el argumento
central del orden de prioridad de la sección 3.

---

## 2. Definición operativa de las categorías

Cada regla tiene identificador estable. El corpus etiquetado (`eval/dataset.jsonl`) referencia
estos identificadores en el campo `regla`.

### 2.1 `cliente_nuevo`

**R1** — Es `cliente_nuevo` cuando el remitente plantea una necesidad jurídica **propia** y no
es titular de ningún expediente vivo en la base del despacho.

- **Verdadera si** se cumplen las tres cosas: (a) hay una persona o empresa identificable
  detrás del correo; (b) esa persona describe un problema o una necesidad que le afecta a
  ella; (c) la consulta de `expedientes` por su dirección no devuelve ningún expediente vivo
  cuya materia guarde relación.
- **Falsa si** el remitente escribe en nombre de un tercero sin acreditar representación
  (→ R9), si es un envío masivo sin necesidad concreta (→ R4), o si ya tiene expediente vivo
  relacionado (→ R2).
- **Señales:** fórmulas de presentación ("me llamo…", "les escribo porque…", "no he trabajado
  antes con ustedes"), ausencia de referencias internas (número de expediente, nombre del
  abogado que lleva el asunto), descripción del problema desde cero.

**R1.1** — Un lead que **no encaja** (materia o jurisdicción fuera del perímetro) **sigue
siendo `cliente_nuevo`**. La cualificación de la sección 4 decide qué se hace con él —
normalmente derivar —, pero no cambia la categoría. Un ciudadano que escribe con una consulta
laboral no es ruido: es una persona esperando una respuesta que el despacho debe dar aunque
sea para decir que no.

### 2.2 `expediente_existente`

**R2** — Es `expediente_existente` cuando el **remitente es titular** de un expediente vivo y
el correo trata de ese expediente.

- **Verdadera si:** la dirección del remitente coincide con `email_contacto` de un expediente
  no cerrado, **y** el contenido del correo guarda relación con la materia de ese expediente
  (o no contradice ninguna).
- **Falsa si:** el vínculo es solo una mención (→ R2.1), si quien escribe no es el titular
  (→ R9), o si el único expediente coincidente está cerrado y la materia no es la suya
  (→ R2.2).
- **Señales:** deícticos que presuponen contexto compartido ("lo que hablamos", "el asunto de
  mi local", "os mando lo que me pedisteis"), aportación de documentación sin explicar para
  qué, preguntas de estado ("¿cómo va?", "¿se sabe algo?").

**R2.1** — **El vínculo lo establece el remitente, no la mención.** Que un correo nombre a un
cliente del despacho, cite un número de expediente o mencione al abogado que lo lleva no
convierte al remitente en titular. Un recomendado que escribe "me ha dado su contacto Ana
Torres" es `cliente_nuevo`, no `expediente_existente`.

**R2.2** — **Expediente cerrado.** Un expediente cerrado solo sostiene `expediente_existente`
si el correo trata **de la materia de ese expediente** (reactivación, ejecución de lo
acordado, factura del asunto). Si el titular de un expediente cerrado plantea una materia
nueva y no relacionada, es `cliente_nuevo`: hay que cualificar de nuevo, y anotar la consulta
en un expediente cerrado la entierra.

### 2.3 `plazo`

**R3** — Es `plazo` cuando el correo contiene un **límite temporal identificable** cuyo
incumplimiento produce una **consecuencia adversa** para el cliente o el despacho.

- **Verdadera si:** hay (a) una fecha, o un cómputo que permite derivarla ("me llegó el jueves
  y son diez días"), **y** (b) una consecuencia nombrada o evidente por el tipo de acto
  (contestar una demanda, recurrir, aportar prueba, responder un requerimiento, ejercer una
  opción contractual, evitar una caducidad).
- **Falsa si:** falta cualquiera de las dos. Una fecha sin consecuencia ("nos vemos el 12") no
  es plazo. Una consecuencia sin fecha ni cómputo derivable no es plazo (→ R3.2).
- **Señales:** nombres de actos con plazo legal típico (demanda, burofax, requerimiento,
  citación, señalamiento, notificación del juzgado), aritmética temporal en el cuerpo, adjuntos
  de origen judicial o notarial, expresiones de cómputo ("hábiles", "vence", "hasta el").

**R3.1** — **Un plazo enterrado sigue siendo un plazo.** La categoría no depende del tono ni
de la posición en el texto. Un correo cordial de tres párrafos cuya última línea dice "por
cierto, el juzgado nos ha dado hasta el 1 de septiembre" es `plazo`. La dificultad de estos
casos es de **detección**, no de clasificación: una vez vista la fecha, R6.1 resuelve solo.

**R3.2** — **La urgencia declarada no es un plazo.** "Urgente", "cuanto antes", "es muy grave",
mayúsculas y signos de exclamación describen el estado de ánimo del remitente, no un límite
temporal. Sin fecha ni cómputo derivable, un correo urgente se clasifica por lo que sea
(normalmente `cliente_nuevo` o `expediente_existente`) y la urgencia se recoge en la dimensión
`urgencia` de la cualificación (R7.2), no en la categoría.

### 2.4 `ruido`

**R4** — Es `ruido` cuando el correo **no exige acción ni respuesta del despacho** y **no
contiene datos de ningún cliente ni expediente**.

- **Verdadera si:** se cumplen las dos condiciones a la vez. Publicidad no solicitada,
  boletines, notificaciones automáticas informativas, correo interno logístico.
- **Falsa si:** hay cualquier acción esperada (aunque sea administrativa: una factura de
  proveedor exige pagarla), o si aparecen datos de cliente o expediente (→ R10).
- **Señales:** pie de baja de suscripción, remitente `no-reply`, tratamiento genérico
  ("Estimado profesional"), maquetación comercial, ausencia total de referencia al despacho
  concreto.

**R4.1** — **Correo interno.** Un correo entre miembros del despacho sin acción para el triage
(logística, avisos de oficina) es `ruido`. Un correo interno que **transporta contenido de un
cliente** (reenvíos, consultas trasladadas) no es ruido: se clasifica por el contenido
transportado, y si ese contenido llega truncado o sin contexto, es `duda`.

**R4.2** — `ruido` es la categoría de **cierre por defecto negativo**: se elige cuando ninguna
otra condición se cumple, nunca cuando varias compiten. Ver R6.5.

### 2.5 `duda`

**R5** — Es `duda` cuando (a) tras aplicar las reglas de desempate siguen quedando **dos o más
categorías defendibles**, o (b) **falta un dato imprescindible** para decidir y ese dato no
está en el correo ni en la base de datos.

- **Verdadera si:** el desacuerdo es de criterio, no de lectura. Dos profesionales del despacho
  con la misma información etiquetarían distinto.
- **Falsa si:** la respuesta está en el correo pero cuesta leerla. `duda` no es la papelera de
  lo incómodo.
- **Señales:** contenido truncado o sin contexto recuperable, remitente cuya relación con el
  despacho no se puede establecer, presencia simultánea de señales de categorías con acciones
  incompatibles.

**R5.1** — **Redacción pobre no es motivo de `duda`.** Faltas de ortografía, ausencia de
acentos, frases sin puntuar, mensajes escritos desde el móvil y correos de personas mayores o
poco familiarizadas con el trámite se clasifican con normalidad si la necesidad es
identificable. Confundir "mal escrito" con "ambiguo" convierte el triage en un filtro de clase
social y llena la cola humana de trabajo que la máquina podía hacer.

### 2.6 Reglas transversales

Dos reglas que no definen categoría pero **excluyen** categorías, sea cual sea el resto del
análisis. Se aplican antes que el desempate de la sección 3.

**R9** — **Terceros y secreto profesional.** Un remitente que no es el titular del expediente
**nunca** se clasifica como `expediente_existente`, por mucho que el expediente exista y la
materia encaje. Familiares, socios, gestorías, aseguradoras y compañeros de otro despacho
pueden tener razón y aun así no acreditan representación desde un correo. Etiqueta correcta:
`duda`, con el motivo indicando qué representación falta acreditar. La autorización del
titular se pide fuera del sistema; no se presume.

**R10** — **Datos de cliente en manos de un tercero.** Si un remitente ajeno al despacho exhibe
datos de un cliente o de un expediente (nombre en relación con un asunto, número de
expediente, señalamiento), el correo **no puede ser `ruido`** aunque sea publicidad evidente.
Etiqueta correcta: `duda`. El motivo no es comercial sino de seguridad: hay que saber de dónde
salió el dato, y archivar sin rastro destruye la única evidencia. Una incidencia de datos que
se detecta tarde cuesta mucho más que leer un correo publicitario de más.

---

## 3. Reglas de desempate

**R6** — Un correo puede cumplir varias condiciones de la sección 2. El sistema devuelve una
sola categoría. Se aplican estas prioridades **en orden**; la primera que dispara decide.

| Prioridad | Regla | Resuelve |
|---|---|---|
| P1 | **R6.1** `plazo` gana a todo | Cliente vivo con plazo; lead nuevo con plazo; plazo fuera de materia |
| P2 | **R6.2** Sospecha de conflicto → `duda` | Lead cuya contraparte es cliente del despacho |
| P3 | **R6.3** `expediente_existente` gana a `cliente_nuevo` | Cliente vivo que plantea materia nueva |
| P4 | **R6.4** `cliente_nuevo` gana a `duda` residual | Lead cualificable aunque el correo sea flojo |
| P5 | **R6.5** `ruido` es residual y nunca gana | Comercial que cita un expediente real |

**R6.1** — **P1: `plazo` tiene prioridad sobre cualquier otra categoría.**
Un cliente con expediente vivo que menciona un plazo procesal es `plazo`, no
`expediente_existente`. Un primer contacto que llega con un burofax de diez días es `plazo`, no
`cliente_nuevo`. Un plazo en materia que el despacho no lleva es `plazo`, no un lead a derivar.

*Justificación por consecuencia del error.* Un plazo mal clasificado es el **único error que el
tiempo hace irreversible**. Si un lead se clasifica como plazo por error, alguien pierde diez
minutos y lo reencamina; el coste es de atención. Si un plazo se clasifica como lead, la
consecuencia puede ser la preclusión del trámite, y ninguna corrección posterior la deshace.
Los dos errores no son simétricos y la prioridad refleja esa asimetría, no una jerarquía
conceptual entre categorías.

*Efecto secundario aceptado.* P1 hace el sistema deliberadamente propenso a **falsos positivos
de plazo**. Es el precio, y está declarado en la sección 7.

**R6.2** — **P2: la sospecha de conflicto de intereses manda el correo a `duda`.**
Si el correo nombra como contraparte a alguien que podría ser cliente del despacho, la
categoría es `duda` aunque el correo encajase perfectamente en `cliente_nuevo` o
`expediente_existente`.

*Justificación.* El error aquí no cuesta tiempo: cuesta la posibilidad de intervenir. Si el
despacho contesta al fondo a alguien que quiere demandar a un cliente propio, el daño ya está
hecho en el primer correo y no se repara clasificando bien el segundo. Va por debajo de P1
únicamente porque un plazo caduca solo y un conflicto no: el conflicto sigue ahí para ser
detectado por el humano que atiende la alerta de plazo.

**R6.3** — **P3: `expediente_existente` gana a `cliente_nuevo`.**
Un cliente con expediente vivo que pregunta por una materia distinta es `expediente_existente`.

*Justificación.* Los dos errores son reversibles, así que decide el coste de limpieza. Una nota
de más en un expediente vivo la lee el abogado que ya lleva a ese cliente y la reencamina en
segundos. Una ficha duplicada ensucia la base, dispara un acuse de recibo que trata al cliente
como desconocido —lo que el cliente sí nota— y obliga a fusionar registros. Excepción: si la
materia nueva dispara la cualificación (conflicto o materia fuera de perímetro), P2 y R7 mandan.

**R6.4** — **P4: `cliente_nuevo` gana a la `duda` residual.**
Si el correo permite completar las cuatro dimensiones de la sección 4 —aunque esté mal escrito,
sea breve o no diga expresamente que quiere contratar—, es `cliente_nuevo`.

*Justificación.* La cola humana solo funciona si es corta. Mandar a revisión todo lo imperfecto
la convierte en una segunda bandeja de entrada, y entonces el despacho está haciendo el trabajo
de antes más el de leer las alertas. `duda` tiene que costar algo o deja de significar nada.

**R6.5** — **P5: `ruido` es residual y nunca gana un desempate.**
Si `ruido` compite con cualquier otra categoría, `ruido` pierde. Un correo comercial que cita
un expediente o un cliente real no es ruido: es `duda`.

*Justificación.* `ruido` es la única rama sin rastro (tabla de la sección 1). Un falso positivo
de ruido no se detecta nunca, porque nadie mira lo archivado: no hay cola, no hay métrica, no
hay reclamación. Es el único error del sistema que se vuelve invisible en el momento de
cometerse, y por eso `ruido` es la categoría con el listón más alto.

---

## 4. Cualificación del `cliente_nuevo`

**R7** — La cualificación **no cambia la categoría** (R1.1): un lead que no encaja sigue siendo
`cliente_nuevo`. Cambia **qué se hace dentro de la rama**. Se evalúan cuatro dimensiones.

### **R7.1** — Materia

| Valor | Criterio | Acción |
|---|---|---|
| `dentro` | Civil o mercantil general | Flujo normal: ficha + acuse |
| `frontera` | Mixta o de encaje discutible (contrato de alta dirección, concursal con vertiente laboral, consumo con vertiente sancionadora) | Ficha + marca `revisar_materia`, sin acuse automático |
| `fuera` | Penal, laboral, contencioso-administrativo, fiscal, extranjería | Ficha + acuse de derivación |

**Falla cuando:** el correo describe el problema en términos coloquiales y la materia real solo
se ve leyendo el contrato ("me han echado de la empresa que monté con mi socio" puede ser
societario o laboral). Ante materia `frontera`, no se envía acuse automático: el acuse crea
expectativa de intervención.

### **R7.2** — Urgencia

| Valor | Criterio |
|---|---|
| `plazo` | Hay límite temporal identificable → **no llega aquí**: R6.1 lo sacó a `plazo` |
| `alta` | Consecuencia grave en curso sin fecha (cuentas bloqueadas, obra parada, ocupación en curso) |
| `normal` | El resto |

**Falla cuando:** el remitente usa el registro de urgencia por costumbre. Se puntúa por el
hecho descrito, nunca por los adverbios (R3.2). Un correo en mayúsculas sobre una consulta
rutinaria es `normal`.

### **R7.3** — Jurisdicción

| Valor | Criterio | Acción |
|---|---|---|
| `dentro` | Territorio y orden atendidos | Flujo normal |
| `derivable` | Territorio español fuera de la Comunidad Valenciana, asunto que admite trabajo a distancia o corresponsalía | Ficha + marca `valorar_corresponsalia` |
| `fuera` | Derecho extranjero, o tribunal extranjero | Ficha + acuse de derivación |

**Falla cuando:** la pista territorial está en el domicilio del remitente y no en el del asunto.
Manda **el foro del asunto**, no dónde vive quien escribe: un residente en Valencia que compra
un inmueble en Lisboa es `fuera`; un residente en Bilbao con un local en Alicante es `dentro`.

### **R7.4** — Conflicto de intereses

| Valor | Criterio | Acción |
|---|---|---|
| `sin_indicios` | No se nombra contraparte, o la nombrada no consta en la base | Flujo normal |
| `posible` | La contraparte nombrada coincide o se parece a un cliente, o el asunto es el reverso de un expediente vivo | **`duda` + revisión humana (R6.2)** |
| `confirmado` | Coincidencia exacta con cliente vivo | **`duda` + revisión humana, sin acuse** |

**Esta es la única dimensión que, ante la duda, va SIEMPRE a humano.** Las otras tres admiten
una decisión automática conservadora —derivar, marcar, esperar—. El conflicto no: no existe una
acción automática segura, porque cualquier respuesta al fondo ya compromete al despacho. La
regla operativa es literal: **si no se puede descartar el conflicto con lo que hay en el
correo y en la base, es `duda`.** No se envía acuse de recibo automático a un lead con
conflicto `posible` o `confirmado`, ni siquiera el genérico: un acuse es un contacto.

### Marca "no encaja"

Un lead se marca **`no_encaja`** si `materia = fuera` **o** `jurisdiccion = fuera`. Efecto: se
crea la ficha igual (queda registro de que el despacho fue contactado y cuándo), el acuse
automático se sustituye por un texto de derivación sin plazo de respuesta comprometido, y no se
abre expediente. Un lead `no_encaja` **nunca se archiva como ruido**: la persona escribió y
merece respuesta.

---

## 5. Escalado a humano

**R8** — Hay **dos caminos distintos** a la cola de revisión. Se parecen en el destino y en
nada más.

### **R8.1** — Vía nombrada: la categoría `duda`

La elige el modelo. Es una **afirmación sobre el correo**: "este correo no se puede clasificar
con la información disponible". Se usa cuando se cumple R5, o cuando lo fuerza R6.2 (conflicto)
o R9 (tercero). El `motivo` debe decir **qué falta o qué compite**, no "no estoy seguro":

- Bien: *"El remitente no consta como titular; dice ser hija de la titular del expediente de
  Lucía Ferrán. No se puede acreditar representación desde el correo."*
- Mal: *"Correo ambiguo, requiere revisión."*

### **R8.2** — Vía forzada: el umbral de `confianza`

Es independiente de la categoría. Si el modelo devuelve cualquier categoría **distinta de
`duda`** con `confianza` por debajo del umbral (por defecto **0,7**), el correo va igualmente a
la cola humana, **conservando la categoría propuesta**. Es una **afirmación sobre el modelo**,
no sobre el correo: "esta clasificación puede ser correcta, pero el sistema no la sostiene".

El humano ve cosas distintas en cada vía y por eso hay que separarlas: en R8.1 recibe una
pregunta abierta; en R8.2 recibe una propuesta que debe confirmar o corregir. Fundirlas
convierte la cola en una lista indiferenciada y hace imposible medir cuál de los dos mecanismos
está fallando.

**R8.3** — **`ruido` con confianza baja se trata como `duda`, no como ruido.**
La regla general de R8.2 conserva la categoría propuesta. `ruido` es la excepción: archivar es
la única acción sin rastro (R6.5), así que un `ruido` con `confianza < 0,7` no se archiva —
entra en la cola con la categoría propuesta marcada como no confirmada. Archivar por debajo del
umbral es tomar la decisión irreversible precisamente cuando el sistema admite que no sabe.

**Umbral.** 0,7 es un punto de partida, no un resultado experimental — ver sección 7. La
calibración real exige medir sobre `eval/dataset.jsonl` y mover el umbral hasta que la cola
humana tenga un tamaño que el despacho pueda absorber cada mañana. El número correcto depende
de cuántos correos al día puede revisar una persona, no de la métrica.

---

## 6. Casos límite resueltos

Cada caso indica entre paréntesis el identificador del correo correspondiente en
`eval/dataset.jsonl`.

**C1. Cliente con expediente vivo que menciona un plazo procesal (e04)**
Sonia Márquez, expediente de desahucio abierto, escribe pidiendo instrucciones y dice que la
contestación vence el 3 de septiembre.
→ **`plazo`**. Cumple R2 y R3 a la vez. Decide R6.1: la nota en el expediente la leerá alguien
cuando abra el expediente; la alerta de plazo la lee alguien hoy. Clasificarlo como
`expediente_existente` no pierde el correo, pierde el reloj.

**C2. Primer contacto que llega con un burofax y diez días (e12)**
Persona sin expediente, adjunta un burofax recibido, dice que le dan diez días y que vence el
25 de agosto.
→ **`plazo`**. R6.1 gana a R1. Es el caso más contraintuitivo de la rúbrica: el correo *es*
literalmente un lead, y el sistema lo trata como plazo. La razón es que la cualificación
comercial puede esperar a mañana y el cómputo no. Consecuencia operativa incómoda: la rama de
plazo actualiza un expediente que aquí no existe — ver sección 7, punto 2.

**C3. Cliente nuevo que dice "urgente" sin ninguna fecha (e07)**
Primer contacto: su socio le ha bloqueado el acceso a las cuentas de la sociedad, escribe en
tono de emergencia y pide ayuda inmediata, sin mencionar ningún acto ni fecha.
→ **`cliente_nuevo`** con `urgencia = alta`. R3.2: no hay límite temporal identificable, luego
no hay plazo, por urgente que sea el problema. Es un caso genuinamente discutible —la urgencia
material es real— y por eso está marcado ambiguo en el corpus. Si `plazo` absorbiera esto,
absorbería el 30% de la bandeja y la alerta dejaría de significar nada.

**C4. Plazo en materia que el despacho no lleva (e25)**
Cliente con expediente civil vivo reenvía un requerimiento de Hacienda con diez días hábiles.
→ **`plazo`**. R6.1 se aplica antes que R7.1: primero se salva el reloj, después se decide si
el despacho atiende la materia o deriva. Invertir el orden —derivar primero por materia
fuera— entrega el problema al cliente con el plazo ya corriendo y sin avisarle de que corre.

**C5. Plazo enterrado en un correo cordial (e17)**
Tres párrafos amables sobre cómo va todo y, en la última línea, "el juzgado nos ha dado hasta
el 1 de septiembre para designar perito".
→ **`plazo`** (R3.1). La categoría no depende del tono. Este caso mide **detección**, no
criterio: por eso no está marcado como ambiguo. Si el modelo lo falla, no falla la rúbrica,
falla la lectura — y es el fallo más caro del sistema, porque el correo parece inocuo también
para el humano que revise la cola.

**C6. Comercial que cita el nombre de un cliente real (e22)**
Empresa de tasaciones ofrece servicios y menciona que "han visto que llevan el asunto de Sonia
Márquez".
→ **`duda`**, no `ruido` (R6.5, R10). Dos motivos, y el segundo pesa más que el primero: es
publicidad, sí, pero un tercero que exhibe el nombre de un cliente en relación con un asunto
vivo plantea de dónde ha salido ese dato. Archivarlo en silencio elimina la única evidencia de
una posible incidencia. La etiqueta correcta no es "publicidad"; es "que alguien mire esto".

**C7. Un familiar pregunta por el expediente de otra persona (e10)**
Escribe una mujer diciendo que es la hija de Lucía Ferrán, titular de un expediente vivo, y
pide que le cuenten cómo va.
→ **`duda`** (R9). Tentación fuerte de `expediente_existente`: el expediente existe, la materia
encaja, el parentesco es probablemente cierto. Pero la remitente no es la titular y el sistema
no puede acreditar representación. Anotar en el expediente es inofensivo; el riesgo está en lo
que viene después —la respuesta automática— y la rúbrica prefiere no abrir esa puerta. Es un
caso de secreto profesional, no de clasificación.

**C8. Lead cuya contraparte es cliente del despacho (e27)**
Primer contacto: quiere reclamar a Comercial Bellavista SL, que tiene expediente vivo en el
despacho.
→ **`duda`** (R6.2, R7.4). Encaja al 100% en `cliente_nuevo` y aun así no lo es. La ficha se
podría borrar, pero el acuse automático ya se habría enviado, y ese acuse es un contacto con
alguien que quiere demandar a un cliente. Es el único caso de la rúbrica donde se prohíbe
expresamente la respuesta automática.

**C9. El mismo remitente, dos correos, dos categorías (e16 y e21)**
Marta Iglesias tiene un único expediente, cerrado en marzo. En un correo pregunta por la fianza
de aquel asunto; en otro plantea un problema con su comunidad de propietarios.
→ El de la fianza es **`expediente_existente`**; el de la comunidad es **`cliente_nuevo`**
(R2.2). Mismo remitente, misma base de datos, distinta etiqueta: lo que decide no es quién
escribe sino si la materia es la del expediente cerrado. Anotar la consulta de la comunidad en
un expediente cerrado es enterrarla, y además salta la cualificación —materia, jurisdicción,
conflicto— que un asunto nuevo necesita aunque el cliente sea viejo.

**C10. Correo mal escrito pero perfectamente claro (e26)**
Persona mayor, sin acentos ni puntuación, dice que le han subido la luz sin avisar y que su
hijo le ha dicho que escriba.
→ **`cliente_nuevo`** (R5.1, R6.4). Hay persona identificable, hay problema propio, hay materia
civil de consumo. No falta nada: falta ortografía. Mandarlo a `duda` sería usar la cola humana
como filtro de forma en vez de como filtro de criterio.

**C11. Reenvío interno con el contenido truncado (e24)**
Un compañero del despacho reenvía algo que le llegó a su buzón personal, sin comentario, y en
el reenvío solo se ve la firma y media frase.
→ **`duda`** (R4.1, R5). Interno sí, pero no logístico: transporta contenido de alguien de
fuera que no se puede leer. `ruido` archivaría un correo que quizá era de un cliente. Es un
caso donde `duda` es la respuesta correcta y no un empate: falta un dato imprescindible y ese
dato existe —lo tiene el compañero—, solo hay que pedírselo.

**C12. Recomendado que cita a un cliente actual (e19)**
Primer contacto que empieza con "me ha dado su contacto Ana Torres, que es clienta suya".
→ **`cliente_nuevo`** (R2.1). Para un humano no hay ambigüedad; para el modelo es una trampa,
porque el nombre de una clienta y la búsqueda en Postgres van a devolver coincidencia. El
vínculo lo crea el remitente, no la mención. Este caso está en el corpus para medir
exactamente ese fallo.

---

## 7. Errores conocidos de esta rúbrica

Lo que sigue son debilidades reales del criterio, no advertencias de cortesía.

**1. P1 canibaliza.** Poner `plazo` por encima de todo hace que cualquier fecha con aire
procesal empuje hacia esa categoría. La rúbrica asume que un exceso de alertas de plazo es
tolerable, y esa asunción **no está medida**: si el despacho recibe treinta correos con fechas
por semana, la alerta se convierte en ruido de fondo y el sistema falla justo donde más se le
confía. El corpus tiene solo cuatro `plazo` y no contiene suficientes fechas inocuas para medir
el falso positivo. Es el hueco más serio del conjunto de evaluación.

**2. La rama `plazo` supone que el remitente ya tiene expediente.** El workflow ejecuta
`UPDATE expedientes SET urgente = true WHERE email_contacto = $1`. Para un primer contacto
(caso C2 / e12) esa condición no casa ninguna fila. Habrá que comprobar en la instalación real
si la alerta al abogado se dispara igualmente o si la rama muere ahí en silencio —**no está
verificado**—. Si muere, el caso que la rúbrica considera más caro de fallar es precisamente el
que el sistema deja caer. Probar antes de dar la demo por buena.

**3. `confianza` es criterio especificado, no comportamiento observado.** El esquema de salida
cableado hoy en el workflow emite `categoria` y `motivo`; no emite `confianza`, y el Switch no
tiene rama de umbral. Es decir: **de las dos puertas de la sección 5, hoy solo existe la
primera**. R8.2 y R8.3 describen cómo debe funcionar el escalado por umbral cuando se
implemente, no cómo funciona ahora. Y el 0,7 es un número elegido a ojo: las confianzas
autoinformadas por un LLM están mal calibradas y no son comparables entre modelos, así que
cambiar de modelo obliga a recalibrar el umbral desde cero.

**4. La identidad del cliente es la dirección de correo, y eso es frágil.** Un cliente que
escribe desde su cuenta personal en vez de la de la empresa aparece como desconocido y se
clasifica `cliente_nuevo`. El segundo brazo de la consulta —`nombre_contacto ILIKE $2`— mitiga
poco y falla de una forma concreta: **`ILIKE` ignora mayúsculas pero no tildes**, y no hay
`unaccent` instalado. Un correo que escriba "Sonia Marquez" o "Lucia Ferran" —como escribe
media España desde el móvil— no casa con `'Sonia Márquez Vidal'` ni con `'Lucía Ferrán Ortiz'`
en la base, y el sistema concluye que esa persona no es cliente. Los casos C6 (e22) y C7 (e10)
dependen enteramente de este brazo, porque el remitente no coincide: si el nombre llega sin
tildes, la búsqueda no devuelve nada, R10 y R9 no llegan a dispararse y el correo cae en
`ruido` o en una `duda` acertada por el motivo equivocado. Mitigación pendiente:
`CREATE EXTENSION unaccent` y comparar `unaccent(nombre_contacto) ILIKE unaccent($2)`. En
general, la frontera R1/R2 es tan buena como la higiene de la base de contactos, que en un
despacho pequeño no suele ser buena.

**5. La detección de conflicto solo funciona si la contraparte se nombra.** La mayoría de
primeros contactos describen el problema sin identificar a la otra parte ("un proveedor",
"mi antiguo socio"). R7.4 no puede disparar sin nombre, así que su cobertura real es baja y
depende de que el conflicto sea evidente. La rúbrica presenta el conflicto como el control más
estricto y es, en la práctica, el peor cubierto: un control fuerte sobre los casos que ve y
ciego sobre los que no.

**6. La taxonomía de cinco valores tiene huecos.** No hay categoría para un cliente que se
queja del servicio, para una factura de proveedor, para un requerimiento dirigido al propio
despacho, ni para la parte contraria de un asunto propio escribiendo directamente. Todos caen
en `duda` por defecto, lo que infla la cola humana con cosas que no son dudosas: son
categorías que faltan. La taxonomía está cerrada por decisión de producto, y esta rúbrica la
respeta, pero el diagnóstico correcto de parte de la cola de `duda` es "falta una etiqueta".

**7. Nadie mide los falsos negativos de `ruido`.** R6.5 y R8.3 endurecen el listón, pero no
existe métrica: lo archivado no se revisa, así que un error de esta clase solo se descubre
cuando el cliente llama preguntando por qué no le contestaron. Mitigación mínima que la rúbrica
recomienda y el sistema no implementa: retención de lo archivado y muestreo manual semanal.

**8. El corpus lo ha escrito una sola mano.** Los 28 correos comparten autor, y por tanto vicios
de estilo, longitud y vocabulario. Un modelo puede acertar por correlaciones espurias —qué
correos llevan acentos, cuáles son largos— sin haber aprendido nada del criterio. Los números
que salgan de este corpus son un indicio, no una medición.

**9. La distribución del corpus no es la de una bandeja real.** Aquí el `ruido` es el 14%; en
una bandeja real de un despacho pequeño está entre el 60% y el 80%. Cualquier métrica agregada
sobre este corpus sobrestima el rendimiento en producción, y la precisión de `ruido` es la más
inflada de todas.

**10. "Civil y mercantil general" es una frontera comercial, no jurídica.** El corte con lo
laboral y lo fiscal es difuso en la práctica —un contrato de alta dirección, un pacto de socios
con efectos retributivos, una reclamación de consumo con vertiente sancionadora— y R7.1 lo
trata como si fuera nítido. El valor `frontera` reconoce el problema sin resolverlo: en última
instancia depende de qué esté dispuesto a coger el despacho ese mes.

**11. La cualificación (sección 4) no se puede medir con este corpus.** El corpus solo tiene
una verdad de referencia, `categoria_esperada`, y por diseño la cualificación **no cambia la
categoría** (R1.1). Consecuencia directa: R7.1, R7.2 y R7.3 no son verificables por la
evaluación —un modelo puede acertar el 100% de las etiquetas y estar cualificando mal todos los
leads—. Solo R7.4 deja rastro medible, porque es la única dimensión que sí cambia la etiqueta
(a `duda`, vía R6.2). De las 30 reglas de esta rúbrica, el corpus ejercita 16. Medir la
cualificación exigiría un segundo campo de verdad de referencia por lead, y este corpus no lo
tiene.

---

## 8. Mantenimiento

Esta rúbrica y `eval/dataset.jsonl` son un solo activo: cambiar una regla sin re-etiquetar el
corpus deja el sistema midiendo un criterio que ya no es el vigente.

- Los identificadores `R…` son **estables**. Si una regla se retira, su identificador se marca
  como retirado y **no se reutiliza**: el corpus y los registros históricos apuntan a él.
- Toda regla nueva **que decida una etiqueta** (categorías, transversales y desempate) nace con
  al menos un correo en el corpus que la ejercite. Las dimensiones de cualificación no son
  medibles con este formato de corpus (sección 7, punto 11).
- Revisión sugerida: trimestral, o tras cualquier cambio de modelo (ver sección 7, punto 3).
