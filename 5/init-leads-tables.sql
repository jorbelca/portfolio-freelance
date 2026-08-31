-- Esquema de la Demo 5 (cualificación de leads -> asignación -> primer contacto).
-- Reejecutable: CREATE TABLE usa IF NOT EXISTS; los cambios posteriores van como ALTER
-- idempotente al final, no editando los CREATE de arriba (mismo convenio que
-- 4/init-facturas-tables.sql).
--
-- Tres tablas, mismo reparto que 4/init-facturas-tables.sql (facturas / cola_revision /
-- extraccion_log):
--   leads             -> cualificados, dato limpio, lo que leería el CRM o el panel.
--   cola_revision     -> dudosos, sin evidencia suficiente, o borradores de email pendientes
--                        de revisar antes de enviarse.
--   cualificacion_log -> TODO camino (incluido el feliz) escribe aquí. La trazabilidad no es
--                        una rama del grafo, es una propiedad suya: sin esto no se puede
--                        demostrar "acierta X de N y manda los dudosos a revisión con motivo".

-- leads: cada lead cualificado con su etiqueta, la regla de la rúbrica que la produjo, y las
-- señales que la sostienen -- cada una con su respaldo de evidencia, porque un motivo cuya
-- señal cita un resultado web que ya ha cambiado es indistinguible de uno inventado.
CREATE TABLE IF NOT EXISTS leads (
  id SERIAL PRIMARY KEY,
  empresa TEXT NOT NULL,
  empresa_normalizada TEXT NOT NULL,
  contacto_nombre TEXT,
  contacto_email TEXT NOT NULL,
  contacto_cargo TEXT,
  canal_origen TEXT,
  -- Hechos de ficha_empresa (mock sobre dataset sintético; en producción, registro mercantil).
  pais TEXT,
  sector TEXT,
  tipo_negocio TEXT,             -- 'producto' | 'servicios' | NULL
  tamano_estimado INTEGER,
  antiguedad_anios NUMERIC(4,1),
  -- Resultado de la cualificación.
  etiqueta TEXT NOT NULL CHECK (etiqueta IN ('caliente', 'tibio', 'frio')),
  -- motivo: texto libre (el vocabulario lo fija la rúbrica y crece sin migración de esquema,
  -- mismo criterio que motivo en 4/cola_revision). regla es el identificador exacto (R8,
  -- R10...) para poder agrupar y auditar por regla.
  motivo TEXT NOT NULL,
  regla TEXT,
  -- señales: una entrada por señal citada en el motivo. La referencia de evidencia (snippet +
  -- url + recuperado_en) es lo que hace el motivo auditable sin fiarse del modelo.
  -- [{"tipo":"S1","valor":"Serie A £8M (mar 2026)","fuente":"buscar_senales",
  --   "snippet":"...","url":"https://...","recuperado_en":"2026-08-31T10:00:00Z"}]
  senales JSONB,
  confianza NUMERIC(4,3),
  -- V2 (cola de asignación/redacción). NULL en V1.
  asignado_a TEXT,              -- comercial, vía dict estático territorio/producto -> comercial
  followup_sugerido TEXT,       -- p.ej. "3 días" -- solo el texto en el log, sin integración de calendario
  borrador_message_id TEXT,     -- id del correo en GreenMail si se redactó borrador
  creado_en TIMESTAMPTZ DEFAULT now(),
  -- Dedup: única fuente de verdad, sin pre-check en Python (mismo criterio que el UNIQUE de
  -- 4/facturas). El UniqueViolation se reconduce a cola_revision con motivo 'duplicado'.
  --  - contacto_email: global. Un contacto es un contacto, esté como esté clasificado.
  --  - empresa_normalizada: PARCIAL, solo caliente/tibio (ver índice al final). Una cuenta que
  --    un comercial trabaja no debe abrirse dos veces; pero una empresa 'frio' (p.ej. fuera de
  --    UK) no reserva el nombre -- si más tarde llega un contacto mejor o la empresa abre
  --    entidad UK, ese lead se evalúa de cero en vez de chocar con un 'duplicado' que
  --    escondería el motivo real.
  UNIQUE (contacto_email)
);

-- cola_revision: mismo contrato de campos que leads, sin los UNIQUE (un lead puede llegar aquí
-- precisamente por ser un duplicado). etiqueta es nullable: si el caso es sin_cualificar, el
-- modelo no llegó a proponer una. tipo distingue las dos clases de cola: la cualificación
-- dudosa y el borrador de email de un 'caliente' esperando visto bueno humano (V2).
CREATE TABLE IF NOT EXISTS cola_revision (
  id SERIAL PRIMARY KEY,
  empresa TEXT,
  empresa_normalizada TEXT,
  contacto_nombre TEXT,
  contacto_email TEXT,
  contacto_cargo TEXT,
  canal_origen TEXT,
  pais TEXT,
  sector TEXT,
  tipo_negocio TEXT,
  tamano_estimado INTEGER,
  antiguedad_anios NUMERIC(4,1),
  etiqueta TEXT,                -- propuesta del modelo, o NULL si sin_cualificar
  senales JSONB,
  confianza NUMERIC(4,3),
  -- 'sin evidencia para cualificar' | 'confianza baja (0.42)' | 'duplicado' |
  -- 'frontera R13: caliente vs tibio' | 'borrador pendiente de revisión' ...
  motivo TEXT NOT NULL,
  tipo TEXT NOT NULL DEFAULT 'cualificacion' CHECK (tipo IN ('cualificacion', 'borrador')),
  borrador_message_id TEXT,     -- id en GreenMail cuando tipo = 'borrador'
  resuelto BOOLEAN DEFAULT false,
  creado_en TIMESTAMPTZ DEFAULT now()
);

-- cualificacion_log: registro único de toda decisión del grafo, una fila por lead procesado.
-- resultado distingue las tres salidas: cualificado (a leads), cola_revision (dudoso), y
-- sin_cualificar (el modelo no devolvió nada aprovechable o no había evidencia -- mismo caso
-- que 'error_extraccion' en la Demo 4: el fallo no puede hacer desaparecer el lead).
-- lead_id / cola_id son nullable y mutuamente excluyentes según resultado; no se impone con
-- CHECK cruzando columnas nullable (frágil en Postgres), se deja como invariante de
-- aplicación verificado por el arnés de eval -- igual que 4/extraccion_log.
CREATE TABLE IF NOT EXISTS cualificacion_log (
  id SERIAL PRIMARY KEY,
  -- id estable del lead en la entrada (equivalente al message_id / pdf_origen de las otras
  -- demos). El eval empareja por aquí e impone un rastro como máximo por lead y ejecución.
  lead_ref TEXT NOT NULL,
  resultado TEXT NOT NULL CHECK (resultado IN ('cualificado', 'cola_revision', 'sin_cualificar')),
  etiqueta TEXT,
  motivo TEXT,
  regla TEXT,
  senales JSONB,
  confianza NUMERIC(4,3),
  lead_id INTEGER REFERENCES leads(id),
  cola_id INTEGER REFERENCES cola_revision(id),
  creado_en TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_cualificacion_log_lead_ref ON cualificacion_log (lead_ref);

-- Dedup de empresa: solo entre las cuentas que un comercial trabaja (caliente/tibio). Ver el
-- comentario en la tabla leads. Índice único parcial -> el UniqueViolation salta igual y
-- persistir_ok lo reconduce a cola.
CREATE UNIQUE INDEX IF NOT EXISTS uq_leads_empresa_trabajada
  ON leads (empresa_normalizada) WHERE etiqueta IN ('caliente', 'tibio');

-- --- ALTERs idempotentes posteriores -------------------------------------------------------
