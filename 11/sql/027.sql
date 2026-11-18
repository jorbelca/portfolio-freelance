BEGIN;
-- Misma identidad pública que public/identity.js.
CREATE OR REPLACE FUNCTION publication_identity(value text) RETURNS text
LANGUAGE plpgsql IMMUTABLE STRICT AS $$
DECLARE
 host text := lower(substring(value from '^https?://([^/:?#]+)'));
 path text := substring(value from '^https?://[^/]+(/[^?#]*)');
 m text[];
BEGIN
 host := regexp_replace(host, '^www\.', '');
 IF host='infojobs.net' THEN
  m := regexp_match(path, '/(of-i[0-9a-f]+)(/|$)', 'i');
  RETURN 'infojobs:' || lower(m[1]);
 ELSIF host='linkedin.com' OR host LIKE '%.linkedin.com' THEN
  m := regexp_match(path, '/jobs/view/(?:[^/]*-)?(\d+)/?$');
  RETURN 'linkedin:' || m[1];
 ELSIF host='apply.workable.com' THEN
  m := regexp_match(path, '^/([^/]+)/j/([a-z0-9]+)(/|$)', 'i');
  RETURN 'workable:' || lower(m[1]) || ':' || upper(m[2]);
 ELSIF host IN ('boards.greenhouse.io','job-boards.greenhouse.io') THEN
  m := regexp_match(path, '^/([^/]+)/jobs/(\d+)(/|$)');
  RETURN 'greenhouse:' || lower(m[1]) || ':' || m[2];
 ELSIF host='jobs.lever.co' THEN
  m := regexp_match(path, '^/([^/]+)/([0-9a-f-]{36})(/|$)', 'i');
  RETURN 'lever:' || lower(m[1]) || ':' || lower(m[2]);
 ELSIF host='api.smartrecruiters.com' THEN
  m := regexp_match(path, '^/v1/companies/([^/]+)/postings/(\d+)(/|$)');
  RETURN 'smartrecruiters:' || lower(m[1]) || ':' || m[2];
 ELSIF host='jobs.smartrecruiters.com' THEN
  m := regexp_match(path, '^/([^/]+)/(\d+)(-|/|$)');
  RETURN 'smartrecruiters:' || lower(m[1]) || ':' || m[2];
 ELSIF host='emploive.com' THEN
  m := regexp_match(path, '^(?:/home)?/jobs/(\d+)(/|$)');
  RETURN 'emploive:' || m[1];
 ELSIF host='careers.indragroup.com' THEN
  m := regexp_match(path, '^/(?:[a-z0-9-]+/)?job/[^/]+/(\d+)/?$', 'i');
  RETURN 'indra:' || m[1];
 ELSIF host ~ '^[a-z0-9-]+\.wd\d+\.myworkdayjobs\.com$' THEN
  m := regexp_match(path, '^/(?:[^/]+/)?[^/]+/job/(?:[^/]+/)*[^/]*_((?:jr|r)-?\d+(?:-\d+)*)/?$', 'i');
  RETURN 'workday:' || host || ':' || lower(m[1]);
 END IF;
 RETURN NULL;
END;
$$;
-- Recalcula las claves de las publicaciones guardadas con la función anterior.
REINDEX INDEX publications_identity_idx;
COMMIT;
