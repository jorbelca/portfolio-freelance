"""HTTP JSON y SQLite compartidos por los dos servicios locales."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler


def ahora():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


@contextmanager
def conectar(path):
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    try:
        with db:
            yield db
    finally:
        db.close()


class ErrorAPI(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


class JSONHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def enviar(self, status, value, tipo="application/json; charset=utf-8", headers=None):
        body = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for key, val in (headers or {}).items():
            self.send_header(key, val)
        self.end_headers()
        self.wfile.write(body)

    def cuerpo(self):
        if self.headers.get("Transfer-Encoding"):
            raise ErrorAPI(400, "Transfer-Encoding no admitido")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise ErrorAPI(400, "Longitud inválida")
        if not 0 < length <= 8192:
            raise ErrorAPI(400, "Se requiere un JSON de hasta 8 KB")
        if self.headers.get_content_type() != "application/json":
            raise ErrorAPI(415, "Se requiere application/json")
        try:
            value = json.loads(self.rfile.read(length))
        except (ValueError, UnicodeError, RecursionError):
            raise ErrorAPI(400, "JSON inválido")
        if not isinstance(value, dict):
            raise ErrorAPI(400, "Se requiere un objeto JSON")
        return value

    def manejar(self):
        self.connection.settimeout(10)
        try:
            self.ruta()
        except ErrorAPI as error:
            self.enviar(error.status, {"error": error.message})
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass
        except (sqlite3.Error, OSError):
            self.enviar(500, {"error": "No se pudo completar la operación"})

    do_GET = manejar
    do_POST = manejar
