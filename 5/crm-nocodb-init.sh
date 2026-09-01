#!/bin/sh
# Conecta la base `crm` como data source externo dentro de NocoDB (idempotente).
# NocoDB 2026.x guarda sus metadatos en la base `nocodb` y NO adopta el esquema de NC_DB,
# así que hay que registrar `crm` por API. Lo llama tablero.sh tras `docker compose up`.
#
# Lee del entorno (los exporta tablero.sh):
#   NC_ADMIN_EMAIL  NC_ADMIN_PASSWORD  DB_POSTGRESDB_PASSWORD
# Opcional:  NC_URL (def. http://127.0.0.1:8091)
set -e
NC_URL="${NC_URL:-http://127.0.0.1:8091}"
[ -n "$NC_ADMIN_PASSWORD" ] && [ -n "$DB_POSTGRESDB_PASSWORD" ] || {
  echo "   (crm-nocodb-init: faltan credenciales, se omite)"; exit 0; }
EMAIL="${NC_ADMIN_EMAIL:-demo@nubeforge.local}"

# 1. esperar a que NocoDB acepte el login (primer arranque tarda en crear el admin)
TOK=""
i=0
while [ $i -lt 30 ]; do
  TOK=$(curl -s -X POST "$NC_URL/api/v1/auth/user/signin" -H 'Content-Type: application/json' \
        -d "{\"email\":\"$EMAIL\",\"password\":\"$NC_ADMIN_PASSWORD\"}" \
        | python3 -c 'import sys,json;print(json.load(sys.stdin).get("token",""))' 2>/dev/null || true)
  [ -n "$TOK" ] && break
  i=$((i+1)); sleep 2
done
[ -n "$TOK" ] || { echo "   (crm-nocodb-init: NocoDB no respondió al login, se omite)"; exit 0; }

# 2. ¿ya existe la base "CRM"?
EXISTS=$(curl -s "$NC_URL/api/v2/meta/bases/" -H "xc-auth: $TOK" \
  | python3 -c 'import sys,json;print(any(b.get("title")=="CRM" for b in json.load(sys.stdin).get("list",[])))' 2>/dev/null || echo False)
if [ "$EXISTS" = "True" ]; then
  echo "   NocoDB: base 'CRM' ya conectada."
  exit 0
fi

# 3. crear base + data source externo apuntando a la base `crm`
BID=$(curl -s -X POST "$NC_URL/api/v2/meta/bases/" -H "xc-auth: $TOK" -H 'Content-Type: application/json' \
      -d '{"title":"CRM"}' \
      | python3 -c 'import sys,json;print(json.load(sys.stdin).get("id",""))' 2>/dev/null || true)
[ -n "$BID" ] || { echo "   (crm-nocodb-init: no se pudo crear la base, se omite)"; exit 0; }

SRC_BODY=$(python3 -c "
import json,os
print(json.dumps({'alias':'crm-pg','type':'pg','inflection_column':'none','inflection_table':'none',
  'config':{'client':'pg','searchPath':['public'],
    'connection':{'host':'postgres','port':5432,'user':'n8n_user',
      'password':os.environ['DB_POSTGRESDB_PASSWORD'],'database':'crm'}}}))")
OK=$(curl -s -X POST "$NC_URL/api/v2/meta/bases/$BID/sources" -H "xc-auth: $TOK" \
     -H 'Content-Type: application/json' -d "$SRC_BODY" \
     | python3 -c 'import sys,json;print("id" in json.load(sys.stdin))' 2>/dev/null || echo False)
if [ "$OK" = "True" ]; then
  echo "   NocoDB: base 'CRM' conectada a la tabla crm_leads."
else
  echo "   (crm-nocodb-init: el data source no se registró — conéctalo a mano en $NC_URL)"
fi
