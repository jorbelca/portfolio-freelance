-- Datos sintéticos de las 3 fincas de la Demo B. comunidad_id y nombre están fijados (el otro
-- agente escribe los estatutos correspondientes en 2/comunidades/) y no se tocan aquí.
-- Reejecutable: ON CONFLICT DO NOTHING sobre las PK/UNIQUE de cada tabla.

-- Direcciones y censos copiados de las escrituras de 2/comunidades/, que son el corpus que
-- indexa el RAG: si estas cifras y aquel texto discrepan, el sistema cita un documento que
-- contradice su propia base de datos, y el fallo sale en la demo. Manda la escritura.
--   CDP-001: 24 viviendas + 2 locales = 26 elementos privativos.
--   CDP-002:  5 plantas x 2 viviendas + 1 local = 11.
--   CDP-003: 21 viviendas + 1 local = 22 (más 20 plazas y 20 trasteros como anejos, que no
--            son elementos privativos independientes y por eso no suman al censo).
INSERT INTO comunidades (comunidad_id, nombre, direccion, num_propietarios, presupuesto_ordinario_anual) VALUES
  ('CDP-001', 'Residencial Los Almendros', 'Avenida de los Almendros 12, Villalmendro de la Vega (ficticia)', 26, 48000.00),
  ('CDP-002', 'Comunidad Plaza Mayor 7',   'Plaza Mayor 7, Villalmendro de la Vega (ficticia)',               11, 21500.00),
  ('CDP-003', 'Edificio Miramar',          'Paseo Marítimo Ficticio 24, Puerto Ejemplo de la Costa',          22, 36750.00)
ON CONFLICT (comunidad_id) DO NOTHING;

-- num_propietarios de arriba es el censo total de cada finca (para cálculos de mayoría/quorum);
-- aquí solo se siembra un puñado representativo por comunidad, no el censo completo, que es
-- cuanto necesita la demo para probar triage y deduplicación entre vecinos distintos.
INSERT INTO propietarios (comunidad_id, nombre, email, piso, puerta) VALUES
  ('CDP-001', 'Marta Fernández Ruiz',   'marta.fernandez@ejemplo.com',   '1', 'A'),
  ('CDP-001', 'Carlos Gómez Lara',      'carlos.gomez@ejemplo.com',      '2', 'B'),
  ('CDP-001', 'Elena Torres Pardo',     'elena.torres@ejemplo.com',      '3', 'A'),
  ('CDP-001', 'David Muñoz Iglesias',   'david.munoz@ejemplo.com',       '4', 'C'),
  ('CDP-002', 'Sofía Navarro Peña',     'sofia.navarro@ejemplo.com',     '1', 'Izq'),
  ('CDP-002', 'Javier Ortega Campos',   'javier.ortega@ejemplo.com',     '2', 'Der'),
  ('CDP-002', 'Lucía Ramos Vidal',      'lucia.ramos@ejemplo.com',       '3', 'Izq'),
  ('CDP-003', 'Pablo Serrano Castro',   'pablo.serrano@ejemplo.com',     '1', '1'),
  ('CDP-003', 'Ana Delgado Vega',       'ana.delgado@ejemplo.com',       '2', '2'),
  ('CDP-003', 'Rubén Molina Sáez',      'ruben.molina@ejemplo.com',      '3', '3'),
  ('CDP-003', 'Cristina Bravo Herrero', 'cristina.bravo@ejemplo.com',    '4', '4')
ON CONFLICT (comunidad_id, email) DO NOTHING;

-- Resto del censo, derivado de eval/dataset.jsonl. No es relleno: la comunidad de una
-- incidencia se resuelve por el email del remitente contra esta tabla, asi que un remitente
-- del corpus que no figure aqui nunca llega al clasificador (cae a la compuerta de
-- 'remitente no identificado') y el arnes lo cuenta como fallo de imputacion. Los tres
-- remitentes de i40/i41/i42 quedan fuera A PROPOSITO: son los que prueban esa compuerta.
INSERT INTO propietarios (comunidad_id, nombre, email, piso, puerta) VALUES
  ('CDP-001', 'Antonio Vidal', 'antonio.vidal@ejemplo.com', '5', 'A'),  -- i43
  ('CDP-001', 'Beatriz Rey', 'beatriz.rey@ejemplo.com', '6', 'A'),  -- i11
  ('CDP-001', 'Ines Campos', 'ines.campos@ejemplo.com', '7', 'A'),  -- i35
  ('CDP-001', 'Jorge Ibanez', 'jorge.ibanez@ejemplo.com', '8', 'A'),  -- i29
  ('CDP-001', 'Julia Serrano', 'julia.serrano@ejemplo.com', '9', 'A'),  -- i01
  ('CDP-001', 'Lorena Aguilar', 'lorena.aguilar@ejemplo.com', '10', 'A'),  -- i28
  ('CDP-001', 'Pedro Villalba', 'pedro.villalba@ejemplo.com', '11', 'A'),  -- i05
  ('CDP-001', 'Sara Blanco', 'sara.blanco@ejemplo.com', '12', 'A'),  -- i07
  ('CDP-002', 'Angel Castro', 'angel.castro@ejemplo.com', '4', 'A'),  -- i03, i30
  ('CDP-002', 'Fernando Gil', 'fernando.gil@ejemplo.com', '5', 'A'),  -- i04
  ('CDP-002', 'Marisol Herrera', 'marisol.herrera@ejemplo.com', '6', 'A'),  -- i02
  ('CDP-002', 'Oscar Redondo', 'oscar.redondo@ejemplo.com', '7', 'A'),  -- i18
  ('CDP-002', 'Teresa Molina', 'teresa.molina@ejemplo.com', '8', 'A'),  -- i06, i39
  ('CDP-003', 'Alberto Ferrer', 'alberto.ferrer@ejemplo.com', '5', 'A'),  -- i10, i23
  ('CDP-003', 'Manuel Ortiz', 'manuel.ortiz@ejemplo.com', '6', 'A'),  -- i16, i34
  ('CDP-003', 'Nuria Campos', 'nuria.campos@ejemplo.com', '7', 'A'),  -- i19
  ('CDP-003', 'Rocio Marquez', 'rocio.marquez@ejemplo.com', '8', 'A')   -- i12, i31
ON CONFLICT (comunidad_id, email) DO NOTHING;
