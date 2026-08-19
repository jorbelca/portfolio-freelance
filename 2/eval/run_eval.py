#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Arnés de evaluación del triage jurídico de incidencias: lee dataset.jsonl + la tabla
`incidencias` de Postgres, empareja por message_id y compara contra las etiquetas esperadas.
No envía correos ni ejecuta n8n. Adaptado de 1/eval/run_eval.py (Demo A) al dominio de
fincas, con dos diferencias de fondo respecto a esa plantilla:

1. Población evaluable: los 45 casos. Una versión anterior excluía 8 (`esperado_en_tabla:
   false`) porque `comunidad_id` era NOT NULL y la taxonomía solo tenía tres valores. Las dos
   cosas se corrigieron: la columna admite NULL y la compuerta registra la incidencia con
   `decidido_por='compuerta'` antes de avisar, y existe un cuarto valor `no_aplica` para las
   consultas que no son incidencia técnica. Ninguna rama del sistema queda ya sin rastro, así
   que ninguna queda fuera de la cobertura. El campo se conserva por si en el futuro hace
   falta excluir algún caso, pero hoy ningún caso lo lleva en false.

2. `revision_esperada` como eje propio, distinto de `ambiguo`. La rúbrica (rubrica-imputacion-
   fincas.md, sección 6) obliga a revisión humana en casos que dependen de una cláusula
   estatutaria concreta, y la sección 3.9.3 obliga a revisión en un caso que NO es mixto y que
   se marca ambiguo=false a propósito (para no ser un mixto disfrazado). Un caso `no_aplica`
   también exige revisión --alguien tiene que contestar la consulta-- sin ser una duda de
   imputación. Derivar "debía escalar" de `ambiguo` habría perdido los tres supuestos.

Uso: run_eval.py [--dry-run] [--umbral-acierto 0.85] [--dataset F] [--dsn DSN]
DSN por variables de entorno si no se pasa --dsn: PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD
(defaults 127.0.0.1/5432/n8n/n8n_user), mismo convenio que 2/test_dedup.py.
"""
import argparse
import json
import os
import re
import sys

try:
    import psycopg2
    import psycopg2.errors
except ImportError:
    psycopg2 = None

VALORES_IMPUTACION = {"comun", "privativo", "mixto", "no_aplica"}


def cargar_dataset(path):
    filas = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    ids = [f["id"] for f in filas]
    assert len(ids) == len(set(ids)), "hay ids duplicados en el dataset"
    msg_ids = [f["message_id"] for f in filas]
    assert len(msg_ids) == len(set(msg_ids)), "hay message_id duplicados en el dataset"
    for f in filas:
        assert f["imputacion_esperada"] in VALORES_IMPUTACION or f["imputacion_esperada"] is None, (
            f"{f['id']}: imputacion_esperada '{f['imputacion_esperada']}' fuera de dominio")
    return filas


def normalizar_norma(cadena):
    """Extrae (numero_de_articulo, resto) de una cita tipo 'art. 9.1.b LPH' o
    'art. 4º estatutos CDP-001'. Tolerante con mayúsculas, puntos, 'º' y espacios variables;
    estricto con el número de artículo en sí, para no confundir 'art. 396 CC' con un
    hipotético 'art. 39.6 CC' solo por haber limpiado puntos a lo bruto. Si la cadena no
    encaja con el patrón 'art. N resto', se devuelve normalizada como texto plano (fallback
    para citas que no sigan el formato 'art.', p. ej. si algún día se cita un Real Decreto)."""
    if not cadena:
        return None
    s = cadena.strip().lower().replace("artículo", "art").replace("articulo", "art")
    m = re.match(r"art\.?\s*([0-9]+(?:\.[0-9a-z]+)*)\s*º?\.?\s+(.*)", s)
    if not m:
        return re.sub(r"\s+", " ", re.sub(r"[.\sº]+", " ", s)).strip()
    numero = m.group(1)
    resto = re.sub(r"\s+", " ", re.sub(r"[.\sº]+", " ", m.group(2))).strip()
    return (numero, resto)


def tipos_de_plazos(valor):
    """plazos_activos es JSONB; puede llegar como lista de strings ('siniestro_lcs16') o
    lista de objetos ({'tipo': 'siniestro_lcs16', ...}). Se extrae un set de tipos aceptando
    cualquiera de las dos formas, en vez de asumir una sola, porque el formato exacto lo fija
    el workflow de n8n (que no se controla desde este fichero)."""
    if not valor:
        return set()
    tipos = set()
    for item in valor:
        if isinstance(item, str):
            tipos.add(item)
        elif isinstance(item, dict) and "tipo" in item:
            tipos.add(item["tipo"])
    return tipos


def construir_dsn(args):
    if args.dsn:
        return args.dsn
    host = os.environ.get("PGHOST", "127.0.0.1")
    port = os.environ.get("PGPORT", "5432")
    dbname = os.environ.get("PGDATABASE", "n8n")
    user = os.environ.get("PGUSER", "n8n_user")
    password = os.environ.get("PGPASSWORD", "")
    return f"host={host} port={port} dbname={dbname} user={user} password={password}"


def leer_incidencias(dsn):
    conn = psycopg2.connect(dsn)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT message_id, comunidad_id, elemento_normalizado, imputacion, "
            "imputacion_rival, fundamento, urgencia, requiere_junta, plazos_activos, "
            "confianza, umbral_aplicado, accion, decidido_por FROM incidencias"
        )
        cols = [c.name for c in cur.description]
        return {row[0]: dict(zip(cols, row)) for row in cur.fetchall()}
    finally:
        conn.close()


def construir_resultados_sinteticos(dataset):
    """Resultado sintético para --dry-run, sobre la población esperado_en_tabla=true (hoy los 45
    casos). Fuerza errores concretos y nombrados para poder verificar con asserts que cada
    sección del informe cuenta lo que dice contar, igual que hace 1/eval/run_eval.py con
    e01/e04/e08: i07 acierta la imputación pero cita mal el artículo, i17 falla en un caso no
    ambiguo, i04 en uno ambiguo, i12 pierde un plazo, i13 se inventa uno, i15 escala de más e
    i33 escala de menos. Todos por id, para que se lean como inyecciones y no como reglas."""
    filas = {}
    for d in dataset:
        if not d.get("esperado_en_tabla", True):
            continue
        fundamento = list(d["fundamento_esperado"])  # copia; se sustituye si el caso está forzado

        # --- fundamento equivocado con imputación correcta (i07: comun correcto, cita mal el articulo)
        if d["id"] == "i07":
            fundamento = [{"norma": "art. 9.1.a LPH", "cita": "sintetico", "fuente": "ley"}]

        imputacion = d["imputacion_esperada"]
        # --- 1 fallo de imputacion en no-ambiguos (i17: privativo -> se fuerza a comun)
        if d["id"] == "i17":
            imputacion = "comun"
        # --- 1 fallo de imputacion en ambiguos (i04: mixto (caso limite) -> se fuerza a comun)
        if d["id"] == "i04":
            imputacion = "comun"

        plazos = list(d["plazos_esperados"])
        # --- recall de plazos: i12 pierde un plazo que si esperaba (falso negativo)
        if d["id"] == "i12":
            plazos = []
        # --- falso positivo de plazo: i13 no esperaba ninguno y el sistema marca uno de mas
        if d["id"] == "i13":
            plazos = ["siniestro_lcs16"]

        # --- escalados esperados (revision_esperada=true) que SI se escalan correctamente
        decidido_por = "humano" if d.get("revision_esperada") else "sistema"
        # --- escalada PERDIDA: i33 rompe la regla simplista "ambiguo implica revision" (es
        # ambiguo=false y aun asi exige revision por la seccion 3.9.3). Se fuerza a que el
        # sistema lo resuelva solo para que el informe pueda detectar escaladas perdidas, no
        # solo escaladas de mas. Va como inyeccion por id, igual que i07/i17/i04/i12/i13/i15,
        # y no como una exclusion dentro de la condicion de arriba: una regla con un id
        # descontado dentro se lee como si el arnes se estuviera reservando una excepcion.
        if d["id"] == "i33":
            decidido_por = "sistema"
        # --- escalada de mas: i15 no requeria revision y el sistema la manda a umbral igualmente
        if d["id"] == "i15":
            decidido_por = "umbral"

        filas[d["message_id"]] = {
            "message_id": d["message_id"],
            "comunidad_id": d["comunidad_id"],
            "elemento_normalizado": d["elemento_esperado"],
            "imputacion": imputacion,
            "imputacion_rival": None,
            "fundamento": fundamento,
            "urgencia": d["urgencia_esperada"],
            "requiere_junta": d["requiere_junta_esperada"],
            "plazos_activos": [{"tipo": t} for t in plazos],
            "confianza": 0.8,
            "umbral_aplicado": 0.7,
            "accion": "archivado",
            "decidido_por": decidido_por,
        }

    # Ya no se fuerza ningun "intruso" (caso excluido que aparece igualmente en la tabla):
    # hoy ningun caso lleva esperado_en_tabla=false, asi que no hay nada que excluir. El informe
    # conserva ese aviso por si en el futuro se excluye alguno.
    return filas


def informe(dataset, filas):
    evaluables = [d for d in dataset if d.get("esperado_en_tabla", True)]
    excluidos = [d for d in dataset if not d.get("esperado_en_tabla", True)]
    total = len(evaluables)

    # ============================================================ 1. Cobertura
    faltantes = [d["id"] for d in evaluables if d["message_id"] not in filas]
    cubiertos = total - len(faltantes)
    print("=== 1. Cobertura ===")
    print(f"{cubiertos} de {total} incidencias esperadas en tabla aparecen en `incidencias`")
    if faltantes:
        print(f"FALTAN (el workflow no las proceso): {', '.join(faltantes)}")
    else:
        print("Cobertura completa sobre la poblacion evaluable.")
    presentes_excluidos = [d["id"] for d in excluidos if d["message_id"] in filas]
    print(f"\n{len(excluidos)} casos excluidos por diseno (sin comunidad identificable o "
          f"administrativos, no generan incidencia tecnica): no cuentan para cobertura ni acierto.")
    if presentes_excluidos:
        print(f"INFORMATIVO (no es fallo de este arnes): {len(presentes_excluidos)} de esos "
              f"casos SI aparecen en la tabla igualmente: {', '.join(presentes_excluidos)}. "
              f"Puede ser una decision valida del workflow (p. ej. archivarlos igualmente); "
              f"revisar manualmente si procede.")

    # ============================================================ 2. Acierto de imputacion
    correctos = 0
    correctos_no_amb = total_no_amb = 0
    correctos_amb = total_amb = 0
    discrepancias = []
    for d in evaluables:
        fila = filas.get(d["message_id"])
        obtenida = fila["imputacion"] if fila else "AUSENTE"
        acierto = obtenida == d["imputacion_esperada"]
        correctos += acierto
        if d["ambiguo"]:
            total_amb += 1
            correctos_amb += acierto
        else:
            total_no_amb += 1
            correctos_no_amb += acierto
        if not acierto:
            discrepancias.append((d["id"], d["imputacion_esperada"], obtenida, d["seccion_rubrica"]))

    print("\n=== 2. Acierto de imputacion ===")
    print(f"Global: {correctos} de {total} ({correctos / total:.1%})")
    p_no_amb = correctos_no_amb / total_no_amb if total_no_amb else 0
    p_amb = correctos_amb / total_amb if total_amb else 0
    print(f"No ambiguos: {correctos_no_amb} de {total_no_amb} ({p_no_amb:.1%})")
    print(f"Ambiguos:    {correctos_amb} de {total_amb} ({p_amb:.1%})  <- el numero interesante")

    # ============================================================ 3. Fundamento equivocado
    # Solo tiene sentido comprobar el fundamento cuando la imputacion ya salio correcta (si la
    # imputacion esta mal, el fundamento tambien lo esta por definicion y no aporta un fallo
    # nuevo) y cuando el dataset fija una norma esperada.
    evaluables_fundamento = 0
    fundamento_mal = []
    for d in evaluables:
        if not d["fundamento_esperado"]:
            continue
        fila = filas.get(d["message_id"])
        if not fila or fila["imputacion"] != d["imputacion_esperada"]:
            continue
        evaluables_fundamento += 1
        principal_esperada = normalizar_norma(d["fundamento_esperado"][0]["norma"])
        obtenidas = {normalizar_norma(f.get("norma")) for f in (fila["fundamento"] or [])
                     if isinstance(f, dict)}
        if principal_esperada not in obtenidas:
            fundamento_mal.append((d["id"], d["fundamento_esperado"][0]["norma"],
                                    [f.get("norma") for f in (fila["fundamento"] or [])]))

    print("\n=== 3. Fundamento equivocado con imputacion correcta ===")
    print(f"{len(fundamento_mal)} de {evaluables_fundamento} casos con imputacion acertada citan "
          f"una norma distinta a la esperada (bucket propio, no cuenta como fallo de imputacion).")
    for id_, esperada, obtenidas in fundamento_mal:
        print(f"  {id_}: esperaba '{esperada}', obtuvo {obtenidas}")

    # ============================================================ 4. Recall de plazos
    con_plazo_esperado = [d for d in evaluables if d["plazos_esperados"]]
    plazos_detectados = 0
    plazos_perdidos = []
    for d in con_plazo_esperado:
        fila = filas.get(d["message_id"])
        tipos_obtenidos = tipos_de_plazos(fila["plazos_activos"]) if fila else set()
        if set(d["plazos_esperados"]) & tipos_obtenidos:
            plazos_detectados += 1
        else:
            plazos_perdidos.append(d["id"])

    sin_plazo_esperado = [d for d in evaluables if not d["plazos_esperados"]]
    falsos_positivos_plazo = []
    for d in sin_plazo_esperado:
        fila = filas.get(d["message_id"])
        if fila and tipos_de_plazos(fila["plazos_activos"]):
            falsos_positivos_plazo.append(d["id"])

    print("\n=== 4. Recall de plazos ===")
    print(f"Recall: {plazos_detectados} de {len(con_plazo_esperado)} plazos esperados "
          f"aparecen en plazos_activos ({plazos_detectados / len(con_plazo_esperado):.1%})"
          if con_plazo_esperado else "Recall: no hay casos con plazo esperado en el dataset.")
    if plazos_perdidos:
        print(f"PLAZOS PERDIDOS (derrama potencial si esto pasa en produccion): {', '.join(plazos_perdidos)}")
    print(f"Falsos positivos: {len(falsos_positivos_plazo)} de {len(sin_plazo_esperado)} casos "
          f"sin plazo esperado activaron uno igualmente (cuesta una revision de mas, no una derrama).")
    if falsos_positivos_plazo:
        print(f"  {', '.join(falsos_positivos_plazo)}")

    # ============================================================ 5. Escalados y discrepancias
    con_revision_esperada = [d for d in evaluables if d.get("revision_esperada")]
    sin_revision_esperada = [d for d in evaluables if not d.get("revision_esperada")]
    escalados_por_via = {}
    escalados_ids = set()
    for d in evaluables:
        fila = filas.get(d["message_id"])
        via = fila["decidido_por"] if fila else None
        # Lo que decide si un caso acaba en una persona es la ACCION, no la vía. Un caso puede
        # llevar decidido_por='sistema' (el modelo no dudaba y no había cláusula) y aun así ir a
        # revisión porque su imputación no tiene automatismo asociado: no_aplica es el caso claro.
        # Contar solo por vía marcaba i14, i36 e i39 como escaladas perdidas cuando las tres
        # estaban en la cola de revisión con accion='revision_administrador'.
        accion = fila["accion"] if fila else None
        if accion == "revision_administrador" or via in ("umbral", "humano", "compuerta", "estatutos"):
            escalados_ids.add(d["id"])
            escalados_por_via[via] = escalados_por_via.get(via, 0) + 1

    escalados_de_mas = [d["id"] for d in sin_revision_esperada if d["id"] in escalados_ids]
    escalados_perdidos = [d["id"] for d in con_revision_esperada if d["id"] not in escalados_ids]

    print("\n=== 5. Escalados y discrepancias ===")
    print(f"Total escalados a revision humana: {len(escalados_ids)} de {total}")
    for via, n in sorted(escalados_por_via.items()):
        print(f"  via '{via}': {n}")
    print(f"Escalados de mas (revision_esperada=false pero se escalo igualmente): "
          f"{len(escalados_de_mas)}  {escalados_de_mas}")
    print(f"Escaladas PERDIDAS (revision_esperada=true pero NO se escalo -- la rubrica seccion 6 "
          f"o 3.9.3 exige revision y el sistema decidio solo): "
          f"{len(escalados_perdidos)}  {escalados_perdidos}")
    print(f"\nDiscrepancias de imputacion ({len(discrepancias)}):")
    if not discrepancias:
        print("  Ninguna.")
    for id_, esperada, obtenida, seccion in discrepancias:
        print(f"  {id_.ljust(5)} | esperada={str(esperada).ljust(10)} | obtenida={str(obtenida).ljust(10)} "
              f"| rubrica {seccion}")

    return {
        "total": total,
        "cubiertos": cubiertos,
        "faltantes": faltantes,
        "correctos": correctos,
        "correctos_no_amb": correctos_no_amb,
        "total_no_amb": total_no_amb,
        "correctos_amb": correctos_amb,
        "total_amb": total_amb,
        "discrepancias": discrepancias,
        "evaluables_fundamento": evaluables_fundamento,
        "fundamento_mal": fundamento_mal,
        "con_plazo_esperado": len(con_plazo_esperado),
        "plazos_detectados": plazos_detectados,
        "plazos_perdidos": plazos_perdidos,
        "falsos_positivos_plazo": falsos_positivos_plazo,
        "escalados_total": len(escalados_ids),
        "escalados_por_via": escalados_por_via,
        "escalados_de_mas": escalados_de_mas,
        "escalados_perdidos": escalados_perdidos,
        "excluidos": len(excluidos),
        "presentes_excluidos": presentes_excluidos,
    }


def verificar_dry_run(m):
    """Asserts estructurales contra el conjunto sintetico de construir_resultados_sinteticos():
    si alguien rompe el calculo de alguna seccion, esto falla con un mensaje concreto.

    Los totales (45, 36/9, etc.) están calculados sobre dataset.jsonl EXACTAMENTE como es hoy
    (45 casos, ninguno excluido, reparto ambiguo/no-ambiguo fijo). Si alguien añade o quita casos del
    dataset sin tocar este fichero, estos asserts fallarán -- y el mensaje lo dice explícitamente
    para no hacer perder tiempo pensando que construir_resultados_sinteticos() se rompió cuando
    lo que cambió fue el propio dataset."""
    assert m["total"] == 45, (
        f"poblacion evaluable = {m['total']}, se esperaban 45: o cambio el numero de casos "
        f"esperado_en_tabla=true en dataset.jsonl, o hay un bug en informe(). Si fue lo primero, "
        f"actualiza este numero (y los de mas abajo); no asumas que es un bug.")
    assert m["cubiertos"] == 45 and m["faltantes"] == [], "el sintetico deberia cubrir todas las esperadas"
    assert m["excluidos"] == 0, (
        f"casos excluidos (esperado_en_tabla=false) = {m['excluidos']}, se esperaban 0: revisa si "
        f"cambio ese campo en dataset.jsonl antes de asumir un bug.")
    assert m["presentes_excluidos"] == [], (
        "hoy ningun caso del dataset lleva esperado_en_tabla=false, asi que no puede haber "
        "excluidos presentes en la tabla; si esto falla, alguien volvio a excluir un caso.")
    assert m["correctos"] == 45 - 2, (
        f"construir_resultados_sinteticos() fuerza exactamente 2 fallos de imputacion (i17, i04); "
        f"fallan {45 - m['correctos']}. Si el total evaluable (45) no cambio, esto es un bug real.")
    assert m["total_no_amb"] == 36 and m["total_amb"] == 9, (
        f"reparto ambiguo/no-ambiguo = {m['total_no_amb']}/{m['total_amb']}, se esperaba 36/9: "
        f"si el dataset cambio de contenido ambiguo, actualiza este numero en vez de investigar un bug.")
    assert m["correctos_no_amb"] == 35, "i17 (no-ambiguo, forzado a fallar) deberia dejar 35 de 36 correctos"
    assert m["correctos_amb"] == 8, "i04 (ambiguo, forzado a fallar) deberia dejar 8 de 9 correctos"
    assert {d[0] for d in m["discrepancias"]} == {"i17", "i04"}, (
        "las unicas discrepancias forzadas por construir_resultados_sinteticos() son i17 e i04")
    assert m["evaluables_fundamento"] >= 1, "deberia haber al menos un caso evaluable de fundamento"
    assert [f[0] for f in m["fundamento_mal"]] == ["i07"], "i07 es el unico fundamento forzado a fallar"
    assert m["con_plazo_esperado"] == 3, (
        f"casos con plazo esperado = {m['con_plazo_esperado']}, se esperaban 3 (i05, i11, i12): "
        f"si se añadio un caso con plazo al dataset, actualiza este numero.")
    assert m["plazos_detectados"] == 2, "i12 esta forzado a perder su plazo, deberian quedar 2 de 3"
    assert "i12" in m["plazos_perdidos"], "i12 deberia estar en plazos perdidos"
    assert m["falsos_positivos_plazo"] == ["i13"], "i13 es el unico falso positivo de plazo forzado"
    assert "i15" in m["escalados_de_mas"], "i15 esta forzado a escalar de mas (revision_esperada=false)"
    assert m["escalados_perdidos"] == ["i33"], "i33 esta forzado a NO escalar pese a revision_esperada=true"
    print("\nVerificacion estructural del dry-run: OK (cobertura, acierto, fundamento, plazos y escalados cuadran).")


def main():
    ap = argparse.ArgumentParser(description="Evalua el triage de incidencias contra el dataset etiquetado.")
    ap.add_argument("--umbral-acierto", type=float, default=0.85,
                     help="acierto minimo exigido sobre los casos NO ambiguos (default: 0.85)")
    ap.add_argument("--dataset", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "dataset.jsonl"))
    ap.add_argument("--dsn", default=None, help="cadena de conexion libpq completa; si se omite se construye desde PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD")
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
        dsn = construir_dsn(args)
        try:
            filas = leer_incidencias(dsn)
        except psycopg2.errors.UndefinedTable:
            print("La tabla incidencias no existe todavia. Ejecuta init-fincas-tables.sql y "
                  "seed-comunidades.sql, levanta el workflow de n8n y luego "
                  "python3 seed_incidencias.py.")
            sys.exit(1)
        except psycopg2.OperationalError as e:
            print(f"No se pudo conectar a Postgres ({dsn.split('password=')[0]}...): {e}")
            sys.exit(1)
        metricas = informe(dataset, filas)

    try:
        assert metricas["cubiertos"] == metricas["total"], (
            f"cobertura incompleta: {metricas['cubiertos']} de {metricas['total']}")
        acierto_no_amb = metricas["correctos_no_amb"] / metricas["total_no_amb"]
        assert acierto_no_amb > args.umbral_acierto, (
            f"acierto en no-ambiguos {acierto_no_amb:.1%} no supera el umbral {args.umbral_acierto:.1%}")
    except AssertionError as e:
        print(f"\nFALLO: {e}")
        sys.exit(1)

    print(f"\nOK: cobertura completa y acierto en no-ambiguos {acierto_no_amb:.1%} "
          f"> umbral {args.umbral_acierto:.1%}")


if __name__ == "__main__":
    main()
