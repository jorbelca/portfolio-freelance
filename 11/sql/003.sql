CREATE TABLE workflow_control (
  id integer PRIMARY KEY CHECK (id=1),
  enabled boolean NOT NULL DEFAULT false,
  revision integer NOT NULL DEFAULT 1 CHECK (revision>0)
);
INSERT INTO workflow_control(id) VALUES(1);
CREATE TABLE workflow_runs (
  id uuid PRIMARY KEY,
  module text NOT NULL CHECK (module='contract'),
  status text NOT NULL CHECK (status IN ('queued','running','succeeded','failed','unknown')),
  settings_revision integer NOT NULL,
  settings_snapshot jsonb NOT NULL,
  input_text text NOT NULL CHECK (length(input_text) BETWEEN 1 AND 100000),
  task_claimed boolean NOT NULL DEFAULT false,
  n8n_execution_id text,
  result jsonb,
  error text,
  created_at timestamptz NOT NULL DEFAULT now(),
  started_at timestamptz,
  finished_at timestamptz
);
CREATE UNIQUE INDEX workflow_runs_one_active ON workflow_runs ((true)) WHERE status IN ('queued','running','unknown');
CREATE INDEX workflow_runs_created ON workflow_runs(created_at DESC);
