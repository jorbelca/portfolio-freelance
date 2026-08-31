#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vuelca el grafo de grafo_facturas.py a Mermaid, para abrir el vídeo con el pipeline dibujado.
draw_mermaid() en vez de draw_mermaid_png(): esta última pide red (mermaid.ink) o graphviz local
-- draw_mermaid() ya viene con langgraph, cero deps nuevas. El .mmd se pega en mermaid.live,
Obsidian o GitHub, todos lo renderizan nativo.
"""
from pathlib import Path

from grafo_facturas import construir_grafo

SALIDA = Path(__file__).resolve().parent / "grafo_facturas.mmd"

if __name__ == "__main__":
    mermaid = construir_grafo().get_graph().draw_mermaid()
    SALIDA.write_text(mermaid, encoding="utf-8")
    print(f"Diagrama escrito en {SALIDA}")
