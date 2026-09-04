#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Grafo LangGraph de la Demo 5: ingesta_lead -> investigacion_agente -> cualificacion_llm
-> aplicar_rubrica -> revision_llm -> validacion_determinista -> gate_confianza
-> {persistir_ok | cola_revision}. Todo camino escribe cualificacion_log.

Reparto de responsabilidad, no negociable al tocar este fichero (mismo criterio que
4/grafo_facturas.py, confirmado con advisor):

1. Las reglas R1-R12 de la rúbrica NO las decide el modelo. `cualificacion_llm` devuelve solo
   juicio factual: qué señales encontró y con qué evidencia (`ref` a un fragmento recuperado),
   si el encaje de producto es fuerte o débil, si el contacto decide. La etiqueta la deriva
   `aplicar_rubrica` en Python -- descalificadores R1-R7 sobre la ficha, gates de encaje
   R8-R9, conteo de señales R10-R12 -- de forma que `regla` es reproducible: el comprador
   re-deriva la etiqueta desde `senales` + `ficha` guardadas, sin fiarse del modelo. El
   esquema de salida del modelo NO tiene campo `etiqueta` a propósito.

1b. `revision_llm` es una SEGUNDA llamada, separada a propósito: recibe la etiqueta
   provisional que ya derivó `aplicar_rubrica` y su porqué, y hace una sola pregunta --
   ¿debería revisar esto un humano? Devuelve una etiqueta rival defendible (o null) y una
   confianza. Ese juicio de "esto es frontera" calibra mejor cuando es su propia pregunta y
   no una clave más en un JSON de cinco. Solo corre para caliente/tibio -- un frio por
   descalificador o un sin_cualificar no tienen nada que reconsiderar.

2. Regla dura (de la Demo 4): si `validacion_determinista` encontró errores, la decisión es
   cola_revision pase lo que pase con la confianza. La confianza declarada por el modelo no
   puede vetar una validación determinista (lección Demo 3: el modelo satura su confianza
   arriba, los errores incluidos).

3. Orden del gate: errores deterministas -> R14 sin evidencia -> R13 recorte por rival ->
   R15 umbral de confianza. R15 el último y el más débil, la propia rúbrica lo dice.

La rúbrica vive en rubrica-cualificacion-leads.md (versionada, se ve en el diff) y ahí es la
referencia para humanos (comprador, revisor) y para R1-R16, que son código, no prompt. El
contrato del modelo es mucho más estrecho que el documento entero -- señales S1-S4 (§3.3) +
encaje_producto (§3.2), nada de R1-R9/R13-R16 ni la narrativa de venta -- así que NO se inyecta
el .md completo en el prompt de `cualificacion_llm`: solo el resumen de esas dos secciones,
escrito a mano ahí mismo. Si §3.2/§3.3 cambian, ese resumen se actualiza a mano también; el
.md sigue siendo la fuente de verdad de la que ese resumen es un extracto, no al revés.
"""
import json
import os
from pathlib import Path
from typing import Optional, TypedDict

import psycopg2
import psycopg2.errors
from langgraph.graph import END, START, StateGraph

from tools import buscar_senales, ficha_empresa
from validaciones import normalizar_empresa, validar_lead

AQUI = Path(__file__).resolve().parent
UMBRAL_DEFECTO = float(os.environ.get("LEADS_CONFIANZA_UMBRAL", "0.7"))
MAX_BUSQUEDAS = int(os.environ.get("LEADS_MAX_BUSQUEDAS", "3"))
MODELO = os.environ.get("LEADS_MODELO", "poolside/laguna-s-2.1:free")  # vía OpenRouter
ORDEN_ETIQUETA = {"frio": 0, "tibio": 1, "caliente": 2}

# Listas del criterio comercial (ver §5 de la rúbrica: son del cliente y cambian; aquí van
# como constantes del módulo, no como config, porque no hay un valor "por entorno").
SECTORES_EXCLUIDOS = ("defensa", "armamento", "gambling", "juego", "casino", "adulto", "adult")
# Competidores ficticios de Nubeforge -- el universo de la demo es sintético entero, no se
# mezclan marcas reales. En producción esta lista la aporta el cliente (§5 de la rúbrica).
COMPETIDORES = ("pipewatch", "cloudsentry", "stackgauge", "nimbusmetrics")

# Cargos que, por sí solos, indican que el contacto no decide una compra (R9). El modelo
# también devuelve `contacto_decisor`, pero satura arriba (lección Demo 3): esta lista manda.
CARGOS_SIN_PODER = ("junior", "intern", "becari", "trainee", "graduate", "student",
                    "apprentice", "assistant", "prácticas", "practicas")
# Sectores del ICP de Nubeforge. Si la ficha sitúa a la empresa de lleno aquí (y es de
# producto), R8 ("encaje débil") no se dispara solo con el juicio del modelo.
SECTORES_ICP = ("software", "saas", "data", "devtools", "developer tools", "cloud",
                "infrastructure", "infraestructura", "analytics", "analítica", "platform")


def _cargo_sin_poder(cargo: Optional[str]) -> bool:
    return any(k in (cargo or "").lower() for k in CARGOS_SIN_PODER)


def _dedup_senales(senales: list) -> list:
    """Un fragmento de evidencia (`ref`) respalda como mucho UNA señal contada. El modelo a
    veces emite dos señales sobre el mismo fragmento (un post de blog leído como dos hechos)
    e infla el conteo hacia R10. Se deduplica en el origen para que conteo, validación y lo
    que se guarda vean la misma lista."""
    vistos, out = set(), []
    for s in senales or []:
        if s.get("ref") in vistos:
            continue
        vistos.add(s.get("ref"))
        out.append(s)
    return out


# --- V2: enrutado + primer email -------------------------------------------------------
# Dict estático sector -> comercial (§14 del plan: "~10 líneas", no round-robin ni carga).
COMERCIALES = {"fintech": "Dana Ruiz", "saas": "Marco Vidal", "software": "Marco Vidal"}
COMERCIAL_DEFECTO = "Aisha Kern"
FOLLOWUP_SUGERIDO = os.environ.get("LEADS_FOLLOWUP", "3 días")  # solo texto en el log, sin calendario


class Estado(TypedDict, total=False):
    lead_ref: str
    empresa: str
    contacto_nombre: Optional[str]
    contacto_email: str
    contacto_cargo: Optional[str]
    canal_origen: Optional[str]
    empresa_normalizada: str
    # Inyectados en modo SALTAR_INVESTIGACION / --sin-llm (ver procesar_leads.py).
    canned_senales: Optional[list]     # sustituye solo la mitad web (no reproducible)
    canned_hallazgos: Optional[dict]   # --sin-llm: además salta el modelo
    # Producidos por los nodos.
    ficha: dict
    senales_crudas: list          # [{"snippet": ..., "url": ..., "recuperado_en": ...}]
    investigacion_pasos: list     # traza del bucle ReAct, para el log / la demo
    hallazgos: dict               # juicio del modelo, SIN etiqueta
    _error_cualificacion: Optional[str]
    etiqueta: Optional[str]
    regla: Optional[str]
    motivo: Optional[str]
    etiqueta_rival: Optional[str]
    motivo_duda: Optional[str]   # de revision_llm: qué haría dudar a un humano
    confianza: float
    errores_validacion: list
    decision: str                 # 'persistir_ok' | 'cola_revision'
    resultado_log: str            # 'cualificado' | 'cola_leads' | 'sin_cualificar'
    lead_id: Optional[int]
    cola_id: Optional[int]
    # V2 (solo caliente que pasa el gate).
    asignado_a: Optional[str]
    followup_sugerido: Optional[str]
    borrador_message_id: Optional[str]
    borrador_asunto: Optional[str]
    borrador_cuerpo: Optional[str]


# --- Nodos --------------------------------------------------------------------------------

def ingesta_lead(estado: Estado) -> dict:
    return {"empresa_normalizada": normalizar_empresa(estado.get("empresa", ""))}


def investigacion_agente(estado: Estado) -> dict:
    """`ficha_empresa` es determinista (lookup en el registro) y siempre se llama -- no hay
    juicio en decidir consultarla. El juicio es la parte web: qué buscar y cuándo parar. Eso
    es el bucle ReAct: el modelo ve la ficha + lo encontrado hasta ahora y decide la siguiente
    query o `parar`, hasta MAX_BUSQUEDAS.

    En modo SALTAR_INVESTIGACION / --sin-llm el estado trae `canned_senales`: se sustituye SOLO
    la mitad web (la no reproducible); la ficha se sigue sacando del mock, para que ese camino
    y el vídeo no puedan divergir (una sola fuente de ficha)."""
    ficha = ficha_empresa(estado.get("empresa", ""))
    if estado.get("canned_senales") is not None:
        return {"ficha": ficha, "senales_crudas": estado["canned_senales"], "investigacion_pasos": []}

    nombre = estado.get("empresa", "")
    api_key = _api_key()
    if not api_key:
        # Error de configuración, no fallo de tool en runtime -> se falla rápido (mismo
        # criterio que extraccion_llm en la Demo 4). Un fallo de buscar_senales EN MEDIO del
        # bucle sí degrada a [] (ver tools.py) y el lead cae a R14, que es lo correcto en vivo.
        raise RuntimeError("Falta OPENROUTER_API_KEY para el bucle de investigación. "
                           "Usa procesar_leads.py --sin-llm o SALTAR_INVESTIGACION=1.")
    senales, pasos = [], []
    for _ in range(MAX_BUSQUEDAS):
        d = _paso_investigacion(nombre, ficha, senales, api_key)
        pasos.append(d)
        if d.get("accion") != "buscar" or not d.get("query"):
            break
        nuevas = buscar_senales(d["query"])
        vistos = {s["url"] for s in senales}
        senales.extend(s for s in nuevas if s.get("url") not in vistos)
    return {"ficha": ficha, "senales_crudas": senales, "investigacion_pasos": pasos}


def _api_key() -> Optional[str]:
    """LEADS_LLM_API_KEY, o GEMINI_API_KEY (ya en ../1/.env para otras demos), o OPENROUTER_API_KEY."""
    return (os.environ.get("LEADS_LLM_API_KEY") or os.environ.get("GEMINI_API_KEY")
            or os.environ.get("OPENROUTER_API_KEY"))


def _llamar_openrouter(prompt: str, modelo: str, api_key: str) -> str:
    import time

    from openai import InternalServerError, OpenAI, RateLimitError
    # Por defecto OpenRouter. LEADS_LLM_BASE_URL apunta el mismo cliente OpenAI a otro proveedor
    # compatible -- p.ej. la API de Gemini de Google AI Studio (tier gratis con cuota propia, no
    # un pool compartido): https://generativelanguage.googleapis.com/v1beta/openai/
    client = OpenAI(base_url=os.environ.get("LEADS_LLM_BASE_URL", "https://openrouter.ai/api/v1"),
                    api_key=api_key)
    kwargs = dict(model=modelo, messages=[{"role": "user", "content": prompt}],
                  # margen para el scratchpad, no solo el JSON (lección Demo 3 i21). Los modelos
                  # de razonamiento :free gastan miles de tokens pensando antes del JSON -> alto.
                  max_tokens=int(os.environ.get("LEADS_MAX_TOKENS", "8192")),
                  temperature=0, timeout=int(os.environ.get("LEADS_TIMEOUT", "120")))
    if os.environ.get("LEADS_JSON_MODE", "1") == "1":
        kwargs["response_format"] = {"type": "json_object"}  # algún modelo free lo rechaza -> LEADS_JSON_MODE=0
    # Los modelos :free devuelven vacío / 429 (pool compartido) de forma intermitente. Reintento
    # con backoff -- temperatura 0, así que no cambia el resultado bueno.
    intentos = int(os.environ.get("LEADS_REINTENTOS", "3"))
    ultimo = ""
    for i in range(intentos):
        try:
            resp = client.chat.completions.create(**kwargs)
        except RateLimitError as e:
            # pool :free de OpenRouter, o cuota por minuto del tier gratis de Gemini. Backoff.
            ultimo = f"429 rate limit ({str(e)[:120]})"
            time.sleep(2 * (i + 1))
            continue
        except InternalServerError as e:
            # 503 "high demand" -- típico de un modelo recién lanzado. Transitorio, mismo backoff.
            ultimo = f"5xx del proveedor ({str(e)[:120]})"
            time.sleep(2 * (i + 1))
            continue
        # Guard de la lección i21 / bug 1 de la Demo 4: una respuesta de error de OpenRouter llega
        # con choices=None. Sin esto, resp.choices[0] tira un TypeError críptico en vez de un motivo.
        if not getattr(resp, "choices", None):
            ultimo = f"OpenRouter sin choices: {getattr(resp, 'error', None) or str(resp)[:200]}"
            continue
        contenido = resp.choices[0].message.content
        if contenido and contenido.strip():
            return contenido
        ultimo = f"respuesta vacía (finish_reason={getattr(resp.choices[0], 'finish_reason', '?')})"
    raise RuntimeError(f"el modelo no devolvió respuesta utilizable tras {intentos} intento(s): {ultimo}")


def _paso_investigacion(nombre: str, ficha: dict, senales: list, api_key: str) -> dict:
    """Un paso del bucle ReAct: el modelo ve la ficha y lo encontrado, y devuelve
    {"accion": "buscar"|"parar", "query": <str>, "razonamiento": <str>}. Un fallo de
    parseo se trata como 'parar' -- no bloquear la investigación por un JSON torcido."""
    encontrado = "\n".join(f"- {s['snippet'][:200]}" for s in senales) or "(nada aún)"
    prompt = (
        f"Investigas si '{nombre}' es un buen lead para Nubeforge (SaaS de observabilidad de "
        "coste y fiabilidad de pipelines de datos en la nube). Buscas señales de TIMING: ronda "
        "de financiación reciente, contratación de ingeniería/plataforma/data, stack "
        "cloud-native, menciones públicas de dolor con coste de nube o fiabilidad de datos.\n\n"
        f"FICHA DE REGISTRO:\n{json.dumps(ficha, ensure_ascii=False)}\n\n"
        f"SEÑALES ENCONTRADAS HASTA AHORA ({len(senales)}):\n{encontrado}\n\n"
        "Decide el siguiente paso. Devuelve SOLO un JSON:\n"
        '  {"accion": "buscar" | "parar", "query": "<consulta web si buscas>", "razonamiento": "<breve>"}\n'
        "Para cuando tengas señales suficientes para cualificar, o cuando dos búsquedas "
        "seguidas no aporten nada nuevo. No repitas una query ya usada."
    )
    try:
        datos = json.loads(_llamar_openrouter(
            prompt, MODELO, api_key))
        return {"accion": datos.get("accion", "parar"), "query": datos.get("query"),
                "razonamiento": datos.get("razonamiento")}
    except Exception as e:
        return {"accion": "parar", "query": None, "razonamiento": f"paso abortado: {e}"}


def cualificacion_llm(estado: Estado) -> dict:
    """Devuelve `hallazgos` (juicio factual SIN etiqueta). La confianza y la etiqueta rival
    salen de `revision_llm`, un paso aparte. En --sin-llm usa canned_hallazgos y no llama a
    ninguna API. Un fallo de parseo NO hace desaparecer el lead: se propaga como
    _error_cualificacion y el gate lo manda a sin_cualificar (lección Demo 3 i21 / bug 5 de
    la Demo 4)."""
    if estado.get("canned_hallazgos") is not None:
        h = dict(estado["canned_hallazgos"])
        h["senales"] = _dedup_senales(h.get("senales") or [])
        return {"hallazgos": h}

    api_key = _api_key()
    if not api_key:
        raise RuntimeError(
            "Falta la clave del modelo (OPENROUTER_API_KEY o LEADS_LLM_API_KEY, en ../1/.env). "
            "Para probar el grafo sin clave, usa procesar_leads.py --sin-llm.")

    ficha = estado.get("ficha") or {}
    crudas = estado.get("senales_crudas") or []
    evidencia = "\n".join(f"[{i}] {s.get('snippet', '')} ({s.get('url', 's/url')})"
                          for i, s in enumerate(crudas)) or "(sin resultados)"
    prompt = (
        "Eres el nodo de cualificación de un pipeline de leads para Nubeforge (SaaS de "
        "observabilidad de coste y fiabilidad de pipelines de datos en la nube; ICP: empresas "
        "de producto software UK, post-PMF, escalando ingeniería). Extrae SOLO juicio factual "
        "según los criterios de abajo -- la etiqueta la deriva otro paso determinista a partir "
        "de lo que devuelvas, no la decides tú.\n\n"
        f"=== FICHA DE EMPRESA (de ficha_empresa) ===\n{json.dumps(ficha, ensure_ascii=False, indent=2)}\n\n"
        f"=== EVIDENCIA WEB (de buscar_señales, numerada) ===\n{evidencia}\n\n"
        "=== CÓMO CONTAR SEÑALES (un fragmento respalda como mucho UNA señal) ===\n"
        "S1 — ronda de financiación anunciada (~12 meses): seed, Serie A o Serie B. Un 'seed' "
        "sin importe cuenta; pre-seed, angel o importe declarado < £1M, NO.\n"
        "S2 — contratación de ingeniería a escala: un fragmento que cita un número de puestos "
        "≥ 2, o varias ofertas distintas de ingeniería/plataforma/data, o lenguaje explícito "
        "de crecimiento de equipo. Una sola vacante concreta NO es S2.\n"
        "S3 — stack cloud-native visible: basta con que la evidencia nombre una nube "
        "gestionada (AWS/GCP/Azure); Kubernetes u orquestación de datos suman pero NO son "
        "obligatorios. 'multi-cloud on AWS and GCP' cuenta.\n"
        "S4 — dolor público en el dominio de Nubeforge: coste de nube, fiabilidad de "
        "pipelines de datos u observabilidad de datos, dicho por la empresa.\n"
        "Si un fragmento no encaja claramente en S1–S4, NO lo cuentes.\n\n"
        "`encaje_producto` = 'debil' SOLO si el producto no es cloud-native o el dominio es "
        "meramente adyacente (automatización contable, compliance…). Una empresa de software "
        "de producto dentro del ICP se considera 'fuerte'.\n\n"
        "Devuelve SOLO un JSON con estas claves:\n"
        '  "senales": lista de {"tipo": "S1"|"S2"|"S3"|"S4", "valor": "<qué dice>", "ref": <índice del fragmento de evidencia que la respalda>}\n'
        '  "encaje_producto": "fuerte" | "debil"\n'
        '  "contacto_decisor": true | false\n'
        "Cada señal DEBE tener un `ref` a un fragmento real de la evidencia. No inventes señales."
    )

    try:
        contenido = _llamar_openrouter(
            prompt, MODELO, api_key)
        datos = json.loads(contenido)
        h = {
            "senales": _dedup_senales(datos.get("senales") or []),
            "encaje_producto": datos.get("encaje_producto"),
            "contacto_decisor": bool(datos.get("contacto_decisor", True)),
        }
        return {"hallazgos": h}
    except (json.JSONDecodeError, KeyError, TypeError, ValueError, AttributeError, RuntimeError) as e:
        return {"_error_cualificacion": str(e), "hallazgos": {}, "confianza": 0.0}


def revision_llm(estado: Estado) -> dict:
    """Segunda lectura (ver punto 1b de la cabecera). Una sola llamada, foco único: dada la
    etiqueta provisional, ¿debería mirarla un humano? Devuelve `etiqueta_rival` (o None), una
    `confianza` derivada de un sí/no ("¿hay un hueco que verificar?" -- un booleano es más
    fiable que pedirle al modelo una probabilidad calibrada) y `motivo_duda`. Corre solo para
    caliente/tibio. En --sin-llm lee de canned_hallazgos. Un fallo NO tumba el lead: sin rival
    y confianza 0.0 -> el gate lo manda a cola por R15 (fallar hacia la revisión humana)."""
    if estado.get("_error_cualificacion"):
        return {}
    etiqueta = estado.get("etiqueta")
    if etiqueta not in ("caliente", "tibio"):
        return {"confianza": 1.0, "etiqueta_rival": None}

    if estado.get("canned_hallazgos") is not None:
        ch = estado["canned_hallazgos"]
        rival = ch.get("etiqueta_rival")
        return {"confianza": float(ch.get("confianza", 0.9)),
                "etiqueta_rival": rival if rival in ORDEN_ETIQUETA and rival != etiqueta else None}

    api_key = _api_key()
    if not api_key:
        raise RuntimeError("Falta la clave del modelo (OPENROUTER_API_KEY o LEADS_LLM_API_KEY).")

    h = estado.get("hallazgos") or {}
    ficha = estado.get("ficha") or {}
    crudas = estado.get("senales_crudas") or []
    evidencia = "\n".join(f"[{i}] {s.get('snippet', '')}" for i, s in enumerate(crudas)) or "(sin resultados)"
    senales_txt = "\n".join(f"- {s.get('tipo')}: {s.get('valor')}" for s in h.get("senales") or []) or "(ninguna)"
    prompt = (
        "Eres el paso de SEGUNDA LECTURA de un pipeline de leads para Nubeforge (SaaS de "
        "observabilidad de coste y fiabilidad de pipelines de datos en la nube; ICP: empresas "
        "de producto software UK, post-PMF, escalando ingeniería).\n\n"
        f"Un paso determinista ya clasificó este lead como **{etiqueta}** (regla "
        f"{estado.get('regla')}): {estado.get('motivo')}\n\n"
        f"FICHA:\n{json.dumps(ficha, ensure_ascii=False)}\n\n"
        f"EVIDENCIA:\n{evidencia}\n\n"
        f"SEÑALES CONTADAS:\n{senales_txt}\n\n"
        "Tu único trabajo: decidir si un humano debería mirar esto antes de actuar. No "
        "re-clasifiques; evalúa la clasificación que ya hay.\n\n"
        "POR DEFECTO NO SE REVISA. La mayoría de los leads bien clasificados salen con "
        "etiqueta_rival=null y revisar=false. Marcar todo para revisión vacía de sentido la "
        "cola: solo se escala lo que un humano podría decidir DISTINTO.\n\n"
        "1. etiqueta_rival — solo si un comercial sensato, con ESTA misma evidencia, podría "
        "defender OTRA etiqueta, y puedes señalar el fragmento concreto que la sostiene. "
        "Ejemplos válidos: la ronda financia explícitamente un pivote fuera del dominio de "
        "Nubeforge; la evidencia dice que las vacantes llevan meses abiertas. Si no hay un "
        "fragmento así, null.\n"
        "2. revisar — solo si falta un dato CONCRETO y NOMBRABLE sin el cual la acción "
        "siguiente (escribir al contacto) podría ser un error.\n"
        "   NO cuentan como hueco, y por sí solos NUNCA justifican revisar=true:\n"
        "   · que la evidencia no traiga fecha o pueda ser antigua — ya viene filtrada por "
        "recencia antes de llegarte;\n"
        "   · que la evidencia no esté confirmada de forma independiente — es la evidencia "
        "que hay, y ya está citada con su fuente;\n"
        "   · que el stack, la vacante o la ronda 'podrían haber cambiado' — vale para "
        "cualquier lead y no distingue nada;\n"
        "   · prudencia genérica, o que el contacto no esté verificado como decisor.\n"
        "   Si tu único motivo cabe en esa lista, revisar=false.\n\n"
        "Devuelve SOLO un JSON:\n"
        '  "etiqueta_rival": null | "caliente" | "tibio" | "frio"\n'
        '  "revisar": true | false\n'
        '  "motivo_duda": "<una frase: la lectura rival o el hueco a verificar, o \'ninguna\'>"\n'
    )
    try:
        datos = json.loads(_llamar_openrouter(prompt, MODELO, api_key))
        rival = datos.get("etiqueta_rival")
        return {"confianza": 0.5 if bool(datos.get("revisar", False)) else 0.9,
                "etiqueta_rival": rival if rival in ORDEN_ETIQUETA and rival != etiqueta else None,
                "motivo_duda": datos.get("motivo_duda")}
    except (json.JSONDecodeError, KeyError, TypeError, ValueError, AttributeError, RuntimeError) as e:
        return {"confianza": 0.0, "etiqueta_rival": None, "motivo_duda": f"segunda lectura falló: {e}"}


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
    tiene_s1 = any(s.get("tipo") == "S1" for s in senales)

    # R8: el modelo propone "encaje débil", pero el nodo la ignora cuando la ficha sitúa a la
    # empresa de lleno en el ICP (producto + sector software/SaaS/data). En ese caso "no
    # cloud-native / dominio adyacente" no se sostiene contra el registro, y si de verdad le
    # falta tracción se refleja solo en el conteo de señales (R11/R12), no en un veto del modelo.
    ficha_icp = ((ficha.get("tipo_negocio") or "").lower() == "producto"
                 and any(x in (ficha.get("sector") or "").lower() for x in SECTORES_ICP))
    if h.get("encaje_producto") == "debil" and not ficha_icp:
        return {"etiqueta": "tibio", "regla": "R8", "motivo": "encaje de producto débil"}

    # R9: cargo sin poder de decisión, y sin S1. v0.4: SOLO la lista determinista. El
    # `contacto_decisor` del modelo satura en falso fuera de la C-suite (un "Engineering
    # Manager" caía a R9), así que ya no vota aquí.
    if _cargo_sin_poder(estado.get("contacto_cargo")) and not tiene_s1:
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
        return {"decision": "cola_revision", "resultado_log": "cola_leads",
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
        return {"decision": "cola_revision", "resultado_log": "cola_leads", "etiqueta": baja,
                "motivo": f"frontera {estado.get('regla')}: {etiqueta} vs {rival} (rival declarada) — se toma {baja}"}

    # R15: umbral de confianza. El último y el más débil.
    if estado.get("confianza", 0.0) < UMBRAL_DEFECTO:
        return {"decision": "cola_revision", "resultado_log": "cola_leads", "etiqueta": etiqueta,
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
    cola_leads.senales -- un motivo cuya señal cita evidencia que ya no está es
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


def _insertar_cola(cur, estado: Estado, motivo: str, tipo: str = "cualificacion") -> int:
    cur.execute(
        """INSERT INTO cola_leads (empresa, empresa_normalizada, contacto_nombre, contacto_email,
           contacto_cargo, canal_origen, pais, sector, tipo_negocio, tamano_estimado,
           antiguedad_anios, etiqueta, senales, confianza, motivo, tipo)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (*_fila_comun(estado), estado.get("etiqueta"), json.dumps(_senales_con_evidencia(estado)),
         estado.get("confianza"), motivo, tipo))
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
            _log(cur, estado, "cola_leads", "duplicado (email o empresa ya en leads)", cola_id=cola_id)
            conn.commit()
            return {"decision": "cola_revision", "resultado_log": "cola_leads",
                    "motivo": "duplicado (email o empresa ya en leads)", "cola_id": cola_id}
    finally:
        conn.close()


def cola_revision_nodo(estado: Estado) -> dict:
    conn = psycopg2.connect(_dsn())
    try:
        cur = conn.cursor()
        cola_id = _insertar_cola(cur, estado, estado.get("motivo") or "(sin motivo)")
        _log(cur, estado, estado.get("resultado_log", "cola_leads"), estado.get("motivo"), cola_id=cola_id)
        conn.commit()
        return {"cola_id": cola_id}
    finally:
        conn.close()


def _rama_gate(estado: Estado) -> str:
    return estado["decision"]


# --- V2: enrutado + redacción del primer email ----------------------------------------

def enrutado(estado: Estado) -> dict:
    """Asigna comercial por sector (dict estático) y fija el followup sugerido. Sin API de
    calendario: `followup_sugerido` es solo texto que un humano lee en la cola."""
    sector = (estado.get("ficha") or {}).get("sector", "")
    return {"asignado_a": COMERCIALES.get(sector, COMERCIAL_DEFECTO),
            "followup_sugerido": FOLLOWUP_SUGERIDO}


def _redactar_email(estado: Estado, api_key: Optional[str]):
    """Devuelve (asunto, cuerpo, es_plantilla). Con key: 1 llamada al modelo. Sin key (o si
    falla): plantilla, MARCADA como tal en el cuerpo -- no se hace pasar una plantilla por
    texto de modelo (mismo criterio que §14.5 sobre el resumen de la Demo 6)."""
    empresa = estado.get("empresa") or "la empresa"
    contacto = estado.get("contacto_nombre") or "equipo"
    motivo = estado.get("motivo") or ""
    senales = "; ".join(f"{s['tipo']}: {s.get('valor') or (s.get('snippet') or '')[:80]}"
                        for s in _senales_con_evidencia(estado)) or "encaje de perfil ICP"

    def plantilla():
        cuerpo = (
            "[BORRADOR GENERADO POR PLANTILLA — sin modelo. Reescribir antes de enviar.]\n\n"
            f"Hola {contacto},\n\n"
            f"He visto que {empresa} encaja con lo que hacemos en Nubeforge: ayudamos a equipos "
            "de datos a controlar el coste y la fiabilidad de sus pipelines en la nube.\n\n"
            f"Motivo de encaje: {motivo}.\n"
            f"Señales: {senales}.\n\n"
            "¿Te viene bien una llamada corta esta semana?\n\nUn saludo")
        return f"{empresa}: primer contacto", cuerpo, True

    if not api_key:
        return plantilla()
    prompt = (
        f"Redacta el PRIMER email de contacto de un comercial de Nubeforge (SaaS de "
        f"observabilidad de coste y fiabilidad de pipelines de datos en la nube) a {contacto} "
        f"de {empresa}. Cita explícitamente por qué encaja: {motivo}. Señales encontradas: "
        f"{senales}. Tono directo, 5-7 frases, sin promesas exageradas, con una llamada a la "
        f'acción clara. Devuelve SOLO un JSON: {{"asunto": "...", "cuerpo": "..."}}.')
    try:
        d = json.loads(_llamar_openrouter(
            prompt, MODELO, api_key))
        return d["asunto"], d["cuerpo"], False
    except Exception:
        return plantilla()


def _enviar_greenmail(asunto: str, cuerpo: str, estado: Estado) -> Optional[str]:
    """Deja el borrador en GreenMail (SMTP de ../1/docker-compose.yml). SIEMPRE a
    borradores@nubeforge.local, NUNCA al prospecto real. Sin servidor -> None, y el borrador
    igual queda en la cola para revisar (degradar, no romper)."""
    import smtplib
    from email.message import EmailMessage
    from email.utils import make_msgid
    msg = EmailMessage()
    msg_id = make_msgid(domain="nubeforge.local")
    msg["Message-ID"] = msg_id
    msg["From"] = "sdr@nubeforge.local"
    msg["To"] = "borradores@nubeforge.local"
    msg["Subject"] = asunto
    msg["X-Lead-Empresa"] = estado.get("empresa") or ""
    msg["X-Lead-Contacto-Real"] = estado.get("contacto_email") or ""
    msg["X-Lead-Comercial"] = estado.get("asignado_a") or ""
    msg.set_content(cuerpo)
    try:
        with smtplib.SMTP(os.environ.get("LEADS_SMTP_HOST", "127.0.0.1"),
                          int(os.environ.get("LEADS_SMTP_PORT", "3025")), timeout=10) as s:
            s.send_message(msg)
        return msg_id
    except Exception:
        return None


def redaccion_borrador(estado: Estado) -> dict:
    # --sin-llm (canned_hallazgos) = ningún camino llama al modelo, este tampoco: usa plantilla.
    # Sin canned -> el modelo redacta si hay clave.
    api_key = None if estado.get("canned_hallazgos") is not None else _api_key()
    asunto, cuerpo, es_plantilla = _redactar_email(estado, api_key)
    marca = " [plantilla]" if es_plantilla else ""
    asunto_final = f"[BORRADOR — revisar antes de enviar]{marca} {asunto} — {estado.get('asignado_a')}"
    msg_id = _enviar_greenmail(asunto_final, cuerpo, estado)

    conn = psycopg2.connect(_dsn())
    try:
        cur = conn.cursor()
        cola_id = _insertar_cola(cur, estado, "borrador pendiente de revisión", tipo="borrador")
        cur.execute("UPDATE cola_leads SET borrador_message_id = %s WHERE id = %s", (msg_id, cola_id))
        cur.execute(
            "UPDATE leads SET asignado_a = %s, followup_sugerido = %s, borrador_message_id = %s WHERE id = %s",
            (estado.get("asignado_a"), estado.get("followup_sugerido"), msg_id, estado.get("lead_id")))
        conn.commit()
        return {"cola_id": cola_id, "borrador_message_id": msg_id,
                "borrador_asunto": asunto_final, "borrador_cuerpo": cuerpo}
    finally:
        conn.close()


def _rama_persistir(estado: Estado) -> str:
    """Solo `caliente` que pasó el gate va a redacción (R16). El camino de duplicado ya lo
    resolvió persistir_ok (insertó cola + logueó); tibio/frio se quedan en leads."""
    if estado.get("decision") != "cola_revision" and estado.get("etiqueta") == "caliente":
        return "outreach"
    return "fin"


def construir_grafo():
    g = StateGraph(Estado)
    for nombre, fn in (("ingesta_lead", ingesta_lead), ("investigacion_agente", investigacion_agente),
                       ("cualificacion_llm", cualificacion_llm), ("aplicar_rubrica", aplicar_rubrica),
                       ("revision_llm", revision_llm),
                       ("validacion_determinista", validacion_determinista),
                       ("gate_confianza", gate_confianza), ("persistir_ok", persistir_ok),
                       ("cola_revision", cola_revision_nodo), ("enrutado", enrutado),
                       ("redaccion_borrador", redaccion_borrador)):
        g.add_node(nombre, fn)

    g.add_edge(START, "ingesta_lead")
    g.add_edge("ingesta_lead", "investigacion_agente")
    g.add_edge("investigacion_agente", "cualificacion_llm")
    g.add_edge("cualificacion_llm", "aplicar_rubrica")
    g.add_edge("aplicar_rubrica", "revision_llm")
    g.add_edge("revision_llm", "validacion_determinista")
    g.add_edge("validacion_determinista", "gate_confianza")
    g.add_conditional_edges("gate_confianza", _rama_gate,
                            {"persistir_ok": "persistir_ok", "cola_revision": "cola_revision"})
    g.add_conditional_edges("persistir_ok", _rama_persistir,
                            {"outreach": "enrutado", "fin": END})
    g.add_edge("enrutado", "redaccion_borrador")
    g.add_edge("redaccion_borrador", END)
    g.add_edge("cola_revision", END)
    return g.compile()
