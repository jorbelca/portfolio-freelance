BEGIN;
ALTER TABLE search_settings ADD COLUMN public_alternatives boolean NOT NULL DEFAULT true;
CREATE OR REPLACE VIEW settings_summary AS
SELECT s.id,s.revision,jsonb_build_object(
 'max_openings',s.max_openings,'batch_size',s.batch_size,'max_age_days',s.max_age_days,
 'timezone',s.timezone,'history_ready',s.history_ready,'model',s.model,'source_prompt',s.source_prompt,'provider',s.provider,'model_retries',s.model_retries,'model_timeout_seconds',s.model_timeout_seconds,'public_alternatives',s.public_alternatives,
 'quota_spain',(SELECT target FROM search_quotas WHERE settings_id=s.id AND zone='spain'),
 'quota_europe',(SELECT target FROM search_quotas WHERE settings_id=s.id AND zone='europe')) AS value FROM search_settings s;
CREATE TABLE search_document_reads (
 candidate_id uuid NOT NULL REFERENCES search_documents(candidate_id),
 route smallint NOT NULL CHECK(route BETWEEN 0 AND 1),
 request_url text NOT NULL,
 format text NOT NULL CHECK(format IN ('html','smartrecruiters','legacy')),
 status text NOT NULL CHECK(status IN ('reserved','complete','incomplete','error','unknown')),
 http_status integer,
 response_url text,
 reason text,
 reserved_at timestamptz NOT NULL DEFAULT now(),
 checked_at timestamptz,
 PRIMARY KEY(candidate_id,route)
);
INSERT INTO search_document_reads(candidate_id,route,request_url,format,status,http_status,response_url,reason,reserved_at,checked_at)
 SELECT candidate_id,0,url,'legacy',CASE WHEN status='reserved' THEN 'unknown' ELSE status END,http_status,url,reason,reserved_at,checked_at FROM search_documents;
COMMIT;
