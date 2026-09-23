#!/usr/bin/env python3
"""Genera los tres datasets sintéticos de la Demo 7 -- ERP, hoja del comercial y
facturación -- con semilla fija, más el ground truth de descuadres esperados
(eval/descuadres_esperados.jsonl). Determinista: misma semilla, mismos datos.

Uso: python3 generar_datos.py
Requiere Postgres arriba (../1/docker-compose.yml) para sembrar facturacion.facturas.
"""
import csv
import json
import os
import random
from datetime import date, timedelta

import psycopg2

SEMILLA = 20260914
N_CLIENTES = 60
N_PEDIDOS = 800
FECHA_REF = date(2026, 9, 14)  # "hoy" dentro del dataset
FECHA_INICIO = FECHA_REF - timedelta(days=365)

# Umbrales que también usará conciliar.py (miércoles). Un solo fichero -- config_conciliacion.json,
# escrito más abajo -- para que la conciliación no incruste sus tolerancias en el código.
CONFIG = {
    "dias_limite_sin_facturar": 30,
    "tolerancia_importe_pct": 0.01,
    "tolerancia_importe_abs": 2.0,
    "dias_desfase_legitimo_max": 29,
}

N_CASOS = {
    "sin_facturar": 8,
    "sin_pedido": 6,
    "importe": 8,
    "duplicado": 5,
    "unidades": 8,
    "desfase_legitimo": 20,
}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
EVAL_DIR = os.path.join(BASE_DIR, "eval")


def _dsn():
    return (f"host={os.environ.get('PGHOST', '127.0.0.1')} port={os.environ.get('PGPORT', '5432')} "
            f"dbname={os.environ.get('PGDATABASE', 'n8n')} user={os.environ.get('PGUSER', 'n8n_user')} "
            f"password={os.environ.get('PGPASSWORD', '')}")


def _fecha_aleatoria(rng):
    dias = rng.randint(0, (FECHA_REF - FECHA_INICIO).days)
    return FECHA_INICIO + timedelta(days=dias)


def generar_pedidos(rng):
    clientes = [f"C{n:02d}" for n in range(1, N_CLIENTES + 1)]
    pedidos = []
    for i in range(1, N_PEDIDOS + 1):
        pedidos.append({
            "pedido_id": f"P{i:05d}",
            "cliente_id": rng.choice(clientes),
            "fecha_pedido": _fecha_aleatoria(rng),
            "importe": round(rng.uniform(80, 4500), 2),
            "unidades": rng.randint(1, 40),
        })
    return pedidos


def asignar_casos(rng, pedidos):
    """Reparte cada pedido en un caso (o 'limpio'). Devuelve dict pedido_id -> caso."""
    antiguos = [p for p in pedidos
                if (FECHA_REF - p["fecha_pedido"]).days >= CONFIG["dias_limite_sin_facturar"] + 5]
    rng.shuffle(antiguos)

    caso_de = {}
    cursor = 0
    for caso in ("sin_facturar", "importe", "duplicado", "desfase_legitimo"):
        n = N_CASOS[caso]
        for p in antiguos[cursor:cursor + n]:
            caso_de[p["pedido_id"]] = caso
        cursor += n

    disponibles = [p for p in pedidos if p["pedido_id"] not in caso_de]
    rng.shuffle(disponibles)
    for p in disponibles[:N_CASOS["unidades"]]:
        caso_de[p["pedido_id"]] = "unidades"

    return caso_de


def generar_comercial(rng, pedidos, caso_de):
    filas = []
    for p in pedidos:
        unidades = p["unidades"]
        if caso_de.get(p["pedido_id"]) == "unidades":
            unidades += rng.choice([-5, -3, -2, 2, 3, 5])
        filas.append({"pedido_id": p["pedido_id"], "unidades_comercial": unidades})
    return filas


def generar_facturas(rng, pedidos, caso_de):
    facturas = []
    n = 1

    def siguiente_id():
        nonlocal n
        fid = f"F{n:06d}"
        n += 1
        return fid

    for p in pedidos:
        caso = caso_de.get(p["pedido_id"])
        antiguedad = (FECHA_REF - p["fecha_pedido"]).days

        if caso == "sin_facturar":
            continue  # el descuadre es precisamente que no hay factura

        if caso == "desfase_legitimo":
            lag = rng.randint(15, CONFIG["dias_desfase_legitimo_max"])
            facturas.append({"factura_id": siguiente_id(), "pedido_id": p["pedido_id"],
                              "fecha_factura": p["fecha_pedido"] + timedelta(days=lag),
                              "importe": p["importe"]})
            continue

        if caso == "importe":
            delta = max(CONFIG["tolerancia_importe_abs"], p["importe"] * CONFIG["tolerancia_importe_pct"])
            delta *= rng.uniform(4, 9) * rng.choice([-1, 1])
            lag = rng.randint(0, 14)
            facturas.append({"factura_id": siguiente_id(), "pedido_id": p["pedido_id"],
                              "fecha_factura": p["fecha_pedido"] + timedelta(days=lag),
                              "importe": round(p["importe"] + delta, 2)})
            continue

        if caso == "duplicado":
            lag = rng.randint(0, 14)
            for _ in range(2):
                facturas.append({"factura_id": siguiente_id(), "pedido_id": p["pedido_id"],
                                  "fecha_factura": p["fecha_pedido"] + timedelta(days=lag),
                                  "importe": p["importe"]})
            continue

        # limpio o 'unidades' (esa discrepancia vive en comercial.csv, no en la factura)
        if antiguedad <= 20:
            continue  # aún no le tocaba: no es un descuadre, sigue sin facturar
        lag = rng.randint(0, 14)
        facturas.append({"factura_id": siguiente_id(), "pedido_id": p["pedido_id"],
                          "fecha_factura": p["fecha_pedido"] + timedelta(days=lag),
                          "importe": p["importe"]})

    # C2: facturas huérfanas, sin pedido en el ERP (rango P9xxxx, no colisiona con P00001..P00800)
    huerfanos = []
    usados = set()
    while len(huerfanos) < N_CASOS["sin_pedido"]:
        pedido_fantasma = f"P9{rng.randint(1000, 9999)}"
        if pedido_fantasma in usados:
            continue
        usados.add(pedido_fantasma)
        huerfanos.append(pedido_fantasma)
        facturas.append({"factura_id": siguiente_id(), "pedido_id": pedido_fantasma,
                          "fecha_factura": _fecha_aleatoria(rng), "importe": round(rng.uniform(80, 4500), 2)})

    return facturas, huerfanos


def aplicar_fealdad(rng, pedidos):
    """Vista 'sucia' que sirve erp_falso.py: nombre de campo de cliente inconsistente,
    fechas en dos formatos, algún null. Los valores no cambian, solo la forma."""
    vista = []
    for p in pedidos:
        item = {"pedido_id": p["pedido_id"], "importe": p["importe"], "unidades": p["unidades"]}

        if rng.random() < 0.5:
            item["cliente_id"] = p["cliente_id"]
        else:
            item["idCliente"] = p["cliente_id"]

        r = rng.random()
        if r < 0.05:
            item["fecha_pedido"] = None
        elif r < 0.30:
            item["fecha_pedido"] = p["fecha_pedido"].strftime("%d/%m/%Y")
        else:
            item["fecha_pedido"] = p["fecha_pedido"].isoformat()

        vista.append(item)
    return vista


def escribir_ground_truth(pedidos, caso_de, huerfanos):
    os.makedirs(EVAL_DIR, exist_ok=True)
    ruta = os.path.join(EVAL_DIR, "descuadres_esperados.jsonl")
    with open(ruta, "w", encoding="utf-8") as f:
        for p in pedidos:
            caso = caso_de.get(p["pedido_id"])
            if caso in ("sin_facturar", "importe", "duplicado", "unidades"):
                f.write(json.dumps({"pedido_id": p["pedido_id"], "tipo": caso, "esperado": True}) + "\n")
            elif caso == "desfase_legitimo":
                f.write(json.dumps({"pedido_id": p["pedido_id"], "tipo": "desfase_legitimo",
                                     "esperado": False}) + "\n")
        for pedido_id in huerfanos:
            f.write(json.dumps({"pedido_id": pedido_id, "tipo": "sin_pedido", "esperado": True}) + "\n")
    return ruta


def sembrar_facturacion(facturas):
    conn = psycopg2.connect(_dsn())
    try:
        with conn.cursor() as cur:
            cur.execute("CREATE SCHEMA IF NOT EXISTS facturacion;")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS facturacion.facturas (
                    factura_id    text PRIMARY KEY,
                    pedido_id     text,
                    fecha_factura date,
                    importe       numeric
                );
            """)
            cur.execute("TRUNCATE facturacion.facturas;")
            cur.executemany(
                "INSERT INTO facturacion.facturas (factura_id, pedido_id, fecha_factura, importe) "
                "VALUES (%(factura_id)s, %(pedido_id)s, %(fecha_factura)s, %(importe)s)",
                facturas,
            )
        conn.commit()
    finally:
        conn.close()


def main():
    rng = random.Random(SEMILLA)
    os.makedirs(DATA_DIR, exist_ok=True)

    pedidos = generar_pedidos(rng)
    caso_de = asignar_casos(rng, pedidos)
    comercial = generar_comercial(rng, pedidos, caso_de)
    facturas, huerfanos = generar_facturas(rng, pedidos, caso_de)
    vista_erp = aplicar_fealdad(rng, pedidos)

    with open(os.path.join(DATA_DIR, "erp_pedidos.json"), "w", encoding="utf-8") as f:
        json.dump(vista_erp, f, ensure_ascii=False, indent=0)

    with open(os.path.join(DATA_DIR, "comercial.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["pedido_id", "unidades_comercial"])
        w.writeheader()
        w.writerows(comercial)

    with open(os.path.join(BASE_DIR, "config_conciliacion.json"), "w", encoding="utf-8") as f:
        json.dump(CONFIG, f, indent=2, ensure_ascii=False)

    sembrar_facturacion([{**f, "fecha_factura": f["fecha_factura"].isoformat()} for f in facturas])
    ruta_gt = escribir_ground_truth(pedidos, caso_de, huerfanos)

    resumen = {}
    for c in caso_de.values():
        resumen[c] = resumen.get(c, 0) + 1
    print(f"{len(pedidos)} pedidos, {len(comercial)} filas comercial, {len(facturas)} facturas")
    print(f"casos: {resumen}")
    print(f"ground truth -> {ruta_gt}")


if __name__ == "__main__":
    main()
