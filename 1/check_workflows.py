#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Valida la integridad estructural de los workflows n8n (JSON) de este proyecto.

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
  6. Todo parámetro con {{ }} empieza por '='. Sin el prefijo n8n no evalúa la
     expresión: la pasa como texto literal, sin error y con el nodo en verde (este
     guardia detectó el bug que invalidó 45 ejecuciones de la Demo B).

Uso:
    python3 check_workflows.py                        # revisa los 3 workflows del proyecto
    python3 check_workflows.py archivo1.json archivo2.json
"""

import json
import sys
from pathlib import Path

DEFAULT_FILES = [
    "Tarea 1 - Triage.json",
    "Tarea 2 - RAG Citas.json",
    "Error Handler.json",
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

    # 6. Todo parámetro con {{ }} empieza por '='. Sin el prefijo n8n no evalúa la
    #    expresión: la pasa como texto literal, sin error y con el nodo en verde.
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
