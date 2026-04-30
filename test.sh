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

pip install --no-cache-dir faster-whisper

pip install --no-cache-dir -r "$MAIN_DIR/custom-server/web/requirements.txt" --ignore-installed

# Replace CPU-only onnxruntime (installed as silero_vad/piper-tts dep) with the
# Jetson CUDA build so Silero VAD and Piper TTS can use the GPU.
pip uninstall -y onnxruntime onnxruntime-gpu 2>/dev/null || true
pip install --no-cache-dir \
    --extra-index-url https://pypi.jetson-ai-lab.dev \
    onnxruntime-gpu

cp -r "$MAIN_DIR/custom-server/server_overrides/." "$SERVER_DIR/"

mkdir -p "$REPO_ROOT/data"
mkdir -p "$SERVER_DIR/data"
mkdir -p "$SERVER_DIR/tmp"

# Download Piper TTS model if not already present
PIPER_DIR="/data/models/piper"
mkdir -p "$PIPER_DIR"
PIPER_MODEL="es_ES-davefx-medium"
PIPER_BASE="https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_ES/davefx/medium"
if [ ! -f "$PIPER_DIR/$PIPER_MODEL.onnx" ]; then
    echo "Downloading Piper TTS model (this may take a minute)..."
    wget -q --show-progress -O "$PIPER_DIR/$PIPER_MODEL.onnx" "$PIPER_BASE/$PIPER_MODEL.onnx"
fi
if [ ! -f "$PIPER_DIR/$PIPER_MODEL.onnx.json" ]; then
    echo "Downloading Piper TTS model config..."
    wget -q -O "$PIPER_DIR/$PIPER_MODEL.onnx.json" "$PIPER_BASE/$PIPER_MODEL.onnx.json"
fi

export PYTHONUNBUFFERED=1
export PYTHONDONTWRITEBYTECODE=1
export DATA_DIR="$REPO_ROOT/data"
export SERVER_DATA_DIR="$SERVER_DIR/data"
export FLASK_PORT=5001
export WS_PORT=8000
export HTTP_PORT=8003
if [ -z "$SERVER_HOST" ] || [ "$SERVER_HOST" = "localhost" ]; then
    export SERVER_HOST=$(hostname -I | awk '{print $1}' 2>/dev/null || echo "127.0.0.1")
fi
export NVIDIA_VISIBLE_DEVICES=all
export NVIDIA_DRIVER_CAPABILITIES=compute,utility

# Reset database so the Spanish defaults in seed.py take effect.
# Remove this line after your agents are configured.
rm -f "$DATA_DIR/custom_server.db"

# Flask auto-starts xiaozhi-server 5 s after binding (see routes/server_control.py).
# Use the web UI at http://localhost:5001/server/status to start/stop/restart it.
cd "$FLASK_DIR" && python app.py