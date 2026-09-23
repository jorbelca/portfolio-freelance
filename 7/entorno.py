"""Carga ../1/.env en os.environ (solo las claves que falten), para que
`python3 informe.py` funcione sin un wrapper de shell. Sin dependencias.

Misma fuente de verdad que las Demos 4/5/6: ../1/.env. Precedencia: variable ya
presente en el entorno > lo que diga ../1/.env.
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


cargar()
