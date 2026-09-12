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
EXIGENCIA_FIRME = "les requiero el abono de"


def _subtipo_sin_derecho(dictamen: dict) -> str:
    """Los tres motivos por los que no hay compensación piden cartas distintas."""
    if dictamen.get("dentro_plazo") is False:
        return "plazo"
    if dictamen.get("circunstancia_exime") is True:
        return "exime"
    return "umbral"


def _linea_peticion(tipo: str, dictamen: dict) -> str:
    imp = dictamen.get("importe_eur", 0)
    art = dictamen.get("articulo", "art. 7")
    if tipo == "firme":
        return (f"En virtud del {art} del Reglamento (CE) n.º 261/2004, {EXIGENCIA_FIRME} "
                f"{imp} € en efectivo (no en bonos ni vales), en el plazo de 14 días desde "
                f"la recepción de este escrito.")
    if tipo == "provisional":
        return (f"Les requiero que me indiquen por escrito la causa exacta del retraso y me "
                f"aporten la documentación que la acredite, junto con las medidas que "
                f"adoptaron para evitarlo. Mientras no quede acreditada una circunstancia "
                f"extraordinaria en el sentido del art. 5(3) y de la jurisprudencia del TJUE, "
                f"la compensación que me corresponde es de {imp} € ({art}), cuyo abono "
                f"reclamo desde ahora.")
    if tipo == "sin_derecho":
        # ponytail: aquí NO se admite nada. El motor sabe que no hay compensación,
        # pero un escrito enviado a la aerolínea nunca renuncia por escrito a un
        # derecho ni le da hecha su defensa: pide datos y lo que sí procede.
        sub = _subtipo_sin_derecho(dictamen)
        if sub == "plazo":
            return ("Les solicito que me remitan la causa exacta del retraso, la hora real de "
                    "llegada registrada y copia de las comunicaciones que me enviaron sobre "
                    "esta incidencia, así como el detalle de la atención que se me prestó.")
        if sub == "exime":
            return ("Les solicito que acrediten documentalmente esa causa y las medidas "
                    "razonables que adoptaron para evitar el retraso, como exige el art. 5(3) "
                    "del Reglamento (CE) n.º 261/2004: la carga de esa prueba les corresponde "
                    "a ustedes. Con independencia de ello, les reclamo los gastos de atención "
                    "que tuve que asumir por mi cuenta (artículos 6 y 9).")
        return ("Les solicito que me confirmen por escrito la hora real de llegada del vuelo "
                "y la causa del retraso, y les reclamo los gastos de atención que tuve que "
                "asumir por mi cuenta (artículos 6 y 9).")
    return ""


# Prosa formal para la carta. El campo `motivo` del dictamen está escrito para la
# pantalla (tuteo, directo) y no sirve para un escrito dirigido a la aerolínea.
_AMBITO_CARTA = {
    "ambito_uk": (
        "Les solicito que me confirmen por escrito la causa del retraso, la hora real de "
        "llegada y el régimen de compensación que aplican a un vuelo con salida desde el "
        "Reino Unido, así como el procedimiento para reclamar ante ustedes."
    ),
    "ambito_b": (
        "Les solicito que me confirmen por escrito qué compañía operó efectivamente el vuelo "
        "y si es un transportista comunitario, dato del que depende la aplicación del "
        "Reglamento (CE) n.º 261/2004 a un vuelo con destino en la Unión Europea "
        "(art. 3(1)(b)), junto con la causa del retraso y la hora real de llegada."
    ),
    "ambito_fuera": (
        "Les solicito que me indiquen la causa del retraso, la hora real de llegada y el "
        "régimen de compensación y asistencia que aplican a este trayecto, con indicación "
        "del convenio o normativa en que se amparan."
    ),
}
_AMBITO_GENERICO = (
    "Les solicito que me confirmen por escrito la causa del retraso, la hora real de llegada "
    "y el régimen de compensación y asistencia aplicable a este vuelo."
)


def _pie_ambito(tipo: str, dictamen: dict) -> str:
    if tipo == "fuera_ambito":
        return _AMBITO_CARTA.get(dictamen.get("ambito_clave"), _AMBITO_GENERICO)
    if tipo == "falta_dato":
        if dictamen.get("falta_dato") == "transportista_comunitario":
            return _AMBITO_CARTA["ambito_b"]
        return _AMBITO_GENERICO
    return ""


def _cierre(tipo: str) -> str:
    if tipo == "firme":
        return ("Quedo a la espera de su respuesta dentro del plazo indicado. De no atenderse, "
                "acudiré al organismo nacional competente y, en su caso, a la vía judicial.")
    if tipo == "provisional":
        return ("Quedo a la espera de su respuesta. De no recibirla o de no acreditarse la "
                "causa alegada, acudiré al organismo nacional competente y, en su caso, a la "
                "vía judicial.")
    return "Quedo a la espera de su respuesta."


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


def _fecha_es(v) -> str:
    """ISO -> dd/mm/aaaa; una carta no lleva fechas en formato de base de datos."""
    s = str(v or "").strip()
    if len(s) == 10 and s[4] == "-" and s[7] == "-":
        return f"{s[8:]}/{s[5:7]}/{s[:4]}"
    return s or "[fecha del vuelo]"


def _horas(v) -> str:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return "un retraso"
    return f"{n:g} hora" + ("" if n == 1 else "s")


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
    fecha = _fecha_es(hechos.get("fecha_vuelo"))
    ref = "El vuelo, con localizador [localizador de la reserva], "

    if tipo in ("fuera_ambito", "falta_dato"):
        texto = _ensamblar(
            _CABECERA,
            f"Asunto: consulta sobre el vuelo {origen}-{destino} de {fecha}",
            f"{ref}salió de {origen} con destino {destino} el {fecha} y llegó con "
            f"{_horas(hechos.get('retraso_llegada_h'))} de retraso sobre la hora prevista.",
            _pie_ambito(tipo, dictamen),
            "Quedo a la espera de su respuesta.",
            _FIRMA,
        )
        return {"tipo": tipo, "texto": texto}

    narrativa = narrativa.strip() or (
        f"{ref}salió de {origen} con destino {destino} el {fecha} y llegó con "
        f"{_horas(hechos.get('retraso_llegada_h'))} de retraso sobre la hora prevista.")
    causa = (hechos.get("causa_texto") or "").strip()
    if not refutacion.strip():
        if not causa:
            refutacion = "No se me ha comunicado por escrito la causa del retraso."
        elif tipo == "sin_derecho":
            refutacion = (f"La causa que se me indicó verbalmente fue «{causa.lower()}», sin "
                          f"que se me haya acreditado documentalmente.")
        else:
            refutacion = (f"La causa alegada ({causa.lower()}) no me consta acreditada, y la "
                          f"carga de acreditarla les corresponde a ustedes.")
    else:
        refutacion = refutacion.strip()
    sent = (dictamen.get("sentencia") or "").strip()
    if sent and sent != "—" and tipo != "sin_derecho":
        etiqueta = "Jurisprudencia aplicable" if sent.startswith(("TJUE", "C-")) else "Fundamento aplicable"
        refutacion += f" {etiqueta}: {sent}."
    oferta = hechos.get("oferta_aerolinea_eur")
    nota_oferta = ""
    if oferta and dictamen.get("importe_eur") and oferta < dictamen["importe_eur"]:
        nota_oferta = (f"No acepto la oferta de {oferta:g} € que se me hizo: es inferior a la "
                       f"compensación que me corresponde y no sustituye a esta.")
    linea_abono = "Abono mediante transferencia a la cuenta IBAN [IBAN]." if tipo == "firme" else ""

    texto = _ensamblar(
        _CABECERA,
        (f"Asunto: solicitud de información sobre el vuelo {origen}-{destino} de {fecha}"
         if tipo == "sin_derecho" else
         f"Asunto: reclamación por el vuelo {origen}-{destino} de {fecha}"),
        narrativa,
        refutacion,
        _linea_peticion(tipo, dictamen),
        nota_oferta,
        linea_abono,
        _cierre(tipo),
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

Dirígete a la aerolínea de usted en plural («les ruego», «ustedes»). Nada de tuteo, ni de
fórmulas de márketing, ni de exclamaciones: es un escrito que puede acabar en un juzgado.

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
