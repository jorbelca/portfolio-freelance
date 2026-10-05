"""Reglas de audio, enumeración exhaustiva y composición de conjuntos."""
import math

from modelo import CLMError, CLMLocal


PREFERENCIAS = {"montaje_sencillo", "portabilidad", "discrecion"}
USOS = {"entrevista_fija", "entrevista_movil", "otro"}


class ConfigError(ValueError):
    pass


def validar_catalogo_audio(catalog):
    for item in catalog["items"]:
        attrs = item["atributos"]
        family = item["familia"]
        if family == "sistema_audio":
            required_supports = [x.removeprefix("soporte:") for x in item["requiere"] if x.startswith("soporte:")]
            people = attrs.get("participantes_max")
            qualities = attrs.get("cualidades")
            support = attrs.get("perfil_soporte")
            if (attrs.get("tipo") != family or isinstance(people, bool) or people not in (1, 2)
                    or not isinstance(attrs.get("perfil_compatibilidad"), str)
                    or not isinstance(attrs.get("salida"), str)
                    or not isinstance(qualities, dict) or any(not isinstance(v, str) for v in qualities.values())
                    or any(not x.startswith("soporte:") for x in item["requiere"])
                    or len(required_supports) > 1
                    or (support is not None and (not isinstance(support, str) or not support))
                    or bool(required_supports) != bool(support)
                    or (required_supports and required_supports[0] != support)):
                raise ConfigError(f"ficha de sistema de audio inválida: {item['id']}")
        elif family == "adaptador_audio":
            if (attrs.get("tipo") != family or not isinstance(attrs.get("perfil_adaptador"), str)
                    or not isinstance(attrs.get("entrada"), str) or not isinstance(attrs.get("salida"), str)
                    or item["requiere"]):
                raise ConfigError(f"ficha de adaptador inválida: {item['id']}")
        elif family == "soporte" and (attrs.get("tipo") != family or not isinstance(attrs.get("perfil_soporte"), str)
                                       or item["requiere"]):
            raise ConfigError(f"ficha de soporte inválida: {item['id']}")


def validar_estado(state, domain, catalog):
    if not isinstance(state, dict):
        raise ConfigError("estado inválido")
    necesidad = state.get("necesidad", "")
    if not isinstance(necesidad, str) or not necesidad.strip() or len(necesidad) > 2000:
        raise ConfigError("necesidad debe tener entre 1 y 2000 caracteres")
    dispositivos = {d["id"] for d in domain["dispositivos"]}
    if state.get("dispositivo_id") not in dispositivos:
        raise ConfigError("elige un dispositivo cuya compatibilidad esté contemplada")
    if state.get("tienda_id", catalog["tienda_id"]) != catalog["tienda_id"]:
        raise ConfigError("la sesión y el catálogo deben pertenecer a la misma tienda")
    if state.get("uso_id") not in (None, *USOS):
        raise ConfigError("uso_id debe ser entrevista_fija, entrevista_movil, otro o null")
    personas = state.get("participantes")
    if isinstance(personas, bool) or not isinstance(personas, int) or not 1 <= personas <= 2:
        raise ConfigError("participantes debe ser 1 o 2")
    presupuesto = state.get("presupuesto_minor")
    if isinstance(presupuesto, bool) or not isinstance(presupuesto, int) or presupuesto < 0:
        raise ConfigError("presupuesto_minor debe ser un entero no negativo")
    preferences = state.get("preferencias", [])
    if (not isinstance(preferences, list) or any(not isinstance(p, str) for p in preferences)
            or len(set(preferences)) != len(preferences) or any(p not in PREFERENCIAS for p in preferences)):
        raise ConfigError("preferencias contiene un criterio desconocido o repetido")
    excluded = state.get("productos_excluidos", [])
    if not isinstance(excluded, list) or any(not isinstance(x, str) for x in excluded):
        raise ConfigError("productos_excluidos debe ser una lista de IDs")
    rules = domain["reglas"]
    if any(item["moneda"] != rules["moneda"] or item["decimales_moneda"] != rules["decimales_moneda"] for item in catalog["items"]):
        raise ConfigError("el catálogo no comparte moneda y decimales con las reglas de audio")
    return state


def _disponible(item):
    return item["disponibilidad"] == "disponible" and (item["cantidad_disponible"] or 0) >= 1


def _compatibilidad(domain, profile, device_id, key="perfil_sistema"):
    return next((row for row in domain["compatibilidades"]
                 if row.get(key) == profile and row["dispositivo_id"] == device_id
                 and (key != "perfil_adaptador" or "perfil_sistema" not in row)), None)


def _detalle_producto(item, quantity=1):
    return {
        "id": item["id"], "nombre": item["nombre"], "familia": item["familia"], "cantidad": quantity,
        "precio_unitario_minor": item["precio_minor"], "subtotal_minor": item["precio_minor"] * quantity,
        "origen_comercial": item["origen_comercial"], "incluye": item["incluye"],
        "evidencia": item["fuentes"], "origen": item["origen"],
    }


def _conjuntos_tecnicos(state, catalog, domain):
    productos = catalog["items"]
    por_id = {p["id"]: p for p in productos}
    previos = set(state.get("productos_previos", []))
    dispositivo = next(d for d in domain["dispositivos"] if d["id"] == state["dispositivo_id"])
    excluidos = set(state.get("productos_excluidos", []))
    resultados, pendientes = [], []

    for sistema in productos:
        attrs = sistema["atributos"]
        if attrs.get("tipo") != "sistema_audio" or sistema["id"] in excluidos:
            continue
        if attrs.get("participantes_max", 0) < state["participantes"]:
            continue
        if not _disponible(sistema):
            if sistema["disponibilidad"] == "desconocido":
                pendientes.append({"producto_id": sistema["id"], "motivo": "disponibilidad desconocida"})
            continue
        compat = _compatibilidad(domain, attrs.get("perfil_compatibilidad"), dispositivo["id"])
        if compat is None or compat["resultado"] == "desconocido":
            pendientes.append({"producto_id": sistema["id"], "motivo": "compatibilidad no verificada"})
            continue
        if compat["resultado"] == "incompatible":
            continue

        adapters = [None]
        if compat["resultado"] == "requires_adapter":
            adapters = []
            for adapter in productos:
                a = adapter["atributos"]
                if a.get("perfil_adaptador") != compat.get("perfil_adaptador") or adapter["id"] in excluidos:
                    continue
                adapter_compat = _compatibilidad(domain, a["perfil_adaptador"], dispositivo["id"], "perfil_adaptador")
                if adapter_compat and adapter_compat["resultado"] == "compatible" and _disponible(adapter):
                    adapters.append(adapter)
                elif adapter_compat and adapter_compat["resultado"] == "compatible" and adapter["disponibilidad"] == "desconocido":
                    pendientes.append({"producto_id": adapter["id"], "motivo": "disponibilidad desconocida"})
            if not adapters:
                continue

        support_profile = attrs.get("perfil_soporte")
        supports = [None]
        if support_profile:
            support_options = [p for p in productos if p["atributos"].get("tipo") == "soporte"
                               and p["atributos"].get("perfil_soporte") == support_profile
                               and p["id"] not in excluidos]
            supports = [p for p in support_options if _disponible(p)]
            if not supports:
                pendientes.extend({"producto_id": p["id"], "motivo": "disponibilidad desconocida"}
                                  for p in support_options if p["disponibilidad"] == "desconocido")
                continue

        for adapter in adapters:
            for support in supports:
                parts = [sistema] + ([adapter] if adapter else []) + ([support] if support else [])
                item_rows = [_detalle_producto(item) for item in parts]
                total = sum(row["subtotal_minor"] for row in item_rows)
                candidate_id = "+".join(item["id"] for item in parts)
                route = f"{sistema['nombre']} → {dispositivo['nombre']}"
                if adapter:
                    route += f" mediante {adapter['nombre']}"
                candidate = {
                    "id": candidate_id, "productos": item_rows, "total_minor": total,
                    "moneda": catalog["items"][0]["moneda"], "decimales_moneda": catalog["items"][0]["decimales_moneda"],
                    "convencion_total": "precios sintéticos con impuestos incluidos; envío desconocido y excluido",
                    "observado_el": catalog["observado_el"],
                    "conexiones": [route],
                    "requisitos_satisfechos": [
                        {"requisito": f"{state['participantes']} {'voz simultánea' if state['participantes'] == 1 else 'voces simultáneas'}", "evidencia": sistema["fuentes"]},
                        {"requisito": f"compatibilidad con {dispositivo['nombre']}", "evidencia": compat["evidencia"]},
                    ],
                    "compromisos": [], "compatibilidad": "verificada",
                    "texto_clm": {
                        "montaje_sencillo": f"Montaje: {(attrs.get('cualidades') or {}).get('montaje') or 'sin datos verificados'}.",
                        "portabilidad": f"Portabilidad: {(attrs.get('cualidades') or {}).get('portabilidad') or 'sin datos verificados'}.",
                        "discrecion": f"Discreción: {(attrs.get('cualidades') or {}).get('discrecion') or 'sin datos verificados'}.",
                    },
                }
                actuales = {item["id"] for item in parts}
                candidate["continuidad"] = {
                    "conservados": [por_id[x]["nombre"] for x in sorted(previos & actuales) if x in por_id],
                    "sustituidos": [por_id[x]["nombre"] if x in por_id else x for x in sorted(previos - actuales)],
                    "añadidos": [por_id[x]["nombre"] for x in sorted(actuales - previos)],
                } if previos else None
                if adapter:
                    candidate["requisitos_satisfechos"].append({"requisito": "adaptación de señal", "evidencia": adapter["fuentes"]})
                if support:
                    candidate["requisitos_satisfechos"].append({"requisito": "soporte incluido", "evidencia": support["fuentes"]})
                resultados.append(candidate)
    return resultados, pendientes


def _sin_texto_modelo(result):
    for key in ("recomendaciones", "alternativas_fuera_presupuesto"):
        for candidate in result[key]:
            candidate.pop("texto_clm", None)
    return result


def _sistemas_unicos(candidates):
    unique, seen = [], set()
    for candidate in candidates:
        system = next((p["id"] for p in candidate["productos"] if p["familia"] == "sistema_audio"), candidate["id"])
        if system not in seen:
            unique.append(candidate)
            seen.add(system)
    return unique


def recomendar(state, catalog, domain, ranker=None):
    validar_catalogo_audio(catalog)
    validar_estado(state, domain, catalog)
    if state.get("uso_id") == "otro":
        return {
            "estado": "fuera_de_alcance", "version_catalogo": catalog["version_catalogo"],
            "snapshot_id": catalog.get("snapshot_id"), "busqueda_completa": True,
            "total_explorados": 0, "candidatos_factibles": 0,
            "candidatos_evaluados_contextualmente": 0, "evaluacion_contextual_completa": True,
            "pendientes_verificacion": [], "recomendaciones": [], "alternativas_fuera_presupuesto": [],
            "pregunta": None, "modelo": {"estado": "no_requerido"}, "orden": "sin_recomendacion",
        }
    technical, pending = _conjuntos_tecnicos(state, catalog, domain)
    under_budget = [c for c in technical if c["total_minor"] <= state["presupuesto_minor"]]
    over_budget = [c for c in technical if c["total_minor"] > state["presupuesto_minor"]]
    last_decision = state.get("historial_decisiones", [])[-1:]
    concession_declined = bool(last_decision and last_decision[0].get("tipo") == "concesion_presupuesto"
                               and last_decision[0].get("respuesta") == "rechazar")
    result = {
        "version_catalogo": catalog["version_catalogo"], "snapshot_id": catalog.get("snapshot_id"),
        "total_explorados": len(technical), "candidatos_factibles": len(under_budget),
        "candidatos_evaluados_contextualmente": 0, "busqueda_completa": True,
        "evaluacion_contextual_completa": True,
        "pendientes_verificacion": pending, "recomendaciones": [], "alternativas_fuera_presupuesto": [],
        "pregunta": None, "modelo": {"estado": "no_requerido"}, "orden": "precio",
    }
    if not under_budget:
        if over_budget and not concession_declined and state.get("preguntas_realizadas", 0) < domain["reglas"]["max_preguntas"]:
            minimum = min(c["total_minor"] for c in over_budget)
            result.update({
                "estado": "requiere_concesion",
                "alternativas_fuera_presupuesto": _sistemas_unicos(
                    sorted(over_budget, key=lambda c: (c["total_minor"], c["id"]))
                )[:3],
                "pregunta": {"id": "aceptar_presupuesto_minimo", "tipo": "concesion_presupuesto",
                             "presupuesto_actual_minor": state["presupuesto_minor"], "presupuesto_minimo_minor": minimum,
                             "texto": "No hay un conjunto verificado dentro del presupuesto. ¿Quieres elevarlo hasta el coste del conjunto más económico?"},
            })
        elif pending and not over_budget:
            result["estado"] = "pendiente_verificacion"
        else:
            result["estado"] = "sin_conjunto_dentro_del_presupuesto"
        return _sin_texto_modelo(result)

    preferencias = state.get("preferencias", [])
    if preferencias:
        rankable = under_budget
        max_model = domain["reglas"].get("max_candidatos_modelo", len(rankable))
        scoring = sorted(rankable, key=lambda c: (c["total_minor"], c["id"]))[:max_model]
        result["evaluacion_contextual_completa"] = len(scoring) == len(rankable)
        context = [
            f"Uso descrito: {state['necesidad']}",
            f"Dispositivo confirmado: {next(d['nombre'] for d in domain['dispositivos'] if d['id'] == state['dispositivo_id'])}",
            f"Participantes: {state['participantes']}",
            "Preferencias confirmadas: " + ", ".join(preferencias),
        ]
        if state.get("uso_id"):
            context.insert(1, f"Uso confirmado: {state['uso_id']}")
        context = "\n".join(context)
        try:
            ranker = ranker or CLMLocal()
            scores, model_status = ranker.ordenar(context, scoring, preferencias)
            result["modelo"] = model_status
            result["candidatos_evaluados_contextualmente"] = len(scoring) if scores else 0
            if scores:
                result["orden"] = "media_puntuaciones_clm_por_preferencia"
                under_budget.sort(key=lambda c: (-scores.get(c["id"], -math.inf),
                                                 -len((c["continuidad"] or {}).get("conservados", [])), c["total_minor"], c["id"]))
            else:
                under_budget.sort(key=lambda c: (c["total_minor"], c["id"]))
        except (CLMError, ValueError) as e:
            result["modelo"] = {"estado": "no_disponible", "motivo": str(e)}
            result["evaluacion_contextual_completa"] = False
            under_budget.sort(key=lambda c: (c["total_minor"], c["id"]))
    else:
        under_budget.sort(key=lambda c: (c["total_minor"], -len((c["continuidad"] or {}).get("conservados", [])), c["id"]))
    result["estado"] = "recomendado"
    por_sistema = _sistemas_unicos(under_budget)
    result["sistemas_factibles"] = len(por_sistema)
    result["recomendaciones"] = por_sistema[:domain["reglas"]["max_recomendaciones"]]
    return _sin_texto_modelo(result)
