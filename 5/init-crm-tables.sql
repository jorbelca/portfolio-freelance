-- Bandeja de entrada del "CRM" de la Demo 5. Vive en una base aparte (`crm`) del mismo
-- Postgres, para que NocoDB la tome como base propia y la muestre sin configuración manual
-- (sus tablas de metadatos `nc_*` quedan aquí, no ensucian `n8n`).
--
-- El pipeline lee las filas en estado 'nuevo', las procesa por el grafo y escribe de vuelta
-- el estado + el resultado. NocoDB es solo la UI: alta de leads a mano y ver la bandeja.
-- Reejecutable.

CREATE TABLE IF NOT EXISTS crm_leads (
  id               SERIAL PRIMARY KEY,
  empresa          TEXT NOT NULL,
  contacto_nombre  TEXT,
  contacto_email   TEXT NOT NULL,
  contacto_cargo   TEXT,
  canal_origen     TEXT NOT NULL DEFAULT 'crm',
  -- nuevo -> procesando -> {cualificado | en_revision | descartado | error}
  estado           TEXT NOT NULL DEFAULT 'nuevo'
                   CHECK (estado IN ('nuevo','procesando','cualificado','en_revision','descartado','error')),
  -- Resultado de la cualificación, desnormalizado para verlo en el grid sin joins.
  etiqueta         TEXT,
  regla            TEXT,
  motivo           TEXT,
  -- Referencias a n8n.leads / n8n.cola_leads. Sin FK real: son bases distintas y el eval
  -- puede truncar esas tablas. Se muestran como texto, no como enlace.
  lead_id          INTEGER,
  cola_id          INTEGER,
  creado_en        TIMESTAMPTZ NOT NULL DEFAULT now(),
  procesado_en     TIMESTAMPTZ
);

-- Un par de leads de ejemplo para que la bandeja no salga vacía en la grabación. Solo
-- nombres que existen en fichas.json (si no, ficha_empresa no devuelve nada -> todo cae a
-- R14 sin_cualificar y la demo del CRM no enseña nada). No se re-insertan si ya están.
INSERT INTO crm_leads (empresa, contacto_nombre, contacto_email, contacto_cargo, canal_origen)
SELECT * FROM (VALUES
  ('Nubestack Ltd', 'Priya Shah',  'priya@nubestack.io',   'CTO',              'formulario_web'),
  ('Signalbox Ltd', 'Tom Reyes',   'tom@signalbox.io',     'Head of Data',     'demo_request'),
  ('Brightforge Ltd','Lena Ortiz',  'lena@brightforge.io',  'Engineering Lead', 'evento')
) AS v(empresa, contacto_nombre, contacto_email, contacto_cargo, canal_origen)
WHERE NOT EXISTS (SELECT 1 FROM crm_leads);
