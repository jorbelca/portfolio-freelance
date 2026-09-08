"""Carga ../1/.env en os.environ (solo las claves que falten), para que
`python3 agente.py ...` funcione sin un wrapper de shell. Sin dependencias.

Igual que las Demos 4 y 5, la fuente de verdad de las claves es ../1/.env.
Precedencia: variable ya presente en el entorno > lo que diga ../1/.env.
"""

from __future__ import annotations

import os
import pathlib

_ENV1 = pathlib.Path(__file__).parent.parent / "1" / ".env"


def cargar() -> None:
    if not _ENV1.is_file():
        return
    for linea in _ENV1.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, _, valor = linea.partition("=")
        clave, valor = clave.strip(), valor.strip().strip('"').strip("'")
        if clave and valor and clave not in os.environ:
            os.environ[clave] = valor

    # Proveedor por defecto: OpenRouter (pool :free auto-enrutado). El tier gratis de
    # Gemini AI Studio se agota antes de las 33 llamadas del eval (ver §3 G-EVAL-REAL).
    # RECLAMACIONES_GEMINI=1 vuelve a Gemini AI Studio.
    if not os.environ.get("RECLAMACIONES_LLM_BASE_URL"):
        if os.environ.get("RECLAMACIONES_GEMINI") == "1" and os.environ.get("GEMINI_API_KEY"):
            os.environ.setdefault("RECLAMACIONES_LLM_BASE_URL",
                                  "https://generativelanguage.googleapis.com/v1beta/openai/")
            os.environ.setdefault("RECLAMACIONES_MODELO", "gemini-3.6-flash")
            os.environ.setdefault("RECLAMACIONES_LLM_API_KEY", os.environ["GEMINI_API_KEY"])
            os.environ.setdefault("RECLAMACIONES_REINTENTOS", "6")
        elif os.environ.get("OPENROUTER_API_KEY"):
            os.environ.setdefault("RECLAMACIONES_LLM_BASE_URL", "https://openrouter.ai/api/v1")
            os.environ.setdefault("RECLAMACIONES_MODELO", "nvidia/nemotron-3-super-120b-a12b:free")
            os.environ.setdefault("RECLAMACIONES_LLM_API_KEY", os.environ["OPENROUTER_API_KEY"])
            os.environ.setdefault("RECLAMACIONES_REINTENTOS", "6")


cargar()
