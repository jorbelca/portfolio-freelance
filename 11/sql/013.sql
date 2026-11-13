BEGIN;
ALTER TABLE search_settings ADD COLUMN model_timeout_seconds integer NOT NULL DEFAULT 120 CHECK(model_timeout_seconds BETWEEN 5 AND 120);
CREATE OR REPLACE VIEW settings_summary AS
SELECT s.id,s.revision,jsonb_build_object(
 'max_openings',s.max_openings,'batch_size',s.batch_size,'max_age_days',s.max_age_days,
 'timezone',s.timezone,'history_ready',s.history_ready,'model',s.model,'source_prompt',s.source_prompt,'provider',s.provider,'model_retries',s.model_retries,'model_timeout_seconds',s.model_timeout_seconds,
 'quota_spain',(SELECT target FROM search_quotas WHERE settings_id=s.id AND zone='spain'),
 'quota_europe',(SELECT target FROM search_quotas WHERE settings_id=s.id AND zone='europe')) AS value FROM search_settings s;
COMMIT;
