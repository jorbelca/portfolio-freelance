"""Registro de decisiones en JSONL (README §5: se conserva el principio de la Demo 5
—toda decisión computada queda registrada con el artículo/regla que la produjo— y se
quita Docker/psycopg2).

Una línea por caso procesado, en TODOS los caminos (elegible, provisional, fuera de
ámbito, falta de dato). Append-only.
"""

from __future__ import annotations

import json
import os
import pathlib
from datetime import datetime, timezone

RUTA = pathlib.Path(os.environ.get(
    "RECLAMACIONES_LOG", pathlib.Path(__file__).parent / "decision_log.jsonl"))


def registrar(*, relato: str, hechos: dict, dictamen: dict, plantilla: str,
              fuente_hechos: str, carta_path: str | None = None) -> dict:
    """Escribe una entrada y la devuelve. `fuente_hechos`: 'modelo' | 'inyectado'."""
    entrada = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "relato": relato,
        "fuente_hechos": fuente_hechos,
        "hechos": {k: v for k, v in hechos.items() if k != "crudo"},
        "dictamen": {
            "en_ambito": dictamen.get("en_ambito"),
            "falta_dato": dictamen.get("falta_dato"),
            "elegible": dictamen.get("elegible"),
            "provisional": dictamen.get("provisional"),
            "importe_eur": dictamen.get("importe_eur"),
            "articulo": dictamen.get("articulo"),
            "circunstancia_exime": dictamen.get("circunstancia_exime"),
            "sentencia": dictamen.get("sentencia"),
            "dentro_plazo": dictamen.get("dentro_plazo"),
            "distancia_km": dictamen.get("distancia_km"),
            "motivo": dictamen.get("motivo"),
        },
        "plantilla": plantilla,
        "carta_path": carta_path,
    }
    RUTA.parent.mkdir(parents=True, exist_ok=True)
    with RUTA.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entrada, ensure_ascii=False, sort_keys=True) + "\n")
    return entrada
