# Xiaozhi Custom Server

A self-contained, single-container deployment of the Xiaozhi ESP32 voice assistant server
for the **NVIDIA Jetson AGX Orin (ARM64)**. Replaces the original Java backend and Vue.js
frontend with a lightweight Flask + SQLite stack. All local AI services run on the
Jetson GPU using [dusty-nv/jetson-containers](https://github.com/dusty-nv/jetson-containers)
as the base image.

---

## What's Inside

| Component | Description |
|---|---|
| **xiaozhi-server** | WebSocket AI engine (Python) — upstream source, unmodified |
| **Flask web UI** | Browser-based admin panel replacing the Java manager-api + Vue frontend |
| **SQLite** | Embedded database — no MySQL or Redis required |
| **Piper TTS** | Offline text-to-speech, GPU-accelerated via onnxruntime CUDA provider |
| **FunASR** | Local speech recognition, GPU-accelerated via CUDA |
| **Ollama LLM / VLLM** | Local LLM and vision model via a separate Ollama container (GPU) |

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

## Default AI Stack

| Service | Provider | Device | Notes |
|---|---|---|---|
| VAD | Silero VAD | CPU | Tiny ONNX model; CPU is faster than GPU for this workload |
| ASR | FunASR SenseVoiceSmall | **GPU** | Model loaded from `/data/models` on the host |
| LLM | Ollama `gemma3:12b` | **GPU** | Via Ollama container at `localhost:11434` |
| VLLM | Ollama `minicpm-v` | **GPU** | Via Ollama container at `localhost:11434` |
| TTS | Piper TTS | **GPU** | ONNX model loaded from `/data/models` on the host |
| Memory | `mem_local_short` | — | LLM-based summarisation, no external service |
| Intent | `function_call` | — | Requires function-call support in the LLM |

All providers can be switched to cloud alternatives through the web UI at any time
without rebuilding the image.

---

## Quick Start

### 1. Prerequisites

- **JetPack 6.x** (R36) installed on the Jetson
- **`default-runtime: nvidia`** set in `/etc/docker/daemon.json` (standard on JetPack 6)
- **`dustynv/framepack`** image already pulled locally — this is the GPU base:
  ```bash
  # Confirm the image is present and note the exact tag
  docker images | grep framepack
  ```
- **`/data/models`** directory on the Jetson with models already downloaded:
  ```
  /data/models/
  ├── huggingface/iic/SenseVoiceSmall/   ← FunASR ASR model
  └── piper/                              ← Piper TTS .onnx + .onnx.json files
  ```
  See [Downloading Models](#downloading-models) if either is missing.
- **Ollama** running and listening on `0.0.0.0:11434`:
  ```bash
  ollama pull gemma3:12b
  ollama pull minicpm-v
  ```
- Working directory for all build commands: `main/` (the parent of `custom-server/`)

### 2. Set the base image tag

Open `custom-server/docker-compose.yml` and update `BASE_IMAGE` to match the tag
shown by `docker images | grep framepack`:

```yaml
args:
  BASE_IMAGE: dustynv/framepack:r36.4.0   # ← change to your local tag
```

### 3. Build

```bash
cd main/
docker compose -f custom-server/docker-compose.yml build
```

The build context is `main/` so the Dockerfile can access both `xiaozhi-server/` and
`custom-server/` in a single pass. The first build takes 15–20 minutes; subsequent
builds reuse the cache and are much faster.

### 4. Run

```bash
cd main/
SERVER_HOST=192.168.1.100 docker compose -f custom-server/docker-compose.yml up -d
```

Set `SERVER_HOST` to your Jetson's LAN IP. This address is written into the WebSocket
and OTA URLs that are sent to ESP32 devices — it does not affect how the container
itself binds to ports.

Or with plain Docker:

```bash
docker run -d \
  --name xiaozhi-custom \
  --restart unless-stopped \
  --network host \
  -v custom-data:/app/data \
  -v custom-server-data:/app/server/data \
  -v /data/models:/data/models:ro \
  -e SERVER_HOST=192.168.1.100 \
  xiaozhi-custom-server
```

> **`--runtime nvidia`** is not required explicitly when `default-runtime` is already
> `nvidia` in `/etc/docker/daemon.json`, which is the standard JetPack 6 configuration.

### 5. First-Run Setup

1. Open `http://<JETSON_IP>:5001` in a browser.
2. You will be redirected to the setup page — create your admin account.
3. Default agents, model configs, and plugins are seeded automatically.

### 6. Verify model paths

The seeded FunASR config points to `/data/models/huggingface/iic/SenseVoiceSmall`.
If your SenseVoiceSmall model lives at a different path, update it via
**Settings → Model Configurations → FunASR → Edit** in the web UI — no rebuild needed.

### 7. Connect Your ESP32

Flash your ESP32 with the xiaozhi firmware and configure:

- **WebSocket URL**: `ws://<JETSON_IP>:8000/xiaozhi/v1/`
- **OTA URL**: `http://<JETSON_IP>:8003/xiaozhi/ota/`

The first time an ESP32 connects with an unrecognised MAC address it is automatically
registered and assigned to the default agent. Go to **Devices** in the web UI to give
it a name or reassign it to a different agent.

---

## Downloading Models

Models are stored on the Jetson host at `/data/models` and bind-mounted read-only into
the container. The container never writes to this directory.

### FunASR SenseVoiceSmall

```bash
pip install -q huggingface-hub
huggingface-cli download iic/SenseVoiceSmall \
  --local-dir /data/models/huggingface/iic/SenseVoiceSmall \
  --local-dir-use-symlinks False
```

The directory must contain at minimum: `model.pt`, `config.yaml`, `tokens.json`.

### Piper TTS voices

```bash
mkdir -p /data/models/piper

# Default voice: English (US), Lessac, medium quality
curl -L "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx" \
     -o /data/models/piper/en_US-lessac-medium.onnx

curl -L "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json" \
     -o /data/models/piper/en_US-lessac-medium.onnx.json
```

Browse all available voices and samples at: <https://rhasspy.github.io/piper-samples/>

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

1. Download the `.onnx` and `.onnx.json` files to `/data/models/piper/` on the host.
2. Open **Settings → Add Model** and create a new TTS entry:

```json
{
  "type": "piper_tts",
  "voice_model": "en_GB-alba-medium",
  "model_dir": "/data/models/piper/",
  "output_dir": "tmp/",
  "use_cuda": true,
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
docker compose -f custom-server/docker-compose.yml build --no-cache
docker compose -f custom-server/docker-compose.yml up -d
```

The SQLite database and model bind-mount are unaffected — no data is lost.

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

The server must be running before you open the test page:

```bash
cd main/
SERVER_HOST=192.168.1.100 docker compose -f custom-server/docker-compose.yml up -d
```

Verify both services are up:

```bash
# Flask UI should return 200
curl -s -o /dev/null -w "%{http_code}" http://localhost:5001/

# WebSocket server should respond with 101 Switching Protocols
curl -s --include --no-buffer \
  -H "Upgrade: websocket" -H "Connection: Upgrade" \
  -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" \
  -H "Sec-WebSocket-Version: 13" \
  http://localhost:8000/xiaozhi/v1/
```

---

### Step 2 — Serve the test page

```bash
cd main/custom-server
python -m http.server 8080
```

Open **http://localhost:8080/test.html** in Chrome or Edge.

---

### Step 3 — Connect

1. Set **WebSocket Server URL** to `ws://<SERVER_IP>:8000/xiaozhi/v1/`.
2. Leave **Device ID** as the auto-generated value — stored in `localStorage`.
3. Leave **Auth token** empty (disabled by default).
4. Click **Connect**.

**Expected log output:**

```
→ sent  {"type":"hello","audio_params":{"format":"opus","sample_rate":24000,...}}
← recv  hello — session_id: a3f8c1d2…
```

**If the connection fails:**
- `WebSocket error` — server not running or wrong address/port.
- `Connection closed (code 1008)` — auth is enabled; add a token.
- `Connection closed (code 1000)` immediately — check `docker exec xiaozhi-custom tail -f /var/log/supervisor/server.log`.

---

### Step 4 — Test the LLM (text path)

Type a message in the input field and press **Enter** or click **Send**.

This sends `{"type":"listen","state":"detect","text":"..."}`, bypassing audio encoding
and feeding text directly to the LLM pipeline.

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

**If no response appears:**
- Check Ollama is running: `curl http://localhost:11434/api/tags`
- Check xiaozhi-server logs: `docker exec xiaozhi-custom tail -f /var/log/supervisor/server.log`

**If you see STT but no audio frames:**
- Check that Piper model files exist at `/data/models/piper/en_US-lessac-medium.onnx`.
- Check the server log for onnxruntime CUDA errors — if `CUDAExecutionProvider` is
  unavailable the provider falls back to CPU automatically; synthesis should still work.

---

### Step 5 — Test TTS audio playback

Audio plays automatically when Opus frames arrive (Chrome/Edge only). If you hear
nothing despite seeing `🔊 Opus frame` lines in the log:

- Check browser audio: tab not muted, system volume up.
- Click **Abort TTS** then send another message to reset the audio decoder.
- Open the browser console (`F12`) and look for `AudioDecoder` errors.

---

### Step 6 — Test microphone input / ASR (Chrome/Edge only)

This tests the full speech path: mic → Opus encode → server VAD → FunASR (GPU) → LLM → Piper TTS (GPU).

1. Click **🎤 Record**.
2. Allow microphone access when prompted.
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

**If `🗣 STT` is empty or missing:**
- FunASR takes 30–60 s to load on first start — check `docker logs xiaozhi-custom`.
- Verify the model path: `ls /data/models/huggingface/iic/SenseVoiceSmall/model.pt`
- Check GPU is being used: `docker exec xiaozhi-custom nvidia-smi`

---

### Step 7 — Test Abort

While TTS audio is playing, click **✕ Abort TTS**.

**Expected:**
```
→ sent  {"type":"abort"}
← recv  tts stop
```

---

### Quick reference — log colours

| Colour | Direction | Meaning |
|---|---|---|
| Blue `→ sent` | Outbound | JSON message sent to server |
| Green `← recv` | Inbound JSON | Server response (hello, stt, tts state) |
| Gray `← recv` | Inbound binary | Opus audio frame from TTS |
| Yellow `ℹ info` | Local | Page-level status |
| Red `✖ error` | Local | Connection or codec error |

---

## Building and Distributing the Image

Because the base image (`dustynv/framepack`) is Jetson-specific (ARM64 + L4T), the
image **must be built on the Jetson** (or another ARM64 machine). Cross-compilation from
x86 is not supported.

### Build on the Jetson and push to a registry

```bash
# On the Jetson
cd main/
docker compose -f custom-server/docker-compose.yml build

# Tag and push
docker tag xiaozhi-custom-server:latest yourdockerhubuser/xiaozhi-custom-server:latest
docker push yourdockerhubuser/xiaozhi-custom-server:latest
```

### Pull and run on another Jetson

```bash
docker pull yourdockerhubuser/xiaozhi-custom-server:latest

docker run -d \
  --name xiaozhi-custom \
  --restart unless-stopped \
  --network host \
  -v custom-data:/app/data \
  -v custom-server-data:/app/server/data \
  -v /data/models:/data/models:ro \
  -e SERVER_HOST=$(hostname -I | awk '{print $1}') \
  yourdockerhubuser/xiaozhi-custom-server:latest
```

### Transfer via file (no registry)

```bash
# On the source Jetson
docker save xiaozhi-custom-server:latest | gzip > xiaozhi-custom-server.tar.gz
scp xiaozhi-custom-server.tar.gz user@<TARGET_JETSON_IP>:~

# On the target Jetson
docker load < xiaozhi-custom-server.tar.gz
docker run -d --name xiaozhi-custom --restart unless-stopped --network host \
  -v custom-data:/app/data -v custom-server-data:/app/server/data \
  -v /data/models:/data/models:ro \
  -e SERVER_HOST=$(hostname -I | awk '{print $1}') \
  xiaozhi-custom-server:latest
```

---

## Architecture

```
main/
├── xiaozhi-server/                    ← Upstream Python AI engine (not modified)
└── custom-server/
    ├── server_overrides/              ← Overlaid on top of xiaozhi-server at build time
    │   └── core/providers/
    │       ├── asr/fun_local.py       ← Override: passes `device` from config to AutoModel
    │       ├── vad/silero.py          ← Override: finds ONNX from silero_vad pip package
    │       ├── tts/piper_tts.py       ← Override: GPU via onnxruntime CUDA provider
    │       └── vllm/ollama_vllm.py    ← New: Ollama vision model provider
    ├── web/                           ← Flask configuration UI
    │   ├── app.py                     ← App factory; writes server/data/.config.yaml on startup
    │   ├── models.py                  ← SQLAlchemy models (User, Agent, Device, ModelConfig, …)
    │   ├── seed.py                    ← First-run data seeding
    │   └── routes/
    │       ├── api.py                 ← Internal REST API consumed by xiaozhi-server
    │       ├── auth.py                ← Login / first-run setup
    │       ├── dashboard.py
    │       ├── agents.py
    │       ├── devices.py
    │       ├── plugins.py
    │       └── settings.py
    ├── Dockerfile                     ← Base: dustynv/framepack (Jetson GPU)
    ├── docker-compose.yml             ← network_mode: host, /data/models bind-mount
    ├── supervisord.conf               ← Runs Flask then xiaozhi-server
    ├── entrypoint.sh
    ├── test.html                      ← Browser-based ESP32 emulator
    └── README.md
```

### GPU provider overrides

| Override | What it does |
|---|---|
| `asr/fun_local.py` | Reads `device` from the model config (`cpu` or `cuda:0`) and passes it to FunASR's `AutoModel`. The upstream file ignores this config key. |
| `vad/silero.py` | Locates `silero_vad.onnx` from the `silero_vad` pip package bundled in `requirements.txt` — no manual model download needed. VAD stays on CPU (the model is too small to benefit from GPU). |
| `tts/piper_tts.py` | Reads `use_cuda` from the model config. When `true`, passes `CUDAExecutionProvider` to onnxruntime. Falls back to CPU gracefully if the CUDA provider is unavailable. |

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

### Model storage

All AI models live on the Jetson host at `/data/models` and are bind-mounted read-only
into the container. No model files are baked into the Docker image.

```
/data/models/
├── huggingface/iic/SenseVoiceSmall/   ← FunASR ASR  (device: cuda:0)
├── piper/                              ← Piper TTS   (use_cuda: true)
└── ...                                 ← Other models used by other containers
```
