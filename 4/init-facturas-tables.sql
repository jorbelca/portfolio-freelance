-- Esquema de la Demo 4 (extracción de facturas -> cola de revisión -> panel).
-- Reejecutable: CREATE TABLE usa IF NOT EXISTS; cambios posteriores van como ALTER
-- idempotentes al final, no editando los CREATE de arriba (mismo convenio que
-- 2/init-fincas-tables.sql).
--
-- Tres tablas, mismo reparto que 1/init-triage-tables.sql (expedientes / revision_humana /
-- triage_log) y 2/init-fincas-tables.sql (incidencias / revision_administrador):
--   facturas       -> aceptadas, dato limpio, lo que lee el panel/Power BI.
--   cola_revision  -> dudosas o inválidas, dato crudo tal cual lo extrajo el modelo, para que
--                     un humano corrija sin tener que releer el PDF desde cero.
--   extraccion_log -> TODO camino (incluido el feliz) escribe aquí. La trazabilidad no es una
--                     rama del grafo, es una propiedad suya: sin esto no se puede demostrar
--                     "acierta X de N y manda los dudosos a revisión con motivo".

-- facturas: contrato de datos de §14.3. Cada campo lleva su confianza aparte (confianza_campos),
-- porque una factura puede tener el total nítido y el NIF borroso -- una confianza global
-- escondería justo el campo que hace falta mirar.
CREATE TABLE IF NOT EXISTS facturas (
  id SERIAL PRIMARY KEY,
  proveedor_nombre TEXT,
  proveedor_nif TEXT NOT NULL,
  cliente_nombre TEXT,
  cliente_nif TEXT,
  numero_factura TEXT NOT NULL,
  fecha_emision DATE,
  base_imponible NUMERIC(10,2),
  tipo_iva NUMERIC(4,2),
  cuota_iva NUMERIC(10,2),
  total NUMERIC(10,2),
  concepto_resumen TEXT,
  -- {"proveedor_nif": 0.95, "total": 0.99, ...} -- una entrada por campo del contrato de datos.
  confianza_campos JSONB,
  -- min() de confianza_campos en el momento de la decisión. Se guarda materializada (no se
  -- recalcula de confianza_campos al leer) por el mismo motivo que umbral_aplicado en
  -- 2/init-fincas-tables.sql: el criterio de agregación (hoy min, ver grafo_facturas.py) puede
  -- cambiar con el tiempo, y congelar el valor vigente en cada decisión es lo que permite
  -- reproducir después por qué una factura concreta pasó el gate.
  confianza_minima NUMERIC(4,3),
  creado_en TIMESTAMPTZ DEFAULT now(),
  -- Único de negocio: misma clave que usa Hacienda para identificar una factura sin ambigüedad.
  -- Duplicarla (mismo proveedor + mismo número) es o un reenvío o un error de imputación, nunca
  -- una segunda factura real -- por eso el UNIQUE vive en SQL, no como un pre-check en Python
  -- (dos verdades que divergen en silencio si el grafo también deduplicara por su cuenta).
  UNIQUE (proveedor_nif, numero_factura)
);

-- cola_revision: mismo contrato de campos que facturas, sin el UNIQUE (una factura puede
-- llegar aquí precisamente por ser un duplicado, y dos duplicados legítimamente coexisten en
-- la cola hasta que un humano decide cuál es la buena). motivo es libre (no CHECK/enum) porque
-- el vocabulario de razones de cola lo fija el grafo (arithmetic, nif, fecha, sin numero,
-- duplicado, confianza baja, extracción fallida...) y puede crecer sin migración de esquema --
-- mismo criterio que elemento_normalizado en incidencias.
CREATE TABLE IF NOT EXISTS cola_revision (
  id SERIAL PRIMARY KEY,
  proveedor_nombre TEXT,
  proveedor_nif TEXT,
  cliente_nombre TEXT,
  cliente_nif TEXT,
  numero_factura TEXT,
  fecha_emision DATE,
  base_imponible NUMERIC(10,2),
  tipo_iva NUMERIC(4,2),
  cuota_iva NUMERIC(10,2),
  total NUMERIC(10,2),
  concepto_resumen TEXT,
  confianza_campos JSONB,
  confianza_minima NUMERIC(4,3),
  motivo TEXT NOT NULL,
  resuelto BOOLEAN DEFAULT false,
  creado_en TIMESTAMPTZ DEFAULT now()
);

-- extraccion_log: registro único de toda decisión del grafo, una fila por PDF procesado.
-- resultado distingue las tres salidas posibles del grafo (persistido / cola_revision /
-- error_extraccion -- esta última cuando el modelo no devuelve nada aprovechable, mismo caso
-- que 'sin_clasificar' en incidencias: el fallo no puede hacer desaparecer el caso).
-- factura_id / cola_id son nullable y mutuamente excluyentes según resultado (el CHECK de abajo
-- no lo impone a propósito: hacerlo con un CHECK cruzando dos columnas nullable es frágil en
-- Postgres si algún día se permite reprocesar; se deja como invariante de aplicación, verificado
-- por el arnés de eval).
CREATE TABLE IF NOT EXISTS extraccion_log (
  id SERIAL PRIMARY KEY,
  pdf_origen TEXT NOT NULL,
  resultado TEXT NOT NULL CHECK (resultado IN ('persistido', 'cola_revision', 'error_extraccion')),
  motivo TEXT,
  confianza_campos JSONB,
  confianza_minima NUMERIC(4,3),
  factura_id INTEGER REFERENCES facturas(id),
  cola_id INTEGER REFERENCES cola_revision(id),
  creado_en TIMESTAMPTZ DEFAULT now()
);

-- El eval empareja por pdf_origen (equivalente al message_id de las otras dos demos): impone
-- que cada PDF de la tanda deje como máximo un rastro en el log por ejecución del arnés.
CREATE INDEX IF NOT EXISTS idx_extraccion_log_pdf_origen ON extraccion_log (pdf_origen);
