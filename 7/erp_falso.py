#!/usr/bin/env python3
"""ERP falso para la Demo 7: sirve /v1/pedidos con la fealdad deliberada de una API
real de nicho -- paginación por cursor, fechas en dos formatos, nombres de campo
inconsistentes, rate limit con 429 real. Los datos salen de data/erp_pedidos.json
(generar antes con generar_datos.py).

Atado a 0.0.0.0 a propósito: lo lee la VM Windows (Power BI), no solo el Mac.

Uso: python3 erp_falso.py
"""
import json
import os
import time
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "data", "erp_pedidos.json")
API_KEY = os.environ.get("ERP_API_KEY", "demo-key-2026")
LIMITE_POR_MIN = 10

with open(DATA_FILE, encoding="utf-8") as f:
    PEDIDOS = json.load(f)

_peticiones = defaultdict(deque)  # api_key -> timestamps dentro de la ventana de 60s


def _rate_limited(api_key):
    ahora = time.time()
    ventana = _peticiones[api_key]
    while ventana and ahora - ventana[0] > 60:
        ventana.popleft()
    if len(ventana) >= LIMITE_POR_MIN:
        return True
    ventana.append(ahora)
    return False


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # silencia el log por defecto de http.server

    def _enviar(self, status, payload, headers=None):
        cuerpo = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path != "/v1/pedidos":
            self._enviar(404, {"error": "not_found"})
            return

        api_key = self.headers.get("X-API-Key", "")
        if api_key != API_KEY:
            self._enviar(401, {"error": "unauthorized"})
            return

        if _rate_limited(api_key):
            self._enviar(429, {"error": "rate_limited", "retry_after": 6}, headers={"Retry-After": "6"})
            return

        qs = parse_qs(parsed.query)
        limit = min(int(qs.get("limit", ["200"])[0]), 200)
        cursor = qs.get("cursor", [None])[0]
        offset = int(cursor) if cursor else 0

        pagina = PEDIDOS[offset:offset + limit]
        siguiente = offset + limit
        next_cursor = str(siguiente) if siguiente < len(PEDIDOS) else None

        self._enviar(200, {"items": pagina, "next_cursor": next_cursor})


def main():
    puerto = int(os.environ.get("ERP_PORT", "8070"))
    servidor = ThreadingHTTPServer(("0.0.0.0", puerto), Handler)
    print(f"ERP falso escuchando en 0.0.0.0:{puerto} ({len(PEDIDOS)} pedidos cargados)")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
