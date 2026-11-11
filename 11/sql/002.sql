-- Conservamos las tablas originales como archivo de la transición.
ALTER TABLE offers RENAME TO legacy_offers;
ALTER TABLE offer_events RENAME TO legacy_offer_events;
ALTER TABLE settings RENAME TO legacy_settings;

CREATE TABLE companies (
  id uuid PRIMARY KEY,
  name text NOT NULL CHECK (length(trim(name)) BETWEEN 1 AND 500),
  created_at timestamptz NOT NULL DEFAULT now()
);
-- Dos empresas pueden tener el mismo nombre. El nombre no acredita identidad.
CREATE INDEX companies_name_idx ON companies (lower(name));
CREATE TABLE opportunities (
  id uuid PRIMARY KEY,
  company_id uuid NOT NULL REFERENCES companies(id),
  title text NOT NULL CHECK (length(trim(title)) BETWEEN 1 AND 500),
  availability text NOT NULL DEFAULT 'desconocida' CHECK (availability IN ('desconocida','abierta','pausada','cerrada','cubierta','cancelada')),
  review_state text NOT NULL DEFAULT 'nueva' CHECK (review_state IN ('nueva','en_revision','guardada','descartada')),
  notes text NOT NULL DEFAULT '',
  version integer NOT NULL DEFAULT 1 CHECK (version > 0),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX opportunities_company_idx ON opportunities(company_id);
CREATE TABLE sources (
  id uuid PRIMARY KEY,
  namespace text NOT NULL UNIQUE,
  label text NOT NULL
);
CREATE TABLE publications (
  id uuid PRIMARY KEY,
  opportunity_id uuid NOT NULL REFERENCES opportunities(id),
  source_id uuid NOT NULL REFERENCES sources(id),
  url text NOT NULL UNIQUE CHECK (url ~ '^https?://'),
  external_id text,
  is_primary boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(source_id, external_id)
);
CREATE INDEX publications_opportunity_idx ON publications(opportunity_id);
CREATE INDEX publications_source_idx ON publications(source_id);
CREATE UNIQUE INDEX publications_one_primary_idx ON publications(opportunity_id) WHERE is_primary;
CREATE TABLE applications (
  id uuid PRIMARY KEY,
  opportunity_id uuid NOT NULL UNIQUE REFERENCES opportunities(id),
  state text NOT NULL CHECK (state IN ('enviada','en_revision','prueba','entrevista','oferta','aceptada','incorporada','rechazada_empresa','oferta_rechazada','rechazada_sin_detalle','retirada','sin_respuesta')),
  submitted_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
-- Una candidatura histórica puede tener fecha desconocida. No inventamos la fecha de envío.
CREATE TABLE follow_up_actions (
  id uuid PRIMARY KEY,
  opportunity_id uuid NOT NULL REFERENCES opportunities(id),
  description text NOT NULL CHECK (length(trim(description)) BETWEEN 1 AND 20000),
  due_on date,
  state text NOT NULL DEFAULT 'pendiente' CHECK (state IN ('pendiente','completada','cancelada')),
  version integer NOT NULL DEFAULT 1 CHECK (version > 0),
  created_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz,
  CHECK ((state = 'completada') = (completed_at IS NOT NULL))
);
CREATE INDEX follow_up_actions_opportunity_idx ON follow_up_actions(opportunity_id);
CREATE INDEX follow_up_actions_due_idx ON follow_up_actions(due_on) WHERE state = 'pendiente';
CREATE TABLE opportunity_events (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  opportunity_id uuid NOT NULL REFERENCES opportunities(id),
  kind text NOT NULL,
  actor text NOT NULL DEFAULT 'usuario' CHECK (actor IN ('usuario','migracion','workflow')),
  reason text NOT NULL DEFAULT '',
  value jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX opportunity_events_opportunity_idx ON opportunity_events(opportunity_id, id);

CREATE TABLE search_settings (
  id integer PRIMARY KEY CHECK (id = 1),
  revision integer NOT NULL DEFAULT 1 CHECK (revision > 0),
  max_openings integer NOT NULL CHECK (max_openings > 0),
  batch_size integer NOT NULL CHECK (batch_size > 0 AND batch_size <= max_openings),
  max_age_days integer NOT NULL CHECK (max_age_days > 0),
  timezone text NOT NULL,
  history_ready boolean NOT NULL DEFAULT false,
  model text NOT NULL DEFAULT '',
  source_prompt text NOT NULL
);
CREATE TABLE search_quotas (
  settings_id integer NOT NULL REFERENCES search_settings(id),
  zone text NOT NULL CHECK (zone IN ('spain','europe')),
  target integer NOT NULL CHECK (target > 0),
  PRIMARY KEY(settings_id, zone)
);
INSERT INTO search_settings
SELECT id, revision, (value->>'max_openings')::integer, (value->>'batch_size')::integer,
 (value->>'max_age_days')::integer, value->>'timezone', (value->>'history_ready')::boolean,
 coalesce(value->>'model',''), value->>'source_prompt' FROM legacy_settings;
INSERT INTO search_quotas SELECT id, 'spain', (value->>'quota_spain')::integer FROM legacy_settings;
INSERT INTO search_quotas SELECT id, 'europe', (value->>'quota_europe')::integer FROM legacy_settings;

-- No fusionar empresas o convocatorias antiguas por semejanza de nombre.
INSERT INTO companies(id,name,created_at) SELECT id,company,created_at FROM legacy_offers;
INSERT INTO opportunities(id,company_id,title,availability,review_state,notes,version,created_at,updated_at)
SELECT id,id,title,CASE WHEN status='cerrada' THEN 'cerrada' ELSE 'desconocida' END,
 CASE WHEN status='descartada' THEN 'descartada' ELSE 'nueva' END,notes,version,created_at,updated_at FROM legacy_offers;
INSERT INTO sources(id,namespace,label)
SELECT id, 'legacy:' || id::text, 'Publicación importada' FROM legacy_offers WHERE url IS NOT NULL;
INSERT INTO publications(id,opportunity_id,source_id,url,is_primary)
SELECT id,id,id,url,true FROM legacy_offers WHERE url IS NOT NULL;
INSERT INTO applications(id,opportunity_id,state,created_at,updated_at)
SELECT o.id,o.id,CASE (CASE WHEN o.status IN ('aplicada','entrevista','rechazada','contratada') THEN o.status ELSE h.status END)
 WHEN 'aplicada' THEN 'enviada' WHEN 'contratada' THEN 'incorporada'
 WHEN 'rechazada' THEN 'rechazada_sin_detalle' ELSE (CASE WHEN o.status IN ('aplicada','entrevista','rechazada','contratada') THEN o.status ELSE h.status END) END,o.created_at,o.updated_at
FROM legacy_offers o
LEFT JOIN LATERAL (
 SELECT value->>'status' AS status FROM legacy_offer_events e
 WHERE e.offer_id=o.id AND value->>'status' IN ('aplicada','entrevista','rechazada','contratada')
 ORDER BY e.id DESC LIMIT 1
) h ON true
WHERE h.status IS NOT NULL OR o.status IN ('aplicada','entrevista','rechazada','contratada');
INSERT INTO follow_up_actions(id,opportunity_id,description,due_on)
SELECT id,id,coalesce(nullif(trim(next_action),''),'Seguimiento importado'),follow_up FROM legacy_offers
WHERE trim(next_action) <> '' OR follow_up IS NOT NULL;
INSERT INTO opportunity_events(opportunity_id,kind,actor,value,created_at)
SELECT offer_id,'legacy','migracion',value,created_at FROM legacy_offer_events ORDER BY id;

-- El bloqueo es derivado. Reabrir una publicación no borra una candidatura.
CREATE VIEW offer_summary AS
SELECT o.*, c.name AS company,
 coalesce(a.state,'sin_candidatura') AS application_state,
 p.url,
 (a.id IS NOT NULL OR o.review_state='descartada' OR o.availability IN ('pausada','cerrada','cubierta','cancelada')) AS excluded,
 EXISTS(SELECT 1 FROM publications p2 WHERE p2.opportunity_id=o.id) AS has_publications
FROM opportunities o JOIN companies c ON c.id=o.company_id
LEFT JOIN applications a ON a.opportunity_id=o.id
LEFT JOIN publications p ON p.opportunity_id=o.id AND p.is_primary;
CREATE VIEW settings_summary AS
SELECT s.id,s.revision,jsonb_build_object(
 'max_openings',s.max_openings,'batch_size',s.batch_size,'max_age_days',s.max_age_days,
 'timezone',s.timezone,'history_ready',s.history_ready,'model',s.model,'source_prompt',s.source_prompt,
 'quota_spain',(SELECT target FROM search_quotas WHERE settings_id=s.id AND zone='spain'),
 'quota_europe',(SELECT target FROM search_quotas WHERE settings_id=s.id AND zone='europe')) AS value FROM search_settings s;
