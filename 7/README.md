# Demo 7 — Reporting periódico con conciliación entre fuentes (Power BI)

**Finalizada — 2026-09-24.**

Automatiza el informe semanal que hoy se monta a mano (exportar, pegar en Excel, cuadrar) y
añade algo que la mayoría de dashboards no hace: **detectar cuándo los números de dos fuentes
no coinciden**, y decir en qué fila exactamente.

**El cálculo y la conciliación salen de SQL determinista, nunca del modelo.** El LLM es
opcional y está apagado por defecto; si se activa, solo redacta el párrafo de resumen del
correo sobre cifras ya calculadas — nunca decide un número ni explica un descuadre.

## Qué hace

1. **Ingesta** desde tres fuentes que no encajan entre sí: una API propia con paginación por
   cursor y rate limit, una hoja de cálculo del equipo comercial, y la base de facturación.
2. **Conciliación** — reglas fijas que comparan las tres fuentes y marcan discrepancias
   (pedido sin facturar, factura sin pedido, importe distinto, duplicado...), distinguiendo un
   descuadre real de un desfase contable normal que no debe alarmar a nadie.
3. **Panel en Power BI** sobre los datos ya cuadrados, con detalle ("drillthrough") desde
   cualquier cifra hasta la fila que la origina.
4. **Correo del lunes** con el resumen y las alertas, sin que nadie tenga que abrir el panel.

## Arquitectura

```
fuente A (API propia)   ─┐
fuente B (hoja/CSV)     ─┤→ ingesta ─→ staging ─→ conciliación (SQL) ─→ Power BI
fuente C (facturación)  ─┘                              │
                                                          └─→ correo del lunes
```

## Estado

Demo finalizada. Ingesta y conciliación funcionan de extremo a extremo contra datos
sintéticos (35/35 descuadres detectados, 0 falsos positivos en los casos de desfase legítimo).

## Ejecutar

```bash
docker compose -f ../1/docker-compose.yml up -d   # Postgres + GreenMail
python3 generar_datos.py                          # datos sintéticos + ground truth (determinista)
python3 erp_falso.py &                             # API falsa en :8070
python3 ingesta.py                                 # ERP + comercial.csv + facturación -> bi_staging
python3 conciliar.py --verificar                   # reglas C1-C5 -> bi_staging.descuadres
python3 informe.py                                  # correo del lunes por GreenMail (ver :8081)
```

## Notas

- Datos sintéticos, generados con semilla fija — sirven para probar la ingesta y la
  conciliación, no como evidencia de demanda de mercado.
- Credenciales reales y notas privadas de planificación quedan fuera del repositorio.
