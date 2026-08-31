#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Genera facturas PDF sintéticas + eval/dataset.jsonl (verdad) a partir de una semilla
determinista (random.Random(SEED), reproducible caso a caso -- no byte a byte del PDF, porque
fpdf2 no permite fijar la fecha de creación embebida sin tocar metadata en cada build; se
documenta como límite conocido, no se persigue).

30 casos: 11 "marcados" (obligatorios por §14.3, ver CASOS_MARCADOS) + 19 de relleno generados
en bucle (_generar_relleno) con proveedor/importe/tipo de IVA variados sobre 3 layouts, todos
limpios (esperado_en_cola=False) -- amplían la variedad de formato sin ser casos de prueba en
sí mismos.

Formato español de importes en el PDF ("1.234,56 EUR") a propósito: es una trampa clásica de
parsing (punto de millar vs. decimal) que la extracción debe superar en cámara.

proveedor_nif se genera con validaciones.generar_cif_valido() -- misma función que usa el
validador -- para que un CIF "válido" en este dataset sea válido de verdad y no una cadena que
solo parece un CIF.
"""
import json
import random
from decimal import Decimal
from pathlib import Path

from fpdf import FPDF

from validaciones import generar_cif_valido, validar_factura

AQUI = Path(__file__).resolve().parent
DIR_PDF = AQUI / "facturas_pdf"
DATASET = AQUI / "eval" / "dataset.jsonl"
SEED = 20260824


def fmt_es(valor) -> str:
    """1234.56 -> '1.234,56 EUR'. Formato español: punto de millar, coma decimal.
    'EUR' en vez del símbolo '€' porque las fuentes core de fpdf2 (Helvetica) son
    latin-1 y no lo codifican -- añadir una fuente Unicode solo para un símbolo sería
    una dependencia (fichero .ttf) que no aporta nada a la prueba de parsing real,
    que es el separador de miles/decimales, no el símbolo de moneda."""
    s = f"{Decimal(str(valor)):,.2f}"
    s = s.translate(str.maketrans(",.", ".,"))
    return f"{s} EUR"


# --- Layouts: 3 variantes visualmente distintas del mismo contenido, para que la extracción no
# se acostumbre a una única disposición de campos (§14.3 pide "2-3 layouts distintos"). ---

def _layout_estandar(pdf: FPDF, c: dict) -> None:
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 12, f"FACTURA {c['numero_factura']}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=11)
    pdf.ln(4)
    pdf.cell(0, 7, f"Fecha de emisión: {c['fecha_emision']}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "Proveedor", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=11)
    pdf.cell(0, 6, c["proveedor_nombre"], new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, f"NIF: {c['proveedor_nif']}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "Cliente", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=11)
    pdf.cell(0, 6, c["cliente_nombre"], new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, f"NIF: {c['cliente_nif']}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)
    pdf.cell(0, 6, f"Concepto: {c['concepto_resumen']}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.cell(0, 6, f"Base imponible: {fmt_es(c['base_imponible'])}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, f"IVA ({c['tipo_iva']}%): {fmt_es(c['cuota_iva'])}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, f"TOTAL: {fmt_es(c['total'])}", new_x="LMARGIN", new_y="NEXT")


def _layout_compacta(pdf: FPDF, c: dict) -> None:
    """Todo en una sola columna densa, sin secciones "Proveedor"/"Cliente" separadas -- el
    layout que más se parece a una factura generada por un TPV o software de facturación
    barato, una línea por dato."""
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 9, f"Nº {c['numero_factura']}  |  {c['fecha_emision']}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=10)
    pdf.ln(2)
    pdf.cell(0, 5, f"{c['proveedor_nombre']} (NIF {c['proveedor_nif']})  ->  "
                   f"{c['cliente_nombre']} (NIF {c['cliente_nif']})", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, c["concepto_resumen"], new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    pdf.cell(0, 5, f"Base {fmt_es(c['base_imponible'])}  +  "
                   f"IVA {c['tipo_iva']}% ({fmt_es(c['cuota_iva'])})  =  "
                   f"TOTAL {fmt_es(c['total'])}", new_x="LMARGIN", new_y="NEXT")


def _layout_tabla(pdf: FPDF, c: dict) -> None:
    """Campos como tabla de dos columnas (etiqueta | valor) -- el layout más fácil de parsear
    por posición, pero distinto en estructura visual a los otros dos."""
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "FACTURA", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=10)
    filas = [
        ("Número", c["numero_factura"]), ("Fecha", c["fecha_emision"]),
        ("Proveedor", c["proveedor_nombre"]), ("NIF proveedor", c["proveedor_nif"]),
        ("Cliente", c["cliente_nombre"]), ("NIF cliente", c["cliente_nif"]),
        ("Concepto", c["concepto_resumen"]),
        ("Base imponible", fmt_es(c["base_imponible"])),
        (f"IVA {c['tipo_iva']}%", fmt_es(c["cuota_iva"])),
        ("TOTAL", fmt_es(c["total"])),
    ]
    for etiqueta, valor in filas:
        pdf.cell(50, 6, etiqueta, border=1)
        pdf.cell(0, 6, str(valor), border=1, new_x="LMARGIN", new_y="NEXT")


LAYOUTS = {"estandar": _layout_estandar, "compacta": _layout_compacta, "tabla": _layout_tabla}


def construir_pdf(path: Path, c: dict, layout: str = "estandar") -> None:
    pdf = FPDF(format="A4")
    pdf.add_page()
    LAYOUTS[layout](pdf, c)
    pdf.output(str(path))


def construir_pdf_multipagina(path: Path, c: dict) -> None:
    """Página 1: factura normal. Página 2: observaciones/desglose -- contenido distractor real,
    no una página en blanco, para probar que ingesta_pdf concatena TODAS las páginas y que
    extraccion_llm no se confunde con texto adicional que no son los campos del contrato."""
    pdf = FPDF(format="A4")
    pdf.add_page()
    _layout_estandar(pdf, c)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 10, "Observaciones", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=10)
    pdf.multi_cell(0, 6,
        "Desglose de materiales incluidos en el concepto facturado: tubería PVC 32mm (12u), "
        "codos 90º (8u), llave de paso 1\" (2u), mano de obra (4h). Garantía de la reparación: "
        "12 meses desde la fecha de emisión. Forma de pago: transferencia bancaria a 30 días.")
    pdf.output(str(path))


def construir_pdf_ruidoso(path: Path, c: dict, seed: int) -> None:
    """Rasteriza la factura como imagen (sin capa de texto) y le añade ruido sal-y-pimienta --
    simula un escaneo de mala calidad. pdfplumber.extract_text() no puede leer nada de esto (no
    hay OCR en el grafo todavía): ingesta_pdf devuelve texto vacío, y con un LLM real la
    extracción tendría que fallar o degradarse -- es un hueco real y deliberado del pipeline
    actual (ver README, sección 'pendiente'), no un caso que el sistema deba resolver hoy.

    El PNG intermedio se conserva (no se borra) a propósito: es el gancho visual del vídeo,
    imagen ruidosa junto a la extracción vacía que produce."""
    from PIL import Image, ImageDraw

    rng = random.Random(seed)
    w, h = 1000, 1400
    img = Image.new("L", (w, h), color=255)
    draw = ImageDraw.Draw(img)
    lineas = [
        f"FACTURA {c['numero_factura']}", f"Fecha: {c['fecha_emision']}",
        c["proveedor_nombre"], f"NIF: {c['proveedor_nif']}", c["concepto_resumen"],
        f"Base: {fmt_es(c['base_imponible'])}", f"IVA {c['tipo_iva']}%: {fmt_es(c['cuota_iva'])}",
        f"TOTAL: {fmt_es(c['total'])}",
    ]
    y = 60
    for linea in lineas:
        draw.text((60, y), linea, fill=0)
        y += 55
    pix = img.load()
    for _ in range(int(w * h * 0.10)):  # 10% de píxeles con ruido sal-y-pimienta
        x, y2 = rng.randrange(w), rng.randrange(h)
        pix[x, y2] = rng.choice([0, 255])

    tmp_png = path.with_suffix(".png")
    img.save(tmp_png)
    pdf = FPDF(format="A4")
    pdf.add_page()
    pdf.image(str(tmp_png), x=0, y=0, w=210)
    pdf.output(str(path))


def _base(id_, **overrides):
    n = id_[1:] if id_[0] == "f" else id_
    c = {
        "numero_factura": f"F-2026-{n}",
        "fecha_emision": "2026-06-15",
        "proveedor_nombre": "Suministros Ejemplo SL",
        "proveedor_nif": generar_cif_valido("B", "1234567"),
        "cliente_nombre": "Comunidad Propietarios CDP-001",
        "cliente_nif": generar_cif_valido("H", "7654321"),
        "concepto_resumen": "Material de fontanería",
        "base_imponible": "1200.00",
        "tipo_iva": "21",
        "cuota_iva": "252.00",
        "total": "1452.00",
    }
    c.update(overrides)
    return c


# --- Casos marcados: los 11 obligatorios de §14.3, con control expreso de cada campo. ---

CASOS_MARCADOS = [
    {"id": "f01", "campos": _base("f01"), "layout": "estandar",
     "esperado_en_cola": False, "motivo_esperado": None,
     "nota": "Caso limpio: aritmética cuadra, NIF válido, fecha pasada, número presente."},

    {"id": "f02", "layout": "estandar", "esperado_en_cola": True, "motivo_esperado": "aritmética",
     "campos": _base("f02", proveedor_nombre="Reformas Genéricas SL",
                      proveedor_nif=generar_cif_valido("B", "2345678"),
                      base_imponible="500.00", tipo_iva="21",
                      cuota_iva="100.00",  # debería ser 105.00 -- error deliberado
                      total="600.00"),
     "nota": "Aritmética rota #1: cuota declarada (100.00) no cuadra con base×tipo "
             "(500×21%=105.00); el LLM puede transcribir estos números con confianza alta "
             "sin detectarlo."},

    {"id": "f05", "layout": "compacta", "esperado_en_cola": True, "motivo_esperado": "aritmética",
     "campos": _base("f05", proveedor_nombre="Ascensores Ficticios SA",
                      proveedor_nif=generar_cif_valido("A", "3456789"),
                      base_imponible="900.00", tipo_iva="21",
                      cuota_iva="189.00", total="1080.00"),  # 900+189=1089, no 1080 -- total roto
     "nota": "Aritmética rota #2: aquí falla base+cuota≈total (1089 esperado, 1080 declarado), "
             "no la cuota en sí -- distinto punto de fallo al de f02."},

    {"id": "f03", "layout": "estandar", "esperado_en_cola": True, "motivo_esperado": "nif",
     "campos": _base("f03", proveedor_nombre="Electricidad Muestra SL",
                      proveedor_nif="B2345671Z"),  # letra de control incorrecta a propósito
     "nota": "NIF inválido #1: CIF con dígito/letra de control que no corresponde a los 7 dígitos."},

    {"id": "f06", "layout": "tabla", "esperado_en_cola": True, "motivo_esperado": "nif",
     "campos": _base("f06", proveedor_nombre="Impermeabilizaciones Modelo SL",
                      proveedor_nif="H99999999"),  # formato correcto, control imposible
     "nota": "NIF inválido #2: mismo tipo de fallo que f03 pero en layout de tabla, para que "
             "la validación no dependa de dónde cae el campo en la página."},

    {"id": "f07", "layout": "estandar", "esperado_en_cola": True, "motivo_esperado": "numero_factura",
     "campos": _base("f07", numero_factura=""),
     "nota": "Sin número de factura: sin clave de deduplicación ni referencia contable."},

    {"id": "f04", "layout": "estandar", "esperado_en_cola": True, "motivo_esperado": "duplicado",
     "campos": _base("f04", numero_factura=_base("f01")["numero_factura"],
                      proveedor_nombre="Suministros Ejemplo SL",
                      proveedor_nif=_base("f01")["proveedor_nif"],
                      base_imponible="1180.00", tipo_iva="21", cuota_iva="247.80", total="1427.80"),
     "nota": "Mismo (proveedor_nif, numero_factura) que f01 pero importes distintos -- simula "
             "un reenvío u OCR divergente del mismo documento. Solo se detecta al intentar "
             "persistir SI f01 se procesó antes (UNIQUE en Postgres, no un pre-check en "
             "Python): el orden de procesado importa, por diseño."},

    {"id": "f08", "layout": "compacta", "esperado_en_cola": False, "motivo_esperado": None,
     "campos": _base("f08", proveedor_nombre="Cerrajería Prototipo SL",
                      proveedor_nif=generar_cif_valido("B", "4567890"),
                      concepto_resumen="Sustitución de cerradura",
                      base_imponible="300.00", tipo_iva="10", cuota_iva="30.00", total="330.00"),
     "nota": "IVA reducido (10%) normal -- NO debe ir a cola: el sistema no debe confundir "
             "'tipo reducido' con 'error aritmético'."},

    {"id": "f09", "layout": "tabla", "esperado_en_cola": False, "motivo_esperado": None,
     "campos": _base("f09", proveedor_nombre="Fontanería Ejemplo SL",
                      proveedor_nif=generar_cif_valido("B", "5678901"),
                      concepto_resumen="Material de construcción (uso vivienda)",
                      base_imponible="800.00", tipo_iva="4", cuota_iva="32.00", total="832.00"),
     "nota": "IVA superreducido (4%) normal -- mismo motivo que f08, tipo distinto."},

    {"id": "f10", "layout": None, "especial": "ruidoso", "esperado_en_cola": True,
     "motivo_esperado": "confianza baja",
     "campos": _base("f10", proveedor_nombre="Reformas Genéricas SL",
                      proveedor_nif=generar_cif_valido("B", "6789012")),
     # Para --sin-llm: simula lo que un modelo real extraería de un escaneo ruidoso -- el
     # nombre del proveedor (texto grande, más resistente al ruido) sale con confianza alta,
     # el resto (números pequeños) con confianza baja. No son los campos_verdad: son una
     # extracción DEGRADADA a propósito, porque el objetivo de este caso es probar el gate de
     # confianza, no la fidelidad de la extracción.
     "canned_override": {"confianza_baja": ["numero_factura", "proveedor_nif", "base_imponible",
                                             "cuota_iva", "total", "fecha_emision"]},
     "nota": "Escaneo ruidoso: PDF sin capa de texto (imagen rasterizada + ruido). "
             "pdfplumber no puede leerlo -- hueco real del pipeline (no hay OCR todavía, ver "
             "README). El canned de --sin-llm simula confianza baja en los campos numéricos, "
             "no la ausencia total de texto."},

    {"id": "f11", "layout": None, "especial": "multipagina", "esperado_en_cola": False,
     "motivo_esperado": None,
     "campos": _base("f11", proveedor_nombre="Ascensores Ficticios SA",
                      proveedor_nif=generar_cif_valido("A", "7890123"),
                      concepto_resumen="Mantenimiento trimestral ascensor"),
     "nota": "Multipágina: página 2 lleva observaciones/desglose (contenido real, no relleno) "
             "-- prueba que ingesta_pdf concatena todas las páginas y que la extracción no se "
             "distrae con texto que no son los campos del contrato."},
]

# --- Relleno: 19 casos limpios generados en bucle, variando proveedor/importe/IVA/layout,
# para llegar a 30 sin escribir cada uno a mano. Todos esperado_en_cola=False. ---

_PROVEEDORES_RELLENO = [
    "Fontanería Ejemplo SL", "Electricidad Muestra SL", "Reformas Genéricas SL",
    "Cerrajería Prototipo SL", "Ascensores Ficticios SA", "Impermeabilizaciones Modelo SL",
    "Pinturas Estándar SL", "Jardinería Genérica SL", "Limpiezas Modelo SA", "Carpintería Ejemplo SL",
]
_CONCEPTOS_RELLENO = [
    "Reparación de avería", "Mantenimiento preventivo", "Suministro de material",
    "Revisión periódica", "Sustitución de pieza", "Instalación de equipo",
]


def _generar_relleno(rng: random.Random, n: int, offset: int) -> list[dict]:
    filas = []
    for i in range(n):
        id_ = f"r{offset + i:02d}"
        base = Decimal(rng.randrange(8000, 200000)) / 100  # 80.00 .. 2000.00
        tipo_iva = rng.choice(["21", "21", "21", "10", "4"])  # 21% predominante, como en la realidad
        cuota = (base * Decimal(tipo_iva) / 100).quantize(Decimal("0.01"))
        total = base + cuota
        letra_org = rng.choice("ABH")
        siete_digitos = f"{rng.randrange(0, 10_000_000):07d}"
        campos = _base(
            id_, numero_factura=f"F-2026-{id_}",
            proveedor_nombre=rng.choice(_PROVEEDORES_RELLENO),
            proveedor_nif=generar_cif_valido(letra_org, siete_digitos),
            concepto_resumen=rng.choice(_CONCEPTOS_RELLENO),
            base_imponible=str(base), tipo_iva=tipo_iva, cuota_iva=str(cuota), total=str(total),
        )
        filas.append({
            "id": id_, "layout": rng.choice(list(LAYOUTS)), "campos": campos,
            "esperado_en_cola": False, "motivo_esperado": None,
            "nota": "Relleno generado: caso limpio, sin propiedad bajo prueba propia.",
        })
    return filas


def generar():
    DIR_PDF.mkdir(exist_ok=True)
    DATASET.parent.mkdir(exist_ok=True)
    rng = random.Random(SEED)
    casos = list(CASOS_MARCADOS) + _generar_relleno(rng, 19, offset=1)

    filas_dataset = []
    for caso in casos:
        pdf_path = DIR_PDF / f"{caso['id']}.pdf"
        especial = caso.get("especial")
        if especial == "ruidoso":
            construir_pdf_ruidoso(pdf_path, caso["campos"], seed=SEED)
        elif especial == "multipagina":
            construir_pdf_multipagina(pdf_path, caso["campos"])
        else:
            construir_pdf(pdf_path, caso["campos"], layout=caso["layout"])

        # Autocontrol: para los casos con campos_verdad limpios evaluables por las 4 reglas
        # deterministas (se excluyen duplicado -- lo detecta el UNIQUE de Postgres, no
        # validar_factura -- y ruidoso -- su "campos" son los reales, el caso de prueba es la
        # imagen, no estos valores), el resultado de validar_factura() debe coincidir con
        # motivo_esperado. Si el dataset se contradice a sí mismo, esto falla aquí y no 30
        # facturas después en el eval.
        if caso["motivo_esperado"] not in ("duplicado", "confianza baja"):
            errores = validar_factura(caso["campos"])
            tiene_error_esperado = caso["motivo_esperado"] is not None
            assert bool(errores) == tiene_error_esperado, (
                f"{caso['id']}: validar_factura()={errores!r} no coincide con "
                f"motivo_esperado={caso['motivo_esperado']!r}")

        fila = {
            "id": caso["id"], "pdf_origen": f"{caso['id']}.pdf",
            "campos_verdad": caso["campos"], "esperado_en_cola": caso["esperado_en_cola"],
            "motivo_esperado": caso["motivo_esperado"], "nota": caso["nota"],
        }
        if "canned_override" in caso:
            fila["canned_override"] = caso["canned_override"]
        filas_dataset.append(fila)

    with open(DATASET, "w", encoding="utf-8") as f:
        for fila in filas_dataset:
            f.write(json.dumps(fila, ensure_ascii=False) + "\n")
    print(f"{len(filas_dataset)} facturas generadas en {DIR_PDF}/, verdad en {DATASET}")


if __name__ == "__main__":
    generar()
