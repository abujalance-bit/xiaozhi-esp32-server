# Build context must be the main/ directory:
#   docker build -f custom-server/Dockerfile -t custom-server .
# Or use docker-compose from within custom-server/:
#   docker compose up --build

FROM python:3.10-slim

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libopus-dev \
    libopus0 \
    ffmpeg \
    supervisor \
    espeak-ng \
    espeak-ng-data \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── 1. Install xiaozhi-server Python dependencies ──────────────────────────
COPY xiaozhi-server/requirements.txt /tmp/server-requirements.txt
RUN pip install --no-cache-dir -r /tmp/server-requirements.txt

# ── 2. Install Piper TTS ────────────────────────────────────────────────────
# piper-tts includes its own onnxruntime; arm64 wheels are available on PyPI
RUN pip install --no-cache-dir piper-tts

# ── 3. Copy xiaozhi-server source ───────────────────────────────────────────
COPY xiaozhi-server/ /app/server/

# ── 4. Apply custom-server overrides (new providers, modified configs) ──────
COPY custom-server/server_overrides/ /app/server/

# ── 5. Install Flask web app dependencies ───────────────────────────────────
COPY custom-server/web/requirements.txt /tmp/web-requirements.txt
RUN pip install --no-cache-dir -r /tmp/web-requirements.txt

# ── 6. Copy Flask web app ───────────────────────────────────────────────────
COPY custom-server/web/ /app/web/

# ── 7. Copy runtime files ───────────────────────────────────────────────────
COPY custom-server/entrypoint.sh /app/entrypoint.sh
COPY custom-server/supervisord.conf /etc/supervisor/conf.d/supervisord.conf

RUN chmod +x /app/entrypoint.sh

# Persistent volumes
VOLUME ["/app/data", "/app/server/data", "/app/server/models"]

# Ports: Flask UI (5001), WebSocket server (8000), HTTP server (8003)
EXPOSE 5001 8000 8003

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DATA_DIR=/app/data \
    SERVER_DATA_DIR=/app/server/data \
    FLASK_PORT=5001 \
    WS_PORT=8000 \
    HTTP_PORT=8003 \
    SERVER_HOST=localhost

ENTRYPOINT ["/app/entrypoint.sh"]
