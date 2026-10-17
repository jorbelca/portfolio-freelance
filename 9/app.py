#!/usr/bin/env python3
"""Ejecutor secuencial persistente y panel de la Demo 9. Solo destino de prueba."""
import csv
import http.client
import io
import ipaddress
import json
import math
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from comun import ErrorAPI, JSONHandler, ahora, conectar
from destino_demo import OPCIONES, FALLOS

BASE = Path(__file__).resolve().parent
DB = Path(os.environ.get("DEMO9_DB", "/data/ejecutor.sqlite3"))
PROXIES = ("proxy-a", "proxy-b", "proxy-c")
DESTINO = "http://destino:8090"
ACTIVOS = ("en curso", "pausada", "interrumpida")
# ponytail: un proceso y un trabajador; separar colas solo si se requiere concurrencia.
COND = threading.Condition(threading.RLock())


def guardar(run):
    with conectar(DB) as db:
        db.execute("INSERT INTO runs VALUES(?,?) ON CONFLICT(id) DO UPDATE SET documento=excluded.documento",
                   (run["id"], json.dumps(run, ensure_ascii=False)))
    COND.notify_all()


def leer(run_id=None):
    with conectar(DB) as db:
        row = db.execute("SELECT documento FROM runs WHERE id=?" if run_id else
                         "SELECT documento FROM runs ORDER BY rowid DESC LIMIT 1", (run_id,) if run_id else ()).fetchone()
    return json.loads(row[0]) if row else None


def evento(run, tipo, detalle, action=None):
    run["eventos"].append({"fecha": ahora(), "tipo": tipo, "detalle": detalle[:300],
                           "posicion": action["posicion"] if action else None})


def validar(data):
    if set(data) != {"opcion", "cantidad", "intervalo", "fallo", "accion_fallo"}:
        raise ErrorAPI(400, "Configuración incompleta o campos desconocidos")
    n, intervalo, pos = data["cantidad"], data["intervalo"], data["accion_fallo"]
    if (data["opcion"] not in OPCIONES or type(n) is not int or not 1 <= n <= 100 or
            type(intervalo) not in (int, float) or not math.isfinite(intervalo) or not 1 <= intervalo <= 60 or
            data["fallo"] not in FALLOS or type(pos) is not int or not 1 <= pos <= n):
        raise ErrorAPI(400, "Opción, volumen, intervalo o fallo inválido")
    return data.copy()


def rpc(proxy, method, path, data=None):
    connection = http.client.HTTPConnection(proxy, 3128, timeout=5)
    try:
        body = json.dumps(data) if data is not None else None
        connection.request(method, DESTINO + path, body, {"Content-Type": "application/json", "Cache-Control": "no-cache"})
        response = connection.getresponse()
        payload = response.read(2_000_001)
        if len(payload) > 2_000_000:
            raise ValueError("Respuesta demasiado grande")
        try:
            result = json.loads(payload)
        except (ValueError, UnicodeError):
            result = {"error": "Respuesta no JSON del proxy"}
        return response.status, result, response.getheader("Retry-After")
    finally:
        connection.close()


def disponibilidad():
    ips = {}
    try:
        for proxy in PROXIES:
            status, value, _ = rpc(proxy, "GET", "/health")
            if status != 200 or not isinstance(value, dict):
                raise ValueError("Destino no disponible")
            ips[proxy] = str(ipaddress.ip_address(value["ip_observada"]))
    except (OSError, http.client.HTTPException, ValueError, KeyError) as exc:
        raise ErrorAPI(503, "No se pudo verificar el destino a través de los tres proxies") from exc
    if len(set(ips.values())) != 3:
        raise ErrorAPI(503, "El destino no observa tres IP distintas")
    return ips


def voto_valido(value, run, action):
    if not isinstance(value, dict) or (value.get("action_id"), value.get("opcion"), value.get("fallo")) != (
            action["id"], run["config"]["opcion"], action["fallo"]):
        raise ValueError("Resultado incompatible con la acción")
    return str(ipaddress.ip_address(value["ip"]))


def espera_indicada(header):
    try:
        if header is not None and header.isascii() and header.isdigit():
            return int(header)
        fecha = parsedate_to_datetime(header)
        if fecha.tzinfo is None:
            return None
        return max(0, (fecha - datetime.now(timezone.utc)).total_seconds())
    except (ValueError, TypeError, OverflowError):
        return None


def crear(config):
    config = validar(config)
    with COND:
        actual = leer()
        if actual and actual["estado"] in ACTIVOS:
            raise ErrorAPI(409, "Ya hay una ejecución activa; continúa o cancela esa ejecución")
        ips = disponibilidad()
        run_id = uuid.uuid4().hex
        run = {"id": run_id, "config": config, "estado": "en curso", "creada": ahora(), "fin": None,
               "proxies": ips, "proximo_envio": 0, "eventos": [], "acciones": []}
        for pos in range(1, config["cantidad"] + 1):
            run["acciones"].append({"id": f"{run_id}:{pos}", "posicion": pos,
                "proxy": PROXIES[((pos - 1) // 5) % 3], "fallo": config["fallo"] if pos == config["accion_fallo"] else "ninguno",
                "estado": "pendiente", "ip": None, "intentos": [], "resultado": ""})
        evento(run, "inicio", "Plan guardado; tres IP internas verificadas")
        guardar(run)
        return run


def controlar(run_id, command):
    with COND:
        run = leer()
        if not run or run["id"] != run_id or run["estado"] not in ACTIVOS:
            raise ErrorAPI(409, "La ejecución ya no admite esa operación")
        if command == "pausar" and run["estado"] == "en curso":
            run["estado"] = "pausada"
        elif command == "continuar" and run["estado"] in ("pausada", "interrumpida"):
            run["proxies"] = disponibilidad()
            run["estado"] = "en curso"
        elif command == "cancelar":
            run["estado"], run["fin"] = "cancelada", ahora()
            for action in run["acciones"]:
                if action["estado"] == "pendiente":
                    action["estado"] = "cancelada"
        else:
            raise ErrorAPI(409, "Operación incompatible con el estado actual")
        evento(run, command, "El intento en curso conserva su resultado; no se iniciarán envíos mientras esté detenida")
        guardar(run)
        return run


def registrar_resultado(run_id, pos, estado, detalle, ip=None, status=None, incierta=False, esperar=0):
    with COND:
        run = leer(run_id)
        action = run["acciones"][pos - 1]
        action["estado"], action["resultado"] = estado, detalle
        if ip:
            action["ip"] = ip
        if action["intentos"] and action["intentos"][-1]["fin"] is None:
            action["intentos"][-1].update(fin=ahora(), status=status, resultado=detalle, ip=ip)
        run["proximo_envio"] = max(run["proximo_envio"], time.time() + esperar)
        if incierta and run["estado"] == "en curso":
            run["estado"] = "pausada"
        if run["estado"] == "cancelada" and estado == "pendiente":
            action["estado"] = "cancelada"
        evento(run, estado, detalle, action)
        guardar(run)


def reconciliar(run, action):
    try:
        status, value, _ = rpc(action["proxy"], "GET", "/votes/" + action["id"])
        if status == 200:
            ip = voto_valido(value, run, action)
            registrar_resultado(run["id"], action["posicion"], "confirmada", "Confirmada por reconciliación", ip, status)
            return
        if status == 404 and isinstance(value, dict) and value.get("error") == "No registrada":
            estado = "pendiente" if len(action["intentos"]) < 3 else "fallida"
            registrar_resultado(run["id"], action["posicion"], estado, "Destino confirma ausencia del registro", status=status)
            return
    except (OSError, http.client.HTTPException, ValueError, KeyError):
        pass
    registrar_resultado(run["id"], action["posicion"], "incierta", "No se pudo reconciliar; restaura el servicio y continúa", incierta=True)


def ejecutar(run, action):
    try:
        status, value, retry = rpc(action["proxy"], "POST", "/votes",
                                  {"action_id": action["id"], "opcion": run["config"]["opcion"], "fallo": action["fallo"]})
        if status in (200, 201):
            ip = voto_valido(value, run, action)
            registrar_resultado(run["id"], action["posicion"], "confirmada", "Participación registrada", ip, status)
            return
        if status in (401, 403):
            registrar_resultado(run["id"], action["posicion"], "incierta", "Acceso rechazado; revisión necesaria", status=status, incierta=True)
            return
        if status == 429:
            espera = espera_indicada(retry)
            if espera is None:
                registrar_resultado(run["id"], action["posicion"], "incierta", "Retry-After inválido; revisar antes de continuar", status=status, incierta=True)
                return
        elif status >= 500:
            # Un proxy puede generar 5xx después de que el destino haya aceptado el POST.
            registrar_resultado(run["id"], action["posicion"], "incierta", "Error temporal; comprobando el destino", status=status)
            reconciliar(run, action)
            return
        elif 400 <= status < 500:
            registrar_resultado(run["id"], action["posicion"], "fallida", f"Petición rechazada ({status})", status=status)
            return
        else:
            raise ValueError("Respuesta inesperada")
        estado = "pendiente" if len(action["intentos"]) < 3 else "fallida"
        registrar_resultado(run["id"], action["posicion"], estado, f"Límite temporal ({status})", status=status, esperar=espera)
    except (OSError, http.client.HTTPException, ValueError, KeyError):
        registrar_resultado(run["id"], action["posicion"], "incierta", "Respuesta perdida o inválida; comprobando el destino")
        reconciliar(run, action)


def trabajador():
    while True:
        with COND:
            run = leer()
            if not run or run["estado"] != "en curso":
                COND.wait(timeout=1)
                continue
            action = next((a for a in run["acciones"] if a["estado"] in ("pendiente", "incierta", "en curso")), None)
            if not action:
                run["estado"] = "completada" if all(a["estado"] == "confirmada" for a in run["acciones"]) else "completada con incidencias"
                run["fin"] = ahora()
                evento(run, "fin", run["estado"])
                guardar(run)
                continue
            consultar = action["estado"] in ("incierta", "en curso")
            if not consultar:
                if time.time() < run["proximo_envio"]:
                    COND.wait(timeout=min(1, run["proximo_envio"] - time.time()))
                    continue
                if len(action["intentos"]) >= 3:
                    action["estado"] = "fallida"
                    guardar(run)
                    continue
                action["estado"] = "en curso"
                action["intentos"].append({"numero": len(action["intentos"]) + 1, "inicio": ahora(), "fin": None,
                                           "proxy": action["proxy"], "status": None, "resultado": "", "ip": None})
                run["proximo_envio"] = time.time() + run["config"]["intervalo"]
                evento(run, "envio", f"Intento {len(action['intentos'])} por {action['proxy']}", action)
                guardar(run)
        try:
            reconciliar(run, action) if consultar else ejecutar(run, action)
        except Exception:
            # Un error inesperado detiene el proceso, nunca convierte un envío en éxito.
            with COND:
                run = leer(run["id"])
                run["estado"] = "interrumpida"
                run["acciones"][action["posicion"] - 1]["estado"] = "incierta"
                evento(run, "error", "Error interno del trabajador; revisar y reconciliar antes de continuar", action)
                guardar(run)


def iniciar():
    DB.parent.mkdir(parents=True, exist_ok=True)
    with conectar(DB) as db:
        db.execute("CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, documento TEXT NOT NULL)")
    with COND:
        run = leer()
        if run and run["estado"] in ACTIVOS:
            run["estado"] = "interrumpida"
            for action in run["acciones"]:
                if action["estado"] == "en curso":
                    action["estado"] = "incierta"
            evento(run, "reinicio", "Reinicio detectado; continúa explícitamente para reconciliar")
            guardar(run)
    threading.Thread(target=trabajador, daemon=True).start()


def informe(run):
    status, destino, _ = rpc(PROXIES[0], "GET", "/runs/" + run["id"])
    if status != 200 or not isinstance(destino, dict) or not isinstance(destino.get("votos"), list):
        raise ErrorAPI(503, "No se pudo contrastar el informe con el destino")
    confirmadas = {a["id"] for a in run["acciones"] if a["estado"] == "confirmada"}
    registrados = {v["action_id"] for v in destino["votos"]}
    return {"ejecucion": run, "destino": destino,
            "conciliacion": {"coinciden": confirmadas == registrados,
                             "solo_ejecutor": sorted(confirmadas - registrados), "solo_destino": sorted(registrados - confirmadas)}}


def csv_informe(report):
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(("accion", "posicion", "proxy", "estado", "ip_interna", "intentos", "resultado"))
    for action in report["ejecucion"]["acciones"]:
        row = (action["id"], action["posicion"], action["proxy"], action["estado"], action["ip"] or "",
               len(action["intentos"]), action["resultado"])
        writer.writerow("'" + v if isinstance(v, str) and v.lstrip().startswith(("=", "+", "-", "@")) else v for v in row)
    return out.getvalue().encode("utf-8-sig")


class Handler(JSONHandler):
    def ruta(self):
        path = urlsplit(self.path).path
        host = self.headers.get("Host", "")
        if host not in ("127.0.0.1:8089", "localhost:8089", "app:8089"):
            raise ErrorAPI(403, "Host no permitido")
        if self.command == "GET":
            if path == "/":
                self.enviar(200, (BASE / "interfaz.html").read_bytes(), "text/html; charset=utf-8")
            elif path == "/api/estado":
                with COND:
                    run = leer()
                self.enviar(200, {"ejecucion": run})
            elif path == "/health":
                self.enviar(200, {"status": "ok"})
            elif path in ("/api/informe.json", "/api/informe.csv"):
                with COND:
                    run = leer()
                if not run:
                    raise ErrorAPI(404, "No hay ejecución")
                try:
                    report = informe(run)
                except (OSError, http.client.HTTPException, ValueError, KeyError):
                    raise ErrorAPI(503, "Destino no disponible para contrastar el informe")
                if path.endswith("csv"):
                    self.enviar(200, csv_informe(report), "text/csv; charset=utf-8",
                                {"Content-Disposition": 'attachment; filename="demo9.csv"'})
                else:
                    self.enviar(200, report, headers={"Content-Disposition": 'attachment; filename="demo9.json"'})
            else:
                raise ErrorAPI(404, "Ruta desconocida")
            return
        origin = self.headers.get("Origin")
        if origin and origin != "http://" + host:
            raise ErrorAPI(403, "Origen no permitido")
        data = self.cuerpo()
        if path == "/api/iniciar":
            self.enviar(201, crear(data))
        elif path == "/api/control":
            if (set(data) != {"run_id", "accion"} or not isinstance(data["run_id"], str)
                    or data["accion"] not in ("pausar", "continuar", "cancelar")):
                raise ErrorAPI(400, "Se requieren run_id y accion")
            self.enviar(200, controlar(data["run_id"], data["accion"]))
        else:
            raise ErrorAPI(404, "Ruta desconocida")


if __name__ == "__main__":
    iniciar()
    print("Demo 9 en http://127.0.0.1:8089", flush=True)
    ThreadingHTTPServer(("0.0.0.0", 8089), Handler).serve_forever()
