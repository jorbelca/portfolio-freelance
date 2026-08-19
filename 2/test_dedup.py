#!/usr/bin/env python3
"""Prueba de la deduplicación por suceso de incidencias (init-fincas-tables.sql).

Cubre lo que UNIQUE(message_id) no cubre: tres vecinos DISTINTOS avisando del mismo
elemento averiado en la misma comunidad y dentro de una ventana de 72h deben producir
una sola incidencia (una raíz + hijas), no tres. Usa buscar_incidencia_raiz(), la función
SQL determinista de init-fincas-tables.sql -- sin similitud semántica ni LLM aquí, a
propósito (ver el comentario de esa función).

Sin framework: funciones planas + assert. Todo corre en una única transacción que se
deshace al final (rollback), así que no deja datos en la base del usuario pase lo que
pase. DSN por variables de entorno, con 127.0.0.1:5432 como valor por defecto:
  PGHOST (127.0.0.1) PGPORT (5432) PGDATABASE (n8n) PGUSER (n8n_user) PGPASSWORD
"""

import os
import sys

import psycopg2


def get_conn():
    return psycopg2.connect(
        host=os.environ.get("PGHOST", "127.0.0.1"),
        port=os.environ.get("PGPORT", "5432"),
        dbname=os.environ.get("PGDATABASE", "n8n"),
        user=os.environ.get("PGUSER", "n8n_user"),
        password=os.environ.get("PGPASSWORD"),
        connect_timeout=5,
    )


def buscar_raiz(cur, comunidad_id, elemento, momento):
    cur.execute(
        "SELECT buscar_incidencia_raiz(%s, %s, %s)", (comunidad_id, elemento, momento)
    )
    return cur.fetchone()[0]


def insertar_incidencia(cur, message_id, comunidad_id, email, elemento, momento, padre_id=None):
    cur.execute(
        """
        INSERT INTO incidencias
            (message_id, comunidad_id, propietario_email, elemento_normalizado, incidencia_padre_id, creado_en)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (message_id, comunidad_id, email, elemento, padre_id, momento),
    )
    return cur.fetchone()[0]


def contar(cur, sql, params=()):
    cur.execute(sql, params)
    return cur.fetchone()[0]


def crear_comunidades_de_prueba(cur):
    # Comunidades propias del test, aisladas de las 3 reales (CDP-001..003) para no
    # depender de si seed-comunidades.sql se ha ejecutado antes.
    cur.execute(
        """
        INSERT INTO comunidades (comunidad_id, nombre) VALUES
            ('CDP-TEST-A', 'Comunidad Test A'),
            ('CDP-TEST-B', 'Comunidad Test B')
        """
    )


def test_caso_1_tres_vecinos_mismo_suceso(cur):
    """Tres vecinos distintos, misma comunidad, mismo elemento, dentro de 72h -> 1 raíz + 2 hijas."""
    t0 = "2026-01-01 09:00:00+00"

    raiz = buscar_raiz(cur, "CDP-TEST-A", "bajante", t0)
    assert raiz is None, "caso1: no debería existir raíz previa"
    id1 = insertar_incidencia(cur, "caso1-msg-1", "CDP-TEST-A", "marta.fernandez@ejemplo.com", "bajante", t0)

    raiz = buscar_raiz(cur, "CDP-TEST-A", "bajante", "2026-01-01 19:00:00+00")  # +10h
    assert raiz == id1, "caso1: el segundo vecino debe encontrar la raíz del primero"
    insertar_incidencia(cur, "caso1-msg-2", "CDP-TEST-A", "carlos.gomez@ejemplo.com", "bajante", "2026-01-01 19:00:00+00", padre_id=raiz)

    raiz = buscar_raiz(cur, "CDP-TEST-A", "bajante", "2026-01-04 07:00:00+00")  # +70h
    assert raiz == id1, "caso1: el tercer vecino (70h después) debe encontrar la misma raíz"
    insertar_incidencia(cur, "caso1-msg-3", "CDP-TEST-A", "elena.torres@ejemplo.com", "bajante", "2026-01-04 07:00:00+00", padre_id=raiz)

    total = contar(cur, "SELECT count(*) FROM incidencias WHERE comunidad_id = 'CDP-TEST-A' AND elemento_normalizado = 'bajante'")
    assert total == 3, f"caso1: esperaba 3 filas (1 raíz + 2 hijas), hay {total}"

    hijas = contar(cur, "SELECT count(*) FROM incidencias WHERE incidencia_padre_id = %s", (id1,))
    assert hijas == 2, f"caso1: esperaba 2 hijas apuntando a la raíz, hay {hijas}"


def test_caso_2_fuera_de_ventana(cur):
    """Mismo elemento y comunidad, pero a 100h -> dos incidencias independientes."""
    t0 = "2026-02-01 09:00:00+00"
    insertar_incidencia(cur, "caso2-msg-1", "CDP-TEST-A", "marta.fernandez@ejemplo.com", "terraza", t0)

    momento_100h = "2026-02-05 13:00:00+00"  # t0 + 100h
    raiz = buscar_raiz(cur, "CDP-TEST-A", "terraza", momento_100h)
    assert raiz is None, "caso2: a 100h la ventana de 72h ya debe estar cerrada"
    insertar_incidencia(cur, "caso2-msg-2", "CDP-TEST-A", "carlos.gomez@ejemplo.com", "terraza", momento_100h)

    raices = contar(
        cur,
        "SELECT count(*) FROM incidencias WHERE comunidad_id = 'CDP-TEST-A' AND elemento_normalizado = 'terraza' AND incidencia_padre_id IS NULL",
    )
    assert raices == 2, f"caso2: esperaba 2 incidencias raíz independientes, hay {raices}"


def test_caso_3_comunidades_distintas(cur):
    """Mismo elemento, misma ventana temporal, pero comunidades distintas -> independientes."""
    t0 = "2026-03-01 09:00:00+00"
    insertar_incidencia(cur, "caso3-msg-1", "CDP-TEST-A", "marta.fernandez@ejemplo.com", "fachada", t0)

    momento = "2026-03-01 10:00:00+00"  # +1h, muy dentro de la ventana
    raiz = buscar_raiz(cur, "CDP-TEST-B", "fachada", momento)
    assert raiz is None, "caso3: otra comunidad no debe encontrar la raíz de CDP-TEST-A (fincas mezcladas)"
    insertar_incidencia(cur, "caso3-msg-2", "CDP-TEST-B", "sofia.navarro@ejemplo.com", "fachada", momento)

    raices = contar(
        cur, "SELECT count(*) FROM incidencias WHERE elemento_normalizado = 'fachada' AND incidencia_padre_id IS NULL"
    )
    assert raices == 2, f"caso3: esperaba una raíz por comunidad (2 en total), hay {raices}"


def test_caso_4_reenvio_mismo_message_id(cur):
    """Reenvío del mismo message_id -> no crea fila nueva, ni siquiera hija."""
    # Comparamos el TOTAL de filas de la tabla, no un count filtrado por message_id (que al ser
    # UNIQUE solo puede dar 0 o 1 y no detectaría una implementación que, ante el conflicto,
    # inserte igualmente una hija con OTRO message_id en vez de no insertar nada).
    total_antes = contar(cur, "SELECT count(*) FROM incidencias")

    # ON CONFLICT DO NOTHING: un INSERT normal contra el UNIQUE de message_id abortaría toda
    # la transacción (y arruinaría los asserts posteriores), así que el dedup exacto se prueba
    # a través del camino real de inserción (INSERT ... ON CONFLICT).
    cur.execute(
        """
        INSERT INTO incidencias (message_id, comunidad_id, propietario_email, elemento_normalizado, creado_en)
        VALUES ('caso1-msg-1', 'CDP-TEST-A', 'quien-reenvia@ejemplo.com', 'bajante', now())
        ON CONFLICT (message_id) DO NOTHING
        """
    )

    total_despues = contar(cur, "SELECT count(*) FROM incidencias")
    assert total_antes == total_despues, (
        f"caso4: el reenvío no debe crear ninguna fila (antes={total_antes}, despues={total_despues})"
    )


def main():
    conn = get_conn()
    try:
        cur = conn.cursor()
        crear_comunidades_de_prueba(cur)

        test_caso_1_tres_vecinos_mismo_suceso(cur)
        print("caso 1 OK: tres vecinos distintos -> una incidencia con dos hijas")

        test_caso_2_fuera_de_ventana(cur)
        print("caso 2 OK: mismo elemento a 100h -> incidencias independientes")

        test_caso_3_comunidades_distintas(cur)
        print("caso 3 OK: misma ventana, comunidades distintas -> incidencias independientes")

        test_caso_4_reenvio_mismo_message_id(cur)
        print("caso 4 OK: reenvío del mismo message_id -> ninguna fila nueva")

        print("test_dedup: todos los casos pasan")
    finally:
        # Nunca se hace commit: la base del usuario queda exactamente como estaba.
        conn.rollback()
        conn.close()


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print(f"FALLO: {e}", file=sys.stderr)
        sys.exit(1)
    except psycopg2.OperationalError as e:
        print(f"No se pudo conectar a Postgres: {e}", file=sys.stderr)
        sys.exit(2)
