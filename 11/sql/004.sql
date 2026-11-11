-- No se deducen fechas de inscripción ni de estado de registros históricos.
ALTER TABLE opportunities ADD COLUMN state_changed_at timestamptz;
CREATE OR REPLACE VIEW offer_summary AS
SELECT o.id,o.company_id,o.title,o.availability,o.review_state,o.notes,o.version,o.created_at,o.updated_at,
 c.name AS company,coalesce(a.state,'sin_candidatura') AS application_state,p.url,
 (a.id IS NOT NULL OR o.review_state='descartada' OR o.availability IN ('pausada','cerrada','cubierta','cancelada')) AS excluded,
 EXISTS(SELECT 1 FROM publications p2 WHERE p2.opportunity_id=o.id) AS has_publications,
 a.submitted_at,o.state_changed_at
FROM opportunities o JOIN companies c ON c.id=o.company_id
LEFT JOIN applications a ON a.opportunity_id=o.id
LEFT JOIN publications p ON p.opportunity_id=o.id AND p.is_primary;
