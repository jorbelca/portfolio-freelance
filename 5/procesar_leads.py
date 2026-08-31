#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Corre el grafo de grafo_leads.py sobre los leads de eval/dataset.jsonl, en orden (importa
para la dedup: un lead solo es 'duplicado' si otro con el mismo email/empresa se procesó antes).

Modos (los dos inyectan evidencia del dataset, ninguno llama a red):
  SALTAR_INVESTIGACION=1  (env)  -> inyecta ficha + señales; el modelo SÍ clasifica.
  --sin-llm                      -> además inyecta hallazgos; salta también el modelo. Para
                                    probar grafo/rúbrica/gate/persistencia/log sin OPENROUTER_API_KEY.

Sin ninguno, investigacion_agente lanza NotImplementedError (el bucle ReAct real llega el
miércoles W36).
"""
import argparse
import json
import os
from pathlib import Path

from grafo_leads import construir_grafo

AQUI = Path(__file__).resolve().parent


def cargar_dataset(path):
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sin-llm", action="store_true",
                    help="inyecta también los hallazgos (salta el modelo)")
    ap.add_argument("--dataset", default=str(AQUI / "eval" / "dataset.jsonl"))
    args = ap.parse_args()

    saltar_inv = os.environ.get("SALTAR_INVESTIGACION") == "1" or args.sin_llm
    grafo = construir_grafo()
    filas = cargar_dataset(args.dataset)
    print(f"Procesando {len(filas)} leads ({'--sin-llm' if args.sin_llm else 'modelo real'}, "
          f"investigación {'inyectada' if saltar_inv else 'real'})...")

    for d in filas:
        estado = {
            "lead_ref": d["id"],
            "empresa": d["lead"]["empresa"],
            "contacto_nombre": d["lead"].get("contacto_nombre"),
            "contacto_email": d["lead"]["contacto_email"],
            "contacto_cargo": d["lead"].get("contacto_cargo"),
            "canal_origen": d["lead"].get("canal_origen"),
        }
        if saltar_inv:
            estado["canned_ficha"] = d.get("ficha") or {}
            estado["canned_senales"] = d.get("senales_crudas") or []
        if args.sin_llm:
            estado["canned_hallazgos"] = d.get("hallazgos") or {"senales": [], "confianza": 0.9}
        r = grafo.invoke(estado)
        motivo = f" ({r['motivo']})" if r.get("motivo") else ""
        print(f"  {d['id']}: {r.get('decision')} / {r.get('resultado_log')} "
              f"-> {r.get('etiqueta')}{motivo}")


if __name__ == "__main__":
    main()
