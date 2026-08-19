#!/usr/bin/env python3
"""Parchea la credencial de Gemini en una copia temporal de los workflows de la
Demo A, los importa en n8n y los reactiva.

Requisito previo: la credencial de Google Gemini (PaLM) tiene que existir ya en n8n.
Este script la busca por tipo en la base de datos y coge su id; nunca lee ni
imprime el valor de la key.

El modelo del CLASIFICADOR de la Demo A ya está migrado a OpenRouter directamente en
el repo (ver "Tarea 1 - Triage.json" y "Tarea 2 - RAG Citas.json", nodo "OpenRouter
Chat Model"): la free tier de Gemini no aguanta una tirada completa. Los EMBEDDINGS de
"Tarea 2 - RAG Citas.json" siguen siendo de Gemini a propósito: los vectores del
corpus del despacho se generaron con ese modelo y esa dimensión, y cambiarlos dejaría
el RAG sin resultados con todos los nodos en verde. Esos dos nodos de embeddings son
los que llevan el placeholder GEMINI_CRED_ID que este script sustituye.

El fichero del repo NUNCA se reescribe: el placeholder es la convención para no
publicar ids reales, así que la sustitución se hace sobre una copia en /tmp.
"""
import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
PLACEHOLDER = "GEMINI_CRED_ID"

# (fichero, id de workflow_entity). Los ids ya están dentro de cada JSON como "id" de
# nivel superior; se repiten aquí porque update:workflow los necesita en la línea de
# comandos y no los lee del fichero importado.
WORKFLOWS = [
    ("Tarea 1 - Triage.json", "94314623b60e4441"),
    ("Tarea 2 - RAG Citas.json", "bee472a8e629465a"),
    ("Error Handler.json", "2a89390fb7794f12"),
]


def credencial_gemini():
    """Devuelve (id, nombre) de la credencial de Google Gemini (PaLM). Nunca toca la columna data."""
    sql = "select id, name from credentials_entity where type='googlePalmApi' order by \"createdAt\";"
    passwd = subprocess.run(
        ["sh", "-c", "grep -m1 '^DB_POSTGRESDB_PASSWORD=' .env | cut -d= -f2-"],
        cwd=AQUI, capture_output=True, text=True, check=True).stdout.strip()
    r = subprocess.run(
        ["psql", "-h", "127.0.0.1", "-U", "n8n_user", "-d", "n8n", "-At", "-F", "\t", "-c", sql],
        env={**os.environ, "PGPASSWORD": passwd},
        capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"psql fallo: {r.stderr.strip()}")
    filas = [l.split("\t") for l in r.stdout.strip().splitlines() if l.strip()]
    if not filas:
        sys.exit("No hay ninguna credencial de tipo googlePalmApi en n8n.\n"
                  "Creala primero: http://localhost:5678 -> Credentials -> Create credential\n"
                  "-> buscar 'Google Gemini(PaLM) Api' -> pegar la API key -> Save. Luego vuelve a lanzar esto.")
    if len(filas) > 1:
        print(f"[aviso] hay {len(filas)} credenciales de Gemini; uso la mas antigua: {filas[0][1]}")
    return filas[0][0], filas[0][1]


def preparar_copia(nombre_fichero, cred_id, tmpdir):
    """Copia el JSON del repo a /tmp sustituyendo el placeholder por el id real.

    Sustitución de texto, no json.load+dump: así el resto del fichero (indentación,
    acentos, orden de claves) llega a n8n byte a byte igual que en el repo, y el
    fichero del repo en sí no se toca en ningún momento.
    """
    origen = AQUI / nombre_fichero
    texto = origen.read_text(encoding="utf-8")
    texto = texto.replace(f'"{PLACEHOLDER}"', f'"{cred_id}"')
    destino = Path(tmpdir) / nombre_fichero
    destino.write_text(texto, encoding="utf-8")
    return destino


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--sin-importar", action="store_true",
                   help="Solo valida y prepara las copias, no toca n8n")
    p.add_argument("--tmpdir", default=None,
                   help="Directorio donde dejar las copias parcheadas (por defecto, "
                        "uno temporal autolimpiado). Debe ser un directorio de scratch, "
                        "nunca la carpeta del repo.")
    args = p.parse_args()

    # Guardia de estructura + la regla del '=' (check 6 de check_workflows.py) sobre
    # los ficheros del repo, antes de tocar nada en n8n.
    subprocess.run([sys.executable, "check_workflows.py"], cwd=AQUI, check=True)

    cred_id, cred_nombre = credencial_gemini()
    print(f"Credencial Gemini: '{cred_nombre}' ({cred_id}) — se usa solo para los "
          f"nodos de embeddings, que siguen en Gemini.")

    def preparar_y_usar(tmpdir):
        copias = [(wf_id, preparar_copia(nombre, cred_id, tmpdir))
                  for nombre, wf_id in WORKFLOWS]

        if args.sin_importar:
            for wf_id, copia in copias:
                print(f"  preparado: {copia} (id={wf_id})")
            return

        for wf_id, copia in copias:
            destino_docker = f"/tmp/{copia.name}"
            subprocess.run(["docker", "cp", str(copia), f"1-n8n-1:{destino_docker}"], check=True)
            subprocess.run(["docker", "exec", "1-n8n-1", "n8n", "import:workflow",
                            f"--input={destino_docker}"], check=True)

    if args.tmpdir:
        Path(args.tmpdir).mkdir(parents=True, exist_ok=True)
        preparar_y_usar(args.tmpdir)
    else:
        with tempfile.TemporaryDirectory() as tmpdir:
            preparar_y_usar(tmpdir)

    if args.sin_importar:
        return

    # import:workflow DESACTIVA el workflow al reimportarlo ("Deactivating workflow ...").
    # Sin esto los tres se quedan parados y el trigger IMAP no lee nada.
    # update:workflow --active=true esta deprecado y por dentro ya delega en
    # publishVersion() (mismo codigo fuente); se usa publish:workflow directamente.
    for _, wf_id in WORKFLOWS:
        subprocess.run(["docker", "exec", "1-n8n-1", "n8n", "publish:workflow",
                        f"--id={wf_id}"], check=True)

    # n8n cachea los workflows activos en memoria: sin reiniciar sigue con el grafo
    # viejo (Gemini) o directamente sin el trigger registrado, y la reactivacion no
    # surte efecto hasta el próximo arranque.
    subprocess.run(["docker", "restart", "1-n8n-1"], check=True)
    print("n8n reiniciado y los tres workflows de la Demo A reactivados. "
          "Espera ~40s a que arranque antes de enviar el correo de prueba.")


if __name__ == "__main__":
    main()
