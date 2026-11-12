CREATE TABLE history_state (id integer PRIMARY KEY CHECK(id=1),revision bigint NOT NULL DEFAULT 1);
INSERT INTO history_state(id) VALUES(1);
ALTER TABLE search_run_state ADD COLUMN history_revision bigint NOT NULL DEFAULT 0;
ALTER TABLE search_run_state ADD COLUMN report_dirty boolean NOT NULL DEFAULT true;
ALTER TABLE search_run_state ADD COLUMN report_revision integer NOT NULL DEFAULT 0;
CREATE FUNCTION invalidate_search_history() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 UPDATE history_state SET revision=revision+1 WHERE id=1;
 RETURN NULL;
END $$;
CREATE TRIGGER opportunities_history AFTER INSERT OR UPDATE OR DELETE ON opportunities FOR EACH STATEMENT EXECUTE FUNCTION invalidate_search_history();
CREATE TRIGGER applications_history AFTER INSERT OR UPDATE OR DELETE ON applications FOR EACH STATEMENT EXECUTE FUNCTION invalidate_search_history();
CREATE TRIGGER publications_history AFTER INSERT OR UPDATE OR DELETE ON publications FOR EACH STATEMENT EXECUTE FUNCTION invalidate_search_history();
ALTER TABLE search_candidates ADD COLUMN version integer NOT NULL DEFAULT 1;
ALTER TABLE search_candidates ADD COLUMN identity_resolution text NOT NULL DEFAULT 'pending' CHECK(identity_resolution IN ('pending','distinct','same_process','duplicate'));
ALTER TABLE search_candidates ADD COLUMN duplicate_candidate_id uuid REFERENCES search_candidates(id);
ALTER TABLE search_candidates ADD CONSTRAINT duplicate_target CHECK((identity_resolution='duplicate')=(duplicate_candidate_id IS NOT NULL));
CREATE TABLE search_candidate_overrides (
 candidate_id uuid NOT NULL REFERENCES search_candidates(id),
 field text NOT NULL,
 value jsonb NOT NULL,
 evidence text NOT NULL,
 reason text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(candidate_id,field)
);
CREATE TABLE search_candidate_events (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 candidate_id uuid NOT NULL REFERENCES search_candidates(id),
 kind text NOT NULL,
 value jsonb NOT NULL,
 reason text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE search_step_attempts (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 step_id uuid NOT NULL REFERENCES search_steps(id),
 execution_id text NOT NULL,
 started_at timestamptz NOT NULL DEFAULT now(),
 finished_at timestamptz,
 status text NOT NULL DEFAULT 'running' CHECK(status IN ('running','succeeded','failed','unknown')),
 result jsonb,
 error text
);
CREATE INDEX search_step_attempts_step ON search_step_attempts(step_id,id);
ALTER TABLE search_source_settings ADD COLUMN max_pages integer NOT NULL DEFAULT 3 CHECK(max_pages BETWEEN 1 AND 100);
INSERT INTO search_source_settings(configuration_id,source,enabled,max_pages) VALUES(1,'smartrecruiters:Scalian:es',true,3);
ALTER TABLE search_documents ADD COLUMN source_payload jsonb;
