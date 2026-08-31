#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Autocheck del núcleo determinista de la Demo 5: aplicar_rubrica (R1-R12), _descalificar y
gate_confianza (R13-R15 + regla dura). No toca Postgres ni llama a ningún modelo.

Cubre en particular que R8/R9 (gates de encaje) y R11/R12 (conteo) son ALCANZABLES -- el bug
que corrigió la reordenación de la rúbrica el 2026-08-31.
"""
from grafo_leads import _descalificar, _senales_con_evidencia, aplicar_rubrica, gate_confianza

# Claves que un fragmento de senales_crudas DEBE traer -- el stub de investigacion_agente las
# produce hoy; el bucle ReAct real (miércoles) tiene que producir las mismas, o la
# auditabilidad de leads.senales se rompe en silencio (recuperado_en -> None).
CLAVES_SENAL_CRUDA = {"snippet", "url", "recuperado_en"}

FICHA_OK = {"pais": "UK", "sector": "software", "tipo_negocio": "producto", "tamano_estimado": 40}


def h(senales=(), encaje="fuerte", decisor=True):
    return {"senales": list(senales), "encaje_producto": encaje, "contacto_decisor": decisor}


def rubrica(ficha, hallazgos):
    return aplicar_rubrica({"ficha": ficha, "hallazgos": hallazgos})


def test_descalificadores():
    assert _descalificar({"pais": "DE"}, h())[0] == "R1"
    assert _descalificar({"pais": "UK", "estado": "dissolved"}, h())[0] == "R2"
    assert _descalificar({"pais": "UK", "tipo_negocio": "servicios"}, h())[0] == "R3"
    assert _descalificar({"pais": "UK", "sector": "online gambling"}, h())[0] == "R4"
    assert _descalificar({"pais": "UK", "tamano_estimado": 400}, h())[0] == "R5"
    assert _descalificar({"pais": "UK", "filial_cotizada": True}, h())[0] == "R5"
    # R6 cruza ficha + hallazgos: 5 personas sin S1 -> frío; con S1 -> pasa
    assert _descalificar({"pais": "UK", "tamano_estimado": 5}, h())[0] == "R6"
    assert _descalificar({"pais": "UK", "tamano_estimado": 5}, h([{"tipo": "S1", "ref": 0}])) is None
    assert _descalificar({"pais": "UK", "nombre": "Datadog UK"}, h())[0] == "R7"
    assert _descalificar(FICHA_OK, h()) is None


def test_gates_de_encaje_alcanzables():
    # R8 gana aunque haya 2 señales (por eso va antes del conteo)
    r = rubrica(FICHA_OK, h([{"tipo": "S1", "ref": 0}, {"tipo": "S2", "ref": 1}], encaje="debil"))
    assert (r["etiqueta"], r["regla"]) == ("tibio", "R8"), r
    # R9: contacto sin poder de decisión y sin S1
    r = rubrica(FICHA_OK, h([{"tipo": "S3", "ref": 0}], decisor=False))
    assert (r["etiqueta"], r["regla"]) == ("tibio", "R9"), r
    # R9 no aplica si hay S1 (una ronda pesa más que el cargo del contacto)
    r = rubrica(FICHA_OK, h([{"tipo": "S1", "ref": 0}], decisor=False))
    assert r["regla"] == "R11", r


def test_conteo_de_senales():
    r = rubrica(FICHA_OK, h([{"tipo": "S1", "ref": 0}, {"tipo": "S2", "ref": 1}]))
    assert (r["etiqueta"], r["regla"]) == ("caliente", "R10"), r
    r = rubrica(FICHA_OK, h([{"tipo": "S1", "ref": 0}]))
    assert (r["etiqueta"], r["regla"]) == ("tibio", "R11"), r
    r = rubrica(FICHA_OK, h([]))
    assert (r["etiqueta"], r["regla"]) == ("tibio", "R12"), r


def test_gate():
    base = {"ficha": FICHA_OK, "etiqueta": "caliente", "regla": "R10", "confianza": 0.95,
            "errores_validacion": [], "motivo": "x"}

    # Camino feliz
    assert gate_confianza(base)["decision"] == "persistir_ok"

    # Regla dura: error determinista -> cola aunque la confianza sea alta
    g = gate_confianza({**base, "errores_validacion": ["contacto_email: email sintácticamente inválido"]})
    assert g["decision"] == "cola_revision" and g["resultado_log"] == "cola_revision"

    # R13: rival declarada -> se toma la más baja
    g = gate_confianza({**base, "etiqueta_rival": "tibio"})
    assert g["decision"] == "cola_revision" and g["etiqueta"] == "tibio", g

    # R14: sin ficha -> sin_cualificar
    g = gate_confianza({**base, "ficha": {}})
    assert g["resultado_log"] == "sin_cualificar" and g["etiqueta"] is None

    # R15: confianza baja -> cola
    g = gate_confianza({**base, "confianza": 0.5})
    assert g["decision"] == "cola_revision" and "confianza baja" in g["motivo"]

    # Fallo de cualificación -> sin_cualificar, no desaparece
    g = gate_confianza({"_error_cualificacion": "JSON inválido"})
    assert g["resultado_log"] == "sin_cualificar"


def test_evidencia_materializada():
    crudas = [{"snippet": "raised Series A", "url": "http://n1", "recuperado_en": "2026-08-31"}]
    assert CLAVES_SENAL_CRUDA <= set(crudas[0]), "fragmento de evidencia incompleto"
    estado = {"senales_crudas": crudas,
              "hallazgos": {"senales": [{"tipo": "S1", "valor": "Serie A", "ref": 0}]}}
    out = _senales_con_evidencia(estado)
    assert out[0]["snippet"] == "raised Series A" and out[0]["recuperado_en"] == "2026-08-31", out
    # ref rota -> se materializa sin evidencia (la validación de trazabilidad ya lo habría parado)
    estado["hallazgos"]["senales"][0]["ref"] = 9
    assert _senales_con_evidencia(estado)[0]["url"] is None


def demo():
    test_descalificadores()
    test_gates_de_encaje_alcanzables()
    test_conteo_de_senales()
    test_gate()
    test_evidencia_materializada()
    print("test_rubrica.py: OK (5 bloques)")


if __name__ == "__main__":
    demo()
