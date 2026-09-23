#!/usr/bin/env python3
"""Ingesta de las tres fuentes de la Demo 7 (ERP, comercial, facturación) hacia
bi_staging en Postgres. Absorbe aquí la fealdad del ERP -- paginación, 429/backoff,
nombres de campo y formatos de fecha -- para que Power Query solo lea una tabla limpia.

Idempotente: upsert por clave, así que puede re-correr sin duplicar filas ni pedir
--sin-llm-style flags. bi_staging.log_corridas deja constancia de cada corrida.

Uso: python3 ingesta.py [--erp-url http://127.0.0.1:8070] [--api-key ...]
"""
import argparse
import csv
import json
import os
import time
from datetime import date
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import psycopg2

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COMERCIAL_CSV = os.path.join(BASE_DIR, "data", "comercial.csv")


def _dsn():
    return (f"host={os.environ.get('PGHOST', '127.0.0.1')} port={os.environ.get('PGPORT', '5432')} "
            f"dbname={os.environ.get('PGDATABASE', 'n8n')} user={os.environ.get('PGUSER', 'n8n_user')} "
            f"password={os.environ.get('PGPASSWORD', '')}")


# ---------- normalización de la fuente ERP (la fealdad se absorbe aquí, no en Power Query) ----------

def _normalizar_fecha(valor):
    """Acepta 'YYYY-MM-DD', 'DD/MM/YYYY' o None."""
    if not valor:
        return None
    if "/" in valor:
        d, m, y = valor.split("/")
        return date(int(y), int(m), int(d)).isoformat()
    return date.fromisoformat(valor).isoformat()


def _normalizar_pedido(item):
    cliente_id = item.get("cliente_id") or item.get("idCliente")
    return {
        "pedido_id": item["pedido_id"],
        "cliente_id": cliente_id,
        "fecha_pedido": _normalizar_fecha(item.get("fecha_pedido")),
        "importe": item.get("importe"),
        "unidades": item.get("unidades"),
    }


def _pedir_pagina(erp_url, api_key, cursor, intentos=6):
    query = "limit=200" + (f"&cursor={cursor}" if cursor else "")
    req = Request(f"{erp_url}/v1/pedidos?{query}", headers={"X-API-Key": api_key})
    espera = 2
    for intento in range(intentos):
        try:
            with urlopen(req, timeout=10) as resp:
                return json.loads(resp.read())
        except HTTPError as e:
            if e.code == 429 and intento < intentos - 1:
                retry_after = int(e.headers.get("Retry-After", espera))
                print(f"  429 rate limit, reintento en {retry_after}s ({intento + 1}/{intentos})")
                time.sleep(retry_after)
                espera = min(espera * 2, 30)
                continue
            raise
    raise RuntimeError("agotados los reintentos ante 429")


def extraer_erp(erp_url, api_key):
    pedidos, cursor, paginas = [], None, 0
    while True:
        pagina = _pedir_pagina(erp_url, api_key, cursor)
        pedidos.extend(_normalizar_pedido(p) for p in pagina["items"])
        paginas += 1
        cursor = pagina.get("next_cursor")
        if not cursor:
            break
    print(f"  ERP: {len(pedidos)} pedidos en {paginas} páginas")
    return pedidos


def extraer_comercial():
    with open(COMERCIAL_CSV, encoding="utf-8", newline="") as f:
        filas = list(csv.DictReader(f))
    print(f"  comercial.csv: {len(filas)} filas")
    return filas


def extraer_facturas(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT factura_id, pedido_id, fecha_factura, importe FROM facturacion.facturas")
        cols = [d.name for d in cur.description]
        filas = [dict(zip(cols, row)) for row in cur.fetchall()]
    print(f"  facturacion.facturas: {len(filas)} filas")
    return filas


# ---------- carga a bi_staging ----------

DDL = """
CREATE SCHEMA IF NOT EXISTS bi_staging;

CREATE TABLE IF NOT EXISTS bi_staging.pedidos (
    pedido_id    text PRIMARY KEY,
    cliente_id   text,
    fecha_pedido date,
    importe      numeric,
    unidades     integer,
    cargado_en   timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS bi_staging.comercial (
    pedido_id           text PRIMARY KEY,
    unidades_comercial  integer,
    cargado_en          timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS bi_staging.facturas (
    factura_id      text PRIMARY KEY,
    pedido_id       text,
    fecha_factura   date,
    importe_factura numeric,
    cargado_en      timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS bi_staging.log_corridas (
    id            serial PRIMARY KEY,
    ejecutado_en  timestamptz DEFAULT now(),
    pedidos       integer,
    comercial     integer,
    facturas      integer
);
"""

UPSERT_PEDIDO = """
INSERT INTO bi_staging.pedidos (pedido_id, cliente_id, fecha_pedido, importe, unidades)
VALUES (%(pedido_id)s, %(cliente_id)s, %(fecha_pedido)s, %(importe)s, %(unidades)s)
ON CONFLICT (pedido_id) DO UPDATE SET
    cliente_id = EXCLUDED.cliente_id, fecha_pedido = EXCLUDED.fecha_pedido,
    importe = EXCLUDED.importe, unidades = EXCLUDED.unidades, cargado_en = now();
"""

UPSERT_COMERCIAL = """
INSERT INTO bi_staging.comercial (pedido_id, unidades_comercial)
VALUES (%(pedido_id)s, %(unidades_comercial)s)
ON CONFLICT (pedido_id) DO UPDATE SET
    unidades_comercial = EXCLUDED.unidades_comercial, cargado_en = now();
"""

UPSERT_FACTURA = """
INSERT INTO bi_staging.facturas (factura_id, pedido_id, fecha_factura, importe_factura)
VALUES (%(factura_id)s, %(pedido_id)s, %(fecha_factura)s, %(importe_factura)s)
ON CONFLICT (factura_id) DO UPDATE SET
    pedido_id = EXCLUDED.pedido_id, fecha_factura = EXCLUDED.fecha_factura,
    importe_factura = EXCLUDED.importe_factura, cargado_en = now();
"""


def cargar(conn, pedidos, comercial, facturas):
    with conn.cursor() as cur:
        cur.execute(DDL)
        for p in pedidos:
            cur.execute(UPSERT_PEDIDO, p)
        for c in comercial:
            cur.execute(UPSERT_COMERCIAL, {
                "pedido_id": c["pedido_id"],
                "unidades_comercial": int(c["unidades_comercial"]),
            })
        for f in facturas:
            cur.execute(UPSERT_FACTURA, {
                "factura_id": f["factura_id"],
                "pedido_id": f["pedido_id"],
                "fecha_factura": f["fecha_factura"],
                "importe_factura": f["importe"],
            })
        cur.execute(
            "INSERT INTO bi_staging.log_corridas (pedidos, comercial, facturas) VALUES (%s, %s, %s)",
            (len(pedidos), len(comercial), len(facturas)),
        )
    conn.commit()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--erp-url", default=os.environ.get("ERP_URL", "http://127.0.0.1:8070"))
    ap.add_argument("--api-key", default=os.environ.get("ERP_API_KEY", "demo-key-2026"))
    args = ap.parse_args()

    print("Extrayendo...")
    pedidos = extraer_erp(args.erp_url, args.api_key)
    comercial = extraer_comercial()

    conn = psycopg2.connect(_dsn())
    try:
        facturas = extraer_facturas(conn)
        print("Cargando en bi_staging...")
        cargar(conn, pedidos, comercial, facturas)
    finally:
        conn.close()

    print(f"OK: {len(pedidos)} pedidos, {len(comercial)} filas comercial, {len(facturas)} facturas -> bi_staging")


if __name__ == "__main__":
    main()
