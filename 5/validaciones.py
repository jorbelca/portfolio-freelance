#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validaciones deterministas de leads: nada de esto pasa por el modelo.

Cada función devuelve None si es válido, o una cadena con el motivo si no lo es -- ese motivo
es literalmente lo que se guarda en cola_revision.motivo, así que el texto importa tanto como
el booleano. Mismo criterio que 4/validaciones.py.
"""
import re
import unicodedata

# Sufijos de forma jurídica: quitarlos es normalización de FORMATO (igual que quitar un '%' de
# un tipo de IVA en la Demo 4), no adivinar significado. "Acme Ltd" y "Acme Limited" son la
# misma cuenta. Lo que NO se toca: "Group", "Holdings", "International" -- colapsar "Acme Ltd"
# con "Acme Group Ltd" sería adivinar que son la misma entidad, y a menudo no lo son.
_SUFIJOS_JURIDICOS = (
    "ltd", "limited", "plc", "llp", "llc", "inc", "incorporated", "corp", "corporation",
    "sl", "s l", "sa", "s a", "slu", "gmbh", "srl", "bv",
)


def normalizar_empresa(nombre: str) -> str:
    """Minúscula, sin tildes, sin puntuación, espacios colapsados, y sin el sufijo de forma
    jurídica final. Es la clave del UNIQUE(empresa_normalizada) de leads -- un segundo contacto
    de la misma empresa choca con él y se reconduce a cola."""
    s = "".join(c for c in unicodedata.normalize("NFKD", nombre or "") if not unicodedata.combining(c))
    s = re.sub(r"[^\w\s]", " ", s.lower())
    s = re.sub(r"\s+", " ", s).strip()
    partes = s.split(" ")
    if len(partes) > 1 and partes[-1] in _SUFIJOS_JURIDICOS:
        partes.pop()
        # "s l" / "s a": dos tokens
    if len(partes) > 1 and " ".join(partes[-2:]) in _SUFIJOS_JURIDICOS:
        partes = partes[:-2]
    return " ".join(partes).strip()


def validar_email(email: str):
    if not email or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", str(email).strip()):
        return "email sintácticamente inválido"
    return None


def validar_trazabilidad_senales(senales: list, senales_crudas: list):
    """Cada señal que el modelo cita en su juicio debe apuntar (`ref`) a un fragmento realmente
    recuperado por buscar_señales. Una señal sin respaldo -> el motivo no es auditable, así que
    el caso va a cola. El modelo no se vigila a sí mismo desde el prompt (lección Demo 3): lo
    comprueba este nodo."""
    for s in senales or []:
        ref = s.get("ref")
        if not isinstance(ref, int) or not (0 <= ref < len(senales_crudas or [])):
            return f"señal {s.get('tipo', '?')} sin respaldo en la evidencia recuperada (ref={ref!r})"
    return None


def validar_lead(campos: dict, hallazgos: dict, senales_crudas: list) -> list:
    """Corre las validaciones sobre un lead y devuelve la lista de motivos de fallo (vacía si
    todo pasa). La deduplicación NO está aquí: vive en el UNIQUE de SQL, una sola fuente de
    verdad (mismo criterio que la Demo 4)."""
    errores = []
    if not (campos.get("empresa") or "").strip():
        errores.append("empresa: nombre de empresa ausente")
    e = validar_email(campos.get("contacto_email"))
    if e:
        errores.append(f"contacto_email: {e}")
    e = validar_trazabilidad_senales((hallazgos or {}).get("senales") or [], senales_crudas or [])
    if e:
        errores.append(f"señales: {e}")
    return errores


def demo():
    """Autocheck mínimo: falla si alguna validación deja de detectar su caso."""
    assert normalizar_empresa("Acme Ltd") == "acme"
    assert normalizar_empresa("Acme Limited") == "acme"
    assert normalizar_empresa("  Açme  Data,  S.L.  ") == "acme data"
    assert normalizar_empresa("Acme Group Ltd") == "acme group", "no se colapsa Group con el nombre base"

    assert validar_email("a@b.io") is None
    assert validar_email("sin-arroba") is not None
    assert validar_email(None) is not None

    crudas = [{"snippet": "raised Series A", "url": "http://x"}]
    assert validar_trazabilidad_senales([{"tipo": "S1", "ref": 0}], crudas) is None
    assert validar_trazabilidad_senales([{"tipo": "S1", "ref": 5}], crudas) is not None, "ref fuera de rango no detectada"
    assert validar_trazabilidad_senales([{"tipo": "S1"}], crudas) is not None, "señal sin ref no detectada"

    limpio = validar_lead(
        {"empresa": "Acme Ltd", "contacto_email": "cto@acme.io"},
        {"senales": [{"tipo": "S1", "ref": 0}]}, crudas)
    assert limpio == [], f"lead limpio no debería dar errores: {limpio}"
    falla = validar_lead({"empresa": "", "contacto_email": "x"}, {}, [])
    assert len(falla) == 2, f"esperados 2 errores (empresa + email), {falla}"
    print("validaciones.py: OK (12 asserts)")


if __name__ == "__main__":
    demo()
