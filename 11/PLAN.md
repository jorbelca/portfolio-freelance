# Plan de implementación — búsqueda y seguimiento de empleo

Estado actualizado: 13 de noviembre de 2026. Las secciones de avances fechadas conservan el historial; el estado actual se resume a continuación.

## Estado actual de la entrega

- Web y n8n arrancan juntos en Docker; Neon remoto conserva configuración, seguimiento y ejecuciones.
- Búsqueda pública conectada: descubrimiento, cruce de historial, reserva de aperturas, lectura, 15 extracciones, 11 comparaciones atómicas y valoración independiente de encaje, evaluación, cupos e informes.
- Programación periódica gestionada desde web/MCP y comprobada por n8n cada minuto; inicialmente desactivada.
- Panel de control, configuración por formularios, selección de proveedor/modelo, pausa/reanudación/cancelación y resolución de identidades/correcciones. Seguimiento secundario con tres estados visibles, fechas, múltiples URLs y fusión auditada de duplicados.
- MCP permite las mismas operaciones, incluidas tareas paginadas y filtradas por estado. Integración comprobada con el cliente oficial del SDK; configuración HTTP/stdio publicada.
- Verificado el recorrido real web → n8n → Codex dentro de Docker → Neon (ejecución n8n 6). Las pruebas reales de búsqueda conservadas terminaron en C; no hay evidencia de reparto real 13+7.
- Pendientes de cierre: cobertura y validación real de búsqueda con finalistas A/B, auditoría final de cobertura de fuentes y del conjunto. Neon sustituye el historial de Obsidian; no hay consulta automática de esa nota ni navegación con sesión.

## Objetivo

Convertir el prompt conservado en `defaults.json → source_prompt` en un sistema de búsqueda verificable, coordinado por n8n, con una web cuyo objetivo principal es configurar, ejecutar y supervisar el workflow de n8n, y secundariamente seguir las ofertas, y PostgreSQL remoto en Neon. El sistema investiga ofertas y registra su seguimiento; nunca envía candidaturas, mensajes ni formularios.

No se cargarán ofertas ficticias ni se presentarán resultados simulados como resultados reales. Si una integración no está conectada, el panel mostrará esa situación.

Modelo de dominio, estados, relaciones y casos de uso: [MODELO.md](MODELO.md). Este diseño sustituye el esquema inicial de estado único y precede a las siguientes fases.

## Decisiones actuales

- Proyecto en la carpeta `11` del repositorio.
- n8n en Docker, con volumen persistente y puerto local `5678`.
- Panel y servicio Node.js locales, puerto configurable, actualmente `3210`.
- Ofertas, historial, configuración y futuras ejecuciones en Neon remoto.
- El historial se mantiene en Neon. La adaptación actual no consulta Obsidian: requiere cargar las candidaturas anteriores y confirmar `history_ready`. No se considerará equivalente a haber comprobado `Agenda/DONE.md`; esta sustitución queda explícita respecto al prompt original.
- Acceso al modelo mediante Codex CLI autenticado con ChatGPT en el Mac. n8n llama al servicio local con una credencial, sin copiar la sesión de ChatGPT al contenedor.
- La disponibilidad de un modelo se comprobará con la cuenta real. «Luna» define aquí el nivel de segmentación requerido; no se da por disponible como identificador público de Codex. Los límites de la suscripción siguen aplicándose.
- Variables funcionales editables desde el panel y versionadas en Neon; credenciales solo en el servidor o en el almacén de credenciales de n8n.

## Implementado y límites comprobados

- [x] Panel de procesos con disponibilidad, revisión personal y candidatura separadas; empresas reutilizables, publicaciones alternativas y múltiples acciones de seguimiento.
- [x] API de altas y cambios con control de concurrencia e historial de eventos transaccional.
- [x] Migración normalizada 002: empresas, procesos, fuentes, publicaciones, candidaturas, acciones, eventos, configuración tipada y cupos. Tablas originales conservadas como legacy.
- [x] Consola principal del workflow con estado de n8n, admisión de ejecuciones, etapas disponibles y pendientes, ejecución del módulo e historial de resultados y errores.
- [x] Configuración con formularios para límites, lotes, cupos, antigüedad, zona horaria, modelo, historial y prompt; persistencia tipada y control de concurrencia.
- [x] Seguimiento de ofertas en pestaña secundaria.
- [x] MCP como interfaz de control para LLM: 21 herramientas con esquemas estrictos, anotaciones y respuestas estructuradas sobre la misma API; recursos y prompt operativo.
- [x] Transportes stdio y Streamable HTTP con token independiente, documentación y configuración copiable en la web. Modo de consultas en el adaptador stdio.
- [x] Edición parcial con revisiones/versiones, consultas individuales y paginación para no obligar al modelo a reenviar todo el perfil ni leer listas completas.
- [x] Controles web explícitos de permitir/pausar, etiquetas accesibles y atributos DOM estables de carga, revisión e identidad de registros.
- [x] Migración 003: control y ejecuciones persistentes con snapshot de configuración, exclusión mutua, identificador idempotente y detección de resultado incierto.
- [x] Instalador `npm run setup:n8n`: credencial desde .env, webhook autenticado, importación/publicación y reinicio del contenedor.
- [x] Cruce por todas las publicaciones registradas; candidatura persistente bloquea aunque se reabra el proceso. Empresa/título requiere revisión, no fusión automática.
- [x] Limpieza básica de enlaces públicos y validación de entradas.
- [x] Puente de extracción de contrato mediante Codex, con esquema JSON y cita literal comprobada.
- [x] n8n arrancado en Docker y workflow `01-contrato.json` importado.
- [x] Conectividad del contenedor con el servicio del Mac comprobada.
- [x] Panel sin datos inventados; conexión real con Neon comprobada. N029 registrada posteriormente por indicación del usuario.
- [x] Proyecto Neon creado y `DATABASE_URL` configurada con validación TLS.
- [x] Migración ejecutada dos veces contra Neon real; configuración conservada y lecturas de ofertas/configuración verificadas desde la API.
- [x] Credencial del puente instalada en n8n. El acceso al editor puede requerir completar el alta del propietario.
- [x] Extracción real panel → n8n → Codex → Neon usando un anuncio auténtico de Scalian, con cita literal validada e ID real de ejecución n8n.

Los workflows disponibles extraen contrato, analizan una ficha aportada en 15 tareas o ejecutan la búsqueda completa sobre las fuentes públicas soportadas. N029 conserva la candidatura y sus dos URLs; ninguna prueba genera ofertas en el seguimiento real. La ejecución real de contrato previa sigue conservada.

## Contrato de trabajo para tareas pequeñas

Cada tarea del modelo resuelve un único dato o decisión acotada. Recibe únicamente el documento, perfil o regla que necesita. Las páginas y ofertas son datos no fiables: sus instrucciones nunca autorizan herramientas ni modifican el flujo.

Una extracción devuelve `value`, `evidence` y `state`. La evidencia debe ser una cita literal de la fuente. Un dato ausente devuelve `desconocido`, sin inferencias. Las tareas que necesiten varios elementos usarán una lista con ese mismo contrato por elemento.

El servicio valida tipos, esquema, tamaño y citas. Si la respuesta falla, guarda el error y deja la tarea pendiente o fallida; no sustituye el dato por una suposición. n8n decide la siguiente tarea a partir de estados explícitos, no de texto libre.

La clasificación, los cupos, la antigüedad, la identidad y los bloqueos de historial se resuelven con código y registros persistentes. El modelo aporta extracciones o comparaciones limitadas con evidencia, sin poder declarar por sí solo una oferta verificada.

## Variables que deben poder modificarse

| Grupo | Variables |
| --- | --- |
| Perfil | Formación, experiencia acreditada, tecnologías, idiomas, residencia y preferencias |
| Búsqueda | Consultas, idiomas, fuentes habilitadas, países, periodicidad y activación |
| Límites | Fichas máximas por ejecución, tamaño del lote, antigüedad y cupos por zona |
| Criterios | Contratos admitidos, modalidades, exclusiones, requisitos y prioridades |
| Historial | Confirmación de carga inicial y revisión de identidad pendiente |
| Modelo | Identificador disponible, tiempo máximo y reintentos acotados |
| Infraestructura | Puerto y URL del servicio, conexión Neon y credenciales n8n |

Los valores actuales de 100 fichas, lotes de 5, 45 días y reparto 13/7 son valores iniciales, no constantes ocultas. Si el perfil estructurado contradice el prompt de referencia, la configuración no podrá activar la búsqueda hasta resolver la contradicción. Ningún secreto se devolverá al navegador.

## Orden de implementación y aceptación

### Fase 1. Completar las conexiones reales

1. Completado: proyecto Neon y conexión TLS en `11/.env`, sin imprimir credenciales.
2. Completado: migraciones numeradas y prueba de normalización con preservación de historial en esquema aislado; comprobar también repetición de migración en la base de la aplicación.
3. Completar el acceso a n8n y configurar Header Auth para el puente.
4. Probar una extracción con una ficha real aportada o consultada con permiso.
5. Verificar registro, edición, recarga e historial en el panel con datos reales autorizados.

Aceptación: n8n obtiene una respuesta validada del modelo y el panel conserva en Neon un cambio real tras reiniciar. Si falta una cuenta o credencial, registrar ese bloqueo sin simular éxito.

### Fase 2. Identidad e historial antes de abrir ofertas

1. Partir de las entidades separadas en 002 y extraer mediante código portal e ID público desde las URLs conocidas.
2. Ampliar las referencias alternativas ya registrables en el panel con IDs de fuente/tenant y resolución asistida de conflictos, conservando el ID interno estable.
3. Añadir coincidencia por portal/ID, enlace canónico y destino de candidatura verificado.
4. Bloquear candidatos ya aplicados, rechazados, descartados, cerrados, contratados o en entrevista antes de abrir su ficha cuando la identidad sea conocida.
5. Detectar coincidencias posibles por empresa/título y enviarlas a revisión; no descartarlas automáticamente ni computarlas.
6. Permitir confirmar duplicados y fusionar referencias sin perder eventos ni estados de exclusión.
7. Incrementar la revisión del historial ante cualquier cambio relevante y revalidar finalistas al cerrar la ejecución.

Aceptación: una URL alternativa de un proceso aplicado no provoca otra apertura si existe el alias; una identidad dudosa queda bloqueada para cómputo y exige revisión. La ausencia de `history_ready` impide iniciar una búsqueda.

No se puede impedir que una fuente externa devuelva una pista ya aplicada. Sí se debe impedir que el sistema vuelva a abrirla o procesarla cuando pueda identificarla antes de la apertura. Si la identidad solo aparece al leer la ficha, se cruza y se excluye inmediatamente después.

### Fase 3. Ejecuciones persistentes y configuración estructurada

1. Crear migraciones aditivas para ejecuciones, pistas, documentos, extracciones y referencias de proceso.
2. Guardar una instantánea de configuración y fecha de corte al iniciar cada ejecución.
3. Persistir cada tarea con entrada identificable, versión, estado, intento y error.
4. Registrar la primera apertura de cada ficha concreta por ejecución con unicidad en la base de datos.
5. Reservar el cupo de apertura de forma transaccional antes de leer una ficha; evitar superar el máximo con concurrencia.
6. Implementar pausa, cancelación y reanudación sin repetir resultados ya guardados.
7. Exponer ejecuciones y tareas en el panel.

Aceptación: reiniciar n8n o el servicio no pierde el avance ni duplica una apertura contabilizada. Reabrir la misma ficha no incrementa su contador; abrir otra ficha duplicada en otro portal sí lo incrementa.

### Fase 4. Descubrimiento y lectura de fuentes reales

1. Definir una interfaz de fuente y comenzar por una fuente pública verificable.
2. Generar consultas desde la configuración, priorizando el cupo deficitario.
3. Guardar pistas con enlace limpio, fuente, fecha y datos de identidad disponibles.
4. Aplicar el cruce de historial antes de cada apertura.
5. Leer la ficha completa y guardar texto, procedencia y fecha de comprobación.
6. Distinguir contenido completo, bloqueo, login, CAPTCHA y redirección genérica.
7. Probar una alternativa pública pertinente cuando exista; registrar el límite si no hay acceso.

Aceptación: una pista del buscador nunca se presenta como ficha leída. Las fuentes no autorizan envíos, creación de cuentas, cambios de perfil ni evasión de accesos. Las peticiones arbitrarias deben impedir acceso a redes privadas y servicios internos.

### Fase 5. Extracciones atómicas

Implementar y verificar una tarea cada vez. Primero ampliar el puente actual para seleccionar tareas permitidas; después añadir nodos separados en n8n. Cada nodo conserva su resultado antes de continuar.

| Tarea | Única responsabilidad | Resultado |
| --- | --- | --- |
| Identidad | Extraer empresa y título de la ficha | Identidad y citas |
| País | Identificar el destino laboral del puesto | País concreto o desconocido y cita |
| Modalidad | Identificar remoto, híbrido o presencial | Modalidad y cita |
| Elegibilidad remota | Identificar países permitidos y exclusión de España | Evidencia explícita o pendiente |
| Publicación | Extraer fecha atribuible al proceso | Fecha o intervalo y tipo de fecha |
| Contrato | Extraer relación laboral y duración | Valor y cita; ya existe la primera versión |
| Experiencia | Extraer mínimo obligatorio y alternativas admitidas | Requisito y cita |
| Formación | Extraer titulación obligatoria y equivalencias | Requisito y cita |
| Idiomas | Extraer niveles obligatorios | Requisitos y citas |
| Tecnología | Separar tecnologías obligatorias, alternativas y méritos | Listas justificadas |
| Función | Identificar tareas y responsabilidad principal | Tareas y citas |
| Vídeo | Identificar vídeo obligatorio para postular | Obligatorio, opcional o desconocido |
| Vigencia | Extraer señales explícitas de cierre o apertura | Evidencia de la página consultada |
| Canal | Verificar la vía específica de candidatura sin enviar | Canal, evidencia y límites |
| Encaje | Comparar requisitos extraídos con el perfil acreditado | Coincidencias, incumplimientos y dudas |

Aceptación por tarea: esquema válido, evidencia literal y prueba de dato ausente o ambiguo. Un fallo afecta a su dato; no rellena el resto ni borra resultados anteriores. El país de la empresa no sustituye al país del puesto, jornada completa no demuestra contrato indefinido y una fecha de actualización no reinicia la antigüedad.

### Fase 6. Reglas deterministas A/B/C y cómputo

1. Traducir cada causa de exclusión del prompt a una regla identificada y configurable, conservando su evidencia.
2. Resolver C cuando existe causa definitiva; no convertir ausencia de información en incumplimiento.
3. Resolver B si quedan condiciones esenciales, con responsable y evidencia necesaria para resolver cada pendiente.
4. Resolver A solo con ficha completa y todas las condiciones esenciales verificadas.
5. Calcular `computable` por separado de la clase: A o B, ficha completa, sin C, identidad única, historial resuelto, fecha admisible y país justificado.
6. Asignar una sola zona por proceso y aplicar cupos independientes; un excedente no compensa otro déficit.
7. Ordenar por encaje y preferencias sin inventar puntuaciones o probabilidades.

Aceptación: una B con contrato pendiente puede computar si cumple las condiciones de cómputo; una B con fecha, país, identidad o historial dudosos no computa. Exactamente 45 días es admisible con la configuración inicial. Un mínimo obligatorio superior a tres años excluye; uno de uno a tres años puede quedar pendiente si las prácticas no están acreditadas.

### Fase 7. Orquestación n8n

Crear workflows separados y pequeños, con entradas/salidas documentadas:

1. `01-contrato`: extracción aislada existente.
2. Inicio: validar configuración e historial y crear ejecución persistente.
3. Descubrimiento: producir pistas para el cupo prioritario.
4. Preapertura: resolver identidad y excluir historial conocido.
5. Lectura: reservar apertura, recuperar ficha y persistir documento.
6. Extracción: ejecutar una tarea atómica por nodo, con resultados persistidos.
7. Evaluación: aplicar reglas, historial y duplicidad; guardar oferta y eventos.
8. Lote: recalcular cupos tras un máximo de cinco fichas, respetando la variable configurada.
9. Cierre: revalidar historial, auditar, buscar sustitutas si procede y generar informe.

Los errores de autenticación o configuración detienen la ejecución con motivo visible. Solo los fallos transitorios se reintentan con espera y límite configurables. Ante respuesta ambigua se conserva la duda. No hay bucles ilimitados ni reinicio ciego de lotes completos.

Aceptación: el coordinador se detiene al cumplir ambos cupos, agotar aperturas, agotar fuentes pertinentes o recibir cancelación. Cada cierre declara el motivo y los déficits exactos.

### Fase 8. Panel completo e informe

1. Añadir pestañas para ofertas, pistas, historial, ejecuciones y configuración.
2. Mostrar clase A/B/C separada del estado de candidatura y de si computa.
3. Mostrar documentos, citas, pendientes, duplicados y próxima acción por oferta.
4. Permitir correcciones manuales auditadas y recalcular resultados afectados.
5. Añadir formularios de variables funcionales, conservando acceso al JSON validado.
6. Mostrar progreso real de n8n, errores y controles de inicio, pausa y reanudación.
7. Generar informe y registro con fecha de corte en Europe/Madrid, aperturas, cupos, desglose europeo, A/B/C y motivo de cierre.
8. Separar recomendadas A, pendientes B computables/no computables, descartadas C y pistas sin ficha completa.

Aceptación: una corrección a aplicada o rechazada se conserva inmediatamente y afecta al siguiente cruce y al informe. No se declara el objetivo cumplido sin auditoría final del reparto configurado.

## Verificación necesaria antes de considerar terminado el sistema

- Pruebas de identidad, alias, enlaces saneados, antigüedad y clasificación con casos límite.
- Pruebas de transacciones, concurrencia y reanudación contra una base de pruebas autorizada; nunca vaciar la base real para probar.
- Comprobación de recuperación tras error del modelo y de la fuente.
- Una ejecución real y acotada desde n8n hasta Neon y el panel, sin envíos de candidaturas.
- Reinicio de Docker y del servicio conservando estado y credenciales.
- Revisión de que no se guardan URLs privadas, credenciales ni datos inventados.

## Siguiente paso inmediato

Los dos workflows están publicados en Docker. El siguiente bloque de implementación es identidad por portal/ID e historial antes de cualquier lectura automática; después, fuentes públicas con reserva transaccional de aperturas. La extracción de 15 tareas está verificada de extremo a extremo con el texto real de Scalian y autorización expresa del usuario.

## Prioridad de producto corregida

La web es la consola del workflow, no un CRM como pantalla principal. El orden de implementación sigue esta jerarquía: configuración de fuentes/perfil/reglas; lanzamiento, observabilidad y resolución de incidencias de tareas pequeñas en n8n; resultados y auditoría; seguimiento de candidaturas como sección secundaria. La consola diferencia disponibilidad del motor, admisión de nuevos lanzamientos y estado de cada ejecución. «Pausar» no promete detener una llamada al modelo en curso. La búsqueda completa continúa pendiente y no se presenta como ejecutable.

## Requisito transversal: control por LLM

Toda nueva capacidad de la web debe poder operarse con una herramienta MCP concreta sobre la misma API, con entradas acotadas, enums compartidos, validación, errores recuperables y versionado cuando escriba. Las lecturas deben poder hacerse por ID y por páginas. Las tareas largas devolverán un identificador consultable; repetir una petición no debe duplicar una ejecución. Una operación pendiente del plan no se anuncia como herramienta disponible. El modelo no necesita acceder a SQL, secretos, Docker ni interpretar pantallas para controlar la aplicación.

Conexión y secuencia de uso: [MCP.md](MCP.md). Verificados stdio, HTTP y operaciones del seguimiento en un esquema de Neon aislado, sin añadir ofertas al seguimiento real. Queda pendiente probar la configuración en el cliente MCP concreto elegido por el usuario; no se ha modificado la configuración global de clientes.

## Entrega: extracciones persistentes y dashboard

- [x] Migración 005 aditiva: tareas independientes por ejecución, posición única, estado, resultado, error y tiempos.
- [x] `02-extracciones.json`: webhook con acuse inmediato → 15 nodos HTTP autenticados → cierre desde Neon. No mantiene una conexión HTTP durante las 15 llamadas.
- [x] Catálogo único en `src/tasks.js`; `node scripts/build-extraction-workflow.js` regenera el JSON de n8n. Cada tarea tiene instrucción acotada, mismo esquema de salida y evidencia literal.
- [x] Guardado antes de avanzar; tareas terminadas se reutilizan dentro de la ejecución, tareas simultáneas o fuera de orden se rechazan. No hay reintentos automáticos.
- [x] Fallos de extracción se guardan y permiten recoger los demás datos; el cierre completo queda fallido si alguna tarea falla, conservando los resultados válidos.
- [x] Reinicio marca ejecución y tarea en curso como inciertas; una ejecución sin cierre supera un plazo derivado de tareas y timeout y se marca incierta al consultar el motor. La comprobación manual sigue siendo necesaria.
- [x] MCP existente ampliado: `start_run(module=extraction)` y `get_run.tasks`; no se requiere operar el editor visual para lanzar o inspeccionar.
- [x] Dashboard con siguiente paso, módulos conectados/pendientes, selector de módulo, historial seleccionable, progreso y resultado/cita/error por tarea.
- [x] 17 pruebas con cero omisiones, incluidas persistencia y recuperación en esquemas aislados de Neon.

Esta entrega no incorpora reanudación ni reintento selectivo, no clasifica A/B/C, no abre URLs y no registra ofertas automáticamente. Una extracción de vigencia o canal describe únicamente el texto aportado. La cuenta/modelo configurados no garantizan ausencia de errores semánticos; las citas comprobadas no sustituyen evaluación ni verificación de fuentes.

### Segmentación fina de los siguientes bloques

Cada fila es una operación independiente con salida persistida; el modelo solo participa donde se indica.

| Orden | Operación singular | Ejecutor | Salida / condición de avance |
| --- | --- | --- | --- |
| I01 | Validar versión y consistencia del perfil estructurado | Código | Configuración válida o bloqueo; no interpretar el prompt con reglas ocultas |
| I02 | Comprobar confirmación y revisión del historial | Código/Neon | Marca de historial válida o bloqueo |
| I03 | Crear ejecución con fecha de corte y snapshot | Transacción | ID idempotente, sin abrir fichas |
| D01 | Elegir cupo con mayor déficit | Código | Una zona y sus plazas pendientes |
| D02 | Componer una consulta desde variables | Código | Consulta, idioma y fuente identificables |
| D03 | Consultar una fuente habilitada | Adaptador de fuente | Pistas y estado de acceso; sin confundir fragmentos con ficha |
| H01 | Extraer portal e ID de cada URL conocida | Código | Namespace e ID público completos; URL limpia |
| H02 | Cruzar todos los aliases contra historial | Neon | Excluida, conocida o sin coincidencia |
| H03 | Buscar coincidencias por empresa/título | Neon | Posible identidad → revisión; no fusión automática |
| L01 | Reservar una apertura única y su cupo | Transacción | Reserva o límite alcanzado; clave ejecución/ficha |
| L02 | Validar URL pública y redirecciones | Código | Bloqueo de redes privadas, sesiones y destinos inseguros |
| L03 | Recuperar un documento de una fuente | Adaptador | Texto, URL y hora; bloqueo/login/error separados |
| L04 | Determinar si la ficha está completa | Adaptador/código | Completa o pista; nunca éxito por HTTP 200 solo |
| L05 | Persistir documento con identidad de contenido | Neon | Documento inmutable y procedencia |
| X01–X15 | Una extracción del catálogo por nodo | Modelo + validador | Dato con cita o desconocido; implementadas para texto aportado |
| H04 | Cruzar IDs nuevos revelados en la ficha | Código/Neon | Identidad e historial resueltos o pendiente |
| E01 | Comprobar una causa de exclusión por regla | Código | Causa documentada o no acreditada; no convertir ausencia en incumplimiento |
| E02 | Comparar un requisito con un dato acreditado del perfil | Código; modelo solo si necesita comparación semántica acotada | Cumple, incumple o pendiente, con ambas evidencias |
| E03 | Resolver condiciones esenciales pendientes | Código | Lista de pendientes con responsable y dato necesario |
| E04 | Asignar A/B/C | Código | Clase derivada de reglas, separada del estado de candidatura |
| E05 | Comprobar computabilidad | Código | Booleano y motivos separados de la clase |
| E06 | Asignar una única zona acreditada | Código | España, Europa o sin asignación; nunca reparto conveniente |
| E07 | Guardar resultado y eventos | Transacción | Proceso estable, aliases y evidencias preservados |
| B01 | Recalcular cupos y aperturas al terminar lote | Código | Avanzar, cerrar o cupo prioritario |
| C01 | Releer revisión del historial | Neon | Revalidar filas afectadas si cambió |
| C02 | Revalidar finalistas sin reabrir por sistema | Código/Neon | Historial y duplicidad resueltos por proceso |
| C03 | Auditar clase, fecha, país y cómputo | Código | Totales verificables y déficits exactos |
| C04 | Resolver continuación o motivo de cierre | Código | Cupos completos, límite, fuentes agotadas o cancelación |
| C05 | Generar informe desde registros validados | Plantilla | Informe trazable; ninguna decisión nueva del modelo |

Cada operación futura tendrá su estado e idempotencia. Los errores de fuente, autenticación o persistencia detienen su rama y dejan visible el bloqueo; no se declara completada la investigación por haber terminado las extracciones.

## Validación real de las 15 tareas — 11/11/2026

Con autorización expresa del usuario se reutilizó el texto real de Scalian conservado en la ejecución inicial, sin volver a consultar la publicación ni crear una oferta.

- Ejecución de la aplicación: `ed04ae76-6267-4a64-bb20-360e3a0a32c5`.
- Ejecución de n8n: `2`, workflow `empleoExtraction02`.
- Configuración: revisión 3. Duración: 92 segundos, desde el inicio de despacho hasta el cierre persistido.
- Resultado: `succeeded`, 15 tareas terminadas, cero fallos técnicos. Seis datos con cita: empresa, puesto, modalidad, contrato, experiencia y tecnologías. Nueve datos desconocidos: país, elegibilidad desde España, publicación, formación, idiomas, funciones, vídeo, vigencia y canal.
- Todas las citas contrastadas literalmente con la entrada; resultado agregado idéntico a los resultados individuales de Neon.
- Dashboard comprobado con 15/15 tareas y enlace a la ejecución real de n8n.
- Repetir el mismo ID, módulo y texto devuelve la ejecución existente sin crear otra ni volver a llamar al modelo.
- Admisión restaurada a pausada. N029 sigue siendo la única oferta, con candidatura enviada y sus dos publicaciones.

Esta prueba acredita la orquestación y persistencia del análisis del texto aportado. No acredita vigencia actual, elegibilidad del candidato, clasificación A/B/C ni funcionamiento de búsqueda automática.

## Avance de búsqueda — 12/11/2026

- Identidad compartida por portal/ID para InfoJobs, LinkedIn, Workable, Greenhouse, Lever, SmartRecruiters y Emploive. El tenant evita confundir IDs reutilizados. El cruce de historial de API/MCP reconoce URLs alternativas; las coincidencias solo por texto siguen requiriendo revisión.
- El alta de publicaciones serializa el mismo ID y evita asociarlo a otro proceso, conservando aliases del mismo proceso. No se ha reescrito el historial.
- Cliente HTTPS público con resolución DNS fijada por petición, comprobación de cada redirección, límites de tamaño/tiempo y bloqueo de redes internas.
- Adaptadores de descubrimiento Arbeitnow, Arbeitnow UK y Remotive. Comprobación real: 300, 100 y 14 pistas respectivamente. No se han insertado pistas ni ofertas de esta comprobación en la base real.
- Lector conservador de JobPosting JSON-LD: una única descripción completa o pista con motivo; no considera login, páginas genéricas ni listados como fichas leídas.
- Documentación oficial consultada: https://www.arbeitnow.com/blog/job-board-api y https://remotive.com/remote-jobs/api . Los resultados de Remotive deben conservar atribución y enlace de origen.

Pendiente para completar el objetivo: integrar estos adaptadores con configuración editable, reservas y tareas persistentes; evaluación del perfil y reglas A/B/C; coordinador n8n con pausa/reanudación y cupos; resultados/auditoría en web y MCP; prueba real completa. El módulo de búsqueda permanece deshabilitado hasta tener ese recorrido conectado y verificado.

### Perfil y evaluación — 12/11/2026

- Migración 006 aplicada en Neon: configuración con revisión, habilidades/evidencias/prioridades, titulaciones, idiomas/niveles, fuentes habilitadas, consultas por zona/idioma y empleadores excluidos. Los datos iniciales proceden del prompt del usuario; prácticas y permisos desconocidos siguen desconocidos.
- API GET/PUT `/api/search/config`; guardado transaccional, revisión optimista, validación estricta y rechazo de duplicados. MCP `get_search_configuration` y `set_search_configuration` (23 herramientas totales).
- Web: secciones editables de perfil, fuentes, consultas y exclusiones, cargadas desde Neon y verificadas en navegador con estado ready/revisión 1. Se usa JSON validado para conservar todos los campos; quedan pendientes controles de formulario más cómodos.
- Once comparaciones semánticas independientes con perfil acreditado y evidencia literal: nivel, experiencia, formación, tecnología, idiomas, contrato, funciones, ubicación, vídeo, vigencia y canal. Se reutiliza el ejecutor Codex; no se ha consumido cuota real en estas pruebas.
- Clasificador puro: C prevalece con causa acreditada; B conserva pendientes con responsable y resolución; A requiere todas las condiciones. Computabilidad separada, 45 días inclusive, sin país por conveniencia ni adscripción por elegibilidad remota. Aún debe conectarse a las tareas persistentes y ampliarse el encaje y ordenación final.
- 29 pruebas completas sin omisiones, incluidas edición/lectura de perfil por MCP en Neon aislado, revisión obsoleta y validaciones. Cruce real de Wiris por alias: conocida y excluida, conservando rechazo original.

El objetivo sigue activo. Próximo bloque: tablas y coordinador de búsqueda con reserva de aperturas, documentos, decisiones y auditoría; workflow n8n con control de pausa/reanudación; resultados de ejecución e informe verificable en web/MCP. No se ha habilitado todavía búsqueda completa ni se ha declarado terminada.

### Coordinador n8n completo conectado — 12/11/2026

- Migración 007 aplicada: estado/revisión de ejecución, pistas, documentos con reserva previa de apertura, enlaces revelados y cola de tareas con claves idempotentes.
- `src/search.js`: descubrimiento por fuente, cruce antes de abrir, reserva transaccional, lectura JSON-LD, cruce de IDs/URLs revelados, extracciones, comparaciones, evaluación, auditoría por lote y final. Prioriza pistas del cupo deficitario sin usar esa pista como evidencia del país. Termina con déficit exacto por cupos, límite o fuentes agotadas.
- `03-busqueda.json` publicado en Docker como `empleoSearch03`; webhook con acuse inmediato, selector persistente y un nodo HTTP autenticado por responsabilidad. Verificado el formato del Switch contra el código instalado en n8n 2.34.6.
- Pausa entre tareas, reanudación, cancelación con conservación de resultados y reintento manual de una tarea fallida/incierta. Un reinicio conserva avances y marca llamadas interrumpidas como inciertas. Una lectura ya reservada no se repite automáticamente.
- UI: módulo buscar → filtrar → presentar, A/B/C y pistas separadas, pendientes y motivos, citas/documento, paginación, paso explícito de A/B al seguimiento y controles de ejecución.
- 28 herramientas MCP: inicio de búsqueda sin texto, resultados, candidato individual, control, incorporación al seguimiento e informe paginado. El informe Markdown y el registro JSON se escriben en `reports/<run_id>/` tras lotes/cierre y se descargan desde la web; directorio ignorado por git.
- Historial confirmado tras comprobar las 40 ofertas importadas, todas excluidas. Configuración funcional original restaurada tras la prueba (100 lecturas, lote 5, 13/7); admisión nuevamente pausada como estaba.
- Prueba real n8n → fuente → Neon → clasificación → cierre: `3674fa43-5077-470c-8c8d-b1f0552b9b26`, máximo una apertura. Ficha real de Tesslcareers, Marketing Manager, publicada 21/09/2026: C por 52 días, sin llamadas al modelo. Se comprobó que buscar en descripciones generaba ruido: ahora las consultas filtran títulos y conservan orden de descubrimiento.
- Informe real y registro generados desde los datos persistidos. No se ha añadido ninguna de esas pistas al seguimiento ni enviado candidaturas.
- 32 pruebas completas sin omisiones, incluidas búsqueda íntegra con fuente/modelo de prueba en esquema aislado, bloqueo de candidatura previa sin apertura, 15 extracciones, 11 comparaciones, pausa/reanudación, límites, persistencia y archivos. Los datos de prueba se eliminan al terminar.

Pendiente de la auditoría de cierre del objetivo: prueba real adicional del recorrido de comparaciones con una ficha admisible actual, verificación visual del dashboard conectado, controles más cómodos que el JSON para el perfil, ordenación por encaje/preferencias, correcciones/fusiones de identidades dudosas y actualización de informes ante cambios posteriores de candidatura. Comprobar recuperación/cancelación en sus casos límite y cobertura de fuentes para España. El objetivo permanece activo; no se declara terminado por la prueba temprana C.

### Entrega presentada al usuario — 12/11/2026

El usuario pidió cerrar esta entrega y presentar el estado actual. Se detuvo la ampliación de funcionalidades y se cerraron las verificaciones en curso.

- Migración 008 aplicada: revisión durable del historial con triggers transaccionales; versiones, resoluciones de identidad, capas de corrección, eventos e intentos de tareas. No se borra la evidencia anterior.
- Resultados e informes se revalidan al consultar si cambia una candidatura, publicación o proceso. Prueba aislada: una B computable se incorpora al seguimiento, se marca inscrita y pasa a C, reduciendo el total y actualizando el informe sin otra lectura.
- Identidades: confirmar otra convocatoria, vincular al proceso conocido o fusionar pistas duplicadas y conservar aliases. Un ID ya conocido no puede eludir el bloqueo declarándose otro proceso. La fusión de dos procesos ya existentes del seguimiento sigue bloqueada explícitamente.
- Ordenación por encaje, prioridades tecnológicas y modalidad/ubicación, sin inventar trayectos ni probabilidades. Se evita confundir RAG con fragmentos de «storage».
- Configuración por formularios: perfil, prácticas, titulación técnica, idiomas/niveles, tecnologías/evidencias/prioridades, fuentes/páginas y consultas. JSON completo disponible como consulta.
- Fuente corporativa configurable SmartRecruiters por empresa y país, con paginación limitada. Lectura pública por API cuando el HTML no contiene ficha completa; comprobación de ID y tenant, descripción completa y datos de procedencia. No se conservan los datos del creador del anuncio ni enlaces de referido.
- 30 herramientas MCP, incluidas resolución y corrección. Historial de cada intento y salto manual de una tarea incierta sin repetir una apertura reservada.
- Prueba real cerrada: `5d0d271e-168b-4881-b249-4566bdc3fb40`, ejecución n8n `4`, 24 tareas completadas sin errores. Scalian, Embedded Software Developer – Aerospace; publicación 30/09/2026, 43 días; C por requisito de titulación técnica universitaria obligatoria. Se conservaron 15 extracciones, tres comparaciones y la cita literal de la causa. Una apertura. Informe y registro en `reports/5d0d271e-168b-4881-b249-4566bdc3fb40/`.
- Configuración general restaurada: 100 aperturas, lotes de 5, 45 días, cupos 13+7; cuatro fuentes habilitadas y admisión pausada como estaba. Las 40 ofertas previas del seguimiento permanecen; ninguna ficha de las pruebas reales se convirtió en candidatura ni oferta de seguimiento.
- 35 pruebas comprobadas (batería completa de 34 + prueba nueva del lector corporativo). Integración aislada cubre correcciones, aliases, bloqueo por inscripción posterior, archivos, pausa/reanudación, fallo/reintento, conservación de intentos y cancelación. Navegador: ready, n8n conectado, formularios reales y resultado C visible; pestaña del panel presentada al usuario.

El objetivo general no se marca completo: falta validar una ejecución real con finalistas A/B y reparto completo; siguen pendientes la fusión de dos procesos existentes, cobertura adicional de fuentes y partes del plan que exceden la entrega actual. No se han simulado finalistas ni se afirma haber cumplido 13+7.

### Recuperación de tareas omitidas — 13/11/2026

- Corregida la continuidad al saltar manualmente una extracción o comparación fallida/incierta: se conserva el motivo, se registra un dato desconocido sin cita y se programa la siguiente tarea singular. La última comparación conduce a evaluación.
- Saltar una lectura conserva el documento como error y la pista sin ficha completa; no repite la apertura.
- Verificación superada en el esquema temporal de la prueba de búsqueda (79 segundos), junto con ocho pruebas de clasificación y motor/modelo; no crea ofertas ni consume llamadas al modelo en la base real. Imagen web reconstruida y aplicada en Docker.
- El objetivo general sigue activo: esta corrección no acredita por sí sola los pendientes de la auditoría de cierre descritos arriba.

### Fusión de ofertas ya registradas — 13/11/2026

- Migración aditiva 010: archivo de identidades fusionadas. El ID absorbido no se borra ni se reutiliza; deja de aparecer como oferta independiente.
- Web y MCP `merge_offers`: ambas versiones obligatorias, motivo y elección explícita de candidatura vigente. Se trasladan publicaciones, acciones y referencias de búsqueda; las notas se combinan y el historial incluye los eventos originales. El evento de fusión conserva las dos fichas y candidaturas previas.
- Se mantienen los bloqueos de historial: ninguna candidatura se puede borrar eligiendo una ficha sin candidatura. No se reabren procesos cerrados por fusionarlos.
- Una consulta del ID absorbido devuelve 410 y el ID principal; MCP ofrece error estructurado `MERGED` con `target_id`. Nuevas modificaciones del archivo se bloquean.
- Incluida la guía MCP en la imagen Docker para que sus recursos funcionen dentro del contenedor.
- Validación aislada de versiones obsoletas, conservación de candidaturas/fechas/enlaces/acciones/eventos y bloqueo por URL absorbida. No se han fusionado ofertas reales como prueba.
- Migración 010 aplicada en Neon y preservación comprobada por comparación íntegra de las cinco tablas de seguimiento antes/después. Contenedor web reconstruido y actualizado; formulario revisado en navegador con los datos reales sin ejecutar fusiones. API/MCP aislados superados (24 segundos) y 15 pruebas unitarias de dominio, evaluación y MCP.

### Codex dentro de Docker verificado — 13/11/2026

- Detectado en prueba real un fallo de conexión de Codex pese a sesión autenticada: la imagen slim carecía de `/etc/ssl/certs`. Node alcanzaba el servicio, pero Codex no conseguía consultar modelos ni completar la petición.
- Dockerfile instala `ca-certificates` del repositorio Debian oficial. No se deshabilita TLS ni se relaja el sandbox de solo lectura. Imagen reconstruida y web reiniciada.
- Extracción real directa del texto de Scalian ya autorizado: `Contrato indefinido`, evidencia literal `Contrato&#xa0;indefinido`, estado acreditado.
- Prueba completa lanzada mediante la misma API de la web: aplicación `58b808e7-5cfa-4360-95ef-621f979d8fa1`, ejecución n8n `6`, estado final `succeeded`, cierre automático, resultado y cita conservados en Neon, sin errores. El modelo se mantuvo en el valor guardado (predeterminado de Codex).
- La primera comprobación auxiliar de n8n (`90f22d1c-d7f2-4c3b-b1fc-7028d58d2e5a`, n8n `5`) terminó su tarea; se confirmó manualmente el cierre tras consultar su ejecución exitosa porque el lanzador de diagnóstico cerró su conexión antes del callback. La segunda prueba anterior acredita el cierre automático del servicio permanente.
- Admisión restaurada a pausada con control de revisión; ninguna oferta ni candidatura creada, editada o enviada por estas pruebas. No acredita una búsqueda con finalistas A/B ni reparto completo.
- Referencia oficial de autenticación en dispositivos sin interfaz y Docker: https://learn.chatgpt.com/docs/auth . El archivo de sesión sigue montado en solo lectura; su renovación se hace desde el Mac como documenta README.

### Resumen de auditoría e informe completos — 13/11/2026

- Informe y dashboard muestran total computable frente al objetivo, clases A/B/C/pistas, B computables y no computables y encaje entre finalistas que cuentan. Se advierte si predominan los encajes débiles.
- Las C aparecen en tabla breve con puesto/empresa, causa, evidencia y fuente. Las B explican expresamente si cuentan; la fecha real de comprobación se incorpora desde el documento conservado.
- El resumen se persiste en el resultado de auditoría y se recalcula tras cambios de historial; API y MCP lo devuelven junto con la ejecución sin inventar nuevas decisiones.
- Ocho pruebas unitarias superadas y búsqueda integral en esquema Neon temporal superada (79 segundos), incluyendo caída de una B del cómputo tras inscripción y actualización del resumen.
- Imagen web reconstruida y desplegada. Informe real de Scalian regenerado desde registros existentes, sin nuevas lecturas, llamadas al modelo ni cambios en ofertas de seguimiento.

## Criterios editables — 13 de noviembre de 2026

Las once reglas de comparación permiten editar nombre, instrucción singular y explicación de lo pendiente desde Configuración y MCP. La migración aditiva 011 guarda las reglas por configuración e ID, sin cambiar ofertas ni candidaturas. Los valores iniciales conservan el comportamiento anterior. Cada ejecución guarda las reglas en su snapshot; las antiguas sin reglas usan los valores originales. Se conservan la secuencia de once decisiones, el corte temprano y la validación de evidencia. Los IDs, la clasificación A/B/C/pista y los controles de identidad/historial son invariantes del motor.

Verificación: 35 pruebas sin base de datos pasan (4 integraciones omitidas en esa ejecución); integración MCP contra un esquema Neon aislado pasa, incluyendo edición, conservación al omitir reglas y rechazo de reglas incompletas/duplicadas. Migración 011 aplicada a Neon y web reconstruida en Docker; formulario desplegado comprobado en navegador, sin cambiar el perfil ni las ofertas reales. No se ha ejecutado una nueva búsqueda con reglas modificadas sobre ofertas reales.

## Reintentos acotados — 13 de noviembre de 2026

Migración aditiva 012: `model_retries` de 0 a 3, inicialmente 0. Editable desde el panel y MCP, versionado en Neon y copiado por ejecución. Solo las respuestas recibidas que fallen validación de extracción o comparación son elegibles. Cada intento es una nueva tarea singular del bucle de n8n sobre la misma fila, con intento persistido aparte; no se repite la ficha ni se borra evidencia. Los errores de transporte/sesión/cuota/tiempo agotado y los resultados inciertos mantienen revisión manual. Agotar el límite pausa la búsqueda. Contrato y análisis de ficha siguen sin reintento automático.

Verificación de reintentos: pruebas de integración MCP y búsqueda pasan sobre esquemas Neon aislados (90 segundos), incluyendo guardado por revisión, rechazo de límite fuera de rango, reintento de la misma tarea, agotamiento y pausa, recuperación manual, conservación de intentos e informe final. Suite sin base de datos: 35 pruebas pasan y 4 integraciones se omiten. Migración 012 aplicada a Neon, valor inicial 0; no se lanzaron llamadas nuevas a modelos ni se modificó el seguimiento real.

### Tiempo máximo de IA configurable

Migración aditiva 013, sin modificar ofertas. Panel, API y MCP admiten `model_timeout_seconds` de 5 a 120; cada ejecución conserva su valor. Ambos motores lo aplican. El máximo respeta los 145 segundos de los nodos HTTP existentes, sin republicar workflows. Pruebas locales: 36 correctas, 4 de integración omitidas sin credenciales en el comando general.

Verificación adicional: integración MCP HTTP contra esquema temporal de Neon correcta (30,8 s); confirma guardado de 30 segundos y rechazo de 121. Migración 013 aplicada en Neon. Web reconstruida en Docker; GET `/api/settings` devuelve 120, panel incluye el control y n8n responde 200. No se han ejecutado búsquedas ni consumido llamadas de IA para esta entrega. La programación periódica sigue pendiente.

### Programación periódica en n8n

Migración 014 aditiva: fila independiente de programación, revisión de configuración, intervalo, próxima fecha UTC y última comprobación/ejecución/error. Interfaz sencilla en Control y herramientas MCP `get_schedule` / `set_schedule`. Workflow 04 con Schedule Trigger cada minuto y una petición autenticada al puente; registrado en setup:n8n. La reserva y el avance de fecha comparten la transacción y el bloqueo de admisión con los lanzamientos manuales. Pausa global, historial pendiente, ejecución activa o incierta y perfil inválido impiden iniciar. No se recuperan múltiples intervalos perdidos. Desactivada por defecto; no se activa en producción durante la verificación.

Referencia de Schedule Trigger: https://github.com/n8n-io/n8n-docs/blob/main/docs/integrations/builtin/core-nodes/n8n-nodes-base.scheduletrigger/README.md

Verificación de programación: 38 pruebas locales correctas, 5 integraciones omitidas en el comando general; las integraciones específicas MCP HTTP, programación y regresión de búsqueda pasan en esquemas temporales eliminados (31,1 s / 9,2 s / 90 s). Se añadió un caso de configuración inválida y se repitió la prueba de programación, correcta en 9,3 s. Migración 014 aplicada; imagen web `4f6f2931c890fe7e7fc849401632545a048543ecf64491f2f2d21feaa760c6f3`. Workflow `empleoSchedule04` importado y publicado sin reimportar los otros tres. Tras reiniciar n8n, su reloj registró `2026-11-13T17:20:46.086Z`, estado `disabled`, sin última búsqueda; el número de ejecuciones del panel sigue en 6. Verificación del panel en navegador: formulario accesible, intervalo 1440, fecha local y programación desactivada. No se consumió cuota IA ni se crearon ofertas.

### Alternativas públicas de lectura

Migración 015 aditiva: opción versionada `public_alternatives` y tabla de lecturas por representación, con backfill explícito `legacy` para documentos anteriores. Plan de dos rutas máximo para un mismo ID público SmartRecruiters: API→HTML para fuentes corporativas y HTML→API si llega desde un agregador. No añade llamadas del modelo ni modifica la segmentación n8n: cada petición reutiliza el nodo singular `read` y otro `step_id`. No hay reintentos de una petición reservada ni de resultados inciertos. La siguiente ruta se encola únicamente tras una respuesta terminada no verificable. Se vuelve a comprobar el historial y el cupo antes de cada ruta. La reserva original cuenta una única ficha del mismo anuncio y permite completar la representación alternativa aun si esa reserva alcanzó el máximo. Otros portales sin adaptador verificable continúan como pistas.

Pruebas: 39 locales correctas y 6 integraciones omitidas en el comando general; integración específica de lectura correcta (20 s), MCP HTTP correcta (32,5 s) y regresión de búsqueda correcta (90,9 s), cada una en esquema temporal eliminado. La prueba de lectura acredita API 403→HTML verificado con max_openings=1, caché de tarea sin nuevas peticiones y bloqueo de la segunda ruta si aparece una candidatura. Comprobación pública sin IA de la oferta real Scalian 744000152675659: API HTTP 200 y ficha completa; HTML HTTP 200 sin ficha estructurada, correctamente no verificable. No se ha creado una oferta de prueba en producción.

Despliegue verificado: migración 015 aplicada; imagen web `dde3aec4eaa7c0de9cb56139cd0eaacba7e23d0270232cac26c795997b3b6211`. Panel en navegador `ready`, sin error, opción visible y activada para nuevas ejecuciones. GET settings 200. Huellas antes/después idénticas para opportunities (91), applications (86), publications (89), follow_up_actions (0) y opportunity_events (106). Programación periódica continúa desactivada. La prueba de lectura se repitió tras corregir la clasificación inmediata C de candidaturas detectadas entre rutas: correcta en 19,7 s, sin segunda petición ni nuevos datos reales.

### Auditoría de cierre

Inventario de requisitos y evidencia en `AUDITORIA.md`. Se detectan pendientes concretos de encaje independiente, continuidad entre ejecuciones y actualización por lotes de fichas incompletas, además de la validación real A/B. No se considera completa la entrega por tener pruebas unitarias verdes.

Corrección en verificación: migración 016 separa revisión/error de archivos del estado de análisis. Los fallos al escribir informes no deben convertir una búsqueda ya cerrada en fallo de IA. Se preparan ambos temporales antes de promocionarlos, se limpian residuos y se comprueba la revisión vigente. Las descargas no sirven un artefacto marcado incompleto o cambiado durante la lectura. La siguiente consulta regenera los archivos desde Neon sin nuevas lecturas ni IA.

Recuperación de informes verificada y desplegada: ver detalle reproducible en `AUDITORIA.md`. Migración 016 aplicada, integración HTTP/MCP con fallo real del segundo archivo correcta (35,5 s), regresión de búsqueda correcta (88,5 s). El informe real Scalian se regeneró sin IA y ambas descargas devolvieron 200 con revisiones 8/8. Quedan abiertos los demás puntos de la auditoría; no se declara completado el objetivo.

### Lotes con fichas incompletas

Corregido el contador compartido de lotes: cuenta documentos evaluados y lecturas que han terminado sin ficha verificable, incluyendo errores y exclusiones detectadas antes de una ruta alternativa. No cuenta una lectura alternativa pendiente ni una ficha completa que todavía se analiza. Los caminos de lectura, evaluación y salto manual reutilizan el mismo cálculo y la clave persistente `batch:N`; cada actualización mantiene prioridad anterior a la siguiente apertura. No requiere migración ni republicar n8n. En verificación: lotes exclusivamente incompletos, lote mixto de C por fecha e incompleta, caché y regresión de lectura/búsqueda.

Contador de lotes desplegado en imagen `3c4067e56cefa719efaec8b228b0f166f95291dcbb18697469a9aee51bf450ba`. Panel, settings, programación y salud de n8n HTTP 200; programación desactivada. Sin migración, búsquedas reales nuevas ni llamadas de IA.

### Encaje independiente

Migración 017 aditiva: `fit_instruction` versionada en el perfil. Nueva tarea singular `assess_fit` y salida del Switch n8n, después de las comparaciones y antes de evaluar; una exclusión previa evita esta llamada. Devuelve favorable/condicionado/débil/desconocido con cita, explica la brecha y alimenta ordenación, resumen e informes sin forzar C. Una valoración desconocida queda pendiente y no computa. Instrucción editable desde web y MCP; corrección manual `fit` con motivo/cita conserva el original. Reintentos de validación y salto manual conservan la cadena. Las ejecuciones anteriores sin esta instrucción mantienen la heurística original. En verificación: unitarias de B débil, C prevalente, desconocidos y citas; integración de configuración, reintento de valoración y corrección de encaje.

Encaje independiente verificado y desplegado: migración 017, 41 unitarias correctas, integraciones de búsqueda/MCP/lotes correctas y test de las 33 salidas n8n. Campo editable comprobado en navegador; workflow publicado y activado. Detalles en `AUDITORIA.md`. Permanecen continuidad entre ejecuciones y prueba real A/B; no se declara completo el objetivo.

### Continuidad entre búsquedas — desplegada 13/11/2026

Migración 018 y los cuatro workflows se publicaron. `recover_previous` recupera A/B anteriores compatibles con fuentes y consultas, revalida historial antes de leer y conserva IDs estables; `reuse_evidence` solo reutiliza extracciones con el mismo documento completo y contrato. Las decisiones, el encaje y la vigencia se revisan en cada ejecución. Ambas opciones se gestionan desde web y MCP. La auditoría documenta lo implementado y la comprobación operativa del panel. Sigue pendiente una búsqueda de integración que pruebe la continuidad completa y una búsqueda real con finalistas A/B; no se activaron la admisión ni la programación.
