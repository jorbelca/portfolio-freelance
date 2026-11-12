CREATE TABLE search_configuration (
 id integer PRIMARY KEY CHECK(id=1),
 revision integer NOT NULL DEFAULT 1 CHECK(revision>0),
 residence text NOT NULL,
 technical_degree boolean NOT NULL,
 professional_years numeric CHECK(professional_years>=0),
 internship_details text NOT NULL,
 relocation text NOT NULL CHECK(relocation IN ('si','no','desconocido')),
 work_authorization text NOT NULL,
 max_required_years integer NOT NULL CHECK(max_required_years>=0)
);
INSERT INTO search_configuration VALUES(1,1,'Banyeres de Mariola, Alicante, España',false,NULL,'Única experiencia en empresa: prácticas; duración, tecnologías y responsabilidades no acreditadas.','desconocido','No acreditada',3);
CREATE TABLE profile_skills (
 configuration_id integer NOT NULL REFERENCES search_configuration(id),
 name text NOT NULL CHECK(length(name) BETWEEN 1 AND 200),
 evidence text NOT NULL CHECK(length(evidence) BETWEEN 1 AND 2000),
 priority integer NOT NULL CHECK(priority>0),
 PRIMARY KEY(configuration_id,name)
);
INSERT INTO profile_skills SELECT 1,name,'Perfil aportado por el usuario',priority FROM (VALUES
 ('JavaScript',2),('TypeScript',2),('React',2),('Node.js',2),('PostgreSQL',2),('Docker',2),('Java',3),('Spring Boot',3),('Python',1),('Git',3),('Redes básicas',3),('AWS',3),('Azure',3),('LLM',1),('Agentes',1),('RAG',1),('Extracción de datos',1),('LangGraph',1)) AS skills(name,priority);
CREATE TABLE profile_qualifications (
 configuration_id integer NOT NULL REFERENCES search_configuration(id),
 name text NOT NULL CHECK(length(name) BETWEEN 1 AND 500),
 PRIMARY KEY(configuration_id,name)
);
INSERT INTO profile_qualifications VALUES(1,'DAW'),(1,'Especialización en Big Data e IA'),(1,'Grado universitario en Derecho');
CREATE TABLE profile_languages (
 configuration_id integer NOT NULL REFERENCES search_configuration(id),
 language text NOT NULL CHECK(length(language) BETWEEN 1 AND 100),
 level text NOT NULL CHECK(level IN ('A1','A2','B1','B2','C1','C2','nativo')),
 PRIMARY KEY(configuration_id,language)
);
INSERT INTO profile_languages VALUES(1,'Inglés','B2'),(1,'Valenciano','C1');
CREATE TABLE search_source_settings (
 configuration_id integer NOT NULL REFERENCES search_configuration(id),
 source text NOT NULL CHECK(length(source) BETWEEN 1 AND 200),
 enabled boolean NOT NULL,
 PRIMARY KEY(configuration_id,source)
);
INSERT INTO search_source_settings VALUES(1,'arbeitnow',true),(1,'arbeitnow_uk',true),(1,'remotive',true);
CREATE TABLE search_queries (
 id uuid PRIMARY KEY,
 configuration_id integer NOT NULL REFERENCES search_configuration(id),
 zone text NOT NULL CHECK(zone IN ('spain','europe','any')),
 language text NOT NULL CHECK(language IN ('es','en')),
 term text NOT NULL CHECK(length(trim(term)) BETWEEN 1 AND 200),
 UNIQUE(configuration_id,zone,language,term)
);
CREATE TABLE excluded_employers (
 configuration_id integer NOT NULL REFERENCES search_configuration(id),
 name text NOT NULL CHECK(length(name) BETWEEN 1 AND 500),
 PRIMARY KEY(configuration_id,name)
);
INSERT INTO excluded_employers VALUES(1,'CNAC'),(1,'Hubmud');
INSERT INTO search_queries VALUES
 ('b96ad4a2-a742-4f22-b2cb-9b3724c1d601',1,'any','es','desarrollador'),
 ('b96ad4a2-a742-4f22-b2cb-9b3724c1d602',1,'any','en','software'),
 ('b96ad4a2-a742-4f22-b2cb-9b3724c1d603',1,'any','en','developer'),
 ('b96ad4a2-a742-4f22-b2cb-9b3724c1d604',1,'any','en','engineer'),
 ('b96ad4a2-a742-4f22-b2cb-9b3724c1d605',1,'any','es','inteligencia artificial');
