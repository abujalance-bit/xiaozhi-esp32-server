# Xiaozhi Custom Server

A self-contained, single-container deployment of the Xiaozhi ESP32 voice assistant server
for the **NVIDIA Jetson AGX Orin (64 GB, ARM64)**. Replaces the original Java backend and
Vue.js frontend with a lightweight Flask + SQLite stack, and defaults to fully local,
offline-capable AI services.

---

## What's Inside

| Component | Description |
|---|---|
| **xiaozhi-server** | WebSocket AI engine (Python) — upstream source, unmodified |
| **Flask web UI** | Browser-based admin panel replacing the Java manager-api + Vue frontend |
| **SQLite** | Embedded database — no MySQL or Redis required |
| **Piper TTS** | Offline text-to-speech, ARM64-native, CPU-only |
| **Ollama LLM / VLLM** | Local LLM and vision model via your existing Ollama instance |

---

## Networking

The container uses **`--network host`**, sharing the Jetson's network stack directly.

- **Ollama** is reachable at `localhost:11434` — no Docker network setup needed.
- **All services bind on `0.0.0.0`** — accessible from any network interface.

| Service | Port | Purpose |
|---|---|---|
| Flask web UI | `5001` | Admin panel and internal config API |
| WebSocket server | `8000` | ESP32 device connection endpoint |
| HTTP server | `8003` | OTA firmware updates and vision API |

---

## Default Local Stack

| Service | Provider | Notes |
|---|---|---|
| VAD | Silero VAD | Bundled; runs on CPU |
| ASR | FunASR SenseVoiceSmall | Bundled model; runs on CPU |
| LLM | Ollama `gemma3:12b` | Via `localhost:11434` |
| VLLM | Ollama `minicpm-v` | Via `localhost:11434` |
| TTS | Piper TTS | CPU-only; model file downloaded separately |
| Memory | `mem_local_short` | LLM-based summarisation, no external service |
| Intent | `function_call` | Fast; requires function-call support in the LLM |

All providers can be switched to cloud alternatives through the web UI at any time
without rebuilding the image.

---

## Quick Start

### 1. Prerequisites

- Docker installed on the Jetson
- Ollama running and listening on `0.0.0.0:11434`
  ```bash
  ollama pull gemma3:12b
  ollama pull minicpm-v
  ```
- Working directory for all build commands: `main/` (the parent of `custom-server/`)

### 2. Build

```bash
cd main/
docker build -f custom-server/Dockerfile -t xiaozhi-custom-server .
```

The build context is `main/` so the Dockerfile can access both `xiaozhi-server/` and
`custom-server/` in a single pass.

### 3. Create Persistent Volumes

```bash
docker volume create custom-data          # SQLite DB and secrets
docker volume create custom-server-data   # xiaozhi-server runtime data
docker volume create custom-models        # AI model files (FunASR, Piper, …)
```

### 4. Run

```bash
docker run -d \
  --name xiaozhi-custom \
  --restart unless-stopped \
  --network host \
  -v custom-data:/app/data \
  -v custom-server-data:/app/server/data \
  -v custom-models:/app/server/models \
  -e SERVER_HOST=192.168.1.100 \
  -e DATA_DIR=/app/data \
  -e SERVER_DATA_DIR=/app/server/data \
  xiaozhi-custom-server
```

Set `SERVER_HOST` to your Jetson's LAN IP. This address is written into the WebSocket
and OTA URLs that are sent to ESP32 devices — it does not affect how the container
itself binds to ports.

#### Using Docker Compose instead

```bash
cd main/
SERVER_HOST=192.168.1.100 docker compose -f custom-server/docker-compose.yml up -d
```

### 5. First-Run Setup

1. Open `http://<JETSON_IP>:5001` in a browser.
2. You will be redirected to the setup page — create your admin account.
3. Default agents, model configs, and plugins are seeded automatically.

### 6. Download the Piper TTS Model

Piper model files must be placed in the `custom-models` volume before TTS will work.

```bash
MODELS_DIR=$(docker volume inspect custom-models --format '{{ .Mountpoint }}')/piper
mkdir -p "$MODELS_DIR"

# Default voice: English (US), Lessac, medium quality
curl -L "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx" \
     -o "$MODELS_DIR/en_US-lessac-medium.onnx"

curl -L "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json" \
     -o "$MODELS_DIR/en_US-lessac-medium.onnx.json"
```

Then restart the container:

```bash
# Plain Docker
docker restart xiaozhi-custom

# Docker Compose
docker compose -f custom-server/docker-compose.yml restart
```

Browse all available voices and samples at: <https://rhasspy.github.io/piper-samples/>

### 7. Connect Your ESP32

Flash your ESP32 with the xiaozhi firmware and configure:

- **WebSocket URL**: `ws://<JETSON_IP>:8000/xiaozhi/v1/`
- **OTA URL**: `http://<JETSON_IP>:8003/xiaozhi/ota/`

The first time an ESP32 connects with an unrecognised MAC address it is automatically
registered and assigned to the default agent. Go to **Devices** in the web UI to give
it a name or reassign it to a different agent.

---

## Web UI

| Page | URL | What it does |
|---|---|---|
| Dashboard | `/dashboard` | Overview: active devices, agent count, recent conversations |
| Agents | `/agents` | Create and configure agents — system prompt, provider selection, TTS voice |
| Devices | `/devices` | Register ESP32 devices and assign them to agents |
| Plugins | `/plugins` | Enable/disable function-calling plugins and enter API keys |
| Settings | `/settings` | System parameters and model configuration CRUD |

---

## Adding Another Piper Voice

1. Download the `.onnx` and `.onnx.json` files from the Piper voices repo into
   `$MODELS_DIR` (see above).
2. Open **Settings → Add Model** and create a new TTS entry:

```json
{
  "type": "piper_tts",
  "voice_model": "en_GB-alba-medium",
  "model_dir": "models/piper/",
  "output_dir": "tmp/",
  "length_scale": 1.0
}
```

Set the Model ID to anything you like (e.g. `PiperTTS-Alba`), then select it as the
TTS provider on any agent.

---

## Adding a Cloud LLM Provider

Any provider supported by the upstream xiaozhi-server can be added via
**Settings → Add Model**. The `type` field maps to a Python filename in
`core/providers/llm/<type>/<type>.py`.

Common examples:

| Provider | type | Notes |
|---|---|---|
| OpenAI | `openai` | Also works for DeepSeek, Together, any OpenAI-compatible API |
| Ollama | `ollama` | Default; points to `localhost:11434` |
| Gemini | `gemini` | Google Gemini API |

Example — DeepSeek via the OpenAI-compatible type:

```json
{
  "type": "openai",
  "model_name": "deepseek-chat",
  "api_key": "sk-...",
  "base_url": "https://api.deepseek.com/v1"
}
```

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `SERVER_HOST` | `localhost` | Jetson LAN IP advertised to ESP32 devices |
| `FLASK_PORT` | `5001` | Flask web UI port |
| `WS_PORT` | `8000` | WebSocket server port |
| `HTTP_PORT` | `8003` | HTTP server port (OTA + vision) |
| `DATA_DIR` | `/app/data` | SQLite DB and secrets |
| `SERVER_DATA_DIR` | `/app/server/data` | xiaozhi-server runtime data |

---

## Logs

```bash
# Follow Flask web UI log
docker exec xiaozhi-custom tail -f /var/log/supervisor/flask.log

# Follow xiaozhi-server log
docker exec xiaozhi-custom tail -f /var/log/supervisor/server.log

# All supervisor output
docker logs -f xiaozhi-custom
```

---

## Updating

```bash
cd main/
git pull
docker build --no-cache -f custom-server/Dockerfile -t xiaozhi-custom-server .
docker stop xiaozhi-custom && docker rm xiaozhi-custom
# Re-run the docker run command from step 4
```

Volumes are preserved across container recreations — no data is lost.

---

## Testing with test.html

`test.html` is a browser-based ESP32 emulator. It speaks the same WebSocket protocol
as the firmware so you can verify the full stack — LLM, TTS, ASR, device registration —
without physical hardware.

> **Browser requirement**: TTS playback and microphone recording use the
> [WebCodecs API](https://developer.mozilla.org/en-US/docs/Web/API/WebCodecs_API),
> available in **Chrome 94+** and **Edge 94+**. The text-send path works in any browser.

---

### Step 1 — Start the server

The server must be running before you open the test page. Pick whichever method applies:

```bash
# Docker (from main/)
SERVER_HOST=192.168.1.100 docker compose -f custom-server/docker-compose.yml up -d

# Bare Python (dev mode, from main/)
python xiaozhi-server/app.py &          # WebSocket :8000 + HTTP :8003
python custom-server/web/app.py &       # Flask UI :5001
```

Verify both services are up:

```bash
# Flask UI should return the login page
curl -s -o /dev/null -w "%{http_code}" http://localhost:5001/

# WebSocket server should accept a raw connection and send a text message
curl -s --include --no-buffer \
  -H "Upgrade: websocket" \
  -H "Connection: Upgrade" \
  -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" \
  -H "Sec-WebSocket-Version: 13" \
  http://localhost:8000/xiaozhi/v1/
```

Expected: Flask returns `200`, the WebSocket curl shows a `101 Switching Protocols` response.

---

### Step 2 — Serve the test page

```bash
cd main/custom-server
python -m http.server 8080
```

Open **http://localhost:8080/test.html** in Chrome or Edge.

---

### Step 3 — Connect

1. Set **WebSocket Server URL** to `ws://<SERVER_IP>:8000/xiaozhi/v1/`
   (use `localhost` if the server is on the same machine).
2. Leave **Device ID** as the auto-generated value — it persists across reloads in
   `localStorage` so the server always sees the same device.
3. Leave **Auth token** empty (auth is disabled by default).
4. Click **Connect**.

**Expected log output:**

```
→ sent  {"type":"hello","audio_params":{"format":"opus","sample_rate":24000,...}}
← recv  hello — session_id: a3f8c1d2…
```

The status dot turns green and the session ID appears. The device is automatically
registered in the Flask database on first connection — check **Devices** in the web UI
at `http://<SERVER_IP>:5001/devices`.

**If the connection fails:**
- `WebSocket error` — server is not running or the address/port is wrong.
- `Connection closed (code 1008)` — auth is enabled; add a token.
- `Connection closed (code 1000)` immediately after open — `device-id` was rejected
  (check server logs: `docker exec xiaozhi-custom tail -f /var/log/supervisor/server.log`).

---

### Step 4 — Test the LLM (text path)

Type a message in the input field and press **Enter** or click **Send**.

This sends `{"type":"listen","state":"detect","text":"your message"}`, which bypasses
audio encoding entirely and feeds the text directly to the LLM pipeline.

**Expected log sequence:**

```
→ sent  {"type":"listen","state":"detect","text":"tell me a joke"}
← recv  🗣 STT: tell me a joke
← recv  tts sentence_start — "Why don't scientists trust atoms?..."
← recv  🔊 Opus frame 120 B
← recv  🔊 Opus frame 118 B
         ... (one entry per 60 ms Opus frame)
← recv  tts stop
```

The LLM response text appears next to `tts sentence_start`. Audio plays through the
browser speakers as the frames arrive.

**If no STT/TTS messages appear:**
- Check the xiaozhi-server log for Python errors.
- Check that Ollama is running: `curl http://localhost:11434/api/tags`
- Check that the agent's LLM model config points to the correct Ollama model.

**If you see STT but no audio frames:**
- Piper TTS model files may be missing — follow [Step 6 in Quick Start](#6-download-the-piper-tts-model).
- Or the TTS provider is misconfigured — check **Settings → Model Configurations** in the web UI.

---

### Step 5 — Test TTS audio playback

Audio plays automatically when Opus frames arrive (Chrome/Edge only). If you hear
nothing despite seeing `🔊 Opus frame` lines in the log:

- Check browser audio: make sure the tab is not muted and your system volume is up.
- Click **Abort TTS** then send another message — this resets the audio decoder.
- Open the browser console (`F12`) and look for `AudioDecoder` errors.

---

### Step 6 — Test microphone input / ASR (Chrome/Edge only)

This tests the full speech path: mic → Opus encode → server VAD → ASR → LLM → TTS.

1. Click **🎤 Record**.
2. Allow microphone access when the browser prompts.
3. Speak a sentence clearly.
4. Click **⏹ Stop Recording**.

**Expected log sequence:**

```
ℹ info  Recording started — speak now, then click Stop
→ sent  {"type":"listen","state":"start","mode":"auto"}
→ sent  [binary] (Opus frames sent silently during recording)
→ sent  {"type":"listen","state":"stop"}
ℹ info  Recording stopped — waiting for server response…
← recv  🗣 STT: <your spoken words>
← recv  tts sentence_start — "<LLM response>"
← recv  🔊 Opus frame ...
← recv  tts stop
```

**If `🗣 STT` text is empty or missing:**
- FunASR model may not have downloaded yet (first-run download can take several minutes —
  check `docker logs xiaozhi-custom`).
- Speak more clearly or increase microphone input level.
- Confirm VAD is configured as `silero` in the agent's settings.

---

### Step 7 — Test Abort

While TTS audio is playing:

1. Click **✕ Abort TTS**.

**Expected:**

```
→ sent  {"type":"abort"}
← recv  tts stop
```

Playback stops immediately. The **Playing…** badge disappears.

---

### Quick reference — what each log color means

| Color | Direction | Meaning |
|---|---|---|
| Blue `→ sent` | Outbound | JSON message sent to server |
| Green `← recv` | Inbound JSON | Server response (hello, stt, tts state) |
| Gray `← recv` | Inbound binary | Opus audio frame from TTS |
| Yellow `ℹ info` | Local | Page-level status (connect, record start/stop) |
| Red `✖ error` | Local | Connection or codec error |

---

## Building, Uploading, and Deploying the Image

Use this workflow when you want to build the image once (e.g. on a dev machine or CI)
and deploy the pre-built image to the Jetson without re-building there.

### Option A — Build directly on the Jetson (simplest)

If you can clone the repo on the Jetson itself, just build natively:

```bash
git clone <repo-url>
cd xiaozhi-esp32-server/main/
docker build -f custom-server/Dockerfile -t xiaozhi-custom-server .
```

Skip to the [Run on Jetson](#run-on-the-jetson) section below.

---

### Option B — Cross-build on x86, push to a registry, pull on Jetson

#### 1. Enable multi-platform builds (one-time setup on your build machine)

```bash
docker buildx create --name multibuilder --use
docker buildx inspect --bootstrap
```

#### 2. Build and push for ARM64

Replace `yourdockerhubuser` with your Docker Hub username (or use `ghcr.io/<github-user>`
for GitHub Container Registry).

```bash
cd main/

docker buildx build \
  --platform linux/arm64 \
  -f custom-server/Dockerfile \
  -t yourdockerhubuser/xiaozhi-custom-server:latest \
  --push \
  .
```

The `--push` flag builds and uploads in one step. Omit it and add `--load` if you only
want the image locally (x86 only, not arm64 with `--load`).

**Tag with a version** instead of always overwriting `latest`:

```bash
docker buildx build \
  --platform linux/arm64 \
  -f custom-server/Dockerfile \
  -t yourdockerhubuser/xiaozhi-custom-server:1.0.0 \
  -t yourdockerhubuser/xiaozhi-custom-server:latest \
  --push \
  .
```

#### 3. Pull and run on the Jetson

SSH into the Jetson, then:

```bash
docker pull yourdockerhubuser/xiaozhi-custom-server:latest

docker run -d \
  --name xiaozhi-custom \
  --restart unless-stopped \
  --network host \
  -v custom-data:/app/data \
  -v custom-server-data:/app/server/data \
  -v custom-models:/app/server/models \
  -e SERVER_HOST=<JETSON_LAN_IP> \
  -e DATA_DIR=/app/data \
  -e SERVER_DATA_DIR=/app/server/data \
  yourdockerhubuser/xiaozhi-custom-server:latest
```

---

### Option C — Transfer via file (no registry required)

Useful for air-gapped environments or one-off transfers.

**On the build machine:**

```bash
cd main/

# Build for ARM64 and export to a tar file
docker buildx build \
  --platform linux/arm64 \
  -f custom-server/Dockerfile \
  -o type=docker,dest=xiaozhi-custom-server.tar \
  .

# Compress (the uncompressed image can be 3–5 GB)
gzip xiaozhi-custom-server.tar

# Copy to the Jetson
scp xiaozhi-custom-server.tar.gz user@<JETSON_IP>:~
```

**On the Jetson:**

```bash
# Load the image
docker load < xiaozhi-custom-server.tar.gz

# Verify it is present
docker images xiaozhi-custom-server

# Run it
docker run -d \
  --name xiaozhi-custom \
  --restart unless-stopped \
  --network host \
  -v custom-data:/app/data \
  -v custom-server-data:/app/server/data \
  -v custom-models:/app/server/models \
  -e SERVER_HOST=<JETSON_LAN_IP> \
  -e DATA_DIR=/app/data \
  -e SERVER_DATA_DIR=/app/server/data \
  xiaozhi-custom-server
```

---

### Run on the Jetson

After `docker pull` or `docker load`, create the persistent volumes (first time only)
and start the container:

```bash
# Create volumes (skip if already created)
docker volume create custom-data
docker volume create custom-server-data
docker volume create custom-models

# Start
docker run -d \
  --name xiaozhi-custom \
  --restart unless-stopped \
  --network host \
  -v custom-data:/app/data \
  -v custom-server-data:/app/server/data \
  -v custom-models:/app/server/models \
  -e SERVER_HOST=$(hostname -I | awk '{print $1}') \
  -e DATA_DIR=/app/data \
  -e SERVER_DATA_DIR=/app/server/data \
  xiaozhi-custom-server   # or yourdockerhubuser/xiaozhi-custom-server:latest
```

`$(hostname -I | awk '{print $1}')` auto-detects the Jetson's primary LAN IP.
Replace with a fixed IP if your network has multiple interfaces.

Then follow steps 5–7 of [Quick Start](#quick-start) (setup page, Piper model, ESP32 config).

---

## Architecture

```
main/
├── xiaozhi-server/               ← Upstream Python AI engine (not modified)
└── custom-server/
    ├── server_overrides/         ← Files overlaid on top of xiaozhi-server at build time
    │   └── core/providers/
    │       ├── tts/piper_tts.py  ← New: offline Piper TTS provider
    │       └── vllm/ollama_vllm.py ← New: Ollama vision model provider
    ├── web/                      ← Flask configuration UI
    │   ├── app.py                ← App factory; writes server/data/.config.yaml on startup
    │   ├── models.py             ← SQLAlchemy models (User, Agent, Device, ModelConfig, …)
    │   ├── seed.py               ← First-run data seeding
    │   └── routes/
    │       ├── api.py            ← Internal REST API consumed by xiaozhi-server
    │       ├── auth.py           ← Login / first-run setup
    │       ├── dashboard.py
    │       ├── agents.py
    │       ├── devices.py
    │       ├── plugins.py
    │       └── settings.py
    ├── Dockerfile                ← Build context: main/
    ├── docker-compose.yml        ← network_mode: host
    ├── supervisord.conf          ← Runs Flask then xiaozhi-server
    ├── entrypoint.sh
    └── README.md
```

### How Flask and xiaozhi-server talk

On startup the Flask app writes `server/data/.config.yaml` with a shared secret and
`manager-api.url: http://localhost:5001`. xiaozhi-server reads this file and calls the
Flask API to fetch its runtime configuration instead of the original Java backend.

```
ESP32  ──WebSocket──▶  xiaozhi-server (:8000)
                              │
                    POST /config/agent-models
                              │
                       Flask API (:5001)
                              │
                           SQLite
```
