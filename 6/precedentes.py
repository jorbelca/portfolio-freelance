"""Tabla de precedentes del TJUE sobre "circunstancias extraordinarias" (art. 5(3)
del Reglamento 261/2004) y el clasificador de causa.

Verificado el 2026-09-08 contra el texto de cada sentencia en EUR-Lex (CELEX
62007CJ0549, 62014CJ0257, 62017CJ0195, 62020CJ0028, 62015CJ0315, 62016CJ0559,
62011CJ0139, 62007CJ0402) y el texto del Reglamento (CELEX 32004R0261). Los
holdings coinciden con esta tabla. Ver README §6 para el detalle fila por fila.
Caveat residual: `problema_medico_pasajero` NO tiene sentencia directa del TJUE
(C-74/19 trata de un pasajero violento, no de urgencia médica).

Reparto de responsabilidad (igual que aplicar_rubrica en la Demo 5):
  - el modelo SOLO mapea el relato libre a una de CATEGORIAS (clasificar_causa)
  - la decisión "exime / no exime" es este lookup determinista, nunca el modelo

D2 (README §2): esta es una herramienta DEL LADO DEL PASAJERO. No concede de oficio
la excusa de la aerolínea. El art. 5(3) pone la carga de la prueba en el
transportista, así que las alegaciones típicas (meteorología, huelga de ATC,
riesgo de seguridad, restricción administrativa) van marcadas exime=None: se
reclama con carácter provisional y se le exige a la aerolínea la documentación
acreditativa. Solo se afirma exime=False (el pasajero tiene derecho claro) cuando
la jurisprudencia lo tiene asentado en contra de la aerolínea.
"""

# categoria -> (exime: bool | None, sentencia: str, nota: str)
#   exime False -> jurisprudencia asentada: la aerolínea paga. El dictamen lo afirma.
#   exime None  -> alegación de la aerolínea o hecho no resuelto por el MVP ->
#                  reclamación provisional, se exige documentación acreditativa.
#   exime True  -> se reserva para supuestos donde la jurisprudencia es inequívoca y el
#                  hecho es puntual y verificable (decisión ATFM, colisión con ave,
#                  sabotaje, defecto de fábrica comunicado). Aun así, la aerolínea debe
#                  acreditarlo; el dictamen lo señala en el motivo. Usar con cautela.
PRECEDENTES = {
    "fallo_tecnico": (
        False,
        "TJUE C-549/07 (Wallentin-Hermann); C-257/14 (van der Lans)",
        "Un problema técnico surgido en el mantenimiento normal NO es circunstancia "
        "extraordinaria. Excepción: defecto oculto de fábrica comunicado por el "
        "fabricante, o daño por sabotaje/acto de terrorismo.",
    ),
    "defecto_fabrica_oculto": (
        True,
        "TJUE C-257/14 (van der Lans), excepción reconocida expresamente; C-549/07",
        "Defecto de diseño/fabricación oculto revelado por el fabricante o una autoridad "
        "competente: sí exime (van der Lans lo enuncia como excepción expresa, no a "
        "contrario). Requiere prueba documental del fabricante o la autoridad.",
    ),
    "sabotaje": (
        True,
        "TJUE C-549/07 (Wallentin-Hermann); C-257/14 (van der Lans)",
        "Daños a la aeronave por sabotaje o acto de terrorismo: exime (excepción enunciada "
        "expresamente en van der Lans, junto al defecto oculto de fábrica).",
    ),
    "meteorologia": (
        None,  # D2: no se concede de oficio. Carga de la prueba en la aerolínea (art. 5(3)).
        "Reglamento 261/2004, considerando 14",
        "Condiciones meteorológicas incompatibles con la operación PUEDEN ser circunstancia "
        "extraordinaria, pero solo si la aerolínea acredita el nexo causal con ESTE vuelo y "
        "que adoptó medidas razonables. Una herramienta del lado del pasajero no lo da por "
        "hecho: se reclama con carácter provisional y se le exige a la aerolínea la "
        "documentación (informe meteorológico, NOTAM, decisión de cierre).",
    ),
    "huelga_atc": (
        None,  # D2: la categoría PUEDE eximir, pero la carga de probar el nexo es de la aerolínea.
        "TJUE C-28/20 (Airhelp/SAS), §§ 42-43; C-22/11 (Finnair)",
        "Una huelga 'externa' —de controladores aéreos o de personal de aeropuerto— SÍ puede "
        "ser circunstancia extraordinaria (C-28/20 § 42, a diferencia de la huelga del propio "
        "personal). Pero la aerolínea sigue teniendo que acreditar que existió, que afectó a "
        "ESTE vuelo y que tomó todas las medidas razonables (reruta incluida). Provisional "
        "hasta ver esa prueba.",
    ),
    "decision_atc": (
        True,
        "Reglamento 261/2004, art. 5(3) y considerando 15",
        "Decisión de gestión de tráfico aéreo (ATFM) que impone retraso a una "
        "aeronave concreta: exime.",
    ),
    "huelga_personal_propio": (
        False,
        "TJUE C-195/17 (Krüsemann); C-28/20 (Airhelp/SAS)",
        "Huelga del propio personal de la aerolínea (incluida la convocada por "
        "sindicatos por condiciones laborales) es inherente a su actividad: NO exime.",
    ),
    "operativo_aerolinea": (
        False,
        "TJUE C-195/17 (Krüsemann) §§ 40-42; C-28/20 (Airhelp) § 29; C-549/07",
        "Retraso por la organización interna de la aerolínea (rotaciones tardías, "
        "falta de tripulación no por huelga, esperar conexión, overbooking operativo): "
        "la gestión y reorganización de la empresa y las condiciones de trabajo del "
        "personal son parte de su actividad normal (C-195/17 § 40, C-28/20 § 29). NO exime.",
    ),
    "colision_ave": (
        True,
        "TJUE C-315/15 (Pešková y Peška)",
        "Colisión con un ave: exime. Ojo: el tiempo de inspección tras la colisión "
        "solo cuenta si la aerolínea no pudo evitar retrasos con medidas razonables.",
    ),
    "riesgo_seguridad": (
        None,  # D2: acreditado por la aerolínea, no presumido.
        "Reglamento 261/2004, considerando 14",
        "Un riesgo de seguridad (amenaza, pasajero disruptivo que obliga a desviar, cierre "
        "de espacio aéreo por seguridad) PUEDE eximir si la aerolínea lo acredita. "
        "Provisional hasta ver la prueba.",
    ),
    "problema_medico_pasajero": (
        None,  # sin sentencia TJUE directa; jurisprudencia nacional dividida.
        "Sin sentencia directa del TJUE (C-74/19 trata de pasajero VIOLENTO, no urgencia médica)",
        "Un desvío por urgencia médica de un pasajero PUEDE eximir, pero no hay holding del "
        "TJUE sobre este supuesto concreto y hay tribunales nacionales que lo rechazan "
        "(exigen que la circunstancia ponga en peligro a la aeronave). Provisional: la "
        "aerolínea debe acreditar el desvío y que no pudo evitar el retraso.",
    ),
    "restriccion_administrativa": (
        None,  # D2: acreditada por la aerolínea.
        "TJUE C-159/18 (Moens) y C-501/17 (Germanwings); C-12/11 (McDonagh) para cierre de espacio aéreo",
        "Un cierre de pista/aeropuerto o de espacio aéreo por decisión de la autoridad (p. "
        "ej. combustible en pista, erupción volcánica) PUEDE ser circunstancia "
        "extraordinaria si la aerolínea lo acredita. Provisional hasta ver la prueba.",
    ),
    "desconocida": (
        None,
        "—",
        "Causa no identificada o mixta ('tormenta pero también avería'). El MVP no "
        "resuelve el nexo causal: dictamen provisional, a confirmar con la "
        "documentación que entregue la aerolínea.",
    ),
}

# Lista cerrada que se le pasa al modelo en clasificar_causa (día X).
CATEGORIAS = tuple(PRECEDENTES.keys())


def analizar_circunstancia(categoria: str) -> dict:
    """Lookup determinista. Devuelve exime / sentencia / nota / provisional."""
    cat = (categoria or "desconocida").strip().lower()
    if cat not in PRECEDENTES:
        cat = "desconocida"
    exime, sentencia, nota = PRECEDENTES[cat]
    return {
        "categoria": cat,
        "exime": exime,             # True | False | None
        "provisional": exime is None,
        "sentencia": sentencia,
        "nota": nota,
    }
