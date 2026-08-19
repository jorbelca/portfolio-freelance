#!/bin/sh
# Estado del triage de incidencias: ultimas ejecuciones + lo que ha quedado en las tablas.
# La contrasena se lee de ../1/.env y no se imprime.
set -e
cd "$(dirname "$0")"
export PGPASSWORD="$(grep -m1 '^DB_POSTGRESDB_PASSWORD=' ../1/.env | cut -d= -f2-)"
Q() { psql -h 127.0.0.1 -U n8n_user -d n8n "$@"; }

echo "== ultimas ejecuciones"
Q -c "select id, status, \"stoppedAt\"-\"startedAt\" dur, \"startedAt\"::time(0) hora
      from execution_entity where \"workflowId\"='b1394623b60e4442'
      order by id desc limit 8;"

echo "== incidencias"
Q -c "select id, comunidad_id cid, imputacion, imputacion_rival rival, confianza conf,
             umbral_aplicado umbral, elemento_normalizado elemento, decidido_por via,
             plazos_activos plazos, fundamento->0->>'fuente' fuente1
      from incidencias order by id;"

echo "== plazos / cola / errores"
Q -c "select tipo, dias_plazo, vence from plazos order by id;"
Q -c "select incidencia_id, left(motivo_escalado,70) motivo from revision_administrador order by id;"
Q -c "select nodo, left(mensaje,70) mensaje from errores where creado_en > now()-interval '1 day';"

echo "== ultimo error de modelo en los logs (si hay)"
docker logs 1-n8n-1 --since 20m 2>&1 | grep -o '\[[0-9]\{3\} [A-Za-z ]*\][^"]*' | tail -3 || true
