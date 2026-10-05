"""Adaptadores de fichero y HTTP al contrato común de catálogo."""
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from catalogo import CatalogError, validar_catalogo


def desde_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return validar_catalogo(json.load(f))
    except (OSError, json.JSONDecodeError) as e:
        raise CatalogError(f"no se pudo leer el catálogo JSON: {e}") from e


def pagina_http_demo(catalog, cursor=None, limit=8):
    """Expone la misma instantánea con nombres y paginación propios de otra tienda."""
    try:
        offset = int(cursor or "0")
    except ValueError as e:
        raise CatalogError("cursor HTTP inválido") from e
    if offset < 0 or limit < 1:
        raise CatalogError("cursor HTTP inválido")
    rows = []
    for item in catalog["items"][offset:offset + limit]:
        origin = item["origen_comercial"]
        rows.append({
            "sku": item["id"], "title": item["nombre"], "category": item["familia"],
            "identifiers": {"store": origin["tienda_id"], "product": origin["producto_id"], "variant": origin["variante_id"], "url": origin.get("url")},
            "price": {"minor_units": item["precio_minor"], "currency": item["moneda"], "fraction_digits": item["decimales_moneda"]},
            "inventory": {"state": item["disponibilidad"], "units": item["cantidad_disponible"]},
            "seenAt": item["observado_el"], "revision": item["version_catalogo"],
            "specifications": item["atributos"], "contents": item["incluye"], "dependencies": item["requiere"],
            "evidence": item["fuentes"], "checkedAt": item["verificado_el"], "dataOrigin": item["origen"],
        })
    end = offset + len(rows)
    return {
        "contract": catalog["schema_version"], "store": catalog["tienda_id"],
        "revision": catalog["version_catalogo"], "observedAt": catalog["observado_el"],
        "categoryComplete": catalog["completo"], "totalEntries": len(catalog["items"]), "entries": rows,
        "next": str(end) if end < len(catalog["items"]) else None,
    }


def _normalizar_fila(row):
    price, stock, ids = row.get("price"), row.get("inventory"), row.get("identifiers")
    if not all(isinstance(x, dict) for x in (price, stock, ids)):
        raise CatalogError("la API de catálogo devolvió una fila incompleta")
    return {
        "id": row.get("sku"), "nombre": row.get("title"), "familia": row.get("category"),
        "origen_comercial": {
            "tienda_id": ids.get("store"), "producto_id": ids.get("product"), "variante_id": ids.get("variant"),
            "url": ids.get("url"),
        },
        "precio_minor": price.get("minor_units"), "moneda": price.get("currency"),
        "decimales_moneda": price.get("fraction_digits"),
        "disponibilidad": stock.get("state"), "cantidad_disponible": stock.get("units"),
        "observado_el": row.get("seenAt"), "version_catalogo": row.get("revision"),
        "atributos": row.get("specifications"), "incluye": row.get("contents"),
        "requiere": row.get("dependencies"), "fuentes": row.get("evidence"),
        "verificado_el": row.get("checkedAt"), "origen": row.get("dataOrigin"),
    }


def desde_http(base_url, api_key=None, timeout=10, fetcher=None):
    items, cursor_vistos, cursor = [], set(), None
    metadata = None
    total_esperado = None
    while True:
        query = urlencode({"cursor": cursor}) if cursor else ""
        url = base_url.rstrip("?") + (f"?{query}" if query else "")
        headers = {"Accept": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        try:
            if fetcher:
                page = fetcher(url, headers, timeout)
            else:
                with urlopen(Request(url, headers=headers), timeout=timeout) as response:
                    page = json.loads(response.read())
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as e:
            raise CatalogError(f"falló la lectura HTTP; no se publicó el catálogo: {e}") from e
        if not isinstance(page, dict) or not isinstance(page.get("entries"), list):
            raise CatalogError("la página HTTP no contiene entries")
        page_meta = {
            "schema_version": page.get("contract"), "tienda_id": page.get("store"),
            "version_catalogo": page.get("revision"), "observado_el": page.get("observedAt"),
            "completo": page.get("categoryComplete"),
        }
        total = page.get("totalEntries")
        if isinstance(total, bool) or not isinstance(total, int) or total < 1:
            raise CatalogError("la API debe declarar totalEntries para detectar una paginación incompleta")
        if metadata is None:
            metadata = page_meta
            total_esperado = total
        elif page_meta != metadata:
            raise CatalogError("los metadatos cambiaron durante la paginación")
        elif total != total_esperado:
            raise CatalogError("totalEntries cambió durante la paginación")
        items.extend(_normalizar_fila(item) for item in page["entries"])
        next_cursor = page.get("next")
        if not next_cursor:
            break
        if not isinstance(next_cursor, str) or next_cursor in cursor_vistos:
            raise CatalogError("cursor HTTP inválido o repetido")
        cursor_vistos.add(next_cursor)
        cursor = next_cursor
    if metadata is None:
        raise CatalogError("la API no devolvió ninguna página")
    if len(items) != total_esperado:
        raise CatalogError(f"paginación incompleta: se recibieron {len(items)} de {total_esperado} referencias")
    return validar_catalogo({**metadata, "items": items})
