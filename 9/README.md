# Demo 9 — Ejecutor secuencial con rotación de proxies

Aplicación local para ejecutar una secuencia finita de acciones contra una API ficticia, repartirlas entre tres proxies HTTP y conservar un registro verificable de cada intento. El destino, los datos y los fallos de prueba son sintéticos; no se conecta a votaciones ni a otros servicios externos.

## Demostración en vídeo

[![Demo 9: ejecutor con proxies, rotación y reintentos](https://img.youtube.com/vi/WdHE3htCdUU/hqdefault.jpg)](https://www.youtube.com/watch?v=WdHE3htCdUU)

## Funcionalidad

- Configura y ejecuta entre 1 y 100 acciones secuenciales con un intervalo mínimo de un segundo.
- Asigna un proxy por bloques de cinco acciones y conserva esa asignación durante los reintentos.
- Permite pausar, continuar y cancelar una ejecución; las acciones confirmadas se conservan.
- Reintenta errores transitorios hasta tres intentos por acción y reconcilia el resultado por `action_id` antes de reenviar una solicitud incierta.
- Registra por separado ejecuciones, acciones, intentos, eventos y solicitudes aceptadas por el destino.
- Expone actividad, rutas observadas y exportación JSON/CSV desde el panel local.

## Arquitectura

```text
Navegador → app → proxy-a / proxy-b / proxy-c → destino sintético
              │                                  │
              └─ SQLite de ejecución              └─ registro de solicitudes
```

Docker Compose levanta cinco servicios: `app`, `destino` y tres proxies Squid. El panel se publica únicamente en `127.0.0.1:8089`; el destino no publica puertos en el host. Las redes internas limitan el tráfico de los proxies al destino de prueba.

La app usa Python y SQLite; el panel está implementado con HTML, CSS y JavaScript nativos. Los volúmenes de SQLite conservan el estado al recrear contenedores. `action_id` es único en el destino: repetir una acción con el mismo contenido devuelve el registro existente; cambiar su contenido produce un conflicto.

## Regla de asignación de rutas

Una acción es una unidad lógica planificada, identificada por su posición. Los reintentos no ocupan otra posición:

```text
índice_de_ruta = ((posición_de_acción - 1) // 5) % número_de_rutas
```

| Posiciones | Ruta |
|---|---|
| 1–5 | `proxy-a` |
| 6–10 | `proxy-b` |
| 11–15 | `proxy-c` |
| 16–20 | `proxy-a` |

La IP que muestra el destino es la IP interna del contenedor que abrió la conexión TCP. No representa una IP pública distinta: los contenedores pueden compartir la misma salida a Internet. El cliente se conecta explícitamente al proxy asignado y el destino no usa cabeceras reenviadas como prueba de origen.

## Estados y errores

| Evento | Comportamiento |
|---|---|
| Respuesta aceptada | La acción pasa a confirmada y se registra en el destino |
| Error temporal | Se reintenta por la misma ruta, hasta tres intentos totales |
| Timeout o respuesta perdida | Se consulta el destino por `action_id` antes de reenviar |
| Destino inaccesible durante la conciliación | La acción queda incierta y la ejecución se pausa |
| Pausa | No empieza otro envío tras resolver el intento en curso |
| Cancelación | No se envían acciones nuevas; se preservan las confirmadas |
| Reinicio de la app | La ejecución activa requiere reconciliación antes de continuar |

## Ejecutar localmente

Requisitos: Docker Engine y Docker Compose v2.

Desde `9/`:

```bash
docker compose up -d --build --wait
```

Abre el [panel local](http://127.0.0.1:8089). Para ejecutar la comprobación de aceptación:

```bash
python3 verificar.py
```

El verificador necesita los servicios Compose y no debe coincidir con una ejecución manual activa. Comprueba el backend y puede detener o recrear servicios para probar recuperación; conserva los volúmenes de datos.

Para inspeccionar registros o detener los contenedores conservando los datos:

```bash
docker compose logs --tail 50 app destino proxy-a proxy-b proxy-c
docker compose down
```

`docker compose down -v` también elimina los datos persistidos y reinicia el estado de la demo.

## Estructura

- `compose.yaml`, `Dockerfile`, `proxy.conf`: servicios, imagen y configuración de Squid.
- `app.py`, `comun.py`: API de control, trabajador secuencial, persistencia y comunicación HTTP.
- `destino_demo.py`: API sintética, deduplicación y fallos de prueba.
- `interfaz.html`: panel local y exportaciones.
- `verificar.py`: comprobación de aceptación del backend.
- `verificar_ui.mjs`: comprobación de la interfaz en el navegador de Codex.

## Límites

La verificación demuestra rotación entre direcciones internas de Docker y manejo de estados contra un destino local controlado. No prueba proxies públicos, rotación de IP pública, automatización de plataformas de terceros ni ejecución exactamente una vez en servicios que no implementen deduplicación y consulta de estado.
