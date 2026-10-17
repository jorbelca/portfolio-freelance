# Demo 5 — Cualificación y asignación de leads

Grafo LangGraph que investiga leads, aplica una rúbrica de cualificación y registra tanto las decisiones automáticas como los casos que necesitan revisión. Los borradores de primer contacto se guardan en GreenMail y no se envían a los prospectos.

## Demostración en vídeo

[![Cualificación de leads con LangGraph](https://img.youtube.com/vi/4A5IdsmL5N0/hqdefault.jpg)](https://www.youtube.com/watch?v=4A5IdsmL5N0)

## Flujo

1. Valida y normaliza los datos de entrada del lead.
2. Obtiene una ficha de empresa desde el catálogo local `fichas.json` y reúne señales web con `buscar_senales` mediante un bucle ReAct.
3. Cualifica como `caliente`, `tibio`, `frio` o `sin_cualificar` contra [`rubrica-cualificacion-leads.md`](rubrica-cualificacion-leads.md).
4. Aplica validaciones deterministas, deduplicación en SQL y un gate de confianza. Los casos dudosos se registran en la cola con su motivo.
5. En la ruta V2, asigna los leads `caliente` que superan el gate y redacta un borrador de correo en GreenMail para revisión.

El grafo tiene dos modos funcionales: V1 termina con cualificación y cola de revisión; V2 añade asignación y redacción del borrador.

## Evaluación

El dataset contiene 30 leads etiquetados manualmente. En `--sin-llm`, el juicio queda fijado para comprobar reglas, gate, persistencia y trazabilidad: **30/30**. Una corrida de referencia con modelo real sobre evidencia fija obtuvo **27/30 etiquetas (90 %), 23/30 reglas (77 %) y 21/30 resultados de enrutado a cola (70 %)**. Son métricas distintas y no se deben combinar; corresponden a una ejecución sobre datos sintéticos.

`SALTAR_INVESTIGACION=1` fija las señales web del dataset para hacer reproducible la evaluación del modelo. No sustituye `ficha_empresa`, que continúa leyendo el catálogo local. Consulta [eval/README.md](eval/README.md) para la definición de métricas y los comandos.

## Componentes

- **LangGraph y Python:** orquestación de investigación, cualificación, validación y salida.
- **PostgreSQL:** leads, cola, asignaciones y log de decisiones.
- **OpenRouter:** modelo para investigación/cualificación y redacción.
- **GreenMail:** buzón local de borradores.
- `test_rubrica.py`, `eval/dataset.jsonl` y `eval/run_eval.py`: pruebas y evaluación.

## Ejecución local

La base de datos se comparte con las demos anteriores. Inicializa PostgreSQL y el esquema de `init-leads-tables.sql`, configura las variables de conexión y, si quieres usar el modelo, la clave de OpenRouter. Desde `5/`:

```bash
docker compose -f ../1/docker-compose.yml up -d
psql -h 127.0.0.1 -U n8n_user -d n8n -f init-leads-tables.sql
python3 test_rubrica.py
python3 procesar_leads.py --sin-llm
python3 eval/run_eval.py --dry-run
```

Para comparar los resultados persistidos con el dataset, ejecuta `python3 eval/run_eval.py` después de procesar los leads. [eval/README.md](eval/README.md) describe el orden de preparación, los dos modos de evaluación y cómo limpiar una corrida previa.

## Límites

La ficha empresarial y el dataset son sintéticos; la investigación web depende del acceso externo y de las señales disponibles en cada corrida. La rúbrica es específica del escenario de prueba. Los correos quedan en un servidor local de pruebas y no se entregan a destinatarios reales.
