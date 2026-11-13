BEGIN;
CREATE TABLE workflow_schedule (
 id integer PRIMARY KEY CHECK(id=1),
 revision integer NOT NULL DEFAULT 1 CHECK(revision>0),
 enabled boolean NOT NULL DEFAULT false,
 interval_minutes integer NOT NULL DEFAULT 1440 CHECK(interval_minutes BETWEEN 15 AND 525600),
 next_run_at timestamptz NOT NULL DEFAULT now()+interval '1 day',
 last_checked_at timestamptz,
 last_run_id uuid REFERENCES workflow_runs(id),
 last_status text,
 last_error text
);
INSERT INTO workflow_schedule(id) VALUES(1);
COMMIT;
