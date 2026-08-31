#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Servidor estático del tablero + un par de endpoints no-estáticos -- http.server normal no
puede ejecutar SQL, de ahí este archivo en vez de `python3 -m http.server`:
  POST /reset          -- botón "Limpiar BBD" (TRUNCATE)
  GET  /api/tabla?tabla=facturas|cola_revision|extraccion_log -- botón "Inspeccionar BBD"
Todo lo demás (GET de tablero.html, facturas_pdf/*) se sirve igual que antes, vía
SimpleHTTPRequestHandler sin tocar."""
import functools
import http.server
import json
import os
import socketserver
from urllib.parse import parse_qs, urlsplit

import psycopg2

# Whitelist explícita, no interpolación de lo que mande el cliente -- nombre de tabla nunca
# debe montarse con f-string a partir de input externo (inyección SQL trivial si no).
TABLAS_PERMITIDAS = {
    "facturas": "id",
    "cola_revision": "id",
    "extraccion_log": "id",
}


def dsn():
    return (f"host={os.environ.get('PGHOST', '127.0.0.1')} port={os.environ.get('PGPORT', '5432')} "
            f"dbname={os.environ.get('PGDATABASE', 'n8n')} user={os.environ.get('PGUSER', 'n8n_user')} "
            f"password={os.environ.get('PGPASSWORD', '')}")


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if urlsplit(self.path).path != "/api/tabla":
            return super().do_GET()
        qs = parse_qs(urlsplit(self.path).query)
        tabla = (qs.get("tabla") or [""])[0]
        if tabla not in TABLAS_PERMITIDAS:
            self._json(400, {"ok": False, "error": f"tabla no permitida: {tabla!r}"})
            return
        orden = TABLAS_PERMITIDAS[tabla]
        try:
            conn = psycopg2.connect(dsn())
            cur = conn.cursor()
            # nombre de tabla ya validado contra la whitelist arriba, no viene del cliente tal cual
            cur.execute(f"SELECT * FROM {tabla} ORDER BY {orden} DESC LIMIT 50")
            columnas = [c.name for c in cur.description]
            filas = [[str(v) if v is not None else None for v in fila] for fila in cur.fetchall()]
            conn.close()
            self._json(200, {"ok": True, "columnas": columnas, "filas": filas})
        except Exception as e:
            self._json(500, {"ok": False, "error": str(e)})

    def do_POST(self):
        if self.path != "/reset":
            self.send_error(404)
            return
        try:
            conn = psycopg2.connect(dsn())
            conn.autocommit = True
            conn.cursor().execute(
                "TRUNCATE TABLE facturas, cola_revision, extraccion_log RESTART IDENTITY;")
            conn.close()
            self._json(200, {"ok": True})
        except Exception as e:
            self._json(500, {"ok": False, "error": str(e)})

    def _json(self, status, body):
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()


if __name__ == "__main__":
    HandlerConDir = functools.partial(Handler, directory="/ui")
    with socketserver.TCPServer(("0.0.0.0", 8090), HandlerConDir) as httpd:
        httpd.serve_forever()
