"""Motor de reglas EU261 — determinista, sin LLM.

Es la pieza que se vende: el importe y la elegibilidad salen de aquí, nunca del
modelo. El modelo (día X) solo rellena `hechos` a partir del relato libre y elige
una categoría de causa; todo lo de este fichero es aritmética y lookup.

Verificado el 2026-09-08 contra el texto del Reglamento en EUR-Lex (CELEX
32004R0261) y las sentencias del TJUE (ver README §6): bandas del art. 7(1)/(2),
gran círculo del art. 7(4), ámbito del art. 3(1) y umbral Sturgeon de 3 h — todos
coinciden, sin cambios de aritmética. La reducción del 7(2) aplicada al retraso
está respaldada por Sturgeon § 63 ("mutatis mutandis").
Plazos de prescripción: solo ES/FR/DE/GB se apoyan en Derecho nacional; el resto
no descarta la reclamación, solo avisa (ver PLAZO_FIABLE).

Cada paso del dictamen deja una fila en `out["traza"]` (regla + fuente con CELEX
y fecha de verificación). `FUENTES` es la tabla de citas; el README §6 se reancla
a ella. `out["motivo"]` es la prosa para el usuario y se compone de esas mismas
piezas — no se deriva por concatenación ciega para no romper la redacción que
revisó G-JURIDICO.

Autocheck: python3 reglas.py
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from math import asin, cos, radians, sin, sqrt

from aeropuertos import coords, en_ue, pais
from precedentes import analizar_circunstancia

# --- Constantes del Reglamento 261/2004 -------------------------------------

UMBRAL_RETRASO_H = 3.0           # llegada al destino final; Sturgeon C-402/07 y C-432/07
BANDA_CORTA_KM = 1500.0          # art. 7(1)(a)
BANDA_LARGA_KM = 3500.0          # art. 7(1)(b) tramo "otros vuelos"

# Fecha de la verificación contra EUR-Lex (README §6). Se cita en cada fila de traza.
VERIFICADO_EUR_LEX = "2026-09-08"

# Tabla de fuentes: clave -> (texto del artículo/sentencia, CELEX). El README §6
# se reancla aquí: si cambia una cita, cambia esta tabla y el §6 en el mismo commit.
FUENTES = {
    "ambito_a":     ("art. 3(1)(a) — salida desde un aeropuerto de la UE", "32004R0261"),
    "ambito_b":     ("art. 3(1)(b) — llegada a la UE desde un 3.er país, transportista comunitario", "32004R0261"),
    "ambito_uk":    ("art. 3(1) — salida fuera de la UE; salidas desde Reino Unido se rigen por UK261", "32004R0261"),
    "ambito_fuera": ("art. 3(1) — ni origen ni destino en el ámbito territorial", "32004R0261"),
    "umbral_3h":    ("art. 7(1) + TJUE C-402/07 y C-432/07 (Sturgeon): 3 h a la llegada", "62007CJ0402"),
    "plazo":        ("TJUE C-139/11 (Cuadrench Moré): el plazo lo fija el Derecho nacional", "62011CJ0139"),
    "banda_a":      ("art. 7(1)(a): 250 € hasta 1500 km", "32004R0261"),
    "banda_b":      ("art. 7(1)(b): 400 € (intracom. >1500 km, o cualquiera 1500–3500 km)", "32004R0261"),
    "banda_c":      ("art. 7(1)(c): 600 € (no intracom. >3500 km)", "32004R0261"),
    "reduccion":    ("art. 7(2): −50 %; aplicado al retraso vía Sturgeon § 63 ('mutatis mutandis')", "32004R0261"),
    "circ_5_3":     ("art. 5(3): circunstancias extraordinarias", "32004R0261"),
}

# Mapea la letra que devuelve `banda_compensacion` -> clave de FUENTES para la traza.
# Acoplado a propósito: si `banda_compensacion` devolviera una letra nueva, el
# KeyError es correcto (hay que añadirla aquí y a FUENTES, no tragárselo).
_ART_A_CLAVE = {"art. 7(1)(a)": "banda_a", "art. 7(1)(b)": "banda_b", "art. 7(1)(c)": "banda_c"}


def cita(clave: str) -> str:
    """Cadena de cita para la traza: 'texto · CELEX xxxx · verif. 2026-09-08'."""
    texto, celex = FUENTES[clave]
    return f"{texto} · CELEX {celex} · verif. {VERIFICADO_EUR_LEX}"


# Plazo para reclamar: lo fija el Derecho nacional de cada Estado (TJUE C-139/11,
# Cuadrench Moré; confirmado por la recopilación DG-MOVE de la Comisión: los plazos
# de Varsovia/Montreal NO se aplican a la compensación del 261).
#
# PLAZO_FIABLE: países cuyo plazo se apoya en ley nacional + práctica asentada. Solo
# aquí se emite un dictamen firme de "fuera de plazo".
PLAZO_ANOS_POR_PAIS = {
    "ES": 5,    # art. 1964.2 CC (redacción Ley 42/2015, en vigor 7-oct-2015)
    "FR": 5,    # art. 2224 Code civil; la Cass. descarta el plazo bienal de Montreal
    "DE": 3,    # § 195 BGB, corre desde el fin del año natural (§ 199.1 BGB)
    "GB": 6,    # Limitation Act 1980 s.5 (Inglaterra y Gales; Escocia son 5)
    # Resto de países: sin plazo verificado. Varios se apoyaban en un plazo de
    # Montreal (IT 2, BE 1) que Cuadrench Moré declara inaplicable. No se descarta
    # la reclamación por prescripción: se avisa. Este valor solo dispara el aviso.
    "IT": 3, "PT": 3, "NL": 5, "BE": 3,
}
# Norma nacional concreta de cada plazo fiable (para la traza; no cambia la lógica).
PLAZO_NORMA_POR_PAIS = {
    "ES": "art. 1964.2 Código Civil (Ley 42/2015)",
    "FR": "art. 2224 Code civil",
    "DE": "§ 195 BGB, desde fin del año natural (§ 199.1)",
    "GB": "Limitation Act 1980 s.5 (Inglaterra y Gales)",
}
PLAZO_FIABLE = {"ES", "FR", "DE", "GB"}
# País ausente del dict de arriba: se usa este valor para decidir si SALTA el aviso de
# posible prescripción. Nunca descarta la reclamación (solo PLAZO_FIABLE lo hace).
PLAZO_ANOS_DEFECTO = 3


# --- Distancia -------------------------------------------------------------

def distancia_km(origen_iata: str, destino_iata: str) -> float:
    """Gran círculo (haversine) entre dos aeropuertos, en km.

    Para vuelos con conexión, C-559/16 (Bossen) exige gran círculo entre el
    primer origen y el destino final, NO la suma de tramos. El MVP asume vuelo
    directo; cuando se implemente la conexión, llamar con (primer_origen,
    destino_final).
    """
    lat1, lon1 = map(radians, coords(origen_iata))
    lat2, lon2 = map(radians, coords(destino_iata))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * asin(sqrt(a)) * 6371.0088


def vuelo_intracomunitario(origen_iata: str, destino_iata: str) -> bool:
    return en_ue(origen_iata) and en_ue(destino_iata)


# --- Compensación art. 7 --------------------------------------------------

def banda_compensacion(dist_km: float, intracomunitario: bool) -> tuple[int, str]:
    """Importe base del art. 7(1) y la letra aplicable.

    (a) 250 € — vuelos de hasta 1500 km
    (b) 400 € — intracomunitarios de más de 1500 km, y todos los demás entre 1500 y 3500 km
    (c) 600 € — el resto (no intracomunitarios de más de 3500 km)
    """
    if dist_km <= BANDA_CORTA_KM:
        return 250, "art. 7(1)(a)"
    if intracomunitario:
        return 400, "art. 7(1)(b)"
    if dist_km <= BANDA_LARGA_KM:
        return 400, "art. 7(1)(b)"
    return 600, "art. 7(1)(c)"


def umbral_reduccion_h(dist_km: float, intracomunitario: bool) -> float:
    """Diferencia de hora de llegada a partir de la cual NO se reduce (art. 7(2)).

    Si la aerolínea ofreció transporte alternativo y la llegada real supera al
    horario previsto en menos de este umbral, la compensación se reduce un 50 %.
    """
    if dist_km <= BANDA_CORTA_KM:
        return 2.0
    if intracomunitario or dist_km <= BANDA_LARGA_KM:
        return 3.0
    return 4.0


# --- Plazo --------------------------------------------------------------

def dentro_de_plazo(fecha_vuelo: date, pais_reclamacion: str, hoy: date | None = None) -> bool:
    hoy = hoy or date.today()
    pais = (pais_reclamacion or "").strip().upper()
    anos = PLAZO_ANOS_POR_PAIS.get(pais, PLAZO_ANOS_DEFECTO)
    if pais == "DE":
        # § 199 BGB: el plazo empieza a contar al final del año natural del vuelo.
        inicio = date(fecha_vuelo.year, 12, 31)
    else:
        inicio = fecha_vuelo
    try:
        limite = inicio.replace(year=inicio.year + anos)
    except ValueError:  # 29-feb
        limite = inicio.replace(year=inicio.year + anos, day=28)
    return hoy <= limite


# --- Dictamen -----------------------------------------------------------

@dataclass
class Hechos:
    origen: str
    destino: str
    retraso_llegada_h: float
    causa_categoria: str = "desconocida"
    fecha_vuelo: date | None = None
    pais_reclamacion: str = "ES"
    hubo_reruteo: bool = False   # ¿la aerolínea ofreció OTRO transporte (art. 8)? Ver _aplicar_reduccion
    oferta_aerolinea_eur: float | None = None  # lo que ofreció la aerolínea (bono o efectivo)
    # Art. 3(1)(b): en vuelos que ENTRAN a la UE desde un tercer país, el Reglamento solo
    # aplica si el transportista operador es comunitario. None = dato desconocido -> preguntar.
    transportista_comunitario: bool | None = None


def en_ambito_261(h: "Hechos") -> tuple[bool | None, str, str]:
    """¿Cae el vuelo dentro del ámbito del art. 3(1)?

    Devuelve (en_ambito, motivo, clave_fuente):
      True   -> cubierto
      False  -> fuera de ámbito (motivo explica por qué)
      None   -> falta el dato de transportista para decidir (vuelo entrante de 3.er país)
    clave_fuente es una clave de FUENTES para la traza.
    """
    sale_ue = en_ue(h.origen)
    llega_ue = en_ue(h.destino)

    # (a) Salida desde un aeropuerto de la UE: cubierto con cualquier compañía.
    if sale_ue:
        return True, "", "ambito_a"

    # D6: salida desde Reino Unido -> régimen británico (UK261), fuera de este MVP.
    if pais(h.origen) == "GB":
        return False, (
            "Tu vuelo salía de Reino Unido. Desde el Brexit esos vuelos van por la norma "
            "británica (UK261, importes en libras), no por el 261/2004 europeo. Esta "
            "herramienta solo calcula el europeo."
        ), "ambito_uk"

    # (b) Llegada a la UE desde un tercer país: solo si el transportista operador es comunitario.
    if llega_ue:
        if h.transportista_comunitario is True:
            return True, "", "ambito_b"
        if h.transportista_comunitario is None:
            return None, (
                "Tu vuelo entraba a la UE desde fuera. En esos casos el 261 solo cubre si "
                "quien operaba el vuelo es una compañía europea (art. 3(1)(b)). Dime si lo "
                "era y sigo."
            ), "ambito_b"
        return False, (
            "Entrabas a la UE desde fuera y el vuelo lo operaba una compañía no europea. "
            "Ahí el 261 no llega: para vuelos de entrada solo cubre si la aerolínea tiene "
            "licencia de un país de la UE (art. 3(1)(b))."
        ), "ambito_b"

    return False, (
        "Ni la salida ni la llegada están en la UE, así que el 261 no entra (art. 3)."
    ), "ambito_fuera"


def _paso(out: dict, paso: str, resultado: str, fuente: str) -> None:
    """Añade una fila a la traza estructurada del dictamen."""
    out["traza"].append({"paso": paso, "resultado": resultado, "fuente": fuente})


def evaluar_elegibilidad(h: Hechos, hoy: date | None = None) -> dict:
    dist = distancia_km(h.origen, h.destino)
    intra = vuelo_intracomunitario(h.origen, h.destino)
    base, letra = banda_compensacion(dist, intra)

    out = {
        "distancia_km": round(dist, 1),
        "intracomunitario": intra,
        "importe_base_eur": base,
        "articulo": letra,
        "elegible": False,
        "importe_eur": 0,
        "reduccion_aplica": False,
        "circunstancia_exime": None,
        "sentencia": None,
        "nota_precedente": "",
        "causa_categoria": h.causa_categoria,
        "dentro_plazo": True,
        "plazo_incierto": False,
        "provisional": False,
        "en_ambito": True,
        "falta_dato": None,
        "motivo": "",
        "traza": [],
    }
    # D4: el derecho de asistencia (art. 6/9) depende del retraso EN SALIDA con umbrales por
    # banda; el MVP no recoge la hora de salida, así que no se dictamina aquí. La carta lo
    # menciona cualitativamente.

    # 0) Ámbito de aplicación (art. 3) — antes que nada
    amb, motivo_amb, clave_amb = en_ambito_261(h)
    if amb is None:
        out["en_ambito"] = None
        out["falta_dato"] = "transportista_comunitario"
        out["ambito_clave"] = clave_amb
        out["motivo"] = motivo_amb + " Hay que preguntarlo antes de dictaminar."
        _paso(out, "ámbito (art. 3)", "falta un dato para decidir", cita(clave_amb))
        return out
    if amb is False:
        out["en_ambito"] = False
        out["ambito_clave"] = clave_amb   # la carta redacta su propia prosa formal a partir de esto
        out["motivo"] = motivo_amb
        _paso(out, "ámbito (art. 3)", "fuera de ámbito", cita(clave_amb))
        return out
    _paso(out, "ámbito (art. 3)", "cubierto", cita(clave_amb))

    # 1) Umbral de retraso (Sturgeon)
    if h.retraso_llegada_h < UMBRAL_RETRASO_H:
        out["motivo"] = (
            f"Llegaste {h.retraso_llegada_h:g} h tarde. La compensación empieza a las 3 h "
            f"de retraso en destino (TJUE C-402/07, Sturgeon), así que por debajo de ese "
            f"umbral el art. 7 no te da nada."
        )
        _paso(out, "umbral de retraso", f"{h.retraso_llegada_h:g} h < 3 h → sin derecho", cita("umbral_3h"))
        return out
    _paso(out, "umbral de retraso", f"{h.retraso_llegada_h:g} h ≥ 3 h", cita("umbral_3h"))

    # 2) Plazo para reclamar (lo fija el Derecho nacional — TJUE C-139/11)
    nota_plazo = ""
    pais_r = (h.pais_reclamacion or "").strip().upper()
    if h.fecha_vuelo is not None and not dentro_de_plazo(h.fecha_vuelo, pais_r, hoy):
        anos = PLAZO_ANOS_POR_PAIS.get(pais_r, PLAZO_ANOS_DEFECTO)
        norma = PLAZO_NORMA_POR_PAIS.get(pais_r, "Derecho nacional (no verificado)")
        if pais_r in PLAZO_FIABLE:
            out["dentro_plazo"] = False
            out["motivo"] = (
                f"El vuelo es del {h.fecha_vuelo.isoformat()} y en {pais_r} hay {anos} años "
                f"para reclamar: se te ha pasado el plazo. Lo fija cada país, no el "
                f"Reglamento (TJUE C-139/11)."
            )
            _paso(out, "plazo", f"fuera del plazo de {anos} años en {pais_r}",
                  f"{cita('plazo')} — {norma}")
            return out
        # País sin plazo verificado: NO se descarta la reclamación, se avisa.
        # dentro_plazo=None (no True): "no se sabe", misma convención que en_ambito.
        out["plazo_incierto"] = True
        out["dentro_plazo"] = None
        nota_plazo = (
            f"AVISO: el vuelo es de {h.fecha_vuelo.isoformat()} y el plazo de prescripción "
            f"en {pais_r or 'ese país'} no está verificado (podría rondar los {anos} años). "
            f"Puede estar prescrito; confírmalo con un abogado local antes de presentar la "
            f"reclamación."
        )
        _paso(out, "plazo", f"posible prescripción en {pais_r or 'ese país'} (no verificado)", cita("plazo"))
    elif h.fecha_vuelo is not None:
        _paso(out, "plazo", f"dentro de plazo en {pais_r or 'ES'}", cita("plazo"))

    def _con_nota(texto: str) -> str:
        return (texto + " " + nota_plazo).strip() if nota_plazo else texto

    # 3) Circunstancia extraordinaria (art. 5(3))
    circ = analizar_circunstancia(h.causa_categoria)
    out["sentencia"] = circ["sentencia"]
    out["nota_precedente"] = circ["nota"]
    out["causa_categoria"] = circ["categoria"]
    if circ["exime"] is True:
        out["circunstancia_exime"] = True
        out["motivo"] = _con_nota(
            f"La aerolínea alega «{circ['categoria']}», y eso sí cuenta como circunstancia "
            f"extraordinaria ({circ['sentencia']}): si lo acredita, se libra de pagar el "
            f"art. 7. Ojo, seguir atendiéndote (comida, hotel, art. 6/9) lo debe igual. "
            f"Pídele la prueba por escrito antes de dar la reclamación por perdida. "
            f"{circ['nota']}"
        )
        _paso(out, "circunstancia extraordinaria (art. 5(3))",
              f"«{circ['categoria']}» puede eximir si se acredita", circ["sentencia"])
        return out
    if circ["exime"] is None:
        out["provisional"] = True
        out["circunstancia_exime"] = None
        out["elegible"] = True  # se reclama, pero el dictamen avisa de que es provisional
        importe, reduc = _aplicar_reduccion(base, dist, intra, h)
        out["importe_eur"], out["reduccion_aplica"] = importe, reduc
        out["motivo"] = _con_nota(
            f"La causa que alegan («{circ['categoria']}») no decide por sí sola: "
            f"{circ['nota']} Reclama los {importe} € ({letra}), pero cuenta con que es "
            f"provisional hasta ver la documentación de la aerolínea."
        )
        _paso(out, "circunstancia extraordinaria (art. 5(3))",
              f"«{circ['categoria']}» no concluyente → reclamación provisional", circ["sentencia"])
        _paso(out, "banda de compensación", f"{importe} € ({letra})", cita(_ART_A_CLAVE[letra]))
        if reduc:
            _paso(out, "reducción art. 7(2)", "−50 % (reruteo con retraso limitado)", cita("reduccion"))
        return out
    _paso(out, "circunstancia extraordinaria (art. 5(3))",
          f"«{circ['categoria']}» no exime", circ["sentencia"])

    # 4) Elegible: circ["exime"] is False
    importe, reduc = _aplicar_reduccion(base, dist, intra, h)
    out["elegible"] = True
    out["circunstancia_exime"] = False
    out["importe_eur"] = importe
    out["reduccion_aplica"] = reduc
    nota_reduc = " (reducido un 50 % por el art. 7(2): reruteo con retraso limitado)" if reduc else ""
    nota_circ = ""
    if h.causa_categoria not in (None, "", "desconocida"):
        nota_circ = (
            f" La excusa que dan («{circ['categoria']}») no las libra "
            f"({circ['sentencia']}): {circ['nota']}"
        )
    out["motivo"] = _con_nota(
        f"{h.retraso_llegada_h:g} h de retraso en un vuelo de {round(dist)} km "
        f"{'dentro de la UE' if intra else 'fuera de la UE'}: te corresponden "
        f"{importe} € por el {letra}{nota_reduc}.{nota_circ}"
    )
    if h.oferta_aerolinea_eur is not None and h.oferta_aerolinea_eur < importe:
        out["motivo"] += (
            f" Te ofrecieron {h.oferta_aerolinea_eur:g} €, "
            f"{importe - h.oferta_aerolinea_eur:g} € por debajo de lo que te toca."
        )
    _paso(out, "banda de compensación", f"{importe} € ({letra})", cita(_ART_A_CLAVE[letra]))
    if reduc:
        _paso(out, "reducción art. 7(2)", "−50 % (reruteo con retraso limitado)", cita("reduccion"))
    if h.oferta_aerolinea_eur is not None and h.oferta_aerolinea_eur < importe:
        _paso(out, "oferta de la aerolínea",
              f"{h.oferta_aerolinea_eur:g} € — {importe - h.oferta_aerolinea_eur:g} € por debajo", cita(_ART_A_CLAVE[letra]))
    return out


def _aplicar_reduccion(base: int, dist: float, intra: bool, h: Hechos) -> tuple[int, bool]:
    """Art. 7(2): la compensación se reduce a la mitad si la aerolínea ofreció transporte
    alternativo (reruta bajo el art. 8) y la llegada al destino final no excede el horario
    previsto en más de 2 h / 3 h / 4 h según banda.

    D5: `hubo_reruteo` significa "me pusieron en OTRO vuelo / otro medio", NO "el mismo
    vuelo salió más tarde". Un vuelo simplemente retrasado no es reruta y no activa el
    7(2). El agente debe hacer esa pregunta de forma que distinga los dos casos y solo
    marcar el flag en el primero.

    Con el umbral de elegibilidad en 3 h (Sturgeon), en la práctica esto solo muerde en
    vuelos largos con retraso de entre 3 y 4 h."""
    if h.hubo_reruteo and h.retraso_llegada_h < umbral_reduccion_h(dist, intra):
        return base // 2, True
    return base, False


# --- Autocheck ---------------------------------------------------------

def _demo() -> None:
    from datetime import date as _d

    # MAD-JFK, 4 h de retraso, fallo técnico, aerolínea ofrece bono de 250 €.
    r = evaluar_elegibilidad(Hechos(
        origen="MAD", destino="JFK", retraso_llegada_h=4.0,
        causa_categoria="fallo_tecnico", fecha_vuelo=_d(2025, 6, 1),
        pais_reclamacion="ES", oferta_aerolinea_eur=250,
    ), hoy=_d(2026, 9, 8))
    assert r["distancia_km"] > 3500 and not r["intracomunitario"]
    assert r["articulo"] == "art. 7(1)(c)" and r["importe_eur"] == 600
    assert r["elegible"] and r["circunstancia_exime"] is False
    assert "250" in r["motivo"] and "350" in r["motivo"]
    # traza: pasos en orden, cada uno con fuente citada
    pasos = [p["paso"] for p in r["traza"]]
    assert pasos == ["ámbito (art. 3)", "umbral de retraso", "plazo",
                     "circunstancia extraordinaria (art. 5(3))", "banda de compensación",
                     "oferta de la aerolínea"], pasos
    assert all("verif. 2026-09-08" in p["fuente"] or "C-" in p["fuente"] for p in r["traza"])

    # BCN-MAD (~500 km), 3.5 h, meteorología -> D2: no se concede de oficio, provisional.
    r = evaluar_elegibilidad(Hechos(
        origen="BCN", destino="MAD", retraso_llegada_h=3.5, causa_categoria="meteorologia",
    ))
    assert r["importe_base_eur"] == 250 and r["articulo"] == "art. 7(1)(a)"
    assert r["elegible"] and r["provisional"] and r["circunstancia_exime"] is None
    assert r["importe_eur"] == 250
    assert r["traza"][-1]["paso"] == "banda de compensación"

    # D1: JFK-MAD operado por transportista NO comunitario -> fuera de ámbito (art. 3).
    r = evaluar_elegibilidad(Hechos(
        origen="JFK", destino="MAD", retraso_llegada_h=4.0, causa_categoria="operativo_aerolinea",
        transportista_comunitario=False,
    ))
    assert r["en_ambito"] is False and not r["elegible"] and "art. 3" in r["motivo"]
    assert r["traza"] == [{"paso": "ámbito (art. 3)", "resultado": "fuera de ámbito",
                           "fuente": cita("ambito_b")}]

    # D1: JFK-MAD operado por transportista comunitario -> cubierto, 600 €.
    r = evaluar_elegibilidad(Hechos(
        origen="JFK", destino="MAD", retraso_llegada_h=4.0, causa_categoria="operativo_aerolinea",
        transportista_comunitario=True,
    ))
    assert r["en_ambito"] is True and r["elegible"] and r["importe_eur"] == 600

    # D1: EWR-BCN sin dato de transportista -> falta_dato.
    r = evaluar_elegibilidad(Hechos(
        origen="EWR", destino="BCN", retraso_llegada_h=4.0, causa_categoria="operativo_aerolinea",
    ))
    assert r["en_ambito"] is None and r["falta_dato"] == "transportista_comunitario"

    # D6: salida desde UK -> fuera de ámbito (UK261).
    r = evaluar_elegibilidad(Hechos(
        origen="LHR", destino="JFK", retraso_llegada_h=4.0, causa_categoria="operativo_aerolinea",
    ))
    assert r["en_ambito"] is False and "UK261" in r["motivo"]

    # "asistencia_art9" ya no está en el dictamen (D4).
    r = evaluar_elegibilidad(Hechos(origen="MAD", destino="BCN", retraso_llegada_h=4.0,
                                    causa_categoria="operativo_aerolinea"))
    assert "asistencia_art9" not in r

    # MAD-BER (~1870 km) intracomunitario, 5 h, huelga de personal propio -> 400 €, no exime.
    r = evaluar_elegibilidad(Hechos(
        origen="MAD", destino="BER", retraso_llegada_h=5.0,
        causa_categoria="huelga_personal_propio",
    ))
    assert r["intracomunitario"] and r["importe_eur"] == 400 and r["articulo"] == "art. 7(1)(b)"
    assert r["elegible"] and r["circunstancia_exime"] is False

    # MAD-LPA (~1770 km) pero Canarias es UE -> intracomunitario, banda (b) 400.
    r = evaluar_elegibilidad(Hechos(origen="MAD", destino="LPA", retraso_llegada_h=3.0,
                                    causa_categoria="fallo_tecnico"))
    assert r["intracomunitario"] and r["importe_eur"] == 400

    # Retraso de 2h55 -> por debajo del umbral, no elegible.
    r = evaluar_elegibilidad(Hechos(origen="MAD", destino="JFK", retraso_llegada_h=2.9167,
                                    causa_categoria="fallo_tecnico"))
    assert not r["elegible"] and "Sturgeon" in r["motivo"]

    # Reruteo con llegada 3.5 h tarde en vuelo largo (umbral 4 h) -> 50 %.
    r = evaluar_elegibilidad(Hechos(
        origen="MAD", destino="JFK", retraso_llegada_h=3.5, causa_categoria="fallo_tecnico",
        hubo_reruteo=True,
    ))
    assert r["importe_eur"] == 300 and r["reduccion_aplica"]
    assert any(p["paso"] == "reducción art. 7(2)" for p in r["traza"])

    # Fuera de plazo en España (vuelo de 2019).
    r = evaluar_elegibilidad(Hechos(
        origen="MAD", destino="BCN", retraso_llegada_h=4.0, causa_categoria="fallo_tecnico",
        fecha_vuelo=_d(2019, 1, 1), pais_reclamacion="ES",
    ), hoy=_d(2026, 9, 8))
    assert not r["elegible"] and not r["dentro_plazo"]
    assert r["traza"][-1]["paso"] == "plazo" and "1964" in r["traza"][-1]["fuente"]

    print("reglas.py: OK")


if __name__ == "__main__":
    _demo()
