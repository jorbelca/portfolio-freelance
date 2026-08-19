-- Esquema de la Demo B (triage jurídico de incidencias de comunidades de propietarios).
-- Todo el fichero es reejecutable: CREATE TABLE/INDEX usan IF NOT EXISTS, y la única función
-- usa CREATE OR REPLACE (Postgres no tiene "CREATE FUNCTION IF NOT EXISTS"; OR REPLACE con el
-- mismo cuerpo logra la misma idempotencia).

-- Ya están instaladas en esta base (compartida con la Demo A), pero se declaran igualmente
-- por si este fichero se ejecuta alguna vez contra una base nueva.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS unaccent;

-- comunidades: las fincas. comunidad_id es el identificador de negocio (aparece en los estatutos
-- que gestiona el otro agente en 2/comunidades/, en el vector store y en cada incidencia), así
-- que es la propia PK en vez de un SERIAL interno.
CREATE TABLE IF NOT EXISTS comunidades (
  comunidad_id TEXT PRIMARY KEY,
  nombre TEXT NOT NULL,
  direccion TEXT,
  num_propietarios INTEGER,
  presupuesto_ordinario_anual NUMERIC,
  creado_en TIMESTAMPTZ DEFAULT now()
);

-- propietarios: vecinos ficticios. UNIQUE(comunidad_id, email) en vez de único global porque
-- nada impide que la misma persona figure en dos comunidades (p.ej. hereda un piso en otra
-- finca), y de paso da un target natural para el ON CONFLICT del seed.
CREATE TABLE IF NOT EXISTS propietarios (
  id SERIAL PRIMARY KEY,
  comunidad_id TEXT NOT NULL REFERENCES comunidades(comunidad_id),
  nombre TEXT NOT NULL,
  email TEXT NOT NULL,
  piso TEXT,
  puerta TEXT,
  creado_en TIMESTAMPTZ DEFAULT now(),
  UNIQUE (comunidad_id, email)
);

-- incidencias: registro central del triage.
--
-- propietario_email es TEXT libre, sin FK a propietarios: el remitente real de un correo puede
-- ser un inquilino, un administrador de fincas externo o alguien que aún no está en el censo, y
-- exigir que exista en `propietarios` bloquearía el alta de la incidencia por un motivo ajeno a
-- si la incidencia es válida.
--
-- elemento_normalizado NO lleva CHECK de vocabulario cerrado a propósito: lo decide el
-- clasificador (prompt), y el vocabulario puede crecer sin que eso implique una migración de
-- esquema. La tabla y la función de deduplicación solo necesitan tratarlo como clave de texto.
--
-- imputacion / imputacion_rival: mismo dominio ('comun'|'privativo'|'mixto'). imputacion_rival
-- es la segunda opción más plausible cuando el clasificador dudó entre dos categorías (puede
-- venir NULL si no hubo ambigüedad relevante); guardarla permite auditar después los casos límite
-- sin tener que releer fundamento JSONB para reconstruirla.
--
-- umbral_aplicado se guarda aparte de confianza porque el umbral de decisión puede cambiar con
-- el tiempo (se afina el sistema); congelar el umbral vigente en el momento de cada decisión es
-- lo que permite reproducir después por qué una incidencia concreta fue a revisión o no.
--
-- incidencia_padre_id apunta SIEMPRE a la incidencia raíz del mismo suceso (la primera reportada),
-- nunca al mensaje inmediatamente anterior: así el grupo entero es una consulta de un salto
-- (WHERE incidencia_padre_id = raiz.id) en vez de tener que recorrer una cadena.
--
-- plazos_activos JSONB es una copia de lectura rápida (para UI/n8n) del estado resumido de los
-- plazos de esta incidencia; la tabla `plazos` de abajo es la fuente de verdad, no esta columna.
CREATE TABLE IF NOT EXISTS incidencias (
  id SERIAL PRIMARY KEY,
  message_id TEXT UNIQUE NOT NULL,
  comunidad_id TEXT NOT NULL REFERENCES comunidades(comunidad_id),
  propietario_email TEXT NOT NULL,
  descripcion TEXT,
  elemento_normalizado TEXT,
  imputacion TEXT CHECK (imputacion IN ('comun', 'privativo', 'mixto')),
  imputacion_rival TEXT CHECK (imputacion_rival IS NULL OR imputacion_rival IN ('comun', 'privativo', 'mixto')),
  fundamento JSONB,
  urgencia BOOLEAN,
  requiere_junta BOOLEAN,
  plazos_activos JSONB,
  confianza NUMERIC(3,2),
  umbral_aplicado NUMERIC(3,2),
  accion TEXT,
  decidido_por TEXT CHECK (decidido_por IN ('sistema', 'umbral', 'humano')),
  incidencia_padre_id INTEGER REFERENCES incidencias(id),
  creado_en TIMESTAMPTZ DEFAULT now()
);

-- Índice parcial (solo raíces, incidencia_padre_id IS NULL) que cubre exactamente la consulta de
-- buscar_incidencia_raiz(): mismas columnas y mismo orden que su WHERE + ORDER BY. Parcial porque
-- las filas hijas nunca son candidatas a raíz, así que indexarlas sería puro peso muerto.
CREATE INDEX IF NOT EXISTS idx_incidencias_dedup
  ON incidencias (comunidad_id, elemento_normalizado, creado_en)
  WHERE incidencia_padre_id IS NULL;

-- plazos: vencimientos vivos, para poder avisar ANTES de que venza (no al vencer).
-- vence es una columna normal, NO generada (inicio + dias_plazo), aunque esa es la regla:
-- el workflow de n8n que da de alta el plazo hace el INSERT con las 5 columnas ya calculadas, y
-- una columna GENERATED ALWAYS rechaza cualquier INSERT que le pase un valor explícito para ella.
-- La regla queda documentada aquí para quien escriba ese INSERT, no impuesta por el motor.
-- Por ahora solo existe un tipo, 'siniestro_lcs16' (7 días, plazo del art. 16 LCS para comunicar
-- el siniestro a la aseguradora); tipo se deja TEXT libre en vez de CHECK/enum por el mismo motivo
-- que elemento_normalizado: añadir un segundo tipo de plazo no debe requerir tocar el esquema.
CREATE TABLE IF NOT EXISTS plazos (
  id SERIAL PRIMARY KEY,
  incidencia_id INTEGER NOT NULL REFERENCES incidencias(id),
  tipo TEXT NOT NULL,
  dias_plazo INTEGER NOT NULL,
  inicio DATE NOT NULL,
  vence DATE NOT NULL,
  avisado BOOLEAN DEFAULT false,
  cerrado BOOLEAN DEFAULT false,
  creado_en TIMESTAMPTZ DEFAULT now()
);

-- Soporta "qué plazos abiertos vencen pronto y no se han avisado todavía" sin escanear la tabla
-- entera; parcial (WHERE NOT cerrado) porque los plazos cerrados no participan en ese aviso.
CREATE INDEX IF NOT EXISTS idx_plazos_por_vencer ON plazos (vence) WHERE NOT cerrado;

-- documentos_comunidad: vector store de estatutos, uno por comunidad (aislados vía metadata).
-- id/text/metadata/embedding son los nombres por defecto del nodo
-- @n8n/n8n-nodes-langchain.vectorStorePGVector (columnNamesField.default). El nodo no fija una
-- dimensión al crear la tabla él mismo (no pasa `dimensions` a ensureTableInDatabase); vector(3072)
-- aquí es una ASUNCIÓN sobre el modelo de embeddings que se vaya a usar, sin verificar con una
-- llamada real a la API. Si la dimensión real no es 3072, el primer insert falla con un error de
-- tipo vector y la corrección es de una línea (cambiar el número).
-- metadata llevará {"comunidad_id": "...", "documento": "...", "pagina": N}.
CREATE TABLE IF NOT EXISTS documentos_comunidad (
  id SERIAL PRIMARY KEY,
  text TEXT,
  metadata JSONB,
  embedding vector(3072)
);

-- El aislamiento entre comunidades se aplica en cada búsqueda como
-- WHERE metadata->>'comunidad_id' = $n (los estatutos de una finca no deben aparecer en las
-- respuestas de otra). Sin este índice ese filtro de confidencialidad —que se ejecuta en el 100%
-- de las búsquedas, no es opcional— sería también el cuello de botella: un scan completo de la
-- tabla en JSONB por cada pregunta.
CREATE INDEX IF NOT EXISTS idx_documentos_comunidad_comunidad_id
  ON documentos_comunidad ((metadata->>'comunidad_id'));

-- revision_administrador: cola de revisión humana. decision_final usa el mismo dominio que
-- incidencias.imputacion (en vez de texto libre) precisamente para poder comparar
-- incidencias.imputacion vs revision_administrador.decision_final con un simple <> y medir dónde
-- discreparon sistema y humano, sin normalizar texto libre a posteriori.
CREATE TABLE IF NOT EXISTS revision_administrador (
  id SERIAL PRIMARY KEY,
  incidencia_id INTEGER NOT NULL REFERENCES incidencias(id),
  motivo_escalado TEXT,
  resuelto BOOLEAN DEFAULT false,
  decision_final TEXT CHECK (decision_final IS NULL OR decision_final IN ('comun', 'privativo', 'mixto')),
  creado_en TIMESTAMPTZ DEFAULT now()
);

-- buscar_incidencia_raiz: la consulta de "búsqueda antes de insertar" para la deduplicación por
-- suceso (tres vecinos distintos avisando de la misma fuga -> una incidencia, no tres).
--
-- Se llama ANTES de insertar la nueva incidencia:
--   SELECT buscar_incidencia_raiz('CDP-001', 'bajante', now());
-- Si devuelve NULL, la nueva fila es raíz (incidencia_padre_id = NULL). Si devuelve un id, la
-- nueva fila es hija de esa raíz (incidencia_padre_id = id devuelto). El dedup por message_id
-- (reenvío exacto del mismo correo) es aparte y lo cubre la restricción UNIQUE de esa columna vía
-- INSERT ... ON CONFLICT (message_id) DO NOTHING; esta función no lo gestiona.
--
-- Clave natural: (comunidad_id, elemento_normalizado, ventana de 72h). El propietario NO entra
-- en la clave a propósito: el caso a cubrir es justo que avisan varios vecinos distintos de un
-- mismo elemento común averiado.
--
-- La ventana de 72h se ancla al creado_en de la RAÍZ (WHERE incidencia_padre_id IS NULL), no al
-- del último mensaje del grupo ("ventana deslizante"). Es una decisión deliberada: con ventana
-- deslizante un mismo suceso podría ir acumulando mensajes indefinidamente si llegan uno cada 71h;
-- anclado a la raíz, un suceso agrupa como máximo 72h de reportes y es trivial de razonar y de
-- probar. Efecto práctico: un aviso a más de 72h de la raíz abre una incidencia nueva (independiente),
-- aunque sea del mismo elemento y comunidad.
--
-- Sin similitud semántica ni LLM aquí: comparación exacta de comunidad_id + elemento_normalizado
-- y una resta de timestamps. Determinista por requisito (el arnés de evaluación asume misma
-- entrada -> misma salida).
CREATE OR REPLACE FUNCTION buscar_incidencia_raiz(
  p_comunidad_id TEXT,
  p_elemento_normalizado TEXT,
  p_momento TIMESTAMPTZ DEFAULT now()
) RETURNS INTEGER AS $$
  SELECT id
  FROM incidencias
  WHERE comunidad_id = p_comunidad_id
    AND elemento_normalizado = p_elemento_normalizado
    AND incidencia_padre_id IS NULL
    AND creado_en <= p_momento
    AND creado_en >= p_momento - INTERVAL '72 hours'
  ORDER BY creado_en DESC
  LIMIT 1;
$$ LANGUAGE sql STABLE;

-- ---------------------------------------------------------------------------------------------
-- Ajustes posteriores al primer diseño. Van como ALTER idempotentes, no editando los CREATE de
-- arriba, porque CREATE TABLE IF NOT EXISTS no toca una tabla que ya existe: sin esto, una base
-- creada con la versión anterior del fichero se quedaría sin los cambios.
-- ---------------------------------------------------------------------------------------------

-- comunidad_id pasa a admitir NULL. Motivo: un correo cuyo remitente no está en el censo no
-- tiene comunidad que resolver, y por la compuerta de confidencialidad no puede pasar por el
-- RAG (sin comunidad_id el filtro de metadatos queda vacío y la búsqueda devolvería fragmentos
-- de todas las fincas). Pero tiene que quedar registrado igual: si esa rama no escribe fila, es
-- la única del sistema que no deja rastro, y nadie vuelve a mirar ese correo. Antes se resolvía
-- mandando solo un aviso por correo, que es exactamente el fallo que esta columna nullable evita.
ALTER TABLE incidencias ALTER COLUMN comunidad_id DROP NOT NULL;

-- 'compuerta' como cuarto valor de decidido_por: la incidencia no la escaló el modelo (`sistema`),
-- ni el umbral de confianza (`umbral`), ni una persona (`humano`), sino una regla estructural del
-- flujo antes de clasificar. Distinguirlo importa porque el log es la pieza que se audita: "¿por
-- qué esto no se clasificó?" tiene una respuesta distinta a "¿por qué se clasificó con dudas?".
ALTER TABLE incidencias DROP CONSTRAINT IF EXISTS incidencias_decidido_por_check;
ALTER TABLE incidencias ADD CONSTRAINT incidencias_decidido_por_check
  CHECK (decidido_por IN ('sistema', 'umbral', 'humano', 'compuerta'));

-- 'no_aplica' como cuarto valor de imputacion. Motivo: la bandeja de un administrador mezcla
-- averías con consultas que no son incidencias técnicas (fecha de la junta, un certificado para
-- el banco, una queja de ruidos entre vecinos, una duda sobre el reparto del ascensor). Sin este
-- valor el clasificador está obligado a elegir entre comun/privativo/mixto, y esas consultas
-- acaban registradas como 'mixto', que según la sección 2 de la rúbrica significa "causa o
-- alcance realmente repartido". Sería una entrada falsa en el log, y el log es justo la pieza
-- que se audita: "¿por qué esto está en mi cola?" no puede responderse con "imputación mixta"
-- cuando la respuesta real es "no hay nada que imputar". No_aplica va a la cola igualmente
-- (alguien tiene que contestar), pero con el motivo correcto.
ALTER TABLE incidencias DROP CONSTRAINT IF EXISTS incidencias_imputacion_check;
ALTER TABLE incidencias ADD CONSTRAINT incidencias_imputacion_check
  CHECK (imputacion IN ('comun', 'privativo', 'mixto', 'no_aplica'));
ALTER TABLE incidencias DROP CONSTRAINT IF EXISTS incidencias_imputacion_rival_check;
ALTER TABLE incidencias ADD CONSTRAINT incidencias_imputacion_rival_check
  CHECK (imputacion_rival IS NULL OR imputacion_rival IN ('comun', 'privativo', 'mixto', 'no_aplica', 'ninguna'));

-- Quinta vía de decisión: la regla dura de dependencia estatutaria (§6 de la rúbrica) manda el
-- caso a un humano por una razón distinta al umbral de confianza, y el log tiene que poder
-- distinguirlas: 'umbral' = el modelo dudaba, 'estatutos' = la respuesta depende de la escritura
-- de esa finca, 'compuerta' = no se identificó al remitente.
ALTER TABLE incidencias DROP CONSTRAINT IF EXISTS incidencias_decidido_por_check;
ALTER TABLE incidencias ADD CONSTRAINT incidencias_decidido_por_check
  CHECK (decidido_por IN ('sistema','umbral','humano','compuerta','estatutos'));

-- Quinto valor de imputacion: 'sin_clasificar'. Cuando el agente no devuelve salida (modelo
-- caido, JSON irrecuperable), el nodo de controles emitia una excepcion y la incidencia no
-- llegaba a ninguna tabla; como el trigger IMAP marca el correo como leido ANTES de ejecutar,
-- el caso se perdia entero. Paso con i21 en la tirada de las 45. Ahora entra con esta etiqueta,
-- confianza 0 y accion revision_administrador: queda a la vista de un humano en vez de
-- desaparecer, y la etiqueta no finge una clasificacion que nadie hizo.
ALTER TABLE incidencias DROP CONSTRAINT IF EXISTS incidencias_imputacion_check;
ALTER TABLE incidencias ADD CONSTRAINT incidencias_imputacion_check
  CHECK (imputacion IN ('comun','privativo','mixto','no_aplica','sin_clasificar'));
