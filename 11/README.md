# 11 — Control del workflow de empleo

Plan y estado de implementación: [PLAN.md](PLAN.md). Modelo de dominio y casos de uso: [MODELO.md](MODELO.md).

Consola local para configurar, ejecutar y supervisar módulos de n8n en Docker, con parámetros y resultados en PostgreSQL remoto de Neon. Ofrece el mismo control mediante MCP para asistentes LLM. El seguimiento de empresas, procesos, publicaciones y candidaturas ocupa una sección secundaria. Los módulos de extracción usan Codex autenticado con ChatGPT.

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

Abre http://127.0.0.1:3210. Registra tus candidaturas y rechazos anteriores. La configuración `history_ready` conserva tu confirmación de que has terminado esa carga. La búsqueda automática se implementará en la siguiente entrega.

## Centro de control y n8n

La pantalla inicial controla el workflow: muestra la conexión del motor, permite o pausa nuevas ejecuciones, ejecuta el módulo disponible y consulta resultados y errores. «Configurar búsqueda» edita los parámetros con formularios; «Seguimiento de ofertas» es la sección secundaria. No hay datos de demostración. Cada fila muestra un único estado: Pendiente, Inscrito, Rechazado o Descartado. El desplegable guarda al seleccionar y registra el cambio en el historial. «Detalles» abre el formulario dentro de la fila para editar notas, enlaces y acciones. Los estados técnicos anteriores se conservan en la base de datos y MCP; guardar sin cambiar el estado visible conserva sus detalles originales. La columna «Fechas» muestra alta, inscripción y último cambio de estado. Marcar por primera vez como Inscrito registra automáticamente la fecha actual; se puede corregir en «Detalles». Las fechas históricas desconocidas no se muestran en la lista; los cambios de estado se fechan automáticamente desde la migración 004, sin deducir fechas anteriores. Editar notas o enlaces no cambia la fecha de estado. La columna «Enlaces» muestra todas las publicaciones; «Añadir URL a esta oferta» vincula otros portales al mismo proceso y mantiene su exclusión de búsquedas.

Desde `11`, ejecuta `npm run setup:n8n`. El comando arranca Docker, instala una credencial Header Auth desde `N8N_TOKEN`, importa y publica ambos workflows y reinicia n8n para registrar el webhook. No imprime el secreto y elimina el archivo temporal del contenedor. Repetir el comando reemplaza ambos workflows y esta credencial por la versión del repositorio: guarda antes cualquier edición realizada en el editor de n8n.

Abre [el panel](http://127.0.0.1:3210) y permite nuevas ejecuciones. Pega una descripción real y elige «Analizar ficha» (15 tareas) o «Extraer solo contrato». Cada tarea guarda dato, cita literal y estado antes de avanzar. El dashboard permite seleccionar una ejecución y ver su progreso y evidencias. El panel crea una ejecución persistente; n8n recibe su identificador por webhook autenticado y llama al servicio local, que ejecuta `codex exec` con la sesión ChatGPT del usuario del Mac. n8n no recibe esa sesión. El modelo se toma de la copia de configuración de la ejecución, después de `CODEX_MODEL` y finalmente de Codex. El prompt general y los límites de búsqueda todavía no se consumen en este módulo acotado.

[El editor n8n](http://localhost:5678/workflow/empleoContract01) permite inspeccionar los nodos y sus ejecuciones; puede pedir completar el acceso de propietario. La imagen está fijada por digest (n8n 2.34.6). Workflows y credenciales persisten en SQLite en el volumen `portfolio-11_n8n_data`; la configuración funcional, las ejecuciones del panel y las ofertas persisten en Neon.

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

## Trabajo pendiente del plan

Identificadores y alias de ATS, fusión de duplicados, búsqueda y lectura de fuentes, extracciones estructuradas por requisito, reglas A/B/C, cupos, reanudación automática, auditoría e informes. Las ejecuciones persistentes de contrato y análisis de ficha ya están conectadas. El contenido original de `source_prompt` se conserva como referencia editable. Esta entrega usa exclusivamente Neon para el historial y no consulta Obsidian. La extracción de contrato todavía no consume ese prompt general, tiene una instrucción acotada propia.

## Validación de esta entrega

Migraciones 001–003 aplicadas en Neon, pruebas unitarias y prueba SQL en esquema temporal revertido. Una ejecución auténtica de contrato del anuncio de [Scalian](https://jobs.smartrecruiters.com/scalian/744000093272285-desarrollador-a-backend-java-microservicios) completó panel → n8n → Codex → Neon, con revisión 1 e ID de n8n 1. Se guarda como ejecución del módulo, no como oferta recomendada ni candidatura. No acredita el encaje o vigencia del puesto para la búsqueda.

Desde el navegador se comprobó el guardado de los mismos parámetros como revisión 2, conservando los valores y la revisión 1 de la ejecución anterior, la navegación al seguimiento con cero ofertas y la pausa de nuevos lanzamientos. Comprobaciones HTTP con aserciones: repetir la petición original devuelve la ejecución existente (202), cambiar su documento devuelve 409, lanzar otra durante la pausa devuelve 409 y llamar al webhook sin credencial devuelve 403. Esta comprobación inicial no creó ofertas; posteriormente se registró N029 por petición del usuario. El panel se deja con nuevas ejecuciones pausadas.

MCP se verificó con el cliente oficial en ambos transportes, incluido stdio desde `/tmp`: 21 herramientas, recursos y prompt operativo. Un cambio parcial que conservaba los valores creó la revisión 3; la revisión obsoleta devolvió CONFLICT, y repetir la ejecución auténtica existente no inició otra. La prueba aislada verificó edición parcial, estados y versiones, publicaciones, bloqueo de historial, acciones, paginación y autenticación. La web incluye una pestaña con configuraciones copiables y atributos estables para automatización por navegador. No se ha registrado el servidor en la configuración global de ningún cliente.

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

