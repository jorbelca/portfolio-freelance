#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Envía el corpus etiquetado de eval/dataset.jsonl al SMTP de pruebas (GreenMail).

Adaptado de 1/seed_emails.py (Demo A) al dataset de incidencias de fincas de la Demo B.

La cabecera Message-ID se fija al valor del campo `message_id` del dataset, verbatim. Esa es
la clave de idempotencia exacta del workflow (UNIQUE sobre incidencias.message_id en
init-fincas-tables.sql): reenviar el corpus dos veces no debe crear fichas duplicadas.

Los 3 casos "sin comunidad identificable" y los 4 administrativos del dataset se envían
igual que cualquier otro correo -- este script no filtra nada por `esperado_en_tabla`,
porque en la vida real el buzón de incidencias@fincas.local recibe exactamente ese tipo de
correo mezclado con incidencias técnicas reales; es el propio workflow el que decide qué
hacer con cada uno. El campo `esperado_en_tabla` solo lo usa eval/run_eval.py, no el envío.

Los 3 casos de deduplicación (i08, i09, i10) deben caer dentro de la ventana de 72h de
buscar_incidencia_raiz() (init-fincas-tables.sql). Este script no calcula fechas: al no
llevar --delay, o con un --delay corto, los tres llegan a Postgres con segundos de diferencia,
muy por debajo de cualquier ventana razonable. No hace falta más lógica que esa.

Uso:
    python3 seed_incidencias.py                    # envía los 45 correos
    python3 seed_incidencias.py --only i08          # envía uno solo (útil al grabar la demo)
    python3 seed_incidencias.py --dry-run           # construye los mensajes sin tocar la red
    python3 seed_incidencias.py --delay 15          # espera 15s entre correos (ver más abajo)
"""

import argparse
import json
import smtplib
import sys
import time
from email.message import EmailMessage
from pathlib import Path

DATASET = Path(__file__).resolve().parent / "eval" / "dataset.jsonl"
DESTINO = "incidencias@fincas.local"
HOST_POR_DEFECTO = "localhost"
PUERTO_POR_DEFECTO = 3025


def cargar(ruta):
    """Lee el JSONL línea a línea. Falla ruidosamente si alguna línea no parsea."""
    registros = []
    with ruta.open(encoding="utf-8") as f:
        for n, linea in enumerate(f, start=1):
            linea = linea.strip()
            if not linea:
                continue
            try:
                registros.append(json.loads(linea))
            except json.JSONDecodeError as err:
                raise SystemExit(f"{ruta}:{n}: JSON inválido: {err}")
    return registros


def construir(registro, destino=None):
    """Convierte un registro del dataset en un EmailMessage listo para enviar.

    EmailMessage codifica solo las cabeceras con acentos (RFC 2047); no hay que
    pre-codificar el asunto a mano.
    """
    msg = EmailMessage()
    msg["Message-ID"] = registro["message_id"]
    msg["From"] = registro["from"]
    msg["To"] = destino or DESTINO
    msg["Subject"] = registro["subject"]
    msg.set_content(registro["body"])
    return msg


def etiqueta_legible(registro):
    """Para el log de envío: imputacion_esperada puede ser None (casos administrativos
    o sin comunidad), así que no se puede formatear directamente como los 'e01 cliente_nuevo'
    de la Demo A sin que reviente en esos casos."""
    imputacion = registro["imputacion_esperada"] or "n/a"
    comunidad = registro["comunidad_id"] or "sin-comunidad"
    return f"{comunidad:<14}{imputacion}"


def main(argv=None):
    p = argparse.ArgumentParser(description="Envía el corpus de incidencias al SMTP de pruebas.")
    p.add_argument("--host", default=HOST_POR_DEFECTO, help=f"SMTP (por defecto {HOST_POR_DEFECTO})")
    p.add_argument("--port", type=int, default=PUERTO_POR_DEFECTO,
                    help=f"Puerto SMTP (por defecto {PUERTO_POR_DEFECTO})")
    p.add_argument("--only", metavar="ID", help="Envía solo el correo con ese id, p. ej. i08")
    p.add_argument("--to", metavar="BUZON", default=DESTINO,
                    help=f"Buzón destino (por defecto {DESTINO}). Tiene que ser el mismo que lee "
                         "la credencial IMAP del trigger de B1, o el workflow no ve nada.")
    p.add_argument("--dry-run", action="store_true",
                    help="Construye los mensajes y comprueba el corpus sin conectar al SMTP")
    p.add_argument("--dataset", type=Path, default=DATASET, help="Ruta al dataset.jsonl")
    p.add_argument("--delay", type=float, default=0.0, metavar="SEG",
                    help="Segundos de espera entre correos. El clasificador gasta ~3.000 tokens "
                         "de entrada por incidencia; con una cuota gratuita de 16.000 tokens/min "
                         "hacen falta unos 15s entre envíos para no chocar con el 429 del "
                         "proveedor en una tirada completa de los 45 correos. Los 3 correos del "
                         "cluster de deduplicación (i08/i09/i10) siguen cayendo dentro de la "
                         "ventana de 72h de buscar_incidencia_raiz() aunque uses --delay 15: 45 "
                         "segundos de diferencia entre el primero y el tercero no es problema.")
    args = p.parse_args(argv)

    registros = cargar(args.dataset)
    total_corpus = len(registros)

    if args.only:
        registros = [r for r in registros if r["id"] == args.only]
        if not registros:
            print(f"error: no hay ningún correo con id '{args.only}' en {args.dataset}",
                  file=sys.stderr)
            return 2

    mensajes = [(r, construir(r, args.to)) for r in registros]

    # --- comprobación ejecutable (solo en dry-run) ---------------------------
    if args.dry_run:
        if not args.only:
            assert len(mensajes) == total_corpus, (
                f"{len(mensajes)} mensajes construidos frente a {total_corpus} líneas del dataset")
        ids = [msg["Message-ID"] for _, msg in mensajes]
        assert all(ids), "algún mensaje se construyó sin cabecera Message-ID"
        assert len(set(ids)) == len(ids), (
            f"Message-ID duplicados: {sorted(i for i in set(ids) if ids.count(i) > 1)}")
        for registro, msg in mensajes:
            assert msg["Message-ID"] == registro["message_id"], (
                f"{registro['id']}: Message-ID alterado al construir el mensaje")
        # Los tres casos de deduplicación deben existir y compartir elemento_esperado.
        dedup_raiz = [r for r in registros if r["id"] == "i08"]
        dedup_hijas = [r for r in registros if r.get("duplicado_de") == "i08"]
        if not args.only:
            assert len(dedup_raiz) == 1, "falta la raíz del cluster de deduplicación (i08)"
            assert len(dedup_hijas) == 2, (
                f"se esperaban 2 hijas de deduplicación (duplicado_de=i08), hay {len(dedup_hijas)}")
            elementos = {dedup_raiz[0]["elemento_esperado"]} | {h["elemento_esperado"] for h in dedup_hijas}
            assert elementos == {"bajante"}, (
                f"el cluster de deduplicación debería compartir elemento_esperado='bajante', hay {elementos}")

    # --- envío ---------------------------------------------------------------
    prefijo = "[dry-run] " if args.dry_run else ""
    if args.dry_run:
        for registro, msg in mensajes:
            print(f"{prefijo}{registro['id']:<5}{etiqueta_legible(registro)}  {registro['subject']}")
        print(f"\nOK: {len(mensajes)} mensajes construidos, "
              f"{len(set(m['Message-ID'] for _, m in mensajes))} Message-ID únicos, "
              f"{total_corpus} líneas en {args.dataset.name}")
        return 0

    try:
        with smtplib.SMTP(args.host, args.port) as smtp:
            for i, (registro, msg) in enumerate(mensajes):
                if args.delay and i:
                    time.sleep(args.delay)
                smtp.send_message(msg)
                print(f"{registro['id']:<5}{etiqueta_legible(registro)}  {registro['subject']}", flush=True)
    except OSError as err:
        print(f"error: no se pudo conectar a {args.host}:{args.port} ({err}). "
              f"¿Está levantado GreenMail? docker compose up -d greenmail", file=sys.stderr)
        return 1

    print(f"\nEnviados {len(mensajes)} correos a {args.to} vía {args.host}:{args.port}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
