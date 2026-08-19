-- Expedientes ficticios que respaldan los correos `expediente_existente` y `plazo` de eval/dataset.jsonl.
-- Carga: docker compose exec -T postgres psql -U n8n_user -d n8n < seed-expedientes.sql

-- Reejecutable: borra solo las 8 direcciones sembradas aquí.
-- No toca las fichas que el propio workflow haya creado durante la demo.
DELETE FROM expedientes WHERE email_contacto IN (
  'carlos.ruiz@ejemplo.com',
  'ana.torres@ejemplo.com',
  'sonia.marquez@ejemplo.com',
  'javier.nogueira@ejemplo.com',
  'lucia.ferran@ejemplo.com',
  'ramon.alcaraz@ejemplo.com',
  'marta.iglesias@ejemplo.com',
  'nestor.villalba@ejemplo.com'
);

INSERT INTO expedientes (nombre_contacto, email_contacto, estado, urgente, notas, creado_en) VALUES

-- e02: pregunta de estado sobre la escritura.
('Carlos Ruiz Peña', 'carlos.ruiz@ejemplo.com', 'abierto', false,
 'Constitución de sociedad limitada. Estatutos revisados y aportaciones dinerarias acreditadas; escritura pendiente de firma ante notario. Falta la certificación negativa de denominación social.',
 '2026-05-18 09:40:00+02'),

-- e08: pregunta por el señalamiento. e25: reenvía un requerimiento de Hacienda (materia fuera de ámbito).
('Ana Torres Gil', 'ana.torres@ejemplo.com', 'abierto', false,
 'Reclamación de cantidad a proveedor por 14.200 EUR en facturas impagadas. Demanda presentada en junio de 2026, a la espera de señalamiento. Clienta que recomienda al despacho con frecuencia.',
 '2026-04-02 12:15:00+02'),

-- e04: plazo de contestación. e23: consulta de materia nueva sobre expediente vivo.
('Sonia Márquez Vidal', 'sonia.marquez@ejemplo.com', 'abierto', false,
 'Desahucio por impago de local comercial en Alicante. Contestación a la demanda en curso. Arrendataria con seis mensualidades pendientes; se explora acuerdo de pago aplazado antes de la vista.',
 '2026-07-21 17:05:00+02'),

-- e14: aporta documentación gráfica de la obra.
('Javier Nogueira Sanz', 'javier.nogueira@ejemplo.com', 'abierto', true,
 'Reclamación por vicios constructivos en reforma de vivienda unifamiliar. Pendiente de informe pericial de humedades; el perito ha pedido acceso al inmueble dos veces sin respuesta de la constructora.',
 '2026-02-27 10:30:00+02'),

-- e17: plazo enterrado en un correo cordial. e10: su hija escribe pidiendo información (tercero, R9).
('Lucía Ferrán Ortiz', 'lucia.ferran@ejemplo.com', 'en_espera', false,
 'División de cosa común sobre local heredado entre tres hermanos. Pendiente de designación judicial de perito tasador. Clienta de edad avanzada, delega parte de la comunicación en su familia.',
 '2026-01-14 11:00:00+01'),

-- e28: consulta sobre la cláusula de exclusividad. e27: es la contraparte del lead con conflicto (R7.4).
('Ramón Alcaraz Beltrán (Comercial Bellavista SL)', 'ramon.alcaraz@ejemplo.com', 'abierto', false,
 'Comercial Bellavista SL. Contrato de distribución en zona de levante: revisión de la cláusula de exclusividad y del régimen de preaviso. Dos distribuidores minoristas han planteado quejas por suministro.',
 '2026-06-09 08:50:00+02'),

-- e21: reactiva este expediente cerrado (misma materia). e16: escribe por materia nueva -> cliente_nuevo (R2.2).
('Marta Iglesias Cebrián', 'marta.iglesias@ejemplo.com', 'cerrado', false,
 'Reclamación de fianza de arrendamiento de vivienda. Cerrado en marzo de 2026 con acuerdo extrajudicial: devolución pactada en dos plazos, el segundo con vencimiento en julio de 2026.',
 '2025-11-06 16:20:00+01'),

-- e18: pregunta por la nota simple.
('Néstor Villalba Prat', 'nestor.villalba@ejemplo.com', 'abierto', false,
 'Compraventa de local comercial en Castellón. Pendiente de nota simple registral y de comprobación de cargas antes de firmar el contrato de arras.',
 '2026-07-30 13:45:00+02');
