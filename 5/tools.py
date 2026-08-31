#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Las dos tools de investigacion_agente.

- ficha_empresa(nombre): hechos de registro. MOCK sobre fichas.json (dataset sintético,
  etiquetado como tal). Es lo único que en producción vendría de un registro mercantil.
  Determinista -> el eval lo deja vivo incluso en modo SALTAR_INVESTIGACION.
- buscar_senales(query): señales de timing/intención. Búsqueda web REAL (DuckDuckGo, sin
  clave). Es el dato "en vivo" del vídeo; en el eval se sustituye por `senales_crudas` del
  dataset. Un fallo de red degrada a lista vacía -> el lead cae a R14/cola, no rompe la corrida.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from validaciones import normalizar_empresa

AQUI = Path(__file__).resolve().parent


def _fichas():
    return json.loads((AQUI / "fichas.json").read_text(encoding="utf-8"))


def ficha_empresa(nombre: str) -> dict:
    """Devuelve la ficha de registro de `nombre`, o {} si no está en fichas.json -- una empresa
    sin rastro en el registro no se puede evaluar contra los descalificadores (R14)."""
    clave = normalizar_empresa(nombre)
    for f in _fichas():
        if normalizar_empresa(f.get("nombre", "")) == clave:
            return f
    return {}


def buscar_senales(query: str, max_resultados: int = 5) -> list:
    """Búsqueda web real. Devuelve [{"snippet", "url", "recuperado_en"}] -- MISMA forma que
    inyecta el dataset (contrato verificado en test_rubrica.CLAVES_SENAL_CRUDA). Cualquier
    fallo (sin red, rate limit, dependencia) -> []."""
    ahora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        from duckduckgo_search import DDGS  # renombrado a `ddgs`; ver nota de deps en README
        resultados = list(DDGS().text(query, max_results=max_resultados))
    except Exception:
        return []
    return [{"snippet": r.get("body", ""), "url": r.get("href", ""), "recuperado_en": ahora}
            for r in resultados if r.get("body")]


if __name__ == "__main__":
    import sys
    n = sys.argv[1] if len(sys.argv) > 1 else "Nubestack Ltd"
    print("ficha_empresa:", json.dumps(ficha_empresa(n), ensure_ascii=False))
    print("buscar_senales:", json.dumps(buscar_senales(f"{n} funding hiring"), ensure_ascii=False)[:400])
