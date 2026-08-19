#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Valida la integridad estructural de los workflows n8n (JSON) de la Demo B.

Adaptado de la Demo A (1/check_workflows.py): misma lógica de conexiones, más dos
comprobaciones propias de esta demo (confidencialidad del RAG por comunidad y formato
de los correos), porque aquí romperlas tiene consecuencias distintas a un typo en un nodo:
una fuga de estatutos entre comunidades, o un correo que sale con el cuerpo vacío.

Editar `connections` a mano es la forma número uno de romper un workflow de n8n en
silencio: el JSON parsea, n8n lo importa, y el grafo está roto. `connections` está
indexado por NOMBRE de nodo, y su anidamiento es
    connections[nombreOrigen][tipo][índiceSalida][] = {node, type, index}
donde `tipo` puede ser 'main' o cualquier tipo de conexión de IA
('ai_languageModel', 'ai_memory', 'ai_tool', 'ai_outputParser', 'ai_embedding',
'ai_document', 'ai_textSplitter', ...). Comprobar solo 'main' deja huecos: los
subnodos de IA (modelo, memoria, tools, output parser, embeddings, text splitter)
solo conectan por esos otros tipos y aparecerían como huérfanos por error, y una
referencia rota en un tipo distinto de 'main' pasaría desapercibida.

Para cada fichero se comprueba:
  1. El fichero parsea como JSON.
  2. Toda clave de `connections` corresponde a un `nodes[].name` existente.
  3. Todo `.node` referenciado en cualquier profundidad de `connections` (cualquier
     tipo, no solo 'main') corresponde a un `nodes[].name` existente.
  4. No hay nombres de nodo duplicados.
  5. Ningún nodo (salvo triggers y sticky notes) queda huérfano: sin ninguna conexión
     de entrada NI de salida, en ningún tipo de conexión.
  6. [Demo B] Todo nodo vectorStorePGVector en modo 'retrieve-as-tool' o 'load' tiene
     un options.searchFilterJson no vacío que menciona comunidad_id. Es la comprobación
     de confidencialidad: sin este filtro, el RAG de estatutos devuelve fragmentos de
     TODAS las comunidades mezclados (ver Sticky Note junto a "IF Comunidad Resuelta"
     en Tarea B1).
  7. [Demo B] Todo nodo emailSend tiene emailFormat fijado a 'text', y ninguno usa
     operation: 'reply' (no existe en emailSend v2.1; solo 'send' y 'sendAndWait').

Uso:
    python3 check_workflows.py                        # revisa los 3 workflows del proyecto
    python3 check_workflows.py archivo1.json archivo2.json
"""

import json
import sys
from pathlib import Path

DEFAULT_FILES = [
    "Tarea B1 - Triage Incidencias.json",
    "Tarea B2 - Carga Estatutos.json",
    "Error Handler B.json",
]

# Nodos que, por naturaleza, no tienen entrada (triggers) o no tienen conexiones
# en absoluto (sticky notes) y por tanto quedan exentos del chequeo de huérfanos.
EXEMPT_TYPES = {
    "n8n-nodes-base.emailReadImap",
    "n8n-nodes-base.errorTrigger",
    "n8n-nodes-base.formTrigger",
    "n8n-nodes-base.manualTrigger",
    "n8n-nodes-base.scheduleTrigger",
    "n8n-nodes-base.webhook",
    "@n8n/n8n-nodes-langchain.chatTrigger",
    "@n8n/n8n-nodes-langchain.manualChatTrigger",
    "n8n-nodes-base.stickyNote",
}

VECTOR_STORE_TYPE = "@n8n/n8n-nodes-langchain.vectorStorePGVector"
MODES_REQUIRING_FILTER = {"retrieve-as-tool", "load"}

EMAIL_SEND_TYPE = "n8n-nodes-base.emailSend"

# Tipo de nodo -> nombre de la credencial que necesita. Un nodo añadido a mano (o por
# script) se queda sin ella sin que nada se queje hasta que la UI bloquea la publicación.
TYPES_REQUIRING_CREDENTIALS = {
    "n8n-nodes-base.postgres": "postgres",
    "n8n-nodes-base.emailSend": "smtp",
    "n8n-nodes-base.emailReadImap": "imap",
    VECTOR_STORE_TYPE: "postgres",
    # lmChatGoogleGemini se queda en el mapa aunque B1 ya use OpenRouter: el guardia
    # sigue valiendo para cualquier otro workflow que lo lleve.
    "@n8n/n8n-nodes-langchain.lmChatGoogleGemini": "googlePalmApi",
    "@n8n/n8n-nodes-langchain.lmChatOpenRouter": "openRouterApi",
    "@n8n/n8n-nodes-langchain.embeddingsGoogleGemini": "googlePalmApi",
}

# Ids que los ficheros llevaban como marcador. POSTGRES_CRED_ID, IMAP_CRED_ID y
# SMTP_CRED_ID resultaron ser ids reales en esta instancia; GEMINI_CRED_ID no.
PLACEHOLDER_CRED_IDS = {"GEMINI_CRED_ID", "CRED_ID", "REPLACE_ME"}


def check_workflow(path: Path) -> list[str]:
    errors: list[str] = []

    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as e:
        return [f"no se pudo leer el fichero: {e}"]

    # 1. El fichero parsea como JSON.
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        return [f"JSON inválido: {e}"]

    nodes = data.get("nodes", [])
    connections = data.get("connections", {})

    names = [n.get("name") for n in nodes]
    name_set = set(names)

    # 4. No hay nombres de nodo duplicados.
    seen = set()
    for n in names:
        if n in seen:
            errors.append(f"nombre de nodo duplicado: '{n}'")
        seen.add(n)

    # 2. Toda clave de connections corresponde a un nodo existente.
    for origen in connections:
        if origen not in name_set:
            errors.append(
                f"connections tiene una clave de origen que no existe como nodo: '{origen}'"
            )

    # 3. Todo .node en cualquier profundidad (cualquier tipo) corresponde a un nodo
    #    existente. De paso, construimos qué nodos tienen alguna conexión de salida
    #    y cuáles alguna de entrada, en CUALQUIER tipo, para el chequeo 5.
    have_outgoing: set[str] = set()
    have_incoming: set[str] = set()

    for origen, tipos in connections.items():
        if not isinstance(tipos, dict):
            errors.append(f"'{origen}': el valor de connections no es un objeto de tipos")
            continue
        for tipo, salidas in tipos.items():
            if not isinstance(salidas, list):
                errors.append(f"connections['{origen}']['{tipo}'] no es una lista de salidas")
                continue
            for salida in salidas:
                if salida is None:
                    continue  # salida vacía de un Switch/If (rama sin conectar): válido
                if not isinstance(salida, list):
                    errors.append(
                        f"connections['{origen}']['{tipo}'] contiene una salida que no es lista ni null"
                    )
                    continue
                for conexion in salida:
                    if conexion is None:
                        continue
                    destino = conexion.get("node") if isinstance(conexion, dict) else None
                    if origen in name_set:
                        have_outgoing.add(origen)
                    if destino in name_set:
                        have_incoming.add(destino)
                    else:
                        errors.append(
                            f"connections['{origen}']['{tipo}'] referencia un nodo destino "
                            f"que no existe: '{destino}'"
                        )

    # 5. Ningún nodo (salvo triggers y sticky notes) queda huérfano.
    for n in nodes:
        name = n.get("name")
        ntype = n.get("type")
        if ntype in EXEMPT_TYPES:
            continue
        if name not in have_outgoing and name not in have_incoming:
            errors.append(
                f"nodo huérfano (sin entrada ni salida en ningún tipo de conexión): "
                f"'{name}' ({ntype})"
            )

    # 6. Confidencialidad: vectorStorePGVector en retrieve-as-tool/load necesita
    #    options.searchFilterJson no vacío mencionando comunidad_id.
    for n in nodes:
        if n.get("type") != VECTOR_STORE_TYPE:
            continue
        params = n.get("parameters", {})
        mode = params.get("mode")
        if mode not in MODES_REQUIRING_FILTER:
            continue
        opciones = params.get("options", {})
        # Dos formas validas de filtrar: options.searchFilterJson (JSON) y
        # options.metadata.metadataValues (pares nombre/valor, la que usa la UI). El helper
        # getMetadataFiltersValues de n8n mira la segunda primero.
        search_filter = opciones.get("searchFilterJson") or "".join(
            f"{v.get('name')}={v.get('value')}"
            for v in opciones.get("metadata", {}).get("metadataValues", [])
        )
        name = n.get("name")
        if not search_filter or not isinstance(search_filter, str) or not search_filter.strip():
            errors.append(
                f"'{name}' (vectorStorePGVector, mode={mode!r}): falta "
                f"options.searchFilterJson — sin este filtro el RAG puede devolver "
                f"estatutos de OTRA comunidad (fuga de confidencialidad)"
            )
        elif "comunidad_id" not in search_filter:
            errors.append(
                f"'{name}' (vectorStorePGVector, mode={mode!r}): "
                f"options.searchFilterJson no menciona comunidad_id: {search_filter!r}"
            )
        elif params.get("tableName") != "documentos_comunidad":
            # Guardar desde la UI se ha llevado este parametro por delante una vez. Sin el, el
            # nodo cae a su default 'n8n_vectors', que no existe: el RAG deja de devolver nada
            # y el clasificador responde sin haber leido ningun estatuto.
            errors.append(
                f"'{name}' (vectorStorePGVector, mode={mode!r}): tableName es "
                f"{params.get('tableName')!r}, debe ser 'documentos_comunidad'"
            )
        elif "$json." in search_filter:
            # En un sub-nodo $json no es el item del nodo raiz: resuelve a undefined,
            # JSON.stringify omite la clave y el filtro se queda en "{}". Sin WHERE, el
            # RAG mezcla estatutos de todas las fincas y el nodo no da ningun error.
            errors.append(
                f"'{name}' (vectorStorePGVector, mode={mode!r}): el filtro usa $json en un "
                f"sub-nodo, donde resuelve a undefined y degrada a filtro vacio. Referencia "
                f"el nodo por nombre: $('Resolver Comunidad y Propietario').first().json"
            )

    # 7. Correos: emailFormat siempre 'text', y nunca operation: 'reply'.
    for n in nodes:
        if n.get("type") != EMAIL_SEND_TYPE:
            continue
        params = n.get("parameters", {})
        name = n.get("name")
        email_format = params.get("emailFormat")
        if email_format != "text":
            errors.append(
                f"'{name}' (emailSend): emailFormat es {email_format!r}, debe ser 'text' "
                f"— con 'html' (el valor por defecto) mailOptions.text no se rellena y el "
                f"correo sale con el cuerpo vacío"
            )
        operation = params.get("operation")
        if operation == "reply":
            errors.append(
                f"'{name}' (emailSend): operation: 'reply' no existe en emailSend v2.1 "
                f"(solo 'send' y 'sendAndWait')"
            )

    # 8. Todo nodo que hable con un servicio externo lleva credencial, y el id no
    #    es un placeholder sin sustituir. La UI de n8n bloquea la publicación con
    #    "1 node has issues" y no dice cuál; aquí sí.
    for n in nodes:
        ntype = n.get("type")
        needs = TYPES_REQUIRING_CREDENTIALS.get(ntype)
        if not needs:
            continue
        name = n.get("name")
        creds = n.get("credentials") or {}
        if needs not in creds:
            errors.append(
                f"'{name}' ({ntype}): sin credencial {needs!r} — n8n no deja publicar "
                f"el workflow y la UI no dice qué nodo es"
            )
            continue
        cred_id = creds[needs].get("id", "")
        if cred_id in PLACEHOLDER_CRED_IDS:
            errors.append(
                f"'{name}' ({ntype}): la credencial apunta al placeholder {cred_id!r}, "
                f"que no existe en credentials_entity"
            )

    # 9. Todo parámetro con {{ }} empieza por '='. Sin el prefijo n8n no evalúa la
    #    expresión: la pasa como texto literal, sin error y con el nodo en verde. Pasó
    #    en el prompt del agente, que recibió "{{ $('IMAP Email Trigger')... }}" en vez
    #    del correo y estuvo clasificando 45 incidencias sin leer ninguna.
    for n in nodes:
        name = n.get("name")
        for clave, valor in (n.get("parameters") or {}).items():
            if isinstance(valor, str) and "{{" in valor and not valor.startswith("="):
                errors.append(
                    f"'{name}': el parámetro {clave!r} contiene {{{{ }}}} pero no empieza "
                    f"por '=' — n8n lo manda como texto literal sin evaluarlo"
                )

    return errors


def main(argv: list[str]) -> int:
    files = argv[1:] or DEFAULT_FILES
    base = Path(__file__).resolve().parent
    overall_ok = True

    for f in files:
        p = Path(f)
        path = p if p.is_absolute() else base / f
        print(f"== {path.name} ==")
        errors = check_workflow(path)
        if errors:
            overall_ok = False
            for e in errors:
                print(f"  FALLO: {e}")
        else:
            print("  OK")

    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
