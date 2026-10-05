"""Comprobación ejecutable mínima: adaptadores, motor y contrato HTTP local."""
import json
import io
import os
import copy
import sys
import tempfile
from email.message import Message
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from adaptadores import desde_http, desde_json, pagina_http_demo  # noqa: E402
from catalogo import CatalogError, CatalogStore  # noqa: E402
from configurador import _conjuntos_tecnicos, recomendar  # noqa: E402
from modelo import MAX_TEXTO_BYTES, _excede_limite  # noqa: E402


def check_http_adapters(catalog_path):
    raw = json.loads(catalog_path.read_text(encoding="utf-8"))
    def fetcher(url, _headers, _timeout):
        cursor = parse_qs(urlparse(url).query).get("cursor", [None])[0]
        return pagina_http_demo(raw, cursor)
    from_json = desde_json(catalog_path)
    from_http = desde_http("http://catalogo-demo.invalid/catalog", fetcher=fetcher)
    assert from_json == from_http
    assert len(from_json["items"]) == 40
    try:
        desde_http("http://catalogo-demo.invalid/catalog",
                   fetcher=lambda _url, _headers, _timeout: pagina_http_demo(raw, limit=8) | {"next":None})
        raise AssertionError("se aceptó una paginación parcial")
    except CatalogError:
        pass
    return from_json


def dispatch(app, path, method="GET", body=None):
    """Ejecuta el mismo router HTTP con streams en memoria (sin abrir sockets)."""
    handler = object.__new__(app.Handler)
    handler.command, handler.path = method, path
    handler.headers = Message()
    encoded = json.dumps(body).encode() if body is not None else b""
    handler.headers["Content-Length"] = str(len(encoded))
    handler.rfile, handler.wfile = io.BytesIO(encoded), io.BytesIO()
    handler.server = SimpleNamespace(server_port=8088)
    status = {"code": 200}
    handler.send_response = lambda code, *_args: status.__setitem__("code", code)
    handler.send_header = lambda *_args: None
    handler.end_headers = lambda: None
    app.Handler._handle(handler)
    return status["code"], json.loads(handler.wfile.getvalue())


def main():
    pregunta = {"q": {"instructions": "Valora este conjunto", "criteria": ["bajo", "medio", "alto"]}}
    assert not _excede_limite("uso descrito", pregunta)
    limite_contexto = MAX_TEXTO_BYTES - len("\n\nValora este conjunto".encode("utf-8"))
    assert not _excede_limite("x" * limite_contexto, pregunta)
    assert _excede_limite("x" * (limite_contexto + 1), pregunta)
    assert _excede_limite("uso", {"q": {"instructions": "ok", "criteria": ["x" * 1801, "alto"]}})
    assert _excede_limite("uso", {"q": {"instructions": "ok", "criteria": {"sí":"x" * 1801, "no":"alto"}}})

    catalog = check_http_adapters(BASE / "datos" / "catalogo.json")
    domain = json.loads((BASE / "dominio" / "audio.json").read_text(encoding="utf-8"))
    catalog["snapshot_id"] = 1
    state = {
        "tienda_id": catalog["tienda_id"], "necesidad": "Entrevista fija para dos personas",
        "uso_id": None, "dispositivo_id": "pixel-8-usbc", "participantes": 2, "presupuesto_minor": 25_000,
        "preferencias": [], "productos_excluidos": [], "preguntas_realizadas": 0,
    }
    result = recomendar(state, catalog, domain)
    assert result["recomendaciones"]
    assert all(c["total_minor"] <= state["presupuesto_minor"] and c["compatibilidad"] == "verificada" for c in result["recomendaciones"])
    assert all(any(p["id"].startswith("audio-") for p in c["productos"]) for c in result["recomendaciones"])
    technical, _ = _conjuntos_tecnicos(state, catalog, domain)
    assert all(not any(p["id"] in {"audio-02", "audio-06", "audio-10", "audio-14"} for p in c["productos"]) for c in technical)
    technical_ids = {candidate["id"] for candidate in technical}
    assert "audio-03+adaptador-01+soporte-01" in technical_ids
    assert "audio-04+adaptador-05" in technical_ids
    assert recomendar({**state, "uso_id":"otro"}, catalog, domain)["estado"] == "fuera_de_alcance"

    previous_ids = [p["id"] for p in result["recomendaciones"][0]["productos"]]
    first_previous_name = next(p["nombre"] for p in catalog["items"] if p["id"] == previous_ids[0])
    changed_device = {**state, "dispositivo_id":"iphone-13-lightning", "productos_previos":previous_ids}
    reconfigured = recomendar(changed_device, catalog, domain)
    assert reconfigured["recomendaciones"]
    assert first_previous_name in reconfigured["recomendaciones"][0]["continuidad"]["sustituidos"]

    unknown_only = {**state, "participantes":1,
                    "productos_excluidos":[p["id"] for p in catalog["items"] if p["id"] != "audio-16"]}
    pending = recomendar(unknown_only, catalog, domain)
    assert pending["estado"] == "pendiente_verificacion" and not pending["recomendaciones"]
    unknown_support = copy.deepcopy(catalog)
    for item in unknown_support["items"]:
        if item["atributos"].get("perfil_soporte") == "pinza" and item["familia"] == "soporte":
            item["disponibilidad"], item["cantidad_disponible"] = "desconocido", None
    support_only = {**state, "dispositivo_id":"iphone-13-lightning", "productos_excluidos":
                    [p["id"] for p in catalog["items"]
                     if p["familia"] == "sistema_audio" and p["id"] != "audio-02"]}
    pending_support = recomendar(support_only, unknown_support, domain)
    assert pending_support["estado"] == "pendiente_verificacion"
    assert any(p["producto_id"] == "soporte-09" for p in pending_support["pendientes_verificacion"])
    impossible = {**state, "productos_excluidos":[p["id"] for p in catalog["items"]]}
    assert recomendar(impossible, catalog, domain)["estado"] == "sin_conjunto_dentro_del_presupuesto"

    low_budget = {**state, "presupuesto_minor": 1000}
    conflict = recomendar(low_budget, catalog, domain)
    assert conflict["estado"] == "requiere_concesion"
    assert conflict["pregunta"]["presupuesto_minimo_minor"] > low_budget["presupuesto_minor"]

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "catalog.sqlite3"
        store = CatalogStore(db_path)
        active = store.importar(catalog, "json")
        sid = "session-check"
        store.crear_sesion(sid, state, result, active["snapshot_id"], "2026-09-29T10:00:00+02:00")
        changed = {**state, "presupuesto_minor": 30_000}
        assert store.actualizar_sesion(1, sid, changed, result, active["snapshot_id"], "2026-09-29T10:01:00+02:00")["version"] == 2
        assert store.actualizar_sesion(1, sid, state, result, active["snapshot_id"], "2026-09-29T10:02:00+02:00") is None
        try:
            store.importar({**catalog, "completo": False}, "http")
            raise AssertionError("no se aceptó la instantánea incompleta")
        except CatalogError:
            assert store.actual()["snapshot_id"] == active["snapshot_id"]

        os.environ["DEMO8_DB"] = str(Path(tmp) / "api.sqlite3")
        import app  # La ruta HTTP también queda limitada a un catálogo temporal.
        app.desde_http = lambda _url: catalog
        class CLMStub:
            def interpretar(self, need):
                if not isinstance(need, str) or not need.strip() or len(need) > 2000:
                    raise ValueError("necesidad debe tener entre 1 y 2000 caracteres")
                assert need == "Entrevista móvil a dos personas"
                return {"estado":"ejecutado", "confirmacion_requerida":True,
                        "uso":{"id":"entrevista_movil","confianza":0.8}, "preferencias":[]}
        app.CLMLocal = CLMStub
        code, interpretation = dispatch(app, "/v1/interpretaciones", "POST", {"necesidad":"Entrevista móvil a dos personas"})
        assert code == 200 and interpretation["confirmacion_requerida"]
        assert dispatch(app, "/v1/interpretaciones", "POST", {"necesidad":" "})[0] == 400
        payload = {"tienda_id": catalog["tienda_id"], "necesidad": state["necesidad"],
                   "uso_id": state["uso_id"], "dispositivo_id": state["dispositivo_id"], "participantes": 2,
                   "presupuesto_minor": 1000, "preferencias": []}
        code, session = dispatch(app, "/v1/sesiones", "POST", payload)
        assert code == 201
        assert session["recomendacion"]["pregunta"]["id"] == "aceptar_presupuesto_minimo"
        decision = {"version_esperada": session["version_estado"], "accion":"responder",
                    "pregunta_id":"aceptar_presupuesto_minimo", "respuesta":"aceptar"}
        code, accepted = dispatch(app, f"/v1/sesiones/{session['id']}/decisiones", "POST", decision)
        assert code == 200
        assert accepted["version_estado"] == 2
        assert accepted["estado_confirmado"]["presupuesto_minor"] == session["recomendacion"]["pregunta"]["presupuesto_minimo_minor"]
        entrada = {key: accepted["estado_confirmado"][key] for key in
                   ("necesidad", "dispositivo_id", "participantes", "presupuesto_minor", "preferencias")}
        entrada["uso_id"] = "entrevista_fija"
        code, confirmed = dispatch(app, f"/v1/sesiones/{session['id']}/decisiones", "POST", {
            "version_esperada":accepted["version_estado"], "accion":"cambiar", "campo":"entrada", "valor":entrada,
        })
        assert code == 200 and confirmed["version_estado"] == 3
        assert confirmed["estado_confirmado"]["uso_id"] == "entrevista_fija"

        code, imported = dispatch(app, "/v1/catalogo/importar", "POST", {"fuente":"http"})
        assert code == 200
        assert imported["referencias"] == 40 and imported["fuente"] == "http"
        code, refreshed = dispatch(app, f"/v1/sesiones/{session['id']}")
        assert code == 200
        assert refreshed["catalogo"]["snapshot_id"] == imported["snapshot_id"]
        assert refreshed["version_estado"] == 4

        stale = {**decision, "version_esperada":1}
        code, _ = dispatch(app, f"/v1/sesiones/{session['id']}/decisiones", "POST", stale)
        assert code == 409
    print("OK · 40 variantes · JSON=HTTP · adaptadores · stock desconocido · presupuesto · concesión · CAS · importación atómica · API · límite CLM")


if __name__ == "__main__":
    main()
