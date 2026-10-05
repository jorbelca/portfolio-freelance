"""Contrato de catálogo e instantáneas SQLite de la Demo 8."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime


class CatalogError(ValueError):
    pass


def validar_catalogo(raw):
    if not isinstance(raw, dict) or raw.get("schema_version") != "1.0":
        raise CatalogError("schema_version debe ser '1.0'")
    if not isinstance(raw.get("tienda_id"), str) or not raw["tienda_id"].strip():
        raise CatalogError("falta tienda_id")
    if not isinstance(raw.get("version_catalogo"), str) or not raw["version_catalogo"].strip():
        raise CatalogError("falta version_catalogo")
    if raw.get("completo") is not True:
        raise CatalogError("solo se publican instantáneas completas")
    if not isinstance(raw.get("observado_el"), str) or not raw["observado_el"].strip():
        raise CatalogError("falta observado_el")
    try:
        datetime.fromisoformat(raw["observado_el"].replace("Z", "+00:00"))
    except ValueError as e:
        raise CatalogError("observado_el debe ser una fecha ISO-8601") from e
    items = raw.get("items")
    if not isinstance(items, list) or not items:
        raise CatalogError("items debe ser una lista no vacía")

    ids, origenes = set(), set()
    canonicos = []
    for n, item in enumerate(items):
        prefijo = f"items[{n}]"
        if not isinstance(item, dict):
            raise CatalogError(f"{prefijo} debe ser un objeto")
        for campo in ("id", "nombre", "familia"):
            if not isinstance(item.get(campo), str) or not item[campo].strip():
                raise CatalogError(f"{prefijo}.{campo} es obligatorio")
        if item["id"] in ids:
            raise CatalogError(f"id interno duplicado: {item['id']}")
        ids.add(item["id"])
        origen = item.get("origen_comercial")
        if not isinstance(origen, dict) or any(
            not isinstance(origen.get(k), str) or not origen[k].strip()
            for k in ("tienda_id", "producto_id", "variante_id")
        ):
            raise CatalogError(f"{prefijo}.origen_comercial debe conservar los tres IDs opacos")
        if origen["tienda_id"] != raw["tienda_id"]:
            raise CatalogError(f"{prefijo} pertenece a otra tienda")
        clave_origen = tuple(origen[k] for k in ("tienda_id", "producto_id", "variante_id"))
        if clave_origen in origenes:
            raise CatalogError(f"identidad comercial duplicada: {clave_origen}")
        origenes.add(clave_origen)
        precio = item.get("precio_minor")
        decimales = item.get("decimales_moneda")
        if isinstance(precio, bool) or not isinstance(precio, int) or precio < 0:
            raise CatalogError(f"{prefijo}.precio_minor debe ser un entero no negativo")
        if isinstance(decimales, bool) or not isinstance(decimales, int) or not 0 <= decimales <= 4:
            raise CatalogError(f"{prefijo}.decimales_moneda inválido")
        if not isinstance(item.get("moneda"), str) or len(item["moneda"]) != 3 or item["moneda"] != item["moneda"].upper():
            raise CatalogError(f"{prefijo}.moneda debe ser un código de 3 letras")
        if item.get("disponibilidad") not in ("disponible", "agotado", "desconocido"):
            raise CatalogError(f"{prefijo}.disponibilidad inválida")
        cantidad = item.get("cantidad_disponible")
        if cantidad is not None and (isinstance(cantidad, bool) or not isinstance(cantidad, int) or cantidad < 0):
            raise CatalogError(f"{prefijo}.cantidad_disponible debe ser nula o un entero no negativo")
        if item["disponibilidad"] == "disponible" and (cantidad is None or cantidad < 1):
            raise CatalogError(f"{prefijo} figura disponible sin cantidad confirmada")
        if item["disponibilidad"] == "agotado" and cantidad not in (None, 0):
            raise CatalogError(f"{prefijo} figura agotado pero tiene unidades")
        if item.get("version_catalogo") != raw["version_catalogo"]:
            raise CatalogError(f"{prefijo} declara otra versión de catálogo")
        for campo in ("atributos",):
            if not isinstance(item.get(campo), dict):
                raise CatalogError(f"{prefijo}.{campo} debe ser un objeto")
        for campo in ("incluye", "requiere", "fuentes"):
            if not isinstance(item.get(campo), list):
                raise CatalogError(f"{prefijo}.{campo} debe ser una lista")
        for campo in ("incluye", "requiere"):
            if any(not isinstance(v, str) or not v.strip() for v in item[campo]):
                raise CatalogError(f"{prefijo}.{campo} solo admite etiquetas no vacías")
        if not item["fuentes"] or any(
            not isinstance(source, dict) or not isinstance(source.get("documento"), str)
            or not isinstance(source.get("localizacion"), str)
            for source in item["fuentes"]
        ):
            raise CatalogError(f"{prefijo}.fuentes debe incluir documento y localización")
        if item.get("origen") not in ("sintético", "documentado"):
            raise CatalogError(f"{prefijo}.origen debe indicar sintético o documentado")
        if not isinstance(item.get("observado_el"), str) or not isinstance(item.get("verificado_el"), str):
            raise CatalogError(f"{prefijo} debe declarar las fechas de observación y verificación")
        try:
            date.fromisoformat(item["verificado_el"])
        except ValueError as e:
            raise CatalogError(f"{prefijo}.verificado_el debe ser YYYY-MM-DD") from e
        canonicos.append(item)

    return {
        "schema_version": "1.0", "tienda_id": raw["tienda_id"],
        "version_catalogo": raw["version_catalogo"], "observado_el": raw["observado_el"],
        "completo": True, "items": canonicos,
    }


class CatalogStore:
    def __init__(self, path):
        self.path = str(path)
        with self._db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS catalog_snapshots (
                    id INTEGER PRIMARY KEY,
                    version TEXT NOT NULL,
                    source TEXT NOT NULL,
                    data_json TEXT NOT NULL,
                    imported_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS active_catalog (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    snapshot_id INTEGER NOT NULL REFERENCES catalog_snapshots(id)
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    version INTEGER NOT NULL,
                    state_json TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    snapshot_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
            """)

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        return db

    @contextmanager
    def _db(self):
        db = self._connect()
        try:
            with db:
                yield db
        finally:
            db.close()

    def importar(self, raw, fuente):
        snapshot = validar_catalogo(raw)
        ahora = datetime.now().astimezone().isoformat(timespec="seconds")
        with self._db() as db:
            cur = db.execute(
                "INSERT INTO catalog_snapshots(version, source, data_json, imported_at) VALUES (?, ?, ?, ?)",
                (snapshot["version_catalogo"], fuente, json.dumps(snapshot, ensure_ascii=False), ahora),
            )
            snapshot_id = cur.lastrowid
            db.execute(
                "INSERT INTO active_catalog(singleton, snapshot_id) VALUES (1, ?) "
                "ON CONFLICT(singleton) DO UPDATE SET snapshot_id=excluded.snapshot_id",
                (snapshot_id,),
            )
        return self.actual()

    def actual(self):
        with self._db() as db:
            row = db.execute("""
                SELECT c.id, c.source, c.imported_at, c.data_json
                FROM active_catalog a JOIN catalog_snapshots c ON c.id=a.snapshot_id
                WHERE a.singleton=1
            """).fetchone()
        if row is None:
            return None
        snapshot = json.loads(row["data_json"])
        snapshot.update(snapshot_id=row["id"], importado_desde=row["source"], importado_el=row["imported_at"])
        return snapshot

    def obtener_sesion(self, session_id):
        with self._db() as db:
            row = db.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"], "version": row["version"],
            "estado": json.loads(row["state_json"]), "resultado": json.loads(row["result_json"]),
            "snapshot_id": row["snapshot_id"], "creada_el": row["created_at"], "actualizada_el": row["updated_at"],
        }

    def crear_sesion(self, session_id, state, result, snapshot_id, now):
        with self._db() as db:
            db.execute("""
                INSERT INTO sessions(id, version, state_json, result_json, snapshot_id, created_at, updated_at)
                VALUES (?, 1, ?, ?, ?, ?, ?)
            """, (session_id, json.dumps(state, ensure_ascii=False), json.dumps(result, ensure_ascii=False), snapshot_id, now, now))
        return self.obtener_sesion(session_id)

    def actualizar_sesion(self, old_version, session_id, state, result, snapshot_id, now):
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            cur = db.execute("""
                UPDATE sessions SET version=version+1, state_json=?, result_json=?, snapshot_id=?, updated_at=?
                WHERE id=? AND version=?
            """, (json.dumps(state, ensure_ascii=False), json.dumps(result, ensure_ascii=False), snapshot_id, now, session_id, old_version))
            if cur.rowcount != 1:
                db.rollback()
                return None
        return self.obtener_sesion(session_id)
