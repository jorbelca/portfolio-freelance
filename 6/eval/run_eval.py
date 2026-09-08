"""Arnés de eval de la Demo 6. Patrón de 4/eval/run_eval.py.

Dos modos, dos números, NO se promedian (§7 de PLAN-demo6.md):

  python3 eval/run_eval.py --sin-llm
      Inyecta `hechos` del dataset directamente en el motor de reglas. Mide SOLO
      reglas + aritmética + lookup de precedentes. Objetivo: 30/30. Un fallo aquí
      es un bug en el articulado o en la autoría del ground truth.

  python3 eval/run_eval.py            (modo real — necesita clave de modelo)
      Le da `relato_es` al agente, que extrae los hechos y clasifica la causa.
      Mide interpretar_relato (extracción + clasificar_causa). Es EL número del vídeo.
      Reporta TRES fracciones sin promediar: acierto de categoría, de elegibilidad
      (incluye la clasificación de ámbito), y de importe.
"""

import argparse
import json
import pathlib
import sys
from datetime import date

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from reglas import Hechos, evaluar_elegibilidad  # noqa: E402

HOY = date(2026, 9, 8)  # fecha de referencia fija para que el plazo sea reproducible
DATASET = pathlib.Path(__file__).parent / "dataset.jsonl"

# Campos del dictamen que se comparan contra `esperado`.
CAMPOS = ["elegible", "importe_eur", "circunstancia_exime", "dentro_plazo", "provisional",
          "reduccion_aplica", "en_ambito", "falta_dato"]
# Valor por defecto esperado cuando el caso no lo declara.
DEFECTOS = {"en_ambito": True, "falta_dato": None, "reduccion_aplica": False,
            "provisional": False, "dentro_plazo": True}


def cargar():
    with DATASET.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def hechos_de(d: dict) -> Hechos:
    h = dict(d)
    if h.get("fecha_vuelo"):
        h["fecha_vuelo"] = date.fromisoformat(h["fecha_vuelo"])
    return Hechos(**h)


def evaluar_sin_llm():
    casos = cargar()
    ok = 0
    fallos = []
    for c in casos:
        got = evaluar_elegibilidad(hechos_de(c["hechos"]), hoy=HOY)
        exp = c["esperado"]
        diffs = {}
        for k in CAMPOS:
            esperado = exp[k] if k in exp else DEFECTOS.get(k)
            if k in exp or k in DEFECTOS:
                if esperado != got[k]:
                    diffs[k] = (esperado, got[k])
        # `articulo` solo se comprueba cuando el caso es elegible
        if exp.get("elegible") and "articulo" in exp and exp["articulo"] != got["articulo"]:
            diffs["articulo"] = (exp["articulo"], got["articulo"])
        if diffs:
            fallos.append((c["id"], diffs))
        else:
            ok += 1
    return ok, len(casos), fallos


def _clasif_ambito(v):
    """True/False/None de en_ambito -> etiqueta comparable."""
    return {True: "ambito", False: "fuera", None: "falta_dato"}[v]


def evaluar_real(limite: int | None = None):
    import os
    import time

    from agente import procesar

    pausa = float(os.environ.get("RECLAMACIONES_PAUSA", "7"))  # respeta la cuota/min del tier gratis
    casos = cargar()
    if limite:
        casos = casos[:limite]
    n = len(casos)
    cat_ok = eleg_ok = imp_ok = 0
    errores = 0
    filas = []
    for idx, c in enumerate(casos):
        if idx:
            time.sleep(pausa)
        exp = c["esperado"]
        try:
            out = procesar(c["relato_es"], escribir_carta=False, registrar_log=False, hoy=HOY)
        except Exception as e:  # noqa: BLE001
            errores += 1
            filas.append((c["id"], "ERROR", str(e)[:80]))
            continue

        if out["estado"] == "faltan_datos":
            got_cat, got_eleg, got_imp, got_amb = "?", False, 0, "falta_dato"
        else:
            d = out["dictamen"]
            got_cat = out["hechos"]["causa_categoria"]
            got_eleg, got_imp = d["elegible"], d["importe_eur"]
            got_amb = _clasif_ambito(d["en_ambito"])

        exp_amb = _clasif_ambito(exp["en_ambito"] if "en_ambito" in exp else DEFECTOS["en_ambito"])
        c_ok = got_cat == exp.get("categoria")
        e_ok = (got_eleg == exp.get("elegible")) and (got_amb == exp_amb)
        i_ok = (got_imp == exp.get("importe_eur")) if exp.get("elegible") else True
        cat_ok += c_ok
        eleg_ok += e_ok
        imp_ok += i_ok
        marca = "".join("." if x else "X" for x in (c_ok, e_ok, i_ok))
        filas.append((c["id"], marca, f"cat={got_cat} eleg={got_eleg} imp={got_imp}"))

    for cid, marca, info in filas:
        print(f"  {cid:5} [{marca}] {info}")
    validos = n - errores
    print(f"\nmodo real ({n} relatos, {errores} con error de proveedor) — sin promediar:")
    if errores:
        print(f"  AVISO: {errores} relatos no se pudieron medir (rate limit / proveedor). "
              f"Números sobre los {validos} válidos; NO es la corrida de referencia.")
    base = validos or 1
    print(f"  categoría de causa : {cat_ok}/{validos}  ({100 * cat_ok / base:.0f}%)")
    print(f"  elegibilidad       : {eleg_ok}/{validos}  ({100 * eleg_ok / base:.0f}%)   (incluye ámbito)")
    print(f"  importe            : {imp_ok}/{validos}  ({100 * imp_ok / base:.0f}%)")
    return cat_ok, eleg_ok, imp_ok, validos, errores


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sin-llm", action="store_true", help="mide solo el motor de reglas")
    ap.add_argument("--limite", type=int, default=None, help="modo real: primeros N casos")
    args = ap.parse_args()

    if args.sin_llm:
        ok, total, fallos = evaluar_sin_llm()
        for cid, diffs in fallos:
            print(f"  FALLO {cid}: " + ", ".join(
                f"{k} esperaba {e!r} obtuvo {g!r}" for k, (e, g) in diffs.items()))
        print(f"\n--sin-llm: {ok}/{total} dictámenes correctos")
        raise SystemExit(0 if ok == total else 1)

    evaluar_real(args.limite)  # medición, no gate: siempre exit 0
    raise SystemExit(0)


if __name__ == "__main__":
    main()
