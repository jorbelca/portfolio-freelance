#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Envía el corpus etiquetado de eval/dataset.jsonl al SMTP de pruebas (GreenMail).

La cabecera Message-ID se fija al valor del campo `message_id` del dataset. Esa es la clave
de idempotencia del workflow: reenviar el corpus dos veces no debe crear fichas duplicadas.

Uso:
    python3 seed_emails.py                 # envía los 28 correos
    python3 seed_emails.py --only e07      # envía uno solo (útil al grabar la demo)
    python3 seed_emails.py --dry-run       # construye los mensajes sin tocar la red
"""

import argparse
import json
import smtplib
import sys
import time
from email.message import EmailMessage
from pathlib import Path

DATASET = Path(__file__).resolve().parent / "eval" / "dataset.jsonl"
DESTINO = "triage@despacho.local"
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


def construir(registro):
    """Convierte un registro del dataset en un EmailMessage listo para enviar.

    EmailMessage codifica solo las cabeceras con acentos (RFC 2047); no hay que
    pre-codificar el asunto a mano.
    """
    msg = EmailMessage()
    msg["Message-ID"] = registro["message_id"]
    msg["From"] = registro["from"]
    msg["To"] = DESTINO
    msg["Subject"] = registro["subject"]
    msg.set_content(registro["body"])
    return msg


def main(argv=None):
    p = argparse.ArgumentParser(description="Envía el corpus de triage al SMTP de pruebas.")
    p.add_argument("--host", default=HOST_POR_DEFECTO, help=f"SMTP (por defecto {HOST_POR_DEFECTO})")
    p.add_argument("--port", type=int, default=PUERTO_POR_DEFECTO,
                   help=f"Puerto SMTP (por defecto {PUERTO_POR_DEFECTO})")
    p.add_argument("--only", metavar="ID", help="Envía solo el correo con ese id, p. ej. e07")
    p.add_argument("--dry-run", action="store_true",
                   help="Construye los mensajes y comprueba el corpus sin conectar al SMTP")
    p.add_argument("--dataset", type=Path, default=DATASET, help="Ruta al dataset.jsonl")
    p.add_argument("--delay", type=float, default=0.0, metavar="SEG",
                   help="Segundos de espera entre correos. El clasificador gasta ~3.000 tokens "
                        "de entrada por correo; con una cuota de 16.000 tokens/min hacen falta "
                        "unos 15 s para no chocar con el 429 del proveedor.")
    args = p.parse_args(argv)

    registros = cargar(args.dataset)
    total_corpus = len(registros)

    if args.only:
        registros = [r for r in registros if r["id"] == args.only]
        if not registros:
            print(f"error: no hay ningún correo con id '{args.only}' en {args.dataset}",
                  file=sys.stderr)
            return 2

    mensajes = [(r, construir(r)) for r in registros]

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

    # --- envío ---------------------------------------------------------------
    prefijo = "[dry-run] " if args.dry_run else ""
    if args.dry_run:
        for registro, msg in mensajes:
            print(f"{prefijo}{registro['id']}  {registro['categoria_esperada']:<22}"
                  f"{registro['subject']}")
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
                print(f"{registro['id']}  {registro['categoria_esperada']:<22}"
                      f"{registro['subject']}", flush=True)
    except OSError as err:
        print(f"error: no se pudo conectar a {args.host}:{args.port} ({err}). "
              f"¿Está levantado GreenMail? docker compose up -d greenmail", file=sys.stderr)
        return 1

    print(f"\nEnviados {len(mensajes)} correos a {DESTINO} vía {args.host}:{args.port}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
