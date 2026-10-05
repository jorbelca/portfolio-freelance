#!/usr/bin/env python3
"""API local de sesiones y catálogo para la Demo 8 (solo loopback)."""
import copy
import json
import os
import re
import sqlite3
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from adaptadores import desde_http, desde_json, pagina_http_demo
from catalogo import CatalogError, CatalogStore
from configurador import ConfigError, PREFERENCIAS, USOS, recomendar, validar_catalogo_audio, validar_estado
from modelo import CLMError, CLMLocal


BASE = Path(__file__).resolve().parent
CATALOGO_JSON = BASE / "datos" / "catalogo.json"
DOMINIO_JSON = BASE / "dominio" / "audio.json"
DB_PATH = Path(os.environ.get("DEMO8_DB", BASE / "state.sqlite3"))
PORT = int(os.environ.get("DEMO8_PORT", "8088"))
HOST = os.environ.get("DEMO8_HOST", "127.0.0.1")
HTML = BASE / "interfaz.html"
VISUALS = {
    "/assets/kit-usbc-basic.png": BASE / "assets" / "kit-usbc-basic.png",
    "/assets/kit-usbc-case.png": BASE / "assets" / "kit-usbc-case.png",
    "/assets/kit-trs-stand.png": BASE / "assets" / "kit-trs-stand.png",
}


class APIError(Exception):
    def __init__(self, status, code, message):
        self.status, self.code, self.message = status, code, message


def _json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


DOMINIO = _json(DOMINIO_JSON)
STORE = CatalogStore(DB_PATH)
if STORE.actual() is None:
    initial_catalog = desde_json(CATALOGO_JSON)
    validar_catalogo_audio(initial_catalog)
    STORE.importar(initial_catalog, "json")


def _ahora():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _recomendar(state, catalog):
    try:
        result = recomendar(state, catalog, DOMINIO)
        primary = result.get("recomendaciones", [])
        state["productos_previos"] = [item["id"] for item in primary[0]["productos"]] if primary else []
        return result
    except ConfigError as e:
        raise APIError(400, "invalid_state", str(e)) from e


def _public_session(session):
    return {
        "id": session["id"], "version_estado": session["version"],
        "estado_confirmado": session["estado"], "catalogo": {
            "tienda_id": session["estado"].get("tienda_id"),
            "version": session["resultado"]["version_catalogo"],
            "snapshot_id": session["snapshot_id"],
        },
        "recomendacion": session["resultado"],
        "creada_el": session["creada_el"], "actualizada_el": session["actualizada_el"],
    }


def _refrescar_sesion(session):
    current = STORE.actual()
    if current is None or session["snapshot_id"] == current["snapshot_id"]:
        return session
    result = _recomendar(session["estado"], current)
    updated = STORE.actualizar_sesion(session["version"], session["id"], session["estado"], result,
                                      current["snapshot_id"], _ahora())
    if updated is None:
        raise APIError(409, "state_conflict", "La sesión cambió durante la actualización del catálogo; vuelve a leerla.")
    return updated


def _respond(handler, status, payload, content_type="application/json; charset=utf-8"):
    body = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


def _request_json(handler):
    try:
        length = int(handler.headers.get("Content-Length", "0"))
    except ValueError as e:
        raise APIError(400, "invalid_length", "Content-Length inválido") from e
    if length <= 0 or length > 1_000_000:
        raise APIError(413 if length > 1_000_000 else 400, "invalid_body_size", "El cuerpo JSON debe tener hasta 1 MB")
    try:
        data = json.loads(handler.rfile.read(length))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise APIError(400, "invalid_json", "El cuerpo debe ser JSON válido") from e
    if not isinstance(data, dict):
        raise APIError(400, "invalid_json", "El cuerpo debe ser un objeto JSON")
    return data


def _source_page(cursor):
    try:
        return pagina_http_demo(_json(CATALOGO_JSON), cursor, 8)
    except CatalogError as e:
        raise APIError(400, "invalid_cursor", "cursor inválido") from e


class Handler(BaseHTTPRequestHandler):
    def log_message(self, _format, *_args):
        pass

    def _route(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        if path == "/" and self.command == "GET":
            _respond(self, 200, HTML.read_bytes(), "text/html; charset=utf-8")
            return
        if path in VISUALS and self.command == "GET":
            _respond(self, 200, VISUALS[path].read_bytes(), "image/png")
            return
        if path == "/health" and self.command == "GET":
            snapshot = STORE.actual()
            try:
                clm_available = CLMLocal().disponible()
            except ValueError:
                clm_available = False
            _respond(self, 200, {"ok": True, "catalogo": {"tienda_id": snapshot["tienda_id"], "version": snapshot["version_catalogo"], "items": len(snapshot["items"]), "fuente": snapshot["importado_desde"]},
                                 "clm_local": {"disponible": clm_available, "requerido_para": "ordenar preferencias contextuales"}})
            return
        if path == "/v1/dispositivos" and self.command == "GET":
            _respond(self, 200, {"dispositivos": DOMINIO["dispositivos"], "preferencias": [
                {"id": p, "nombre": {"montaje_sencillo":"Montaje sencillo", "portabilidad":"Portabilidad", "discrecion":"Discreción"}[p]}
                for p in sorted(PREFERENCIAS)
            ], "usos": [
                {"id": uso, "nombre": {"entrevista_fija":"Entrevista fija en interior",
                                         "entrevista_movil":"Entrevista móvil o en movimiento",
                                         "otro":"Otro uso"}[uso]}
                for uso in sorted(USOS)
            ]})
            return
        if path == "/v1/interpretaciones" and self.command == "POST":
            request = _request_json(self)
            try:
                interpretation = CLMLocal().interpretar(request.get("necesidad"))
            except ValueError as e:
                raise APIError(400, "invalid_need", str(e)) from e
            except CLMError as e:
                raise APIError(503, "clm_unavailable", str(e)) from e
            _respond(self, 200, interpretation)
            return
        if path == "/demo/origen/catalogo" and self.command == "GET":
            cursor = parse_qs(parsed.query).get("cursor", [None])[0]
            _respond(self, 200, _source_page(cursor))
            return
        if path == "/v1/catalogo/importar" and self.command == "POST":
            request = _request_json(self)
            source = request.get("fuente")
            if source == "json":
                snapshot = desde_json(CATALOGO_JSON)
            elif source == "http":
                snapshot = desde_http(f"http://127.0.0.1:{self.server.server_port}/demo/origen/catalogo")
            else:
                raise APIError(400, "invalid_source", "fuente debe ser json o http")
            try:
                validar_catalogo_audio(snapshot)
            except ConfigError as e:
                raise CatalogError(str(e)) from e
            imported = STORE.importar(snapshot, source)
            _respond(self, 200, {"ok": True, "tienda_id": imported["tienda_id"], "version": imported["version_catalogo"],
                                 "snapshot_id": imported["snapshot_id"], "referencias": len(imported["items"]), "fuente": source})
            return
        if path == "/v1/sesiones" and self.command == "POST":
            request = _request_json(self)
            snapshot = STORE.actual()
            if request.get("tienda_id") != snapshot["tienda_id"]:
                raise APIError(400, "unknown_store", "La sesión debe pertenecer a la tienda del catálogo activo")
            state = {
                "tienda_id": snapshot["tienda_id"],
                "necesidad": request.get("necesidad"), "dispositivo_id": request.get("dispositivo_id"),
                "presupuesto_minor": request.get("presupuesto_minor"), "participantes": request.get("participantes"),
                "uso_id": request.get("uso_id"), "preferencias": request.get("preferencias", []), "productos_excluidos": [],
                "productos_previos": [],
                "preguntas_realizadas": 0, "historial_decisiones": [],
            }
            try:
                validar_estado(state, DOMINIO, snapshot)
            except ConfigError as e:
                raise APIError(400, "invalid_request", str(e)) from e
            result = _recomendar(state, snapshot)
            session_id = str(uuid.uuid4())
            session = STORE.crear_sesion(session_id, state, result, snapshot["snapshot_id"], _ahora())
            _respond(self, 201, _public_session(session))
            return
        match = re.fullmatch(r"/v1/sesiones/([0-9a-f-]+)(?:/(decisiones))?", path)
        if match:
            session = STORE.obtener_sesion(match.group(1))
            if session is None:
                raise APIError(404, "session_not_found", "No existe esa sesión")
            session = _refrescar_sesion(session)
            snapshot = STORE.actual()
            if self.command == "GET" and not match.group(2):
                _respond(self, 200, _public_session(session))
                return
            if self.command == "POST" and match.group(2) == "decisiones":
                request = _request_json(self)
                expected = request.get("version_esperada")
                if isinstance(expected, bool) or not isinstance(expected, int):
                    raise APIError(400, "invalid_version", "version_esperada debe ser un entero")
                if expected != session["version"]:
                    raise APIError(409, "state_conflict", "La sesión cambió; vuelve a leerla antes de enviar otra decisión.")
                state = copy.deepcopy(session["estado"])
                action = request.get("accion")
                history = state["historial_decisiones"]
                if action == "responder":
                    question = session["resultado"].get("pregunta")
                    if not question or request.get("pregunta_id") != question["id"]:
                        raise APIError(409, "question_changed", "La pregunta ya no está pendiente; vuelve a leer la sesión.")
                    answer = request.get("respuesta")
                    if answer not in ("aceptar", "rechazar"):
                        raise APIError(400, "invalid_answer", "respuesta debe ser aceptar o rechazar")
                    old_budget = state["presupuesto_minor"]
                    state["preguntas_realizadas"] += 1
                    if answer == "aceptar":
                        state["presupuesto_minor"] = question["presupuesto_minimo_minor"]
                    history.append({"tipo": "concesion_presupuesto", "anterior_minor": old_budget,
                                    "nuevo_minor": state["presupuesto_minor"], "respuesta": answer, "confirmada_el": _ahora()})
                elif action == "cambiar":
                    field, value = request.get("campo"), request.get("valor")
                    old = None
                    if field in ("necesidad", "uso_id", "dispositivo_id", "presupuesto_minor", "participantes"):
                        old = state.get(field)
                        state[field] = value
                    elif field == "entrada":
                        required = ("necesidad", "uso_id", "dispositivo_id", "participantes", "presupuesto_minor", "preferencias")
                        if not isinstance(value, dict) or any(key not in value for key in required):
                            raise APIError(400, "invalid_change", "entrada debe incluir necesidad, dispositivo, participantes, presupuesto y preferencias")
                        old = {key: state[key] for key in required}
                        state.update({key: value[key] for key in required})
                    elif field == "preferencias":
                        if not isinstance(value, list):
                            raise APIError(400, "invalid_preference", "preferencias debe ser una lista")
                        old = state["preferencias"]
                        state["preferencias"] = value
                    elif field == "excluir_producto_id":
                        if not isinstance(value, str) or value not in {p["id"] for p in snapshot["items"]}:
                            raise APIError(400, "unknown_product", "producto excluido no existe en el catálogo")
                        old = list(state["productos_excluidos"])
                        if value not in state["productos_excluidos"]:
                            state["productos_excluidos"].append(value)
                    else:
                        raise APIError(400, "invalid_change", "campo de cambio no permitido")
                    try:
                        validar_estado(state, DOMINIO, snapshot)
                    except ConfigError as e:
                        raise APIError(400, "invalid_change", str(e)) from e
                    history.append({"tipo": "cambio_confirmado", "campo": field, "anterior": old,
                                    "nuevo": value, "confirmada_el": _ahora()})
                else:
                    raise APIError(400, "invalid_action", "accion debe ser cambiar o responder")
                result = _recomendar(state, snapshot)
                updated = STORE.actualizar_sesion(expected, session["id"], state, result, snapshot["snapshot_id"], _ahora())
                if updated is None:
                    raise APIError(409, "state_conflict", "Otra decisión actualizó la sesión; vuelve a leerla.")
                _respond(self, 200, _public_session(updated))
                return
        raise APIError(404, "not_found", "No se encontró esa ruta")

    def do_GET(self):
        self._handle()

    def do_POST(self):
        self._handle()

    def _handle(self):
        try:
            self._route()
        except APIError as e:
            _respond(self, e.status, {"error": {"code": e.code, "message": e.message}})
        except CatalogError as e:
            _respond(self, 422, {"error": {"code": "invalid_catalog", "message": str(e)}})
        except (OSError, sqlite3.Error) as e:
            _respond(self, 500, {"error": {"code": "internal_error", "message": "No se pudo completar la operación"}})


def main():
    if HOST not in ("127.0.0.1", "localhost", "::1"):
        raise SystemExit("Demo 8 solo escucha en loopback; no la expongas directamente a Internet.")
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Demo 8 lista en http://{HOST}:{PORT} · catálogo {STORE.actual()['version_catalogo']} · inferencia CLM solo local")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
