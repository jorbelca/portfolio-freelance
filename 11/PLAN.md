# Plan de implementación — búsqueda y seguimiento de empleo

Estado actualizado: 11 de noviembre de 2026.

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

Los workflows disponibles extraen contrato o analizan una ficha aportada en 15 tareas. Todavía no realizan búsquedas ni clasifican ofertas. N029 conserva la candidatura y sus dos URLs; ninguna prueba genera ofertas en el seguimiento real. La ejecución real de contrato previa sigue conservada.

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
