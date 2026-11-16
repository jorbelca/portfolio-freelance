ALTER TABLE search_quotas DROP CONSTRAINT search_quotas_target_check;
ALTER TABLE search_quotas ADD CONSTRAINT search_quotas_target_check CHECK (target >= 0);
