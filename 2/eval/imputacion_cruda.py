#!/usr/bin/env python3
"""Acierto del MODELO antes de los controles deterministas de 'Parsear y Aplicar Controles'.

La tabla incidencias guarda la imputacion ya reescrita por las reglas, asi que no
sirve para saber si un fallo es del modelo o del codigo. Esto lee la salida cruda
del agente desde execution_data y la compara con dataset.jsonl.

Uso: PGPASSWORD=... python3 eval/imputacion_cruda.py [--desde ID_EJECUCION]
"""
import argparse
import csv
import json
import os
import re
import subprocess
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
CSV_MAX = 10 ** 9


def descargar(desde):
    sql = ("copy (select ed.data from execution_data ed "
           "join execution_entity e on e.id=ed.\"executionId\" "
           "join workflow_entity w on w.id=e.\"workflowId\" "
           f"where w.name like 'Demo B1%' and e.id>{int(desde)}) to stdout with (format csv)")
    r = subprocess.run(["psql", "-h", "127.0.0.1", "-U", "n8n_user", "-d", "n8n", "-At", "-c", sql],
                       capture_output=True, text=True, env=os.environ)
    if r.returncode != 0:
        sys.exit(f"psql fallo: {r.stderr.strip()}")
    return r.stdout


def extraer(datos_csv):
    """caso -> {imputacion, confianza, fuentes} leyendo el formato 'flatted' de n8n."""
    csv.field_size_limit(CSV_MAX)
    res = {}
    for (raw,) in csv.reader(datos_csv.splitlines()):
        d = json.loads(raw)
        # En flatted los valores string son indices dentro del propio array.
        D = lambda v: d[int(v)] if isinstance(v, str) and v.isdigit() and int(v) < len(d) else v
        caso = next((m.group(1) for s in d if isinstance(s, str)
                     for m in [re.fullmatch(r"<(i\d+)@demo\.local>", s)] if m), None)
        # La salida cruda lleva imputacion+fundamento+confianza pero NO decidido_por:
        # eso solo lo pone el nodo de controles, que es justo lo que queremos excluir.
        sal = next((el for el in d if isinstance(el, dict)
                    and {"imputacion", "fundamento", "confianza"} <= set(el)
                    and "decidido_por" not in el), None)
        if not caso or not sal:
            continue
        fuentes = {D(D(fr).get("fuente")) for fr in (D(sal.get("fundamento")) or [])
                   if isinstance(D(fr), dict)}
        res[caso] = {"imputacion": D(sal["imputacion"]), "confianza": D(sal["confianza"]),
                     "fuentes": sorted(f for f in fuentes if f)}
    return res


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--desde", default=0, help="Solo ejecuciones con id mayor que este")
    args = p.parse_args()

    esperado = {r["id"]: r for r in (json.loads(l) for l in (AQUI / "dataset.jsonl").open())}
    res = extraer(descargar(args.desde))
    if not res:
        sys.exit("No he encontrado ninguna salida de agente. Revisa --desde.")

    ok = okna = nna = 0
    rotos = []
    for c, r in res.items():
        e = esperado[c]["imputacion_esperada"]
        if not esperado[c]["ambiguo"]:
            nna += 1
        if r["imputacion"] == e:
            ok += 1
            if not esperado[c]["ambiguo"]:
                okna += 1
            if "estatutos" in r["fuentes"] and e != "mixto":
                rotos.append(c)

    print(f"Acierto del modelo (crudo): {ok}/{len(res)} = {100 * ok / len(res):.1f}%")
    print(f"  no ambiguos: {okna}/{nna} = {100 * okna / nna:.1f}%")
    cita = sorted(c for c, r in res.items() if "estatutos" in r["fuentes"])
    print(f"  cita estatutos: {len(cita)}/{len(res)} {cita}")
    if rotos:
        print(f"  ACERTABA y la regla estatutaria lo reescribiria: {rotos}")

    print("\ncaso | esperada    | modelo      | conf | fuentes")
    for c, r in sorted(res.items(), key=lambda x: int(x[0][1:])):
        e = esperado[c]["imputacion_esperada"]
        marca = "OK" if r["imputacion"] == e else ""
        print(f"{c:5}| {e:11} | {r['imputacion']:11} | {r['confianza']:4} | "
              f"{','.join(r['fuentes']) or '-':16} {marca}")


if __name__ == "__main__":
    main()
