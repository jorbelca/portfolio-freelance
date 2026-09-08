"""Redacción de la reclamación.

D3 (README §2): el tipo de carta lo decide `clasificar_plantilla()` de forma
determinista a partir del dictamen, y la línea de petición (con el importe y el
artículo) la construye este módulo en código. El modelo solo redacta dos párrafos
de prosa (relato de los hechos y refutación de la excusa); nunca toca la cifra.

Un dictamen `provisional` NUNCA produce una exigencia de pago firme: su plantilla
pide primero la acreditación de la circunstancia extraordinaria. Test en
test_carta.py.
"""

from __future__ import annotations

import os

# --- Selección de plantilla (determinista) --------------------------------

TIPOS = ("fuera_ambito", "falta_dato", "firme", "provisional", "sin_derecho")


def clasificar_plantilla(dictamen: dict) -> str:
    if dictamen.get("en_ambito") is False:
        return "fuera_ambito"
    if dictamen.get("en_ambito") is None:
        return "falta_dato"
    if not dictamen.get("elegible"):
        return "sin_derecho"       # < 3 h, fuera de plazo, o circunstancia que exime
    if dictamen.get("provisional"):
        return "provisional"
    return "firme"


# Frase que SOLO puede aparecer en la plantilla "firme".
EXIGENCIA_FIRME = "le requiero el abono de"


def _linea_peticion(tipo: str, dictamen: dict) -> str:
    imp = dictamen.get("importe_eur", 0)
    art = dictamen.get("articulo", "art. 7")
    if tipo == "firme":
        return (f"En virtud del {art} del Reglamento (CE) n.º 261/2004, {EXIGENCIA_FIRME} "
                f"{imp} € en efectivo (no en bonos ni vales), en el plazo de 14 días.")
    if tipo == "provisional":
        return (f"Solicito que me indiquen por escrito el motivo exacto del retraso y me "
                f"aporten la documentación que lo acredite. De no acreditarse una "
                f"circunstancia extraordinaria en el sentido del art. 5(3) y la "
                f"jurisprudencia del TJUE, la compensación que correspondería es de {imp} € "
                f"({art}), cuyo abono reclamaré entonces.")
    if tipo == "sin_derecho":
        return ("Conforme a los datos aportados, no se cumplen los requisitos para la "
                "compensación del art. 7. Aun así, les solicito la documentación que "
                "acredite la causa alegada y les recuerdo el deber de asistencia del "
                "art. 6/9, que se debe con independencia de aquella.")
    return ""


def _pie_ambito(tipo: str, dictamen: dict) -> str:
    if tipo == "fuera_ambito":
        return dictamen.get("motivo", "El vuelo queda fuera del ámbito del Reglamento 261/2004.")
    if tipo == "falta_dato":
        return ("No es posible emitir un dictamen: falta un dato imprescindible "
                f"({dictamen.get('falta_dato')}). " + dictamen.get("motivo", ""))
    return ""


# Cabecera y firma con huecos entre corchetes que el usuario rellena a mano.
_CABECERA = (
    "[Nombre y apellidos]\n"
    "[DNI / NIE]\n"
    "[Dirección postal]\n"
    "[Email de contacto] · [Teléfono]\n\n"
    "A la atención del Servicio de Atención al Cliente de [aerolínea]\n\n"
    "En [lugar], a [fecha de envío]"
)

_FIRMA = (
    "Atentamente,\n\n"
    "Fdo.: [Nombre y apellidos]\n\n"
    "Documentación que adjunto: [tarjeta de embarque / reserva], "
    "[justificante del retraso si lo hay]."
)


def _ensamblar(*bloques: str) -> str:
    """Une los bloques no vacíos con línea en blanco entre ellos. Sin sangría:
    los datos personales de la cabecera van a la izquierda, no indentados."""
    return "\n\n".join(b.strip() for b in bloques if b and b.strip()) + "\n"


def construir_carta(dictamen: dict, hechos: dict, *, narrativa: str = "",
                    refutacion: str = "") -> dict:
    """Ensambla la carta. `narrativa` y `refutacion` son los dos párrafos que puede
    rellenar el modelo; si vienen vacíos, se usa un texto mínimo. Los datos
    personales van como huecos entre corchetes: la capa determinista nunca los
    inventa y el modelo tiene instrucción de no hacerlo. Devuelve {tipo, texto}."""
    tipo = clasificar_plantilla(dictamen)
    origen = hechos.get("origen", "?")
    destino = hechos.get("destino", "?")
    fecha = hechos.get("fecha_vuelo") or "[fecha del vuelo]"
    ref = "El vuelo, con localizador [localizador de la reserva], "

    if tipo in ("fuera_ambito", "falta_dato"):
        texto = _ensamblar(
            _CABECERA,
            f"Asunto: consulta sobre el vuelo {origen}-{destino} de {fecha}",
            _pie_ambito(tipo, dictamen),
            "Quedo a la espera de su respuesta.",
            _FIRMA,
        )
        return {"tipo": tipo, "texto": texto}

    narrativa = narrativa.strip() or (
        f"{ref}salió de {origen} con destino {destino} el {fecha} y llegó con "
        f"{hechos.get('retraso_llegada_h', '?')} horas de retraso sobre la hora prevista.")
    refutacion = refutacion.strip() or (
        f"La causa alegada ({hechos.get('causa_texto') or 'no comunicada'}) no me consta "
        f"acreditada.")
    if dictamen.get("sentencia"):
        refutacion += f" Jurisprudencia aplicable: {dictamen['sentencia']}."
    oferta = hechos.get("oferta_aerolinea_eur")
    nota_oferta = ""
    if oferta and dictamen.get("importe_eur") and oferta < dictamen["importe_eur"]:
        nota_oferta = (f"Rechazo la oferta de {oferta:g} €: es inferior a la compensación "
                       f"que me corresponde.")
    linea_abono = "Abono mediante transferencia a la cuenta IBAN [IBAN]." if tipo == "firme" else ""

    texto = _ensamblar(
        _CABECERA,
        f"Asunto: reclamación por el vuelo {origen}-{destino} de {fecha}",
        narrativa,
        refutacion,
        _linea_peticion(tipo, dictamen),
        nota_oferta,
        linea_abono,
        "Quedo a la espera de su respuesta en el plazo indicado. En su defecto, acudiré al "
        "organismo nacional competente y, en su caso, a la vía judicial.",
        _FIRMA,
    )
    return {"tipo": tipo, "texto": texto}


# --- Prosa del modelo (opcional) ------------------------------------------

_PROMPT_CUERPO = """Redacta DOS párrafos breves y formales en español para una reclamación
por retraso de vuelo, en primera persona. Devuelve SOLO un JSON:
{{"narrativa": "...", "refutacion": "..."}}

- narrativa: relata los hechos (vuelo, fecha, retraso) con tono sobrio, sin exigir importes.
- refutacion: rebate la excusa de la aerolínea. NO menciones ninguna cifra de dinero ni el
  importe de la compensación.

NO inventes datos personales, nombres, localizadores, matrículas ni horas concretas: si
necesitas nombrar uno, escribe un hueco entre corchetes, p. ej. [localizador de la reserva],
[hora de llegada prevista]. Usa exactamente los datos de abajo, nada más.

Datos: vuelo {origen}-{destino} del {fecha}, retraso de {retraso} h a la llegada.
Excusa de la aerolínea: {causa}.
"""


def redactar_reclamacion(dictamen: dict, hechos: dict, *, usar_modelo: bool | None = None) -> dict:
    """Carta completa. Si hay clave de modelo (y no se desactiva), el modelo redacta
    los dos párrafos de prosa; el resto es determinista."""
    tipo = clasificar_plantilla(dictamen)
    if tipo in ("fuera_ambito", "falta_dato"):
        return construir_carta(dictamen, hechos)

    if usar_modelo is None:
        usar_modelo = os.environ.get("RECLAMACIONES_CARTA_LLM", "1") == "1"

    narrativa = refutacion = ""
    if usar_modelo:
        try:
            import json

            from llm import llamar
            d = json.loads(llamar(_PROMPT_CUERPO.format(
                origen=hechos.get("origen"), destino=hechos.get("destino"),
                fecha=hechos.get("fecha_vuelo") or "fecha no indicada",
                retraso=hechos.get("retraso_llegada_h"),
                causa=hechos.get("causa_texto") or "no comunicada")))
            narrativa, refutacion = d.get("narrativa", ""), d.get("refutacion", "")
        except Exception:
            pass  # sin modelo o fallo -> texto mínimo determinista

    return construir_carta(dictamen, hechos, narrativa=narrativa, refutacion=refutacion)
