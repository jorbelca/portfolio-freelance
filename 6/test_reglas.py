"""Tests del motor de reglas EU261. Sin framework: python3 test_reglas.py

Mismo estilo que 5/test_rubrica.py: bloques de asserts, un print por bloque, un
resumen al final. Falla ruidoso.
"""

from datetime import date

from aeropuertos import coords
from precedentes import CATEGORIAS, analizar_circunstancia
from reglas import (
    Hechos,
    banda_compensacion,
    dentro_de_plazo,
    distancia_km,
    evaluar_elegibilidad,
    umbral_reduccion_h,
    vuelo_intracomunitario,
)

_fallos = []


def check(cond, msg):
    if not cond:
        _fallos.append(msg)
        print(f"  FALLO: {msg}")


# --- Bloque 1: distancias (gran círculo, tolerancia ±2 %) ---------------
print("1. distancias")
for a, b, esperado in [
    ("MAD", "BCN", 483),
    ("MAD", "JFK", 5766),
    ("MAD", "BER", 1866),
    ("MAD", "LPA", 1774),
    ("CDG", "FCO", 1105),
    ("LHR", "JFK", 5540),
]:
    d = distancia_km(a, b)
    check(abs(d - esperado) / esperado < 0.02, f"{a}-{b}: {d:.0f} km, esperaba ~{esperado}")
check(abs(distancia_km("MAD", "BCN") - distancia_km("BCN", "MAD")) < 0.01, "distancia asimétrica")

# --- Bloque 2: ámbito territorial / intracomunitario -------------------
print("2. intracomunitario")
check(vuelo_intracomunitario("MAD", "BER"), "MAD-BER debería ser intracomunitario")
check(vuelo_intracomunitario("MAD", "LPA"), "MAD-LPA (Canarias) debería ser intracomunitario")
check(vuelo_intracomunitario("MAD", "KEF"), "MAD-KEF (Islandia/EEE) debería contar como UE")
check(not vuelo_intracomunitario("MAD", "LHR"), "MAD-LHR NO es intracomunitario (UK fuera)")
check(not vuelo_intracomunitario("MAD", "JFK"), "MAD-JFK NO es intracomunitario")

# --- Bloque 3: bandas del art. 7(1) -----------------------------------
print("3. bandas art. 7(1)")
check(banda_compensacion(500, False) == (250, "art. 7(1)(a)"), "500 km -> 250")
check(banda_compensacion(1500, False) == (250, "art. 7(1)(a)"), "1500 km exacto -> 250 (<=)")
check(banda_compensacion(1501, True) == (400, "art. 7(1)(b)"), "1501 intra -> 400")
check(banda_compensacion(3000, False) == (400, "art. 7(1)(b)"), "3000 no-intra -> 400")
check(banda_compensacion(3500, False) == (400, "art. 7(1)(b)"), "3500 exacto no-intra -> 400 (<=)")
check(banda_compensacion(3501, False) == (600, "art. 7(1)(c)"), "3501 no-intra -> 600")
check(banda_compensacion(9000, True) == (400, "art. 7(1)(b)"), "intra larguísimo -> sigue 400")

# --- Bloque 4: reducción del 50 % (art. 7(2)) -------------------------
print("4. reducción art. 7(2)")
check(umbral_reduccion_h(500, False) == 2.0, "umbral corta = 2 h")
check(umbral_reduccion_h(3000, False) == 3.0, "umbral media = 3 h")
check(umbral_reduccion_h(6000, False) == 4.0, "umbral larga = 4 h")
r = evaluar_elegibilidad(Hechos("MAD", "JFK", 3.9, "fallo_tecnico", hubo_reruteo=True))
check(r["importe_eur"] == 300 and r["reduccion_aplica"], "reruteo largo 3.9<4 -> 300")
r = evaluar_elegibilidad(Hechos("MAD", "JFK", 4.0, "fallo_tecnico", hubo_reruteo=True))
check(r["importe_eur"] == 600 and not r["reduccion_aplica"], "reruteo largo 4.0>=4 -> 600 completo")
r = evaluar_elegibilidad(Hechos("MAD", "BCN", 3.5, "operativo_aerolinea", hubo_reruteo=True))
check(r["importe_eur"] == 250 and not r["reduccion_aplica"],
      "reruteo corto: retraso 3.5 ya supera el umbral de 2 h -> sin reducción")

# --- Bloque 5: umbral de retraso (Sturgeon) --------------------------
print("5. umbral 3 h")
check(not evaluar_elegibilidad(Hechos("MAD", "JFK", 2.99, "fallo_tecnico"))["elegible"],
      "2h59 -> no elegible")
check(evaluar_elegibilidad(Hechos("MAD", "JFK", 3.0, "fallo_tecnico"))["elegible"],
      "3h00 exacto -> elegible")

# --- Bloque 6: circunstancias extraordinarias -----------------------
print("6. art. 5(3)")
# D2: solo se afirma exime=True para supuestos puntuales y verificables.
EXIMEN = {"decision_atc", "colision_ave", "sabotaje", "defecto_fabrica_oculto"}
# Alegaciones típicas de la aerolínea -> None (provisional, carga de la prueba en la aerolínea)
PROVISIONAL = {"meteorologia", "huelga_atc", "riesgo_seguridad", "restriccion_administrativa",
               "problema_medico_pasajero", "desconocida"}
NO_EXIMEN = {"fallo_tecnico", "huelga_personal_propio", "operativo_aerolinea"}
for cat in EXIMEN:
    check(analizar_circunstancia(cat)["exime"] is True, f"{cat} debería eximir")
for cat in PROVISIONAL:
    check(analizar_circunstancia(cat)["exime"] is None, f"{cat} -> None (provisional, D2)")
for cat in NO_EXIMEN:
    check(analizar_circunstancia(cat)["exime"] is False, f"{cat} NO debería eximir")
check(analizar_circunstancia("categoria_inventada")["categoria"] == "desconocida",
      "categoría no listada -> desconocida")
check(set(CATEGORIAS) == EXIMEN | PROVISIONAL | NO_EXIMEN,
      "el test no cubre exactamente las CATEGORIAS de precedentes.py")

# fallo técnico no exime -> se paga; y el motivo lo dice citando la sentencia
r = evaluar_elegibilidad(Hechos("MAD", "JFK", 4.0, "fallo_tecnico", oferta_aerolinea_eur=250))
check(r["elegible"] and r["importe_eur"] == 600, "fallo técnico MAD-JFK -> 600 €")
check("Wallentin-Hermann" in r["motivo"], "el motivo debería citar Wallentin-Hermann")
check("350" in r["motivo"], "el motivo debería señalar el déficit de 350 € de la oferta")

# D2: meteorología no concede la excusa de oficio -> provisional, importe completo
r = evaluar_elegibilidad(Hechos("MAD", "LIS", 3.5, "meteorologia"))
check(r["elegible"] and r["provisional"] and r["circunstancia_exime"] is None,
      "meteorología -> reclamación provisional")
check(r["importe_eur"] == r["importe_base_eur"], "provisional reclama el importe completo")

# exime=True -> no elegible, pero el motivo invita a exigir la prueba
r = evaluar_elegibilidad(Hechos("MAD", "JFK", 5.0, "colision_ave"))
check(not r["elegible"] and r["circunstancia_exime"] is True, "colisión con ave -> no elegible")
check("prueba" in r["motivo"].lower() or "acredit" in r["motivo"].lower(),
      "el motivo debería pedir la prueba documental")

# causa desconocida -> provisional pero se reclama
r = evaluar_elegibilidad(Hechos("MAD", "BER", 4.0, "desconocida"))
check(r["elegible"] and r["provisional"] and r["importe_eur"] == 400,
      "desconocida -> reclamación provisional de 400 €")

# --- Bloque 9: ámbito del art. 3 (D1, D6) --------------------------
print("9. ámbito art. 3")
# salida desde la UE: cubierto con cualquier compañía
check(evaluar_elegibilidad(Hechos("MAD", "JFK", 4.0, "operativo_aerolinea"))["en_ambito"] is True,
      "MAD-JFK (salida UE) -> en ámbito")
# entrante de 3.er país con transportista no comunitario -> fuera
r = evaluar_elegibilidad(Hechos("JFK", "MAD", 4.0, "operativo_aerolinea", transportista_comunitario=False))
check(r["en_ambito"] is False and not r["elegible"] and "art. 3" in r["motivo"],
      "JFK-MAD transportista no comunitario -> fuera de ámbito")
# entrante de 3.er país con transportista comunitario -> cubierto
r = evaluar_elegibilidad(Hechos("JFK", "MAD", 4.0, "operativo_aerolinea", transportista_comunitario=True))
check(r["en_ambito"] is True and r["elegible"] and r["importe_eur"] == 600,
      "JFK-MAD transportista comunitario -> 600 €")
# entrante de 3.er país sin dato -> falta_dato, no dictamina
r = evaluar_elegibilidad(Hechos("EWR", "BCN", 4.0, "operativo_aerolinea"))
check(r["en_ambito"] is None and r["falta_dato"] == "transportista_comunitario" and not r["elegible"],
      "EWR-BCN sin transportista -> falta_dato")
# D6: salida desde UK -> fuera, con mención a UK261
r = evaluar_elegibilidad(Hechos("LHR", "JFK", 4.0, "operativo_aerolinea"))
check(r["en_ambito"] is False and "UK261" in r["motivo"], "LHR-JFK -> UK261, fuera de MVP")
# MAD-LHR (salida UE, aunque destino UK) sí está cubierto
check(evaluar_elegibilidad(Hechos("MAD", "LHR", 4.0, "operativo_aerolinea"))["en_ambito"] is True,
      "MAD-LHR (salida UE) -> en ámbito")
# D4: asistencia_art9 ya no está en el dictamen
check("asistencia_art9" not in evaluar_elegibilidad(Hechos("MAD", "BCN", 4.0, "operativo_aerolinea")),
      "asistencia_art9 no debería estar en el dictamen (D4)")

# --- Bloque 7: plazo por país --------------------------------------
print("7. plazo (TJUE C-139/11)")
HOY = date(2026, 9, 8)
check(dentro_de_plazo(date(2022, 1, 1), "ES", HOY), "ES 5 años: vuelo 2022 dentro")
check(not dentro_de_plazo(date(2020, 1, 1), "ES", HOY), "ES 5 años: vuelo 2020 fuera")
check(dentro_de_plazo(date(2021, 3, 1), "GB", HOY), "GB 6 años: vuelo 2021 dentro")
check(not dentro_de_plazo(date(2022, 6, 1), "DE", HOY), "DE 3 años desde fin de año: 2022 fuera")
check(dentro_de_plazo(date(2024, 1, 1), "DE", HOY), "DE 3 años: 2024 dentro")
check(dentro_de_plazo(date(2025, 1, 1), "XX", HOY), "país no listado -> aviso, no descarte")

# G-JURIDICO: fuera del set fiable NO se descarta por prescripción, solo se avisa.
_r = evaluar_elegibilidad(Hechos("MAD", "BCN", 4.0, "operativo_aerolinea",
                                 fecha_vuelo=date(2019, 1, 1), pais_reclamacion="IT"), hoy=HOY)
check(_r["elegible"] and _r["dentro_plazo"] is None, "IT vuelo 2019: sigue elegible, dentro_plazo=None")
check(_r["plazo_incierto"] and "prescri" in _r["motivo"].lower(), "IT: avisa de posible prescripción en el motivo")
_r2 = evaluar_elegibilidad(Hechos("MAD", "BCN", 4.0, "operativo_aerolinea",
                                  fecha_vuelo=date(2019, 1, 1), pais_reclamacion="ES"), hoy=HOY)
check(not _r2["elegible"] and _r2["dentro_plazo"] is False, "ES vuelo 2019: sí se descarta (set fiable)")

# --- Bloque 8: casos frontera del §6 del plan ---------------------
print("8. frontera")
# distancia justo en el límite de banda: se construye un par que dé ~1500
d_bcn_cdg = distancia_km("BCN", "CDG")
check(800 < d_bcn_cdg < 900, f"BCN-CDG sanity {d_bcn_cdg:.0f}")
# retraso 2h55
check(not evaluar_elegibilidad(Hechos("MAD", "JFK", 2 + 55 / 60, "meteorologia"))["elegible"],
      "2h55 -> no elegible aunque la causa no importe ya")

# --- resumen -----------------------------------------------------
print()
if _fallos:
    print(f"FALLdown: {len(_fallos)} fallo(s)")
    raise SystemExit(1)
print("test_reglas.py: TODO OK")
