WITH added AS (
 INSERT INTO profile_languages(configuration_id,language,level)
 SELECT 1,'Español','nativo'
 WHERE NOT EXISTS (
  SELECT 1 FROM profile_languages
  WHERE configuration_id=1 AND lower(language) IN ('español','castellano','spanish','es')
 )
 ON CONFLICT DO NOTHING
 RETURNING configuration_id
)
UPDATE search_configuration SET revision=revision+1
WHERE id IN (SELECT configuration_id FROM added);
