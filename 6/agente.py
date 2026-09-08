"""Glue de la Demo 6: relato libre -> dictamen determinista -> carta -> log.

No es un grafo (README §0.6): un flujo lineal con un único punto de juicio del
modelo (`interpretar_relato`). Todo lo que decide dinero o derecho es determinista.

Uso:
    python3 agente.py "Madrid-Nueva York, 4 h de retraso, me dijeron problema técnico
                       y me ofrecieron 250 € en bonos"
    echo "<relato>" | python3 agente.py -
"""

from __future__ import annotations

import sys
from dataclasses import fields
from datetime import date

from carta import clasificar_plantilla, redactar_reclamacion
from decision_log import registrar
from reglas import Hechos, evaluar_elegibilidad

_CAMPOS_HECHOS = {f.name for f in fields(Hechos)}


def _a_hechos(d: dict) -> Hechos:
    kw = {k: v for k, v in d.items() if k in _CAMPOS_HECHOS}
    # El modelo suele devolver pais_reclamacion: null; ese None pisaría el
    # "ES" por defecto del dataclass y dispararía plazo_incierto sin motivo.
    if not kw.get("pais_reclamacion"):
        kw.pop("pais_reclamacion", None)
    fv = kw.get("fecha_vuelo")
    if isinstance(fv, str) and fv:
        try:
            kw["fecha_vuelo"] = date.fromisoformat(fv)
        except ValueError:
            kw["fecha_vuelo"] = None
    return Hechos(**kw)


def procesar(relato: str, *, hechos_inyectados: dict | None = None,
             escribir_carta: bool = True, registrar_log: bool = True,
             escribir_html: bool = False, pdf: bool = False,
             carta_llm: bool | None = None,
             hoy: date | None = None) -> dict:
    if hechos_inyectados is not None:
        info = dict(hechos_inyectados)
        fuente = "inyectado"
    else:
        from interpretar import interpretar_relato
        info = interpretar_relato(relato)
        fuente = "modelo"

    if not info.get("origen") or not info.get("destino") or info.get("retraso_llegada_h") is None:
        faltan = info.get("faltan") or [k for k in ("origen", "destino", "retraso_llegada_h")
                                        if not info.get(k) and info.get(k) != 0]
        salida = {"estado": "faltan_datos", "faltan": faltan, "fuente_hechos": fuente,
                  "info": info}
        if registrar_log:
            registrar(relato=relato, hechos=info,
                      dictamen={"en_ambito": None, "falta_dato": ",".join(faltan)},
                      plantilla="falta_dato", fuente_hechos=fuente)
        return salida

    hechos = _a_hechos(info)
    dictamen = evaluar_elegibilidad(hechos, hoy=hoy)
    plantilla = clasificar_plantilla(dictamen)

    hechos_d = {**{f.name: getattr(hechos, f.name) for f in fields(Hechos)},
                "causa_texto": info.get("causa_texto", ""),
                "fecha_vuelo": info.get("fecha_vuelo")}

    carta = None
    carta_path = None
    if escribir_carta:
        carta = redactar_reclamacion(dictamen, hechos_d, usar_modelo=carta_llm)
        import pathlib
        cid = info.get("id") or f"{hechos.origen}-{hechos.destino}"
        carta_path = str(pathlib.Path(__file__).parent / "cartas" / f"{cid}.txt")
        pathlib.Path(carta_path).parent.mkdir(exist_ok=True)
        pathlib.Path(carta_path).write_text(carta["texto"], encoding="utf-8")

    resultado = {"estado": "ok", "fuente_hechos": fuente, "dictamen": dictamen,
                 "plantilla": plantilla, "carta": carta, "hechos": hechos_d,
                 "confianza": info.get("confianza")}

    if (escribir_html or pdf) and carta is not None:
        from vista import generar_pdf, render_html
        import pathlib
        cid = info.get("id") or f"{hechos.origen}-{hechos.destino}"
        base = pathlib.Path(__file__).parent / "cartas" / cid
        base.parent.mkdir(exist_ok=True)
        h = render_html(resultado, relato)
        base.with_suffix(".html").write_text(h, encoding="utf-8")
        resultado["html_path"] = str(base.with_suffix(".html"))
        if pdf:
            resultado["pdf_path"] = str(generar_pdf(h, base.with_suffix(".pdf")))

    if registrar_log:
        registrar(relato=relato, hechos=hechos_d, dictamen=dictamen, plantilla=plantilla,
                  fuente_hechos=fuente, carta_path=carta_path)

    return resultado


def _demo() -> None:
    """Autocheck sin modelo: hechos inyectados, ruta feliz + provisional + fuera de ámbito."""
    import os
    os.environ["RECLAMACIONES_CARTA_LLM"] = "0"  # el autocheck no llama al modelo
    r = procesar("(inyectado)", hechos_inyectados=dict(
        origen="MAD", destino="JFK", retraso_llegada_h=4.0, causa_categoria="fallo_tecnico",
        oferta_aerolinea_eur=250, causa_texto="problema técnico"),
        escribir_carta=True, registrar_log=False)
    assert r["dictamen"]["importe_eur"] == 600 and r["plantilla"] == "firme"
    assert "600 €" in r["carta"]["texto"] and "le requiero el abono de" in r["carta"]["texto"]

    r = procesar("(inyectado)", hechos_inyectados=dict(
        origen="MAD", destino="LIS", retraso_llegada_h=3.5, causa_categoria="meteorologia"),
        registrar_log=False)
    assert r["plantilla"] == "provisional"
    assert "le requiero el abono de" not in r["carta"]["texto"]
    assert "no acreditarse una circunstancia extraordinaria" in r["carta"]["texto"]

    r = procesar("(inyectado)", hechos_inyectados=dict(
        origen="JFK", destino="MAD", retraso_llegada_h=4.0, causa_categoria="operativo_aerolinea",
        transportista_comunitario=False), registrar_log=False)
    assert r["plantilla"] == "fuera_ambito" and "le requiero" not in r["carta"]["texto"]

    print("agente.py: OK (modo inyectado)")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a not in ("--html", "--pdf")]
    if args:
        quiere_html = "--html" in sys.argv or "--pdf" in sys.argv
        quiere_pdf = "--pdf" in sys.argv
        relato = sys.stdin.read() if args[0] == "-" else " ".join(args)
        out = procesar(relato, escribir_html=quiere_html, pdf=quiere_pdf)
        if out["estado"] == "faltan_datos":
            print("Faltan datos:", ", ".join(out["faltan"]))
        else:
            d = out["dictamen"]
            print(f"\nPlantilla: {out['plantilla']}  |  fuente hechos: {out['fuente_hechos']}")
            print(f"Elegible: {d['elegible']}  Importe: {d['importe_eur']} €  {d['articulo']}")
            print(f"Motivo: {d['motivo']}\n")
            print("--- CARTA " + "-" * 50)
            print(out["carta"]["texto"])
            if out.get("html_path"):
                print("HTML:", out["html_path"])
            if out.get("pdf_path"):
                print("PDF: ", out["pdf_path"])
    else:
        _demo()
