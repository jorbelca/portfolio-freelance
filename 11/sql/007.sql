ALTER TABLE workflow_runs DROP CONSTRAINT workflow_runs_module_check;
ALTER TABLE workflow_runs ADD CONSTRAINT workflow_runs_module_check CHECK(module IN ('contract','extraction','search'));
CREATE TABLE search_run_state (
 run_id uuid PRIMARY KEY REFERENCES workflow_runs(id),
 control text NOT NULL DEFAULT 'active' CHECK(control IN ('active','paused','cancelled')),
 revision integer NOT NULL DEFAULT 1,
 close_reason text,
 updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE search_candidates (
 id uuid PRIMARY KEY,
 run_id uuid NOT NULL REFERENCES workflow_runs(id),
 source text NOT NULL,
 external_id text NOT NULL DEFAULT '',
 url text NOT NULL,
 company text NOT NULL,
 title text NOT NULL,
 hint jsonb NOT NULL,
 opportunity_id uuid REFERENCES opportunities(id),
 history jsonb,
 evaluation jsonb,
 stage text NOT NULL DEFAULT 'lead' CHECK(stage IN ('lead','excluded','reading','extracting','evaluated','blocked')),
 reason text,
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(run_id,url)
);
CREATE INDEX search_candidates_run ON search_candidates(run_id,stage);
CREATE TABLE search_documents (
 candidate_id uuid PRIMARY KEY REFERENCES search_candidates(id),
 run_id uuid NOT NULL REFERENCES workflow_runs(id),
 url text NOT NULL,
 status text NOT NULL CHECK(status IN ('reserved','complete','incomplete','error')),
 http_status integer,
 text text,
 job jsonb,
 reason text,
 reserved_at timestamptz NOT NULL DEFAULT now(),
 checked_at timestamptz,
 CHECK(status<>'complete' OR (length(text)>0 AND job IS NOT NULL))
);
CREATE INDEX search_documents_run ON search_documents(run_id);
CREATE TABLE search_steps (
 id uuid PRIMARY KEY,
 run_id uuid NOT NULL REFERENCES workflow_runs(id),
 candidate_id uuid REFERENCES search_candidates(id),
 task_key text NOT NULL,
 kind text NOT NULL,
 priority integer NOT NULL,
 input jsonb NOT NULL DEFAULT '{}',
 status text NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','running','succeeded','failed','unknown')),
 result jsonb,
 error text,
 created_at timestamptz NOT NULL DEFAULT now(),
 started_at timestamptz,
 finished_at timestamptz,
 UNIQUE(run_id,task_key)
);
CREATE INDEX search_steps_queue ON search_steps(run_id,status,priority,created_at,id);
CREATE TABLE search_candidate_links (
 candidate_id uuid NOT NULL REFERENCES search_candidates(id),
 url text NOT NULL,
 PRIMARY KEY(candidate_id,url)
);
ALTER TABLE search_run_state ADD COLUMN selected_step uuid REFERENCES search_steps(id);
