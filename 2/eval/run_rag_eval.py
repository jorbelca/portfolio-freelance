#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Arnés de evaluación del RAG de estatutos (Demo B): convierte eval/rag_casos.jsonl (12 casos)
en una comprobación ejecutable contra la tabla `documentos_comunidad` de Postgres.

QUÉ MIDE Y QUÉ NO -- léase antes de interpretar cualquier "OK" de este script
------------------------------------------------------------------------------
Esto mide RECUPERACIÓN (retrieval), no generación. Consulta pgvector directamente replicando
lo que hace el nodo `Cargar Estatutos de la Comunidad` de "Tarea B1 - Triage Incidencias.json"
(vectorStorePGVector en mode='load'); no hay ningún LLM redactando una respuesta. Por tanto:
  - Este script NO comprueba si el chat contesta bien en prosa, si cita el artículo con el
    formato correcto, ni si declara "no tengo información suficiente" ante una trampa -- eso
    ocurre en el paso de generación, aguas abajo de lo que aquí se consulta, y está fuera de
    alcance a propósito (es determinista, rápido, gratis y la afirmación que hay que demostrar
    -- aislamiento entre comunidades -- vive entera en el retrieval).
  - Lo que SÍ demuestra: que la consulta filtrada por comunidad_id nunca devuelve fragmentos de
    otra comunidad (aserción 3, la que de verdad importa), que el fragmento que debería
    sustentar cada respuesta está entre lo recuperado (aserciones 1 y 2), y que la premisa de
    las dos preguntas trampa (r11, r12) sigue siendo cierta sobre el corpus actual (aserción 4).

REPLICACIÓN DE B1 (verificado leyendo el nodo y el código fuente dentro del contenedor de n8n,
no supuesto) -- ver `Tarea B1 - Triage Incidencias.json`, nodo "Cargar Estatutos de la
Comunidad":
  - tabla: documentos_comunidad. topK: 12. Columnas (defaults de VectorStorePGVector, el nodo no
    las sobreescribe): id, embedding, text, metadata (jsonb). distanceStrategy: cosine.
  - filtro: metadata->>'comunidad_id' = <comunidad_id resuelta del email>. Se aplica en el WHERE
    de la consulta SQL, no en Python después de traer filas -- por construcción, ninguna fila de
    otra comunidad puede volver de esta consulta si el filtro está bien puesto y los datos están
    bien etiquetados. Por eso la aserción 3 tal cual la pide B1 es, en cierto sentido, una prueba
    de que "WHERE funciona": un guardia de regresión necesario pero no suficiente. Este script
    añade una segunda comprobación (3b) que SÍ puede fallar de verdad: busca cada fragmento_clave
    en TODO el corpus sin filtro y comprueba en qué comunidad(es) aparece.
  - SQL exacto reconstruido desde @langchain/community/dist/vectorstores/pgvector.js dentro del
    contenedor (ExtendedPGVectorStore.searchPostgres): `SELECT *, "embedding" <=> $vector AS
    "_distance" FROM documentos_comunidad WHERE metadata->>'comunidad_id' = $filtro ORDER BY
    "_distance" ASC LIMIT $topK`. Este script emite la misma consulta (mismo operador <=>, mismo
    WHERE, mismo ORDER BY, mismo LIMIT); los marcadores de posición van en otro orden porque los
    arma psycopg2, no porque el comportamiento cambie.
  - metadata realmente almacenada (comprobado con SELECT, no supuesto): solo comunidad_id,
    documento (literalmente "Escritura y Estatutos" en las tres comunidades, no distingue nada),
    pagina y loc. NO se guarda el nombre de fichero de origen. Por eso "documento correcto"
    (aserción 1) no puede comparar contra el string `documento_esperado` de rag_casos.jsonl tal
    cual: se traduce comunidad_id -> nombre de fichero real leyendo comunidades/*.md, y se
    valida esa traducción contra el dataset al cargar (ver cargar_casos). Con eso, "documento
    correcto" se reduce a "la consulta filtrada devolvió al menos 1 fragmento" -- que sigue
    siendo una comprobación real (detecta un topK/filtro roto o una comunidad sin estatutos
    cargados), solo que no por comparación de nombre de fichero.
  - dato empírico importante para leer los resultados con la cabeza fría: el corpus tiene 12/8/11
    fragmentos por comunidad (CDP-001/002/003) y topK=12. Como topK >= fragmentos de CUALQUIER
    comunidad individual, la consulta filtrada devuelve SIEMPRE el 100% de los fragmentos de esa
    comunidad, haya o no similitud semántica real con la pregunta. Esto no invalida las
    aserciones 1/2/3a (siguen comprobando que el dato existe y está bien etiquetado), pero sí
    quiere decir que estos 12 casos NO ejercitan la calidad del ranking semántico -- solo la de
    la partición por comunidad y la del contenido del corpus. El script lo señala en su salida
    cada vez que aplica.

EMBEDDINGS DE CONSULTA -- variable de entorno GEMINI_API_KEY (obligatoria para las aserciones 1
y 2 con ranking real y para el contraste 3c; el resto del script funciona sin ella, ver abajo)
------------------------------------------------------------------------------
El nodo `Embeddings Google Gemini` de B1 no fija ningún parámetro (confirmado leyendo
EmbeddingsGoogleGemini.node.js dentro del contenedor), así que usa su default:
modelName='models/gemini-embedding-001', sin taskType. Ese modelo por defecto emite vectores de
3072 dimensiones, que es justo lo que tiene `documentos_comunidad.embedding` (vector(3072),
comprobado con vector_dims()) -- así que es el modelo correcto, no una suposición. Este script
llama al mismo endpoint REST que usa la librería @google/generative-ai por debajo
(POST {host}/v1beta/models/gemini-embedding-001:embedContent, header x-goog-api-key, sin
taskType) usando solo la librería estándar (urllib), sin añadir dependencias nuevas.

La clave se lee EXCLUSIVAMENTE de la variable de entorno GEMINI_API_KEY (ya documentada en
1/.env.example). Este script, igual que eval/run_eval.py, NO lee ningún .env. Si quieres
ejecutar las aserciones que dependen de embeddings:

    export GEMINI_API_KEY="tu-clave"
    python3 eval/run_rag_eval.py

Si GEMINI_API_KEY no está presente, o la API la rechaza (clave inválida, cuota agotada, sin
red), el script NO se detiene: gracias a que topK cubre el 100% de cada comunidad (ver arriba),
las aserciones 1, 2, 3a y 3b siguen siendo válidas usando una consulta de respaldo ordenada por
id en vez de por distancia coseno (mismo WHERE, mismo LIMIT, mismo conjunto de filas resultante
para este corpus -- solo cambia el ORDEN, y ninguna de esas aserciones depende del orden). Lo
único que se pierde sin clave es la aserción 3c (contraste sin filtro: cuántos de los vecinos
más cercanos por embedding real caerían en otra comunidad si el filtro no existiera) -- es
evidencia adicional, no bloqueante, y el informe final lo marca como PARCIAL cuando falta.

Uso: run_rag_eval.py [--dry-run] [--umbral-acierto 0.85] [--topk 12] [--dataset F] [--dsn DSN]
DSN por variables de entorno si no se pasa --dsn: PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD
(defaults 127.0.0.1/5432/n8n/n8n_user), mismo convenio que eval/run_eval.py y 2/test_dedup.py.
"""
import argparse
import json
import os
import re
import sys
import unicodedata
import urllib.error
import urllib.request

try:
    import psycopg2
    import psycopg2.errors
except ImportError:
    psycopg2 = None

GEMINI_HOST = "https://generativelanguage.googleapis.com"
GEMINI_MODEL = "models/gemini-embedding-001"  # default real del nodo n8n, ver cabecera

# Términos extraídos a mano de la propia `pregunta` de cada caso trampa (no de `nota`, que es
# prosa libre pensada para un lector humano y no debería dictar el comportamiento del código).
# Si alguno de estos términos apareciera en el corpus, la trampa habría dejado de ser trampa.
TERMINOS_PREMISA_TRAMPA = {
    "r11": ["aseguradora", "poliza"],  # "compañía aseguradora... número de póliza"
    "r12": ["decenal"],  # "garantía decenal... Ley de Ordenación de la Edificación"
}


class ErrorEmbedding(Exception):
    """Fallo al pedir un embedding de consulta a Gemini. El mensaje nunca incluye la clave."""


# ============================================================ Normalización y comparación de texto

def normalizar(cadena):
    """minúsculas + sin tildes/diacríticos + espacios colapsados, para que una comparación de
    substring no falle por un acento o un espacio doble. NFKD también convierte 'º' (ordinal) en
    'o' plano, lo cual conviene: aplicado por igual a ambos lados de cada comparación, sigue
    siendo una comparación estricta, solo que insensible a esa variación tipográfica."""
    if not cadena:
        return ""
    forma = unicodedata.normalize("NFKD", cadena)
    sin_marcas = "".join(c for c in forma if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sin_marcas.lower()).strip()


def segmentos_de(fragmento_clave):
    """Algunos fragmento_clave del dataset elidan texto intermedio con '...' (p. ej. r08: es una
    elisión de quien escribió el caso, no texto literal del documento -- comprobado contra
    comunidades/CDP-003: el original es una frase continua sin puntos suspensivos). Partimos por
    ese separador y exigimos que TODOS los trozos aparezcan en el mismo fragmento recuperado, en
    vez de relajar la comparación a "aparece el primer trozo" (perdería rigor) o buscar la frase
    completa con los puntos suspensivos literales (nunca va a aparecer así en el corpus real)."""
    trozos = re.split(r"\.{3}|…", fragmento_clave)
    return [normalizar(t) for t in trozos if normalizar(t)]


def contiene_fragmento_clave(texto_normalizado, fragmento_clave):
    return all(seg in texto_normalizado for seg in segmentos_de(fragmento_clave))


def es_forma_articulo(clausula_esperada):
    """Distingue las citas 'Artículo Nº' (aparecen literalmente en el corpus como encabezado,
    ej. '**Artículo 2º. Elementos comunes.**') de las citas 'Expone N' / 'Expone N, ...'
    (r03/r04/r07: el corpus solo tiene '**IV.**' o '**III.**' sueltos bajo un encabezado
    '### EXPONE' aparte -- comprobado con grep, la cadena combinada no existe literalmente). Solo
    la primera forma es comprobable por substring literal; la segunda se reporta como
    informativa, no se usa para pasar/fallar nada."""
    return bool(re.match(r"^articulo \d+o$", normalizar(clausula_esperada)))


def documento_correcto(fragmentos):
    """Aserción 1: al menos un fragmento volvió de la consulta filtrada. Con la metadata
    realmente almacenada (sin nombre de fichero, ver cabecera) es lo más fiel que se puede
    comprobar sin inventar un campo que no existe."""
    return len(fragmentos) >= 1


def fila_viola_aislamiento(comunidad_de_la_fila, comunidad_esperada):
    return comunidad_de_la_fila != comunidad_esperada


def ids_de_pares_de_fuga(casos):
    """Un 'par de fuga' no se marca a mano ni se lee de `nota` (prosa libre, frágil de parsear):
    se deriva mecánicamente tal y como los define el enunciado -- dos preguntas literalmente
    idénticas dirigidas a comunidades distintas. Se agrupa por `pregunta` exacta; cualquier grupo
    con más de una comunidad_id distinta es un par de fuga. Verificado contra el dataset real:
    esto aísla exactamente {r01,r02} y {r03,r04}, sin necesidad de tocar el texto de `nota`."""
    por_pregunta = {}
    for c in casos:
        por_pregunta.setdefault(c["pregunta"], []).append(c)
    pares = set()
    for grupo in por_pregunta.values():
        if len({c["comunidad_id"] for c in grupo}) > 1:
            pares.update(c["id"] for c in grupo)
    return pares


def vector_a_literal(vector):
    return "[" + ",".join(repr(x) for x in vector) + "]"


# ============================================================ Carga y validación del dataset

def construir_mapa_documentos(dir_comunidades):
    """comunidad_id -> nombre de fichero real, leído de comunidades/*.md. Necesario porque la
    metadata ingerida en Postgres NO guarda el nombre de fichero de origen (ver cabecera)."""
    mapa = {}
    for nombre in sorted(os.listdir(dir_comunidades)):
        if not nombre.endswith(".md"):
            continue
        m = re.match(r"^(CDP-\d+)", nombre)
        assert m, f"fichero en comunidades/ sin prefijo CDP-NNN reconocible: {nombre}"
        comunidad_id = m.group(1)
        assert comunidad_id not in mapa, (
            f"dos ficheros en comunidades/ para {comunidad_id}: '{mapa[comunidad_id]}' y '{nombre}'")
        mapa[comunidad_id] = nombre
    return mapa


def cargar_casos(path, mapa_documentos):
    filas = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    ids = [f["id"] for f in filas]
    assert len(ids) == len(set(ids)), "hay ids duplicados en rag_casos.jsonl"
    campos_de_respuesta = ("documento_esperado", "clausula_esperada", "fragmento_clave")
    for f in filas:
        assert isinstance(f.get("respondible"), bool), f"{f['id']}: 'respondible' deberia ser boolean"
        if f["respondible"]:
            for campo in campos_de_respuesta:
                assert f.get(campo), f"{f['id']}: respondible=true pero '{campo}' esta vacio/null"
            esperado_por_comunidad = mapa_documentos.get(f["comunidad_id"])
            assert esperado_por_comunidad, (
                f"{f['id']}: comunidad_id '{f['comunidad_id']}' no tiene fichero en comunidades/")
            assert f["documento_esperado"] == esperado_por_comunidad, (
                f"{f['id']}: documento_esperado='{f['documento_esperado']}' no coincide con el "
                f"fichero real de {f['comunidad_id']} en comunidades/ ('{esperado_por_comunidad}'). "
                f"Esto es un bug del dataset o del directorio, no del retrieval: arreglar antes de evaluar.")
        else:
            for campo in campos_de_respuesta:
                assert f.get(campo) is None, (
                    f"{f['id']}: respondible=false pero '{campo}' no es null ({f.get(campo)!r}) -- "
                    f"revisar si el caso dejo de ser una trampa")
    return filas


def verificar_premisa_trampas(casos, texto_normalizado_por_comunidad):
    """Comprueba que la premisa de cada trampa (respondible=false) sigue siendo cierta sobre el
    corpus actual: que los términos que delatarían una respuesta real (ver TERMINOS_PREMISA_
    TRAMPA) siguen ausentes. Esto es distinto de "el sistema declara que no sabe" (eso es
    generación, fuera de alcance): esto es "¿la trampa sigue siendo una trampa?", una
    comprobación de la propia fijación de datos, no del sistema evaluado."""
    resultados = []
    for c in casos:
        if c["respondible"]:
            continue
        terminos = TERMINOS_PREMISA_TRAMPA.get(c["id"], [])
        texto = texto_normalizado_por_comunidad.get(c["comunidad_id"], "")
        encontrados = [t for t in terminos if normalizar(t) in texto]
        resultados.append((c["id"], terminos, encontrados))
    return resultados


# ============================================================ Autotest de detectores (sin Postgres ni red)

def verificar_detectores():
    """Autotest de las funciones de detección con casos de mano mínimos, obviamente correctos
    por inspección. No toca Postgres ni red: se ejecuta siempre (dry-run y real), porque es
    instantáneo y da una garantía que los 12 casos reales NO pueden dar por sí solos -- la
    aserción de aislamiento tal como la pide B1 (3a) es tautológica sobre datos ya filtrados por
    SQL (ver cabecera): si un día SÍ hubiera una fuga real, hace falta saber que el código la
    marcaría. Aquí se prueba la función de detección en frío, con datos inventados a propósito
    para que SÍ puedan fallar, no el resultado ya-filtrado de aplicarla sobre los 12 casos."""
    assert fila_viola_aislamiento("CDP-002", "CDP-001") is True, "deberia marcar una fila de otra comunidad"
    assert fila_viola_aislamiento("CDP-001", "CDP-001") is False, "no deberia marcar una fila de la propia comunidad"

    frase_completa = normalizar(
        "los propietarios titulares de plaza y trastero, en proporcion al coeficiente que "
        "estos tengan adscrito, sin repercutirse a las viviendas sin garaje ni trastero")
    clave_con_elipsis = "titulares de plaza y trastero... sin repercutirse a las viviendas"
    assert contiene_fragmento_clave(frase_completa, clave_con_elipsis) is True, (
        "con los dos segmentos presentes en el mismo texto, deberia contar como encontrado")
    assert contiene_fragmento_clave(normalizar("titulares de plaza y trastero, y nada mas"),
                                     clave_con_elipsis) is False, (
        "si falta el segundo segmento, NO deberia contar como encontrado (no basta un segmento suelto)")

    assert documento_correcto([]) is False, "una lista vacia de fragmentos es un fallo de asercion 1"
    assert documento_correcto([{"comunidad_id": "CDP-001", "text": "x"}]) is True

    pares = ids_de_pares_de_fuga([
        {"id": "x1", "pregunta": "misma pregunta", "comunidad_id": "CDP-001"},
        {"id": "x2", "pregunta": "misma pregunta", "comunidad_id": "CDP-002"},
        {"id": "x3", "pregunta": "pregunta distinta", "comunidad_id": "CDP-003"},
    ])
    assert pares == {"x1", "x2"}, "el agrupador de pares de fuga no aisla bien por pregunta identica"

    print("Autotest de detectores (aislamiento, fragmento con elipsis, documento vacio, pares de "
          "fuga) sobre casos de mano: OK. Esto NO sustituye a los 12 casos reales, los complementa: "
          "prueba que el codigo SI sabe fallar cuando le toca.")


# ============================================================ Embeddings de consulta (Gemini)

def obtener_embedding(texto, api_key, timeout=30):
    """Replica _convertToContent()+embedContent() de @langchain/google-genai (mismo endpoint,
    mismo header x-goog-api-key, mismo cuerpo), leído directamente del código dentro del
    contenedor de n8n -- no es una suposición sobre cómo funciona la librería. No se fija
    taskType porque el nodo EmbeddingsGoogleGemini de n8n tampoco lo fija (parameters: {} en el
    workflow): dejarlo sin fijar es lo fiel a B1, no un descuido de este script."""
    cuerpo = json.dumps({
        "content": {"role": "user", "parts": [{"text": texto.replace("\n", " ")}]},
    }).encode("utf-8")
    url = f"{GEMINI_HOST}/v1beta/{GEMINI_MODEL}:embedContent"
    peticion = urllib.request.Request(url, data=cuerpo, method="POST", headers={
        "Content-Type": "application/json",
        "x-goog-api-key": api_key,
    })
    try:
        with urllib.request.urlopen(peticion, timeout=timeout) as resp:
            datos = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detalle = e.read().decode("utf-8", errors="replace")[:300]
        raise ErrorEmbedding(f"HTTP {e.code} de la API de Gemini (la clave nunca se imprime): {detalle}") from None
    except urllib.error.URLError as e:
        raise ErrorEmbedding(f"no se pudo contactar con la API de Gemini: {e.reason}") from None
    valores = (datos.get("embedding") or {}).get("values")
    if not valores:
        raise ErrorEmbedding(f"respuesta sin 'embedding.values': {json.dumps(datos)[:300]}")
    return valores


# ============================================================ Postgres

def construir_dsn(args):
    if args.dsn:
        return args.dsn
    host = os.environ.get("PGHOST", "127.0.0.1")
    port = os.environ.get("PGPORT", "5432")
    dbname = os.environ.get("PGDATABASE", "n8n")
    user = os.environ.get("PGUSER", "n8n_user")
    password = os.environ.get("PGPASSWORD", "")
    return f"host={host} port={port} dbname={dbname} user={user} password={password}"


def _filas_a_dicts(cur):
    cols = [c.name for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def contar_por_comunidad(cur):
    cur.execute("SELECT metadata->>'comunidad_id' AS comunidad_id, count(*) FROM documentos_comunidad GROUP BY 1")
    return {row[0]: row[1] for row in cur.fetchall()}


def obtener_todas_las_filas(cur):
    cur.execute("SELECT id, text, metadata->>'comunidad_id' AS comunidad_id FROM documentos_comunidad")
    return _filas_a_dicts(cur)


def recuperar_filtrado(cur, comunidad_id, topk, vector):
    """Replica la consulta de B1 (ver cabecera). Si `vector` es None, usa ORDER BY id como
    respaldo sin embeddings: mismo WHERE, mismo LIMIT, mismo conjunto de filas resultante para
    este corpus (topK >= fragmentos por comunidad, ver cabecera) -- solo cambia el orden."""
    if vector is not None:
        cur.execute(
            'SELECT id, text, metadata->>\'comunidad_id\' AS comunidad_id, '
            '"embedding" <=> %s::vector AS distancia '
            "FROM documentos_comunidad WHERE metadata->>'comunidad_id' = %s "
            "ORDER BY distancia ASC LIMIT %s",
            (vector_a_literal(vector), comunidad_id, topk),
        )
    else:
        cur.execute(
            "SELECT id, text, metadata->>'comunidad_id' AS comunidad_id, NULL AS distancia "
            "FROM documentos_comunidad WHERE metadata->>'comunidad_id' = %s "
            "ORDER BY id LIMIT %s",
            (comunidad_id, topk),
        )
    return _filas_a_dicts(cur)


def recuperar_sin_filtro(cur, vector, topk):
    """Aserción 3c (contraste, solo con embeddings): el mismo topK por distancia coseno pero SIN
    el filtro de comunidad_id. Sirve para demostrar que el filtro es necesario de verdad: cuenta
    cuántos de los vecinos más cercanos por embedding puro caerían en otra comunidad si el
    filtro no existiera."""
    cur.execute(
        'SELECT id, metadata->>\'comunidad_id\' AS comunidad_id, "embedding" <=> %s::vector AS distancia '
        "FROM documentos_comunidad ORDER BY distancia ASC LIMIT %s",
        (vector_a_literal(vector), topk),
    )
    return _filas_a_dicts(cur)


# ============================================================ Informe

def informe(casos, contexto):
    """Imprime el informe por secciones numeradas y devuelve un dict de métricas para el assert
    final y para verificar_dry_run(). `contexto` trae todo lo ya calculado (fragmentos por caso,
    hallazgos de fuga real, etc.) para que esta función solo agregue y presente, sin volver a
    tocar Postgres/red -- igual que informe() en run_eval.py separa cálculo de presentación."""
    respondibles = [c for c in casos if c["respondible"]]
    trampas = [c for c in casos if not c["respondible"]]
    ids_pares_fuga = ids_de_pares_de_fuga(casos)

    print("Recordatorio de alcance: este informe mide RECUPERACION (retrieval) sobre pgvector, "
          "replicando el filtro y la consulta reales de B1. NO mide la calidad de la respuesta "
          "redactada por el LLM ni si el sistema declara correctamente 'no tengo informacion' "
          "ante una trampa -- eso es generacion, fuera de alcance de este script (ver cabecera).")

    # ============================================================ 1. Cobertura y consistencia
    conteo = contexto["conteo_por_comunidad"]
    topk = contexto["topk"]
    print("\n=== 1. Cobertura y consistencia del dataset ===")
    print(f"{len(casos)} casos ({len(respondibles)} respondibles, {len(trampas)} trampas). "
          f"{len(ids_pares_fuga)} casos forman parte de un par de fuga (preguntas identicas, "
          f"comunidad distinta): {sorted(ids_pares_fuga)}")
    print(f"Fragmentos por comunidad en documentos_comunidad: {conteo or '(tabla vacia)'}")
    if conteo and topk >= max(conteo.values(), default=0):
        print(f"AVISO DE ALCANCE: topK={topk} cubre el 100% de fragmentos de cada comunidad "
              f"(maximo actual: {max(conteo.values())}). La consulta filtrada devuelve SIEMPRE "
              f"todo el corpus de la comunidad, haya o no relevancia semantica real: las "
              f"aserciones 1/2/3a comprueban existencia y etiquetado correcto, no calidad del "
              f"ranking. Solo la asercion 3c (si hay embeddings) ejercita el ranking de verdad.")
    fuente = contexto.get("fuente_embeddings", "sintetico (--dry-run)")
    print(f"Fuente de embeddings de consulta: {fuente}")

    # ============================================================ 2. Aislamiento por filtro SQL (3a)
    print("\n=== 2. Aislamiento -- filtro SQL de B1 (aserción 3a) ===")
    print("Aviso: esta comprobacion es un guardia de regresion, no un descubrimiento -- el WHERE "
          "de la consulta ya impide por construccion que vuelva una fila de otra comunidad si el "
          "filtro esta bien puesto y los datos bien etiquetados. Ver aserción 3b para la prueba "
          "que SI puede fallar de verdad.")
    fallos_3a = []
    for c in casos:
        for frag in contexto["fragmentos_por_caso"][c["id"]]:
            if fila_viola_aislamiento(frag["comunidad_id"], c["comunidad_id"]):
                fallos_3a.append((c["id"], c["comunidad_id"], frag["comunidad_id"], frag.get("id")))
    print(f"Fragmentos ajenos entre los recuperados en los {len(casos)} casos: {len(fallos_3a)}")
    for id_, esperada, obtenida, frag_id in fallos_3a:
        print(f"  FALLO GRAVE DE AISLAMIENTO: {id_} (comunidad {esperada}) recupero un fragmento "
              f"(id={frag_id}) de la comunidad {obtenida}")

    # ============================================================ 3. Aislamiento real, sin filtro (3b)
    print("\n=== 3. Aislamiento -- busqueda sin filtro en todo el corpus (aserción 3b, la que importa) ===")
    print("Para cada fragmento_clave (solo casos respondible=true) se busca en las 31 filas de "
          "TODAS las comunidades, sin el filtro de comunidad_id, y se comprueba en que "
          "comunidad(es) aparece de verdad. Es la unica de las cuatro aserciones que puede "
          "detectar una fuga real (contenido duplicado o mal etiquetado entre comunidades), y no "
          "necesita embeddings.")
    fallos_3b_fuga = []
    fallos_3b_ausente = []
    informativos_3b = []
    for c in respondibles:
        encontradas = contexto["hallazgos_fuga_real"][c["id"]]
        propia = c["comunidad_id"] in encontradas
        otras = encontradas - {c["comunidad_id"]}
        if not propia:
            fallos_3b_ausente.append(c["id"])
            print(f"  {c['id']}: fragmento_clave NO aparece ni siquiera en su propia comunidad "
                  f"({c['comunidad_id']}) en todo el corpus -- posible problema real de corpus o "
                  f"de fijacion del caso, no un fallo de aislamiento (ver aserción 2 para el detalle).")
            continue
        if otras:
            if c["id"] in ids_pares_fuga:
                fallos_3b_fuga.append((c["id"], sorted(otras)))
                print(f"  FALLO GRAVE DE FUGA REAL: {c['id']} es mitad de un par de fuga y su "
                      f"fragmento_clave aparece tambien en {sorted(otras)}, no solo en "
                      f"{c['comunidad_id']}")
            else:
                informativos_3b.append((c["id"], sorted(otras)))
                print(f"  HALLAZGO DEL FIXTURE (no es un par de fuga disenado, pero es real): "
                      f"el fragmento_clave de {c['id']} es texto identico en {sorted(otras)} "
                      f"ademas de en {c['comunidad_id']} -- no cuenta como fallo (el caso no fue "
                      f"disenado para probar aislamiento y el filtro SQL sigue haciendo su "
                      f"trabajo), pero para ESTE caso concreto 'el fragmento correcto volvio' no "
                      f"distingue aislamiento correcto de una fuga: el mismo texto habria vuelto "
                      f"igual si el filtro hubiera aplicado la comunidad equivocada. Ver 'Que NO "
                      f"demuestra esta evaluacion' en eval/README.md.")
    if not fallos_3b_fuga and not fallos_3b_ausente:
        print("  Ninguna fuga real detectada en los pares disenados para eso, y todos los "
              "fragmento_clave respondible=true aparecen en su propia comunidad.")

    # ============================================================ 4. Documento correcto (aserción 1)
    print("\n=== 4. Documento correcto (aserción 1) ===")
    print("La metadata ingerida no guarda nombre de fichero (solo comunidad_id/documento/pagina/"
          "loc, ver cabecera), asi que esto se reduce a: la consulta filtrada por comunidad_id "
          "devolvio al menos un fragmento. La correspondencia comunidad_id <-> fichero ya se "
          "valido al cargar el dataset (cargar_casos), asi que un resultado no vacio SI implica "
          "que es el documento correcto.")
    fallos_doc = [c["id"] for c in respondibles if not documento_correcto(contexto["fragmentos_por_caso"][c["id"]])]
    print(f"Documento correcto: {len(respondibles) - len(fallos_doc)} de {len(respondibles)}")
    if fallos_doc:
        print(f"  FALLO: {fallos_doc} -- la consulta filtrada no devolvio ningun fragmento")

    # ============================================================ 5. Fragmento clave (aserción 2)
    print("\n=== 5. Fragmento clave (aserción 2, solo respondible=true) ===")
    fallos_frag = []
    aciertos_clausula_informativo = 0
    evaluables_clausula_informativo = 0
    for c in respondibles:
        textos = [normalizar(f["text"]) for f in contexto["fragmentos_por_caso"][c["id"]]]
        ok = any(contiene_fragmento_clave(t, c["fragmento_clave"]) for t in textos)
        if not ok:
            fallos_frag.append(c["id"])
        # clausula_esperada: comprobacion adicional informativa, no gatea nada. Solo se evalua
        # cuando la cita tiene la forma "Articulo Nº" (la unica que aparece literal en el
        # corpus, ver es_forma_articulo); la forma "Expone N" (r03/r04/r07) es una cita legible
        # para humanos que no existe como string combinado en el corpus, y se deja fuera.
        if c["clausula_esperada"] and es_forma_articulo(c["clausula_esperada"]):
            evaluables_clausula_informativo += 1
            if any(normalizar(c["clausula_esperada"]) in t for t in textos):
                aciertos_clausula_informativo += 1
    print(f"Fragmento clave presente: {len(respondibles) - len(fallos_frag)} de {len(respondibles)}")
    if fallos_frag:
        print(f"  FALLO: {fallos_frag} -- fragmento_clave no aparece (normalizado) en ningun "
              f"fragmento recuperado")
    print(f"INFORMATIVO -- clausula_esperada con forma 'Articulo Nº' tambien presente: "
          f"{aciertos_clausula_informativo} de {evaluables_clausula_informativo} "
          f"(no gatea el resultado; la forma 'Expone N' no es comprobable por substring, ver cabecera)")

    # ============================================================ 6. Trampas (aserción 4)
    print("\n=== 6. Trampas -- respondible=false (aserción 4) ===")
    print("documento_esperado/clausula_esperada/fragmento_clave son null en las dos trampas (ya "
          "validado al cargar el dataset): no hay contenido especifico que comprobar como "
          "ausente en lo recuperado. Lo unico verificable mecanicamente sobre estos dos casos es "
          "(a) el aislamiento general, ya cubierto en las secciones 2 y 3 arriba, y (b) que la "
          "PREMISA de la trampa sigue siendo cierta: que el corpus de su comunidad no contiene "
          "los terminos que delatarian una respuesta real. Esto NO comprueba si el sistema "
          "declara correctamente 'no tengo informacion' -- eso es generacion, fuera de alcance.")
    premisa_rota = []
    for id_, terminos, encontrados in contexto["premisas_trampas"]:
        print(f"  {id_}: terminos de prueba {terminos} -> "
              f"{'ENCONTRADOS ' + str(encontrados) + ' (premisa rota, revisar el corpus/caso)' if encontrados else 'ausentes del corpus (premisa intacta)'}")
        if encontrados:
            premisa_rota.append(id_)

    # ============================================================ 7. Contraste sin filtro (aserción 3c)
    print("\n=== 7. Contraste sin filtro (aserción 3c, informativa, requiere embeddings) ===")
    if contexto["embeddings_disponibles"]:
        print("Mismo topK por distancia coseno real, pero SIN el filtro de comunidad_id: mide si "
              "el embedding por si solo separaria las comunidades, o si el aislamiento depende "
              "por completo del filtro SQL (evidencia de que el filtro es necesario, no adorno).")
        for c in casos:
            r = contexto["contrafactual_por_caso"].get(c["id"])
            if r is None:
                print(f"  {c['id']}: no disponible (fallo puntual de embedding en este caso)")
                continue
            print(f"  {c['id']} ({c['comunidad_id']}): {r['otra_comunidad']} de {r['total']} "
                  f"vecinos mas cercanos por embedding puro pertenecen a OTRA comunidad")
    else:
        print(f"NO EVALUADA: {contexto.get('motivo_sin_embeddings', 'GEMINI_API_KEY no disponible')}. "
              f"No bloquea el resultado (es evidencia adicional), pero el resumen final se marca "
              f"como PARCIAL por esto.")

    # ============================================================ 8. Resumen
    total = len(casos)
    aciertos_doc_y_frag = len([c for c in respondibles
                                if c["id"] not in fallos_doc and c["id"] not in fallos_frag])
    print("\n=== 8. Resumen ===")
    print(f"Cobertura: {total} de {total} casos consultados sin excepcion")
    print(f"Aislamiento (3a, filtro SQL): {len(fallos_3a)} fallos")
    print(f"Aislamiento real (3b, sin filtro, solo pares de fuga): {len(fallos_3b_fuga)} fallos")
    print(f"Documento correcto (1): {len(respondibles) - len(fallos_doc)} de {len(respondibles)}")
    print(f"Fragmento clave (2): {len(respondibles) - len(fallos_frag)} de {len(respondibles)}")
    print(f"Documento+fragmento correctos a la vez: {aciertos_doc_y_frag} de {len(respondibles)}")
    print(f"Premisa de trampa rota: {len(premisa_rota)} de {len(trampas)}")
    if informativos_3b:
        print(f"AVISO DE ALCANCE: {[i for i, _ in informativos_3b]} tienen un fragmento_clave que "
              f"es texto identico en mas de una comunidad (ver seccion 3) -- para esos casos, un "
              f"acierto en la asercion 2 no distingue aislamiento correcto de una fuga real, "
              f"porque la respuesta esperada no es exclusiva de su comunidad. No es un fallo de "
              f"este arnes ni del filtro SQL; es una limitacion del fixture, documentada en "
              f"eval/README.md.")

    return {
        "total": total,
        "total_respondibles": len(respondibles),
        "total_trampas": len(trampas),
        "fallos_3a": fallos_3a,
        "fallos_3b_fuga": fallos_3b_fuga,
        "fallos_3b_ausente": fallos_3b_ausente,
        "informativos_3b": informativos_3b,
        "fallos_doc": fallos_doc,
        "fallos_frag": fallos_frag,
        "aciertos_doc_y_frag": aciertos_doc_y_frag,
        "premisa_rota": premisa_rota,
        "embeddings_disponibles": contexto["embeddings_disponibles"],
    }


# ============================================================ Camino real (Postgres + Gemini)

def ejecutar_real(casos, args, mapa_documentos):
    dsn = construir_dsn(args)
    if psycopg2 is None:
        print("Falta psycopg2 (pip install psycopg2-binary). Es la unica dependencia externa permitida.")
        sys.exit(1)
    try:
        conn = psycopg2.connect(dsn)
    except psycopg2.OperationalError as e:
        print(f"No se pudo conectar a Postgres ({dsn.split('password=')[0]}...): {e}")
        sys.exit(1)

    try:
        cur = conn.cursor()
        try:
            conteo_por_comunidad = contar_por_comunidad(cur)
            todas_las_filas = obtener_todas_las_filas(cur)
        except psycopg2.errors.UndefinedTable:
            conn.rollback()
            print("La tabla documentos_comunidad no existe todavia. Ejecuta init-fincas-tables.sql, "
                  "levanta B2 (Carga Estatutos) en n8n y sube los tres ficheros de comunidades/.")
            sys.exit(1)

        # Tabla vacia o sin filas para alguna comunidad: conteo_por_comunidad/todas_las_filas
        # quedan vacios o incompletos y el resto del pipeline lo propaga como 0 resultados por
        # caso (documento_correcto([]) -> False), no como excepcion -- verificado forzando
        # comunidad_id inexistentes, ver informe de verificacion.
        texto_normalizado_por_comunidad = {}
        for fila in todas_las_filas:
            texto_normalizado_por_comunidad.setdefault(fila["comunidad_id"], "")
            texto_normalizado_por_comunidad[fila["comunidad_id"]] += " " + normalizar(fila["text"])
        texto_normalizado_por_fila = [(f["comunidad_id"], normalizar(f["text"])) for f in todas_las_filas]

        api_key = os.environ.get("GEMINI_API_KEY")
        embeddings_disponibles = False
        motivo_sin_embeddings = None
        if not api_key:
            motivo_sin_embeddings = "GEMINI_API_KEY no esta exportada en el entorno"
        else:
            try:
                obtener_embedding(casos[0]["pregunta"], api_key)
                embeddings_disponibles = True
            except ErrorEmbedding as e:
                motivo_sin_embeddings = str(e)

        fragmentos_por_caso = {}
        contrafactual_por_caso = {}
        for c in casos:
            vector = None
            if embeddings_disponibles:
                try:
                    vector = obtener_embedding(c["pregunta"], api_key)
                except ErrorEmbedding as e:
                    print(f"  AVISO: fallo puntual de embedding en {c['id']} ({e}); se usa la "
                          f"consulta de respaldo ordenada por id solo para este caso.")
            fragmentos_por_caso[c["id"]] = recuperar_filtrado(cur, c["comunidad_id"], args.topk, vector)
            if embeddings_disponibles and vector is not None:
                filas_sin_filtro = recuperar_sin_filtro(cur, vector, args.topk)
                otra = sum(1 for f in filas_sin_filtro if f["comunidad_id"] != c["comunidad_id"])
                contrafactual_por_caso[c["id"]] = {"otra_comunidad": otra, "total": len(filas_sin_filtro)}
            else:
                contrafactual_por_caso[c["id"]] = None

        hallazgos_fuga_real = {}
        for c in casos:
            if not c["respondible"]:
                continue
            hallazgos_fuga_real[c["id"]] = {
                comunidad_id for comunidad_id, texto in texto_normalizado_por_fila
                if contiene_fragmento_clave(texto, c["fragmento_clave"])
            }

        premisas_trampas = verificar_premisa_trampas(casos, texto_normalizado_por_comunidad)

        contexto = {
            "mapa_documentos": mapa_documentos,
            "conteo_por_comunidad": conteo_por_comunidad,
            "topk": args.topk,
            "fragmentos_por_caso": fragmentos_por_caso,
            "hallazgos_fuga_real": hallazgos_fuga_real,
            "embeddings_disponibles": embeddings_disponibles,
            "motivo_sin_embeddings": motivo_sin_embeddings,
            "contrafactual_por_caso": contrafactual_por_caso,
            "premisas_trampas": premisas_trampas,
            "fuente_embeddings": (f"Gemini real ({GEMINI_MODEL})" if embeddings_disponibles
                                   else f"respaldo sin embeddings ({motivo_sin_embeddings})"),
        }
        return contexto
    finally:
        conn.close()


# ============================================================ Camino sintético (--dry-run)

def construir_contexto_sintetico(casos, mapa_documentos):
    """Contexto sintético para --dry-run: no toca Postgres ni red. Fuerza exactamente 1 error
    (r09 pierde su fragmento_clave) para que verificar_dry_run() pueda comprobar con asserts que
    la sección 5 cuenta lo que dice contar -- igual que run_eval.py fuerza i07/i17/i04/etc. Se
    deja el resto (aislamiento 3a/3b) limpio a propósito: esas dos SÍ tienen zero-tolerance en el
    gate final (ver main()), y forzar un fallo ahí haria que el --dry-run por defecto no pasara.
    La capacidad de detectar una fuga real se prueba por separado en verificar_detectores(), con
    datos de mano, no aquí."""
    fragmentos_por_caso = {}
    hallazgos_fuga_real = {}
    for c in casos:
        if c["respondible"]:
            texto = f"contexto sintetico que SI contiene: {c['fragmento_clave']}"
            if c["id"] == "r09":
                texto = "contexto sintetico generico, sin la frase que se busca"
            fragmentos_por_caso[c["id"]] = [{"id": -1, "comunidad_id": c["comunidad_id"], "text": texto}]
            hallazgos_fuga_real[c["id"]] = {c["comunidad_id"]}  # limpio: solo en su propia comunidad
        else:
            fragmentos_por_caso[c["id"]] = [{"id": -1, "comunidad_id": c["comunidad_id"],
                                              "text": "contenido generico de estatutos sin relacion con la pregunta"}]

    conteo_por_comunidad = {}
    for c in casos:
        conteo_por_comunidad[c["comunidad_id"]] = conteo_por_comunidad.get(c["comunidad_id"], 0) + 1

    # La premisa de las trampas SI se comprueba contra el corpus real en disco (comunidades/*.md):
    # es un fichero local, no Postgres ni red, y --dry-run solo promete no tocar Postgres (igual
    # que run_eval.py: su cargar_dataset() tambien lee del disco en modo --dry-run).
    texto_normalizado_por_comunidad = {}
    dir_comunidades = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "comunidades")
    for comunidad_id, nombre_fichero in mapa_documentos.items():
        with open(os.path.join(dir_comunidades, nombre_fichero), encoding="utf-8") as fh:
            texto_normalizado_por_comunidad[comunidad_id] = normalizar(fh.read())
    premisas_trampas = verificar_premisa_trampas(casos, texto_normalizado_por_comunidad)

    return {
        "mapa_documentos": mapa_documentos,
        "conteo_por_comunidad": conteo_por_comunidad,
        "topk": 12,
        "fragmentos_por_caso": fragmentos_por_caso,
        "hallazgos_fuga_real": hallazgos_fuga_real,
        "embeddings_disponibles": False,
        "motivo_sin_embeddings": "modo --dry-run: no se llama a la API de Gemini",
        "contrafactual_por_caso": {},
        "premisas_trampas": premisas_trampas,
        "fuente_embeddings": "sintetico (--dry-run)",
    }


def verificar_dry_run(m):
    """Asserts estructurales contra el contexto sintetico de construir_contexto_sintetico(): si
    alguien rompe el calculo de alguna seccion de informe(), esto falla con un mensaje concreto.
    Los numeros (12, 10/2, etc.) estan calculados sobre rag_casos.jsonl EXACTAMENTE como es hoy;
    si el dataset cambia sin tocar este fichero, estos asserts fallaran con un mensaje que lo
    dice explicitamente -- igual que la nota equivalente en run_eval.py."""
    assert m["total"] == 12, (
        f"total de casos = {m['total']}, se esperaban 12: si el dataset cambio de tamano, "
        f"actualiza este numero (y los de abajo); no asumas que es un bug del script.")
    assert m["total_respondibles"] == 10 and m["total_trampas"] == 2, (
        f"reparto respondible/trampa = {m['total_respondibles']}/{m['total_trampas']}, se "
        f"esperaba 10/2: si el dataset cambio de contenido, actualiza este numero.")
    assert m["fallos_3a"] == [], "el sintetico principal no fuerza ninguna fuga por filtro SQL (3a)"
    assert m["fallos_3b_fuga"] == [], "el sintetico principal no fuerza ninguna fuga real (3b)"
    assert m["fallos_doc"] == [], "el sintetico principal no fuerza ningun documento vacio"
    assert m["fallos_frag"] == ["r09"], "r09 es el unico fragmento_clave forzado a fallar"
    assert m["aciertos_doc_y_frag"] == 9, "9 de 10 deberian acertar documento+fragmento (solo r09 falla)"
    assert m["premisa_rota"] == [], "el corpus real no debe contener los terminos de las dos trampas"
    print("\nVerificacion estructural del dry-run: OK (cobertura, aislamiento, documento, "
          "fragmento y trampas cuadran con los numeros esperados).")


# ============================================================ main

def main():
    ap = argparse.ArgumentParser(
        description="Evalua el retrieval RAG de estatutos (pgvector) contra rag_casos.jsonl. "
                    "Mide recuperacion, no generacion -- ver docstring del modulo.")
    ap.add_argument("--umbral-acierto", type=float, default=0.85,
                     help="acierto minimo exigido en documento+fragmento sobre los casos "
                          "respondible=true (default: 0.85); el aislamiento NO se controla con "
                          "este umbral, es zero-tolerance siempre.")
    ap.add_argument("--topk", type=int, default=12, help="debe coincidir con el topK real de B1 (default: 12)")
    ap.add_argument("--dataset", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "rag_casos.jsonl"))
    ap.add_argument("--dsn", default=None, help="cadena de conexion libpq completa; si se omite se construye "
                                                  "desde PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD")
    ap.add_argument("--dry-run", action="store_true", help="valida el informe con datos sinteticos, sin tocar Postgres")
    args = ap.parse_args()

    verificar_detectores()  # autotest instantaneo, siempre, no necesita --dry-run

    dir_comunidades = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "comunidades")
    mapa_documentos = construir_mapa_documentos(dir_comunidades)
    casos = cargar_casos(args.dataset, mapa_documentos)

    if args.dry_run:
        contexto = construir_contexto_sintetico(casos, mapa_documentos)
        metricas = informe(casos, contexto)
        verificar_dry_run(metricas)
    else:
        contexto = ejecutar_real(casos, args, mapa_documentos)
        metricas = informe(casos, contexto)

    try:
        assert metricas["total"] == 12, f"cobertura incompleta o dataset alterado: {metricas['total']} casos"
        assert metricas["fallos_3a"] == [], (
            f"AISLAMIENTO (aserción 3a): fallo grave -- {len(metricas['fallos_3a'])} fragmento(s) "
            f"de otra comunidad volvieron de una consulta filtrada: {metricas['fallos_3a']}")
        assert metricas["fallos_3b_fuga"] == [], (
            f"AISLAMIENTO REAL (aserción 3b): fallo grave -- fuga confirmada en pares de fuga "
            f"disenados para detectarla: {metricas['fallos_3b_fuga']}")
        ratio = metricas["aciertos_doc_y_frag"] / metricas["total_respondibles"]
        assert ratio >= args.umbral_acierto, (
            f"documento+fragmento correctos {ratio:.1%} no alcanza el umbral {args.umbral_acierto:.1%} "
            f"(fallos de documento: {metricas['fallos_doc']}; fallos de fragmento: {metricas['fallos_frag']})")
    except AssertionError as e:
        print(f"\nFALLO: {e}")
        sys.exit(1)

    if metricas["embeddings_disponibles"]:
        print(f"\nOK: cobertura completa, aislamiento perfecto (3a y 3b) y documento+fragmento "
              f"{ratio:.1%} >= umbral {args.umbral_acierto:.1%}. Incluye el contraste sin filtro (3c).")
    else:
        print(f"\nOK (PARCIAL): cobertura completa, aislamiento perfecto (3a y 3b) y "
              f"documento+fragmento {ratio:.1%} >= umbral {args.umbral_acierto:.1%}. NO se evaluo "
              f"la aserción 3c (contraste sin filtro, requiere GEMINI_API_KEY funcionando) -- es "
              f"evidencia adicional, no bloqueante, pero falta. Recuerda ademas que este arnes "
              f"mide retrieval, no la respuesta redactada (ver cabecera del script).")


if __name__ == "__main__":
    main()
