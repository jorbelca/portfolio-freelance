#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Corre el grafo de grafo_facturas.py sobre las facturas de facturas_pdf/, en el orden del
dataset (importa para el caso f04: solo es 'duplicado' si f01 se procesó antes en esta misma
ejecución o en una anterior).

--sin-llm: inyecta la extracción "verdad" de eval/dataset.jsonl como canned_extraccion, con
confianza uniforme alta -- salta la llamada real a OpenRouter (no requiere OPENROUTER_API_KEY)
para poder probar ingesta/validación/gate/persistencia/log de punta a punta. Mismo espíritu que
--dry-run en 1/eval/run_eval.py y 2/eval/run_eval.py, aplicado aquí a la ejecución, no solo al
informe.
"""
import argparse
import json
import os
from pathlib import Path

from grafo_facturas import construir_grafo

AQUI = Path(__file__).resolve().parent
CONFIANZA_CANNED = 0.95  # confianza uniforme alta en modo --sin-llm; no ejercita la rama de
                          # confianza baja a propósito -- esa rama se prueba con datos reales.


CONFIANZA_RUIDOSA = 0.35  # confianza de un campo "leído" con dificultad de un escaneo ruidoso


def cargar_canned(dataset_path):
    """Por defecto usa campos_verdad con confianza uniforme alta. Si el caso trae
    'canned_override' (hoy solo el escaneo ruidoso, f10) simula una extracción DEGRADADA en
    vez de la verdad -- ver la nota en generar_facturas.py sobre por qué ese caso no debe
    inyectar la verdad tal cual."""
    canned = {}
    for linea in open(dataset_path, encoding="utf-8"):
        if not linea.strip():
            continue
        d = json.loads(linea)
        campos = d["campos_verdad"]
        confianza = {c: CONFIANZA_CANNED for c in campos}
        override = d.get("canned_override", {})
        for campo in override.get("confianza_baja", []):
            confianza[campo] = CONFIANZA_RUIDOSA
        canned[d["pdf_origen"]] = {"extraccion": campos, "confianza_campos": confianza}
    return canned


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sin-llm", action="store_true",
                     help="usa la extracción verdad de eval/dataset.jsonl en vez de llamar a OpenRouter")
    ap.add_argument("--dataset", default=str(AQUI / "eval" / "dataset.jsonl"))
    ap.add_argument("--pdf-dir", default=str(AQUI / "facturas_pdf"))
    args = ap.parse_args()

    if args.sin_llm:
        canned = cargar_canned(args.dataset)
        orden = list(canned.keys())  # dataset.jsonl ya está en el orden f01..f04
    else:
        canned = {}
        orden = sorted(p.name for p in Path(args.pdf_dir).glob("*.pdf"))

    grafo = construir_grafo()
    print(f"Procesando {len(orden)} facturas ({'--sin-llm' if args.sin_llm else 'OpenRouter real'})...")
    for pdf_origen in orden:
        pdf_path = str(Path(args.pdf_dir) / pdf_origen)
        estado_inicial = {"pdf_path": pdf_path, "pdf_origen": pdf_origen}
        if args.sin_llm:
            estado_inicial["canned_extraccion"] = canned[pdf_origen]
        resultado = grafo.invoke(estado_inicial)
        motivo = f" ({resultado['motivo']})" if resultado.get("motivo") else ""
        print(f"  {pdf_origen}: {resultado['decision']}{motivo}")


if __name__ == "__main__":
    main()
