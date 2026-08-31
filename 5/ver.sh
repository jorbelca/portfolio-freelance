#!/bin/sh
# Estado de la cualificación de leads: lo que ha quedado en las tablas tras procesar_leads.py.
# La contraseña se lee de ../1/.env y no se imprime. Mismo patrón que 2/ver.sh.
set -e
cd "$(dirname "$0")"
export PGPASSWORD="$(grep -m1 '^DB_POSTGRESDB_PASSWORD=' ../1/.env | cut -d= -f2-)"
Q() { psql -h 127.0.0.1 -U n8n_user -d n8n "$@"; }

echo "== leads (cualificados)"
Q -c "select id, left(empresa,22) empresa, etiqueta, regla, left(motivo,34) motivo,
             asignado_a, confianza conf
      from leads order by id;"

echo "== cola de cualificación (lo dudoso)"
Q -c "select id, left(empresa,22) empresa, etiqueta, left(motivo,50) motivo
      from cola_leads where tipo='cualificacion' order by id;"

echo "== borradores de email pendientes (V2)"
Q -c "select id, left(empresa,22) empresa, contacto_email, borrador_message_id is not null enviado
      from cola_leads where tipo='borrador' order by id;"

echo "== reparto por etiqueta / regla más frecuente"
Q -c "select * from v_leads_por_etiqueta;"
Q -c "select * from v_leads_regla_frecuencia order by n_leads desc limit 6;"

echo
echo "borradores en GreenMail: http://127.0.0.1:8081  (usuario borradores@nubeforge.local, clave cualquiera)"
echo "tablas en Adminer:        http://127.0.0.1:8082  (servidor postgres, base n8n)"
