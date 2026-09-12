"""Tests de la redacción (carta.py). Cierra D3: un dictamen provisional NUNCA
produce una exigencia de pago firme. python3 test_carta.py
"""

from carta import EXIGENCIA_FIRME, clasificar_plantilla, construir_carta, redactar_reclamacion
from reglas import Hechos, evaluar_elegibilidad

_fallos = []


def check(cond, msg):
    if not cond:
        _fallos.append(msg)
        print(f"  FALLO: {msg}")


def dictamen(**hechos):
    return evaluar_elegibilidad(Hechos(**hechos))


HECHOS = dict(origen="MAD", destino="JFK", retraso_llegada_h=4.0, fecha_vuelo=None,
              causa_texto="problema técnico", oferta_aerolinea_eur=250)

# --- 1: selección de plantilla ------------------------------------------
print("1. clasificar_plantilla")
check(clasificar_plantilla(dictamen(origen="MAD", destino="JFK", retraso_llegada_h=4.0,
      causa_categoria="fallo_tecnico")) == "firme", "fallo técnico -> firme")
check(clasificar_plantilla(dictamen(origen="MAD", destino="LIS", retraso_llegada_h=3.5,
      causa_categoria="meteorologia")) == "provisional", "meteo -> provisional")
check(clasificar_plantilla(dictamen(origen="MAD", destino="JFK", retraso_llegada_h=2.0,
      causa_categoria="fallo_tecnico")) == "sin_derecho", "2 h -> sin_derecho")
check(clasificar_plantilla(dictamen(origen="MAD", destino="JFK", retraso_llegada_h=5.0,
      causa_categoria="colision_ave")) == "sin_derecho", "ave (exime) -> sin_derecho")
check(clasificar_plantilla(dictamen(origen="JFK", destino="MAD", retraso_llegada_h=4.0,
      causa_categoria="operativo_aerolinea", transportista_comunitario=False))
      == "fuera_ambito", "entrante no comunitario -> fuera_ambito")
check(clasificar_plantilla(dictamen(origen="EWR", destino="BCN", retraso_llegada_h=4.0,
      causa_categoria="operativo_aerolinea")) == "falta_dato", "sin transportista -> falta_dato")

# --- 2: D3 — provisional nunca exige pago firme -----------------------
print("2. D3: provisional")
for cat in ("meteorologia", "huelga_atc", "riesgo_seguridad", "restriccion_administrativa",
            "desconocida"):
    d = dictamen(origen="MAD", destino="BER", retraso_llegada_h=4.0, causa_categoria=cat)
    c = construir_carta(d, dict(HECHOS, destino="BER"))
    check(c["tipo"] == "provisional", f"{cat}: tipo provisional")
    check(EXIGENCIA_FIRME not in c["texto"], f"{cat}: SIN exigencia de pago firme")
    check("Mientras no quede acreditada una circunstancia extraordinaria" in c["texto"],
          f"{cat}: pide acreditación primero")
    check("400 €" in c["texto"], f"{cat}: menciona el importe que correspondería")

# --- 3: firme sí exige, con importe correcto -------------------------
print("3. firme")
d = dictamen(origen="MAD", destino="JFK", retraso_llegada_h=4.0, causa_categoria="fallo_tecnico")
c = construir_carta(d, HECHOS)
check(c["tipo"] == "firme" and EXIGENCIA_FIRME in c["texto"], "firme exige el abono")
check("600 €" in c["texto"], "firme: importe 600 €")
check("No acepto la oferta de 250" in c["texto"], "firme: rechaza la oferta a la baja")
check("600" in c["texto"] and c["texto"].count("€ en efectivo") >= 1, "firme: efectivo, no bonos")

# --- 4: fuera de ámbito / falta de dato — sin línea de petición ------
print("4. fuera_ambito / falta_dato")
d = dictamen(origen="JFK", destino="MAD", retraso_llegada_h=4.0,
             causa_categoria="operativo_aerolinea", transportista_comunitario=False)
c = construir_carta(d, dict(HECHOS, origen="JFK", destino="MAD"))
check(c["tipo"] == "fuera_ambito" and EXIGENCIA_FIRME not in c["texto"], "fuera_ambito: sin exigencia")
check("art. 3" in c["texto"], "fuera_ambito: explica el art. 3")

d = dictamen(origen="EWR", destino="BCN", retraso_llegada_h=4.0, causa_categoria="operativo_aerolinea")
c = construir_carta(d, dict(HECHOS, origen="EWR", destino="BCN"))
check(c["tipo"] == "falta_dato" and "transportista comunitario" in c["texto"],
      "falta_dato: nombra el dato que falta")

# --- 5: sin_derecho — informativa, sin exigencia --------------------
print("5. sin_derecho")
d = dictamen(origen="MAD", destino="JFK", retraso_llegada_h=2.5, causa_categoria="fallo_tecnico")
c = construir_carta(d, HECHOS)
check(c["tipo"] == "sin_derecho" and EXIGENCIA_FIRME not in c["texto"], "sin_derecho: sin exigencia")
check("artículos 6 y 9" in c["texto"], "sin_derecho: recuerda el deber de asistencia")

# --- 5b: plazo incierto (G-JURIDICO) — routing intacto, sin armar a la aerolínea ---
print("5b. plazo incierto")
from datetime import date as _date
d = evaluar_elegibilidad(Hechos("MAD", "BCN", 4.0, "operativo_aerolinea",
                                fecha_vuelo=_date(2019, 1, 1), pais_reclamacion="IT"),
                         hoy=_date(2026, 9, 8))
check(d["plazo_incierto"] and d["elegible"] and d["dentro_plazo"] is None,
      "IT 2019: elegible, dentro_plazo=None, con aviso de prescripción")
c = construir_carta(d, dict(HECHOS, origen="MAD", destino="BCN"))
check(c["tipo"] == "firme" and EXIGENCIA_FIRME in c["texto"],
      "plazo incierto: la plantilla sigue siendo firme (no provisional)")
check("prescri" not in c["texto"].lower() and "verificado" not in c["texto"].lower(),
      "plazo incierto: la carta a la aerolínea NO menciona la posible prescripción")

# --- 6: redactar_reclamacion sin modelo (texto mínimo) -------------
print("6. redactar_reclamacion sin modelo")
d = dictamen(origen="MAD", destino="JFK", retraso_llegada_h=4.0, causa_categoria="fallo_tecnico")
c = redactar_reclamacion(d, HECHOS, usar_modelo=False)
check(c["tipo"] == "firme" and "600 €" in c["texto"], "sin modelo: carta firme coherente")

print()
if _fallos:
    print(f"{len(_fallos)} fallo(s)")
    raise SystemExit(1)
print("test_carta.py: TODO OK")
