"""Genera eval/dataset.jsonl — 30 casos EU261 con ground truth hecho a mano.

Determinista: ejecutar produce siempre el mismo fichero byte a byte.

Cada línea:
  id          identificador estable
  relato_es   lo que el usuario le cuenta al agente (lenguaje libre) — lo parsea el modelo
  hechos      hechos estructurados que --sin-llm inyecta para medir SOLO el motor de reglas
  esperado    ground truth (autoría humana, NO derivado del motor)

Distribución (§6 de PLAN-demo6.md, ajustada tras D1/D2 del README):
  8  elegibles claros (bandas a/b/c; 7 sin reducción + 1 con reducción del 7(2) —
     con el umbral de 3 h, el 7(2) solo muerde en vuelo largo con retraso 3-4 h)
  2  no elegibles por circunstancia puntual y verificable (colisión con ave, decisión ATFM)
  4  provisionales por alegación de la aerolínea (D2: meteo, huelga ATC, seguridad, cierre)
  4  elegibles pese a la excusa de la aerolínea  <- casos del vídeo
  4  retraso inferior a 3 h
  3  fuera de plazo
  3  frontera (umbral de 3 h exacto, umbral del 7(2) exacto, distancia junto al límite de banda)
  2  causa desconocida -> reclamación provisional
  3  ámbito del art. 3 (D1/D6: entrante no comunitario, entrante comunitario, sin dato)
"""

import json
import pathlib

# hechos: origen, destino, retraso_llegada_h, causa_categoria, fecha_vuelo (ISO o None),
#         pais_reclamacion, hubo_reruteo, oferta_aerolinea_eur, transportista_comunitario
CASOS = [
    # --- 8 elegibles claros ---------------------------------------------------
    ("c01", "Volé de Madrid a Barcelona y aterrizamos 3 horas y media tarde porque el avión "
            "venía retrasado de antes. Ninguna explicación rara, solo que iban mal de horarios.",
     dict(origen="MAD", destino="BCN", retraso_llegada_h=3.5, causa_categoria="operativo_aerolinea"),
     dict(elegible=True, importe_eur=250, articulo="art. 7(1)(a)", circunstancia_exime=False,
          categoria="operativo_aerolinea", dentro_plazo=True, provisional=False)),

    ("c02", "Barcelona-París, llegamos con 4 horas de retraso. Dijeron que faltaba personal de "
            "tierra y no pudieron preparar el avión a tiempo.",
     dict(origen="BCN", destino="CDG", retraso_llegada_h=4.0, causa_categoria="operativo_aerolinea"),
     dict(elegible=True, importe_eur=250, articulo="art. 7(1)(a)", circunstancia_exime=False,
          categoria="operativo_aerolinea", dentro_plazo=True, provisional=False)),

    ("c03", "Madrid a Berlín con 3 horas y 10 minutos de retraso a la llegada. Problema de "
            "rotación de la tripulación, nos dijeron.",
     dict(origen="MAD", destino="BER", retraso_llegada_h=3.167, causa_categoria="operativo_aerolinea"),
     dict(elegible=True, importe_eur=400, articulo="art. 7(1)(b)", circunstancia_exime=False,
          categoria="operativo_aerolinea", dentro_plazo=True, provisional=False)),

    ("c04", "París-Atenas, 5 horas tarde. La aerolínea decidió esperar a unos pasajeros de "
            "otro vuelo suyo que iban con conexión.",
     dict(origen="CDG", destino="ATH", retraso_llegada_h=5.0, causa_categoria="operativo_aerolinea"),
     dict(elegible=True, importe_eur=400, articulo="art. 7(1)(b)", circunstancia_exime=False,
          categoria="operativo_aerolinea", dentro_plazo=True, provisional=False)),

    ("c05", "Madrid-Nueva York, aterrizamos 4 horas después de lo previsto. Retraso operativo, "
            "sin más detalle.",
     dict(origen="MAD", destino="JFK", retraso_llegada_h=4.0, causa_categoria="operativo_aerolinea"),
     dict(elegible=True, importe_eur=600, articulo="art. 7(1)(c)", circunstancia_exime=False,
          categoria="operativo_aerolinea", dentro_plazo=True, provisional=False)),

    ("c06", "Fráncfort a Nueva York con 6 horas de retraso. La tripulación había excedido su "
            "jornada y tuvieron que buscar otra.",
     dict(origen="FRA", destino="JFK", retraso_llegada_h=6.0, causa_categoria="operativo_aerolinea"),
     dict(elegible=True, importe_eur=600, articulo="art. 7(1)(c)", circunstancia_exime=False,
          categoria="operativo_aerolinea", dentro_plazo=True, provisional=False)),

    ("c07", "Ámsterdam-Barcelona, 3 horas y 20 minutos de retraso a la llegada. El avión llegó "
            "tarde de su vuelo anterior, sin más.",
     dict(origen="AMS", destino="BCN", retraso_llegada_h=3.333, causa_categoria="operativo_aerolinea"),
     dict(elegible=True, importe_eur=250, articulo="art. 7(1)(a)", circunstancia_exime=False,
          categoria="operativo_aerolinea", dentro_plazo=True, provisional=False, reduccion_aplica=False)),

    ("c08", "Madrid-Nueva York. Me reubicaron en un vuelo alternativo y llegué 3 horas y media "
            "después de lo que ponía mi billete. El motivo del cambio fue un lío de rotaciones.",
     dict(origen="MAD", destino="JFK", retraso_llegada_h=3.5, causa_categoria="operativo_aerolinea",
          hubo_reruteo=True),
     dict(elegible=True, importe_eur=300, articulo="art. 7(1)(c)", circunstancia_exime=False,
          categoria="operativo_aerolinea", dentro_plazo=True, provisional=False, reduccion_aplica=True)),

    # --- 2 no elegibles (circunstancia puntual y verificable) + 4 provisionales (D2:
    #     alegación de la aerolínea, carga de la prueba en ella) ----------------------
    ("c09", "Madrid-Lisboa, 3 horas de retraso. La aerolínea dice que fue por una tormenta "
            "enorme que cerró la operativa un buen rato.",
     dict(origen="MAD", destino="LIS", retraso_llegada_h=3.0, causa_categoria="meteorologia"),
     dict(elegible=True, importe_eur=250, articulo="art. 7(1)(a)", circunstancia_exime=None,
          categoria="meteorologia", dentro_plazo=True, provisional=True)),

    ("c10", "Barcelona-Roma con 4 horas de retraso. Nos dijeron que hubo huelga de los "
            "controladores aéreos italianos ese día.",
     dict(origen="BCN", destino="FCO", retraso_llegada_h=4.0, causa_categoria="huelga_atc"),
     dict(elegible=True, importe_eur=250, articulo="art. 7(1)(a)", circunstancia_exime=None,
          categoria="huelga_atc", dentro_plazo=True, provisional=True)),

    ("c11", "Madrid-Nueva York, 5 horas tarde. Un pájaro impactó contra el motor en el "
            "despegue anterior y tuvieron que revisar toda la aeronave.",
     dict(origen="MAD", destino="JFK", retraso_llegada_h=5.0, causa_categoria="colision_ave"),
     dict(elegible=False, importe_eur=0, circunstancia_exime=True, categoria="colision_ave",
          dentro_plazo=True, provisional=False)),

    ("c12", "París-Múnich, 3 horas y media. Dijeron que evacuaron la terminal por una alerta "
            "de seguridad y todo se retrasó.",
     dict(origen="CDG", destino="MUC", retraso_llegada_h=3.5, causa_categoria="riesgo_seguridad"),
     dict(elegible=True, importe_eur=250, articulo="art. 7(1)(a)", circunstancia_exime=None,
          categoria="riesgo_seguridad", dentro_plazo=True, provisional=True)),

    ("c13", "Ámsterdam-Madrid con 4 horas de retraso. Control de tráfico aéreo impuso una "
            "ranura de salida mucho más tarde por congestión.",
     dict(origen="AMS", destino="MAD", retraso_llegada_h=4.0, causa_categoria="decision_atc"),
     dict(elegible=False, importe_eur=0, circunstancia_exime=True, categoria="decision_atc",
          dentro_plazo=True, provisional=False)),

    ("c14", "Madrid-París, 6 horas de retraso. La aerolínea alega que la autoridad cerró una "
            "de las pistas por un incidente y solo operaba una.",
     dict(origen="MAD", destino="CDG", retraso_llegada_h=6.0, causa_categoria="restriccion_administrativa"),
     dict(elegible=True, importe_eur=250, articulo="art. 7(1)(a)", circunstancia_exime=None,
          categoria="restriccion_administrativa", dentro_plazo=True, provisional=True)),

    # --- 4 elegibles pese a la excusa de la aerolínea (vídeo) ---------------
    ("c15", "Madrid-Nueva York, 4 horas de retraso. Me dijeron que fue un problema técnico del "
            "avión y me ofrecieron un bono de 250 euros.",
     dict(origen="MAD", destino="JFK", retraso_llegada_h=4.0, causa_categoria="fallo_tecnico",
          oferta_aerolinea_eur=250),
     dict(elegible=True, importe_eur=600, articulo="art. 7(1)(c)", circunstancia_exime=False,
          categoria="fallo_tecnico", dentro_plazo=True, provisional=False)),

    ("c16", "Barcelona-Madrid con 3 horas y media de retraso por una avería que detectaron en "
            "el mantenimiento rutinario.",
     dict(origen="BCN", destino="MAD", retraso_llegada_h=3.5, causa_categoria="fallo_tecnico"),
     dict(elegible=True, importe_eur=250, articulo="art. 7(1)(a)", circunstancia_exime=False,
          categoria="fallo_tecnico", dentro_plazo=True, provisional=False)),

    ("c17", "Madrid-Berlín, 5 horas tarde por una huelga de los pilotos de la propia "
            "compañía por sus condiciones laborales.",
     dict(origen="MAD", destino="BER", retraso_llegada_h=5.0, causa_categoria="huelga_personal_propio"),
     dict(elegible=True, importe_eur=400, articulo="art. 7(1)(b)", circunstancia_exime=False,
          categoria="huelga_personal_propio", dentro_plazo=True, provisional=False)),

    ("c18", "Fráncfort-Nueva York, 7 horas de retraso por huelga del personal de cabina de la "
            "aerolínea. Me ofrecieron un vale de 400 euros para futuros vuelos.",
     dict(origen="FRA", destino="JFK", retraso_llegada_h=7.0, causa_categoria="huelga_personal_propio",
          oferta_aerolinea_eur=400),
     dict(elegible=True, importe_eur=600, articulo="art. 7(1)(c)", circunstancia_exime=False,
          categoria="huelga_personal_propio", dentro_plazo=True, provisional=False)),

    # --- 4 retraso inferior a 3 h -----------------------------------------
    ("c19", "Madrid-Nueva York, llegué 2 horas y 55 minutos tarde. Dijeron que fue un fallo "
            "técnico.",
     dict(origen="MAD", destino="JFK", retraso_llegada_h=2.9167, causa_categoria="fallo_tecnico"),
     dict(elegible=False, importe_eur=0, categoria="fallo_tecnico", dentro_plazo=True, provisional=False)),

    ("c20", "Madrid-Barcelona con una hora de retraso por congestión en el aeropuerto.",
     dict(origen="MAD", destino="BCN", retraso_llegada_h=1.0, causa_categoria="operativo_aerolinea"),
     dict(elegible=False, importe_eur=0, categoria="operativo_aerolinea", dentro_plazo=True,
          provisional=False)),

    ("c21", "París-Roma, 2 horas y media de retraso. Nada especial, solo que salimos tarde.",
     dict(origen="CDG", destino="FCO", retraso_llegada_h=2.5, causa_categoria="operativo_aerolinea"),
     dict(elegible=False, importe_eur=0, categoria="operativo_aerolinea", dentro_plazo=True,
          provisional=False)),

    ("c22", "Madrid-Londres, 2 horas y 59 minutos tarde por mal tiempo.",
     dict(origen="MAD", destino="LHR", retraso_llegada_h=2.983, causa_categoria="meteorologia"),
     dict(elegible=False, importe_eur=0, categoria="meteorologia", dentro_plazo=True, provisional=False)),

    # --- 3 fuera de plazo ----------------------------------------------
    ("c23", "Madrid-Barcelona en enero de 2019, 4 horas de retraso operativo. Reclamo desde "
            "España ahora.",
     dict(origen="MAD", destino="BCN", retraso_llegada_h=4.0, causa_categoria="operativo_aerolinea",
          fecha_vuelo="2019-01-15", pais_reclamacion="ES"),
     dict(elegible=False, importe_eur=0, categoria="operativo_aerolinea", dentro_plazo=False,
          provisional=False)),

    ("c24", "París-Nueva York en marzo de 2019, 4 horas tarde por un lío de tripulación. "
            "Reclamo en Francia ahora.",
     dict(origen="CDG", destino="JFK", retraso_llegada_h=4.0, causa_categoria="operativo_aerolinea",
          fecha_vuelo="2019-03-10", pais_reclamacion="FR"),
     dict(elegible=False, importe_eur=0, categoria="operativo_aerolinea", dentro_plazo=False,
          provisional=False)),

    ("c25", "Fráncfort-Múnich en marzo de 2022, 4 horas de retraso operativo. Reclamo en "
            "Alemania.",
     dict(origen="FRA", destino="MUC", retraso_llegada_h=4.0, causa_categoria="operativo_aerolinea",
          fecha_vuelo="2022-03-01", pais_reclamacion="DE"),
     dict(elegible=False, importe_eur=0, categoria="operativo_aerolinea", dentro_plazo=False,
          provisional=False)),

    # --- 3 frontera --------------------------------------------------
    ("c26", "Madrid-Nueva York, exactamente 3 horas de retraso a la llegada. Retraso operativo.",
     dict(origen="MAD", destino="JFK", retraso_llegada_h=3.0, causa_categoria="operativo_aerolinea"),
     dict(elegible=True, importe_eur=600, articulo="art. 7(1)(c)", circunstancia_exime=False,
          categoria="operativo_aerolinea", dentro_plazo=True, provisional=False)),

    ("c27", "Madrid-Nueva York. Me reubicaron y llegué justo 4 horas después de mi horario "
            "previsto. El cambio fue por un problema de organización de la aerolínea.",
     dict(origen="MAD", destino="JFK", retraso_llegada_h=4.0, causa_categoria="operativo_aerolinea",
          hubo_reruteo=True),
     dict(elegible=True, importe_eur=600, articulo="art. 7(1)(c)", circunstancia_exime=False,
          categoria="operativo_aerolinea", dentro_plazo=True, provisional=False, reduccion_aplica=False)),

    ("c28", "Madrid-Múnich (poco menos de 1500 km), 4 horas de retraso operativo.",
     dict(origen="MAD", destino="MUC", retraso_llegada_h=4.0, causa_categoria="operativo_aerolinea"),
     dict(elegible=True, importe_eur=250, articulo="art. 7(1)(a)", circunstancia_exime=False,
          categoria="operativo_aerolinea", dentro_plazo=True, provisional=False)),

    # --- 2 causa desconocida -> provisional ---------------------------
    ("c29", "Madrid-Berlín, 4 horas tarde. Primero dijeron que había una tormenta y luego que "
            "también tenían una avería. No quedó claro qué fue.",
     dict(origen="MAD", destino="BER", retraso_llegada_h=4.0, causa_categoria="desconocida"),
     dict(elegible=True, importe_eur=400, articulo="art. 7(1)(b)", circunstancia_exime=None,
          categoria="desconocida", dentro_plazo=True, provisional=True)),

    ("c30", "Madrid-Nueva York, 5 horas de retraso y nadie del personal supo decirme el "
            "motivo.",
     dict(origen="MAD", destino="JFK", retraso_llegada_h=5.0, causa_categoria="desconocida"),
     dict(elegible=True, importe_eur=600, articulo="art. 7(1)(c)", circunstancia_exime=None,
          categoria="desconocida", dentro_plazo=True, provisional=True)),

    # --- 3 ámbito del art. 3 (D1, D6) --------------------------------
    ("c31", "Nueva York-Madrid, 4 horas de retraso operativo. El vuelo lo operaba Delta.",
     dict(origen="JFK", destino="MAD", retraso_llegada_h=4.0, causa_categoria="operativo_aerolinea",
          transportista_comunitario=False),
     dict(elegible=False, importe_eur=0, categoria="operativo_aerolinea", dentro_plazo=True,
          provisional=False, en_ambito=False)),

    ("c32", "Nueva York-Madrid, 4 horas de retraso operativo. El vuelo lo operaba Iberia.",
     dict(origen="JFK", destino="MAD", retraso_llegada_h=4.0, causa_categoria="operativo_aerolinea",
          transportista_comunitario=True),
     dict(elegible=True, importe_eur=600, articulo="art. 7(1)(c)", circunstancia_exime=False,
          categoria="operativo_aerolinea", dentro_plazo=True, provisional=False, en_ambito=True)),

    ("c33", "Newark-Barcelona, 4 horas de retraso operativo. No sé qué compañía operaba "
            "realmente el avión, el billete lo compré por una agencia.",
     dict(origen="EWR", destino="BCN", retraso_llegada_h=4.0, causa_categoria="operativo_aerolinea"),
     dict(elegible=False, importe_eur=0, categoria="operativo_aerolinea", dentro_plazo=True,
          provisional=False, en_ambito=None, falta_dato="transportista_comunitario")),
]


def main() -> None:
    out = pathlib.Path(__file__).parent / "dataset.jsonl"
    with out.open("w", encoding="utf-8") as f:
        for cid, relato, hechos, esperado in CASOS:
            rec = {"id": cid, "relato_es": " ".join(relato.split()),
                   "hechos": hechos, "esperado": esperado}
            f.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
    assert len(CASOS) == 33, f"esperaba 33 casos, hay {len(CASOS)}"
    assert len({c[0] for c in CASOS}) == 33, "ids duplicados"
    print(f"escrito {out} ({len(CASOS)} casos)")


if __name__ == "__main__":
    main()
