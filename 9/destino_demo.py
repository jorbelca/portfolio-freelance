#!/usr/bin/env python3
"""Votación sintética: deduplicación atómica, IP TCP y fallos reproducibles."""
import os
import re
import socket
import time
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from comun import ErrorAPI, JSONHandler, ahora, conectar

DB = Path(os.environ.get("DEMO9_DESTINO_DB", "/data/destino.sqlite3"))
OPCIONES = ("parque", "biblioteca", "carril-bici")
FALLOS = ("ninguno", "temporal", "persistente", "respuesta_perdida", "limite",
          "limite_invalido", "rechazo", "validacion", "lenta", "incierta")
ID = re.compile(r"[0-9a-f]{32}:[1-9][0-9]{0,2}\Z")


def iniciar():
    DB.parent.mkdir(parents=True, exist_ok=True)
    with conectar(DB) as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS votos (
          action_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, opcion TEXT NOT NULL,
          fecha TEXT NOT NULL, ip TEXT NOT NULL, fallo TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS solicitudes (
          id INTEGER PRIMARY KEY, action_id TEXT, metodo TEXT, fecha TEXT,
          ip TEXT, status INTEGER, detalle TEXT);
        """)


class Handler(JSONHandler):
    def registrar(self, db, action_id, status, detalle=""):
        db.execute("INSERT INTO solicitudes(action_id,metodo,fecha,ip,status,detalle) VALUES(?,?,?,?,?,?)",
                   (action_id, self.command, ahora(), self.client_address[0], status, detalle))

    def cortar(self):
        self.close_connection = True
        self.connection.shutdown(socket.SHUT_RDWR)
        self.connection.close()

    def ruta(self):
        path = urlsplit(self.path).path
        ip = self.client_address[0]
        if self.command == "GET" and path == "/health":
            self.enviar(200, {"status": "ok", "ip_observada": ip})
            return
        if self.command == "GET" and path.startswith("/runs/"):
            run_id = path.removeprefix("/runs/")
            if not re.fullmatch(r"[0-9a-f]{32}", run_id):
                raise ErrorAPI(400, "ID de ejecución inválido")
            with conectar(DB) as db:
                votos = [dict(r) for r in db.execute("SELECT * FROM votos WHERE run_id=? ORDER BY action_id", (run_id,))]
                solicitudes = [dict(r) for r in db.execute(
                    "SELECT * FROM solicitudes WHERE substr(action_id,1,32)=? ORDER BY id", (run_id,))]
            self.enviar(200, {"votos": votos, "solicitudes": solicitudes})
            return
        if self.command == "GET" and path.startswith("/votes/"):
            action_id = path.removeprefix("/votes/")
            if not ID.fullmatch(action_id):
                raise ErrorAPI(400, "ID de acción inválido")
            with conectar(DB) as db:
                voto = db.execute("SELECT * FROM votos WHERE action_id=?", (action_id,)).fetchone()
                # Fallo deliberado: primera consulta tras una respuesta perdida también se pierde.
                previas = db.execute("SELECT count(*) FROM solicitudes WHERE action_id=? AND metodo='GET'", (action_id,)).fetchone()[0]
                cortar = voto and voto["fallo"] == "incierta" and previas == 0
                self.registrar(db, action_id, 200 if voto else 404, "respuesta cortada" if cortar else "consulta")
            if cortar:
                self.cortar()
            else:
                self.enviar(200 if voto else 404, dict(voto) if voto else {"error": "No registrada"})
            return
        if self.command != "POST" or path != "/votes":
            raise ErrorAPI(404, "Ruta desconocida")
        data = self.cuerpo()
        if set(data) != {"action_id", "opcion", "fallo"}:
            raise ErrorAPI(400, "Campos de participación inválidos")
        action_id, opcion, fallo = data["action_id"], data["opcion"], data["fallo"]
        if not isinstance(action_id, str) or not ID.fullmatch(action_id) or opcion not in OPCIONES or fallo not in FALLOS:
            raise ErrorAPI(400, "Participación inválida")
        if int(action_id.split(":")[1]) > 100:
            raise ErrorAPI(400, "Acción fuera del límite de la demo")
        with conectar(DB) as db:
            # Reserva SQLite antes de leer: dos POST simultáneos no pueden insertar el mismo voto.
            db.execute("BEGIN IMMEDIATE")
            existente = db.execute("SELECT * FROM votos WHERE action_id=?", (action_id,)).fetchone()
            intentos = db.execute("SELECT count(*) FROM solicitudes WHERE action_id=? AND metodo='POST'", (action_id,)).fetchone()[0]
            status, detalle = 201, "aceptada"
            if existente:
                status = 200 if existente["opcion"] == opcion and existente["fallo"] == fallo else 409
                detalle = "deduplicada" if status == 200 else "contenido distinto"
            elif fallo == "persistente" or (fallo == "temporal" and intentos == 0):
                status, detalle = 503, "fallo temporal"
            elif fallo in ("limite", "limite_invalido") and intentos == 0:
                status, detalle = 429, "límite de prueba"
            elif fallo in ("rechazo", "validacion"):
                status, detalle = (403 if fallo == "rechazo" else 422), "rechazo de prueba"
            if status == 201:
                db.execute("INSERT INTO votos VALUES(?,?,?,?,?,?)",
                           (action_id, action_id.split(":")[0], opcion, ahora(), ip, fallo))
            self.registrar(db, action_id, status, detalle)
            voto = db.execute("SELECT * FROM votos WHERE action_id=?", (action_id,)).fetchone()
        if fallo == "lenta" and status == 201:
            time.sleep(3)
        if fallo in ("respuesta_perdida", "incierta") and status == 201:
            self.cortar()
            return
        headers = {"Retry-After": "2" if fallo == "limite" else "inválido"} if status == 429 else None
        self.enviar(status, dict(voto) if status in (200, 201) else {"error": detalle}, headers=headers)


if __name__ == "__main__":
    iniciar()
    print("Destino sintético en :8090", flush=True)
    ThreadingHTTPServer(("0.0.0.0", 8090), Handler).serve_forever()
