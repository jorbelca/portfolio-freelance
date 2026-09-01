#!/bin/sh
# Arranca todo lo de la Demo 5 y abre el tablero: docker de ../1/, esquema, y el servidor.
# Uso:  ./tablero.sh
set -e
cd "$(dirname "$0")"

ENV1=../1/.env
[ -f "$ENV1" ] || { echo "Falta $ENV1"; exit 1; }
export PGHOST=127.0.0.1 PGPORT=5432 PGDATABASE=n8n PGUSER=n8n_user
export PGPASSWORD="$(grep -m1 '^DB_POSTGRESDB_PASSWORD=' "$ENV1" | cut -d= -f2-)"
export DB_POSTGRESDB_PASSWORD="$PGPASSWORD"   # lo lee docker-compose.crm.yml
export OPENROUTER_API_KEY="$(grep -m1 '^OPENROUTER_API_KEY=' "$ENV1" | cut -d= -f2-)"
export NC_ADMIN_PASSWORD="$(grep -m1 '^NC_ADMIN_PASSWORD=' "$ENV1" | cut -d= -f2-)"
export NC_ADMIN_EMAIL="$(grep -m1 '^NC_ADMIN_EMAIL=' "$ENV1" | cut -d= -f2-)"
export GEMINI_API_KEY="$(grep -m1 '^GEMINI_API_KEY=' "$ENV1" | cut -d= -f2-)"
# Si hay GEMINI_API_KEY y nadie fijó ya LEADS_LLM_BASE_URL, usar Gemini de AI Studio (cuota
# propia, no el pool :free de OpenRouter) en vez del default. `LEADS_MODELO=...` antes de
# llamar a este script gana igual, por si se quiere otro modelo de Gemini.
if [ -n "$GEMINI_API_KEY" ] && [ -z "$LEADS_LLM_BASE_URL" ]; then
  export LEADS_LLM_BASE_URL="https://generativelanguage.googleapis.com/v1beta/openai/"
  export LEADS_MODELO="${LEADS_MODELO:-gemini-2.5-flash}"
  export LEADS_REINTENTOS="${LEADS_REINTENTOS:-6}"
fi

echo "1/4  docker (postgres + greenmail + roundcube + adminer)..."
docker compose -f ../1/docker-compose.yml up -d postgres greenmail roundcube adminer >/dev/null
# esperar a que postgres acepte conexiones
for i in $(seq 1 30); do
  docker exec 1-postgres-1 pg_isready -U n8n_user -d n8n >/dev/null 2>&1 && break
  sleep 1
done

echo "2/4  esquema + panel (idempotente)..."
psql1() { docker exec -i -e "PGOPTIONS=-c client_min_messages=warning" 1-postgres-1 \
            psql -U n8n_user -d n8n -q "$@"; }
psql1 < init-leads-tables.sql >/dev/null
psql1 < panel/panel.sql >/dev/null

# --- CRM ---------------------------------------------------------------------------------
# La bandeja (base `crm` + tabla + card en el tablero) NO necesita contraseña: es otra base
# del mismo Postgres. NocoDB (la UI tipo CRM) sí exige un admin -> solo si hay
# NC_ADMIN_PASSWORD en ../1/.env. Nada de esto tumba el tablero (subshell + set +e).
echo "2b   CRM: base 'crm' + esquema..."
( set +e
  for d in crm nocodb; do
    docker exec 1-postgres-1 psql -U n8n_user -d n8n -tAc \
      "SELECT 1 FROM pg_database WHERE datname='$d'" | grep -q 1 \
      || docker exec 1-postgres-1 psql -U n8n_user -d n8n -q -c "CREATE DATABASE $d OWNER n8n_user"
  done
  docker exec -i -e "PGOPTIONS=-c client_min_messages=warning" 1-postgres-1 \
    psql -U n8n_user -d crm -q < init-crm-tables.sql >/dev/null
) && export CRM_PGDATABASE=crm || echo "   (base 'crm' no se creó — el tablero sigue sin bandeja)"

if [ -n "$NC_ADMIN_PASSWORD" ] && [ -n "$CRM_PGDATABASE" ]; then
  echo "     NocoDB (UI tipo CRM) en http://127.0.0.1:8091 ..."
  if docker compose -f docker-compose.crm.yml up -d >/dev/null 2>&1; then
    export CRM_NOCODB_URL="http://127.0.0.1:8091"
    ( set +e; NC_URL="$CRM_NOCODB_URL" sh crm-nocodb-init.sh )   # conecta la base `crm` (idempotente)
  else
    echo "   (NocoDB no arrancó — la bandeja del tablero funciona igual)"
  fi
else
  echo "     NocoDB: sin NC_ADMIN_PASSWORD en ../1/.env -> se omite (la bandeja funciona igual)"
fi

echo "3/4  abriendo http://127.0.0.1:8095 ..."
( sleep 2; command -v open >/dev/null && open http://127.0.0.1:8095 || true ) &

echo "4/4  servidor (Ctrl+C para parar)"
exec python3 ui/servidor.py
