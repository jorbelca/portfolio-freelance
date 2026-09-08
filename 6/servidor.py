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
        return {"ok": False, "error": "Escribe el relato del vuelo."}
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
  --bg:#eceef1; --panel:#f7f8fa; --card:#fff; --ink:#1c1f26; --muted:#6b7280;
  --line:#dfe3e8; --navy:#1e3a5f; --violet:#6d28d9;
  --si:#15803d; --prov:#b45309; --no:#b91c1c; --fuera:#475569;
  --paper:#fdfcfa; --paper-ink:#1a1a1a;
  --mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace;
  --serif:Georgia,"Times New Roman",serif;
}
@media (prefers-color-scheme:dark){:root{
  --bg:#0f1115; --panel:#161922; --card:#1c2029; --ink:#e8eaed; --muted:#9aa1ac;
  --line:#2b303b; --navy:#8bb4e0; --violet:#b794f6;
  --si:#4ade80; --prov:#fbbf24; --no:#f87171; --fuera:#94a3b8;
  --paper:#e9e7e1; --paper-ink:#1a1a1a;
}}
*{box-sizing:border-box}
[hidden]{display:none!important}
body{margin:0;font:15px/1.55 -apple-system,system-ui,"Segoe UI",sans-serif;
  background:var(--bg);color:var(--ink)}
header{padding:14px 22px;border-bottom:1px solid var(--line);background:var(--panel);
  display:flex;flex-wrap:wrap;align-items:baseline;gap:6px 16px}
header h1{margin:0;font-size:15px;font-weight:650}
header p{margin:0;font-size:12px;color:var(--muted)}
.legend{margin-left:auto;font-size:11px;color:var(--muted);display:flex;gap:14px}
.legend i{font-style:normal;display:inline-flex;align-items:center;gap:5px}
.dot{width:8px;height:8px;border-radius:50%;display:inline-block}
.dot.m{background:var(--violet)} .dot.d{background:var(--navy)}
main{display:grid;grid-template-columns:minmax(0,1.05fr) minmax(0,.95fr);
  height:calc(100vh - 52px)}
@media (max-width:900px){main{grid-template-columns:1fr;height:auto}}
#left{padding:18px 20px;overflow-y:auto;display:flex;flex-direction:column;gap:14px}
#right{border-left:1px solid var(--line);background:var(--panel);padding:20px;overflow-y:auto}
@media (max-width:900px){#right{border-left:0;border-top:1px solid var(--line)}}

.chips{display:flex;flex-wrap:wrap;gap:6px}
.chip{font-size:11.5px;padding:5px 10px;border:1px solid var(--line);border-radius:999px;
  background:var(--card);color:var(--muted);cursor:pointer}
.chip:hover{color:var(--ink);border-color:var(--navy)}

.stage{background:var(--card);border:1px solid var(--line);border-radius:12px;
  padding:14px 16px;opacity:.45;transition:opacity .2s}
.stage.on{opacity:1}
.stage.s3.on{border-color:var(--navy)}
.stage h3{margin:0 0 8px;font-size:11px;letter-spacing:.06em;text-transform:uppercase;
  color:var(--muted);display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.stage h3 .n{color:var(--ink);font-weight:700}
.badge{font-size:10px;font-weight:700;letter-spacing:.03em;padding:2px 7px;border-radius:5px;
  text-transform:uppercase;color:#fff}
.badge.m{background:var(--violet)} .badge.d{background:var(--navy)}
.badge.e{background:var(--fuera)}

.relato-txt{white-space:pre-wrap;font-size:14px}
.facts{display:grid;grid-template-columns:auto 1fr;gap:3px 14px;font:13px/1.5 var(--mono);
  font-variant-numeric:tabular-nums}
.facts dt{color:var(--muted)}
.facts dd{margin:0}
.metaline{margin-top:8px;font:11.5px var(--mono);color:var(--muted)}

.verdict{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;margin:2px 0 10px}
.tag{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.04em;
  padding:3px 9px;border-radius:999px;color:#fff}
.tag.si{background:var(--si)} .tag.prov{background:var(--prov)}
.tag.no{background:var(--no)} .tag.fuera{background:var(--fuera)} .tag.falta{background:var(--fuera)}
.amount{font:700 30px/1 var(--mono);font-variant-numeric:tabular-nums;letter-spacing:-.02em}
.amount .u{font-size:18px;font-weight:600;color:var(--muted)}
.art{font:13px var(--mono);color:var(--muted)}

.deriv{width:100%;border-collapse:collapse;font:13px/1.5 var(--mono);
  font-variant-numeric:tabular-nums;margin:4px 0 10px}
.deriv td{padding:3px 0;border-bottom:1px dashed var(--line)}
.deriv td:last-child{text-align:right;white-space:nowrap}
.deriv .k{color:var(--muted)}
.deriv .tot td{border-bottom:0;font-weight:700;font-size:14px}
.deriv .gain td{color:var(--navy);font-weight:700}

.excusa{border:1px solid var(--line);border-left:3px solid var(--fuera);border-radius:8px;
  padding:10px 12px;margin:10px 0;font-size:13px}
.excusa.no{border-left-color:var(--si)}
.excusa.si,.excusa.prov{border-left-color:var(--prov)}
.excusa .hd{font-weight:600}
.excusa .cite{font:12px var(--mono);color:var(--muted);margin-top:3px}
.excusa .nota{color:var(--muted);margin-top:5px;font-size:12.5px}

.motivo{font-size:12.5px;color:var(--muted);border-top:1px solid var(--line);
  padding-top:8px;margin-top:8px}
.warn{color:var(--prov);font-size:12.5px;margin-top:6px}

.composer{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px}
.tabs{display:flex;gap:4px;margin-bottom:10px}
.tabs button{flex:1;padding:7px;border:1px solid var(--line);border-radius:8px;background:transparent;
  color:var(--muted);font:inherit;font-size:13px;cursor:pointer}
.tabs button.sel{background:var(--navy);border-color:var(--navy);color:#fff;font-weight:600}
textarea{width:100%;resize:vertical;min-height:76px;padding:10px 12px;border:1px solid var(--line);
  border-radius:9px;font:inherit;background:var(--panel);color:var(--ink)}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.grid2 label{font-size:11px;color:var(--muted);display:flex;flex-direction:column;gap:3px}
.grid2 input,.grid2 select{padding:7px 9px;border:1px solid var(--line);border-radius:8px;
  font:inherit;font-size:13px;background:var(--panel);color:var(--ink)}
.full{grid-column:1/-1}
form button.go{margin-top:10px;width:100%;padding:9px;border:0;border-radius:9px;
  background:var(--navy);color:#fff;font:inherit;font-weight:650;cursor:pointer}
form button.go:disabled{opacity:.5;cursor:default}

#right h2{font:12px/1 -apple-system,system-ui,sans-serif;letter-spacing:.06em;
  text-transform:uppercase;color:var(--muted);margin:0 0 4px}
#right .sub{font-size:12px;color:var(--muted);margin:0 0 14px}
.acts{margin:0 0 14px;display:flex;gap:8px}
.acts button{background:var(--card);color:var(--ink);border:1px solid var(--line);
  border-radius:8px;padding:6px 12px;font:inherit;font-size:13px;cursor:pointer}
#carta{white-space:pre-wrap;font:15px/1.75 var(--serif);color:var(--paper-ink);
  background:var(--paper);border:1px solid var(--line);border-radius:6px;
  padding:44px 48px;max-width:66ch}
#carta.vacio{font:13px -apple-system,system-ui,sans-serif;color:var(--muted);
  background:transparent;border:1px dashed var(--line);padding:20px}
#carta mark{background:#fde68a;color:#1a1a1a;padding:0 2px;border-radius:2px}
@media print{#carta mark{background:none;border:1px solid #999;color:#000}}

.spin{width:13px;height:13px;border:2px solid var(--line);border-top-color:var(--navy);
  border-radius:50%;display:inline-block;animation:g .8s linear infinite;vertical-align:-2px}
@keyframes g{to{transform:rotate(360deg)}}

@media print{
  header,#left,#right h2,#right .sub,.acts{display:none}
  main{display:block;height:auto}
  #right{border:0;padding:0;background:#fff}
  #carta{border:0;padding:0;max-width:none;font-size:12pt;background:#fff;color:#000}
}
</style></head>
<body>
<header>
  <h1>Agente de reclamaciones · Reglamento (CE) 261/2004</h1>
  <p>El importe y la elegibilidad los fija un motor de reglas determinista.</p>
  <div class="legend">
    <i><span class="dot m"></span>modelo</i>
    <i><span class="dot d"></span>motor determinista</i>
    <i id="minfo"></i>
  </div>
</header>
<main>
  <section id="left">
    <div class="chips" id="chips"></div>

    <div class="composer">
      <div class="tabs">
        <button id="tabR" class="sel">Relato libre</button>
        <button id="tabF">Datos del vuelo</button>
      </div>
      <form id="fR">
        <textarea id="t" placeholder="Origen y destino, retraso a la llegada, fecha del vuelo, qué excusa dio la aerolínea, qué te ofrecieron…"></textarea>
        <button class="go" id="goR">Analizar</button>
      </form>
      <form id="fF" hidden>
        <div class="grid2">
          <label>Origen (IATA)<input id="f_origen" maxlength="3" placeholder="MAD"></label>
          <label>Destino (IATA)<input id="f_destino" maxlength="3" placeholder="JFK"></label>
          <label>Retraso a la llegada (h)<input id="f_retraso" type="number" step="0.5" min="0" placeholder="4"></label>
          <label>Fecha del vuelo<input id="f_fecha" type="date"></label>
          <label class="full">Causa que alega la aerolínea<select id="f_causa"></select></label>
          <label>Oferta de la aerolínea (€)<input id="f_oferta" type="number" step="1" min="0" placeholder="250"></label>
          <label>País de la reclamación<input id="f_pais" maxlength="2" placeholder="ES"></label>
          <label class="full">Transportista comunitario (solo vuelos que entran a la UE)
            <select id="f_tc"><option value="">no aplica / no lo sé</option><option value="si">sí</option><option value="no">no</option></select></label>
          <label class="full" style="flex-direction:row;align-items:center;gap:7px">
            <input type="checkbox" id="f_llm" style="width:auto"> redactar la carta con el modelo (más lento; sin marcar sale la plantilla determinista)</label>
        </div>
        <button class="go" id="goF">Calcular</button>
      </form>
    </div>

    <div class="stage s1" id="st1">
      <h3><span class="n">1 · Relato</span> <span class="badge e">entrada</span></h3>
      <div class="relato-txt" id="c1">—</div>
    </div>

    <div class="stage s2" id="st2">
      <h3><span class="n">2 · Hechos extraídos</span> <span class="badge m" id="b2">modelo · único punto de juicio</span></h3>
      <div id="c2"><span class="relato-txt" style="color:var(--muted)">—</span></div>
    </div>

    <div class="stage s3" id="st3">
      <h3><span class="n">3 · Dictamen</span> <span class="badge d">motor determinista · 0 llamadas al modelo</span></h3>
      <div id="c3"><span class="relato-txt" style="color:var(--muted)">—</span></div>
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

if(MINFO.hay_clave){$('#minfo').textContent='modelo: '+MINFO.modelo+' · '+MINFO.proveedor}
else{$('#minfo').textContent='sin clave de modelo — solo «Datos del vuelo»';
  $('#tabR').disabled=true;$('#t').disabled=true;$('#goR').disabled=true;setTab('F')}

EJ.forEach(x=>{const c=document.createElement('span');c.className='chip';
  c.textContent=x.length>52?x.slice(0,52)+'…':x;c.title=x;
  c.onclick=()=>{setTab('R');$('#t').value=x;$('#t').focus()};$('#chips').appendChild(c)});

const selC=$('#f_causa');
CATS.forEach(c=>{const o=document.createElement('option');o.value=c;o.textContent=LAB[c]||c;selC.appendChild(o)});
selC.value='desconocida';

function setTab(m){
  const R=m==='R';
  $('#tabR').classList.toggle('sel',R); $('#tabF').classList.toggle('sel',!R);
  $('#fR').hidden=!R; $('#fF').hidden=R;
}
$('#tabR').onclick=()=>setTab('R'); $('#tabF').onclick=()=>setTab('F');

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
function reset(){['st1','st2','st3'].forEach(i=>stage(i,false));
  $('#c1').textContent='—';
  $('#c2').innerHTML='<span class="relato-txt" style="color:var(--muted)">—</span>';
  $('#c3').innerHTML='<span class="relato-txt" style="color:var(--muted)">—</span>'}

async function enviar(body,relatoVisible,modelo){
  reset();
  stage('st1',true); $('#c1').textContent=relatoVisible;
  $('#b2').textContent = modelo ? 'modelo · único punto de juicio' : 'datos introducidos a mano';
  $('#b2').className = 'badge '+(modelo?'m':'e');
  stage('st2',true);
  $('#carta').className='vacio'; $('#carta').textContent='Generando…'; $('#acts').hidden=true;
  $('#c2').innerHTML = modelo
    ? '<span class="spin"></span> <span style="color:var(--muted)">interpretando el relato…</span>'
    : '<span style="color:var(--muted)">…</span>';
  document.querySelectorAll('.go').forEach(b=>b.disabled=true);
  try{
    const r=await fetch('/api/reclamar',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body)});
    render(await r.json());
  }catch(e){ $('#c2').innerHTML='<span style="color:var(--no)">Error de red: '+esc(''+e)+'</span>'; }
  document.querySelectorAll('.go').forEach(b=>b.disabled=false);
}

$('#fR').onsubmit=e=>{e.preventDefault();const v=$('#t').value.trim();if(!v)return;
  enviar({relato:v},v,true)};
$('#fF').onsubmit=e=>{e.preventDefault();
  const h={origen:$('#f_origen').value,destino:$('#f_destino').value,
    retraso_llegada_h:$('#f_retraso').value,fecha_vuelo:$('#f_fecha').value,
    causa_categoria:$('#f_causa').value,oferta_aerolinea_eur:$('#f_oferta').value,
    pais_reclamacion:$('#f_pais').value,transportista_comunitario:$('#f_tc').value,
    carta_llm:$('#f_llm').checked?1:''};
  const vis=[h.origen||'?',h.destino||'?',(h.retraso_llegada_h||'?')+' h',h.causa_categoria].filter(Boolean).join(' · ');
  enviar({hechos:h},vis.toUpperCase(),false)};

function facts(h){
  const row=(k,v)=>v==null||v===''||v===false?'':'<dt>'+k+'</dt><dd>'+esc(''+v)+'</dd>';
  return '<dl class="facts">'+
    row('origen',h.origen)+row('destino',h.destino)+
    row('retraso',h.retraso_llegada_h!=null?h.retraso_llegada_h+' h':'')+
    row('causa',h.causa_categoria)+
    row('fecha vuelo',h.fecha_vuelo)+
    row('oferta',h.oferta_aerolinea_eur!=null?h.oferta_aerolinea_eur+' €':'')+
    row('país recl.',h.pais_reclamacion)+
    (h.transportista_comunitario!=null?('<dt>transp. comunitario</dt><dd>'+(h.transportista_comunitario?'sí':'no')+'</dd>'):'')+
    '</dl>';
}

function excusa(j){
  const c=j.causa_categoria;
  if(!c||c==='desconocida')return '';
  let cls,txt;
  if(j.circunstancia_exime===false){cls='no';txt='NO exime — tienes derecho a la compensación';}
  else if(j.circunstancia_exime===true){cls='si';txt='puede eximir si la aerolínea la acredita';}
  else{cls='prov';txt='provisional — la aerolínea debe acreditarla primero';}
  return '<div class="excusa '+cls+'"><div class="hd">Excusa alegada: <code>'+esc(c)+'</code> → '+txt+'</div>'+
    (j.sentencia?'<div class="cite">'+esc(j.sentencia)+'</div>':'')+
    (j.nota_precedente?'<div class="nota">'+esc(j.nota_precedente)+'</div>':'')+'</div>';
}

function dictamen(j){
  const T={si:'con derecho',prov:'provisional',no:'sin derecho',fuera:'fuera de ámbito',falta:'falta un dato'};
  let h='<div class="verdict"><span class="tag '+j.clase+'">'+T[j.clase]+'</span>';
  if(j.elegible)h+='<span class="amount">'+nf(j.importe_eur)+'<span class="u"> €</span></span><span class="art">'+esc(j.articulo||'')+'</span>';
  else h+='<span class="amount">0<span class="u"> €</span></span>';
  h+='</div>';

  if(j.clase==='falta'){
    h+='<div class="motivo">'+esc(j.motivo)+'</div>';return h;
  }
  if(j.elegible||j.clase==='no'){
    h+='<table class="deriv">';
    if(j.distancia_km)h+=r2('distancia (gran círculo)',nf(j.distancia_km)+' km');
    if(j.intracomunitario!=null)h+=r2('vuelo',j.intracomunitario?'intracomunitario':'no intracomunitario');
    if(j.importe_base_eur)h+=r2('banda del art. 7(1)',nf(j.importe_base_eur)+' €');
    if(j.reduccion_aplica)h+=r2('reducción art. 7(2)','−50 %');
    h+='<tr class="tot"><td>compensación</td><td>'+nf(j.importe_eur)+' €</td></tr>';
    if(j.oferta_eur!=null)h+=r2('oferta de la aerolínea',nf(j.oferta_eur)+' €');
    if(j.deficit_eur!=null)h+='<tr class="gain"><td>reclamas de más</td><td>'+nf(j.deficit_eur)+' €</td></tr>';
    if(j.fecha_vuelo&&j.pais){
      const pl=j.dentro_plazo===false?'fuera de plazo':j.dentro_plazo===null?'sin verificar':'dentro de plazo';
      h+=r2('plazo ('+esc(j.pais)+', desde '+esc(j.fecha_vuelo)+')',pl);
    }
    h+='</table>';
  }
  h+=excusa(j);
  if(j.plazo_incierto)h+='<div class="warn">⚠ Posible prescripción: el plazo para reclamar en ese país no está verificado. Confírmalo con un abogado local.</div>';
  if(j.clase==='prov')h+='<div class="warn">Se reclama igualmente; la aerolínea aún debe acreditar la circunstancia que alega.</div>';
  h+='<div class="motivo">'+esc(j.motivo)+'</div>';
  return h;
}
const r2=(k,v)=>'<tr><td class="k">'+k+'</td><td>'+v+'</td></tr>';

function render(j){
  if(!j.ok){$('#c2').innerHTML='<span style="color:var(--no)">'+esc(j.error)+'</span>';return}
  if(j.estado==='faltan_datos'){
    $('#c2').innerHTML='<span style="color:var(--prov)">El relato no da: <b>'+esc((j.faltan||[]).join(', '))+'</b>. Añádelos y reenvía.</span>';
    return;
  }
  let meta;
  if(j.modo==='relato'){
    meta='modelo: '+(j.modelo_usado||'—');
    if(j.modelo_config&&j.modelo_usado&&j.modelo_usado!==j.modelo_config)meta+=' (reserva; el primario falló)';
    if(j.proveedor)meta+=' · '+j.proveedor;
  }else meta='sin modelo · datos introducidos a mano';
  if(j.latencia_ms!=null)meta+=' · '+j.latencia_ms+' ms';
  $('#c2').innerHTML=facts(j.hechos)+'<div class="metaline">'+esc(meta)+'</div>';
  stage('st3',true);
  $('#c3').innerHTML=dictamen(j);
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
    assert "3 · Dictamen" in page and "@media print" in page and "visibility:hidden" not in page
    assert '"hay_clave"' in page
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
