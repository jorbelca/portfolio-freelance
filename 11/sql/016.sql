BEGIN;
ALTER TABLE search_run_state ADD COLUMN report_files_revision integer NOT NULL DEFAULT 0 CHECK(report_files_revision>=0);
ALTER TABLE search_run_state ADD COLUMN report_files_error text;
COMMIT;
