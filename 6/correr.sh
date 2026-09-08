#!/bin/sh
# Ejecuta el agente sobre un relato, con las claves de ../1/.env exportadas.
# Uso:  ./correr.sh "Madrid-Nueva York, 4 h de retraso, problema técnico, ofrecen 250 €"
#       ./correr.sh --eval          (modo real sobre los 33 relatos del dataset)
#       ./correr.sh --eval-sin-llm  (solo el motor)
set -e
cd "$(dirname "$0")"

ENV1=../1/.env
[ -f "$ENV1" ] || { echo "Falta $ENV1"; exit 1; }
export OPENROUTER_API_KEY="$(grep -m1 '^OPENROUTER_API_KEY=' "$ENV1" | cut -d= -f2-)"
export GEMINI_API_KEY="$(grep -m1 '^GEMINI_API_KEY=' "$ENV1" | cut -d= -f2-)"

# OpenRouter (pool :free auto-enrutado) por defecto. RECLAMACIONES_GEMINI=1 para Gemini AI Studio.
if [ "$RECLAMACIONES_GEMINI" = "1" ] && [ -n "$GEMINI_API_KEY" ]; then
  export RECLAMACIONES_LLM_BASE_URL="https://generativelanguage.googleapis.com/v1beta/openai/"
  export RECLAMACIONES_LLM_API_KEY="$GEMINI_API_KEY"
  export RECLAMACIONES_MODELO="${RECLAMACIONES_MODELO:-gemini-3.6-flash}"
  export RECLAMACIONES_REINTENTOS="${RECLAMACIONES_REINTENTOS:-6}"
elif [ -n "$OPENROUTER_API_KEY" ]; then
  export RECLAMACIONES_LLM_BASE_URL="https://openrouter.ai/api/v1"
  export RECLAMACIONES_LLM_API_KEY="$OPENROUTER_API_KEY"
  export RECLAMACIONES_MODELO="${RECLAMACIONES_MODELO:-nvidia/nemotron-3-super-120b-a12b:free}"
  export RECLAMACIONES_REINTENTOS="${RECLAMACIONES_REINTENTOS:-6}"
fi

case "$1" in
  --eval)         exec python3 eval/run_eval.py ;;
  --eval-sin-llm) exec python3 eval/run_eval.py --sin-llm ;;
  --ui)           shift; exec python3 servidor.py "$@" ;;
  *)              exec python3 agente.py "$@" ;;
esac
