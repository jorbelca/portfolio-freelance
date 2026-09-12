"""Vista HTML del dictamen + carta, y export a PDF.

Cubre dos pendientes del README:
  - §5 "UI mínima": HTML renderizado (no servidor SSE). Burbujas de chat con el
    relato y la respuesta del agente, y debajo la carta como documento.
  - §8 "el PDF no se recorta": `generar_pdf()` imprime esa misma carta.

El PDF sale de la carta que construye `carta.py` en código: el importe y el
artículo NUNCA los pone esta capa. Aquí solo se maqueta.

Autocheck: python3 vista.py
"""

from __future__ import annotations

import html
import pathlib
import shutil
import subprocess

# ponytail: PDF vía Chrome headless (todo Mac lo tiene). Techo: necesita Chrome y
# ~1 s de subproceso. Vía de ampliación: weasyprint si hay que generarlo en un
# servidor sin navegador.
_CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

_CSS = """
:root { color-scheme: light }
* { box-sizing: border-box }
body { font: 16px/1.5 -apple-system, system-ui, sans-serif; margin: 0;
       background: #f4f4f5; color: #18181b }
.wrap { max-width: 720px; margin: 0 auto; padding: 32px 20px 64px }
h1 { font-size: 20px; margin: 0 0 4px }
.sub { color: #71717a; font-size: 13px; margin: 0 0 24px }
.chat { display: flex; flex-direction: column; gap: 12px; margin-bottom: 28px }
.msg { padding: 12px 16px; border-radius: 14px; max-width: 85%; white-space: pre-wrap }
.user { align-self: flex-end; background: #2563eb; color: #fff; border-bottom-right-radius: 4px }
.bot  { align-self: flex-start; background: #fff; border: 1px solid #e4e4e7; border-bottom-left-radius: 4px }
.veredicto { font-weight: 600 }
.veredicto .eur { font-size: 20px }
.cita { color: #71717a; font-size: 13px; margin-top: 6px }
.doc { background: #fff; border: 1px solid #e4e4e7; border-radius: 8px;
       padding: 40px 44px; white-space: pre-wrap; font-size: 15px; line-height: 1.7 }
.doc-label { font-size: 12px; text-transform: uppercase; letter-spacing: .05em;
             color: #a1a1aa; margin: 32px 0 8px }
@media print {
  body { background: #fff }
  .wrap { max-width: none; padding: 0 }
  h1, .sub, .chat, .doc-label { display: none }
  .doc { border: 0; padding: 0; font-size: 12pt }
}
"""


def _veredicto(res: dict) -> str:
    """Resumen de una línea para la burbuja del agente."""
    if res.get("estado") == "faltan_datos":
        return "Faltan datos para dictaminar: " + ", ".join(res.get("faltan", []))
    d = res["dictamen"]
    if d.get("en_ambito") is False:
        return "Fuera del ámbito del Reglamento 261/2004. " + d.get("motivo", "")
    if d.get("en_ambito") is None:
        return "No consta si el vuelo entra en el Reglamento 261/2004 (falta: "\
               f"{d.get('falta_dato')})."
    if not d.get("elegible"):
        return "Sin derecho a compensación del art. 7. " + d.get("motivo", "")
    linea = f'Compensación: <span class="eur">{d["importe_eur"]} €</span> ({d["articulo"]})'
    if d.get("provisional"):
        linea += " — provisional: la aerolínea aún debe acreditar la circunstancia que alega"
    if d.get("reduccion_aplica"):
        linea += " — con la reducción del 50 % del art. 7(2)"
    if d.get("plazo_incierto"):
        linea += (" ⚠ posible prescripción: el plazo para reclamar en ese país no está "
                  "verificado; confírmalo con un abogado local")
    return linea


def render_html(res: dict, relato: str) -> str:
    d = res.get("dictamen") or {}
    ver = _veredicto(res)
    cita = ""
    if d.get("sentencia"):
        cita = f'<div class="cita">Jurisprudencia: {html.escape(d["sentencia"])}</div>'
    carta = (res.get("carta") or {}).get("texto", "")
    doc = ""
    if carta:
        doc = (f'<div class="doc-label">Carta de reclamación (imprimir → PDF)</div>'
               f'<div class="doc">{html.escape(carta)}</div>')
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Reclamación de vuelo</title><style>{_CSS}</style></head>
<body><div class="wrap">
<h1>Agente de reclamaciones · Reglamento (CE) 261/2004</h1>
<p class="sub">El importe y el artículo los fija el motor determinista. El modelo solo interpreta el caso.</p>
<div class="chat">
  <div class="msg user">{html.escape(relato.strip())}</div>
  <div class="msg bot"><div class="veredicto">{ver}</div>{cita}</div>
</div>
{doc}
</div></body></html>
"""


def generar_pdf(html_str: str, destino: str | pathlib.Path) -> pathlib.Path:
    """Imprime la carta a PDF con Chrome headless. Lanza RuntimeError si no está
    Chrome (usa entonces Cmd+P sobre el .html)."""
    chrome = _CHROME if pathlib.Path(_CHROME).exists() else shutil.which("chromium")
    if not chrome:
        raise RuntimeError("no se encontró Chrome; abre el .html e imprime con Cmd+P")
    destino = pathlib.Path(destino)
    tmp = destino.with_suffix(".tmp.html")
    tmp.write_text(html_str, encoding="utf-8")
    try:
        subprocess.run(
            [chrome, "--headless", "--disable-gpu", "--no-pdf-header-footer",
             f"--print-to-pdf={destino}", tmp.resolve().as_uri()],
            check=True, capture_output=True, timeout=60)
    finally:
        tmp.unlink(missing_ok=True)
    return destino


def _demo() -> None:
    firme = {"estado": "ok", "dictamen": {
        "en_ambito": True, "elegible": True, "importe_eur": 600, "articulo": "art. 7(1)(c)",
        "provisional": False, "reduccion_aplica": False, "sentencia": "Sturgeon (C-402/07)"},
        "carta": {"texto": "A la atención del Servicio de Atención al Cliente\n\n"
                  "... le requiero el abono de 600 € en efectivo ..."}}
    h = render_html(firme, "Madrid-Nueva York, 4 h tarde, dijeron problema técnico")
    assert "600 €" in h and "le requiero el abono de" in h
    assert "@media print" in h and "Sturgeon" in h

    prov = {"estado": "ok", "dictamen": {
        "en_ambito": True, "elegible": True, "importe_eur": 400, "articulo": "art. 7(1)(b)",
        "provisional": True, "reduccion_aplica": False},
        "carta": {"texto": "... De no acreditarse una circunstancia extraordinaria ..."}}
    hp = render_html(prov, "Barcelona-Berlín, 3h30, dijeron mal tiempo")
    assert "provisional" in hp and "le requiero el abono de" not in hp

    fuera = {"estado": "ok", "dictamen": {"en_ambito": False, "motivo": "Salida de EEUU, transportista no comunitario."}}
    assert "Fuera del ámbito" in render_html(fuera, "Nueva York-Madrid con Delta, 4 h")

    print("vista.py: OK")


if __name__ == "__main__":
    _demo()
