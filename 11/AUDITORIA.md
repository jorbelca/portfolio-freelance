# Auditoría de cierre del workflow y la web

Fecha: 13 de noviembre de 2026. Objetivo todavía abierto.

Fuentes de requisitos: petición del usuario, cambios posteriores del chat y prompt íntegro conservado en `defaults.json → source_prompt`. Los requisitos de seguimiento en Neon y gestión manual de ofertas prevalecen sobre la prohibición del prompt de guardar ofertas en portales externos: la aplicación no guarda ni postula en esos portales.

## Evidencia por requisito

| Requisito | Evidencia actual | Resultado |
| --- | --- | --- |
| Proyecto y plan conservados en el repositorio | Carpeta `11`, `PLAN.md`, `MODELO.md`, README y MCP | Implementado |
| Arrancar web y n8n juntos con Docker | `compose.yaml`, dos servicios con reinicio persistente; despliegues y HTTP reales documentados en PLAN | Verificado |
| PostgreSQL remoto normalizado | Migraciones SQL, entidades separadas de empresa/proceso/publicación/candidatura/acciones/eventos; Neon real | Verificado; preservar datos existentes |
| Web centrada en configurar/controlar n8n | Vistas Control, Configuración, Seguimiento e Integraciones; navegador real | Verificado |
| Elegir motor, modelo y parámetros | Codex por sesión, OpenAI por clave, catálogo, revisión y snapshot; perfil, fuentes, criterios, límites, cuotas, reintentos y tiempo máximo editables | Implementado; conexión API real sin verificar por falta de clave configurada |
| Segmentar para un modelo de menor capacidad | 15 extracciones y 11 comparaciones individuales; esquema estricto, cita literal y persistencia por tarea; nodos autenticados n8n | Verificado estructuralmente y recorrido real con Codex; la validación de citas no garantiza corrección semántica |
| Programación desde panel y MCP | `schedule.js`, workflow 04, reserva atómica, exclusión mutua y heartbeat real | Verificado; desactivada |
| Pausar, reanudar, cancelar y resolver fallos | Estado persistente, intentos conservados, recuperación incierta, controles y tests de integración | Verificado en los casos cubiertos por tests; completar revisión de todos los tipos de tarea |
| Fácil control por LLM/MCP | 35 herramientas, HTTP y stdio, validación estricta, versiones y errores recuperables; cliente oficial SDK en tests | Verificado con un cliente concreto del SDK; configuración HTTP/stdio publicada para clientes compatibles |
| Seguimiento sencillo desde la lista | Desplegable Pendiente/Inscrito/Rechazado, estilos y fechas, edición sin perder candidatura previa | Verificado |
| Múltiples URLs por proceso y duplicados | Publicaciones, identidades por portal/tenant, aliases, fusión explícita auditada y versiones | Verificado en integración aislada; no se fusionaron ofertas reales durante las pruebas |
| Importar ofertas reales de DONE.md y registrar casos del chat | `scripts/import-obsidian.js`, pruebas del importador y evidencia histórica en PLAN; N029 y Wiris registrados | Realizado previamente; no hay sincronización continua de Obsidian |
| Excluir procesos ya inscritos o rechazados antes de abrir | Cruce por identidad/empresa/título antes de reservar y antes de cada ruta; revalidación antes de cierre | Verificado en tests; no se repiten lecturas reservadas |
| Historial de Obsidian/versionado selectivo del prompt | La aplicación usa historial de Neon y su revisión transaccional, en sustitución de DONE.md | Adaptación explícita; no implementa consulta automática selectiva de Obsidian |
| No inventar datos, citas ni candidaturas | Runtime sin seed de ofertas; fixtures solo en pruebas aisladas; sin envío de formularios/correos ni escritura en Obsidian | Verificado por código y casos reales conservados |
| Ficha completa y alternativa pública | JSON-LD o API corporativa; SmartRecruiters API/HTML del mismo ID en tareas distintas y con resultados separados | Verificado; otros sitios sin adaptador fiable siguen como pistas |
| 100 fichas, lotes de 5 y reparto 13+7 | Reservas previas, contador persistente, cupos independientes, cierre con déficit y prioridad por cupo | Límites y cupos probados; actualización por lotes incompletos y mixtos verificada |
| País y antigüedad acreditados | `postingCountry`, `publicationAge`, fechas imposibles/futuras y límite inclusivo de 45 días | Verificado en pruebas unitarias |
| Causas definitivas C y B con pendientes | 11 reglas editables, clasificación y cómputo separados; exclusiones prevalecen | Verificado en pruebas; se necesitan finalistas reales A/B para ampliar evidencia del recorrido |
| Encaje favorable/condicionado/débil independiente | Tarea singular `assess_fit`, instrucción editable, cita, explicación de brecha y corrección manual; preferencias en `rankCandidate` | Verificado y desplegado; B débil y desconocidos probados, snapshots anteriores preservados |
| Continuidad entre ejecuciones | Migración 018, proceso estable, recuperación A/B por fuente/consulta, revalidación de historial, reutilización literal de extracciones y correcciones condicionadas por evidencia/perfil | Implementada y desplegada; configuración y 34 operaciones n8n visibles. Falta una búsqueda de integración para probar el recorrido completo |
| Informe y registro tras lotes y correcciones | Markdown/JSON, revisiones de historial, revalidación y enlaces; clases y déficits separados | Verificado en integración; recuperación de archivos desplegada |
| Recuperación de artefactos sin repetir análisis | Migración 016, revisión de archivos, error separado, regeneración y HTTP 503 en vez de entregar archivos desactualizados | Verificado y desplegado: callback de cierre, 503, reparación y pérdida de archivo probados; informe real Scalian regenerado |
| Entrega de 20 resultados reales 13+7 | Las búsquedas reales conservadas terminaron en C; el sistema informa el déficit | No acreditado. No equivale a demostrar finalistas reales ni a cumplir el objetivo de resultados |

## Incidencias concretas que faltan cerrar

1. Resuelto: recuperación de informes cuando falla la promoción del segundo archivo y cuando se pierde un archivo ya generado. Prueba HTTP/MCP correcta y despliegue confirmado.
2. Resuelto: actualización por cada lote terminado, incluidas fichas incompletas y errores, antes de abrir la siguiente ficha. Integración de lotes incompletos y mixtos correcta.
3. Resuelto: evaluación de encaje separada, instrucción editable, brecha con cita y corrección manual. Integraciones y despliegue verificados.
4. Verificar la continuidad en una búsqueda de integración: recuperación A/B, exclusión de una candidatura actual, deduplicación de alias, reutilización de citas y recálculo de decisiones.
5. Ampliar la prueba real con una ficha compatible A/B y revisar cobertura de España/resto de Europa. Un déficit honesto es una salida válida de ejecución; no acredita haber encontrado 13+7.
6. Contrastar de nuevo todo este inventario tras las correcciones y registrar sus pruebas finales.

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
