"""Cliente de modelo — adaptado de 5/grafo_leads.py.

Se usa en UN solo sitio con juicio: interpretar el relato libre (interpretar.py).
La redacción de la carta también llama al modelo, pero solo para prosa: el importe
y el artículo van fijados por el motor, no los decide el modelo.

Claves (en ../1/.env): RECLAMACIONES_LLM_API_KEY | GEMINI_API_KEY | OPENROUTER_API_KEY
Modelo: RECLAMACIONES_MODELO (por defecto un :free de OpenRouter)
Base URL alternativa: RECLAMACIONES_LLM_BASE_URL (p. ej. la API OpenAI-compatible de Gemini)
"""

from __future__ import annotations

import os
import time

import entorno  # noqa: F401  -- carga ../1/.env al importar


def api_key() -> str | None:
    return (os.environ.get("RECLAMACIONES_LLM_API_KEY")
            or os.environ.get("GEMINI_API_KEY")
            or os.environ.get("OPENROUTER_API_KEY"))


def modelo() -> str:
    return os.environ.get("RECLAMACIONES_MODELO", "nvidia/nemotron-3-super-120b-a12b:free")


# Último modelo que devolvió respuesta utilizable (puede ser el de reserva si el
# primario agotó los reintentos). Lo lee la UI para no mentir sobre qué respondió.
_ultimo_modelo = ""


def ultimo_modelo() -> str:
    return _ultimo_modelo


def proveedor() -> str:
    base = os.environ.get("RECLAMACIONES_LLM_BASE_URL", "https://openrouter.ai/api/v1")
    return base.split("//", 1)[-1].split("/", 1)[0]


def llamar(prompt: str, *, json_mode: bool = True) -> str:
    """Una llamada al modelo con reintentos. temperatura 0 (determinista salvo
    variación del proveedor). Lanza RuntimeError si no hay respuesta utilizable."""
    key = api_key()
    if not key:
        raise RuntimeError(
            "Falta la clave del modelo (RECLAMACIONES_LLM_API_KEY / GEMINI_API_KEY / "
            "OPENROUTER_API_KEY en ../1/.env). Para medir solo el motor usa --sin-llm.")

    from openai import OpenAI  # import perezoso: --sin-llm no necesita openai

    try:
        from openai import APIError, BadRequestError
    except ImportError:  # versiones viejas del sdk
        APIError = Exception
        BadRequestError = ()

    client = OpenAI(
        base_url=os.environ.get("RECLAMACIONES_LLM_BASE_URL", "https://openrouter.ai/api/v1"),
        api_key=key)
    base_kwargs = dict(messages=[{"role": "user", "content": prompt}],
                       max_tokens=int(os.environ.get("RECLAMACIONES_MAX_TOKENS", "4096")),
                       temperature=0, timeout=int(os.environ.get("RECLAMACIONES_TIMEOUT", "120")))
    if json_mode and os.environ.get("RECLAMACIONES_JSON_MODE", "1") == "1":
        base_kwargs["response_format"] = {"type": "json_object"}

    # El tier gratis de OpenRouter cae de forma intermitente (429, 404 "Provider
    # returned error", 200 con choices=None). Reintentos con backoff y, tras agotar
    # el modelo primario, se prueba el de reserva (pool :free auto-enrutado).
    intentos = int(os.environ.get("RECLAMACIONES_REINTENTOS", "3"))
    backoff = int(os.environ.get("RECLAMACIONES_BACKOFF", "15"))
    modelos = [modelo()]
    fallback = os.environ.get("RECLAMACIONES_MODELO_FALLBACK", "openrouter/free")
    if fallback and fallback not in modelos:
        modelos.append(fallback)

    ultimo = ""
    for m in modelos:
        for i in range(intentos):
            try:
                resp = client.chat.completions.create(model=m, **base_kwargs)
            except BadRequestError as e:  # type: ignore[misc]
                raise RuntimeError(f"petición inválida al modelo {m}: {str(e)[:200]}") from e
            except APIError as e:  # 429, 5xx, 404 de proveedor, timeout, conexión
                ultimo = f"{type(e).__name__} ({m}): {str(e)[:120]}"
                time.sleep(backoff * (i + 1))
                continue
            # Un error de OpenRouter puede llegar como 200 con choices=None
            # (lección Demo 4 bug 1); sin esto resp.choices[0] tira TypeError críptico.
            if not getattr(resp, "choices", None):
                ultimo = f"sin choices ({m}): {getattr(resp, 'error', None) or str(resp)[:200]}"
                time.sleep(backoff * (i + 1))
                continue
            contenido = resp.choices[0].message.content
            if contenido and contenido.strip():
                global _ultimo_modelo
                _ultimo_modelo = m
                return contenido
            ultimo = f"vacío ({m}, finish_reason={getattr(resp.choices[0], 'finish_reason', '?')})"
            time.sleep(3 * (i + 1))
    raise RuntimeError(
        f"ningún modelo devolvió respuesta utilizable ({', '.join(modelos)}, "
        f"{intentos} intento(s) c/u): {ultimo}")
