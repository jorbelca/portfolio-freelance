#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Grafo LangGraph de la Demo 5: ingesta_lead -> investigacion_agente -> cualificacion_llm
-> aplicar_rubrica -> validacion_determinista -> gate_confianza -> {persistir_ok | cola_revision}.
Todo camino escribe cualificacion_log.

Reparto de responsabilidad, no negociable al tocar este fichero (mismo criterio que
4/grafo_facturas.py, confirmado con advisor):

1. Las reglas R1-R12 de la rúbrica NO las decide el modelo. `cualificacion_llm` devuelve solo
   juicio: qué señales encontró y con qué evidencia (`ref` a un fragmento recuperado), si el
   encaje de producto es fuerte o débil, si el contacto decide, y una etiqueta rival si la ve.
   La etiqueta la deriva `aplicar_rubrica` en Python -- descalificadores R1-R7 sobre la ficha,
   gates de encaje R8-R9, conteo de señales R10-R12 -- de forma que `regla` es reproducible:
   el comprador re-deriva la etiqueta desde `senales` + `ficha` guardadas, sin fiarse del
   modelo. El esquema de salida del modelo NO tiene campo `etiqueta` a propósito.

2. Regla dura (de la Demo 4): si `validacion_determinista` encontró errores, la decisión es
   cola_revision pase lo que pase con la confianza. La confianza declarada por el modelo no
   puede vetar una validación determinista (lección Demo 3: el modelo satura su confianza
   arriba, los errores incluidos).

3. Orden del gate: errores deterministas -> R14 sin evidencia -> R13 recorte por rival ->
   R15 umbral de confianza. R15 el último y el más débil, la propia rúbrica lo dice.

La rúbrica vive en rubrica-cualificacion-leads.md (versionada, se ve en el diff), no en el
string del prompt: se carga y se inyecta como contexto.
"""
import json
import os
from pathlib import Path
from typing import Optional, TypedDict

import psycopg2
import psycopg2.errors
from langgraph.graph import END, START, StateGraph

from validaciones import normalizar_empresa, validar_lead

AQUI = Path(__file__).resolve().parent
UMBRAL_DEFECTO = float(os.environ.get("LEADS_CONFIANZA_UMBRAL", "0.7"))
ORDEN_ETIQUETA = {"frio": 0, "tibio": 1, "caliente": 2}

# Listas del criterio comercial (ver §5 de la rúbrica: son del cliente y cambian; aquí van
# como constantes del módulo, no como config, porque no hay un valor "por entorno").
SECTORES_EXCLUIDOS = ("defensa", "armamento", "gambling", "juego", "casino", "adulto", "adult")
COMPETIDORES = ("datadog", "grafana labs", "new relic", "observe inc")


def _cargar_rubrica() -> str:
    return (AQUI / "rubrica-cualificacion-leads.md").read_text(encoding="utf-8")


class Estado(TypedDict, total=False):
    lead_ref: str
    empresa: str
    contacto_nombre: Optional[str]
    contacto_email: str
    contacto_cargo: Optional[str]
    canal_origen: Optional[str]
    empresa_normalizada: str
    # Inyectados en modo SALTAR_INVESTIGACION / --sin-llm (ver procesar_leads.py).
    canned_ficha: Optional[dict]
    canned_senales: Optional[list]
    canned_hallazgos: Optional[dict]
    # Producidos por los nodos.
    ficha: dict
    senales_crudas: list          # [{"snippet": ..., "url": ..., "recuperado_en": ...}]
    hallazgos: dict               # juicio del modelo, SIN etiqueta
    _error_cualificacion: Optional[str]
    etiqueta: Optional[str]
    regla: Optional[str]
    motivo: Optional[str]
    etiqueta_rival: Optional[str]
    confianza: float
    errores_validacion: list
    decision: str                 # 'persistir_ok' | 'cola_revision'
    resultado_log: str            # 'cualificado' | 'cola_revision' | 'sin_cualificar'
    lead_id: Optional[int]
    cola_id: Optional[int]


# --- Nodos --------------------------------------------------------------------------------

def ingesta_lead(estado: Estado) -> dict:
    return {"empresa_normalizada": normalizar_empresa(estado.get("empresa", ""))}


def investigacion_agente(estado: Estado) -> dict:
    """El bucle ReAct real (tools ficha_empresa + buscar_señales, criterio de parada) llega el
    miércoles. Hoy: si el estado trae ficha/señales inyectadas se usan tal cual. La forma que
    se produce aquí -- `ficha` dict, `senales_crudas` lista de {snippet,url,recuperado_en} --
    es la que tendrá que devolver el bucle real, para que sea un swap y no una reescritura."""
    if estado.get("canned_ficha") is not None:
        return {"ficha": estado["canned_ficha"],
                "senales_crudas": estado.get("canned_senales") or []}
    raise NotImplementedError(
        "investigacion_agente real pendiente (W36 miércoles). Para probar el resto del grafo, "
        "ejecuta procesar_leads.py con SALTAR_INVESTIGACION=1 -- inyecta ficha y señales del "
        "dataset, mismo patrón que --sin-llm en la Demo 4.")


def _llamar_openrouter(prompt: str, modelo: str, api_key: str) -> str:
    from openai import OpenAI
    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)
    resp = client.chat.completions.create(
        model=modelo,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=4096,          # margen para el scratchpad del modelo, no solo el JSON (lección Demo 3 i21)
        temperature=0,
        response_format={"type": "json_object"},
        timeout=60,
    )
    return resp.choices[0].message.content


def cualificacion_llm(estado: Estado) -> dict:
    """Devuelve `hallazgos` (juicio SIN etiqueta), `confianza` y `etiqueta_rival`. En
    --sin-llm usa canned_hallazgos y no llama a ninguna API. Un fallo de parseo NO hace
    desaparecer el lead: se propaga como _error_cualificacion y el gate lo manda a
    sin_cualificar (lección Demo 3 i21 / bug 5 de la Demo 4)."""
    if estado.get("canned_hallazgos") is not None:
        h = estado["canned_hallazgos"]
        return {"hallazgos": h, "confianza": float(h.get("confianza", 0.9)),
                "etiqueta_rival": h.get("etiqueta_rival")}

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Falta OPENROUTER_API_KEY (añádela a ../1/.env). Para probar el grafo sin clave, "
            "usa procesar_leads.py --sin-llm.")

    ficha = estado.get("ficha") or {}
    crudas = estado.get("senales_crudas") or []
    evidencia = "\n".join(f"[{i}] {s.get('snippet', '')} ({s.get('url', 's/url')})"
                          for i, s in enumerate(crudas)) or "(sin resultados)"
    prompt = (
        "Eres el nodo de cualificación de un pipeline de leads para Nubeforge. Aplica la "
        "rúbrica de abajo, pero devuelve SOLO tu juicio -- la etiqueta la deriva otro paso "
        "determinista a partir de lo que devuelvas.\n\n"
        f"=== RÚBRICA ===\n{_cargar_rubrica()}\n\n"
        f"=== FICHA DE EMPRESA (de ficha_empresa) ===\n{json.dumps(ficha, ensure_ascii=False, indent=2)}\n\n"
        f"=== EVIDENCIA WEB (de buscar_señales, numerada) ===\n{evidencia}\n\n"
        "Devuelve SOLO un JSON con estas claves:\n"
        '  "senales": lista de {"tipo": "S1"|"S2"|"S3"|"S4", "valor": "<qué dice>", "ref": <índice del fragmento de evidencia que la respalda>}\n'
        '  "encaje_producto": "fuerte" | "debil"\n'
        '  "contacto_decisor": true | false\n'
        '  "etiqueta_rival": null | "caliente" | "tibio" | "frio"  (segunda lectura defendible con la misma evidencia, o null)\n'
        '  "confianza": 0.0-1.0\n'
        "Cada señal DEBE tener un `ref` a un fragmento real de la evidencia. No inventes señales."
    )

    try:
        contenido = _llamar_openrouter(
            prompt, os.environ.get("LEADS_MODELO", "dots-studio/dots-3-note-preview:free"), api_key)
        datos = json.loads(contenido)
        h = {
            "senales": list(datos.get("senales") or []),
            "encaje_producto": datos.get("encaje_producto"),
            "contacto_decisor": bool(datos.get("contacto_decisor", True)),
        }
        rival = datos.get("etiqueta_rival")
        return {"hallazgos": h, "confianza": float(datos.get("confianza", 0.0)),
                "etiqueta_rival": rival if rival in ORDEN_ETIQUETA else None}
    except (json.JSONDecodeError, KeyError, TypeError, ValueError, AttributeError, RuntimeError) as e:
        return {"_error_cualificacion": str(e), "hallazgos": {}, "confianza": 0.0}


def _descalificar(ficha: dict, hallazgos: dict):
    """R1-R7. Predicados deterministas sobre la ficha (R6 cruza ficha + hallazgos). Devuelve
    (regla, motivo) del primero que aplica, o None."""
    pais = (ficha.get("pais") or "").strip().upper()
    if pais and pais not in ("UK", "GB", "REINO UNIDO", "UNITED KINGDOM", "ENGLAND", "SCOTLAND", "WALES"):
        return "R1", "fuera de territorio"
    estado_reg = (ficha.get("estado") or "").lower()
    if any(k in estado_reg for k in ("disuelta", "liquidaci", "dormant", "dissolved", "insolven")):
        return "R2", "sociedad inactiva"
    if (ficha.get("tipo_negocio") or "").lower() == "servicios":
        return "R3", "no es empresa de producto"
    sector = (ficha.get("sector") or "").lower()
    if any(x in sector for x in SECTORES_EXCLUIDOS):
        return "R4", "sector excluido"
    tam = ficha.get("tamano_estimado")
    if (isinstance(tam, int) and tam > 250) or ficha.get("filial_cotizada"):
        return "R5", "cuenta enterprise — fuera del motion self-serve"
    tiene_s1 = any(s.get("tipo") == "S1" for s in (hallazgos or {}).get("senales") or [])
    if isinstance(tam, int) and tam < 8 and not tiene_s1:
        return "R6", "demasiado pronto, sin presupuesto"
    nombre = (ficha.get("nombre") or ficha.get("empresa") or "").lower()
    # ponytail: match por subcadena. Falso positivo posible (token de competidor en otro
    # nombre); upgrade a match sobre dominio/registro si el cliente aporta lista real.
    if any(c in nombre for c in COMPETIDORES):
        return "R7", "competidor"
    return None


def aplicar_rubrica(estado: Estado) -> dict:
    """Deriva etiqueta + regla + motivo en Python. Reproducible: misma ficha + mismos hallazgos
    -> misma etiqueta. Si la cualificación falló, no hay nada que derivar (gate -> sin_cualificar)."""
    # Sin ficha no hay base para R1-R12 (gate lo manda a sin_cualificar por R14); sin
    # cualificación tampoco. En ambos casos no se deriva etiqueta ni regla -- que quedaría
    # obsoleta en el log.
    if estado.get("_error_cualificacion") or not estado.get("ficha"):
        return {}
    ficha = estado["ficha"]
    h = estado.get("hallazgos") or {}

    desc = _descalificar(ficha, h)
    if desc:
        return {"etiqueta": "frio", "regla": desc[0], "motivo": desc[1]}

    senales = h.get("senales") or []
    if h.get("encaje_producto") == "debil":
        return {"etiqueta": "tibio", "regla": "R8", "motivo": "encaje de producto débil"}
    tiene_s1 = any(s.get("tipo") == "S1" for s in senales)
    if not h.get("contacto_decisor", True) and not tiene_s1:
        return {"etiqueta": "tibio", "regla": "R9", "motivo": "contacto sin poder de decisión"}

    n = len(senales)
    if n >= 2:
        tipos = ", ".join(s.get("tipo", "?") for s in senales)
        return {"etiqueta": "caliente", "regla": "R10", "motivo": f"encaje ICP + {n} señales: {tipos}"}
    if n == 1:
        return {"etiqueta": "tibio", "regla": "R11",
                "motivo": f"una sola señal ({senales[0].get('tipo', '?')}) — no basta para caliente"}
    return {"etiqueta": "tibio", "regla": "R12", "motivo": "encaja perfil, sin disparador de timing"}


def validacion_determinista(estado: Estado) -> dict:
    if estado.get("_error_cualificacion"):
        return {"errores_validacion": []}
    return {"errores_validacion": validar_lead(
        {"empresa": estado.get("empresa"), "contacto_email": estado.get("contacto_email")},
        estado.get("hallazgos") or {}, estado.get("senales_crudas") or [])}


def gate_confianza(estado: Estado) -> dict:
    if estado.get("_error_cualificacion"):
        return {"decision": "cola_revision", "resultado_log": "sin_cualificar", "etiqueta": None,
                "motivo": f"cualificación fallida: {estado['_error_cualificacion']}"}

    # Regla dura: errores deterministas ganan siempre, sin mirar la confianza.
    if estado.get("errores_validacion"):
        return {"decision": "cola_revision", "resultado_log": "cola_revision",
                "etiqueta": estado.get("etiqueta"), "motivo": "; ".join(estado["errores_validacion"])}

    # R14: sin evidencia para cualificar. Ausencia de datos no es señal negativa -> no se fuerza frio.
    if not estado.get("ficha"):
        return {"decision": "cola_revision", "resultado_log": "sin_cualificar", "etiqueta": None,
                "motivo": "sin evidencia para cualificar"}

    etiqueta = estado.get("etiqueta")
    rival = estado.get("etiqueta_rival")
    # R13: el modelo nombra una etiqueta rival defendible -> se toma la más baja y va a cola.
    if rival in ORDEN_ETIQUETA and rival != etiqueta:
        baja = min((etiqueta, rival), key=lambda x: ORDEN_ETIQUETA[x])
        return {"decision": "cola_revision", "resultado_log": "cola_revision", "etiqueta": baja,
                "motivo": f"frontera {estado.get('regla')}: {etiqueta} vs {rival} (rival declarada) — se toma {baja}"}

    # R15: umbral de confianza. El último y el más débil.
    if estado.get("confianza", 0.0) < UMBRAL_DEFECTO:
        return {"decision": "cola_revision", "resultado_log": "cola_revision", "etiqueta": etiqueta,
                "motivo": f"confianza baja ({estado.get('confianza', 0.0):.2f} < {UMBRAL_DEFECTO})"}

    return {"decision": "persistir_ok", "resultado_log": "cualificado", "etiqueta": etiqueta,
            "motivo": estado.get("motivo")}


# --- Persistencia ------------------------------------------------------------------------

def _dsn():
    return (f"host={os.environ.get('PGHOST', '127.0.0.1')} port={os.environ.get('PGPORT', '5432')} "
            f"dbname={os.environ.get('PGDATABASE', 'n8n')} user={os.environ.get('PGUSER', 'n8n_user')} "
            f"password={os.environ.get('PGPASSWORD', '')}")


def _senales_con_evidencia(estado: Estado) -> list:
    """Resuelve cada `ref` a su fragmento recuperado. Lo que se guarda en leads.senales /
    cola_revision.senales -- un motivo cuya señal cita evidencia que ya no está es
    inauditable, así que la evidencia se materializa junto a la señal."""
    crudas = estado.get("senales_crudas") or []
    out = []
    for s in (estado.get("hallazgos") or {}).get("senales") or []:
        ref = s.get("ref")
        ev = crudas[ref] if isinstance(ref, int) and 0 <= ref < len(crudas) else {}
        out.append({"tipo": s.get("tipo"), "valor": s.get("valor"), "fuente": "buscar_senales",
                    "snippet": ev.get("snippet"), "url": ev.get("url"),
                    "recuperado_en": ev.get("recuperado_en")})
    return out


_CAMPOS_FICHA = ("pais", "sector", "tipo_negocio", "tamano_estimado", "antiguedad_anios")


def _fila_comun(estado: Estado) -> tuple:
    f = estado.get("ficha") or {}
    return (estado.get("empresa"), estado.get("empresa_normalizada"), estado.get("contacto_nombre"),
            estado.get("contacto_email"), estado.get("contacto_cargo"), estado.get("canal_origen"),
            f.get("pais"), f.get("sector"), f.get("tipo_negocio"), f.get("tamano_estimado"),
            f.get("antiguedad_anios"))


def _insertar_cola(cur, estado: Estado, motivo: str) -> int:
    cur.execute(
        """INSERT INTO cola_revision (empresa, empresa_normalizada, contacto_nombre, contacto_email,
           contacto_cargo, canal_origen, pais, sector, tipo_negocio, tamano_estimado,
           antiguedad_anios, etiqueta, senales, confianza, motivo, tipo)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'cualificacion') RETURNING id""",
        (*_fila_comun(estado), estado.get("etiqueta"), json.dumps(_senales_con_evidencia(estado)),
         estado.get("confianza"), motivo))
    return cur.fetchone()[0]


def _log(cur, estado: Estado, resultado: str, motivo, lead_id=None, cola_id=None):
    cur.execute(
        """INSERT INTO cualificacion_log (lead_ref, resultado, etiqueta, motivo, regla, senales,
           confianza, lead_id, cola_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (estado.get("lead_ref"), resultado, estado.get("etiqueta"), motivo, estado.get("regla"),
         json.dumps(_senales_con_evidencia(estado)), estado.get("confianza"), lead_id, cola_id))


def persistir_ok(estado: Estado) -> dict:
    """INSERT en leads. El UNIQUE(contacto_email) y UNIQUE(empresa_normalizada) son la única
    fuente de verdad de deduplicación (sin pre-check en Python): si salta cualquiera de los
    dos, se reconduce a cola con motivo='duplicado' para que el comercial ya asignado decida."""
    conn = psycopg2.connect(_dsn())
    try:
        cur = conn.cursor()
        try:
            cur.execute(
                """INSERT INTO leads (empresa, empresa_normalizada, contacto_nombre, contacto_email,
                   contacto_cargo, canal_origen, pais, sector, tipo_negocio, tamano_estimado,
                   antiguedad_anios, etiqueta, motivo, regla, senales, confianza)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                (*_fila_comun(estado), estado.get("etiqueta"), estado.get("motivo"), estado.get("regla"),
                 json.dumps(_senales_con_evidencia(estado)), estado.get("confianza")))
            lead_id = cur.fetchone()[0]
            _log(cur, estado, "cualificado", estado.get("motivo"), lead_id=lead_id)
            conn.commit()
            return {"decision": "persistir_ok", "lead_id": lead_id}
        except psycopg2.errors.UniqueViolation:
            conn.rollback()
            cur = conn.cursor()
            cola_id = _insertar_cola(cur, estado, "duplicado (email o empresa ya en leads)")
            _log(cur, estado, "cola_revision", "duplicado (email o empresa ya en leads)", cola_id=cola_id)
            conn.commit()
            return {"decision": "cola_revision", "resultado_log": "cola_revision",
                    "motivo": "duplicado (email o empresa ya en leads)", "cola_id": cola_id}
    finally:
        conn.close()


def cola_revision_nodo(estado: Estado) -> dict:
    conn = psycopg2.connect(_dsn())
    try:
        cur = conn.cursor()
        cola_id = _insertar_cola(cur, estado, estado.get("motivo") or "(sin motivo)")
        _log(cur, estado, estado.get("resultado_log", "cola_revision"), estado.get("motivo"), cola_id=cola_id)
        conn.commit()
        return {"cola_id": cola_id}
    finally:
        conn.close()


def _rama_gate(estado: Estado) -> str:
    return estado["decision"]


def construir_grafo():
    g = StateGraph(Estado)
    for nombre, fn in (("ingesta_lead", ingesta_lead), ("investigacion_agente", investigacion_agente),
                       ("cualificacion_llm", cualificacion_llm), ("aplicar_rubrica", aplicar_rubrica),
                       ("validacion_determinista", validacion_determinista),
                       ("gate_confianza", gate_confianza), ("persistir_ok", persistir_ok),
                       ("cola_revision", cola_revision_nodo)):
        g.add_node(nombre, fn)

    g.add_edge(START, "ingesta_lead")
    g.add_edge("ingesta_lead", "investigacion_agente")
    g.add_edge("investigacion_agente", "cualificacion_llm")
    g.add_edge("cualificacion_llm", "aplicar_rubrica")
    g.add_edge("aplicar_rubrica", "validacion_determinista")
    g.add_edge("validacion_determinista", "gate_confianza")
    g.add_conditional_edges("gate_confianza", _rama_gate,
                            {"persistir_ok": "persistir_ok", "cola_revision": "cola_revision"})
    g.add_edge("persistir_ok", END)
    g.add_edge("cola_revision", END)
    return g.compile()
