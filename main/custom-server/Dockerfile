# Build context must be the main/ directory:
#   docker build -f custom-server/Dockerfile -t xiaozhi-custom-server .
# Or use docker-compose from within custom-server/:
#   docker compose up --build
#
# ── Base image ──────────────────────────────────────────────────────────────────
# Uses dusty-nv/jetson-containers as base to get PyTorch + CUDA for Jetson.
# Find your local tag: docker images | grep framepack
# Then set the build arg: docker build --build-arg BASE_IMAGE=dustynv/framepack:<tag> ...
# Or override in docker-compose.yml (see args: section).
ARG BASE_IMAGE=dustynv/framepack:r36.4.0
FROM ${BASE_IMAGE}

# ── System dependencies ─────────────────────────────────────────────────────────
# Most Python/CUDA packages are already in the base image.
# We only add system libraries and tools the base does not include.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libopus-dev \
    libopus0 \
    ffmpeg \
    supervisor \
    espeak-ng \
    espeak-ng-data \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── 1. Install xiaozhi-server Python dependencies ──────────────────────────────
# The base image already ships an optimised Jetson build of PyTorch/torchaudio.
# Pinning torch==2.2.2 from requirements.txt would DOWNGRADE it and break CUDA,
# so those two lines are excluded here.
COPY xiaozhi-server/requirements.txt /tmp/server-requirements.txt
RUN grep -Ev '^(torch|torchaudio)==' /tmp/server-requirements.txt \
    | pip install --no-cache-dir -r /dev/stdin

# ── 2. Install Piper TTS without overwriting onnxruntime-gpu ───────────────────
# piper-tts declares onnxruntime (CPU) as a dependency, which would replace the
# GPU-enabled build already present in the base image.
# We install the phonemizer separately, then piper itself with --no-deps.
RUN pip install --no-cache-dir piper-phonemize-cross && \
    pip install --no-cache-dir piper-tts --no-deps

# ── 3. Copy xiaozhi-server source ───────────────────────────────────────────────
COPY xiaozhi-server/ /app/server/

# ── 4. Apply custom-server overrides (GPU-aware providers) ──────────────────────
COPY custom-server/server_overrides/ /app/server/

# ── 5. Install Flask web app dependencies ───────────────────────────────────────
COPY custom-server/web/requirements.txt /tmp/web-requirements.txt
RUN pip install --no-cache-dir -r /tmp/web-requirements.txt

# ── 6. Copy Flask web app ───────────────────────────────────────────────────────
COPY custom-server/web/ /app/web/

# ── 7. Copy runtime files ───────────────────────────────────────────────────────
COPY custom-server/entrypoint.sh /app/entrypoint.sh
COPY custom-server/supervisord.conf /etc/supervisor/conf.d/supervisord.conf

RUN chmod +x /app/entrypoint.sh

# Persistent volumes (models come from /data/models host bind-mount, not a volume)
VOLUME ["/app/data", "/app/server/data"]

# Ports: Flask UI (5001), WebSocket server (8000), HTTP server (8003)
EXPOSE 5001 8000 8003

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DATA_DIR=/app/data \
    SERVER_DATA_DIR=/app/server/data \
    FLASK_PORT=5001 \
    WS_PORT=8000 \
    HTTP_PORT=8003 \
    SERVER_HOST=localhost \
    # Tell PyTorch / CUDA where to find libraries on Jetson
    NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility

ENTRYPOINT ["/app/entrypoint.sh"]
