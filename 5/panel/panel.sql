-- Capa de panel de la Demo 5. Vistas sobre leads + cola_revision + cualificacion_log,
-- mismo convenio que 4/panel/panel.sql: cualquier BI se conecta a estas vistas, no a las
-- tablas. Requiere init-leads-tables.sql aplicado antes. Reejecutable (CREATE OR REPLACE).

-- 1. Cola de cualificación pendiente -- lo dudoso que un humano tiene que mirar hoy.
--    tipo = 'cualificacion' SOLO: los borradores de email (tipo = 'borrador') son otra cosa
--    (el sistema decidió con confianza y redactó), y mezclarlos falsea el "cuánto duda".
CREATE OR REPLACE VIEW v_cola_pendiente AS
SELECT id, empresa, contacto_email, etiqueta, motivo, confianza, creado_en
FROM cola_revision
WHERE tipo = 'cualificacion' AND NOT resuelto
ORDER BY creado_en DESC;

-- 2. Borradores de primer email pendientes de visto bueno (V2). Cola distinta: aquí el
--    sistema NO dudó -- clasificó caliente y escribió el correo; falta que un humano lo
--    apruebe antes de enviarlo. borrador_message_id es el id en GreenMail.
CREATE OR REPLACE VIEW v_borradores_pendientes AS
SELECT c.id, c.empresa, c.contacto_email, l.asignado_a, l.followup_sugerido,
       c.borrador_message_id, c.creado_en
FROM cola_revision c
LEFT JOIN leads l ON l.empresa_normalizada = c.empresa_normalizada
WHERE c.tipo = 'borrador' AND NOT c.resuelto
ORDER BY c.creado_en DESC;

-- 3. Motivos de cola de cualificación más frecuentes. Responde "¿qué me manda leads a
--    revisión, la falta de ficha o la confianza baja del modelo?" -- decide dónde afinar.
CREATE OR REPLACE VIEW v_motivos_cola AS
SELECT split_part(motivo, ':', 1) AS motivo_categoria,
       split_part(motivo, ' (', 1) AS motivo_subcategoria,
       count(*)                    AS n_leads,
       round(avg(confianza), 3)     AS confianza_media
FROM cola_revision
WHERE tipo = 'cualificacion'
GROUP BY 1, 2
ORDER BY n_leads DESC;

-- 4. Reparto de leads por etiqueta -- el pulso del pipeline. Si "frio" se dispara, o la
--    rúbrica está mal calibrada o la lista de leads que entra es mala.
CREATE OR REPLACE VIEW v_leads_por_etiqueta AS
SELECT etiqueta, count(*) AS n_leads, round(avg(confianza), 3) AS confianza_media,
       round(100.0 * count(*) / nullif(sum(count(*)) OVER (), 0), 1) AS pct
FROM leads
GROUP BY etiqueta
ORDER BY n_leads DESC;

-- 5. Qué regla de la rúbrica dispara cada decisión (del log). Es la vista de calibración:
--    si el 80% de los "tibio" son R12 ("sin disparador de timing"), el problema no es la
--    rúbrica, es que los leads llegan demasiado pronto.
CREATE OR REPLACE VIEW v_regla_frecuencia AS
SELECT coalesce(regla, '(sin regla)') AS regla,
       etiqueta,
       count(*) AS n_leads
FROM cualificacion_log
GROUP BY 1, 2
ORDER BY n_leads DESC;

-- 6. Tasa de paso directo vs. revisión por día -- el número del mantenimiento mensual: si la
--    proporción a cola sube, algo cambió en el modelo o en la calidad de los leads de entrada.
CREATE OR REPLACE VIEW v_tasa_cola AS
SELECT date_trunc('day', creado_en)::date                          AS dia,
       count(*) FILTER (WHERE resultado = 'cualificado')            AS cualificados,
       count(*) FILTER (WHERE resultado = 'cola_revision')          AS a_revision,
       count(*) FILTER (WHERE resultado = 'sin_cualificar')         AS sin_cualificar,
       round(100.0 * count(*) FILTER (WHERE resultado = 'cualificado')
             / nullif(count(*), 0), 1)                              AS pct_paso_directo
FROM cualificacion_log
GROUP BY 1
ORDER BY 1 DESC;
