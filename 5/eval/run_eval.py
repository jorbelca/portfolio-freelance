#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Arnes de evaluacion de la Demo 5. Lee eval/dataset.jsonl + cualificacion_log (Postgres),
empareja por lead_ref y compara contra `esperado`. No llama a ningun modelo ni envia correos.

DOS MODOS, DOS NUMEROS -- no se promedian (ver eval/README.md):
  - log de `procesar_leads.py --sin-llm`          -> mide el CODIGO (rubrica+gate). 30/30 esperado.
  - log de `SALTAR_INVESTIGACION=1 procesar_leads.py` -> mide el MODELO sobre evidencia fija.
                                                        El numero que va al video.
run_eval.py no sabe que modo lo genero: solo mide. El umbral se pasa por CLI.

`regla` es la metrica que mas importa: R8/R11/R12 producen todas `tibio` y solo `regla` las
distingue -- va en su propio bucket (mismo criterio que "fundamento equivocado con imputacion
correcta" en la Demo 3).

Uso: run_eval.py [--dry-run] [--umbral-etiqueta 0.85] [--dataset F] [--dsn DSN]
"""
import argparse
import json
import os
import sys

try:
    import psycopg2
except ImportError:
    psycopg2 = None

ETIQUETAS = ["caliente", "tibio", "frio", None]  # None == sin_cualificar
RESULTADOS = ("cualificado", "cola_revision", "sin_cualificar")
AQUI = os.path.dirname(os.path.abspath(__file__))


def cargar_dataset(path):
    filas = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    ids = [f["id"] for f in filas]
    assert len(ids) == len(set(ids)), "ids duplicados en el dataset"
    for f in filas:
        e = f["esperado"]
        assert e["etiqueta"] in ETIQUETAS, f"{f['id']}: etiqueta esperada '{e['etiqueta']}' fuera de rango"
        assert e["resultado_log"] in RESULTADOS, f"{f['id']}: resultado_log fuera de rango"
        assert isinstance(e["en_cola"], bool), f"{f['id']}: en_cola no es bool"
    return filas


def construir_dsn():
    """Saca la password de Postgres de ../1/.env, sin python-dotenv (igual que 1/eval)."""
    env_path = os.path.join(AQUI, "..", "..", "1", ".env")
    password = ""
    if os.path.exists(env_path):
        for linea in open(env_path, encoding="utf-8"):
            clave, _, valor = linea.strip().partition("=")
            if clave == "DB_POSTGRESDB_PASSWORD":
                password = valor.split("#")[0].strip()
    host = os.environ.get("PGHOST", "127.0.0.1")
    port = os.environ.get("PGPORT", "5432")
    db = os.environ.get("PGDATABASE", "n8n")
    user = os.environ.get("PGUSER", "n8n_user")
    return f"host={host} port={port} dbname={db} user={user} password={os.environ.get('PGPASSWORD', password)}"


def leer_log(dsn):
    conn = psycopg2.connect(dsn)
    try:
        cur = conn.cursor()
        cur.execute("SELECT lead_ref, resultado, etiqueta, regla, motivo FROM cualificacion_log ORDER BY id")
        por_ref = {}
        for lref, *resto in cur.fetchall():
            por_ref.setdefault(lref, []).append(tuple(resto))
    finally:
        conn.close()
    multi = {k: len(v) for k, v in por_ref.items() if len(v) > 1}
    if multi:
        print(f"ERROR: {len(multi)} lead_ref con mas de una fila en cualificacion_log: {multi}")
        print("Hay resultados de mas de una corrida mezclados; el numero no seria fiable.")
        print('Vacia y repite:  psql ... -c "TRUNCATE leads, cola_revision, cualificacion_log RESTART IDENTITY;"')
        sys.exit(1)
    return {k: v[0] for k, v in por_ref.items()}


def construir_sintetico(dataset):
    """--dry-run: log perfecto salvo dos fallos forzados -- l06 (etiqueta) y l21 (regla)."""
    out = {}
    for d in dataset:
        e = d["esperado"]
        et, rg = e["etiqueta"], e["regla"]
        res = e["resultado_log"]
        if d["id"] == "l06":
            et = "caliente"
        if d["id"] == "l21":
            rg = "R8"
        out[d["id"]] = (res, et, rg, e.get("motivo_contiene") or "sintetico")
    return out


def informe(dataset, log):
    total = len(dataset)
    faltan = [d["id"] for d in dataset if d["id"] not in log]
    cobertura = total - len(faltan)

    print("=== 1. Cobertura ===")
    print(f"{cobertura} de {total} leads aparecen en cualificacion_log")
    if faltan:
        print(f"FALTAN: {', '.join(faltan)}")

    etiqueta_ok = regla_ok = cola_ok = 0
    matriz = {}
    disc = []
    escalados_de_mas = []
    motivos_cola = {}

    def nom(x):
        return x if x is not None else "sin_cualificar"

    for d in dataset:
        e = d["esperado"]
        fila = log.get(d["id"])
        if not fila:
            disc.append((d["id"], "AUSENTE", "-", "-"))
            matriz[(nom(e["etiqueta"]), "AUSENTE")] = matriz.get((nom(e["etiqueta"]), "AUSENTE"), 0) + 1
            continue
        res, et, rg, mo = fila
        et = et or None
        rg = rg or None
        en_cola_obt = res != "cualificado"

        matriz[(nom(e["etiqueta"]), nom(et))] = matriz.get((nom(e["etiqueta"]), nom(et)), 0) + 1
        if et == e["etiqueta"]:
            etiqueta_ok += 1
        else:
            disc.append((d["id"], "etiqueta", nom(e["etiqueta"]), nom(et)))
        if rg == e["regla"]:
            regla_ok += 1
        else:
            disc.append((d["id"], "regla", str(e["regla"]), str(rg)))
        if en_cola_obt == e["en_cola"]:
            cola_ok += 1
        else:
            disc.append((d["id"], "en_cola", str(e["en_cola"]), str(en_cola_obt)))
        if en_cola_obt and not e["en_cola"]:
            escalados_de_mas.append(d["id"])
        if en_cola_obt:
            cat = (mo or "").split(":")[0].split(" (")[0]
            motivos_cola[cat] = motivos_cola.get(cat, 0) + 1

    print("\n=== 2. Acierto de ETIQUETA ===")
    print(f"{etiqueta_ok} de {total} ({etiqueta_ok / total:.1%})")
    print("\n=== 3. Acierto de REGLA (la metrica que distingue R8/R11/R12) ===")
    print(f"{regla_ok} de {total} ({regla_ok / total:.1%})")
    print("\n=== 4. Acierto de enrutado a cola (dudoso vs directo) ===")
    print(f"{cola_ok} de {total} ({cola_ok / total:.1%})")

    print("\n=== 5. Matriz de etiqueta (esperada x obtenida) ===")
    cols = ["caliente", "tibio", "frio", "sin_cualificar"] + (["AUSENTE"] if faltan else [])
    w = max(len(c) for c in cols + ["esperada\\obtenida"]) + 2
    print("esperada\\obtenida".ljust(w) + "".join(c.ljust(w) for c in cols))
    for esp in ["caliente", "tibio", "frio", "sin_cualificar"]:
        print(esp.ljust(w) + "".join(str(matriz.get((esp, o), 0)).ljust(w) for o in cols))

    print("\n=== 6. Discrepancias ===")
    if not disc:
        print("Ninguna.")
    for lid, campo, esp, obt in disc:
        print(f"  {lid.ljust(5)} {campo.ljust(10)} esperado={esp.ljust(16)} obtenido={obt}")

    print("\n=== 7. Cola de revision ===")
    for cat, n in sorted(motivos_cola.items(), key=lambda x: -x[1]):
        print(f"  {cat.ljust(30)} {n}")
    print(f"Escalados de mas (esperado directo, fue a cola): {len(escalados_de_mas)} "
          f"{escalados_de_mas if escalados_de_mas else ''}")

    return {"total": total, "cobertura": cobertura, "faltan": faltan, "etiqueta_ok": etiqueta_ok,
            "regla_ok": regla_ok, "cola_ok": cola_ok, "matriz": matriz,
            "disc_ids": {d[0] for d in disc}, "escalados_de_mas": len(escalados_de_mas)}


def verificar_dry_run(m):
    assert m["cobertura"] == m["total"] == 30, "el sintetico deberia cubrir 30"
    assert m["faltan"] == [], "el sintetico no deberia tener faltantes"
    assert m["etiqueta_ok"] == 29, f"esperado 1 fallo de etiqueta forzado (l06), {m['etiqueta_ok']}/30"
    assert m["regla_ok"] == 29, f"esperado 1 fallo de regla forzado (l21), {m['regla_ok']}/30"
    assert m["cola_ok"] == 30, "el sintetico no cambia en_cola"
    assert m["disc_ids"] == {"l06", "l21"}, f"discrepancias inesperadas: {m['disc_ids']}"
    assert sum(m["matriz"].values()) == 30, "la matriz no suma 30"
    assert m["escalados_de_mas"] == 0
    print("\nVerificacion estructural del dry-run: OK.")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="valida el informe con datos sinteticos, sin Postgres")
    ap.add_argument("--umbral-etiqueta", type=float, default=0.85,
                    help="acierto minimo de etiqueta exigido (default 0.85; el modo --sin-llm da 1.0)")
    ap.add_argument("--dataset", default=os.path.join(AQUI, "dataset.jsonl"))
    ap.add_argument("--dsn", default=None)
    args = ap.parse_args()

    dataset = cargar_dataset(args.dataset)

    if args.dry_run:
        m = informe(dataset, construir_sintetico(dataset))
        verificar_dry_run(m)
        return

    if psycopg2 is None:
        print("Falta psycopg2 (pip install psycopg2-binary).")
        sys.exit(1)
    log = leer_log(args.dsn or construir_dsn())
    m = informe(dataset, log)

    print("\n=== Resultado ===")
    p = m["etiqueta_ok"] / m["total"]
    if m["faltan"]:
        print(f"FALLA: {len(m['faltan'])} leads sin procesar.")
        sys.exit(1)
    if p < args.umbral_etiqueta:
        print(f"FALLA: acierto de etiqueta {p:.1%} < umbral {args.umbral_etiqueta:.0%}.")
        sys.exit(1)
    print(f"OK: acierto de etiqueta {p:.1%} >= {args.umbral_etiqueta:.0%}; regla {m['regla_ok'] / m['total']:.1%}.")


if __name__ == "__main__":
    main()
