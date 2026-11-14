BEGIN;

ALTER TABLE opportunity_merges
 ADD COLUMN undone_at timestamptz,
 ADD COLUMN undo_reason text,
 ADD COLUMN target_snapshot jsonb,
 ADD COLUMN target_application jsonb,
 ADD COLUMN moved_publications jsonb,
 ADD COLUMN moved_action_ids uuid[] NOT NULL DEFAULT '{}',
 ADD COLUMN moved_candidate_ids uuid[] NOT NULL DEFAULT '{}',
 ADD COLUMN reparented_merges uuid[] NOT NULL DEFAULT '{}',
 ADD COLUMN target_version_after integer,
 ADD COLUMN source_version_at_merge integer,
 ADD CONSTRAINT opportunity_merges_undo_state CHECK (
  (undone_at IS NULL AND undo_reason IS NULL) OR
  (undone_at IS NOT NULL AND length(trim(undo_reason)) BETWEEN 1 AND 2000)
 );

CREATE INDEX opportunity_merges_active_target
 ON opportunity_merges(target_id,created_at DESC,source_id)
 WHERE undone_at IS NULL;

CREATE OR REPLACE VIEW offer_summary AS
SELECT o.id,o.company_id,o.title,o.availability,o.review_state,o.notes,o.version,o.created_at,o.updated_at,
 c.name AS company,coalesce(a.state,'sin_candidatura') AS application_state,p.url,
 (a.id IS NOT NULL OR o.review_state='descartada' OR o.availability IN ('pausada','cerrada','cubierta','cancelada')) AS excluded,
 EXISTS(SELECT 1 FROM publications p2 WHERE p2.opportunity_id=o.id) AS has_publications,
 a.submitted_at,o.state_changed_at
FROM opportunities o JOIN companies c ON c.id=o.company_id
LEFT JOIN applications a ON a.opportunity_id=o.id
LEFT JOIN publications p ON p.opportunity_id=o.id AND p.is_primary
WHERE NOT EXISTS(SELECT 1 FROM opportunity_merges m WHERE m.source_id=o.id AND m.undone_at IS NULL);

COMMIT;
