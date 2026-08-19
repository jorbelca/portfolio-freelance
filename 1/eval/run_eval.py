#!/usr/bin/env python3
"""Arnes de evaluacion del triage de correo: lee dataset.jsonl + triage_log
(Postgres), empareja por message_id y compara. No envia correos ni ejecuta n8n.
Uso: run_eval.py [--dry-run] [--umbral-acierto 0.85] [--dataset F] [--dsn DSN]"""
import argparse
import json
import os
import sys

try:
    import psycopg2
    import psycopg2.errors
except ImportError:
    psycopg2 = None

TAXONOMIA = ["cliente_nuevo", "expediente_existente", "plazo", "ruido", "duda"]
TRAMOS = ["[0-0.5)", "[0.5-0.7)", "[0.7-0.9)", "[0.9-1.0]"]

def bucket_de(conf):
    if conf < 0.5:
        return TRAMOS[0]
    if conf < 0.7:
        return TRAMOS[1]
    if conf < 0.9:
        return TRAMOS[2]
    return TRAMOS[3]

def cargar_dataset(path):
    filas = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    ids = [f["id"] for f in filas]
    assert len(ids) == len(set(ids)), "hay ids duplicados en el dataset"
    msg_ids = [f["message_id"] for f in filas]
    assert len(msg_ids) == len(set(msg_ids)), "hay message_id duplicados en el dataset"
    for f in filas:
        assert f["categoria_esperada"] in TAXONOMIA, (
            f"{f['id']}: categoria_esperada '{f['categoria_esperada']}' fuera de la taxonomia"
        )
    return filas

def construir_dsn():
    """Parseo trivial de .env (CLAVE=valor, sin python-dotenv) para sacar la
    contrasena de Postgres del fichero .env del directorio padre."""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
    password = None
    for linea in open(env_path, encoding="utf-8") if os.path.exists(env_path) else []:
        clave, _, valor = linea.strip().partition("=")
        if clave == "DB_POSTGRESDB_PASSWORD":
            password = valor.split("#")[0].strip()
    if not password:
        print(f"No se encontro DB_POSTGRESDB_PASSWORD en {env_path}")
        sys.exit(1)
    return f"host=localhost port=5432 dbname=n8n user=n8n_user password={password}"

def leer_triage_log(dsn):
    conn = psycopg2.connect(dsn)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT message_id, categoria, motivo, confianza, accion, decidido_por FROM triage_log"
        )
        cols = [c.name for c in cur.description]
        return {row[0]: dict(zip(cols, row)) for row in cur.fetchall()}
    finally:
        conn.close()

def construir_resultados_sinteticos(dataset):
    """Resultado sintetico para --dry-run: acierta todo salvo dos casos forzados
    (e01 y e04), y reparte la confianza entre los cuatro tramos para ejercitar
    esa seccion del informe. e08 se fuerza a decidido_por='umbral' para probar
    la logica de escalados sin tocar su etiqueta (que sigue siendo correcta)."""
    ciclo = [0.45, 0.65, 0.85, 0.95]
    forzados = {"e01": "ruido", "e04": "expediente_existente"}
    conf_forzada = {"e01": 0.4, "e04": 0.55}
    filas = {}
    for i, d in enumerate(dataset):
        filas[d["message_id"]] = {
            "categoria": forzados.get(d["id"], d["categoria_esperada"]),
            "confianza": conf_forzada.get(d["id"], ciclo[i % 4]),
            "decidido_por": "umbral" if d["id"] == "e08" else "sistema",
            "motivo": "sintetico",
            "accion": "archivado",
        }
    return filas

def informe(dataset, filas):
    total = len(dataset)
    faltantes = [d["id"] for d in dataset if d["message_id"] not in filas]
    cubiertos = total - len(faltantes)

    print("=== 1. Cobertura ===")
    print(f"{cubiertos} de {total} correos aparecen en triage_log")
    if faltantes:
        print(f"FALTAN (el workflow no los proceso): {', '.join(faltantes)}")
    else:
        print("Cobertura completa: no falta ningun correo.")

    correctos = 0
    matriz = {}
    discrepancias = []
    tramos = {t: [0, 0] for t in TRAMOS}  # [aciertos, fallos]
    escalados_ids = set()
    escalados_de_mas = 0
    correctos_no_amb = total_no_amb = 0
    correctos_amb = total_amb = 0

    for d in dataset:
        fila = filas.get(d["message_id"])
        esperada = d["categoria_esperada"]
        obtenida = fila["categoria"] if fila else "AUSENTE"
        acierto = obtenida == esperada
        if acierto:
            correctos += 1
        matriz[(esperada, obtenida)] = matriz.get((esperada, obtenida), 0) + 1

        if d["ambiguo"]:
            total_amb += 1
            correctos_amb += acierto
        else:
            total_no_amb += 1
            correctos_no_amb += acierto

        if not acierto:
            conf = fila["confianza"] if fila else None
            discrepancias.append((d["id"], esperada, obtenida, conf, d["regla"], d["nota_rubrica"]))

        if fila:
            conf = fila["confianza"]
            if conf is not None:
                bucket = bucket_de(float(conf))
                tramos[bucket][0 if acierto else 1] += 1
            if fila["decidido_por"] == "umbral" or fila["categoria"] == "duda":
                escalados_ids.add(d["id"])
                if esperada != "duda":
                    escalados_de_mas += 1

    print("\n=== 2. Acierto global ===")
    print(f"{correctos} de {total} ({correctos / total:.1%})")
    if faltantes:
        print("(los correos no procesados cuentan como fallo; ver Cobertura arriba)")

    print("\n=== 3. Matriz de confusion (esperada x obtenida) ===")
    columnas = TAXONOMIA + (["AUSENTE"] if faltantes else [])
    ancho = max(len(c) for c in columnas + TAXONOMIA + ["esperada\\obtenida"]) + 2
    print("esperada\\obtenida".ljust(ancho) + "".join(c.ljust(ancho) for c in columnas))
    for esp in TAXONOMIA:
        fila_txt = esp.ljust(ancho)
        for obt in columnas:
            fila_txt += str(matriz.get((esp, obt), 0)).ljust(ancho)
        print(fila_txt)

    print("\n=== 4. Desglose por dificultad ===")
    p_no_amb = correctos_no_amb / total_no_amb if total_no_amb else 0
    p_amb = correctos_amb / total_amb if total_amb else 0
    print(f"No ambiguos: {correctos_no_amb} de {total_no_amb} ({p_no_amb:.1%})")
    print(f"Ambiguos:    {correctos_amb} de {total_amb} ({p_amb:.1%})")

    print("\n=== 5. Discrepancias ===")
    if not discrepancias:
        print("Ninguna.")
    for id_, esp, obt, conf, regla, nota in discrepancias:
        conf_txt = f"{float(conf):.2f}" if conf is not None else "-"
        print(f"{id_.ljust(5)} | esperada={esp.ljust(22)} | obtenida={obt.ljust(22)} | "
              f"confianza={conf_txt.ljust(5)} | {regla.ljust(6)} | {nota}")

    print("\n=== 6. Errores por tramo de confianza ===")
    for t in TRAMOS:
        a, f = tramos[t]
        print(f"{t.ljust(12)} aciertos={a:>3}  fallos={f:>3}")

    print("\n=== 7. Escalados a revision humana ===")
    print(f"Total escalados (decidido_por='umbral' o categoria='duda'): {len(escalados_ids)} de {total}")
    print(f"De esos, escalados de mas (la etiqueta humana no era 'duda'): {escalados_de_mas}")

    return {
        "total": total,
        "cubiertos": cubiertos,
        "faltantes": faltantes,
        "correctos": correctos,
        "matriz": matriz,
        "discrepancias": discrepancias,
        "tramos": tramos,
        "correctos_no_amb": correctos_no_amb,
        "total_no_amb": total_no_amb,
        "correctos_amb": correctos_amb,
        "total_amb": total_amb,
        "escalados_total": len(escalados_ids),
        "escalados_de_mas": escalados_de_mas,
    }

def verificar_dry_run(m):
    """Asserts estructurales contra el conjunto sintetico: si alguien rompe el
    calculo de cobertura, matriz, dificultad, tramos o escalados, esto falla."""
    assert m["cubiertos"] == m["total"] == 28, "el sintetico deberia cubrir los 28 correos"
    assert m["faltantes"] == [], "el sintetico no deberia tener faltantes"
    assert m["correctos"] == m["total"] - 2, "deberian fallar exactamente 2 casos forzados"
    assert sum(m["matriz"].values()) == m["total"], "la matriz de confusion no suma 28"
    assert {d[0] for d in m["discrepancias"]} == {"e01", "e04"}, "discrepancias inesperadas"
    assert m["correctos_no_amb"] == m["total_no_amb"] - 1 == 17, "desglose no-ambiguos incorrecto"
    assert m["correctos_amb"] == m["total_amb"] - 1 == 9, "desglose ambiguos incorrecto"
    total_tramos = sum(a + f for a, f in m["tramos"].values())
    assert total_tramos == m["total"], "los tramos de confianza no suman 28"
    assert all(a + f > 0 for a, f in m["tramos"].values()), "algun tramo de confianza quedo vacio"
    assert sum(a for a, f in m["tramos"].values()) == m["correctos"], "aciertos por tramo no cuadran"
    assert sum(f for a, f in m["tramos"].values()) == m["total"] - m["correctos"], "fallos por tramo no cuadran"
    assert m["escalados_total"] == 6, "escalados_total deberia ser 6 (5 duda + e08 forzado)"
    assert m["escalados_de_mas"] == 1, "escalados_de_mas deberia ser 1 (solo e08)"
    print("\nVerificacion estructural del dry-run: OK (matriz, dificultad, tramos y escalados cuadran).")

def main():
    ap = argparse.ArgumentParser(description="Evalua el triage de correo contra el dataset etiquetado.")
    ap.add_argument("--umbral-acierto", type=float, default=0.85,
                     help="acierto minimo exigido sobre los casos NO ambiguos (default: 0.85)")
    ap.add_argument("--dataset", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "dataset.jsonl"))
    ap.add_argument("--dsn", default=None, help="cadena de conexion libpq completa; si se omite se construye desde .env")
    ap.add_argument("--dry-run", action="store_true", help="valida el informe con datos sinteticos, sin tocar Postgres")
    args = ap.parse_args()

    dataset = cargar_dataset(args.dataset)

    if args.dry_run:
        filas = construir_resultados_sinteticos(dataset)
        metricas = informe(dataset, filas)
        verificar_dry_run(metricas)
    else:
        if psycopg2 is None:
            print("Falta psycopg2 (pip install psycopg2-binary). Es la unica dependencia externa permitida.")
            sys.exit(1)
        dsn = args.dsn or construir_dsn()
        try:
            filas = leer_triage_log(dsn)
        except psycopg2.errors.UndefinedTable:
            print("La tabla triage_log no existe todavia. Ejecuta el workflow de triage primero "
                  "(python3 seed_emails.py y espera a que procese los correos).")
            sys.exit(1)
        except psycopg2.OperationalError as e:
            print(f"No se pudo conectar a Postgres ({dsn.split('password=')[0]}...): {e}")
            sys.exit(1)
        metricas = informe(dataset, filas)

    try:
        assert metricas["cubiertos"] == metricas["total"], (
            f"cobertura incompleta: {metricas['cubiertos']} de {metricas['total']}"
        )
        acierto_no_amb = metricas["correctos_no_amb"] / metricas["total_no_amb"]
        assert acierto_no_amb > args.umbral_acierto, (
            f"acierto en no-ambiguos {acierto_no_amb:.1%} no supera el umbral {args.umbral_acierto:.1%}"
        )
    except AssertionError as e:
        print(f"\nFALLO: {e}")
        sys.exit(1)

    print(f"\nOK: cobertura completa y acierto en no-ambiguos {acierto_no_amb:.1%} "
          f"> umbral {args.umbral_acierto:.1%}")

if __name__ == "__main__":
    main()
