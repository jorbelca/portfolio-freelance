BEGIN;
CREATE TABLE search_criteria (
 configuration_id integer NOT NULL REFERENCES search_configuration(id),
 rule_id text NOT NULL CHECK (rule_id IN ('seniority','experience','education','technology','languages','contract','functions','remote','video','availability','channel')),
 label text NOT NULL CHECK (length(label) BETWEEN 1 AND 200),
 instruction text NOT NULL CHECK (length(instruction) BETWEEN 1 AND 8000),
 pending text NOT NULL CHECK (length(pending) BETWEEN 1 AND 1000),
 PRIMARY KEY(configuration_id,rule_id)
);
COMMIT;
