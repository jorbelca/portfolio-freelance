BEGIN;

CREATE TABLE rejection_reasons (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 name text NOT NULL CHECK (name=trim(name) AND length(name) BETWEEN 1 AND 100)
);

CREATE UNIQUE INDEX rejection_reasons_name_idx ON rejection_reasons (lower(name));

INSERT INTO rejection_reasons(name) VALUES
 ('Experiencia insuficiente'),
 ('Requisitos técnicos'),
 ('Formación o certificación'),
 ('Idiomas'),
 ('Ubicación o modalidad'),
 ('Condiciones económicas'),
 ('Disponibilidad'),
 ('Vacante cerrada o cancelada'),
 ('Otro perfil seleccionado'),
 ('Motivo no comunicado');

ALTER TABLE opportunities ADD COLUMN rejection_reason_id uuid REFERENCES rejection_reasons(id);

CREATE OR REPLACE VIEW offer_summary AS
SELECT o.id,o.company_id,o.title,o.availability,o.review_state,o.notes,o.version,o.created_at,o.updated_at,
 c.name AS company,coalesce(a.state,'sin_candidatura') AS application_state,p.url,
 (a.id IS NOT NULL OR o.review_state='descartada' OR o.availability IN ('pausada','cerrada','cubierta','cancelada')) AS excluded,
 EXISTS(SELECT 1 FROM publications p2 WHERE p2.opportunity_id=o.id) AS has_publications,
 a.submitted_at,o.state_changed_at,o.rejection_reason_id,r.name AS rejection_reason
FROM opportunities o JOIN companies c ON c.id=o.company_id
LEFT JOIN applications a ON a.opportunity_id=o.id
LEFT JOIN publications p ON p.opportunity_id=o.id AND p.is_primary
LEFT JOIN rejection_reasons r ON r.id=o.rejection_reason_id
WHERE NOT EXISTS(SELECT 1 FROM opportunity_merges m WHERE m.source_id=o.id AND m.undone_at IS NULL);

COMMIT;
