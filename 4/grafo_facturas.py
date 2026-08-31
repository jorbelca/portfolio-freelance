#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Grafo LangGraph de la Demo 4: ingesta_pdf -> extraccion_llm -> validacion_determinista
-> gate_confianza -> {persistir_ok | cola_revision}. Todo camino escribe extraccion_log.

Dos reglas de diseño que NO son negociables al tocar este fichero (§14.3, y confirmadas con
`advisor` antes de escribir esto):

1. La regla dura se comprueba estructuralmente ANTES del umbral de confianza, no como un `or`
   dentro de él: si `validacion_determinista` encontró errores, la decisión es cola_revision
   pase lo que pase con la confianza. Un modelo que declara 0.99 sobre una aritmética que no
   cuadra no puede vetar la aritmética -- eso reintroduciría el juicio del modelo justo donde
   acaba de demostrarse poco fiable (nota §14.3, "regla dura por encima de cualquier umbral").

2. La confianza que decide el gate es el MÍNIMO de confianza_campos, no la media. Elegido a
   propósito y no por defecto: una media dejaría que un total nítido (0.99) tape un NIF borroso
   (0.40) y aun así pase el umbral. Una factura con un solo campo ilegible es tan inservible
   para contabilidad como una con todos los campos dudosos.
"""
import json
import os
import unicodedata
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional, TypedDict

import psycopg2
import psycopg2.errors
from langgraph.graph import END, START, StateGraph

from validaciones import validar_factura

AQUI = Path(__file__).resolve().parent
CAMPOS_FACTURA = [
    "proveedor_nombre", "proveedor_nif", "cliente_nombre", "cliente_nif",
    "numero_factura", "fecha_emision", "base_imponible", "tipo_iva",
    "cuota_iva", "total", "concepto_resumen",
]
UMBRAL_DEFECTO = float(os.environ.get("FACTURAS_CONFIANZA_UMBRAL", "0.7"))
CAMPOS_NUMERICOS = {"base_imponible", "tipo_iva", "cuota_iva", "total"}


def _normalizar_clave(k: str) -> str:
    """Quita tildes/diacríticos, guiones bajos y pasa a minúscula -- comparación tolerante de
    FORMATO de nombres de campo, nunca de su significado (eso sería adivinar, no normalizar).
    Visto en vivo: 'clienté_nif' (tilde espuria) y 'clientenif' (sin guion bajo) en vez de
    'cliente_nif' -- ambos casos son la misma clave con formato distinto, no una clave
    distinta. 'clientename' en vez de 'cliente_nombre' NO se cubre aquí a propósito: esa es
    otra palabra ('name' vs 'nombre'), no un problema de formato."""
    sin_tildes = "".join(c for c in unicodedata.normalize("NFKD", k) if not unicodedata.combining(c))
    return sin_tildes.lower().replace("_", "").replace(" ", "")


_CAMPOS_NORMALIZADOS = {_normalizar_clave(c): c for c in CAMPOS_FACTURA}


def _sanear_claves(d: dict) -> dict:
    """Remapea cada clave a su forma canónica de CAMPOS_FACTURA si matchea salvo
    tildes/mayúsculas; una clave que no matchea ninguna esperada se deja tal cual (no se
    inventa a qué campo pertenece -- eso sí sería juicio fuera de lugar)."""
    return {_CAMPOS_NORMALIZADOS.get(_normalizar_clave(k), k): v for k, v in d.items()}


def _sanear_numerico(v):
    """Quita un '%' final antes de parsear -- visto en vivo: el modelo devuelve tipo_iva como
    '21%' pese al prompt, de forma sistemática, no como error aislado. Esto es normalización de
    formato (inequívoca, igual que fmt_es con miles/decimales), no adivinar un valor dudoso.
    Si aun así no parsea como Decimal, None -- eso sí se valida como 'ausente'
    (validar_aritmetica) y persiste como NULL, no como texto inválido en una columna NUMERIC."""
    if v is None:
        return None
    candidato = v.strip().rstrip("%").strip() if isinstance(v, str) else v
    try:
        return Decimal(str(candidato))
    except InvalidOperation:
        return None


def _sanear_tipo_iva(v):
    """Visto en vivo (r18): el modelo devuelve tipo_iva como fracción ('0.21') en vez de puntos
    porcentuales enteros ('21'), pese a que el prompt pide el número de puntos. En España el IVA
    nunca es <1 punto en este dominio (4/10/21) -- un valor entre 0 y 1 exclusive es
    inequívocamente la misma cifra en otra representación, no un tipo de IVA real distinto, así
    que se puede reescalar sin adivinar significado. Se aplica DESPUÉS de _sanear_numerico
    (recibe Decimal o None)."""
    if v is None:
        return None
    if 0 < v < 1:
        return v * 100
    return v


class Estado(TypedDict, total=False):
    pdf_path: str
    pdf_origen: str
    texto_pdf: str
    canned_extraccion: Optional[dict]  # inyectado en modo --sin-llm; ver extraccion_llm()
    extraccion: dict           # campos extraídos
    confianza_campos: dict     # {campo: float}
    confianza_minima: float
    errores_validacion: list
    decision: str              # 'persistir_ok' | 'cola_revision'
    motivo: str
    factura_id: Optional[int]
    cola_id: Optional[int]


# --- Nodos --------------------------------------------------------------------------------

def ingesta_pdf(estado: Estado) -> dict:
    import pdfplumber
    with pdfplumber.open(estado["pdf_path"]) as pdf:
        texto = "\n".join(p.extract_text() or "" for p in pdf.pages)
    return {"texto_pdf": texto}


def _llamar_openrouter(prompt: str, modelo: str, api_key: str) -> str:
    from openai import OpenAI
    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)
    # maxTokens con margen para el scratchpad interno del modelo, no solo para el JSON de
    # salida -- lección de Demo 3 (i21): un modelo razonador gasta presupuesto pensando antes
    # de emitir el JSON, y un límite ajustado al tamaño del esquema corta la respuesta a medias.
    resp = client.chat.completions.create(
        model=modelo,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=4096,
        temperature=0,  # extracción, no creatividad -- menos varianza entre corridas
        response_format={"type": "json_object"},
        timeout=60,
    )
    return resp.choices[0].message.content


def _llamar_google(prompt: str, modelo: str, api_key: str) -> str:
    """Llamada directa a la API de Google (Gemini), sin pasar por OpenRouter -- fallback cuando
    OpenRouter bloquea el modelo free por política de datos de la cuenta (visto en vivo con
    google/gemma-4-31b-it:free: 404 'guardrail restrictions'). Mismo modelo, servido directo.

    Gemma 4 razona por defecto: la respuesta trae varias 'parts', las de scratchpad marcadas
    'thought': true y la respuesta final en la ÚLTIMA parte sin esa marca -- coger parts[0] a
    ciegas devuelve el razonamiento, no el JSON (visto en vivo). Se descartan las de thought."""
    import requests
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
    resp = requests.post(
        url, params={"key": api_key}, timeout=90,
        json={"contents": [{"parts": [{"text": prompt}]}],
              "generationConfig": {"responseMimeType": "application/json", "temperature": 0}})
    resp.raise_for_status()
    parts = resp.json()["candidates"][0]["content"]["parts"]
    finales = [p["text"] for p in parts if not p.get("thought")]
    return finales[-1] if finales else parts[-1]["text"]


def extraccion_llm(estado: Estado) -> dict:
    """Si estado trae canned_extraccion (modo --sin-llm, ver procesar_facturas.py --sin-llm),
    se usa tal cual sin llamar a ninguna API. En caso contrario prueba OpenRouter primero
    (dots-3-note-preview, multimodal, servido por AtlasCloud) y, si falla, cae a Google/Gemma
    directo -- ambos multimodales a propósito (necesario para f10 más adelante), ninguno de
    los dos depende de un pool compartido como sí le pasaba a Gemma servido vía OpenRouter."""
    if estado.get("canned_extraccion") is not None:
        c = estado["canned_extraccion"]
        return {"extraccion": c["extraccion"], "confianza_campos": c["confianza_campos"]}

    api_key_or = os.environ.get("OPENROUTER_API_KEY")
    api_key_google = os.environ.get("GEMINI_API_KEY")
    if not api_key_or and not api_key_google:
        raise RuntimeError(
            "Falta OPENROUTER_API_KEY y GEMINI_API_KEY. Añade al menos una a 1/.env (mismo "
            "fichero que usan las otras demos) o exporta la variable antes de ejecutar. Para "
            "probar el resto del grafo sin clave, usa procesar_facturas.py --sin-llm.")

    esquema = {campo: "string o null" for campo in CAMPOS_FACTURA}
    prompt = (
        "Extrae los datos de esta factura española. Los importes pueden venir en formato "
        "español (punto de millar, coma decimal, p.ej. '1.234,56 EUR'): normalízalos a "
        "número con punto decimal en la salida (p.ej. 1234.56).\n\n"
        f"Devuelve SOLO un JSON con dos claves: 'campos' (objeto con exactamente estas "
        f"claves: {list(esquema.keys())}) y 'confianza' (objeto con la MISMA lista de claves, "
        "cada una con tu confianza 0.0-1.0 en ese campo concreto -- no una confianza global).\n\n"
        f"TEXTO DE LA FACTURA:\n{estado['texto_pdf']}"
    )

    contenido = None
    error_previo = None
    # OpenRouter primero de nuevo, pero con dots-studio/dots-3-note-preview:free en vez de
    # nemotron: es multimodal (text+image, cubre f10 más adelante) y lo sirve AtlasCloud
    # (proveedor dedicado), no el pool de Google compartido entre todos los usuarios de
    # OpenRouter que rompía el routing de Gemma. Google/Gemma directo queda de fallback.
    if api_key_or:
        try:
            modelo_or = os.environ.get("FACTURAS_MODELO", "dots-studio/dots-3-note-preview:free")
            contenido = _llamar_openrouter(prompt, modelo_or, api_key_or)
        except Exception as e:
            error_previo = f"openrouter: {e}"

    if contenido is None and api_key_google:
        try:
            modelo_google = os.environ.get("FACTURAS_MODELO_GOOGLE", "gemma-4-31b-it")
            contenido = _llamar_google(prompt, modelo_google, api_key_google)
        except Exception as e:
            error_previo = f"{error_previo}; google: {e}" if error_previo else f"google: {e}"

    try:
        if contenido is None:
            raise RuntimeError(error_previo or "sin proveedor disponible")
        datos = json.loads(contenido)
        campos = _sanear_claves(datos["campos"])
        # Cadena vacía normalizada a None: mismo significado que un campo ausente, para que
        # validación y el INSERT (columnas DATE/NUMERIC) usen una sola representación de "no
        # extraído" -- '' pasada tal cual a una columna DATE rompe el INSERT (visto en vivo con
        # el escaneo ruidoso, f10, texto vacío -> el modelo devuelve fecha_emision="").
        campos = {k: (None if isinstance(v, str) and not v.strip() else v) for k, v in campos.items()}
        campos = {k: (_sanear_numerico(v) if k in CAMPOS_NUMERICOS else v) for k, v in campos.items()}
        if "tipo_iva" in campos:
            campos["tipo_iva"] = _sanear_tipo_iva(campos["tipo_iva"])
        confianza = _sanear_claves({k: float(v) for k, v in datos["confianza"].items()})
    except (json.JSONDecodeError, KeyError, TypeError, ValueError, IndexError, AttributeError,
            RuntimeError) as e:
        # Fallo de extracción NO puede hacer desaparecer el caso (lección i21 de Demo 3):
        # se propaga como confianza 0 en todos los campos, y gate_confianza lo manda a cola.
        return {
            "extraccion": {c: None for c in CAMPOS_FACTURA},
            "confianza_campos": {c: 0.0 for c in CAMPOS_FACTURA},
            "_error_extraccion": str(e),
        }
    return {"extraccion": campos, "confianza_campos": confianza}


def validacion_determinista(estado: Estado) -> dict:
    return {"errores_validacion": validar_factura(estado["extraccion"])}


def gate_confianza(estado: Estado) -> dict:
    if estado.get("_error_extraccion"):
        return {"decision": "cola_revision", "motivo": f"extracción fallida: {estado['_error_extraccion']}",
                "confianza_minima": 0.0}

    # Regla 1 (no negociable, ver docstring del módulo): errores deterministas ganan siempre,
    # sin mirar la confianza declarada por el modelo.
    if estado["errores_validacion"]:
        return {"decision": "cola_revision", "motivo": "; ".join(estado["errores_validacion"]),
                "confianza_minima": min(estado["confianza_campos"].values() or [0.0])}

    confianza_minima = min(estado["confianza_campos"].values() or [0.0])  # Regla 2: mínimo, no media
    if confianza_minima < UMBRAL_DEFECTO:
        campo_dudoso = min(estado["confianza_campos"], key=estado["confianza_campos"].get)
        return {"decision": "cola_revision",
                "motivo": f"confianza baja en '{campo_dudoso}' ({confianza_minima:.2f} < {UMBRAL_DEFECTO})",
                "confianza_minima": confianza_minima}

    return {"decision": "persistir_ok", "motivo": None, "confianza_minima": confianza_minima}


def _dsn():
    return (f"host={os.environ.get('PGHOST', '127.0.0.1')} port={os.environ.get('PGPORT', '5432')} "
            f"dbname={os.environ.get('PGDATABASE', 'n8n')} user={os.environ.get('PGUSER', 'n8n_user')} "
            f"password={os.environ.get('PGPASSWORD', '')}")


def persistir_ok(estado: Estado) -> dict:
    """Intenta el INSERT en facturas. El UNIQUE(proveedor_nif, numero_factura) es la única
    fuente de verdad de deduplicación (no hay pre-check en Python, ver init-facturas-tables.sql):
    si salta, se reconduce a cola_revision con motivo='duplicado' en vez de propagar el error."""
    e, cc = estado["extraccion"], estado["confianza_campos"]
    conn = psycopg2.connect(_dsn())
    try:
        cur = conn.cursor()
        try:
            cur.execute(
                """INSERT INTO facturas (proveedor_nombre, proveedor_nif, cliente_nombre, cliente_nif,
                   numero_factura, fecha_emision, base_imponible, tipo_iva, cuota_iva, total,
                   concepto_resumen, confianza_campos, confianza_minima)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                (e.get("proveedor_nombre"), e.get("proveedor_nif"), e.get("cliente_nombre"), e.get("cliente_nif"),
                 e.get("numero_factura"), e.get("fecha_emision"), e.get("base_imponible"), e.get("tipo_iva"),
                 e.get("cuota_iva"), e.get("total"), e.get("concepto_resumen"), json.dumps(cc),
                 estado["confianza_minima"]))
            factura_id = cur.fetchone()[0]
            _log(cur, estado["pdf_origen"], "persistido", None, cc, estado["confianza_minima"],
                 factura_id=factura_id)
            conn.commit()
            return {"decision": "persistir_ok", "factura_id": factura_id}
        except psycopg2.errors.UniqueViolation:
            conn.rollback()
            cur = conn.cursor()
            cola_id = _insertar_cola(cur, e, cc, estado["confianza_minima"], "duplicado")
            _log(cur, estado["pdf_origen"], "cola_revision", "duplicado", cc,
                 estado["confianza_minima"], cola_id=cola_id)
            conn.commit()
            return {"decision": "cola_revision", "motivo": "duplicado", "cola_id": cola_id}
    finally:
        conn.close()


def _insertar_cola(cur, e, cc, confianza_minima, motivo) -> int:
    cur.execute(
        """INSERT INTO cola_revision (proveedor_nombre, proveedor_nif, cliente_nombre, cliente_nif,
           numero_factura, fecha_emision, base_imponible, tipo_iva, cuota_iva, total,
           concepto_resumen, confianza_campos, confianza_minima, motivo)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (e.get("proveedor_nombre"), e.get("proveedor_nif"), e.get("cliente_nombre"), e.get("cliente_nif"),
         e.get("numero_factura"), e.get("fecha_emision"), e.get("base_imponible"), e.get("tipo_iva"),
         e.get("cuota_iva"), e.get("total"), e.get("concepto_resumen"), json.dumps(cc),
         confianza_minima, motivo))
    return cur.fetchone()[0]


def _log(cur, pdf_origen, resultado, motivo, cc, confianza_minima, factura_id=None, cola_id=None):
    cur.execute(
        """INSERT INTO extraccion_log (pdf_origen, resultado, motivo, confianza_campos,
           confianza_minima, factura_id, cola_id) VALUES (%s,%s,%s,%s,%s,%s,%s)""",
        (pdf_origen, resultado, motivo, json.dumps(cc), confianza_minima, factura_id, cola_id))


def cola_revision_nodo(estado: Estado) -> dict:
    e, cc = estado["extraccion"], estado.get("confianza_campos", {})
    conn = psycopg2.connect(_dsn())
    try:
        cur = conn.cursor()
        cola_id = _insertar_cola(cur, e, cc, estado["confianza_minima"], estado["motivo"])
        _log(cur, estado["pdf_origen"], "cola_revision", estado["motivo"], cc,
             estado["confianza_minima"], cola_id=cola_id)
        conn.commit()
        return {"cola_id": cola_id}
    finally:
        conn.close()


def _rama_gate(estado: Estado) -> str:
    return estado["decision"]


def construir_grafo():
    g = StateGraph(Estado)
    g.add_node("ingesta_pdf", ingesta_pdf)
    g.add_node("extraccion_llm", extraccion_llm)
    g.add_node("validacion_determinista", validacion_determinista)
    g.add_node("gate_confianza", gate_confianza)
    g.add_node("persistir_ok", persistir_ok)
    g.add_node("cola_revision", cola_revision_nodo)

    g.add_edge(START, "ingesta_pdf")
    g.add_edge("ingesta_pdf", "extraccion_llm")
    g.add_edge("extraccion_llm", "validacion_determinista")
    g.add_edge("validacion_determinista", "gate_confianza")
    g.add_conditional_edges("gate_confianza", _rama_gate,
                             {"persistir_ok": "persistir_ok", "cola_revision": "cola_revision"})
    g.add_edge("persistir_ok", END)
    g.add_edge("cola_revision", END)
    return g.compile()
