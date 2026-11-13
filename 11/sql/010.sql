-- El proceso absorbido sigue archivado; ningún ID histórico se reutiliza.
CREATE TABLE opportunity_merges (
 source_id uuid PRIMARY KEY REFERENCES opportunities(id),
 target_id uuid NOT NULL REFERENCES opportunities(id),
 reason text NOT NULL CHECK(length(trim(reason)) BETWEEN 1 AND 2000),
 created_at timestamptz NOT NULL DEFAULT now(),
 CHECK(source_id<>target_id)
);
CREATE INDEX opportunity_merges_target ON opportunity_merges(target_id);
CREATE OR REPLACE VIEW offer_summary AS
SELECT o.id,o.company_id,o.title,o.availability,o.review_state,o.notes,o.version,o.created_at,o.updated_at,
 c.name AS company,coalesce(a.state,'sin_candidatura') AS application_state,p.url,
 (a.id IS NOT NULL OR o.review_state='descartada' OR o.availability IN ('pausada','cerrada','cubierta','cancelada')) AS excluded,
 EXISTS(SELECT 1 FROM publications p2 WHERE p2.opportunity_id=o.id) AS has_publications,
 a.submitted_at,o.state_changed_at
FROM opportunities o JOIN companies c ON c.id=o.company_id
LEFT JOIN applications a ON a.opportunity_id=o.id
LEFT JOIN publications p ON p.opportunity_id=o.id AND p.is_primary
WHERE NOT EXISTS(SELECT 1 FROM opportunity_merges m WHERE m.source_id=o.id);
