#!/usr/bin/env python3
"""Calibra los umbrales del triage contra una tirada ya ejecutada.

    PGPASSWORD="..." python3 eval/calibrar_umbrales.py

Existe porque «los umbrales son valores de partida» es una excusa, no un limite. Cruza la tabla
`incidencias` con las etiquetas de `dataset.jsonl` y responde tres preguntas que deciden si el
mecanismo de seguridad hace algo o solo lo parece:

  1. ¿Separa la confianza lo correcto de lo incorrecto? (si no, mover el corte no arregla nada)
  2. ¿Cuanto cierra el sistema solo con cada umbral, y cuantas escaladas pierde por el camino?
  3. ¿Quien causa de verdad los escalados de mas: el umbral o la regla estatutaria de la seccion 6?

No lee `.env`: la contraseña entra por PGPASSWORD, igual que `run_eval.py`.
"""
import argparse, json, os, subprocess, sys
from pathlib import Path

PSQL = "/opt/homebrew/opt/postgresql@17/bin/psql"
RAIZ = Path(__file__).resolve().parent


def consulta(dsn_args):
    sql = ("select coalesce(json_agg(row_to_json(t)), '[]') from (select message_id, imputacion, confianza, "
           "fundamento, jsonb_array_length(coalesce(plazos_activos,'[]'::jsonb)) plazos from incidencias) t;")
    r = subprocess.run([PSQL, *dsn_args, "-t", "-A", "-c", sql], capture_output=True, text=True, env=os.environ)
    if r.returncode:
        sys.exit(f"psql fallo: {r.stderr.strip()}")
    return {f["message_id"]: f for f in json.loads(r.stdout)}


def cargar(dataset, filas):
    casos = []
    for linea in dataset.read_text(encoding="utf-8").splitlines():
        if not linea.strip():
            continue
        d = json.loads(linea)
        f = filas.get(d["message_id"])
        if not f:
            continue
        fuentes = {(x or {}).get("fuente") for x in (f["fundamento"] or [])}
        casos.append({
            "id": d["id"],
            "ok": f["imputacion"] == d["imputacion_esperada"],
            "conf": float(f["confianza"] or 0),
            "ley": "ley" in fuentes,
            "estatutos": "estatutos" in fuentes,
            "plazos": f["plazos"],
            "rev": d.get("revision_esperada", False),
        })
    return casos


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dataset", type=Path, default=RAIZ / "dataset.jsonl")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--user", default="n8n_user")
    p.add_argument("--db", default="n8n")
    a = p.parse_args()

    if not os.environ.get("PGPASSWORD"):
        sys.exit("falta PGPASSWORD en el entorno (ver cabecera del fichero)")

    casos = cargar(a.dataset, consulta(["-h", a.host, "-U", a.user, "-d", a.db]))
    if not casos:
        sys.exit("0 casos emparejados: ¿se ha ejecutado ya una tirada? (tabla `incidencias` vacia)")
    print(f"casos emparejados: {len(casos)}\n")

    print("=== 1. Poder discriminante de la confianza ===")
    alta = [c for c in casos if c["conf"] >= 0.9]
    baja = [c for c in casos if c["conf"] < 0.9]
    for nombre, sub in (("conf >= 0.90", alta), ("conf <  0.90", baja)):
        if sub:
            print(f"  {nombre}: n={len(sub):2}  acierto={sum(c['ok'] for c in sub)/len(sub)*100:5.1f}%")
    if alta and baja:
        delta = sum(c["ok"] for c in alta)/len(alta) - sum(c["ok"] for c in baja)/len(baja)
        print(f"  diferencia: {delta*100:+.1f} puntos"
              f"{'   <- demasiado poca para apoyar una decision en ella' if abs(delta) < 0.15 else ''}")

    print("\n=== 2. Barrido de umbral (solo afecta a lo que la regla estatutaria no para ya) ===")
    print("  umbral | cierra solo | de esos, mal | escaladas perdidas")
    for u in (0.5, 0.6, 0.7, 0.8, 0.9, 0.95):
        cierra = [c for c in casos if c["conf"] >= u and not c["estatutos"]]
        perdidas = [c for c in cierra if c["rev"]]
        print(f"   {u:4.2f}  |     {len(cierra):2}      |      {sum(1 for c in cierra if not c['ok']):2}      "
              f"| {len(perdidas)} {sorted(c['id'] for c in perdidas)}")

    print("\n=== 3. Quien causa los escalados de mas ===")
    por_regla = [c for c in casos if c["estatutos"]]
    print(f"  casos con cita estatutaria: {len(por_regla)} de {len(casos)}  "
          f"-> escalados de mas atribuibles solo a la regla: {sum(1 for c in por_regla if not c['rev'])}")
    # La alternativa evidente es escalar solo cuando la clausula va sola, sin articulo legal que
    # la respalde. Se mide aqui en vez de discutirse: libera muchos casos, pero pierde escaladas.
    libera = [c for c in casos if c["estatutos"] and c["ley"]]
    perdidas = sorted(c["id"] for c in libera if c["rev"])
    print(f"  si la regla exigiera cita estatutaria SIN articulo legal: libera {len(libera)} casos, "
          f"pero pierde {len(perdidas)} escaladas {perdidas}")

    print("\n=== 4. ¿Se dispara el umbral asimetrico (0.9 sin plazo)? ===")
    zona = [c for c in casos if c["plazos"] == 0 and not c["estatutos"] and 0.7 <= c["conf"] < 0.9]
    print(f"  casos en la franja donde el 0.9 escala y el 0.7 no: {len(zona)} {sorted(c['id'] for c in zona)}"
          f"{'   <- regla sin efecto observado en esta tirada' if not zona else ''}")


if __name__ == "__main__":
    main()
