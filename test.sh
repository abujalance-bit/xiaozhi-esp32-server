#!/usr/bin/env bash
set -e

# Derive all paths from this script's location so it works from any clone
# directory: /opt/xiaozhi-esp32-server, /data/xiaozhi-esp32-server, etc.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MAIN_DIR="$REPO_ROOT/main"
SERVER_DIR="$MAIN_DIR/xiaozhi-server"
FLASK_DIR="$MAIN_DIR/custom-server/web"

sudo apt-get update && sudo apt-get install -y \
    libopus-dev \
    libopus0 \
    ffmpeg \
    espeak-ng \
    espeak-ng-data

grep -Ev '^(torch|torchaudio)==' "$SERVER_DIR/requirements.txt" \
    | pip install --no-cache-dir -r /dev/stdin

pip install --no-cache-dir piper-phonemize-cross
pip install --no-cache-dir piper-tts --no-deps

pip install --no-cache-dir -r "$MAIN_DIR/custom-server/web/requirements.txt" --ignore-installed

cp -r "$MAIN_DIR/custom-server/server_overrides/." "$SERVER_DIR/"

mkdir -p "$REPO_ROOT/data"
mkdir -p "$SERVER_DIR/data"

export PYTHONUNBUFFERED=1
export PYTHONDONTWRITEBYTECODE=1
export DATA_DIR="$REPO_ROOT/data"
export SERVER_DATA_DIR="$SERVER_DIR/data"
export FLASK_PORT=5001
export WS_PORT=8000
export HTTP_PORT=8003
export SERVER_HOST="${SERVER_HOST:-localhost}"
export NVIDIA_VISIBLE_DEVICES=all
export NVIDIA_DRIVER_CAPABILITIES=compute,utility

cat > "$SERVER_DIR/data/.config.yaml" <<'EOF'
server:
  ip: 0.0.0.0
  port: 8000
  http_port: 8003
  websocket: ws://192.168.1.72:8000/xiaozhi/v1/
  vision_explain: http://192.168.1.72:8003/mcp/vision/explain
  timezone_offset: +1

selected_module:
  LLM: OllamaLLM
  TTS: EdgeTTS

LLM:
  OllamaLLM:
    base_url: http://localhost:11434
    model_name: qwen3.5:9b

ASR:
  FunASR:
    language: auto

TTS:
  EdgeTTS:
    voice: es-ES-AlvaroNeural

prompt: |
  Eres un asistente de voz llamado Xiaozhi.
  IMPORTANTE: Responde SIEMPRE en español, sin excepción.
  Responde con frases muy cortas, máximo 2 frases por respuesta.
  Nunca uses chino ni ningún otro idioma.
EOF

(cd "$SERVER_DIR" && python app.py) &
cd "$FLASK_DIR" && python app.py