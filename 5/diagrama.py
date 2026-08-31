#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vuelca el grafo de grafo_leads.py a Mermaid. draw_mermaid() (no _png): ya viene con
langgraph, cero deps ni red. El .mmd se pega en mermaid.live, Obsidian o GitHub. Mismo
criterio que 4/diagrama.py."""
from pathlib import Path

from grafo_leads import construir_grafo

SALIDA = Path(__file__).resolve().parent / "grafo_leads.mmd"

if __name__ == "__main__":
    SALIDA.write_text(construir_grafo().get_graph().draw_mermaid(), encoding="utf-8")
    print(f"Diagrama escrito en {SALIDA}")
