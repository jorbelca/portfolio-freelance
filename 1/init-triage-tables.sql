CREATE TABLE IF NOT EXISTS expedientes (
  id SERIAL PRIMARY KEY,
  nombre_contacto TEXT,
  email_contacto TEXT,
  estado TEXT,
  urgente BOOLEAN DEFAULT false,
  notas TEXT,
  creado_en TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS expediente_notas (
  id SERIAL PRIMARY KEY,
  expediente_email TEXT,
  nota TEXT,
  creado_en TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS revision_humana (
  id SERIAL PRIMARY KEY,
  remitente TEXT,
  asunto TEXT,
  motivo_duda TEXT,
  revisado BOOLEAN DEFAULT false,
  creado_en TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS errores (
  id SERIAL PRIMARY KEY,
  workflow TEXT,
  nodo TEXT,
  mensaje TEXT,
  creado_en TIMESTAMPTZ DEFAULT now()
);

-- unaccent: mitigación pendiente para el hueco descrito en rubrica-intake-legal.md sección 7 punto 4
-- (ILIKE ignora mayúsculas pero no tildes). Se instala aquí; ninguna query la usa todavía.
CREATE EXTENSION IF NOT EXISTS unaccent;

-- triage_log: registro único de toda decisión de triage. decidido_por: 'sistema' (clasificó y se
-- ejecutó la rama determinada por su categoría), 'umbral' (fue a revisión por confianza baja,
-- conservando la categoría propuesta) o 'humano' (lo resolvió una persona después).
CREATE TABLE IF NOT EXISTS triage_log (
  id SERIAL PRIMARY KEY,
  message_id TEXT UNIQUE NOT NULL,
  remitente TEXT,
  asunto TEXT,
  cuerpo TEXT,
  categoria TEXT,
  motivo TEXT,
  confianza NUMERIC(3,2),
  accion TEXT,
  decidido_por TEXT,
  creado_en TIMESTAMPTZ DEFAULT now()
);

-- documentos_despacho: nombre de tabla y columnas (id/text/metadata/embedding) verificados contra
-- los defaults del nodo @n8n/n8n-nodes-langchain.vectorStorePGVector (columnNamesField.default en
-- VectorStorePGVector.node.js de n8n:latest). El nodo NO fija una dimensión (no pasa `dimensions` a
-- ensureTableInDatabase), así que si él mismo creara la tabla usaría un `vector` sin restricción de
-- tamaño. vector(3072) está VERIFICADO contra datos reales: `select vector_dims(embedding) from
-- documentos_despacho` devuelve 3072 sobre las filas que ya ingirió el modelo de embeddings real
-- (Gemini, models/gemini-embedding-001). El aviso del propio nodo en la UI dice "768-dimensional",
-- pero eso no se corresponde con lo que el modelo devuelve en la práctica.
-- pgvector no admite dimensión variable: cambiar de modelo de embeddings obliga a
-- ALTER TABLE documentos_despacho ALTER COLUMN embedding TYPE vector(N) y a reprocesar el corpus.
CREATE TABLE IF NOT EXISTS documentos_despacho (
  id SERIAL PRIMARY KEY,
  text TEXT,
  metadata JSONB,
  embedding vector(3072)
);
