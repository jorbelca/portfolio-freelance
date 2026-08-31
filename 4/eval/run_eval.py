#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Arnés de evaluación de la Demo 4: lee dataset.jsonl + la tabla `extraccion_log` de Postgres,
empareja por pdf_origen y compara contra las etiquetas esperadas. No ejecuta el grafo (eso lo
hace ../procesar_facturas.py); solo mide lo que ya quedó escrito.

Mismo patrón que 1/eval/run_eval.py y 2/eval/run_eval.py: --dry-run construye un resultado
sintético con fallos inyectados a propósito y lo verifica con asserts, para que romper el
cálculo de una sección del informe falle aquí y no 30 facturas después contra Postgres real.

Uso: run_eval.py [--dry-run] [--dataset F] [--dsn DSN]
DSN por variables de entorno si no se pasa --dsn: PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD
(defaults 127.0.0.1/5432/n8n/n8n_user), mismo convenio que 2/eval/run_eval.py.
"""
import argparse
import json
import os
import sys

try:
    import psycopg2
except ImportError:
    psycopg2 = None


def cargar_dataset(path):
    filas = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    ids = [f["pdf_origen"] for f in filas]
    assert len(ids) == len(set(ids)), "hay pdf_origen duplicados en el dataset"
    return filas


def construir_dsn(args):
    if args.dsn:
        return args.dsn
    host = os.environ.get("PGHOST", "127.0.0.1")
    port = os.environ.get("PGPORT", "5432")
    dbname = os.environ.get("PGDATABASE", "n8n")
    user = os.environ.get("PGUSER", "n8n_user")
    password = os.environ.get("PGPASSWORD", "")
    return f"host={host} port={port} dbname={dbname} user={user} password={password}"


def leer_log(dsn):
    """Se queda con la ÚLTIMA fila por pdf_origen (id más alto): permite re-ejecutar
    procesar_facturas.py sin truncar antes y que el eval mida el estado actual, no un historial
    de reintentos mezclado."""
    conn = psycopg2.connect(dsn)
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT DISTINCT ON (pdf_origen) pdf_origen, resultado, motivo, confianza_minima
               FROM extraccion_log ORDER BY pdf_origen, id DESC""")
        cols = [c.name for c in cur.description]
        return {row[0]: dict(zip(cols, row)) for row in cur.fetchall()}
    finally:
        conn.close()


def construir_resultados_sinteticos(dataset):
    """Resultado sintético para --dry-run, con cobertura completa (100%, como en los datasets
    reales de hoy) y dos fallos de clasificación inyectados y nombrados por id: f02 se fuerza a
    'persistido' cuando debía ir a cola (falso negativo del motor de reglas), f08 se fuerza a
    cola cuando debía persistirse limpio (falso positivo). Cobertura completa a propósito -- el
    dry-run es un smoke test que debe salir con exit 0, igual que en 1/eval y 2/eval; un hueco
    de cobertura forzado se probaría con un caso unitario de informe(), no aquí."""
    filas = {}
    for d in dataset:
        resultado = "cola_revision" if d["esperado_en_cola"] else "persistido"
        motivo = d["motivo_esperado"]
        if d["id"] == "f02":
            resultado, motivo = "persistido", None  # falso negativo forzado
        if d["id"] == "f08":
            resultado, motivo = "cola_revision", "aritmética"  # falso positivo forzado
        filas[d["pdf_origen"]] = {
            "pdf_origen": d["pdf_origen"], "resultado": resultado, "motivo": motivo,
            "confianza_minima": 0.35 if resultado == "cola_revision" else 0.95,
        }
    return filas


def informe(dataset, filas):
    total = len(dataset)

    # ============================================================ 1. Cobertura
    faltantes = [d["id"] for d in dataset if d["pdf_origen"] not in filas]
    cubiertos = total - len(faltantes)
    print("=== 1. Cobertura ===")
    print(f"{cubiertos} de {total} facturas esperadas aparecen en extraccion_log")
    if faltantes:
        print(f"FALTAN (no se procesaron): {', '.join(faltantes)}")

    # ============================================================ 2. Acierto de decisión
    correctos = 0
    discrepancias = []
    for d in dataset:
        fila = filas.get(d["pdf_origen"])
        obtenido_en_cola = (fila["resultado"] == "cola_revision") if fila else None
        acierto = obtenido_en_cola == d["esperado_en_cola"]
        correctos += acierto
        if not acierto:
            discrepancias.append((d["id"], d["esperado_en_cola"], obtenido_en_cola))
    print("\n=== 2. Acierto de decisión (persistir vs. cola) ===")
    print(f"{correctos} de {total} ({correctos / total:.1%})")
    if discrepancias:
        print("Discrepancias:")
        for id_, esperado, obtenido in discrepancias:
            print(f"  {id_}: esperado_en_cola={esperado}, obtenido={obtenido}")

    # ============================================================ 3. Motivo (solo casos que sí esperaban cola)
    esperaban_cola = [d for d in dataset if d["esperado_en_cola"]]
    motivo_ok = 0
    motivo_mal = []
    for d in esperaban_cola:
        fila = filas.get(d["pdf_origen"])
        motivo_obtenido = (fila or {}).get("motivo") or ""
        if d["motivo_esperado"] and d["motivo_esperado"] in motivo_obtenido:
            motivo_ok += 1
        else:
            motivo_mal.append((d["id"], d["motivo_esperado"], motivo_obtenido))
    print(f"\n=== 3. Motivo de cola correcto (de las que sí fueron a cola) ===")
    print(f"{motivo_ok} de {len(esperaban_cola)}")
    for id_, esperado, obtenido in motivo_mal:
        print(f"  {id_}: esperaba motivo que contenga '{esperado}', obtuvo '{obtenido}'")

    return {
        "total": total, "cubiertos": cubiertos, "faltantes": faltantes,
        "correctos": correctos, "discrepancias": discrepancias,
        "esperaban_cola": len(esperaban_cola), "motivo_ok": motivo_ok, "motivo_mal": motivo_mal,
    }


def verificar_dry_run(m):
    """Los totales (30, etc.) están calculados sobre dataset.jsonl EXACTAMENTE como es hoy. Si
    alguien añade/quita casos sin tocar este fichero, estos asserts fallarán -- y el mensaje lo
    dice explícitamente, para no perder tiempo pensando que el informe se rompió cuando lo que
    cambió fue el dataset."""
    assert m["total"] == 30, (
        f"población = {m['total']}, se esperaban 30: si cambió el número de casos en "
        f"dataset.jsonl, actualiza este número; no asumas que es un bug.")
    assert m["cubiertos"] == 30 and m["faltantes"] == [], "el sintético cubre las 30 facturas"
    assert m["correctos"] == 28, (
        f"construir_resultados_sinteticos() fuerza exactamente 2 fallos de decisión (f02, f08); "
        f"fallan {30 - m['correctos']}. Si el total (30) no cambió, esto es un bug real.")
    assert {d[0] for d in m["discrepancias"]} == {"f02", "f08"}, (
        f"las discrepancias forzadas deberían ser f02/f08, salieron {[d[0] for d in m['discrepancias']]}")
    assert m["esperaban_cola"] == 7, (
        f"casos con esperado_en_cola=true = {m['esperaban_cola']}, se esperaban 7 "
        f"(f02,f05,f03,f06,f07,f04,f10): si el dataset cambió, actualiza este número.")
    assert m["motivo_ok"] == 6 and [mm[0] for mm in m["motivo_mal"]] == ["f02"], (
        "f02 forzado a motivo=None es el único motivo incorrecto esperado (queda en cola vía "
        "f08 con motivo correcto 'aritmética', así que no cuenta aquí)")
    print("\nVerificación estructural del dry-run: OK (cobertura, decisión y motivo cuadran).")


def main():
    ap = argparse.ArgumentParser(description="Evalúa la extracción de facturas contra el dataset etiquetado.")
    ap.add_argument("--umbral-acierto", type=float, default=0.85,
                     help="acierto mínimo exigido en la decisión persistir/cola (default: 0.85)")
    ap.add_argument("--dataset", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "dataset.jsonl"))
    ap.add_argument("--dsn", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    dataset = cargar_dataset(args.dataset)

    if args.dry_run:
        filas = construir_resultados_sinteticos(dataset)
        metricas = informe(dataset, filas)
        verificar_dry_run(metricas)
    else:
        if psycopg2 is None:
            print("Falta psycopg2 (pip install psycopg2-binary).")
            sys.exit(1)
        dsn = construir_dsn(args)
        try:
            filas = leer_log(dsn)
        except psycopg2.errors.UndefinedTable:
            print("extraccion_log no existe todavía. Ejecuta init-facturas-tables.sql y "
                  "procesar_facturas.py primero.")
            sys.exit(1)
        except psycopg2.OperationalError as e:
            print(f"No se pudo conectar a Postgres: {e}")
            sys.exit(1)
        metricas = informe(dataset, filas)

    try:
        assert metricas["cubiertos"] == metricas["total"], (
            f"cobertura incompleta: {metricas['cubiertos']} de {metricas['total']}")
        acierto = metricas["correctos"] / metricas["total"]
        assert acierto >= args.umbral_acierto, (
            f"acierto {acierto:.1%} no alcanza el umbral {args.umbral_acierto:.1%}")
    except AssertionError as e:
        print(f"\nFALLO: {e}")
        sys.exit(1)

    print(f"\nOK: cobertura completa y acierto de decisión {acierto:.1%} >= umbral {args.umbral_acierto:.1%}")


if __name__ == "__main__":
    main()
