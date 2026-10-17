# Demo 8 — Configurador de audio

Prototipo local que convierte una necesidad de grabación en conjuntos de audio compatibles. Tiene en cuenta el dispositivo que ya usa la persona, cuántos participantes habrá, el presupuesto y las preferencias indicadas.

La aplicación propone conjuntos completos, explica qué piezas se conectan, calcula el coste y señala los datos que no están verificados. Si cambian las condiciones, vuelve a comprobar la selección y conserva las piezas que siguen siendo válidas.

## Demostración en vídeo

[![Configurador de audio con interpretación contextual](https://img.youtube.com/vi/bOzBnumUCyM/hqdefault.jpg)](https://www.youtube.com/watch?v=bOzBnumUCyM)

## Índice

- [Cómo funciona](#cómo-funciona)
- [Ejecutar](#ejecutar)
- [Evaluación y límites](#evaluación-y-límites)
- [Código](#código)

## Cómo funciona

- El catálogo normalizado y las reglas describen productos, dispositivos, compatibilidades y accesorios.
- El motor genera combinaciones y aplica las restricciones técnicas y de presupuesto.
- CLM puede sugerir el uso y las preferencias a partir del texto, y puntuar las opciones viables. Las sugerencias requieren confirmación; la compatibilidad la determinan las reglas, no el modelo.
- La interfaz web consume una API local. Las sesiones y las instantáneas de catálogo se guardan en SQLite.

## Ejecutar

Requiere Python 3. Desde la raíz del repositorio:

    cd 8
    python3 verificar.py
    python3 app.py

Abre http://127.0.0.1:8088. La aplicación básica funciona sin CLM: muestra los conjuntos que cumplen las reglas y los ordena por coste. Para activar la interpretación y puntuación contextual hay que iniciar también CLM y su encoder local; la integración usa servicios en loopback.

## Evaluación y límites

La evaluación final contiene 40 escenarios: no se observaron violaciones de restricciones obligatorias y hubo una opción aceptable entre las tres primeras en 23 de los 23 casos puntuables. La evaluación de interpretación libre es pequeña y obtuvo 2/4 para el uso y 2/4 para las preferencias; por eso, esas sugerencias no se aplican sin confirmación humana.

El catálogo tiene 40 referencias sintéticas. Precios, disponibilidad y compatibilidades son datos de demostración; las ilustraciones de los kits son conceptuales. Los adaptadores JSON y HTTP son ejemplos, no conectores a tiendas reales. CLM se ejecuta localmente con un encoder Qwen3 cuantizado a 4 bits; su paridad con el modelo original no se ha medido.

## Código

- app.py: servidor HTTP, API y sesiones.
- interfaz.html: interfaz web.
- configurador.py: reglas, combinaciones y reconfiguración.
- catalogo.py y adaptadores.py: validación e importación del catálogo.
- modelo.py: integración con CLM.
- datos/ y dominio/: catálogo y reglas de la categoría de audio.

CLM: [repositorio](https://github.com/Contrastive-LM/CLM) · [checkpoint](https://huggingface.co/Contrastive-LM/CLM-v0.1-8B).
