# 11 — Control del workflow de empleo

Plan y estado de implementación: [PLAN.md](PLAN.md). Modelo de dominio y casos de uso: [MODELO.md](MODELO.md).

Consola local para configurar, ejecutar y supervisar módulos de n8n en Docker, con parámetros y resultados en PostgreSQL remoto de Neon. Ofrece el mismo control mediante MCP para asistentes LLM. El seguimiento de empresas, procesos, publicaciones y candidaturas ocupa una sección secundaria. Los módulos de extracción usan Codex autenticado con ChatGPT.


## Entrega verificada — 12/11/2026

Panel: http://127.0.0.1:3210. Workflow n8n: http://localhost:5678/workflow/empleoSearch03. Migraciones 001–018 aplicadas en Neon.

Prueba real `5d0d271e-168b-4881-b249-4566bdc3fb40`, ejecución n8n 4: descubrimiento corporativo → ficha completa → 15 extracciones → 3 comparaciones → evaluación → lote → auditoría. 24 tareas sin errores; Scalian, Embedded Software Developer – Aerospace, clasificada C por titulación técnica universitaria obligatoria, con cita literal. Máximo una apertura; parámetros originales 100/5/45 días/13+7 restaurados y admisión nuevamente pausada. No se ha enviado candidatura ni añadido la ficha al seguimiento.

35 pruebas comprobadas, incluida una batería completa de 34 y la nueva prueba del lector corporativo. Las pruebas SQL/API/MCP usan esquemas aislados que se eliminan al terminar. El panel y sus formularios se verificaron en navegador, con estado ready y motor conectado.

## Panel local

El servicio puede arrancar sin `DATABASE_URL` para mostrar el estado de configuración. Hasta conectar Neon, los contadores permanecen sin datos y las operaciones de gestión quedan deshabilitadas.

## Arranque

Requiere Node 22, PostgreSQL de Neon y Codex CLI autenticado mediante `codex login`. Desde esta carpeta:

```sh
npm install
cp .env.example .env
```

Configura `DATABASE_URL` con las credenciales de Neon y `N8N_TOKEN` con un secreto propio. Usa una conexión con validación TLS. Después:

```sh
npm run migrate
npm start
```

Abre http://127.0.0.1:3210. Registra tus candidaturas y rechazos anteriores. La configuración `history_ready` conserva tu confirmación de que has terminado esa carga. La búsqueda automática está disponible en el módulo «Buscar → filtrar → presentar ofertas».

## Arrancar web y n8n juntos

Desde `11`, con Docker Desktop abierto y `.env` configurado:

```sh
docker compose up -d --build
```

Arranca ambos servicios: [web](http://127.0.0.1:3210) y [n8n](http://localhost:5678). Los dos usan `restart: unless-stopped`: vuelven al arrancar Docker salvo que los hayas detenido explícitamente. `docker compose down` detiene ambos; para recuperar el conjunto usa el comando anterior. No hace falta ejecutar `npm start` por separado. Tras modificar código, reconstruye con el mismo comando.

La imagen incluye Node, Codex CLI y certificados CA del sistema para las conexiones TLS de Codex. Monta únicamente `~/.codex/auth.json` y `models_cache.json` en lectura, nunca todo el directorio personal. Requiere esos archivos de una sesión Codex iniciada en el Mac; para renovar la sesión usa `codex login` en el Mac y recrea la web con `docker compose up -d --force-recreate web`. La clave API se lee de `.env`. Los informes permanecen en `11/reports`; Neon y el volumen de n8n conservan sus datos. Los puertos publicados siguen limitados a loopback.

## Centro de control y n8n

La pantalla inicial controla el workflow: muestra la conexión del motor, permite o pausa nuevas ejecuciones, ejecuta el módulo disponible y consulta resultados y errores. «Configurar búsqueda» edita los parámetros con formularios; «Seguimiento de ofertas» es la sección secundaria. No hay datos de demostración. Cada fila muestra un único estado: Pendiente, Inscrito o Rechazado. El desplegable guarda al seleccionar y registra el cambio en el historial. «Actualizar estado» vuelve a consultar el workflow y, en «Seguimiento», recarga también la lista y el detalle seleccionado. «Detalles» abre el formulario dentro de la fila para editar notas, enlaces y acciones. Los estados técnicos anteriores se conservan en la base de datos y MCP; guardar sin cambiar el estado visible conserva sus detalles originales. La columna «Fechas» muestra alta, inscripción y último cambio de estado. Marcar por primera vez como Inscrito registra automáticamente la fecha actual; se puede corregir en «Detalles». Las fechas históricas desconocidas no se muestran en la lista; los cambios de estado se fechan automáticamente desde la migración 004, sin deducir fechas anteriores. Editar notas o enlaces no cambia la fecha de estado. La columna «Enlaces» muestra todas las publicaciones; «Añadir URL a esta oferta» vincula otros portales al mismo proceso y mantiene su exclusión de búsquedas.

Desde `11`, ejecuta `npm run setup:n8n`. El comando arranca Docker, instala una credencial Header Auth desde `N8N_TOKEN`, importa y publica los cuatro workflows y reinicia n8n para registrar el webhook. No imprime el secreto y elimina el archivo temporal del contenedor. Repetir el comando reemplaza los cuatro workflows y esta credencial por la versión del repositorio: guarda antes cualquier edición realizada en el editor de n8n.

Abre [el panel](http://127.0.0.1:3210) y permite nuevas ejecuciones. Pega una descripción real y elige «Analizar ficha» (15 tareas) o «Extraer solo contrato». Cada tarea guarda dato, cita literal y estado antes de avanzar. El dashboard permite seleccionar una ejecución y ver su progreso y evidencias. El panel crea una ejecución persistente; n8n recibe su identificador por webhook autenticado y llama al servicio local, que ejecuta `codex exec` con la sesión ChatGPT configurada (en Docker se monta el archivo de autenticación del Mac en solo lectura). n8n no recibe esa sesión. El modelo se toma de la copia de configuración de la ejecución, después de `CODEX_MODEL` y finalmente de Codex. El prompt general y los límites de búsqueda todavía no se consumen en este módulo acotado.

[El editor n8n](http://localhost:5678/workflow/empleoSearch03) permite inspeccionar los nodos y sus ejecuciones; puede pedir completar el acceso de propietario. La imagen está fijada por digest (n8n 2.34.6). Workflows y credenciales persisten en SQLite en el volumen `portfolio-11_n8n_data`; la configuración funcional, las ejecuciones del panel y las ofertas persisten en Neon.

Pausar bloquea nuevos lanzamientos desde el panel; las tareas iniciadas continúan. La pausa no despublica el webhook. El servicio solo admite un lanzamiento activo, reclama cada tarea una sola vez y reconoce reintentos con el mismo identificador sin repetirla. Cada ejecución conserva revisión y copia de configuración. Una respuesta perdida o un reinicio deja el resultado como incierto y bloquea nuevos lanzamientos hasta documentar una comprobación manual de n8n. No hay reintentos automáticos ni cancelación de una llamada al modelo en curso.

Las tareas de Codex duran como máximo `CODEX_TIMEOUT_MS` (por defecto 120 segundos). El puente HTTP espera hasta 160 segundos; si se amplía el tiempo de Codex debe ajustarse también el timeout del nodo y del puente. Un fallo de autenticación, cuota o modelo queda visible. La ejecución usa sandbox de solo lectura y un directorio temporal aislado.

## Interfaces implementadas

- `POST /mcp` sirve MCP Streamable HTTP autenticado con `MCP_TOKEN`; el adaptador `src/mcp-stdio.js` ofrece stdio.
- `GET /api/integration` devuelve configuración de conexión copiable, sin secretos. Guía: [MCP.md](MCP.md).
- `GET/POST /api/offers` lista o registra procesos. Cada entrada distingue `availability`, `review_state` y `application_state`. Se reutiliza una empresa mediante `company_id`; sin ID se crea otra entidad.
- `PUT /api/offers/:id` actualiza la oferta con su `version` actual, devuelve 409 si cambió.
- `GET /api/offers/:id/events` consulta la cronología.
- `GET/POST /api/offers/:id/publications` consulta o añade enlaces alternativos del mismo proceso.
- `GET/POST /api/offers/:id/actions` consulta o añade acciones; `PUT /api/offers/:id/actions/:actionId` cambia una acción con su versión.
- `GET /api/companies` devuelve empresas; `GET /api/catalogs` devuelve estados permitidos.
- `GET/PUT /api/settings` consulta o actualiza configuración con `revision` para detectar concurrencia.
- `PATCH /api/settings` recibe `revision` y `patch`; conserva los campos omitidos, incluida la referencia original del perfil, y valida el cambio bajo bloqueo transaccional.
- `GET /api/offers/:id` obtiene el proceso actual; `PATCH /api/offers/:id` admite `version` y `patch` con cambios parciales.
- `POST /api/history/check` acepta `url`, `company` y `title`. Un enlace principal o alternativo resuelve al proceso. Cualquier candidatura, descarte personal o proceso pausado/cerrado/cubierto/cancelado produce `excluded: true`. Empresa/título sin enlace coincidente requiere revisión; un proceso conocido devuelve `already_known`.
- `GET /api/workflow` consulta conexión del motor, control de admisión y módulos disponibles.
- `PUT /api/workflow/control` cambia `enabled` con su `revision` actual.
- `GET/POST /api/workflow/runs` consulta las últimas 50 ejecuciones o lanza una con `id` UUID, `module: contract | extraction` y `text` real.
- `GET /api/workflow/runs/:id` recupera una ejecución por ID, incluidas sus tareas y resultados; `include_input=true` y `include_settings=true` permiten pedir entrada y snapshot explícitamente.
- `POST /api/workflow/runs/:id/resolve` cierra una incidencia incierta con un motivo documentado después de comprobar n8n.
- `POST /api/tasks/:taskId` es interno de n8n: requiere N8N_TOKEN y run_id activo con tarea permitida, orden y exclusión mutua. El contrato conserva su respuesta compatible. `POST /api/tasks/finish` cierra desde los resultados persistidos e identifica la ejecución n8n.

Los cambios en procesos, candidaturas y su evento se guardan en una transacción. Cambiar estados exige motivo. Volver a sin candidatura desde una candidatura registrada requiere una futura operación de corrección explícita; el editor ordinario lo rechaza. Las URLs duplicadas devuelven 409. El panel se sirve exclusivamente en loopback y rechaza otros orígenes y hosts. Las credenciales no llegan al navegador.

## Comprobación

```sh
npm test
python3 ../1/check_workflows.py workflows/01-contrato.json
```

Las migraciones están numeradas y registradas. La 002 normaliza el esquema y conserva las tablas anteriores como `legacy_*`; no se vuelven a importar al repetir el comando. Los formularios editan columnas tipadas y cupos relacionados. La 003 añade el control de admisión y las ejecuciones con exclusión mutua en PostgreSQL. Los eventos conservan snapshots JSON para auditoría.

Para probar la migración contra Neon sin tocar los datos de la aplicación: `node --env-file=.env --test test/migration.test.js`. Usa un esquema aislado dentro de una transacción siempre revertida. Las fixtures nunca se muestran en el panel.

Para probar operaciones MCP contra la API y Neon: `node --env-file=.env --test test/mcp-api.test.js`. Levanta una instancia en otro puerto y un esquema `test_mcp_*`, verifica que su conexión usa exclusivamente ese esquema y lo elimina al terminar. No crea datos en el seguimiento real ni llama al modelo.

La migración conserva registros y configuración existente. Para verificar Neon, ejecuta la migración y prueba alta, edición, recarga e historial desde el panel.

## Búsqueda conectada y límites

El módulo de búsqueda usa el perfil estructurado y sus habilidades/evidencias, idiomas, consultas, fuentes, exclusiones y prioridades. Descubre pistas en Arbeitnow, Arbeitnow UK, Remotive y fuentes corporativas configurables de SmartRecruiters (`smartrecruiters:Empresa:país`). El número máximo de páginas es editable por fuente. No confunde fragmentos de buscador con fichas completas.

Cada apertura se reserva en Neon antes de consultar la ficha. Se cruza el historial antes de abrir y al evaluar/cerrar. Quince extracciones y hasta once comparaciones independientes guardan citas literales; una causa C acreditada detiene las comparaciones restantes. Clasificación, cómputo, antigüedad, país y déficits se resuelven con código. Las B no se presentan como recomendadas.

El panel permite pausar entre tareas, reanudar, cancelar conservando datos, resolver identidades y corregir datos con evidencia. Cada corrección y cada intento quedan registrados. Marcar un proceso como inscrito o rechazado incrementa la revisión del historial; consultar de nuevo resultados/informe recalcula las filas y los cupos sin reabrir fichas. Los informes Markdown y registros JSON se generan por lote/cierre en `reports/<run_id>/`, excluidos de git.

Pendiente de validación general: una ejecución real con finalistas A/B y el reparto completo. Dos registros confirmados como el mismo proceso pueden fusionarse desde el detalle o MCP (`merge_offers`): se conservan URLs, acciones e historial, el absorbido queda archivado y se elige explícitamente la candidatura vigente. Las versiones de ambos evitan fusionar cambios obsoletos. No se consultan automáticamente Obsidian ni portales con sesión; Neon contiene el historial importado. La cobertura se limita a los adaptadores soportados. Las llamadas usan la sesión y cuota de Codex, sin garantía de disponibilidad de Luna.

## Validación de esta entrega

Migraciones 001–003 aplicadas en Neon, pruebas unitarias y prueba SQL en esquema temporal revertido. Una ejecución auténtica de contrato del anuncio de [Scalian](https://jobs.smartrecruiters.com/scalian/744000093272285-desarrollador-a-backend-java-microservicios) completó panel → n8n → Codex → Neon, con revisión 1 e ID de n8n 1. Se guarda como ejecución del módulo, no como oferta recomendada ni candidatura. No acredita el encaje o vigencia del puesto para la búsqueda.

Desde el navegador se comprobó el guardado de los mismos parámetros como revisión 2, conservando los valores y la revisión 1 de la ejecución anterior, la navegación al seguimiento con cero ofertas y la pausa de nuevos lanzamientos. Comprobaciones HTTP con aserciones: repetir la petición original devuelve la ejecución existente (202), cambiar su documento devuelve 409, lanzar otra durante la pausa devuelve 409 y llamar al webhook sin credencial devuelve 403. Esta comprobación inicial no creó ofertas; posteriormente se registró N029 por petición del usuario. El panel se deja con nuevas ejecuciones pausadas.

MCP se verificó con el cliente oficial en ambos transportes, incluido stdio desde `/tmp`: 30 herramientas, recursos y prompt operativo. Un cambio parcial que conservaba los valores creó la revisión 3; la revisión obsoleta devolvió CONFLICT, y repetir la ejecución auténtica existente no inició otra. La prueba aislada verificó edición parcial, estados y versiones, publicaciones, bloqueo de historial, acciones, paginación y autenticación. La web incluye una pestaña con configuraciones copiables y atributos estables para automatización por navegador. No se ha registrado el servidor en la configuración global de ningún cliente.

## Segmentación de la extracción

`workflows/02-extracciones.json` contiene 15 nodos, uno por dato, y un cierre desde Neon. `src/tasks.js` es el catálogo compartido de instrucciones; regenera el JSON con `node scripts/build-extraction-workflow.js` y publica con `npm run setup:n8n`. La migración 005 añade `workflow_tasks` sin alterar ofertas ni resultados previos.

n8n responde inmediatamente al lanzamiento largo y cierra por callback. Un fallo de extracción conserva el error y permite continuar con los demás datos; el estado final será fallido si hubo algún error. Los fallos de transporte del nodo detienen el flujo; una ejecución sin cierre se marca incierta al consultar el motor después del plazo de seguridad derivado del timeout y número de tareas. Un reinicio deja incierta la tarea en curso. No se reejecutan llamadas automáticamente.

Las 15 extracciones reciben solo el texto aportado y su instrucción acotada. No usan el prompt general para decidir acciones, no abren páginas ni verifican formularios y no clasifican A/B/C. Las citas se validan literalmente; el usuario debe revisar la interpretación. Validación automática: 17 pruebas, incluyendo concurrencia, resultados parciales, orden, recuperación, API y MCP, con fixtures únicamente en esquemas aislados de Neon.

## Prueba real del análisis de ficha

El 11/11/2026, con autorización expresa, la ejecución `ed04ae76-6267-4a64-bb20-360e3a0a32c5` completó las 15 tareas con el texto real de Scalian: n8n `2`, configuración v3, 92 segundos, seis datos con cita y nueve desconocidos. Todas las citas y los resultados agregados quedaron verificados contra la entrada y Neon; el dashboard mostró 15/15. Repetir el mismo ID devolvió el resultado existente sin otra ejecución. No se creó ninguna oferta ni candidatura; N029 y sus dos URLs se conservaron. La admisión quedó pausada. Esto verifica el análisis del texto, sin acreditar vigencia o elegibilidad del puesto.

## Importación del historial de Obsidian

Importación realizada el 11/11/2026 desde `Agenda/DONE.md` a Neon: 41 acciones reales, 40 ofertas distintas (35 inscritas y 5 descartadas). Se crearon 39 ofertas; las entradas de VoxJobs e InfoJobs se vincularon a N029, que ya existía. Todas quedan excluidas de nuevas búsquedas.

Se conservaron las líneas originales, identificadores públicos, enlaces y procedencia en eventos `obsidian_import`. Los nombres de portales no se convierten en empresas: se muestran como «Empresa no indicada» cuando corresponde. Las fechas tienen precisión de día; el timestamp UTC representa esa fecha civil, sin acreditar una hora. El alta refleja la importación, no el descubrimiento original.

Para importar una copia local de esa nota, revisar primero con `node scripts/import-obsidian.js /ruta/DONE.md` y aplicar con `node --env-file=.env scripts/import-obsidian.js /ruta/DONE.md --apply`. Se ejecuta en una sola transacción y conserva los estados actuales de las ofertas conocidas. Repetir líneas idénticas no crea registros nuevos. Una modificación de una entrada sin URL ni ID requiere revisión manual, pues no permite demostrar identidad automáticamente.


### Elegir motor y modelo
En Configuración → Motor, modelo y antecedentes se elige Codex (sesión local) o API de OpenAI. El catálogo de Codex procede de su caché local; admite un identificador manual. La API requiere `OPENAI_API_KEY` en `.env` y reiniciar el servidor. Su catálogo se consulta con esa clave; no todos los modelos admiten Responses y JSON Schema. No hay cambio automático de proveedor ante errores. Cada ejecución conserva proveedor y modelo en su snapshot.

La integración API utiliza [Responses con salida estructurada](https://developers.openai.com/api/docs/guides/structured-outputs), sin herramientas ni almacenamiento solicitado. La evidencia literal se valida igualmente tras recibir la respuesta.

Los criterios de evaluación se editan en **Configuración → Criterios de evaluación**: cada uno tiene nombre, instrucción y explicación del dato pendiente. Se aplican a las nuevas búsquedas, con la misma segmentación y validación de citas. MCP permite editarlos en `criteria` de la configuración de búsqueda.

**Reintentos de IA en búsquedas:** Configuración permite de 0 a 3 reintentos adicionales por tarea (por defecto 0). Solo se repite una extracción o comparación cuya respuesta recibida falle la validación de datos o citas. Cada intento queda registrado. Fallos de sesión, cuota, red, tiempo agotado o resultado incierto requieren revisión; no se repiten automáticamente lecturas, altas ni otras operaciones. Al agotar el límite, la búsqueda se pausa y conserva el avance. Los módulos de contrato y análisis de ficha mantienen recuperación manual.

El parámetro `model_timeout_seconds` permite fijar entre 5 y 120 segundos por tarea de IA (120 por defecto). Se guarda con revisión y se copia al iniciar cada ejecución; se aplica tanto a Codex como a OpenAI. El máximo mantiene margen frente al límite HTTP de n8n. Un tiempo agotado exige revisión manual y no consume reintentos automáticos.

Programación periódica: `get_schedule` y `set_schedule` (o sección «Búsqueda programada» del panel) permiten activar, fijar intervalo de 15 a 525600 minutos y próxima fecha UTC. Lee `revision` antes de guardar. El workflow n8n `empleoSchedule04` comprueba cada minuto usando la credencial del puente. La programación empieza desactivada. Respeta admisión global, historial confirmado y ejecuciones activas o inciertas. Los intervalos se cuentan desde el lanzamiento, sin ráfagas para recuperar fechas perdidas. Cambiar el intervalo en el panel no requiere republicar n8n. Deben estar arrancados Docker, n8n y la web. La programación autoriza consumo periódico del motor elegido; no envía candidaturas.

`GET/PUT /api/workflow/schedule` expone configuración y estado. `POST /api/workflow/schedule/tick` es exclusivo de `N8N_TOKEN`, no accesible con el token MCP ni con la cabecera del panel. La reserva de ejecución y el avance de fecha se confirman juntos en Neon; si falla el envío posterior a n8n, la ejecución queda incierta y bloquea nuevos lanzamientos hasta su revisión.

La opción `public_alternatives` (web y `patch_settings`, activada por defecto en nuevas ejecuciones) permite probar la API pública o la ficha HTML de SmartRecruiters cuando la primera representación es incompleta. Ambas deben identificar el mismo tenant y anuncio; no se siguen enlaces arbitrarios ni se emplean sesiones. Cada petición es una tarea `read` distinta, con reserva previa y resultado en `get_search_candidate → reads` y en el registro JSON. Las dos representaciones del mismo anuncio cuentan una sola ficha; otro anuncio o portal exige otra reserva. Se revalida el historial antes de cada petición. Respuestas incompletas o ambiguas siguen como pistas; no se convierte texto genérico en evidencia. Los snapshots antiguos sin esta opción conservan una sola ruta.

Referencia de la API pública: https://developers.smartrecruiters.com/reference/v1getposting

La generación de informes tiene estado independiente del análisis: `report_files_revision` y `report_files_error` aparecen en el estado de búsqueda. Un fallo de disco/permisos conserva los resultados y el cierre de la búsqueda; las siguientes consultas intentan regenerar solo Markdown/JSON desde Neon. Las descargas responden 503 mientras los archivos no correspondan a la revisión actual. Si un archivo ya generado se pierde, su siguiente descarga intenta reconstruirlo. Comprueba espacio/permisos de `11/reports`; no relances la búsqueda para reparar un informe.

Los lotes cuentan fichas terminadas, tanto evaluadas como incompletas o con error de lectura. Una representación alternativa pendiente no termina la ficha ni suma otra apertura. Al alcanzar `batch_size`, n8n ejecuta la actualización del informe antes de abrir la siguiente ficha. Una ficha completa espera a su evaluación antes de cerrar el lote; una lectura incierta conserva la revisión manual.

Las nuevas búsquedas incluyen una tarea independiente `assess_fit` tras las 11 comparaciones, salvo que ya exista una causa C. Valora favorable/condicionado/débil con cita literal; no excluye por sí sola. La instrucción `fit_instruction` se edita en perfil/configuración y por MCP. El encaje desconocido queda pendiente y fuera del cómputo hasta aclararlo. Informe, registro y panel muestran la valoración, su explicación y cita. `correct_search_candidate` admite `field: "fit"` con valor favorable, condicionado, débil o desconocido, cita y motivo. Las ejecuciones anteriores conservan su heurística hasta una corrección explícita. Máximo por ficha sin exclusión temprana: 15 extracciones + 11 comparaciones + 1 valoración de encaje. Se aplican los mismos reintentos acotados, tiempo máximo y recuperación manual.

## Continuidad entre búsquedas

La migración 018 añade un ID estable de proceso, el enlace a la observación anterior y claves de publicación. En Configuración del perfil puedes desactivar por separado `recover_previous` y `reuse_evidence` (ambos activos por defecto). Una búsqueda nueva recupera los A/B de la última observación que coincida con fuentes y términos habilitados, vuelve a comprobar el historial y relee la ficha. Candidaturas inscritas, rechazadas o descartadas quedan excluidas antes de reservar una lectura. Las observaciones del mismo proceso y sus URLs se agrupan para no abrirlas dos veces.

Si el texto completo y el contrato de extracción coinciden, se pueden reutilizar las 15 extracciones con sus citas y procedencia; las 11 decisiones y el encaje se evalúan de nuevo con el perfil actual. Las correcciones solo pasan a la observación nueva si su cita literal sigue en el mismo texto; las decisiones dependientes del perfil requieren además el mismo perfil. El ID de proceso y la observación anterior aparecen en resultados e informes. El workflow n8n incluye `recover` como operación singular.
