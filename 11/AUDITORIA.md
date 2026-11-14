# Auditoría de cierre del workflow y la web

Fecha: 14 de noviembre de 2026. Objetivo todavía abierto.

Fuentes de requisitos: petición del usuario, cambios posteriores del chat y prompt íntegro conservado en `defaults.json → source_prompt`. Los requisitos de seguimiento en Neon y gestión manual de ofertas prevalecen sobre la prohibición del prompt de guardar ofertas en portales externos: la aplicación no guarda ni postula en esos portales.

## Evidencia por requisito

| Requisito | Evidencia actual | Resultado |
| --- | --- | --- |
| Proyecto y plan conservados en el repositorio | Carpeta `11`, `PLAN.md`, `MODELO.md`, README y MCP | Implementado |
| Arrancar web y n8n juntos con Docker | `compose.yaml`, dos servicios con reinicio persistente; despliegues y HTTP reales documentados en PLAN | Verificado |
| PostgreSQL remoto normalizado | Migraciones SQL, entidades separadas de empresa/proceso/publicación/candidatura/acciones/eventos; Neon real | Verificado; preservar datos existentes |
| Web centrada en configurar/controlar n8n | Vistas Control, Configuración, Seguimiento e Integraciones; navegador real | Verificado; conexión, control pausado, cero ejecuciones activas, tres módulos conectados, 34 tareas de búsqueda y seis ejecuciones cargadas desde Neon |
| Elegir motor, modelo y parámetros | Codex por sesión, OpenAI por clave, catálogo, revisión y snapshot; perfil, fuentes, criterios, límites, cuotas, reintentos y tiempo máximo editables | Implementado; conexión API real sin verificar por falta de clave configurada |
| Configurar variables sin editar JSON | Formularios para perfil, tecnologías, idiomas, fuentes, consultas, criterios, motor y límites; secciones avanzadas plegadas con resumen y selector de modelo visible | Verificado visualmente en `127.0.0.1:3210`; todos los campos siguen editables y JSON es solo lectura |
| Segmentar para un modelo de menor capacidad | 15 extracciones y 11 comparaciones individuales; esquema estricto, cita literal y persistencia por tarea; nodos autenticados n8n | Verificado estructuralmente y recorrido real con Codex; la validación de citas no garantiza corrección semántica |
| Programación desde panel y MCP | `schedule.js`, workflow 04, reserva atómica, exclusión mutua y heartbeat real | Verificado; desactivada |
| Pausar, reanudar, cancelar y resolver fallos | Estado persistente, intentos conservados, recuperación incierta, controles y tests de integración | Verificado en los casos cubiertos por tests; completar revisión de todos los tipos de tarea |
| Fácil control por LLM/MCP | 42 herramientas, HTTP y stdio, validación estricta, versiones y errores recuperables; cliente oficial SDK en tests | Verificado con un cliente concreto del SDK; configuración HTTP/stdio publicada para clientes compatibles |
| Seguimiento sencillo desde la lista | Desplegable Pendiente/Inscrito/Rechazado, estilos y fechas, edición sin perder candidatura previa | Verificado |
| Múltiples URLs por proceso y duplicados | Publicaciones, aliases, fusión explícita y reversible en orden inverso; conserva snapshots y auditoría | Verificado en integración aislada; no se fusionaron ofertas reales durante las pruebas |
| Fuente del historial del workflow | Consultas de exclusión de identidad y candidatura contra Neon; no lee `Agenda/DONE.md`, Obsidian ni su procedencia | Solo Neon. Los datos importados antes permanecen como filas ordinarias; se evalúan por su estado guardado, igual que cualquier otra oferta |
| Excluir procesos ya inscritos o rechazados antes de abrir | Cruce por identidad/empresa/título antes de reservar y antes de cada ruta; revalidación antes de cierre | Verificado en tests; no se repiten lecturas reservadas |
| Fuente del historial usado por el workflow | Consultas por identidad, candidatura y estado desde Neon | Solo Neon; el usuario excluye `Agenda/DONE.md` del workflow |
| No inventar datos, citas ni candidaturas | Runtime sin seed de ofertas; fixtures solo en pruebas aisladas; sin envío de formularios/correos | Verificado por código y casos reales conservados |
| Ficha, candidatura y requisitos | Navegación Google/Bing con Chrome MCP; HTML/texto visible; formulario inspeccionado sin completar; requisitos comparados con el perfil | Verificado con navegador simulado y fixtures; requiere un agente conectado a Empleo MCP y Chrome DevTools MCP para ejecución real |
| 100 fichas, lotes de 5 y reparto 13+7 | Reservas previas, contador persistente, cupos independientes, cierre con déficit y prioridad por cupo | Límites y cupos probados; actualización por lotes incompletos y mixtos verificada |
| País y antigüedad acreditados | `postingCountry`, `publicationAge`, fechas imposibles/futuras y límite inclusivo de 45 días | Verificado en pruebas unitarias |
| Causas definitivas C y B con pendientes | 11 reglas editables, clasificación y cómputo separados; exclusiones prevalecen | Verificado en pruebas; se necesitan finalistas reales A/B para ampliar evidencia del recorrido |
| Encaje favorable/condicionado/débil independiente | Tarea singular `assess_fit`, instrucción editable, cita, explicación de brecha y corrección manual; preferencias en `rankCandidate` | Verificado y desplegado; B débil y desconocidos probados, snapshots anteriores preservados |
| Continuidad entre ejecuciones | Migración 018, proceso estable, recuperación A/B por fuente/consulta, revalidación de historial, reutilización literal de extracciones y correcciones condicionadas por evidencia/perfil | Implementada y desplegada; configuración y 34 operaciones n8n visibles. Integración de `recover` en esquema temporal verificada: deduplica aliases, excluye candidaturas aplicadas antes de abrir, reutiliza extracción/cita y recalcula con corrección heredada. Sin búsquedas ni modelos reales |
| Informe y registro tras lotes y correcciones | Markdown/JSON, revisiones de historial, revalidación y enlaces; clases y déficits separados | Verificado en integración; recuperación de archivos desplegada |
| Recuperación de artefactos sin repetir análisis | Migración 016, revisión de archivos, error separado, regeneración y HTTP 503 en vez de entregar archivos desactualizados | Verificado y desplegado: callback de cierre, 503, reparación y pérdida de archivo probados; informe real Scalian regenerado |
| Entrega de 20 resultados reales 13+7 | Las búsquedas reales conservadas terminaron en C; el sistema informa el déficit | No acreditado. No equivale a demostrar finalistas reales ni a cumplir el objetivo de resultados |

## Incidencias concretas que faltan cerrar

1. Resuelto: recuperación de informes cuando falla la promoción del segundo archivo y cuando se pierde un archivo ya generado. Prueba HTTP/MCP correcta y despliegue confirmado.
2. Resuelto: actualización por cada lote terminado, incluidas fichas incompletas y errores, antes de abrir la siguiente ficha. Integración de lotes incompletos y mixtos correcta.
3. Resuelto: evaluación de encaje separada, instrucción editable, brecha con cita y corrección manual. Integraciones y despliegue verificados.
4. Resuelto en integración aislada: continuidad dentro de una ejecución, incluidos recuperación A/B, exclusión de candidaturas ya aplicadas antes de abrir, deduplicación de alias, reutilización de una extracción con la misma cita e impacto de la corrección heredada en la evaluación. La prueba completa el orquestador con portales y modelos simulados en un esquema temporal de Neon que se elimina al finalizar. No valida la calidad semántica de ofertas reales.
5. Ampliar la prueba real con una ficha compatible A/B y revisar cobertura de España/resto de Europa. Un déficit honesto es una salida válida de ejecución; no acredita haber encontrado 13+7.
6. Resuelto: inventario contrastado con el código, la suite 49/49 y el estado desplegado; la búsqueda real por navegador sigue pendiente en el punto 5.

No se marca el objetivo completo mientras quede trabajo o evidencia pendiente. Los resultados de pruebas aisladas no se presentan como ofertas reales.

## Verificación de la corrección de artefactos

Pruebas locales: 39 correctas, 6 integraciones omitidas en el comando general. Integraciones específicas: búsqueda persistente correcta (88,5 s) y HTTP/MCP correcta (35,5 s tras añadir el callback de cierre con fallo de disco). La prueba fuerza un directorio en el destino del segundo archivo; la tarea audit termina como succeeded, el análisis queda cerrado, se conservan las tareas y el error se limita a los archivos. La descarga da 503, no quedan temporales y se recuperan ambos archivos al retirar el bloqueo. La pérdida posterior de informe.md también se recupera sin aumentar la revisión del análisis ni ejecutar tareas.

Migración 016 aplicada. Imagen desplegada `697146486065271a2769d5a8809bd0a69cfd4799154f92999737227a9b4d8e8a`. Comprobación real sobre la búsqueda Scalian `5d0d271e-168b-4881-b249-4566bdc3fb40`: estado succeeded, revisión de informe 8 y de archivos 8, error nulo, Markdown y JSON HTTP 200; n8n health HTTP 200. No se llamó al modelo ni se ejecutó una nueva búsqueda.

## Verificación de lotes

39 pruebas locales correctas, 7 integraciones omitidas en el comando general. Integraciones específicas de lotes (54,5 s), lectura alternativa (23 s) y búsqueda persistente (90,7 s) correctas en esquemas temporales eliminados. El informe intermedio se escribe después de cinco fichas no verificables y antes de la sexta apertura; una segunda ejecución prueba el lote mixto con una C por fecha y una ficha incompleta. La alternativa pendiente y el análisis todavía en curso no adelantan el lote. Cada lote conserva una sola tarea persistida, sin llamadas del modelo en las pruebas de lecturas fallidas.

Contador de lotes desplegado en imagen `3c4067e56cefa719efaec8b228b0f166f95291dcbb18697469a9aee51bf450ba`. Panel, settings, programación y salud de n8n HTTP 200; programación desactivada. Sin migración, búsquedas reales nuevas ni llamadas de IA.

## Verificación del encaje independiente

41 pruebas locales correctas y 7 integraciones omitidas en el comando general. Integraciones específicas: búsqueda completa con una B de encaje débil, reintento de validación y corrección manual a favorable (101,7 s); configuración MCP con edición y preservación al omitir `fit_instruction` (35,7 s); regresión de lotes (53,4 s). Unitarias: C prevalece, encaje desconocido no computa, cita inventada/valor inválido se rechazan y snapshots antiguos siguen compatibles. El test estructural comprueba las 33 salidas del Switch y cada nodo autenticado.

Migración 017 aplicada. Imagen web `40f41690c01d8a0fa6464277698cf8de4947825afba1fd05b855c344038cdfc4`. Workflow de búsqueda actualizado y publicado en n8n, que activa los cuatro workflows tras reiniciar. Panel en navegador ready, instrucción visible y editable de 722 caracteres, sin error. API real anuncia 33 operaciones y `assess_fit`; conexión n8n correcta. Admisión y programación siguen desactivadas. No se llamaron modelos ni se crearon ofertas reales durante esta entrega.

## Continuidad y actualización del seguimiento — 13/11/2026

Migración 018 aplicada a Neon: añade `process_id`, `prior_candidate_id` y `publication_key` sin eliminar registros, además de `recover_previous` y `reuse_evidence` activos por defecto. El workflow publicado `empleoSearch03` contiene 34 operaciones singulares, incluida `recover`; la interfaz MCP y el panel exponen ambas opciones. Se agrupan las observaciones por proceso/alias dentro de la ejecución, se priorizan A anteriores al truncar y los informes registran qué extracción se reutilizó. Las correcciones exigen el mismo documento y cita literal; las decisiones dependientes del perfil también exigen el perfil anterior.

Despliegue web `sha256:d2e2914ca38e2cb1a1166242c3aaad09d73c954c763991b6ac9aa7c1aa744123`; web y n8n siguen en ejecución con `restart: unless-stopped`. El botón global «Actualizar estado» ahora recarga también las ofertas cuando se está en «Seguimiento». Comprobación no destructiva en navegador: aplicación `ready`, 91 ofertas leídas, llamada GET a ofertas al actualizar y mensaje de éxito. Admisión y programación permanecen desactivadas. No se inició búsqueda ni se modificó ninguna oferta o candidatura. No se ejecutaron pruebas automatizadas en este turno; continuidad requiere una integración real antes de darse por verificada.

## Revisión del arranque y del seguimiento — 14/11/2026

Se arrancó el stack con `docker compose up -d --build web n8n`. Ambos contenedores quedaron `Up`; la imagen web local actual es `sha256:f9188470cf1663ff52c804ea5532bbcfed901e32667d6cb35a8a0677a13779b5`. El panel respondió desde `127.0.0.1:3210`, `/api/runtime` informó `databaseConfigured: true` y la consulta de seguimiento devolvió las ofertas de Neon.

En el navegador, «Actualizar estado» refrescó el panel y cargó 91 ofertas; el primer registro conservó su estado real. Esto confirma la recarga del panel, no un cambio de estado. No se usó una oferta real como dato de prueba: un PATCH de inscripción/rechazo añade historial y puede bloquear búsquedas futuras. `public/app.js` separa el error de guardado de los errores al refrescar; la escritura de estado está cubierta en `test/offer-state.test.js` y el flujo HTTP/MCP en `test/mcp-api.test.js`, pero no se ejecutaron pruebas en esta revisión.

La actualización de un estado real sigue sin verificación de extremo a extremo en esta sesión. Se corrigió el caso en que un fallo al recargar después de guardar podía dejar deshabilitado el selector: el `finally` ahora cubre tanto la recarga de la oferta como la del panel. El contenedor sirvió este código y devolvió HTTP 200 en `/api/runtime`; la comprobación no cambió candidaturas. También siguen pendientes la búsqueda de integración de continuidad y la prueba adicional de cobertura real indicada arriba; no se lanzaron búsquedas ni llamadas de modelo. La versión Docker incluye la corrección de `previousFinalists` que evita que una observación anterior sin evaluación oculte una finalista evaluada.

## Alineación de flechas en desplegables — 14/11/2026

Se sustituyó la flecha nativa del navegador por dos gradientes CSS posicionados explícitamente en el estilo global de `select`. La vista Seguimiento muestra la flecha del filtro y de los estados centrada y alineada al borde derecho; aplica también al resto de desplegables. Imagen web reconstruida `sha256:f2e8eea6735643df68b1def640a32814cbeeb4e7b3df9f39f8fb8b5a0378c26e`. Comprobación visual en el navegador; no se modificaron datos.

## Filtro inicial de seguimiento — 14/11/2026

La lista abre con «Inscrito» seleccionado y muestra solo las ofertas inscritas; «Todos», «Pendiente» y «Rechazado» siguen disponibles. Verificación visual en el panel: 68 inscritas mostradas de 91 ofertas, sin alterar registros. Incluido en la imagen Docker `sha256:2b79df93e49784eae52d7f763b80149372f2e887c80e655cc313290001b7a3a0`.

## Cobertura local de continuidad — 14/11/2026

Se añadieron tres pruebas unitarias para priorizar A y deduplicar procesos/URLs, reutilizar extracciones solo con evidencia válida y heredar correcciones solo con documento, cita y perfil compatibles. `node --test test/continuity.test.js`: 3 correctas. La cobertura detectó que comparar toda la configuración impedía heredar correcciones válidas al cambiar opciones de búsqueda; ahora se comparan solo los campos del perfil que participan en la evaluación. El contenedor actualizado respondió HTTP 200 en `/api/runtime`. Estas pruebas usan un cliente simulado, sin Neon, portales ni modelos; la integración `recover`, que entonces quedaba pendiente, se verificó en el bloque siguiente.

## Integración de continuidad — 14/11/2026

`node --env-file=.env --test test/search.test.js`: correcta (159,3 s) en esquema temporal de Neon, eliminado en `finally`. La ejecución recuperó dos finalistas de tres observaciones, preservó los aliases, excluyó una candidatura enviada antes de reservar lectura, reutilizó la extracción de empresa solo con el mismo documento/cita/contrato e incorporó una corrección de encaje válida al recalcular la evaluación. Descubrimiento, lectura y modelo usaron funciones simuladas; no se inició búsqueda real, no hubo llamadas de IA y no se alteraron ofertas del esquema de producción.

## Dashboard conectado — 14/11/2026

Verificación en navegador tras esperar la carga asíncrona: n8n conectado; control de nuevas ejecuciones pausado; cero ejecuciones activas; módulos contrato, extracción (15 tareas) y búsqueda (34 tareas) conectados; historial de seis ejecuciones; configuración v7 con historial confirmado; programación desactivada. No se inició búsqueda ni se modificó configuración.

## Simplificación de la configuración — 14/11/2026

La primera vista ahora muestra puestos buscados, un resumen del perfil, fuentes/reglas avanzadas y el selector de proveedor/modelo. Las listas extensas, criterios, límites y prompt original quedan plegados; los resúmenes reflejan la configuración cargada. Si un campo requerido plegado no es válido, su bloque se abre para señalarlo. Imagen web reconstruida y vista en el navegador `127.0.0.1:3210`; no se guardó configuración ni se ejecutó una búsqueda. No se ejecutaron pruebas automatizadas.

## Captura por navegador y comprobación de candidatura — 14/11/2026

La integración activa de búsqueda utiliza solo Google/Bing navegados con Chrome DevTools MCP. Las entradas anteriores sobre APIs de Greenhouse, Lever y SmartRecruiters describían un diseño descartado y se eliminan de las instrucciones vigentes. Los formatos de identidad que puedan seguir en la base sirven para deduplicar enlaces vistos en el navegador; no conectan con esos servicios.

La tarea `discover` recoge resultados visibles del buscador; `read` conserva una ficha pública completa; `browser_apply` inspecciona la página pública del canal para el puesto concreto. Los requisitos obligatorios del anuncio pasan después por tareas pequeñas que comparan citas literales con el perfil. Una ficha que no pueda leerse o un formulario no accesible queda pendiente y fuera del cómputo. No se inicia sesión, no se rellenan campos ni se envía candidatura.

La comprobación del canal registra el formulario vacío, los campos obligatorios y bloqueos como login, CAPTCHA o cierre. Si la página redirige a otro dominio, la identidad del puesto y la empresa deben aparecer en el texto visible aportado. `accessible` exige que el formulario esté visible; no afirma que la candidatura se haya completado o enviado.

Límite operativo: Docker y n8n no controlan por sí solos el Chrome del Mac. Un agente que ejecute la búsqueda necesita Empleo MCP y Chrome DevTools MCP. El workflow consulta solo Neon. Los registros importados previamente desde la agenda permanecen como datos ordinarios de la base y no se vuelve a leer la nota.

## Suite completa de integración — 14/11/2026

`node --env-file=.env --test --test-reporter=spec`: **49 correctas, 0 fallidas, 0 omitidas**. Se ejecutaron migración/normalización, MCP HTTP, programación, lectura y formulario públicos, búsqueda persistente, lotes, continuidad, bloqueo por historial, informes, tareas, identidad, fusiones reversibles y validación de fuentes. Las integraciones usan esquemas temporales eliminados o transacciones revertidas en Neon; las fuentes, documentos y respuestas del modelo son fixtures. No se inició una búsqueda, no se visitaron ofertas y no se consumió cuota de IA.

Durante esta pasada se alinearon los fixtures con la configuración vigente: MCP aplica todas las migraciones hasta la 021, programación usa `browser:google`, y la prueba de búsqueda procesa los `precheck` pendientes antes del cierre. Ningún dato del seguimiento real fue alterado.

## Reinicio de servicios Docker — 14/11/2026

Con cero ejecuciones activas y admisión/programación apagadas, se reiniciaron `web` y `n8n`. Ambos contenedores volvieron a estado `running`; el navegador quedó en `ready`, `/api/workflow` devolvió HTTP 200 y confirmó n8n disponible con módulos contrato, extracción y búsqueda. Neon conservó las 91 oportunidades y el estado pausado; no hubo búsqueda ni cambios en ofertas.

## Respuesta nula del modelo y fusiones reversibles — 14/11/2026

El parser de respuestas OpenAI ignora con seguridad bloques `null` en `output` o `content`; se añadió una regresión para ambos lugares. También se serializan como JSON los enlaces movidos al guardar el snapshot de fusión. La migración 021 está aplicada y permite deshacer fusiones en orden inverso. Suite completa: 49/49; Neon conserva 91 ofertas, 86 candidaturas y ningún esquema temporal de prueba. La web y n8n están en ejecución. El error del parser se corrigió y se cubrió con respuesta simulada, pero no se reprodujo desde el proveedor configurado en una búsqueda real; ninguna búsqueda fue iniciada.

## Revisión del error visible en la web — 14/11/2026

Abrí una pestaña nueva en `127.0.0.1:3210/#configuration`: la aplicación cargó hasta `ready`, sin errores de consola; la configuración servida ofrece Google/Bing por navegador. No pude reproducir `Cannot read properties of null (reading 'type')`. Una pestaña previa conservaba la interfaz antigua en memoria. Los cuatro JSON de n8n no contienen nodos sin `type` ni conexiones colgantes. El editor de n8n abre su pantalla de inicio de sesión, sin ese error; no se introdujeron credenciales. No se lanzó el workflow ni se modificaron datos. Sigue pendiente identificar el clic/pantalla exactos si el error reaparece; la búsqueda real por navegador permanece sin ejecutar.


## Cierre de revisión de implementación — 14/11/2026

Se revisaron el plan, la consola web, los cuatro workflows y sus pruebas sobre los cambios existentes. La consola bloquea el lanzamiento de búsqueda si el historial no está confirmado, sin impedir el análisis aislado de textos; el siguiente paso dirige a la configuración. Los errores al consultar la tarea de navegador se muestran con opción de actualizar, en lugar de ocultarse como si no hubiera tarea. La espera distingue buscador, ficha y formulario público, y respeta la pausa. Las tareas completadas con resultado nulo no rompen la vista.

Verificación en esta sesión: suite completa previa a estas correcciones, 49/49, sin omitidas, incluidas las siete integraciones en esquemas temporales de Neon. Después de los cambios: suite local 44 correctas y siete integraciones omitidas; dos regresiones nuevas para bloqueo de lanzamiento y resultados nulos. Sintaxis JavaScript y `git diff --check` correctos. La integración HTTP añade comprobación de entrega de los módulos JavaScript de la web.

Web reconstruida en Docker y carga comprobada en navegador: n8n conectado, seis ejecuciones históricas, cero activas, admisión pausada y programación desactivada. No se modificaron ofertas ni configuración, no se lanzaron búsquedas reales ni llamadas de IA. La validación con ofertas reales A/B y cobertura España/Europa continúa pendiente; no se sustituye por fixtures ni se declara cumplido el reparto 13+7.

Comprobación posterior final: `node --env-file=.env --test --test-reporter=spec test/mcp-api.test.js test/workflow-state.test.js`: 3/3 correctas, ninguna omitida. Incluye API/MCP aislada, entrega HTTP de los tres módulos JavaScript y las dos regresiones de consola.
