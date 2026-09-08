"""El único punto donde el modelo juzga: convertir el relato libre del pasajero en
hechos estructurados y una categoría de causa cerrada.

Todo lo demás (distancia, banda, elegibilidad, importe, exención) es determinista y
vive en reglas.py / precedentes.py. El modelo NO ve importes ni artículos.

`SALTAR_INTERPRETACION=1` no aplica aquí: el modo --sin-llm de eval/run_eval.py ya
inyecta los hechos del dataset y no llama a este módulo.
"""

from __future__ import annotations

import json
import re

from aeropuertos import AEROPUERTOS
from llm import llamar
from precedentes import PRECEDENTES

# Nombres de ciudad -> IATA, solo para rescatar cuando el modelo devuelve ciudad en vez de código.
_CIUDAD_IATA = {
    "madrid": "MAD", "barcelona": "BCN", "malaga": "AGP", "málaga": "AGP", "valencia": "VLC",
    "sevilla": "SVQ", "palma": "PMI", "alicante": "ALC", "ibiza": "IBZ",
    "gran canaria": "LPA", "las palmas": "LPA", "tenerife": "TFN",
    "paris": "CDG", "parís": "CDG", "niza": "NCE", "fráncfort": "FRA", "francfort": "FRA",
    "frankfurt": "FRA", "munich": "MUC", "múnich": "MUC", "berlin": "BER", "berlín": "BER",
    "amsterdam": "AMS", "ámsterdam": "AMS", "bruselas": "BRU", "lisboa": "LIS", "oporto": "OPO",
    "roma": "FCO", "milan": "MXP", "milán": "MXP", "atenas": "ATH", "viena": "VIE",
    "copenhague": "CPH", "estocolmo": "ARN", "helsinki": "HEL", "dublin": "DUB", "dublín": "DUB",
    "varsovia": "WAW", "praga": "PRG", "oslo": "OSL", "reikiavik": "KEF", "zurich": "ZRH",
    "zúrich": "ZRH", "ginebra": "GVA", "londres": "LHR", "manchester": "MAN", "edimburgo": "EDI",
    "nueva york": "JFK", "new york": "JFK", "newark": "EWR", "miami": "MIA", "los angeles": "LAX",
    "los ángeles": "LAX", "chicago": "ORD", "toronto": "YYZ", "sao paulo": "GRU",
    "são paulo": "GRU", "buenos aires": "EZE", "mexico": "MEX", "méxico": "MEX", "dubai": "DXB",
    "dubái": "DXB", "doha": "DOH", "bangkok": "BKK", "hong kong": "HKG", "tokio": "NRT",
    "pekin": "PEK", "pekín": "PEK", "singapur": "SIN", "johannesburgo": "JNB", "casablanca": "CMN",
    "cancun": "CUN", "cancún": "CUN", "punta cana": "PUJ", "delhi": "DEL", "estambul": "IST",
}

_CATS = "\n".join(f"  - {c}: {PRECEDENTES[c][2][:90]}" for c in PRECEDENTES)

_PROMPT = """Eres un asistente que extrae datos de la queja de un pasajero por un retraso de vuelo.
Devuelve SOLO un objeto JSON con estos campos (usa null si el relato no lo dice):

- origen: código IATA de 3 letras del aeropuerto de salida (p. ej. "MAD")
- destino: código IATA de 3 letras del aeropuerto de llegada
  (si el relato nombra la ciudad pero no el aeropuerto, usa el hub internacional
  principal: Nueva York->JFK, Londres->LHR, París->CDG, Milán->MXP, Tokio->NRT.
  NO dejes origen ni destino en null si el relato nombra la ciudad.)
- retraso_llegada_h: horas de retraso a la llegada al destino final, número decimal
- fecha_vuelo: "YYYY-MM-DD" o null
- pais_reclamacion: ISO-2 del país donde reclama el pasajero, o null
- hubo_reruteo: true SOLO si le pusieron en OTRO vuelo o medio de transporte distinto;
  false si fue el mismo vuelo saliendo más tarde
- oferta_aerolinea_eur: cuantía en euros que ofreció la aerolínea (bono o efectivo), o null
- transportista_comunitario: true si la compañía operadora es de la UE/EEE, false si no,
  null si no se sabe (solo importa en vuelos que ENTRAN a la UE desde fuera)
- causa_categoria: EXACTAMENTE una de esta lista cerrada; usa "desconocida" si el relato
  no permite decidir o menciona dos causas incompatibles:
{cats}
- causa_texto: cita textual breve del relato sobre el motivo del retraso
- confianza: 0..1, tu seguridad en la categoría de causa
- faltan: lista de campos importantes que el relato no aporta y habría que preguntar

Relato del pasajero:
\"\"\"{relato}\"\"\"
"""


def _iata(valor) -> str | None:
    if not valor or not isinstance(valor, str):
        return None
    v = valor.strip().upper()
    if v in AEROPUERTOS:
        return v
    return _CIUDAD_IATA.get(valor.strip().lower())


def _num(valor):
    if isinstance(valor, (int, float)):
        return float(valor)
    if isinstance(valor, str):
        m = re.search(r"-?\d+(?:[.,]\d+)?", valor)
        if m:
            return float(m.group().replace(",", "."))
    return None


def _parsear(crudo: str) -> dict:
    try:
        return json.loads(crudo)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", crudo, re.S)
        if not m:
            raise
        return json.loads(m.group())


def interpretar_relato(relato: str) -> dict:
    """Llama al modelo y normaliza su salida. Devuelve un dict con los campos de
    Hechos + `causa_texto`, `confianza`, `faltan`, `crudo` (la respuesta sin tocar).

    Reintenta si la respuesta no parsea como JSON: los modelos free devuelven texto
    degradado de forma intermitente bajo carga (README §3 G-EVAL-REAL)."""
    import os
    prompt = _PROMPT.format(cats=_CATS, relato=relato.strip())
    intentos = int(os.environ.get("RECLAMACIONES_INTERPRETAR_REINTENTOS", "3"))
    crudo = ""
    for i in range(intentos):
        crudo = llamar(prompt)
        try:
            d = _parsear(crudo)
            break
        except json.JSONDecodeError:
            if i == intentos - 1:
                d = {}

    cat = str(d.get("causa_categoria", "desconocida")).strip().lower()
    if cat not in PRECEDENTES:
        cat = "desconocida"

    origen, destino = _iata(d.get("origen")), _iata(d.get("destino"))
    faltan = list(d.get("faltan") or [])
    for campo, val in (("origen", origen), ("destino", destino)):
        if val is None and campo not in faltan:
            faltan.append(campo)

    tc = d.get("transportista_comunitario")
    return {
        "origen": origen,
        "destino": destino,
        "retraso_llegada_h": _num(d.get("retraso_llegada_h")),
        "fecha_vuelo": d.get("fecha_vuelo") or None,
        "pais_reclamacion": (str(d["pais_reclamacion"]).upper()
                             if d.get("pais_reclamacion") else None),
        "hubo_reruteo": bool(d.get("hubo_reruteo")),
        "oferta_aerolinea_eur": _num(d.get("oferta_aerolinea_eur")),
        "transportista_comunitario": tc if isinstance(tc, bool) else None,
        "causa_categoria": cat,
        "causa_texto": d.get("causa_texto") or "",
        "confianza": _num(d.get("confianza")) or 0.0,
        "faltan": faltan,
        "crudo": crudo,
    }
