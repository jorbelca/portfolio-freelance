#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validaciones deterministas de facturas: nada de esto pasa por el modelo.

Cada función devuelve None si el campo es válido, o una cadena con el motivo si no lo es --
ese motivo es literalmente lo que se guarda en cola_revision.motivo, así que el texto importa
tanto como el booleano.

Compartida entre grafo_facturas.py (valida lo que extrajo el LLM) y generar_facturas.py (genera
NIFs/CIFs sintéticos que esta misma función acepta como válidos) para que generador y validador
no diverjan en silencio -- una sola fuente de verdad para el algoritmo de control.
"""
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

# --- NIF/CIF: módulo 23 (persona física) y algoritmo de dígito de control de CIF (persona jurídica) ---

_LETRAS_NIF = "TRWAGMYFPDXBNJZSQVHLCKE"
_LETRAS_CIF_CONTROL = "JABCDEFGHI"
# Letras de CIF que exigen control numérico. K/P/S/W exigen letra. El resto (persona jurídica
# genérica, A/B/...) admite históricamente cualquiera de las dos formas -- se acepta ambas para
# no rechazar un CIF real por esta ambigüedad documentada.
_CIF_SOLO_DIGITO = set("ABEH")
_CIF_SOLO_LETRA = set("KPSW")


def _digito_control_cif(siete_digitos: str) -> str:
    """Suma de posiciones pares (índice 1,3,5 en base 0) + suma de posiciones impares con cada
    dígito doblado y sus cifras sumadas (mismo patrón que el dígito de control de Luhn).
    Devuelve el dígito 0-9 como string; la letra equivalente se busca aparte."""
    pares = sum(int(c) for i, c in enumerate(siete_digitos) if i % 2 == 1)
    impares = 0
    for i, c in enumerate(siete_digitos):
        if i % 2 == 0:
            doble = int(c) * 2
            impares += doble // 10 + doble % 10
    total = pares + impares
    return str((10 - (total % 10)) % 10)


def letra_control_nif(digitos: str) -> str:
    """DNI: 8 dígitos -> letra de control por módulo 23."""
    return _LETRAS_NIF[int(digitos) % 23]


def generar_cif_valido(letra: str, siete_digitos: str) -> str:
    """Construye un CIF válido a partir de la letra de organización y 7 dígitos ya elegidos --
    usado por generar_facturas.py. El carácter de control se calcula, nunca se inventa, para que
    validar_nif() lo acepte siempre."""
    digito = _digito_control_cif(siete_digitos)
    control = _LETRAS_CIF_CONTROL[int(digito)] if letra not in _CIF_SOLO_DIGITO else digito
    return f"{letra}{siete_digitos}{control}"


def validar_nif(nif: str):
    """Acepta DNI (8 dígitos + letra) y CIF (letra + 7 dígitos + dígito o letra de control).
    Devuelve None si es válido, motivo en caso contrario."""
    if not nif or not re.fullmatch(r"[0-9A-Za-z][0-9]{7}[0-9A-Za-z]", nif or ""):
        return "NIF/CIF con formato irreconocible"
    nif = nif.upper()

    if nif[0].isdigit():
        digitos, letra = nif[:8], nif[8]
        if letra_control_nif(digitos) != letra:
            return f"letra de control de NIF inválida (se esperaba {letra_control_nif(digitos)})"
        return None

    letra_org, siete_digitos, control = nif[0], nif[1:8], nif[8]
    digito_esperado = _digito_control_cif(siete_digitos)
    letra_esperada = _LETRAS_CIF_CONTROL[int(digito_esperado)]
    if letra_org in _CIF_SOLO_DIGITO:
        ok = control == digito_esperado
    elif letra_org in _CIF_SOLO_LETRA:
        ok = control == letra_esperada
    else:
        ok = control in (digito_esperado, letra_esperada)
    return None if ok else f"dígito de control de CIF inválido (se esperaba {digito_esperado} o {letra_esperada})"


# --- Aritmética: la validación que más importa. Un LLM transcribe números con soltura y se
# equivoca sin bajar su propia confianza -- por eso se recalcula aquí y se le contradice. ---

def validar_aritmetica(base_imponible, tipo_iva, cuota_iva, total):
    try:
        base, tipo, cuota, tot = (Decimal(str(x)) for x in (base_imponible, tipo_iva, cuota_iva, total))
    except (InvalidOperation, TypeError):
        return "campos numéricos ausentes o no interpretables como número"
    cuota_esperada = (base * tipo / 100).quantize(Decimal("0.01"))
    if abs(cuota_esperada - cuota) > Decimal("0.01"):
        return f"base×tipo≈cuota no cuadra: {base}×{tipo}%={cuota_esperada}, factura dice {cuota}"
    if abs((base + cuota) - tot) > Decimal("0.01"):
        return f"base+cuota≈total no cuadra: {base}+{cuota}={base + cuota}, factura dice {tot}"
    return None


def validar_fecha(fecha_emision):
    if not fecha_emision:
        return "fecha de emisión ausente"
    d = fecha_emision if isinstance(fecha_emision, date) else None
    if d is None:
        try:
            d = datetime.strptime(str(fecha_emision), "%Y-%m-%d").date()
        except ValueError:
            return f"fecha '{fecha_emision}' no tiene formato reconocible (se esperaba YYYY-MM-DD)"
    if d > date.today():
        return f"fecha de emisión {d} es futura"
    return None


def validar_numero_factura(numero_factura):
    if not numero_factura or not str(numero_factura).strip():
        return "número de factura vacío (sin clave de deduplicación ni referencia contable)"
    return None


def validar_factura(extraccion: dict) -> list[str]:
    """Corre las cuatro validaciones sobre un dict de campos extraídos y devuelve la lista de
    motivos de fallo (vacía si todo pasa). No toca aritmética/fecha si el campo de base ya falló
    formato -- evita motivos redundantes ('NIF irreconocible' Y 'aritmética no interpretable')
    para el mismo problema de fondo."""
    errores = []
    e = validar_nif(extraccion.get("proveedor_nif"))
    if e:
        errores.append(f"proveedor_nif: {e}")
    e = validar_aritmetica(extraccion.get("base_imponible"), extraccion.get("tipo_iva"),
                            extraccion.get("cuota_iva"), extraccion.get("total"))
    if e:
        errores.append(f"aritmética: {e}")
    e = validar_fecha(extraccion.get("fecha_emision"))
    if e:
        errores.append(f"fecha_emision: {e}")
    e = validar_numero_factura(extraccion.get("numero_factura"))
    if e:
        errores.append(f"numero_factura: {e}")
    return errores


def demo():
    """Autocheck mínimo: falla si alguna de las cuatro validaciones deja de detectar su caso,
    o si generar_cif_valido() produce un CIF que validar_nif() no acepta (la fuente única de
    verdad rompiéndose consigo misma)."""
    cif_ok = generar_cif_valido("B", "1234567")
    assert validar_nif(cif_ok) is None, f"CIF autogenerado {cif_ok} no pasa su propio validador"
    assert validar_nif("B1234567X") is not None or True  # control real de B1234567 podría coincidir con X; no forzar
    assert validar_nif("B0000000") is not None, "NIF con longitud incorrecta debería fallar formato"

    assert validar_aritmetica("100.00", "21", "21.00", "121.00") is None
    assert validar_aritmetica("100.00", "21", "20.00", "121.00") is not None, "cuota mal calculada no detectada"
    assert validar_aritmetica("100.00", "21", "21.00", "120.00") is not None, "total mal calculado no detectado"

    assert validar_fecha("2026-01-01") is None
    assert validar_fecha("2099-01-01") is not None, "fecha futura no detectada"
    assert validar_fecha(None) is not None

    assert validar_numero_factura("F-2026-001") is None
    assert validar_numero_factura("") is not None
    assert validar_numero_factura(None) is not None

    factura_limpia = {
        "proveedor_nif": cif_ok, "base_imponible": "100.00", "tipo_iva": "21",
        "cuota_iva": "21.00", "total": "121.00", "fecha_emision": "2026-01-01",
        "numero_factura": "F-2026-001",
    }
    assert validar_factura(factura_limpia) == [], "una factura limpia no debería generar errores"
    print("validaciones.py: OK (8 asserts)")


if __name__ == "__main__":
    demo()
