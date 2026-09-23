#!/usr/bin/env python3
"""El correo del lunes: alertas arriba, resumen debajo, enlace al panel al final.
Todos los números salen de bi_staging (SQL ya corrido por conciliar.py) -- este script
no calcula nada, solo los lee y los redacta.

El LLM es opcional y está APAGADO por defecto (INFORME_LLM=0). Si se activa, añade un
único párrafo de prosa sobre los números ya calculados, marcado como [LLM] en el propio
correo. No puede sumar, agregar, ni explicar un descuadre concreto -- si el modelo falla
o no hay clave, el correo sale igual sin ese párrafo (degradar, no romper).

Uso: python3 informe.py [--destino correo@dominio]
"""
import argparse
from html import escape
import os
from email.message import EmailMessage
from email.utils import make_msgid

import entorno  # noqa: F401  -- carga ../1/.env al importar
import psycopg2


def _dsn():
    password = os.environ.get("PGPASSWORD") or os.environ.get("DB_POSTGRESDB_PASSWORD", "")
    return (f"host={os.environ.get('PGHOST', '127.0.0.1')} port={os.environ.get('PGPORT', '5432')} "
            f"dbname={os.environ.get('PGDATABASE', 'n8n')} user={os.environ.get('PGUSER', 'n8n_user')} "
            f"password={password}")


ETIQUETAS = {
    "sin_facturar": "pedidos sin facturar pasado el plazo",
    "sin_pedido": "facturas sin pedido en el ERP",
    "importe": "facturas con importe distinto al pedido",
    "duplicado": "pedidos facturados dos veces",
    "unidades": "pedidos con discrepancia de unidades (ERP vs. comercial)",
}


def leer_numeros(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT count(*), coalesce(sum(importe), 0) FROM bi_staging.pedidos")
        n_pedidos, importe_total = cur.fetchone()

        cur.execute("SELECT count(*) FROM bi_staging.facturas")
        n_facturas = cur.fetchone()[0]

        cur.execute("SELECT tipo, count(*) FROM bi_staging.descuadres GROUP BY tipo ORDER BY tipo")
        por_tipo = dict(cur.fetchall())

        cur.execute("SELECT pedido_id, tipo, detalle FROM bi_staging.descuadres ORDER BY tipo, pedido_id")
        filas = cur.fetchall()

    return {
        "n_pedidos": n_pedidos,
        "importe_total": float(importe_total),
        "n_facturas": n_facturas,
        "por_tipo": por_tipo,
        "total_descuadres": sum(por_tipo.values()),
        "filas": filas,
    }


def _parrafo_llm(numeros):
    """Una llamada, solo prosa sobre los números ya calculados. Si falla o no hay
    clave, no rompe el correo -- simplemente no añade el párrafo."""
    # Gemini AI Studio primero: el pool :free de OpenRouter filtra razonamiento crudo sin
    # limpiar en la respuesta (visto en pruebas de esta demo, misma lección que la Demo 5).
    clave = os.environ.get("GEMINI_API_KEY") or os.environ.get("OPENROUTER_API_KEY")
    if not clave:
        return None
    try:
        from openai import OpenAI
        if os.environ.get("GEMINI_API_KEY"):
            base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
            modelo = "gemini-3.6-flash"
        else:
            base_url = "https://openrouter.ai/api/v1"
            modelo = "nvidia/nemotron-3-super-120b-a12b:free"
        cliente = OpenAI(base_url=base_url, api_key=clave)
        prompt = (
            "Redacta UN párrafo breve (máx. 3 frases) para un informe semanal de reporting, en "
            "español, tono directo de negocio. Usa EXCLUSIVAMENTE estos números ya calculados, "
            "no inventes ni agregues ninguno nuevo, no expliques descuadres concretos:\n"
            f"- pedidos totales: {numeros['n_pedidos']}\n"
            f"- facturas totales: {numeros['n_facturas']}\n"
            f"- descuadres detectados: {numeros['total_descuadres']}\n"
            f"- desglose: {numeros['por_tipo']}\n"
        )
        resp = cliente.chat.completions.create(
            model=modelo, messages=[{"role": "user", "content": prompt}],
            max_tokens=4096, temperature=0, timeout=30)
        razon = getattr(resp.choices[0], "finish_reason", "?") if resp.choices else "?"
        print(f"  [LLM] finish_reason={razon}")
        if resp.choices and resp.choices[0].message.content:
            return resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"  [LLM] párrafo omitido: {type(e).__name__}: {str(e)[:120]}")
    return None


def _html_email(numeros, panel_url, titular, porcentaje, parrafo):
    total = numeros["total_descuadres"]
    color = "#b42318" if total else "#067647"
    alertas = "".join(
        f"<li><strong>{n}</strong> {escape(ETIQUETAS.get(tipo, tipo))}</li>"
        for tipo, n in numeros["por_tipo"].items()
    ) or "<li>Sin descuadres esta semana.</li>"
    panel = ""
    if panel_url and "(pendiente)" not in panel_url:
        href = escape(panel_url, quote=True)
        panel = f'<p><a href="{href}" style="color:#1769aa;font-weight:700">Abrir el panel completo</a></p>'
    llm = f'<div style="margin-top:24px;padding:14px;background:#f5f7fa;border-radius:8px"><strong>Resumen:</strong> {escape(parrafo)}</div>' if parrafo else ""
    return f"""<!doctype html>
<html lang="es"><body style="margin:0;background:#eef2f7;font-family:Arial,sans-serif;color:#172b4d">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#eef2f7;padding:34px 0">
<tr><td align="center"><table role="presentation" width="700" cellspacing="0" cellpadding="0" style="max-width:700px;width:94%;background:#fff;border-radius:14px;overflow:hidden;box-shadow:0 4px 18px rgba(18,59,99,.10)">
<tr><td align="center" style="background:#123b63;padding:36px 34px 32px;color:#fff"><div style="font-size:12px;letter-spacing:2px;color:#b9d7f2">NUBEFORGE · REPORTING</div><h1 style="margin:12px 0 8px;font-size:28px;line-height:1.2">Informe semanal de conciliación</h1><div style="font-size:14px;color:#dbeafe">ERP · Comercial · Facturación</div></td></tr>
<tr><td style="padding:38px 44px 34px"><p style="margin:0 0 28px">Hola,</p>
<div style="border-left:5px solid {color};padding:18px 20px;background:#f8fafc;border-radius:0 9px 9px 0;text-align:center"><div style="font-size:11px;letter-spacing:1.5px;color:#64748b">TITULAR</div><div style="margin-top:8px;font-size:20px;line-height:1.35;font-weight:700;color:{color}">{escape(titular)}</div></div>
<h2 style="font-size:16px;text-align:center;margin:34px 0 14px;color:#123b63">Resumen ejecutivo</h2>
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:separate;border-spacing:8px 0"><tr>
<td width="25%" align="center" style="background:#eef6ff;border:1px solid #d7e8fb;border-radius:9px;padding:18px 6px"><div style="font-size:25px;font-weight:700;color:#123b63">{numeros['n_pedidos']}</div><div style="margin-top:5px;font-size:11px;letter-spacing:.4px;color:#52606d">PEDIDOS</div></td>
<td width="25%" align="center" style="background:#eef6ff;border:1px solid #d7e8fb;border-radius:9px;padding:18px 6px"><div style="font-size:25px;font-weight:700;color:#123b63">{numeros['n_facturas']}</div><div style="margin-top:5px;font-size:11px;letter-spacing:.4px;color:#52606d">FACTURAS</div></td>
<td width="25%" align="center" style="background:#fff4f2;border:1px solid #f7d5d0;border-radius:9px;padding:18px 6px"><div style="font-size:25px;font-weight:700;color:{color}">{total}</div><div style="margin-top:5px;font-size:11px;letter-spacing:.4px;color:#52606d">DESCUADRES</div></td>
<td width="25%" align="center" style="background:#eef6ff;border:1px solid #d7e8fb;border-radius:9px;padding:18px 6px"><div style="font-size:25px;font-weight:700;color:#123b63">{porcentaje:.1f}%</div><div style="margin-top:5px;font-size:11px;letter-spacing:.4px;color:#52606d">TASA</div></td>
</tr></table>
<div style="margin:18px 8px 0;padding:12px 16px;background:#f8fafc;border-radius:8px;text-align:center;font-size:13px;color:#52606d">Importe total en pedidos: <strong style="color:#172b4d">{numeros['importe_total']:,.2f} €</strong></div>
<div style="margin-top:34px;padding:20px 22px;background:#fff8e6;border:1px solid #f8e3ad;border-radius:10px"><h2 style="font-size:16px;margin:0 0 12px;color:#7a5412">Alertas detectadas</h2><ul style="margin:0;padding-left:22px;line-height:1.9;color:#344054">{alertas}</ul></div>
<div style="margin-top:24px;padding:18px 22px;background:#f4f8fc;border-radius:10px"><strong style="color:#123b63">Siguiente paso</strong><br><span style="display:block;margin-top:6px">{'Revisar las filas marcadas en la página DESCUADRES del informe.' if total else 'No hay acciones pendientes de conciliación esta semana.'}</span></div>
{llm}{panel}
<p style="margin:30px 0 0;text-align:center;font-size:12px;color:#718096">Generado automáticamente a partir de la conciliación SQL.</p>
</td></tr></table></td></tr></table></body></html>"""


def redactar(numeros, panel_url):
    total = numeros["total_descuadres"]
    porcentaje = total / numeros["n_pedidos"] * 100 if numeros["n_pedidos"] else 0
    titular = (f"Se han detectado {total} descuadres que requieren revisión."
               if total else "No se han detectado descuadres esta semana.")
    lineas = [
        "Hola,",
        "",
        "INFORME SEMANAL DE CONCILIACIÓN",
        "ERP · Comercial · Facturación",
        "",
        "TITULAR",
        titular,
        "",
        "INDICADORES",
        f"- Pedidos analizados: {numeros['n_pedidos']}",
        f"- Facturas analizadas: {numeros['n_facturas']}",
        f"- Importe total en pedidos: {numeros['importe_total']:,.2f} €",
        f"- Tasa de descuadre: {porcentaje:.1f}% de los pedidos",
        "",
        "ALERTAS",
    ]
    if not total:
        lineas.append("- Sin descuadres esta semana.")
    else:
        for tipo, n in numeros["por_tipo"].items():
            lineas.append(f"- {n} {ETIQUETAS.get(tipo, tipo)}")

    lineas += [
        "",
        "SIGUIENTE PASO",
        ("Revisar las filas marcadas en la página DESCUADRES del informe."
         if total else "No hay acciones pendientes de conciliación esta semana."),
        "",
        "Este correo se genera automáticamente a partir de la conciliación SQL.",
    ]

    parrafo = None
    if os.environ.get("INFORME_LLM", "0") == "1":
        parrafo = _parrafo_llm(numeros)
        if parrafo:
            lineas += ["", "[LLM] " + parrafo]

    if panel_url and "(pendiente)" not in panel_url:
        lineas += ["", f"Panel completo (detalle fila a fila): {panel_url}"]
    cuerpo = "\n".join(lineas)
    asunto = (f"Informe semanal — {numeros['total_descuadres']} descuadres detectados"
              if numeros["total_descuadres"] else "Informe semanal — todo cuadra")
    return asunto, cuerpo, _html_email(numeros, panel_url, titular, porcentaje, parrafo)


def enviar(asunto, cuerpo, cuerpo_html, destino):
    msg = EmailMessage()
    msg["Message-ID"] = make_msgid(domain="nubeforge.local")
    msg["From"] = "reporting@nubeforge.local"
    msg["To"] = destino
    msg["Subject"] = asunto
    msg.set_content(cuerpo)
    msg.add_alternative(cuerpo_html, subtype="html")
    try:
        import smtplib
        # OJO: no reutilizar la SMTP_HOST genérica de ../1/.env -- esa vale "greenmail"
        # (el nombre dentro de la red de docker compose, lo usa n8n) y no resuelve desde
        # el Mac. Desde el host el mismo GreenMail se ve en 127.0.0.1:3025.
        with smtplib.SMTP(os.environ.get("INFORME_SMTP_HOST", "127.0.0.1"),
                          int(os.environ.get("INFORME_SMTP_PORT", "3025")), timeout=10) as s:
            s.send_message(msg)
        return True
    except Exception as e:
        print(f"AVISO: no se pudo enviar por SMTP ({type(e).__name__}: {e}). Correo generado igual:\n")
        print(cuerpo)
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--destino", default=os.environ.get("INFORME_DESTINO", "direccion@nubeforge.local"))
    ap.add_argument("--panel-url", default=os.environ.get("POWERBI_URL", ""))
    args = ap.parse_args()

    conn = psycopg2.connect(_dsn())
    try:
        numeros = leer_numeros(conn)
    finally:
        conn.close()

    asunto, cuerpo, cuerpo_html = redactar(numeros, args.panel_url)
    print(f"Asunto: {asunto}\n\n{cuerpo}\n")
    enviado = enviar(asunto, cuerpo, cuerpo_html, args.destino)
    if enviado:
        print(f"OK: enviado a {args.destino} (GreenMail, ver http://localhost:8081)")


if __name__ == "__main__":
    main()
