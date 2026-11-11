ALTER TABLE workflow_runs DROP CONSTRAINT workflow_runs_module_check;
ALTER TABLE workflow_runs ADD CONSTRAINT workflow_runs_module_check CHECK(module IN ('contract','extraction'));
CREATE TABLE workflow_tasks (
  run_id uuid NOT NULL REFERENCES workflow_runs(id),
  task_id text NOT NULL,
  position integer NOT NULL CHECK(position>0),
  status text NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','running','succeeded','failed','unknown')),
  result jsonb,
  error text,
  started_at timestamptz,
  finished_at timestamptz,
  PRIMARY KEY(run_id,task_id),
  UNIQUE(run_id,position),
  CHECK((status='succeeded') = (result IS NOT NULL))
);
