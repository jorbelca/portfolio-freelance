"""Red de seguridad del motor de reglas para el refactor de `reglas.py`.

`evaluar_elegibilidad` es una función pura. Este script barre un producto
cartesiano de casos (ámbito × retraso × causa × fecha × país × reruteo ×
transportista, más barridos enfocados) y congela cada salida en
`golden_motor.jsonl`.

  ANTES de tocar reglas.py:   python3 eval/golden_motor.py --write
  DESPUÉS (y en el CI local): python3 eval/golden_motor.py           # falla si algo cambió

El refactor preserva el comportamiento o está mal: este fichero tiene que salir
byte a byte igual. Los 33 casos del dataset no cubren todas las ramas; esto sí.
"""

from __future__ import annotations

import json
import pathlib
import sys
from datetime import date

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from precedentes import CATEGORIAS  # noqa: E402
from reglas import Hechos, evaluar_elegibilidad  # noqa: E402

HOY = date(2026, 9, 8)  # fija, para que el plazo sea reproducible
GOLDEN = pathlib.Path(__file__).parent / "golden_motor.jsonl"

# Pares que tocan cada rama del art. 3 y cada banda del art. 7(1)/(2).
_PARES = [
    "MAD-BCN",   # intracom. corto (<=1500)
    "MAD-LIS",   # intracom. ~1000
    "MAD-HEL",   # intracom. largo (>1500) -> 400
    "MAD-JFK",   # no intracom. >3500 -> 600
    "MAD-CMN",   # no intracom. 1500-3500 -> 400
    "MAD-LHR",   # salida UE -> destino UK (cubierto por salida)
    "LHR-JFK",   # salida UK -> fuera de ámbito (UK261)
    "LHR-MAD",   # UK -> UE: llega_ue, depende de transportista
    "JFK-MAD",   # 3.er país -> UE: llega_ue, depende de transportista
    "JFK-YYZ",   # ni origen ni destino UE -> fuera
    "LPA-MAD",   # Canarias (UE) -> intracom.
    "ZRH-GVA",   # Suiza (UE por acuerdo) -> intracom. corto
]
_DELAYS = [1.0, 2.0, 2.9, 3.0, 3.5, 4.0, 5.0]
_CAUSAS_MAIN = ["fallo_tecnico", "meteorologia", "colision_ave", "desconocida"]
_FECHAS = [None, "2019-01-01", "2024-06-01"]
_PAISES = ["ES", "DE", "GB", "IT", ""]
_RERUTEO = [False, True]
_TRANSP = [None, True, False]


def _casos():
    for par in _PARES:
        o, d = par.split("-")
        for rt in _DELAYS:
            for causa in _CAUSAS_MAIN:
                for f in _FECHAS:
                    for p in _PAISES:
                        for rr in _RERUTEO:
                            for tc in _TRANSP:
                                yield dict(origen=o, destino=d, retraso_llegada_h=rt,
                                           causa_categoria=causa, fecha_vuelo=f,
                                           pais_reclamacion=p, hubo_reruteo=rr,
                                           transportista_comunitario=tc)
    # las 13 categorías de causa, escenario elegible fijo
    for causa in CATEGORIAS:
        for f in _FECHAS:
            yield dict(origen="MAD", destino="JFK", retraso_llegada_h=4.0,
                       causa_categoria=causa, fecha_vuelo=f, pais_reclamacion="ES",
                       hubo_reruteo=False, transportista_comunitario=None)
    # barrido de oferta de la aerolínea (solo afecta al motivo)
    for of in [None, 0, 100, 250, 600, 700]:
        yield dict(origen="MAD", destino="JFK", retraso_llegada_h=4.0,
                   causa_categoria="fallo_tecnico", fecha_vuelo="2024-06-01",
                   pais_reclamacion="ES", hubo_reruteo=False,
                   transportista_comunitario=None, oferta_aerolinea_eur=of)


def _a_hechos(c: dict) -> Hechos:
    kw = dict(c)
    if kw.get("fecha_vuelo"):
        kw["fecha_vuelo"] = date.fromisoformat(kw["fecha_vuelo"])
    return Hechos(**kw)


def _norm(out: dict) -> dict:
    return {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in out.items()}


def generar():
    for c in _casos():
        yield {"h": c, "out": _norm(evaluar_elegibilidad(_a_hechos(c), hoy=HOY))}


def escribir() -> None:
    n = 0
    with GOLDEN.open("w", encoding="utf-8") as f:
        for row in generar():
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            n += 1
    print(f"escrito {GOLDEN.name}: {n} casos, {GOLDEN.stat().st_size // 1024} KB")


def comprobar() -> None:
    if not GOLDEN.exists():
        raise SystemExit(f"no hay {GOLDEN.name}; corre `python3 eval/golden_motor.py --write` primero")
    esperado = [json.loads(l) for l in GOLDEN.read_text(encoding="utf-8").splitlines() if l.strip()]
    actual = list(generar())
    if len(esperado) != len(actual):
        raise SystemExit(f"nº de casos cambió: golden {len(esperado)} vs ahora {len(actual)} "
                         f"(¿cambió el generador? entonces --write y revisa el diff a mano)")
    # Comparación de subconjunto: toda clave que existía en el baseline debe
    # seguir con el mismo valor. Claves NUEVAS (p. ej. `traza`) están permitidas
    # —el refactor puede añadir, no cambiar ni quitar—.
    difs = []
    for e, a in zip(esperado, actual):
        eo, ao = e["out"], a["out"]
        malas = {k: (eo[k], ao.get(k, "<AUSENTE>")) for k in eo if ao.get(k) != eo[k]}
        if malas:
            difs.append((e["h"], malas))
    if difs:
        for h, malas in difs[:8]:
            print("CASO:", json.dumps(h, ensure_ascii=False))
            for k, (vg, va) in sorted(malas.items()):
                print(f"  {k}:\n    golden = {vg!r}\n    ahora  = {va!r}")
        raise SystemExit(f"{len(difs)}/{len(actual)} casos difieren del golden — el refactor cambió comportamiento")
    print(f"golden_motor: {len(actual)} casos, todas las claves del baseline intactas")


if __name__ == "__main__":
    escribir() if "--write" in sys.argv else comprobar()
