"""UI local del agente EU261.

Enseña el reparto que es el argumento de la demo: el relato lo interpreta el
modelo (un único punto de juicio), y el importe / la elegibilidad / la cita
salen de un motor de reglas determinista. La pantalla lo pone en tres etapas:

    1 · Relato            (entrada)
    2 · Hechos extraídos  (modelo — único punto de juicio)
    3 · Dictamen          (motor determinista — 0 llamadas al modelo)

Dos formas de entrar los hechos:
  - «Relato libre»  -> interpretar_relato() con el modelo.
  - «Datos del vuelo» -> se inyectan directos al motor; render instantáneo,
    funciona aunque el proveedor esté caído (lo está a ratos en el tier free).

    python3 servidor.py           # http://127.0.0.1:8060
    python3 servidor.py 9000      # otro puerto

ponytail: http.server de la stdlib, sin framework ni build. Un proceso, sin
auth, para demo local. Producción = detrás de gunicorn y claves fuera de ../1/.env.

Autocheck: python3 servidor.py --check
"""

from __future__ import annotations

import json
import sys
import time as _time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from precedentes import CATEGORIAS

PUERTO = 8060

_EJEMPLOS = [
    "Vuelo Madrid–Nueva York el 12/03/2026, llegué 4 h tarde. Me dijeron que fue "
    "un problema técnico del avión y me ofrecieron un bono de 250 €.",
    "Barcelona–Berlín, 3 h 30 de retraso a la llegada. La aerolínea alega mal tiempo.",
    "Palma–Londres Gatwick, aterrizamos con 2 h de retraso por una avería.",
    "Nueva York–Madrid con Delta, 5 h tarde por overbooking operativo.",
]

# Etiquetas legibles para el desplegable de causa (presentación; la lista viva
# es precedentes.CATEGORIAS).
_CAUSA_LABEL = {
    "fallo_tecnico": "Avería / problema técnico",
    "defecto_fabrica_oculto": "Defecto de fábrica oculto (comunicado por el fabricante)",
    "sabotaje": "Sabotaje o acto de terrorismo",
    "meteorologia": "Meteorología adversa",
    "huelga_atc": "Huelga de controladores / personal de aeropuerto",
    "decision_atc": "Decisión de control de tráfico aéreo (ATFM)",
    "huelga_personal_propio": "Huelga del personal de la aerolínea",
    "operativo_aerolinea": "Problema operativo (rotaciones, tripulación, overbooking)",
    "colision_ave": "Colisión con un ave",
    "riesgo_seguridad": "Riesgo de seguridad",
    "problema_medico_pasajero": "Urgencia médica de un pasajero",
    "restriccion_administrativa": "Cierre de pista / espacio aéreo por la autoridad",
    "desconocida": "No lo sé / no me lo dijeron",
}


# --- lógica: resultado del agente -> lo que pinta la UI ---------------------

def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _norm_hechos(campos: dict) -> dict:
    """Coacciona los strings del formulario a los tipos que espera el motor."""
    h = {
        "origen": (campos.get("origen") or "").strip().upper(),
        "destino": (campos.get("destino") or "").strip().upper(),
        "retraso_llegada_h": _num(campos.get("retraso_llegada_h")),
        "causa_categoria": (campos.get("causa_categoria") or "desconocida").strip(),
        "causa_texto": _CAUSA_LABEL.get(campos.get("causa_categoria"), ""),
    }
    if campos.get("fecha_vuelo"):
        h["fecha_vuelo"] = campos["fecha_vuelo"]
    if _num(campos.get("oferta_aerolinea_eur")) is not None:
        h["oferta_aerolinea_eur"] = _num(campos["oferta_aerolinea_eur"])
    pais = (campos.get("pais_reclamacion") or "").strip().upper()
    if pais:
        h["pais_reclamacion"] = pais
    tc = campos.get("transportista_comunitario")
    if tc in ("si", "no", True, False):
        h["transportista_comunitario"] = tc in ("si", True)
    return h


def _linea_hechos(h: dict) -> str:
    trozos = [h.get("origen") or "?", h.get("destino") or "?"]
    r = h.get("retraso_llegada_h")
    trozos.append(f"{r:g} h" if r is not None else "? h")
    if h.get("causa_categoria") and h["causa_categoria"] != "desconocida":
        trozos.append(h["causa_categoria"])
    if h.get("fecha_vuelo"):
        trozos.append(str(h["fecha_vuelo"]))
    if h.get("oferta_aerolinea_eur") is not None:
        trozos.append(f"oferta {h['oferta_aerolinea_eur']:g} €")
    return " · ".join(trozos)


def _jsonable(v):
    return v.isoformat() if hasattr(v, "isoformat") else v


def _flatten(r: dict, relato: str, modo: str) -> dict:
    if r.get("estado") == "faltan_datos":
        return {"ok": True, "estado": "faltan_datos", "faltan": r.get("faltan", []),
                "relato": relato, "modo": modo}

    d = r.get("dictamen") or {}
    hechos = {k: _jsonable(v) for k, v in (r.get("hechos") or {}).items()}
    en_amb = d.get("en_ambito")
    exime = d.get("circunstancia_exime")

    if en_amb is False:
        clase = "fuera"
    elif en_amb is None:
        clase = "falta"
    elif not d.get("elegible"):
        clase = "no"
    elif d.get("provisional") or d.get("plazo_incierto"):
        clase = "prov"
    else:
        clase = "si"

    importe = d.get("importe_eur", 0) or 0
    oferta = _num(hechos.get("oferta_aerolinea_eur"))
    deficit = round(importe - oferta, 2) if (oferta is not None and oferta < importe) else None

    return {
        "ok": True, "estado": "ok", "modo": modo, "relato": relato, "clase": clase,
        "fuente_hechos": r.get("fuente_hechos"),
        "hechos": hechos,
        "hechos_linea": _linea_hechos(hechos),
        "elegible": bool(d.get("elegible")),
        "en_ambito": en_amb,
        "importe_eur": importe,
        "articulo": d.get("articulo"),
        "importe_base_eur": d.get("importe_base_eur"),
        "distancia_km": d.get("distancia_km"),
        "intracomunitario": d.get("intracomunitario"),
        "reduccion_aplica": bool(d.get("reduccion_aplica")),
        "provisional": bool(d.get("provisional")),
        "plazo_incierto": bool(d.get("plazo_incierto")),
        "dentro_plazo": d.get("dentro_plazo"),
        "pais": hechos.get("pais_reclamacion"),
        "fecha_vuelo": hechos.get("fecha_vuelo"),
        "oferta_eur": oferta,
        "deficit_eur": deficit,
        "causa_categoria": d.get("causa_categoria") or hechos.get("causa_categoria"),
        "circunstancia_exime": exime,
        "traza": d.get("traza", []),
        "sentencia": d.get("sentencia"),
        "nota_precedente": d.get("nota_precedente", ""),
        "motivo": d.get("motivo", ""),
        "carta_tipo": (r.get("carta") or {}).get("tipo"),
        "carta": (r.get("carta") or {}).get("texto", ""),
    }


def payload(entrada: dict, procesar) -> dict:
    """`procesar` es agente.procesar (se inyecta para testear sin red)."""
    campos = entrada.get("hechos") or {}
    if campos:
        h = _norm_hechos(campos)
        if not h["origen"] or not h["destino"] or h["retraso_llegada_h"] is None:
            return {"ok": False, "error": "Faltan origen, destino o retraso a la llegada."}
        disp = _linea_hechos(h)
        t0 = _time.monotonic()
        try:
            r = procesar(disp, hechos_inyectados=h, carta_llm=bool(campos.get("carta_llm")))
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}
        out = _flatten(r, disp, "form")
        out["latencia_ms"] = round((_time.monotonic() - t0) * 1000)
        out["modelo_usado"] = None
        if campos.get("carta_llm"):
            out["modelo_usado"] = _modelo_usado()
        return out

    relato = (entrada.get("relato") or "").strip()
    if not relato:
        return {"ok": False, "error": "Escribe el caso del vuelo."}
    t0 = _time.monotonic()
    try:
        r = procesar(relato)
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    out = _flatten(r, relato, "relato")
    out["latencia_ms"] = round((_time.monotonic() - t0) * 1000)
    out["modelo_config"], out["proveedor"] = _modelo_config()
    out["modelo_usado"] = _modelo_usado()
    return out


def _modelo_config() -> tuple[str, str]:
    try:
        import llm
        return llm.modelo(), llm.proveedor()
    except Exception:
        return "?", "?"


def _modelo_usado():
    try:
        import llm
        return llm.ultimo_modelo() or None
    except Exception:
        return None


# --- HTML (una página, sin assets externos) --------------------------------

PAGINA = r"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Agente EU261</title>
<style>
:root{
  /* identidad: azul UE + oro del emblema, sobre neutros cálidos de documento */
  --bg:#f3f1ec; --panel:#faf8f4; --card:#fff; --ink:#1a1c22; --muted:#6a6f7a;
  --line:#e3ded3; --navy:#16324f; --accent:#9a6b12; --violet:#6d28d9;
  --si:#1c7c43; --prov:#b45309; --no:#b91c1c; --fuera:#5b6473;
  --paper:#fbfaf6; --paper-ink:#1a1a1a; --hl:#f6e2a8;
  --mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace;
  --serif:"Iowan Old Style","Palatino Linotype",Palatino,"Book Antiqua",Georgia,serif;
  /* escala de espaciado: 4 · 8 · 12 · 16 · 24 · 32 */
}
@media (prefers-color-scheme:dark){:root{
  --bg:#0f1216; --panel:#161a20; --card:#1b1f27; --ink:#e7e9ec; --muted:#98a0ac;
  --line:#2a2f3a; --navy:#7ea9d8; --accent:#d9a441; --violet:#b794f6;
  --si:#4ade80; --prov:#fbbf24; --no:#f87171; --fuera:#98a0ac;
  --paper:#e9e6df; --paper-ink:#1a1a1a; --hl:#e7c877;
}}
*{box-sizing:border-box}
[hidden]{display:none!important}
body{margin:0;font:15px/1.55 -apple-system,system-ui,"Segoe UI",sans-serif;
  background:var(--bg);color:var(--ink)}

header{padding:16px 24px;border-bottom:2px solid var(--navy);background:var(--panel)}
header .kick{font:10.5px/1 var(--mono);letter-spacing:.17em;text-transform:uppercase;
  color:var(--accent);margin-bottom:6px}
header h1{margin:0;font-size:18px;font-weight:700;letter-spacing:-.015em}
header p{margin:6px 0 0;font-size:12.5px;color:var(--muted);max-width:74ch}
header p b{color:var(--navy)}
header .minfo{font:11px var(--mono);color:var(--muted);margin-top:5px}

main{display:grid;grid-template-columns:minmax(0,1.05fr) minmax(0,.95fr);
  height:calc(100vh - 60px)}
@media (max-width:900px){main{grid-template-columns:1fr;height:auto}}
#left{position:relative;padding:24px 24px 24px 44px;overflow-y:auto;
  display:flex;flex-direction:column;gap:24px}
#right{border-left:1px solid var(--line);background:var(--panel);
  padding:clamp(14px,3vw,24px);overflow-y:auto}
@media (max-width:900px){#right{border-left:0;border-top:1px solid var(--line)}}

.chips{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px}
.chip{font-size:11.5px;padding:5px 10px;border:1px solid var(--line);border-radius:999px;
  background:var(--card);color:var(--muted);cursor:pointer;transition:transform .15s,border-color .15s,color .15s}
.chip:hover{color:var(--ink);border-color:var(--navy);transform:translateY(-1px)}

/* espina del pipeline: cada etapa dibuja su marca + el segmento hacia la siguiente */
.stage{position:relative;background:var(--card);border:1px solid var(--line);border-radius:12px;
  padding:16px;opacity:.5;transition:opacity .25s}
.stage.on{opacity:1}
.stage::before{content:"";position:absolute;left:-26px;top:15px;width:12px;height:12px;
  border-radius:50%;background:var(--bg);border:2px solid var(--line);z-index:1;
  transition:background .3s,border-color .3s,box-shadow .3s}
.stage::after{content:"";position:absolute;left:-21px;top:20px;bottom:-26px;width:2px;
  background:var(--line);z-index:0}
.stage:last-child::after{display:none}
.stage.on::before{background:var(--navy);border-color:var(--navy);
  box-shadow:0 0 0 4px color-mix(in srgb,var(--navy) 14%,transparent)}
.stage.s3{opacity:1}  /* la leyenda del dictamen se lee antes de calcular */
.stage.s3.on{border-color:var(--navy);box-shadow:0 0 0 1px var(--navy) inset}
.stage h3{margin:0 0 8px;font-size:11px;letter-spacing:.06em;text-transform:uppercase;
  color:var(--muted);display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.stage h3 .n{color:var(--ink);font-weight:700}
.hp{font-size:12px;color:var(--muted);margin:0 0 12px}
.badge{font-size:10px;font-weight:700;letter-spacing:.03em;padding:2px 7px;border-radius:5px;
  text-transform:uppercase;color:#fff}
.badge.m{background:var(--violet)} .badge.d{background:var(--navy)}
.badge.e{background:var(--fuera)}
.hpx{font-size:11px;color:var(--muted);font-weight:400}

/* panel «cómo funciona» — <details> nativo, 0 JS */
details.how{margin:12px 24px 0;border:1px solid var(--line);border-radius:10px;
  background:var(--panel);overflow:hidden}
details.how>summary{cursor:pointer;padding:11px 16px;font-size:12.5px;font-weight:650;
  color:var(--navy);list-style:none}
details.how>summary::-webkit-details-marker{display:none}
details.how>summary::before{content:"▸ ";color:var(--accent)}
details.how[open]>summary::before{content:"▾ "}
details.how .body{padding:0 16px 14px;font-size:12.5px;line-height:1.6;color:var(--ink);max-width:88ch}
details.how .body p{margin:8px 0}
details.how .body b{color:var(--navy)}
details.how ol{margin:8px 0;padding-left:20px}
details.how ol li{margin:3px 0}

/* icono de ayuda: tooltip CSS + title nativo de reserva (táctil / a11y) */
.q{display:inline-flex;align-items:center;justify-content:center;width:14px;height:14px;
  border:1px solid var(--muted);color:var(--muted);border-radius:50%;font:700 9px/1 sans-serif;
  cursor:help;position:relative;vertical-align:1px}
.q:hover,.q:focus{border-color:var(--navy);color:var(--navy);outline:none}
.q::after{content:attr(data-tip);position:absolute;left:50%;bottom:calc(100% + 7px);
  transform:translateX(-50%);width:210px;background:var(--ink);color:var(--card);
  padding:8px 10px;border-radius:6px;font:400 11px/1.45 -apple-system,system-ui,sans-serif;
  text-align:left;opacity:0;pointer-events:none;transition:opacity .12s;z-index:6;
  box-shadow:0 4px 14px rgba(0,0,0,.18)}
.q:hover::after,.q:focus::after{opacity:1}
/* ponytail: tooltip puede recortarse contra el borde de #left (overflow:auto); el title nativo cubre ese caso */

.leyenda{border-collapse:collapse;margin:10px 0 12px;font-size:12px}
.leyenda td{padding:4px 8px 4px 0;vertical-align:top;color:var(--muted);line-height:1.45}
.leyenda td:first-child{white-space:nowrap}
.leyenda b{color:var(--ink)}

@keyframes rise{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
@keyframes pop{from{opacity:0;transform:scale(.9)}to{opacity:1;transform:none}}
@keyframes g{to{transform:rotate(360deg)}}
@keyframes fl{0%{background:color-mix(in srgb,var(--navy) 20%,var(--panel));
  box-shadow:0 0 0 2px var(--navy)}100%{background:var(--panel);box-shadow:0 0 0 0 transparent}}
.filled{animation:fl 1s ease}
.stage.s3.on{animation:rise .3s ease}
.deriv,.excusa{animation:rise .28s ease}

.verdict{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;margin:4px 0 12px}
.tag{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.04em;
  padding:3px 9px;border-radius:999px;color:#fff}
.tag.si{background:var(--si)} .tag.prov{background:var(--prov)}
.tag.no{background:var(--no)} .tag.fuera{background:var(--fuera)} .tag.falta{background:var(--fuera)}
.amount{font:700 36px/1 var(--mono);font-variant-numeric:tabular-nums;letter-spacing:-.03em;
  animation:pop .3s ease}
.amount .u{font-size:19px;font-weight:600;color:var(--muted)}
.art{font:13px var(--mono);color:var(--muted)}

.deriv{width:100%;border-collapse:collapse;font:13px/1.5 var(--mono);
  font-variant-numeric:tabular-nums;margin:8px 0 12px}
.deriv caption{caption-side:top;text-align:left;font-size:10px;letter-spacing:.04em;
  text-transform:uppercase;color:var(--muted);padding-bottom:6px}
.deriv td{padding:4px 0}
.deriv tr.pr td{border-bottom:1px dashed var(--line)}
.deriv td:last-child:not([colspan]){text-align:right;white-space:nowrap}
.deriv .k{color:var(--muted)}
.deriv tr.pr{cursor:pointer}
.deriv tr.pr:hover .k{color:var(--ink)}
.deriv tr.pr .k::before{content:"▸ ";color:var(--navy)}
.deriv tr.pr.open .k::before{content:"▾ "}
.deriv tr.src{display:none}
.deriv tr.src.show{display:table-row}
.deriv tr.src td{border:0;padding:2px 0 10px;font-size:11px;color:var(--muted);white-space:normal;line-height:1.4}
.deriv tr.gain td{color:var(--accent);font-weight:700}
.ctx{font:12px var(--mono);color:var(--muted);margin:4px 0 8px}
.ctx.gain{color:var(--accent);font-weight:700}

/* la excusa: careo a dos columnas — lo que alega la aerolínea vs. lo que dice la norma */
.excusa{display:grid;grid-template-columns:1fr 1fr;gap:12px 16px;
  border:1px solid var(--line);border-left:4px solid var(--fuera);border-radius:10px;
  padding:16px;margin:16px 0;background:var(--panel)}
.excusa.no{border-left-color:var(--si)}
.excusa.si,.excusa.prov{border-left-color:var(--prov)}
.excusa .col{display:flex;flex-direction:column;gap:5px;min-width:0}
.excusa .lbl{font:9.5px/1 var(--mono);letter-spacing:.07em;text-transform:uppercase;color:var(--muted)}
.excusa .col code{font-size:14px;color:var(--ink);word-break:break-word}
.excusa .dice{font-size:14px;line-height:1.4}
.excusa .dice b{color:var(--ink)}
.excusa .cite,.excusa .nota{grid-column:1/-1}
.excusa .cite{font:11.5px var(--mono);color:var(--muted);border-top:1px dashed var(--line);padding-top:10px}
.excusa .nota{font-size:12.5px;color:var(--ink);opacity:.85}
@media (max-width:520px){.excusa{grid-template-columns:1fr}}

.motivo{font-size:12.5px;color:var(--muted);border-top:1px solid var(--line);
  padding-top:12px;margin-top:12px}
.warn{color:var(--prov);font-size:12.5px;margin-top:8px}

textarea{width:100%;resize:vertical;min-height:72px;padding:10px 12px;border:1px solid var(--line);
  border-radius:9px;font:inherit;background:var(--panel);color:var(--ink)}
textarea:focus,.grid2 input:focus,.grid2 select:focus{outline:2px solid var(--navy);outline-offset:1px;border-color:var(--navy)}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.grid2 label{font-size:11px;color:var(--muted);display:flex;flex-direction:column;gap:4px}
.grid2 label .lh{display:flex;align-items:center;gap:5px;flex-wrap:wrap}
.grid2 input,.grid2 select{padding:8px 10px;border:1px solid var(--line);border-radius:8px;
  font:inherit;font-size:13px;background:var(--panel);color:var(--ink)}
.full{grid-column:1/-1}
form button.go{margin-top:16px;width:100%;padding:10px;border:0;border-radius:9px;
  background:var(--navy);color:#fff;font:inherit;font-weight:650;cursor:pointer;
  transition:filter .15s,transform .05s}
form button.go.ghost{background:transparent;color:var(--navy);border:1px solid var(--line)}
form button.go:not(:disabled):hover{filter:brightness(1.1)}
form button.go.ghost:not(:disabled):hover{background:color-mix(in srgb,var(--navy) 8%,transparent);filter:none}
form button.go:not(:disabled):active{transform:translateY(1px)}
form button.go:disabled{opacity:.5;cursor:default}

#right h2{font:12px/1 -apple-system,system-ui,sans-serif;letter-spacing:.06em;
  text-transform:uppercase;color:var(--muted);margin:0 0 4px}
#right .sub{font-size:12px;color:var(--muted);margin:0 0 16px}
.acts{margin:0 0 16px;display:flex;flex-wrap:wrap;gap:8px}
.acts button{background:var(--card);color:var(--ink);border:1px solid var(--line);
  border-radius:8px;padding:7px 12px;font:inherit;font-size:13px;cursor:pointer;transition:border-color .15s,color .15s}
.acts button:hover{border-color:var(--navy);color:var(--navy)}
#carta{white-space:pre-wrap;overflow-wrap:break-word;
  font:clamp(13px,.4vw + 12px,15px)/1.75 var(--serif);color:var(--paper-ink);
  background:var(--paper);border:1px solid var(--line);border-radius:6px;
  padding:clamp(20px,4vw,44px) clamp(18px,4.5vw,48px);
  box-shadow:0 1px 3px rgba(0,0,0,.06)}
#carta.vacio{font:13px -apple-system,system-ui,sans-serif;color:var(--muted);
  background:transparent;border:1px dashed var(--line);padding:24px;box-shadow:none}
#carta mark{background:var(--hl);color:#1a1a1a;padding:0 2px;border-radius:2px}
@media print{#carta mark{background:none;border:1px solid #999;color:#000}}

.spin{width:13px;height:13px;border:2px solid var(--line);border-top-color:var(--navy);
  border-radius:50%;display:inline-block;animation:g .8s linear infinite;vertical-align:-2px}

@media (prefers-reduced-motion:reduce){
  *,*::before,*::after{animation-duration:.001ms!important;animation-iteration-count:1!important;
    transition-duration:.001ms!important}
}
@media print{
  header,#left,#right h2,#right .sub,.acts{display:none}
  main{display:block;height:auto}
  #right{border:0;padding:0;background:#fff}
  #carta{border:0;padding:0;max-width:none;font-size:12pt;background:#fff;color:#000;box-shadow:none}
}
</style></head>
<body>
<header>
  <div class="kick">Reglamento (CE) 261/2004 · jurisprudencia del TJUE</div>
  <h1>Agente de reclamaciones de vuelo</h1>
  <div class="minfo" id="minfo"></div>
</header>

<details class="how">
  <summary>¿Cómo funciona? · por qué un motor de reglas y no un modelo</summary>
  <div class="body">
    <p>Calcula la compensación <b>máxima</b> que te debe una aerolínea por un vuelo retrasado,
       según el Reglamento (CE) 261/2004 y la jurisprudencia del TJUE.</p>
    <p>El importe, la elegibilidad y el artículo los decide un <b>motor de reglas determinista</b>:
       las mismas entradas dan siempre la misma salida, y cada paso cita su fuente (texto del
       Reglamento + sentencia, con su CELEX). Un modelo de lenguaje <b>no</b> decide nada de eso —
       puede equivocarse, y aquí equivocarse cuesta dinero.</p>
    <p>El modelo hace <b>una</b> cosa: si le pegas un caso en lenguaje natural (etapa 1), lo
       transcribe a los campos de la etapa 2. Nada más. Puedes saltártelo y rellenar la etapa 2 a mano.</p>
    <ol>
      <li><b>El caso</b> — opcional. Texto libre → el modelo saca los datos del vuelo.</li>
      <li><b>Los hechos</b> — los 8 campos que entran al motor. La única entrada real.</li>
      <li><b>El dictamen</b> — el motor aplica 5 pasos fijos (ámbito → umbral de 3 h → plazo →
          circunstancia extraordinaria → banda del art. 7) y devuelve el importe, el artículo y la traza.</li>
    </ol>
    <p>La carta de reclamación (derecha) la redacta una plantilla a partir del dictamen; no toca el importe.</p>
  </div>
</details>

<main>
  <section id="left">

    <div class="stage s1 on" id="st1">
      <h3><span class="n">1 · El caso</span> <span class="badge e">opcional · intake por IA</span></h3>
      <p class="hp">Texto libre: vuelo, fecha, retraso a la llegada, la excusa de la aerolínea y lo que te
         ofrecieron. El modelo lo lee y <b>rellena la etapa 2</b> — no calcula nada. Si prefieres,
         sáltate esta etapa y rellena la 2 a mano.</p>
      <div class="chips" id="chips"></div>
      <form id="fR" autocomplete="off">
        <textarea id="t" placeholder="Vuelo y fecha, retraso a la llegada, qué excusa dio la aerolínea, qué te ofrecieron…"></textarea>
        <button class="go ghost" id="goR">Rellenar la etapa 2 con el modelo</button>
      </form>
    </div>

    <div class="stage s2 on" id="st2">
      <h3><span class="n">2 · Los hechos del vuelo</span> <span class="badge e" id="b2">a mano</span></h3>
      <p class="hp">Estos 8 campos son <b>todo</b> lo que entra al motor. Si usaste la etapa 1, el modelo
         solo ha rellenado estas casillas: <b>revísalas y corrígelas</b> antes de calcular. Origen y
         destino en código IATA (MAD, BCN, JFK…).</p>
      <form id="fF" autocomplete="off">
        <div class="grid2">
          <label>Origen (IATA)<input id="f_origen" maxlength="3"></label>
          <label>Destino (IATA)<input id="f_destino" maxlength="3"></label>
          <label><span class="lh">Retraso a la llegada (h) <span class="q" tabindex="0" data-tip="Horas entre la llegada prevista y la real. El umbral del 261 (TJUE Sturgeon, C-402/07) son 3 h EN DESTINO, no en salida." title="Horas entre la llegada prevista y la real. Umbral: 3 h en destino (TJUE C-402/07).">?</span></span><input id="f_retraso" type="number" step="0.5" min="0"></label>
          <label>Fecha del vuelo<input id="f_fecha" type="date"></label>
          <label class="full">Causa que alega la aerolínea<select id="f_causa"></select></label>
          <label><span class="lh">Oferta de la aerolínea (€) <span class="q" tabindex="0" data-tip="Lo que la aerolínea ya te ha ofrecido, si algo. El motor calcula cuánto reclamas de más por encima de esa oferta." title="Lo ya ofrecido. El motor calcula cuánto reclamas por encima.">?</span></span><input id="f_oferta" type="number" step="1" min="0"></label>
          <label><span class="lh">País de la reclamación <span class="q" tabindex="0" data-tip="Fija el plazo de prescripción, que decide cada ley nacional (TJUE C-139/11). En España son 5 años. Si no está verificado para ese país, el dictamen lo avisa." title="Fija el plazo de prescripción (ley nacional, TJUE C-139/11). ES: 5 años.">?</span></span><input id="f_pais" maxlength="2"></label>
          <label class="full"><span class="lh">Transportista comunitario <span class="q" tabindex="0" data-tip="Compañía con licencia de un Estado de la UE. Solo importa cuando el vuelo ENTRA a la UE desde un país tercero: si no es comunitario, el 261 no aplica (art. 3(1)(b))." title="Compañía con licencia de un Estado UE. Solo importa en vuelos que entran a la UE (art. 3(1)(b)).">?</span> <span class="hpx">(solo vuelos que ENTRAN a la UE)</span></span>
            <select id="f_tc"><option value="">no aplica / no lo sé</option><option value="si">sí</option><option value="no">no</option></select></label>
          <label class="full" style="flex-direction:row;align-items:center;gap:7px">
            <input type="checkbox" id="f_llm" style="width:auto"> redactar la carta con el modelo (más lento; sin marcar sale la plantilla determinista)</label>
        </div>
        <button class="go" id="goF">Calcular con el motor de reglas</button>
      </form>
    </div>

    <div class="stage s3" id="st3">
      <h3><span class="n">3 · El dictamen</span> <span class="badge d">motor de reglas · determinista</span></h3>
      <div id="c3">
        <p class="hp">Rellena la etapa 2 y pulsa «Calcular». El motor devuelve uno de estos estados:</p>
        <table class="leyenda">
          <tr><td><span class="tag si">con derecho</span></td><td>cumple todo; el importe es firme.</td></tr>
          <tr><td><span class="tag prov">provisional</span></td><td>cumple, pero la aerolínea alega una circunstancia que <b>podría</b> eximirla; se reclama igual y ella debe acreditarla.</td></tr>
          <tr><td><span class="tag no">sin derecho</span></td><td>no llega al umbral de 3 h, o la circunstancia sí exime.</td></tr>
          <tr><td><span class="tag fuera">fuera de ámbito</span></td><td>el vuelo no lo cubre el art. 3 del Reglamento.</td></tr>
          <tr><td><span class="tag falta">falta un dato</span></td><td>hace falta algún campo para poder decidir.</td></tr>
        </table>
        <p class="hp">La <b>traza</b> lista los pasos que aplicó el motor (los 5 fijos más la
           reducción del art. 7(2) y la comparación con la oferta, si tocan). Clic en un paso →
           la fuente exacta: texto del Reglamento o sentencia del TJUE, con su CELEX y fecha.</p>
      </div>
    </div>
  </section>

  <section id="right">
    <h2>Carta de reclamación</h2>
    <p class="sub">La redacta <code>carta.py</code> a partir del dictamen. El importe y el artículo no los toca esta capa.</p>
    <div class="acts" id="acts" hidden>
      <button id="bCopy" onclick="cp()">Copiar carta</button>
      <button onclick="print()">Imprimir / Guardar PDF</button>
      <button onclick="dl()">Descargar .txt</button>
    </div>
    <p class="sub" id="hint" hidden>Los <code>[corchetes]</code> son huecos que rellenas tú (nombre, localizador, IBAN…).</p>
    <div id="carta" class="vacio">Aún no hay dictamen.</div>
  </section>
</main>

<script>
const $=s=>document.querySelector(s);
const EJ=_EJEMPLOS_, CATS=_CATS_, LAB=_LAB_, MINFO=_MODELOINFO_;
let ultimaCarta='';
const nf=n=>Number(n).toLocaleString('es-ES',{maximumFractionDigits:1});
const esc=s=>(s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));

$('#minfo').textContent = MINFO.hay_clave
  ? 'intake por IA disponible · modelo '+MINFO.modelo+' ('+MINFO.proveedor+')'
  : 'sin clave de modelo — la etapa 1 está desactivada; rellena la etapa 2 a mano';
if(!MINFO.hay_clave){$('#t').disabled=true;$('#goR').disabled=true;$('#st1').style.opacity=.4}

EJ.forEach(x=>{const c=document.createElement('span');c.className='chip';
  c.textContent=x.length>52?x.slice(0,52)+'…':x;c.title=x;
  c.onclick=()=>{$('#t').value=x;$('#t').focus()};$('#chips').appendChild(c)});

// arrancar siempre en limpio: Chrome restaura los campos al recargar
$('#fR').reset(); $('#fF').reset();
addEventListener('pageshow',e=>{if(e.persisted){$('#fR').reset();$('#fF').reset()}});

const selC=$('#f_causa');
CATS.forEach(c=>{const o=document.createElement('option');o.value=c;o.textContent=LAB[c]||c;selC.appendChild(o)});
selC.value='desconocida';

function dl(){const a=document.createElement('a');
  a.href=URL.createObjectURL(new Blob([ultimaCarta],{type:'text/plain'}));
  a.download='reclamacion.txt';a.click()}
async function cp(){
  try{await navigator.clipboard.writeText(ultimaCarta);}
  catch(e){const t=document.createElement('textarea');t.value=ultimaCarta;document.body.appendChild(t);
    t.select();document.execCommand('copy');t.remove();}
  const b=$('#bCopy');const o=b.textContent;b.textContent='✓ copiada';setTimeout(()=>b.textContent=o,1500);
}

function stage(id,on){$('#'+id).classList.toggle('on',on)}
function tg(el){el.classList.toggle('open');const s=el.nextElementSibling;
  if(s&&s.classList.contains('src'))s.classList.toggle('show')}
function flash(el){el.classList.remove('filled');void el.offsetWidth;el.classList.add('filled')}

const F={origen:'f_origen',destino:'f_destino',retraso_llegada_h:'f_retraso',fecha_vuelo:'f_fecha',
  causa_categoria:'f_causa',oferta_aerolinea_eur:'f_oferta',pais_reclamacion:'f_pais'};

function poblarForm(h){
  for(const [k,id] of Object.entries(F)){
    const el=$('#'+id); if(!el) continue;
    let v=h[k]; if(v==null)v='';
    el.value=v; flash(el);
  }
  const tc=$('#f_tc');
  tc.value = h.transportista_comunitario===true?'si':h.transportista_comunitario===false?'no':'';
  flash(tc);
}

function busy(on){document.querySelectorAll('.go').forEach(b=>b.disabled=on)}

// ETAPA 1 · relato -> el modelo rellena la etapa 2, luego se pinta el dictamen
$('#fR').onsubmit=async e=>{
  e.preventDefault();
  const v=$('#t').value.trim(); if(!v) return;
  stage('st3',false);
  $('#c3').innerHTML='<span class="spin"></span> <span class="hp">el modelo está leyendo el caso…</span>';
  $('#b2').textContent='leyendo…'; $('#b2').className='badge m'; busy(true);
  try{
    const r=await fetch('/api/reclamar',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({relato:v})});
    const j=await r.json();
    if(!j.ok){$('#c3').innerHTML='<span style="color:var(--no)">'+esc(j.error)+'</span>';
      $('#b2').textContent='error'; $('#b2').className='badge e';}
    else if(j.estado==='faltan_datos'){
      $('#b2').textContent='✎ del modelo · incompleto'; $('#b2').className='badge m';
      $('#c3').innerHTML='<span style="color:var(--prov)">El modelo no pudo sacar: <b>'+
        esc((j.faltan||[]).join(', '))+'</b>. Complétalo arriba y pulsa «Calcular».</span>';
    }else{
      poblarForm(j.hechos);
      $('#b2').textContent='✎ del modelo'+(j.latencia_ms!=null?' · '+j.latencia_ms+' ms':'')+
        (j.modelo_usado?' · '+j.modelo_usado.split('/').pop():'');
      $('#b2').className='badge m';
      // ponytail: el dictamen solo lo pinta la etapa 2; aquí solo se rellenan los campos
      $('#c3').innerHTML='<span class="hp">Campos rellenados. Revísalos y pulsa «Calcular con el motor de reglas».</span>';
    }
  }catch(err){$('#c3').innerHTML='<span style="color:var(--no)">Error de red: '+esc(''+err)+'</span>';}
  busy(false);
};

// ETAPA 2 · los datos (a mano o retocados) -> motor de reglas, 0 IA
$('#fF').onsubmit=async e=>{
  e.preventDefault();
  const h={origen:$('#f_origen').value,destino:$('#f_destino').value,
    retraso_llegada_h:$('#f_retraso').value,fecha_vuelo:$('#f_fecha').value,
    causa_categoria:$('#f_causa').value,oferta_aerolinea_eur:$('#f_oferta').value,
    pais_reclamacion:$('#f_pais').value,transportista_comunitario:$('#f_tc').value,
    carta_llm:$('#f_llm').checked?1:''};
  if(!h.origen||!h.destino||!h.retraso_llegada_h){
    $('#c3').innerHTML='<span style="color:var(--prov)">Faltan origen, destino o retraso.</span>';return;}
  stage('st3',false); $('#c3').innerHTML='<span class="spin"></span> <span class="hp">motor de reglas…</span>';
  $('#b2').textContent='a mano'; $('#b2').className='badge e'; busy(true);
  try{
    const r=await fetch('/api/reclamar',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({hechos:h})});
    const j=await r.json();
    if(!j.ok)$('#c3').innerHTML='<span style="color:var(--no)">'+esc(j.error)+'</span>';
    else render3(j);
  }catch(err){$('#c3').innerHTML='<span style="color:var(--no)">Error de red: '+esc(''+err)+'</span>';}
  busy(false);
};

function excusa(j){
  const c=j.causa_categoria;
  const evaluada=(j.traza||[]).some(p=>p.paso.indexOf('circunstancia')===0);
  if(!c||c==='desconocida'||!evaluada)return '';  // no se llegó a valorar la excusa
  let cls,txt;
  if(j.circunstancia_exime===false){cls='no';txt='<b>NO exime</b> — tienes derecho a la compensación';}
  else if(j.circunstancia_exime===true){cls='si';txt='<b>puede eximir</b> si la aerolínea lo acredita';}
  else{cls='prov';txt='<b>provisional</b> — la aerolínea debe acreditarlo primero';}
  return '<div class="excusa '+cls+'">'+
    '<div class="col"><span class="lbl">la aerolínea alega</span><code>'+esc(c)+'</code></div>'+
    '<div class="col dice"><span class="lbl">Reglamento 261 + TJUE</span><span>'+txt+'</span></div>'+
    (j.sentencia?'<div class="cite">'+esc(j.sentencia)+'</div>':'')+
    (j.nota_precedente?'<div class="nota">'+esc(j.nota_precedente)+'</div>':'')+'</div>';
}

function traza(tz){
  if(!tz||!tz.length)return '';
  let h='<table class="deriv"><caption>traza del motor · clic en un paso para ver la fuente</caption>';
  tz.forEach(p=>{
    const gain=p.paso==='oferta de la aerolínea';
    h+='<tr class="pr'+(gain?' gain':'')+'" onclick="tg(this)"><td class="k">'+esc(p.paso)+
       '</td><td>'+esc(p.resultado)+'</td></tr>';
    if(p.fuente)h+='<tr class="src"><td colspan="2">'+esc(p.fuente)+'</td></tr>';
  });
  h+='</table>';
  return h;
}

function render3(j){
  stage('st3',true);
  const T={si:'con derecho',prov:'provisional',no:'sin derecho',fuera:'fuera de ámbito',falta:'falta un dato'};
  let h='<div class="verdict"><span class="tag '+j.clase+'">'+T[j.clase]+'</span>';
  if(j.elegible)h+='<span class="amount">'+nf(j.importe_eur)+'<span class="u"> €</span></span><span class="art">'+esc(j.articulo||'')+'</span>';
  else h+='<span class="amount">0<span class="u"> €</span></span>';
  h+='</div>';
  if(j.clase!=='falta'&&j.distancia_km)h+='<div class="ctx">'+nf(j.distancia_km)+
    ' km <span class="q" tabindex="0" data-tip="Distancia ortodrómica entre aeropuertos (art. 7(4) del Reglamento), no la de la ruta real." title="Distancia ortodrómica (art. 7(4)), no la de la ruta real.">?</span> · '+
    (j.intracomunitario?'intracomunitario':'no intracomunitario')+'</div>';
  h+=traza(j.traza);
  if(j.deficit_eur!=null)h+='<div class="ctx gain">reclamas '+nf(j.deficit_eur)+' € de más de lo ofrecido</div>';
  h+=excusa(j);
  if(j.plazo_incierto)h+='<div class="warn">⚠ Posible prescripción: el plazo para reclamar en ese país no está verificado. Confírmalo con un abogado local.</div>';
  if(j.clase==='prov')h+='<div class="warn">Se reclama igualmente; la aerolínea aún debe acreditar la circunstancia que alega.</div>';
  h+='<div class="motivo">'+esc(j.motivo)+'</div>';
  $('#c3').innerHTML=h;

  if(j.carta){ultimaCarta=j.carta;$('#carta').className='';
    $('#carta').innerHTML=esc(j.carta).replace(/\[[^\]\n]+\]/g,m=>'<mark>'+m+'</mark>');
    $('#acts').hidden=false;$('#hint').hidden = j.carta.indexOf('[')<0}
  else{$('#carta').className='vacio';$('#carta').textContent='Sin carta para este caso.';
    $('#acts').hidden=true;$('#hint').hidden=true}
}
</script>
</body></html>
"""


def _modelo_info() -> dict:
    try:
        import llm
        return {"modelo": llm.modelo(), "proveedor": llm.proveedor(),
                "hay_clave": bool(llm.api_key())}
    except Exception:
        return {"modelo": "?", "proveedor": "?", "hay_clave": False}


def render_pagina() -> str:
    return (PAGINA
            .replace("_EJEMPLOS_", json.dumps(_EJEMPLOS))
            .replace("_CATS_", json.dumps(list(CATEGORIAS)))
            .replace("_LAB_", json.dumps(_CAUSA_LABEL))
            .replace("_MODELOINFO_", json.dumps(_modelo_info())))


class _H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, code, body, ctype="text/html; charset=utf-8"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, render_pagina())
        else:
            self._send(404, "no")

    def do_POST(self):
        if self.path != "/api/reclamar":
            self._send(404, "no")
            return
        try:
            n = int(self.headers.get("Content-Length", 0))
            entrada = json.loads(self.rfile.read(n) or b"{}")
            from agente import procesar
            out = payload(entrada, lambda *a, **k: procesar(*a, escribir_html=False, pdf=False, **k))
        except Exception:
            out = {"ok": False, "error": traceback.format_exc(limit=2)}
        self._send(200, json.dumps(out), "application/json; charset=utf-8")


def _check() -> None:
    firme = lambda relato, **k: {"estado": "ok", "fuente_hechos": k.get("_f", "modelo"),
        "dictamen": {"elegible": True, "importe_eur": 600, "articulo": "art. 7(1)(c)",
                     "importe_base_eur": 600, "distancia_km": 5765.0, "intracomunitario": False,
                     "provisional": False, "en_ambito": True, "circunstancia_exime": False,
                     "causa_categoria": "fallo_tecnico", "nota_precedente": "Un problema técnico…",
                     "motivo": "Retraso de 4 h.", "sentencia": "TJUE C-549/07; C-257/14"},
        "hechos": {"origen": "MAD", "destino": "JFK", "retraso_llegada_h": 4.0,
                   "causa_categoria": "fallo_tecnico", "oferta_aerolinea_eur": 250.0},
        "carta": {"tipo": "firme", "texto": "… le requiero el abono de 600 € …"}}

    p = payload({"relato": "MAD-JFK 4h fallo tecnico, ofrecen 250"}, firme)
    assert p["ok"] and p["clase"] == "si" and p["importe_eur"] == 600
    assert p["deficit_eur"] == 350.0 and p["modo"] == "relato"
    assert p["circunstancia_exime"] is False and "C-549/07" in p["sentencia"]

    p = payload({"hechos": {"origen": "mad", "destino": "jfk", "retraso_llegada_h": "4",
                            "causa_categoria": "fallo_tecnico", "oferta_aerolinea_eur": "250"}}, firme)
    assert p["ok"] and p["modo"] == "form" and p["deficit_eur"] == 350.0

    assert not payload({"relato": ""}, firme)["ok"]
    assert not payload({"hechos": {"origen": "MAD"}}, firme)["ok"]

    def boom(*a, **k):
        raise RuntimeError("proveedor caído")
    assert "proveedor" in payload({"relato": "x"}, boom)["error"]

    prov = lambda relato, **k: {"estado": "ok", "fuente_hechos": "modelo",
        "dictamen": {"elegible": True, "importe_eur": 400, "articulo": "art. 7(1)(b)",
                     "provisional": True, "en_ambito": True, "circunstancia_exime": None,
                     "causa_categoria": "meteorologia", "motivo": "Alega meteo."},
        "hechos": {}, "carta": {"tipo": "provisional", "texto": "…"}}
    assert payload({"relato": "x"}, prov)["clase"] == "prov"

    falta = lambda relato, **k: {"estado": "faltan_datos", "faltan": ["retraso_llegada_h"]}
    assert payload({"relato": "x"}, falta)["estado"] == "faltan_datos"

    # el HTML sale bien tras todas las sustituciones
    page = render_pagina()
    for tok in ("_EJEMPLOS_", "_CATS_", "_LAB_", "_MODELOINFO_"):
        assert tok not in page, tok
    assert "3 · El dictamen" in page and "@media print" in page and "visibility:hidden" not in page
    assert '"hay_clave"' in page
    # el badge de la etapa 2 arranca neutro ("a mano"), nunca "modelo" antes de un submit
    assert 'id="b2">a mano</span>' in page and "único punto de juicio" not in page
    print("servidor.py: OK")


def main() -> None:
    if "--check" in sys.argv:
        _check()
        return
    puerto = next((int(a) for a in sys.argv[1:] if a.isdigit()), PUERTO)
    import entorno  # noqa: F401  (carga ../1/.env)
    srv = ThreadingHTTPServer(("127.0.0.1", puerto), _H)
    print(f"  Agente EU261 → http://127.0.0.1:{puerto}   (Ctrl-C para parar)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
