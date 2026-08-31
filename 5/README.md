# Demo 5 — Cualificación de leads → asignación → primer contacto

Grafo de agentes (LangGraph, Python) que reutiliza el esqueleto de la Demo 4 con otro juicio
en el centro: un lead entra, un agente lo investiga (bucle ReAct con dos tools), se cualifica
como `caliente`/`tibio`/`frio` **contra una rúbrica de negocio escrita y versionada**
(`rubrica-cualificacion-leads.md`), pasa por validación determinista (campos, email, dedup en
SQL) y un gate de confianza, y lo dudoso va a cola de revisión con motivo. Los `caliente` que
pasan el gate se asignan a un comercial y se les redacta el primer email citando el motivo de
encaje; el borrador queda en GreenMail, sin enviar. Log de motivos en todos los caminos.

Un solo repo, un solo grafo, dos actos: V1 (investigación + cualificación + cola) y V2 (V1 +
la cola de asignación/redacción de 2 nodos). `SALTAR_INVESTIGACION=1` inyecta una ficha de
empresa y unos fragmentos de búsqueda predefinidos por caso en vez de llamar a las tools, para
que el eval mida la clasificación con evidencia fija y reproducible (mismo patrón que el
`canned_extraccion` del `--sin-llm` de la Demo 4). Lo que se vende es el patrón, no el caso.

Construido con LangGraph, Postgres (reutiliza `../1/docker-compose.yml`), GreenMail y modelos
vía OpenRouter.
