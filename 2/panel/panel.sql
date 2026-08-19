-- Capa de panel de la Demo B (flujo B2 de la planificación).
--
-- Por qué el gasto vive en su propia tabla y no como una columna de `incidencias`:
-- el triage decide QUIÉN paga; la contabilidad registra CUÁNTO se pagó, y existe en el despacho
-- antes y al margen de este sistema. Modelarlo como una tabla aparte que se une por
-- `incidencia_id` cuando lo hay refleja eso, y permite sembrar un trimestre de contabilidad
-- sintética sin depender de haber procesado antes ninguna incidencia.
--
-- Requiere init-fincas-tables.sql aplicado antes (necesita la tabla `comunidades`).
-- Idempotente y reejecutable.

CREATE TABLE IF NOT EXISTS gastos (
  id SERIAL PRIMARY KEY,
  comunidad_id TEXT NOT NULL REFERENCES comunidades(comunidad_id),
  -- Nullable a propósito: la contabilidad histórica es anterior al triage y no tiene incidencia
  -- asociada. Cuando el sistema esté en marcha, las nuevas sí la tendrán.
  incidencia_id INTEGER REFERENCES incidencias(id),
  fecha DATE NOT NULL,
  elemento_normalizado TEXT,
  -- A quién se imputó EN LA CONTABILIDAD, que no es necesariamente lo que el triage habría
  -- dicho. La diferencia entre estas dos columnas es el argumento de venta de la primera
  -- reunión: dinero repartido de una forma que nadie ha vuelto a mirar.
  imputado_a TEXT CHECK (imputado_a IN ('comun', 'privativo')),
  proveedor TEXT,
  importe NUMERIC(10,2) NOT NULL,
  concepto TEXT,
  -- Clave natural para poder resembrar sin duplicar.
  UNIQUE (comunidad_id, fecha, proveedor, importe, concepto)
);

CREATE INDEX IF NOT EXISTS idx_gastos_comunidad_fecha ON gastos (comunidad_id, fecha);

-- Un trimestre de contabilidad sintética. Los importes están elegidos para que el reparto salga
-- en ~55 % común (CDP-001), ~45 % (CDP-002) y ~80 % (CDP-003): CDP-003 es la anomalía visible del
-- panel, el caso que el vídeo señala ("aquí hay dinero mal repartido, y hasta hoy no lo miraba
-- nadie").
--
-- Y la anomalía no es un número inventado: tres de los gastos de CDP-003 son carpintería exterior
-- imputada a común, cuando el artículo 4º de sus propios estatutos la atribuye expresamente a cada
-- propietario. La finca lleva un trimestre pagando de fondo común lo que su título dice que es
-- privativo. Eso es lo que el panel enseña y lo que el RAG puede fundamentar con la cláusula en la
-- mano: el argumento de venta no es el gráfico, es la cláusula debajo del gráfico.
INSERT INTO gastos (comunidad_id, fecha, elemento_normalizado, imputado_a, proveedor, importe, concepto) VALUES
  ('CDP-001', '2026-04-08', 'bajante',            'comun',     'Fontanería Ejemplo SL',   340.00, 'Reparación bajante patio interior'),
  ('CDP-001', '2026-04-21', 'terraza',            'comun',     'Impermeabilizaciones Modelo SL', 1250.00, 'Sellado terraza atico 6A'),
  ('CDP-001', '2026-05-03', 'derivacion_particular', 'privativo', 'Fontanería Ejemplo SL', 145.00, 'Derivacion particular 2B'),
  ('CDP-001', '2026-05-14', 'ascensor',           'comun',     'Ascensores Ficticios SA', 480.00, 'Mantenimiento trimestral'),
  ('CDP-001', '2026-05-27', 'instalacion_electrica', 'comun',  'Electricidad Muestra SL', 275.00, 'Cuadro general portal B'),
  ('CDP-001', '2026-06-05', 'ventana',            'privativo', 'Cerrajería Prototipo SL', 210.00, 'Ventana 4C'),
  ('CDP-001', '2026-06-11', 'fachada',            'comun',     'Reformas Genéricas SL',   890.00, 'Repaso revestimiento fachada norte'),
  ('CDP-001', '2026-06-23', 'instalacion_agua',   'privativo', 'Fontanería Ejemplo SL',   160.00, 'Llave de paso 1A'),
  ('CDP-001', '2026-04-30', 'derivacion_particular', 'privativo', 'Fontanería Ejemplo SL', 620.00, 'Fuga derivacion 5A y reposicion alicatado'),
  ('CDP-001', '2026-05-20', 'ventana',            'privativo', 'Cerrajería Prototipo SL', 540.00, 'Sustitucion ventanal 6B'),
  ('CDP-001', '2026-06-02', 'instalacion_electrica', 'privativo', 'Electricidad Muestra SL', 480.00, 'Reforma cuadro interior 3A'),
  ('CDP-001', '2026-06-26', 'terraza',            'privativo', 'Reformas Genéricas SL',   495.00, 'Retirada jardineras y limpieza sumideros 6A'),

  ('CDP-002', '2026-04-04', 'cubierta',           'comun',     'Reformas Genéricas SL',   720.00, 'Reparacion faldon cubierta'),
  ('CDP-002', '2026-04-19', 'terraza',            'privativo', 'Reformas Genéricas SL',   385.00, 'Solado terraza 5 Izq'),
  ('CDP-002', '2026-05-02', 'instalacion_agua',   'comun',     'Fontanería Ejemplo SL',   295.00, 'Montante general'),
  ('CDP-002', '2026-05-16', 'derivacion_particular', 'privativo', 'Fontanería Ejemplo SL', 130.00, 'Derivacion 3 Der'),
  ('CDP-002', '2026-05-29', 'ventana',            'privativo', 'Cerrajería Prototipo SL', 240.00, 'Carpinteria 2 Izq'),
  ('CDP-002', '2026-06-09', 'fachada',            'comun',     'Reformas Genéricas SL',   610.00, 'Grietas fachada posterior'),
  ('CDP-002', '2026-06-18', 'instalacion_electrica', 'privativo', 'Electricidad Muestra SL', 175.00, 'Cuadro interior 4 Der'),
  ('CDP-002', '2026-06-27', 'bajante',            'comun',     'Fontanería Ejemplo SL',   410.00, 'Bajante fachada posterior'),
  ('CDP-002', '2026-04-25', 'derivacion_particular', 'privativo', 'Fontanería Ejemplo SL', 560.00, 'Fuga bajo fregadero 2 Izq'),
  ('CDP-002', '2026-05-22', 'ventana',            'privativo', 'Cerrajería Prototipo SL', 520.00, 'Carpinteria 5 Der'),
  ('CDP-002', '2026-06-24', 'instalacion_agua',   'privativo', 'Fontanería Ejemplo SL',   480.00, 'Sustitucion tuberia interior 1 Izq'),

  ('CDP-003', '2026-04-06', 'garaje',             'comun',     'Reformas Genéricas SL',   540.00, 'Puerta automatica garaje'),
  ('CDP-003', '2026-04-15', 'ventana',            'comun',     'Cerrajería Prototipo SL', 320.00, 'Carpinteria exterior 3-2'),
  ('CDP-003', '2026-04-28', 'ventana',            'comun',     'Cerrajería Prototipo SL', 295.00, 'Carpinteria exterior 5-1'),
  ('CDP-003', '2026-05-07', 'instalacion_agua',   'comun',     'Fontanería Ejemplo SL',   380.00, 'Grupo de presion'),
  ('CDP-003', '2026-05-19', 'derivacion_particular', 'comun',  'Fontanería Ejemplo SL',   190.00, 'Derivacion 6-3'),
  ('CDP-003', '2026-05-25', 'ventana',            'comun',     'Cerrajería Prototipo SL', 305.00, 'Carpinteria exterior 7-1'),
  ('CDP-003', '2026-06-03', 'trastero',           'comun',     'Reformas Genéricas SL',   225.00, 'Humedad trastero 12'),
  ('CDP-003', '2026-06-14', 'ascensor',           'comun',     'Ascensores Ficticios SA', 495.00, 'Mantenimiento trimestral'),
  ('CDP-003', '2026-06-21', 'cubierta',           'comun',     'Reformas Genéricas SL',   860.00, 'Impermeabilizacion cubierta'),
  ('CDP-003', '2026-06-29', 'derivacion_particular', 'privativo', 'Fontanería Ejemplo SL', 155.00, 'Derivacion 2-1'),
  ('CDP-003', '2026-05-12', 'derivacion_particular', 'privativo', 'Fontanería Ejemplo SL', 410.00, 'Fuga interior 4-2'),
  ('CDP-003', '2026-06-17', 'instalacion_electrica', 'privativo', 'Electricidad Muestra SL', 340.00, 'Cuadro interior 7-3')
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------------------------------
-- Vistas. Power BI se conecta a estas, no a las tablas: el modelo del panel no debe romperse
-- cada vez que cambie una columna del triage.
-- ---------------------------------------------------------------------------------------------

-- 1. Reparto común/privativo por comunidad y mes. Es el panel de la primera reunión.
CREATE OR REPLACE VIEW v_reparto_imputacion AS
SELECT
  g.comunidad_id,
  c.nombre                                   AS comunidad,
  date_trunc('month', g.fecha)::date         AS mes,
  g.imputado_a,
  count(*)                                   AS n_gastos,
  sum(g.importe)                             AS importe
FROM gastos g
JOIN comunidades c USING (comunidad_id)
GROUP BY 1, 2, 3, 4;

-- 2. La anomalía, ya calculada. Qué proporción del gasto carga cada finca a la comunidad:
-- una finca muy por encima de las demás está repartiendo mal, o tiene un problema estructural.
-- La vista no dictamina cuál de las dos cosas es: eso es trabajo del administrador.
CREATE OR REPLACE VIEW v_proporcion_comun AS
SELECT
  g.comunidad_id,
  c.nombre                                                        AS comunidad,
  sum(g.importe)                                                  AS gasto_total,
  sum(g.importe) FILTER (WHERE g.imputado_a = 'comun')            AS gasto_comun,
  round(100.0 * sum(g.importe) FILTER (WHERE g.imputado_a = 'comun')
        / nullif(sum(g.importe), 0), 1)                           AS pct_comun
FROM gastos g
JOIN comunidades c USING (comunidad_id)
GROUP BY 1, 2;

-- 3. Gasto por proveedor y comunidad.
CREATE OR REPLACE VIEW v_gasto_proveedor AS
SELECT g.comunidad_id, c.nombre AS comunidad, g.proveedor,
       count(*) AS n_gastos, sum(g.importe) AS importe
FROM gastos g
JOIN comunidades c USING (comunidad_id)
GROUP BY 1, 2, 3;

-- 4. Estado de los plazos. `dias_restantes` en negativo es un plazo ya vencido. El panel debe
-- avisar en la franja 'por_vencer', no cuando ya no hay nada que hacer.
CREATE OR REPLACE VIEW v_plazos_estado AS
SELECT
  p.id, p.incidencia_id, i.comunidad_id, c.nombre AS comunidad,
  p.tipo, p.inicio, p.vence, p.avisado, p.cerrado,
  (p.vence - CURRENT_DATE)      AS dias_restantes,
  CASE
    WHEN p.cerrado                       THEN 'cerrado'
    WHEN p.vence < CURRENT_DATE          THEN 'vencido'
    WHEN p.vence <= CURRENT_DATE + 2     THEN 'por_vencer'
    ELSE 'vivo'
  END                            AS estado
FROM plazos p
JOIN incidencias i ON i.id = p.incidencia_id
JOIN comunidades c ON c.comunidad_id = i.comunidad_id;

-- 5. Reincidencia: mismo elemento repitiéndose en la misma finca. Cuenta grupos de incidencia
-- (solo raíces), no mensajes, para que tres vecinos avisando de una fuga no inflen la señal.
-- Es lo que precede a una derrama, y hoy no lo mira nadie.
CREATE OR REPLACE VIEW v_incidencias_reincidentes AS
SELECT
  i.comunidad_id, c.nombre AS comunidad, i.elemento_normalizado,
  count(*)                          AS n_incidencias,
  min(i.creado_en)::date            AS primera,
  max(i.creado_en)::date            AS ultima
FROM incidencias i
JOIN comunidades c ON c.comunidad_id = i.comunidad_id
WHERE i.incidencia_padre_id IS NULL
GROUP BY 1, 2, 3
HAVING count(*) > 1;

-- 6. Todas las decisiones, con una bandera de escalado. Cubre TODAS las incidencias a propósito,
-- no solo las escaladas: una vista que solo contuviera escalados no permite calcular la tasa de
-- escalado, porque le falta el denominador. Los escalados se sacan filtrando `escalado`.
-- Es la vista que justifica el mantenimiento mensual: sin ella, "reviso la cola de casos
-- dudosos" no se puede demostrar con un número.
CREATE OR REPLACE VIEW v_decisiones AS
SELECT
  i.comunidad_id, c.nombre AS comunidad, i.id AS incidencia_id,
  i.elemento_normalizado, i.imputacion AS imputacion_sistema,
  i.imputacion_rival, i.confianza, i.umbral_aplicado, i.decidido_por,
  (i.decidido_por <> 'sistema') AS escalado,
  i.creado_en::date AS fecha
FROM incidencias i
JOIN comunidades c ON c.comunidad_id = i.comunidad_id
WHERE i.incidencia_padre_id IS NULL;
