BEGIN;
ALTER TABLE search_settings ADD COLUMN reasoning_effort text NOT NULL DEFAULT 'max' CHECK(reasoning_effort IN ('low','medium','high','xhigh','max'));
CREATE OR REPLACE VIEW settings_summary AS
SELECT s.id,s.revision,jsonb_build_object(
 'max_openings',s.max_openings,'batch_size',s.batch_size,'max_age_days',s.max_age_days,
 'timezone',s.timezone,'history_ready',s.history_ready,'model',s.model,'source_prompt',s.source_prompt,'provider',s.provider,'reasoning_effort',s.reasoning_effort,'model_retries',s.model_retries,'model_timeout_seconds',s.model_timeout_seconds,'public_alternatives',s.public_alternatives,
 'quota_spain',(SELECT target FROM search_quotas WHERE settings_id=s.id AND zone='spain'),
 'quota_europe',(SELECT target FROM search_quotas WHERE settings_id=s.id AND zone='europe')) AS value FROM search_settings s;
COMMIT;
