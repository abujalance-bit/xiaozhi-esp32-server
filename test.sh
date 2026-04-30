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
if [ -z "$SERVER_HOST" ] || [ "$SERVER_HOST" = "localhost" ]; then
    export SERVER_HOST=$(hostname -I | awk '{print $1}' 2>/dev/null || echo "127.0.0.1")
fi
export NVIDIA_VISIBLE_DEVICES=all
export NVIDIA_DRIVER_CAPABILITIES=compute,utility


# Flask auto-starts xiaozhi-server 5 s after binding (see routes/server_control.py).
# Use the web UI at http://localhost:5001/server/status to start/stop/restart it.
cd "$FLASK_DIR" && python app.py