"""Coordenadas de aeropuertos (lat, lon en grados decimales) y país.

Subconjunto curado de OpenFlights: solo los aeropuertos que necesita el dataset
de prueba (§6 de PLAN-demo6.md). Ampliar cuando el dataset crezca; cargar los
7000+ de OpenFlights entero sería peso muerto para una demo.

ponytail: dict embebido en vez de CSV parseado. Si esto pasa de ~80 entradas,
migrar a data/aeropuertos.csv.
"""

# iata: (lat, lon, iso_pais, en_ue)  -- en_ue segun Reglamento 261/2004
#   Incluye Islandia, Noruega, Suiza (aplican el Reglamento por acuerdos) y
#   los territorios ultraperifericos (Canarias, Madeira, Azores, DOM franceses).
AEROPUERTOS = {
    # --- España ---
    "MAD": (40.4936, -3.5668, "ES", True),
    "BCN": (41.2971, 2.0785, "ES", True),
    "AGP": (36.6749, -4.4991, "ES", True),
    "VLC": (39.4893, -0.4816, "ES", True),
    "SVQ": (37.4180, -5.8931, "ES", True),
    "PMI": (39.5517, 2.7388, "ES", True),
    "ALC": (38.2822, -0.5582, "ES", True),
    "LPA": (27.9319, -15.3866, "ES", True),   # Gran Canaria
    "TFN": (28.4827, -16.3415, "ES", True),   # Tenerife Norte
    "IBZ": (38.8729, 1.3731, "ES", True),
    # --- Resto UE / EEE ---
    "CDG": (49.0097, 2.5479, "FR", True),
    "ORY": (48.7233, 2.3794, "FR", True),
    "NCE": (43.6584, 7.2159, "FR", True),
    "FRA": (50.0379, 8.5622, "DE", True),
    "MUC": (48.3538, 11.7861, "DE", True),
    "BER": (52.3667, 13.5033, "DE", True),
    "TXL": (52.5597, 13.2877, "DE", True),
    "AMS": (52.3105, 4.7683, "NL", True),
    "BRU": (50.9014, 4.4844, "BE", True),
    "LIS": (38.7742, -9.1342, "PT", True),
    "OPO": (41.2481, -8.6814, "PT", True),
    "FNC": (32.6979, -16.7745, "PT", True),   # Madeira
    "FCO": (41.8003, 12.2389, "IT", True),
    "MXP": (45.6306, 8.7281, "IT", True),
    "LIN": (45.4451, 9.2767, "IT", True),
    "ATH": (37.9364, 23.9445, "GR", True),
    "VIE": (48.1103, 16.5697, "AT", True),
    "CPH": (55.6180, 12.6508, "DK", True),
    "ARN": (59.6519, 17.9186, "SE", True),
    "HEL": (60.3172, 24.9633, "FI", True),
    "DUB": (53.4213, -6.2701, "IE", True),
    "WAW": (52.1657, 20.9671, "PL", True),
    "PRG": (50.1008, 14.2600, "CZ", True),
    "OSL": (60.1939, 11.1004, "NO", True),
    "KEF": (63.9850, -22.6056, "IS", True),
    "ZRH": (47.4647, 8.5492, "CH", True),
    "GVA": (46.2381, 6.1090, "CH", True),
    # --- Reino Unido (ya fuera de la UE; el Reglamento aplica a salidas desde UE
    #     o a llegadas a UE con transportista comunitario) ---
    "LHR": (51.4700, -0.4543, "GB", False),
    "LGW": (51.1537, -0.1821, "GB", False),
    "STN": (51.8850, 0.2350, "GB", False),
    "MAN": (53.3537, -2.2750, "GB", False),
    "EDI": (55.9500, -3.3725, "GB", False),
    # --- Fuera del EEE (destinos de larga distancia habituales) ---
    "JFK": (40.6413, -73.7781, "US", False),
    "EWR": (40.6895, -74.1745, "US", False),
    "MIA": (25.7959, -80.2870, "US", False),
    "LAX": (33.9416, -118.4085, "US", False),
    "ORD": (41.9742, -87.9073, "US", False),
    "YYZ": (43.6777, -79.6248, "CA", False),
    "GRU": (-23.4356, -46.4731, "BR", False),
    "EZE": (-34.8222, -58.5358, "AR", False),
    "MEX": (19.4363, -99.0721, "MX", False),
    "DXB": (25.2532, 55.3657, "AE", False),
    "DOH": (25.2731, 51.6081, "QA", False),
    "BKK": (13.6900, 100.7501, "TH", False),
    "HKG": (22.3080, 113.9185, "HK", False),
    "NRT": (35.7720, 140.3929, "JP", False),
    "PEK": (40.0799, 116.6031, "CN", False),
    "SIN": (1.3644, 103.9915, "SG", False),
    "JNB": (-26.1392, 28.2460, "ZA", False),
    "CMN": (33.3675, -7.5899, "MA", False),
    "CUN": (21.0365, -86.8771, "MX", False),
    "PUJ": (18.5674, -68.3634, "DO", False),
    "DEL": (28.5562, 77.1000, "IN", False),
    "IST": (41.2753, 28.7519, "TR", False),
}


def coords(iata: str) -> tuple[float, float]:
    iata = iata.strip().upper()
    if iata not in AEROPUERTOS:
        raise KeyError(f"aeropuerto no conocido: {iata!r} (añádelo a aeropuertos.py)")
    lat, lon, _pais, _ue = AEROPUERTOS[iata]
    return lat, lon


def en_ue(iata: str) -> bool:
    """True si el aeropuerto está en el ámbito territorial del Reglamento 261/2004."""
    return AEROPUERTOS[iata.strip().upper()][3]


def pais(iata: str) -> str:
    return AEROPUERTOS[iata.strip().upper()][2]
