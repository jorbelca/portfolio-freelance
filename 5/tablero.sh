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
# Proveedor: Gemini de AI Studio por defecto (LEADS_MODELO manda). OpenRouter como
# alternativa con LEADS_OPENROUTER=1 -- ojo, el tier gratis de AI Studio es por modelo/día.
if [ "$LEADS_OPENROUTER" != "1" ] && [ -n "$GEMINI_API_KEY" ] && [ -z "$LEADS_LLM_BASE_URL" ]; then
  export LEADS_LLM_BASE_URL="https://generativelanguage.googleapis.com/v1beta/openai/"
  export LEADS_MODELO="${LEADS_MODELO:-gemini-3.6-flash}"
  export LEADS_REINTENTOS="${LEADS_REINTENTOS:-6}"
else
  unset GEMINI_API_KEY   # _clave() la prefiere sobre OPENROUTER_API_KEY
  export LEADS_LLM_BASE_URL="${LEADS_LLM_BASE_URL:-https://openrouter.ai/api/v1}"
  export LEADS_MODELO="${LEADS_MODELO:-nvidia/nemotron-3-ultra-550b-a55b:free}"
  export LEADS_REINTENTOS="${LEADS_REINTENTOS:-6}"   # pool :free -> 429 intermitente
  export LEADS_TIMEOUT="${LEADS_TIMEOUT:-300}"       # ~17 s/llamada, razona antes de responder
fi

# Un LEADS_MODELO malo hace fallar CADA llamada -> la corrida de los 30 sale 0/30 y el error
# queda enterrado como `sin_cualificar`. Dos comprobaciones, solo en la ruta Gemini:
#   1. ¿existe en el catálogo?  (curl al listado, gratis) -> caza typos
#   2. ¿devuelve algo usable?   (1 llamada real) -> caza modelos que existen pero rechazan
#      json_object, truncan pensando, o tienen la cuota agotada. Como cuesta 1 llamada, solo
#      corre si el modelo NO es el default conocido-bueno, o si LEADS_SMOKE=1.
case "$LEADS_LLM_BASE_URL" in
  *generativelanguage.googleapis.com*)
    _cat=$(curl -s -m 10 "https://generativelanguage.googleapis.com/v1beta/models?key=$GEMINI_API_KEY" 2>/dev/null || true)
    if printf '%s' "$_cat" | grep -q '"name"'; then
      if ! printf '%s' "$_cat" | grep -q "\"models/$LEADS_MODELO\""; then
        echo "ERROR: LEADS_MODELO='$LEADS_MODELO' no está en el catálogo de Gemini AI Studio." >&2
        echo "       Disponibles (flash):" >&2
        printf '%s' "$_cat" | grep -o '"models/gemini-[a-z0-9.-]*flash[a-z0-9.-]*"' | sort -u | sed 's/^/         /' >&2
        exit 1
      fi
    else
      echo "   (aviso: no se pudo verificar LEADS_MODELO contra Gemini; sigo)"
    fi
    if [ "$LEADS_MODELO" != "gemini-3.6-flash" ] || [ "$LEADS_SMOKE" = "1" ]; then
      echo "0/4  probando LEADS_MODELO='$LEADS_MODELO' (1 llamada)..."
      _smoke=$(curl -s -m 30 "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions" \
        -H "Authorization: Bearer $GEMINI_API_KEY" -H 'Content-Type: application/json' \
        -d "{\"model\":\"$LEADS_MODELO\",\"messages\":[{\"role\":\"user\",\"content\":\"Responde solo con el JSON {\\\"ok\\\":true}\"}],\"temperature\":0,\"max_tokens\":8192,\"response_format\":{\"type\":\"json_object\"}}" 2>/dev/null || true)
      if ! printf '%s' "$_smoke" | grep -q '"content"[[:space:]]*:[[:space:]]*"[^"]'; then
        echo "ERROR: '$LEADS_MODELO' no devolvió respuesta usable. Respuesta del proveedor:" >&2
        printf '%s\n' "$_smoke" | head -c 600 >&2; echo >&2
        echo "       Prueba LEADS_MODELO=gemini-3.6-flash" >&2
        exit 1
      fi
    fi
    ;;
  *openrouter.ai*)
    echo "0/4  probando LEADS_MODELO='$LEADS_MODELO' en OpenRouter (1 llamada)..."
    _smoke=$(curl -s -m 60 "https://openrouter.ai/api/v1/chat/completions" \
      -H "Authorization: Bearer $OPENROUTER_API_KEY" -H 'Content-Type: application/json' \
      -d "{\"model\":\"$LEADS_MODELO\",\"messages\":[{\"role\":\"user\",\"content\":\"Responde solo con el JSON {\\\"ok\\\":true}\"}],\"temperature\":0,\"max_tokens\":2048,\"response_format\":{\"type\":\"json_object\"}}" 2>/dev/null || true)
    if ! printf '%s' "$_smoke" | grep -q '"content"[[:space:]]*:[[:space:]]*"[^"]'; then
      echo "ERROR: '$LEADS_MODELO' no devolvió respuesta usable en OpenRouter:" >&2
      printf '%s\n' "$_smoke" | head -c 600 >&2; echo >&2
      echo "       Si dice 'guardrail': permite el modelo en https://openrouter.ai/workspaces/default/guardrails" >&2
      exit 1
    fi
    ;;
esac

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
