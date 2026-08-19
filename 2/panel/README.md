# Panel (flujo B2)

**El fichero `.pbix` no está en este repositorio, y es deliberado.** Un `.pbix` es un binario opaco: no se revisa en un diff, no se prueba, y no demuestra nada que no demuestre mejor la consulta que lo alimenta. Lo que sí está versionado es la parte que se puede leer y romper: el modelo de datos (`panel.sql`) y las medidas. Reconstruir el libro desde aquí es media hora de trabajo mecánico.

## Montarlo

```bash
docker compose exec -T postgres psql -U n8n_user -d n8n < ../2/panel/panel.sql
```

(desde `1/`, donde está el compose; requiere `init-fincas-tables.sql` aplicado antes)

En Power BI Desktop: **Obtener datos → PostgreSQL**, servidor `localhost:5432`, base `n8n`. Importar **solo las vistas** `v_reparto_imputacion`, `v_proporcion_comun`, `v_gasto_proveedor`, `v_plazos_estado`, `v_incidencias_reincidentes`, `v_decisiones`. No importar las tablas: el modelo del panel no debe romperse cada vez que cambie una columna del triage.

Modo **Import** con refresco programado, no DirectQuery: el volumen es pequeño y el refresco programado es lo que hay que demostrar en el vídeo.

## Los cuatro paneles

| Panel | Vista | Qué enseña |
|---|---|---|
| Reparto común/privativo | `v_reparto_imputacion`, `v_proporcion_comun` | El argumento de la primera reunión |
| Gasto por proveedor y comunidad | `v_gasto_proveedor` | Concentración de proveedor |
| Plazos | `v_plazos_estado` | Vivos, por vencer, vencidos |
| Reincidencia | `v_incidencias_reincidentes` | La señal que precede a una derrama |

## Medidas DAX

```dax
Gasto total = SUM ( v_reparto_imputacion[importe] )

Gasto comun =
CALCULATE ( [Gasto total], v_reparto_imputacion[imputado_a] = "comun" )

% imputado a comun =
DIVIDE ( [Gasto comun], [Gasto total] )

-- El mes anterior dentro de la misma comunidad. Sin una tabla de calendario marcada como
-- tabla de fechas, DATEADD no funciona: crear una y relacionarla con [mes].
Gasto total mes anterior =
CALCULATE ( [Gasto total], DATEADD ( Calendario[Fecha], -1, MONTH ) )

Variacion mensual =
VAR Previo = [Gasto total mes anterior]
RETURN DIVIDE ( [Gasto total] - Previo, Previo )

Plazos vencidos = CALCULATE ( COUNTROWS ( v_plazos_estado ), v_plazos_estado[estado] = "vencido" )
Plazos por vencer = CALCULATE ( COUNTROWS ( v_plazos_estado ), v_plazos_estado[estado] = "por_vencer" )

-- Cuántas decisiones no las tomó el sistema solo. Es la medida que justifica el mantenimiento
-- mensual: sin ella, "reviso la cola de casos dudosos" no se puede demostrar con un número.
-- v_decisiones contiene TODAS las incidencias, no solo las escaladas: sin el denominador
-- completo esta división daría siempre 1.
Escalados = CALCULATE ( COUNTROWS ( v_decisiones ), v_decisiones[escalado] = TRUE )

Tasa de escalado = DIVIDE ( [Escalados], COUNTROWS ( v_decisiones ) )
```

`% imputado a comun` da 80,0 % en CDP-003 frente a 55,0 % y 45,0 % en las otras dos fincas. **Y la desviación no es un número decorativo**: tres de esos gastos son carpintería exterior cargada al fondo común, cuando el artículo 4º de los propios estatutos de CDP-003 la atribuye a cada propietario. El panel señala la anomalía; el chat documental de la Demo B la fundamenta con la cláusula. El argumento de venta no es el gráfico, es la cláusula debajo del gráfico.

## Límites

- Los importes de `gastos` son **contabilidad sintética de un trimestre**, elegidos para que el reparto salga en 80/55/45. Con datos reales la desviación puede tener explicación legítima —una finca antigua gasta más en elementos comunes— y el panel no distingue "mal imputado" de "estructuralmente caro". Esa distinción es del administrador; la vista solo la hace visible.
- `v_plazos_estado` y `v_incidencias_reincidentes` salen vacías hasta que se procesen incidencias: dependen del triage, no del seed.
- El umbral de `por_vencer` está fijado en 2 días a ojo. Con volumen real se calibra.
