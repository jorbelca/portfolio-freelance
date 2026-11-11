BEGIN;
CREATE TABLE IF NOT EXISTS settings (
  id integer PRIMARY KEY CHECK (id = 1),
  value jsonb NOT NULL,
  revision integer NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS offers (
  id uuid PRIMARY KEY,
  company text NOT NULL,
  title text NOT NULL,
  url text UNIQUE,
  status text NOT NULL CHECK (status IN ('pendiente','aplicada','entrevista','rechazada','descartada','cerrada','contratada')),
  notes text NOT NULL DEFAULT '',
  next_action text NOT NULL DEFAULT '',
  follow_up date,
  version integer NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS offer_events (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  offer_id uuid NOT NULL REFERENCES offers(id),
  value jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
COMMIT;
