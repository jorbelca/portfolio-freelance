#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tablero de la Demo 5: un formulario para meter un lead y ver el grafo clasificarlo en vivo
(traza del bucle ReAct, etiqueta + regla + motivo, señales con fuente, y el borrador de email
si sale caliente), más las tres tablas en tiempo real.

http.server normal no puede invocar el grafo ni tocar SQL, de ahí este fichero. Endpoints:
  GET  /                 -> tablero.html
  GET  /api/casos        -> los 30 leads de eval/dataset.jsonl (para "cargar caso")
  GET  /api/estado       -> {leads, cola_cualificacion, cola_borradores}
  POST /api/procesar     -> {lead, canned_senales?, canned_hallazgos?} -> corre el grafo
  POST /api/reset        -> TRUNCATE (+ crm_leads vuelve a 'nuevo' si el CRM está activo)
  GET  /api/crm          -> bandeja de crm_leads (solo si CRM_PGDATABASE está exportada)
  POST /api/crm          -> alta de un lead a mano en la bandeja
  POST /api/crm/procesar -> corre por el grafo las filas en estado 'nuevo'

Arranque (desde 5/):  PGHOST=... PGPASSWORD=... [OPENROUTER_API_KEY=...] python3 ui/servidor.py
Requiere el Postgres de ../1/ arriba y el esquema aplicado (init-leads-tables.sql).
"""
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from socketserver import ThreadingTCPServer
from urllib.parse import urlsplit

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))  # para importar grafo_leads / tools

import psycopg2  # noqa: E402
from grafo_leads import MODELO, UMBRAL_DEFECTO, construir_grafo  # noqa: E402

GRAFO = construir_grafo()
PUERTO = int(os.environ.get("LEADS_UI_PUERTO", "8095"))
DATASET = AQUI.parent / "eval" / "dataset.jsonl"
RUBRICA = AQUI.parent / "rubrica-cualificacion-leads.md"


def _dsn():
    return (f"host={os.environ.get('PGHOST', '127.0.0.1')} port={os.environ.get('PGPORT', '5432')} "
            f"dbname={os.environ.get('PGDATABASE', 'n8n')} user={os.environ.get('PGUSER', 'n8n_user')} "
            f"password={os.environ.get('PGPASSWORD', '')}")


def _q(sql, params=None, dsn=None):
    conn = psycopg2.connect(dsn or _dsn())
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        if cur.description is None:
            conn.commit()
            return []
        cols = [c.name for c in cur.description]
        filas = [dict(zip(cols, row)) for row in cur.fetchall()]
        conn.commit()
        return filas
    finally:
        conn.close()


# CRM: la bandeja se activa si tablero.sh creó la base `crm` (CRM_PGDATABASE). NocoDB (UI) es
# aparte -- CRM_NOCODB_URL solo se exporta si NocoDB llegó a arrancar.
CRM_DB = os.environ.get("CRM_PGDATABASE") or None
CRM_NOCODB_URL = os.environ.get("CRM_NOCODB_URL") or None


def _dsn_crm():
    return (f"host={os.environ.get('PGHOST', '127.0.0.1')} port={os.environ.get('PGPORT', '5432')} "
            f"dbname={CRM_DB} user={os.environ.get('PGUSER', 'n8n_user')} "
            f"password={os.environ.get('PGPASSWORD', '')}")


def estado_bbd():
    return {
        "leads": _q("SELECT id, empresa, etiqueta, regla, motivo, asignado_a, confianza, "
                    "senales, creado_en FROM leads ORDER BY id DESC LIMIT 40"),
        "cola_cualificacion": _q("SELECT id, empresa, etiqueta, motivo, confianza, creado_en "
                                 "FROM cola_leads WHERE tipo='cualificacion' ORDER BY id DESC LIMIT 40"),
        "cola_borradores": _q("SELECT id, empresa, contacto_email, borrador_message_id, creado_en "
                              "FROM cola_leads WHERE tipo='borrador' ORDER BY id DESC LIMIT 40"),
    }


def _estado_inicial(cuerpo):
    lead = cuerpo["lead"]
    estado = {
        "lead_ref": lead.get("lead_ref") or f"ui-{os.urandom(3).hex()}",
        "empresa": lead.get("empresa", ""),
        "contacto_nombre": lead.get("contacto_nombre"),
        "contacto_email": lead.get("contacto_email", ""),
        "contacto_cargo": lead.get("contacto_cargo"),
        "canal_origen": lead.get("canal_origen") or "tablero",
    }
    if cuerpo.get("canned_senales") is not None:
        estado["canned_senales"] = cuerpo["canned_senales"]
    if cuerpo.get("canned_hallazgos") is not None:
        estado["canned_hallazgos"] = cuerpo["canned_hallazgos"]
    return estado


def _formato_resultado(r, pasos):
    return {
        "decision": r.get("decision"),
        "resultado_log": r.get("resultado_log"),
        "etiqueta": r.get("etiqueta"),
        "regla": r.get("regla"),
        "motivo": r.get("motivo"),
        "confianza": r.get("confianza"),
        "ficha": r.get("ficha") or {},
        "hallazgos": r.get("hallazgos") or {},
        "errores_validacion": r.get("errores_validacion") or [],
        "etiqueta_rival": r.get("etiqueta_rival"),
        "motivo_duda": r.get("motivo_duda"),
        "investigacion_pasos": r.get("investigacion_pasos") or [],
        "senales": (r.get("hallazgos") or {}).get("senales") or [],
        "senales_crudas": r.get("senales_crudas") or [],
        "asignado_a": r.get("asignado_a"),
        "followup_sugerido": r.get("followup_sugerido"),
        "borrador_asunto": r.get("borrador_asunto"),
        "borrador_cuerpo": r.get("borrador_cuerpo"),
        "borrador_message_id": r.get("borrador_message_id"),
        "pasos": pasos,
    }


def procesar(cuerpo):
    r, pasos = {}, []
    for evento in GRAFO.stream(_estado_inicial(cuerpo), stream_mode="updates"):
        for nodo, salida in evento.items():
            pasos.append({"nodo": nodo, "salida": salida})
            r.update(salida or {})
    return _formato_resultado(r, pasos)


EVAL = {"corriendo": False, "parar": False, "hechos": 0, "total": 0,
        "filas": [], "resumen": None, "error": None}


def _correr_eval():
    """Corre los 30 casos del dataset por el grafo (evidencia fija del caso, la IA clasifica),
    compara cada uno contra `esperado` (etiqueta / regla / en_cola) y va dejando una fila por
    caso en EVAL['filas']. Mismos buckets que eval/run_eval.py. TRUNCA antes -> el histórico
    refleja esta corrida. Se para si EVAL['parar']."""
    try:
        casos = [json.loads(l) for l in open(DATASET, encoding="utf-8") if l.strip()]
        conn = psycopg2.connect(_dsn())
        conn.autocommit = True
        conn.cursor().execute("TRUNCATE leads, cola_leads, cualificacion_log RESTART IDENTITY;")
        conn.close()
        EVAL.update(total=len(casos), hechos=0, filas=[], resumen=None, error=None)
        for c in casos:
            if EVAL["parar"]:
                break
            e = c["esperado"]
            r = GRAFO.invoke({
                "lead_ref": c["id"],
                "empresa": c["lead"].get("empresa", ""),
                "contacto_nombre": c["lead"].get("contacto_nombre"),
                "contacto_email": c["lead"].get("contacto_email", ""),
                "contacto_cargo": c["lead"].get("contacto_cargo"),
                "canal_origen": "eval",
                "canned_senales": c["senales_crudas"],
            })
            et = r.get("etiqueta") or None
            rg = r.get("regla") or None
            en_cola_obt = (r.get("resultado_log") or "cualificado") != "cualificado"
            # Un fallo de la llamada al modelo (modelo inexistente, 429 agotado, timeout) sale
            # por aquí: sin él, `sin_cualificar` parece un resultado de clasificación y esconde
            # un error de config (p.ej. LEADS_MODELO mal escrito -> los 30 a 0/30).
            err = r.get("_error_cualificacion") or (
                r.get("motivo_duda") if "falló" in (r.get("motivo_duda") or "") else None)
            EVAL["filas"].append({
                "id": c["id"], "empresa": c["lead"].get("empresa", ""),
                "esp_etiqueta": e["etiqueta"] or "sin_cualificar",
                "obt_etiqueta": et or "sin_cualificar",
                "esp_regla": e["regla"], "obt_regla": rg,
                "esp_cola": e["en_cola"], "obt_cola": en_cola_obt,
                "et_ok": et == e["etiqueta"], "rg_ok": rg == e["regla"],
                "cola_ok": en_cola_obt == e["en_cola"],
                "error": err,
            })
            EVAL["hechos"] += 1
        f = EVAL["filas"]
        EVAL["resumen"] = {
            "hechos": len(f), "total": len(casos), "parado": EVAL["parar"],
            "etiqueta_ok": sum(x["et_ok"] for x in f),
            "regla_ok": sum(x["rg_ok"] for x in f),
            "cola_ok": sum(x["cola_ok"] for x in f),
            "errores": sum(1 for x in f if x["error"]),
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        EVAL["error"] = str(e)
    finally:
        EVAL["corriendo"] = False


# --- CRM (bandeja NocoDB) -- solo activo si tablero.sh exportó CRM_PGDATABASE ------------
CRM = {"corriendo": False, "hechos": 0, "total": 0, "error": None}


def _crm_estado(resultado_log, etiqueta):
    if resultado_log == "cualificado":
        return "descartado" if etiqueta == "frio" else "cualificado"
    if resultado_log == "sin_cualificar":
        return "error"
    return "en_revision"  # cola_leads


def _correr_crm():
    """Procesa por el grafo las filas de crm_leads en estado 'nuevo' (investigación real, sin
    evidencia inyectada) y escribe de vuelta estado + resultado. Como _correr_eval pero sobre
    la bandeja del CRM y sin TRUNCAR nada."""
    dsn = _dsn_crm()
    try:
        nuevos = _q("SELECT id, empresa, contacto_nombre, contacto_email, contacto_cargo, "
                    "canal_origen FROM crm_leads WHERE estado='nuevo' ORDER BY id", dsn=dsn)
        CRM.update(total=len(nuevos), hechos=0, error=None)
        for row in nuevos:
            _q("UPDATE crm_leads SET estado='procesando' WHERE id=%s", (row["id"],), dsn=dsn)
            try:
                r = GRAFO.invoke({
                    "lead_ref": f"crm-{row['id']}",
                    "empresa": row["empresa"] or "",
                    "contacto_nombre": row["contacto_nombre"],
                    "contacto_email": row["contacto_email"] or "",
                    "contacto_cargo": row["contacto_cargo"],
                    "canal_origen": row["canal_origen"] or "crm",
                })
                _q("UPDATE crm_leads SET estado=%s, etiqueta=%s, regla=%s, motivo=%s, "
                   "lead_id=%s, cola_id=%s, procesado_en=now() WHERE id=%s",
                   (_crm_estado(r.get("resultado_log") or "cualificado", r.get("etiqueta")),
                    r.get("etiqueta"), r.get("regla"), r.get("motivo"),
                    r.get("lead_id"), r.get("cola_id"), row["id"]), dsn=dsn)
            except Exception as e:
                _q("UPDATE crm_leads SET estado='error', motivo=%s, procesado_en=now() WHERE id=%s",
                   (str(e)[:300], row["id"]), dsn=dsn)
            CRM["hechos"] += 1
    except Exception as e:
        import traceback
        traceback.print_exc()
        CRM["error"] = str(e)
    finally:
        CRM["corriendo"] = False


def crm_bandeja():
    filas = _q("SELECT id, empresa, contacto_nombre, contacto_email, contacto_cargo, canal_origen, "
               "estado, etiqueta, regla, motivo, lead_id, cola_id, creado_en, procesado_en "
               "FROM crm_leads ORDER BY id DESC LIMIT 100", dsn=_dsn_crm())
    return {"filas": filas, "nuevos": sum(1 for f in filas if f["estado"] == "nuevo"),
            "corriendo": CRM["corriendo"], "hechos": CRM["hechos"], "total": CRM["total"],
            "error": CRM["error"], "url": CRM_NOCODB_URL}


class H(BaseHTTPRequestHandler):
    def _send(self, status, body, ctype="application/json"):
        payload = body if isinstance(body, bytes) else json.dumps(body, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *a):
        pass

    def _procesar_stream(self, cuerpo):
        """SSE: un `data:` por nodo del grafo según se completa (como la Demo 4), y un evento
        final con el resultado ya formateado. El modelo :free tarda ~100 s -> ver los nodos
        encenderse de uno en uno bate al spinner congelado."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        def envia(obj):
            self.wfile.write(f"data: {json.dumps(obj, default=str)}\n\n".encode())
            self.wfile.flush()

        r, pasos = {}, []
        try:
            for evento in GRAFO.stream(_estado_inicial(cuerpo), stream_mode="updates"):
                for nodo, salida in evento.items():
                    pasos.append({"nodo": nodo, "salida": salida})
                    r.update(salida or {})
                    envia({"tipo": "paso", "nodo": nodo, "salida": salida})
            envia({"tipo": "fin", "resultado": _formato_resultado(r, pasos)})
        except Exception as e:
            import traceback
            traceback.print_exc()
            envia({"tipo": "error", "error": str(e)})

    def do_GET(self):
        ruta = urlsplit(self.path).path
        if ruta in ("/", "/index.html", "/tablero.html"):
            return self._send(200, (AQUI / "tablero.html").read_bytes(), "text/html; charset=utf-8")
        if ruta == "/api/casos":
            casos = [json.loads(l) for l in open(DATASET, encoding="utf-8") if l.strip()]
            return self._send(200, casos)
        if ruta == "/api/estado":
            try:
                return self._send(200, estado_bbd())
            except Exception as e:
                return self._send(500, {"error": str(e)})
        if ruta in ("/rubrica", "/rubrica.html"):
            return self._send(200, (AQUI / "rubrica.html").read_bytes(), "text/html; charset=utf-8")
        if ruta == "/api/rubrica":
            return self._send(200, RUBRICA.read_bytes(), "text/plain; charset=utf-8")
        if ruta == "/api/eval":
            return self._send(200, EVAL)
        if ruta == "/api/config":
            return self._send(200, {"modelo": MODELO, "umbral": UMBRAL_DEFECTO,
                                    "crm": bool(CRM_DB), "nocodb_url": CRM_NOCODB_URL})
        if ruta == "/api/crm":
            if not CRM_DB:
                return self._send(200, {"habilitado": False})
            try:
                return self._send(200, {"habilitado": True, **crm_bandeja()})
            except Exception as e:
                return self._send(500, {"error": str(e)})
        return self._send(404, {"error": "no encontrado"})

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        cuerpo = json.loads(self.rfile.read(n) or b"{}")
        ruta = urlsplit(self.path).path
        try:
            if ruta == "/api/procesar_stream":
                return self._procesar_stream(cuerpo)
            if ruta == "/api/procesar":
                return self._send(200, procesar(cuerpo))
            if ruta == "/api/reset":
                conn = psycopg2.connect(_dsn())
                conn.autocommit = True
                conn.cursor().execute("TRUNCATE leads, cola_leads, cualificacion_log RESTART IDENTITY;")
                conn.close()
                if CRM_DB:  # los leads de la bandeja vuelven a 'nuevo', listos para re-procesar
                    _q("UPDATE crm_leads SET estado='nuevo', etiqueta=NULL, regla=NULL, motivo=NULL, "
                       "lead_id=NULL, cola_id=NULL, procesado_en=NULL", dsn=_dsn_crm())
                return self._send(200, {"ok": True})
            if ruta == "/api/eval":
                if EVAL["corriendo"]:
                    return self._send(409, {"error": "ya hay una corrida en marcha"})
                EVAL.update(corriendo=True, parar=False, hechos=0, total=0,
                            filas=[], resumen=None, error=None)
                threading.Thread(target=_correr_eval, daemon=True).start()
                return self._send(200, {"ok": True})
            if ruta == "/api/eval/parar":
                EVAL["parar"] = True
                return self._send(200, {"ok": True})
            if ruta == "/api/crm":  # alta de lead a mano
                if not CRM_DB:
                    return self._send(400, {"error": "CRM no configurado"})
                emp = (cuerpo.get("empresa") or "").strip()
                email = (cuerpo.get("contacto_email") or "").strip()
                if not emp or not email:
                    return self._send(400, {"error": "empresa y email son obligatorios"})
                _q("INSERT INTO crm_leads (empresa, contacto_nombre, contacto_email, contacto_cargo, "
                   "canal_origen) VALUES (%s,%s,%s,%s,%s)",
                   (emp, (cuerpo.get("contacto_nombre") or "").strip() or None, email,
                    (cuerpo.get("contacto_cargo") or "").strip() or None,
                    (cuerpo.get("canal_origen") or "crm").strip()), dsn=_dsn_crm())
                return self._send(200, {"ok": True})
            if ruta == "/api/crm/procesar":
                if not CRM_DB:
                    return self._send(400, {"error": "CRM no configurado"})
                if CRM["corriendo"]:
                    return self._send(409, {"error": "ya hay una corrida en marcha"})
                CRM.update(corriendo=True, hechos=0, total=0, error=None)
                threading.Thread(target=_correr_crm, daemon=True).start()
                return self._send(200, {"ok": True})
        except Exception as e:
            import traceback
            traceback.print_exc()
            return self._send(500, {"error": str(e)})
        return self._send(404, {"error": "no encontrado"})


if __name__ == "__main__":
    print(f"Tablero Demo 5 en http://127.0.0.1:{PUERTO}  (Ctrl+C para parar)")
    ThreadingTCPServer.allow_reuse_address = True
    ThreadingTCPServer(("127.0.0.1", PUERTO), H).serve_forever()
