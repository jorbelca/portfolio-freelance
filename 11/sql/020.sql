BEGIN;
ALTER TABLE search_document_reads DROP CONSTRAINT search_document_reads_format_check;
ALTER TABLE search_document_reads ADD CONSTRAINT search_document_reads_format_check
 CHECK(format IN ('html','smartrecruiters','greenhouse','lever','browser','legacy'));

CREATE TABLE search_application_checks (
 candidate_id uuid PRIMARY KEY REFERENCES search_candidates(id),
 run_id uuid NOT NULL REFERENCES workflow_runs(id),
 application_url text,
 page_url text,
 status text NOT NULL CHECK(status IN ('pending','accessible','login_required','captcha','closed','blocked','unknown')),
 form_found boolean,
 required_fields jsonb NOT NULL DEFAULT '[]',
 evidence text,
 reason text,
 checked_at timestamptz,
 updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX search_application_checks_run ON search_application_checks(run_id,status);

DELETE FROM search_source_settings WHERE configuration_id=1;
INSERT INTO search_source_settings(configuration_id,source,enabled,max_pages)
 VALUES(1,'browser:google',true,3),(1,'browser:bing',false,3);
UPDATE search_configuration SET revision=revision+1 WHERE id=1;
COMMIT;
