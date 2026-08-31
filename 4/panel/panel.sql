-- Capa de panel de la Demo 4. Vistas sobre facturas + cola_revision + extraccion_log,
-- mismo convenio que 2/panel/panel.sql: Power BI (o cualquier BI) se conecta a estas vistas,
-- no a las tablas -- el modelo del panel no debe romperse cada vez que cambie una columna de
-- extracción. Requiere init-facturas-tables.sql aplicado antes. Reejecutable (CREATE OR REPLACE).

-- 1. Cola de revisión pendiente, más reciente primero. Es la vista de "qué tengo que mirar hoy".
CREATE OR REPLACE VIEW v_cola_pendiente AS
SELECT id, proveedor_nombre, proveedor_nif, numero_factura, total, motivo, confianza_minima, creado_en
FROM cola_revision
WHERE NOT resuelto
ORDER BY creado_en DESC;

-- 2. Motivos de cola más frecuentes. El número que responde "¿qué falla más, el OCR de NIFs o
-- la aritmética de los proveedores?" -- decide dónde afinar el prompt o el umbral primero.
CREATE OR REPLACE VIEW v_motivos_cola AS
SELECT
  -- motivo es texto libre con detalle variable (incluye el valor concreto que falló);
  -- se agrupa por la primera palabra antes de ':' para que "aritmética: ..." de dos facturas
  -- distintas cuente como el mismo motivo en vez de como dos motivos únicos.
  split_part(motivo, ':', 1) AS motivo_categoria,
  count(*)                   AS n_facturas,
  round(avg(confianza_minima), 3) AS confianza_media
FROM cola_revision
GROUP BY 1
ORDER BY n_facturas DESC;

-- 3. Importe total retenido en cola: el número que el comprador entiende sin explicación
-- ("tienes X EUR de facturas que nadie ha mirado todavía").
CREATE OR REPLACE VIEW v_importe_retenido AS
SELECT
  count(*) FILTER (WHERE NOT resuelto)                          AS n_pendientes,
  coalesce(sum(total) FILTER (WHERE NOT resuelto), 0)            AS importe_pendiente,
  count(*) FILTER (WHERE resuelto)                               AS n_resueltas,
  coalesce(sum(total) FILTER (WHERE resuelto), 0)                 AS importe_resuelto
FROM cola_revision;

-- 4. Tasa de paso directo vs. revisión, por día -- el número que justifica el mantenimiento
-- mensual: si la proporción de cola sube con el tiempo, algo cambió en el formato de facturas
-- de un proveedor o en el modelo, y toca mirar el prompt antes de que lo note el cliente.
CREATE OR REPLACE VIEW v_tasa_revision AS
SELECT
  date_trunc('day', creado_en)::date                              AS dia,
  count(*) FILTER (WHERE resultado = 'persistido')                AS persistidas,
  count(*) FILTER (WHERE resultado = 'cola_revision')              AS a_revision,
  count(*) FILTER (WHERE resultado = 'error_extraccion')           AS errores,
  round(100.0 * count(*) FILTER (WHERE resultado = 'persistido')
        / nullif(count(*), 0), 1)                                  AS pct_paso_directo
FROM extraccion_log
GROUP BY 1
ORDER BY 1 DESC;
