#!/usr/bin/env python3
"""Cambia el modelo del clasificador de B1 de Gemini a OpenRouter, y lo importa en n8n.

Requisito previo: la credencial de OpenRouter tiene que existir ya en n8n
(Credentials -> Create credential -> OpenRouter -> pegar la API key -> Save).
Este script la busca por tipo en la base de datos y coge su id; nunca lee ni
imprime el valor de la key.

Los embeddings SIGUEN siendo de Gemini a proposito: los vectores de
documentos_comunidad se generaron con ese modelo y esa dimension. Cambiarlos
dejaria la busqueda de estatutos sin resultados con todos los nodos en verde.
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
WORKFLOW = AQUI / "Tarea B1 - Triage Incidencias.json"
NODO_VIEJO = "Google Gemini Chat Model"
NODO_NUEVO = "OpenRouter Chat Model"
TIPO_NUEVO = "@n8n/n8n-nodes-langchain.lmChatOpenRouter"
# Gratis y con function calling segun /api/v1/models. El agente necesita tools
# dos veces (la tool de RAG y el format_final_json_response de n8n), asi que un
# modelo sin tools no sirve aunque conteste bien.
MODELO_POR_DEFECTO = "nvidia/nemotron-3-super-120b-a12b:free"
ID_B1 = "b1394623b60e4442"


def credencial_openrouter():
    """Devuelve (id, nombre) de la credencial de OpenRouter. Nunca toca la columna data."""
    sql = "select id, name from credentials_entity where type='openRouterApi' order by \"createdAt\";"
    passwd = subprocess.run(
        ["sh", "-c", "grep -m1 '^DB_POSTGRESDB_PASSWORD=' ../1/.env | cut -d= -f2-"],
        cwd=AQUI, capture_output=True, text=True, check=True).stdout.strip()
    r = subprocess.run(
        ["psql", "-h", "127.0.0.1", "-U", "n8n_user", "-d", "n8n", "-At", "-F", "\t", "-c", sql],
        env={**os.environ, "PGPASSWORD": passwd},
        capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"psql fallo: {r.stderr.strip()}")
    filas = [l.split("\t") for l in r.stdout.strip().splitlines() if l.strip()]
    if not filas:
        sys.exit("No hay ninguna credencial de tipo openRouterApi en n8n.\n"
                 "Creala primero: http://localhost:5678 -> Credentials -> Create credential\n"
                 "-> buscar 'OpenRouter' -> pegar la API key -> Save. Luego vuelve a lanzar esto.")
    if len(filas) > 1:
        print(f"[aviso] hay {len(filas)} credenciales de OpenRouter; uso la mas antigua: {filas[0][1]}")
    return filas[0][0], filas[0][1]


def parchear(modelo, cred_id, cred_nombre):
    w = json.loads(WORKFLOW.read_text())
    viejo = next((n for n in w["nodes"] if n["name"] in (NODO_VIEJO, NODO_NUEVO)), None)
    if viejo is None:
        sys.exit(f"No encuentro el nodo del modelo ni como '{NODO_VIEJO}' ni como '{NODO_NUEVO}'.")

    nuevo = {
        # maxTokens no es cosmetico: 'razonamiento' es la PRIMERA propiedad del esquema, asi que
        # un razonamiento largo se come el presupuesto y la respuesta se corta a media palabra
        # ("imputacion": "co). El parser la rechaza con 'Invalid JSON in model output' y el caso
        # cae a sin_clasificar aunque la clasificacion fuera correcta. Es lo que le paso a i21.
        "parameters": {"model": modelo, "options": {"maxTokens": 4096}},
        "type": TIPO_NUEVO,
        "typeVersion": 1,
        "id": "openrouter-model-b1",
        "name": NODO_NUEVO,
        "position": viejo["position"],
        "credentials": {"openRouterApi": {"id": cred_id, "name": cred_nombre}},
        # El free tier de OpenRouter devuelve 429/503 en hora punta igual que Gemini.
        # Sin reintentos se pierde el correo, porque el trigger IMAP marca \SEEN antes
        # de ejecutar el workflow.
        "retryOnFail": True,
        "maxTries": 3,
        "waitBetweenTries": 30000,
        # Agotados los reintentos, el fallo NO puede matar la ejecucion: el trigger IMAP ya marco
        # el correo como \SEEN y se perderia entero. Con esto el item baja igual y el nodo de
        # controles lo etiqueta 'sin_clasificar'. Verificado en runtime apuntando a un slug
        # inexistente: sin esta linea la ejecucion moria; con ella entra en la cola de revision.
        "onError": "continueRegularOutput",
    }
    w["nodes"] = [nuevo if n is viejo else n for n in w["nodes"]]

    # Las dos conexiones ai_languageModel tienen que ir al nodo nuevo: el agente y el
    # autoFix del Output Parser. Si solo se recablea el agente, el parser se queda sin
    # modelo y vuelve el "Model output doesn't fit required format".
    if NODO_VIEJO in w["connections"]:
        w["connections"][NODO_NUEVO] = w["connections"].pop(NODO_VIEJO)
    for v in w["connections"].values():
        for ramas in v.values():
            for rama in ramas:
                for c in rama or []:
                    if c.get("node") == NODO_VIEJO:
                        c["node"] = NODO_NUEVO

    destinos = [c["node"] for r in w["connections"].get(NODO_NUEVO, {}).get("ai_languageModel", [])
                for c in (r or [])]
    if sorted(destinos) != ["AI Agent Clasificador", "Output Parser Estructurado"]:
        sys.exit(f"El nodo del modelo no alimenta a los dos destinos esperados: {destinos}")

    WORKFLOW.write_text(json.dumps(w, indent=2, ensure_ascii=False) + "\n")
    return destinos


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--modelo", default=MODELO_POR_DEFECTO,
                   help=f"Slug de OpenRouter (por defecto {MODELO_POR_DEFECTO}). "
                        "Tiene que soportar tools.")
    p.add_argument("--sin-importar", action="store_true",
                   help="Solo parchea el fichero, no toca n8n")
    args = p.parse_args()

    cred_id, cred_nombre = credencial_openrouter()
    destinos = parchear(args.modelo, cred_id, cred_nombre)
    print(f"Nodo '{NODO_NUEVO}' -> modelo {args.modelo}, credencial '{cred_nombre}'")
    print(f"  alimenta: {', '.join(destinos)}")
    print("  embeddings: siguen en Gemini (los vectores ya estan generados con ese modelo)")

    subprocess.run([sys.executable, "check_workflows.py"], cwd=AQUI, check=True)

    if args.sin_importar:
        return
    subprocess.run(["docker", "cp", str(WORKFLOW), "1-n8n-1:/tmp/b1.json"], check=True)
    subprocess.run(["docker", "exec", "1-n8n-1", "n8n", "import:workflow", "--input=/tmp/b1.json"],
                   check=True)
    # import:workflow DESACTIVA el workflow al reimportarlo ("Deactivating workflow ...").
    # Sin esto B1 se queda parado y el trigger IMAP no lee nada.
    # update:workflow --active=true esta deprecado y por dentro ya delega en
    # publishVersion() (mismo codigo fuente); se usa publish:workflow directamente.
    subprocess.run(["docker", "exec", "1-n8n-1", "n8n", "publish:workflow",
                    f"--id={ID_B1}"], check=True)
    # n8n cachea los workflows activos en memoria: sin reiniciar sigue ejecutando el
    # grafo viejo con el nodo de Gemini, y la reactivacion no registra el trigger.
    subprocess.run(["docker", "restart", "1-n8n-1"], check=True)
    print("n8n reiniciado y B1 reactivado. Espera ~40s a que arranque antes de enviar el correo.")


if __name__ == "__main__":
    main()
