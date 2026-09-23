#!/usr/bin/env python3
"""Conciliación entre las tres fuentes de bi_staging -- 100% SQL determinista, el LLM
no entra aquí. Aplica C1-C5 y escribe cada descuadre en bi_staging.descuadres.

C6 (desfase contable legítimo) no es una regla que "apague" otra: simplemente ninguna
de las reglas de abajo mira cuánto tarda una factura en llegar, solo si falta del todo
pasado el plazo (C1). Por eso una factura tardía pero dentro de plazo no aparece nunca
-- no hace falta una excepción explícita para no gritar cuando no hay nada que gritar.

Uso: python3 conciliar.py [--verificar]   (--verificar compara contra eval/descuadres_esperados.jsonl)
"""
import argparse
import json
import os

import psycopg2

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config_conciliacion.json")
GROUND_TRUTH_FILE = os.path.join(BASE_DIR, "eval", "descuadres_esperados.jsonl")


def _dsn():
    return (f"host={os.environ.get('PGHOST', '127.0.0.1')} port={os.environ.get('PGPORT', '5432')} "
            f"dbname={os.environ.get('PGDATABASE', 'n8n')} user={os.environ.get('PGUSER', 'n8n_user')} "
            f"password={os.environ.get('PGPASSWORD', '')}")


def _config():
    with open(CONFIG_FILE, encoding="utf-8") as f:
        return json.load(f)


DDL = """
CREATE TABLE IF NOT EXISTS bi_staging.descuadres (
    id            serial PRIMARY KEY,
    pedido_id     text NOT NULL,
    tipo          text NOT NULL,
    detalle       text,
    detectado_en  timestamptz DEFAULT now()
);
"""

# Cada regla es una consulta autocontenida. Las tolerancias llegan por parámetro
# (%(nombre)s), cargadas de config_conciliacion.json -- nunca incrustadas aquí, para
# que el comprador pueda discutirlas sin tocar código (§4 del plan).

SQL_C1_SIN_FACTURAR = """
SELECT p.pedido_id,
       format('pedido de %%s€ del %%s, sin factura %%s días después',
              p.importe, p.fecha_pedido, CURRENT_DATE - p.fecha_pedido) AS detalle
FROM bi_staging.pedidos p
WHERE NOT EXISTS (SELECT 1 FROM bi_staging.facturas f WHERE f.pedido_id = p.pedido_id)
  AND CURRENT_DATE - p.fecha_pedido > %(dias_limite_sin_facturar)s
"""

SQL_C2_SIN_PEDIDO = """
SELECT f.pedido_id,
       format('factura %%s de %%s€ del %%s sin pedido en el ERP',
              f.factura_id, f.importe_factura, f.fecha_factura) AS detalle
FROM bi_staging.facturas f
WHERE NOT EXISTS (SELECT 1 FROM bi_staging.pedidos p WHERE p.pedido_id = f.pedido_id)
"""

SQL_C3_IMPORTE = """
SELECT p.pedido_id,
       format('ERP: %%s€, factura %%s: %%s€ (diff %%s€)',
              p.importe, f.factura_id, f.importe_factura, round(f.importe_factura - p.importe, 2)) AS detalle
FROM bi_staging.pedidos p
JOIN bi_staging.facturas f ON f.pedido_id = p.pedido_id
WHERE abs(p.importe - f.importe_factura) > GREATEST(%(tolerancia_importe_abs)s,
                                                      p.importe * %(tolerancia_importe_pct)s)
  AND (SELECT count(*) FROM bi_staging.facturas f2 WHERE f2.pedido_id = p.pedido_id) = 1
"""

SQL_C4_DUPLICADO = """
SELECT f.pedido_id,
       format('%%s facturas para el mismo pedido: %%s', count(*), string_agg(f.factura_id, ', ')) AS detalle
FROM bi_staging.facturas f
GROUP BY f.pedido_id
HAVING count(*) > 1
"""

SQL_C5_UNIDADES = """
SELECT p.pedido_id,
       format('ERP: %%s ud., comercial: %%s ud.', p.unidades, c.unidades_comercial) AS detalle
FROM bi_staging.pedidos p
JOIN bi_staging.comercial c ON c.pedido_id = p.pedido_id
WHERE p.unidades != c.unidades_comercial
"""

REGLAS = [
    ("sin_facturar", SQL_C1_SIN_FACTURAR),
    ("sin_pedido", SQL_C2_SIN_PEDIDO),
    ("importe", SQL_C3_IMPORTE),
    ("duplicado", SQL_C4_DUPLICADO),
    ("unidades", SQL_C5_UNIDADES),
]


def conciliar(conn, config):
    with conn.cursor() as cur:
        cur.execute(DDL)
        cur.execute("TRUNCATE bi_staging.descuadres;")
        resumen = {}
        for tipo, sql in REGLAS:
            cur.execute(sql, config)
            filas = cur.fetchall()
            for pedido_id, detalle in filas:
                cur.execute(
                    "INSERT INTO bi_staging.descuadres (pedido_id, tipo, detalle) VALUES (%s, %s, %s)",
                    (pedido_id, tipo, detalle),
                )
            resumen[tipo] = len(filas)
    conn.commit()
    return resumen


def verificar(conn):
    """Compara bi_staging.descuadres contra eval/descuadres_esperados.jsonl. Un único
    check ejecutable, sin framework: falla con AssertionError si algo no cuadra."""
    esperados = []
    with open(GROUND_TRUTH_FILE, encoding="utf-8") as f:
        for linea in f:
            esperados.append(json.loads(linea))

    positivos_esperados = {(e["pedido_id"], e["tipo"]) for e in esperados if e["esperado"]}
    negativos_esperados = {e["pedido_id"] for e in esperados if not e["esperado"]}

    with conn.cursor() as cur:
        cur.execute("SELECT pedido_id, tipo FROM bi_staging.descuadres")
        detectados = set(cur.fetchall())

    faltan = positivos_esperados - detectados
    falsos_en_c6 = {(pid, tipo) for pid, tipo in detectados if pid in negativos_esperados}
    ruido = detectados - positivos_esperados - falsos_en_c6

    print(f"Esperados (deben detectarse): {len(positivos_esperados)}")
    print(f"Negativos (NO deben detectarse -- desfase legítimo, C6): {len(negativos_esperados)}")
    print(f"Detectados en total: {len(detectados)}")
    if faltan:
        print(f"FALTAN ({len(faltan)}): {sorted(faltan)}")
    if falsos_en_c6:
        print(f"FALSOS POSITIVOS en casos legítimos C6 ({len(falsos_en_c6)}): {sorted(falsos_en_c6)}")
    if ruido:
        print(f"No esperados ni en negativos ({len(ruido)}): {sorted(ruido)}")

    assert not faltan, f"el motor no detectó {len(faltan)} descuadres esperados"
    assert not falsos_en_c6, f"el motor marcó {len(falsos_en_c6)} casos de desfase legítimo (C6)"
    assert not ruido, f"el motor marcó {len(ruido)} pedidos fuera del ground truth"
    print("OK: coincide exacto con el ground truth (positivos y negativos).")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verificar", action="store_true", help="compara contra eval/descuadres_esperados.jsonl")
    args = ap.parse_args()

    config = _config()
    conn = psycopg2.connect(_dsn())
    try:
        resumen = conciliar(conn, config)
        print(f"{sum(resumen.values())} descuadres -> bi_staging.descuadres")
        for tipo, n in resumen.items():
            print(f"  {tipo}: {n}")
        if args.verificar:
            print()
            verificar(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
