# CLAUDE.md — Xiaozhi Custom Server

## What this project is

`main/custom-server/` is a self-contained deployment of the Xiaozhi ESP32 voice
assistant, targeting the NVIDIA Jetson AGX Orin (ARM64). It replaces the original
Java + MySQL + Redis + Vue.js stack with:

- A **Flask web app** (`web/`) for configuration (SQLite, no Redis/MySQL)
- Two **new AI providers** (`server_overrides/`) dropped into xiaozhi-server
- A **single Docker container** using host networking

The upstream Python engine lives in `../xiaozhi-server/` (unchanged). This project
only adds or overlays files on top of it.

---

## Directory layout

```
custom-server/
├── server_overrides/          # Files copied over xiaozhi-server at Docker build time
│   └── core/providers/
│       ├── tts/piper_tts.py   # Offline Piper TTS (ARM64, CPU-only)
│       └── vllm/ollama_vllm.py
├── web/
│   ├── app.py                 # Flask factory — also writes server/data/.config.yaml
│   ├── models.py              # SQLAlchemy models
│   ├── seed.py                # First-run seeding (model configs, plugins, sys params)
│   └── routes/
│       ├── api.py             # *** Critical *** REST API consumed by xiaozhi-server
│       ├── auth.py
│       ├── agents.py
│       ├── devices.py
│       ├── plugins.py
│       └── settings.py
├── Dockerfile                 # Build context must be main/ (parent directory)
├── docker-compose.yml         # network_mode: host
├── supervisord.conf           # Flask starts first; xiaozhi-server waits 15 s
└── entrypoint.sh
```

---

## Build context

The Dockerfile build context is **`main/`**, not `custom-server/`. Always build from
`main/`:

```bash
docker build -f custom-server/Dockerfile -t xiaozhi-custom-server .
# or
docker compose -f custom-server/docker-compose.yml up --build
```

The Dockerfile copies `xiaozhi-server/` first, then overlays `custom-server/server_overrides/`
on top of it. Any file in `server_overrides/` that matches a path in `xiaozhi-server/`
will replace it.

---

## How Flask bridges to xiaozhi-server

1. On startup, `web/app.py` writes `server/data/.config.yaml`:
   ```yaml
   manager-api:
     url: http://localhost:5001
     secret: <random hex, stored in data/.api_secret>
   ```

2. xiaozhi-server reads this file and calls the Flask API for all configuration.

3. The Flask API (`routes/api.py`) implements three endpoints that xiaozhi-server calls:

   | Endpoint | When called | Returns |
   |---|---|---|
   | `POST /config/server-base` | Server startup | Global config + default VAD/ASR |
   | `POST /config/agent-models` | Each ESP32 connection | Full per-device agent config |
   | `POST /config/correct-words` | Each ESP32 connection | Word correction list (currently empty) |

4. All API endpoints require `Authorization: Bearer <secret>` using the shared secret
   from `data/.api_secret`.

### Response format

All API responses use the same envelope:
```json
{ "code": 0, "data": { … }, "msg": "success" }
```

The `agent-models` response is the most critical. xiaozhi-server reads it as:
```json
{
  "selected_module": { "ASR": "FunASR", "LLM": "OllamaLLM", "TTS": "PiperTTS", … },
  "ASR":    { "FunASR":    { "type": "fun_local", … } },
  "LLM":    { "OllamaLLM": { "type": "ollama",   … } },
  "TTS":    { "PiperTTS":  { "type": "piper_tts", … } },
  "prompt": "You are …",
  "plugins": { "get_weather": { "key": "…" } }
}
```

---

## Provider type → filename mapping

This mapping is the single most important piece of knowledge for this project.
xiaozhi-server's `core/utils/{category}.py` does dynamic import by filename.

### LLM (`core/providers/llm/<type>/<type>.py`)
| Model config `type` | File loaded |
|---|---|
| `ollama` | `core/providers/llm/ollama/ollama.py` |
| `openai` | `core/providers/llm/openai/openai.py` (also used for DeepSeek, any OpenAI-compatible API) |
| `gemini` | `core/providers/llm/gemini/gemini.py` |

### TTS (`core/providers/tts/<type>.py`)
| Model config `type` | File loaded |
|---|---|
| `piper_tts` | `core/providers/tts/piper_tts.py` ← added by this project |
| `edge` | `core/providers/tts/edge.py` |
| `openai_tts` | `core/providers/tts/openai.py` |

### ASR (`core/providers/asr/<type>.py`)
| Model config `type` | File loaded |
|---|---|
| `fun_local` | `core/providers/asr/fun_local.py` |

### VAD (`core/providers/vad/<type>.py`)
| Model config `type` | File loaded |
|---|---|
| `silero` | `core/providers/vad/silero.py` |

### VLLM (`core/providers/vllm/<type>.py`)
| Model config `type` | File loaded |
|---|---|
| `ollama_vllm` | `core/providers/vllm/ollama_vllm.py` ← added by this project |
| `openai` | `core/providers/vllm/openai.py` |

### Memory / Intent
`type` matches the provider key directly (e.g. `type: mem_local_short`, `type: function_call`).

---

## Database schema (SQLite via SQLAlchemy)

All tables live in `DATA_DIR/custom_server.db`.

| Table | Key columns | Notes |
|---|---|---|
| `users` | `id`, `username`, `password_hash` | Single admin user |
| `agents` | `id`, `name`, `system_prompt`, `*_model_id`, `is_default` | `is_default=True` → fallback for unassigned devices |
| `devices` | `mac_address`, `agent_id`, `status`, `last_seen` | Auto-registered on first ESP32 connection |
| `model_configs` | `id`, `type`, `name`, `config_json` | `id` is the `selected_module` value; `config_json.type` is the Python filename |
| `plugins` | `code`, `enabled`, `params_json` | `code` matches the plugin folder name in `plugins_func/functions/` |
| `sys_params` | `key`, `value`, `value_type` | Dotted keys (e.g. `server.auth.enabled`) become nested dicts in the API response |
| `chat_history` | `session_id`, `mac_address`, `content` | Populated by `POST /agent/chat-history/report` |

---

## Default seeded data (`seed.py`)

Run automatically on first startup. Safe to call multiple times (checks existence before inserting).

**Model configs seeded:** SileroVAD, FunASR, OllamaLLM, OllamaVLLM, PiperTTS, EdgeTTS, OpenAITTS, OpenaiASR, nomem, mem_local_short, mem0ai, function_call, nointent, intent_llm, DeepSeekLLM

**Default agent:** "Default Assistant" using FunASR + OllamaLLM (gemma3:12b) + PiperTTS + mem_local_short + function_call

**Plugins seeded (all disabled by default):** get_weather, get_time, change_role, play_music, get_news_from_chinanews, get_news_from_newsnow, search_from_ragflow, hass_get_state, hass_set_state, hass_play_music, hass_get_history, hass_search_devices

---

## New provider: Piper TTS (`server_overrides/core/providers/tts/piper_tts.py`)

- Class name must be `TTSProvider` (xiaozhi-server convention)
- Inherits from `core.providers.tts.base.TTSProviderBase`
- `text_to_speak(text, output_file)` is the only abstract method to implement
- Uses `piper-tts` Python package; model files (.onnx + .onnx.json) live in `models/piper/`
- Synthesis runs in an executor thread (blocking I/O off the event loop)

---

## New provider: Ollama VLLM (`server_overrides/core/providers/vllm/ollama_vllm.py`)

- Class name must be `VLLMProvider`
- Inherits from `core.providers.vllm.base.VLLMProviderBase`
- `response(question, base64_image)` is the only method to implement
- Uses the OpenAI Python client pointed at `localhost:11434/v1` (Ollama's OpenAI-compatible endpoint)
- Default model: `minicpm-v`

---

## Startup sequence

1. `entrypoint.sh` — detects host IP, starts `supervisord`
2. **Flask** starts (priority 10); writes `server/data/.config.yaml`; creates and seeds SQLite DB
3. **xiaozhi-server** starts after 15-second delay (priority 20); reads `.config.yaml`; connects to Flask API

---

## Common tasks

### Add a new LLM provider
1. Confirm the provider's Python file exists in `../xiaozhi-server/core/providers/llm/<type>/<type>.py`
2. In the web UI: **Settings → Add Model**, set `type` to the directory name, fill in the JSON config

### Add a new Piper voice
1. Copy `.onnx` and `.onnx.json` into the `custom-models` Docker volume under `piper/`
2. In the web UI: **Settings → Add Model** (type `TTS`), set `"type": "piper_tts"` and `"voice_model": "<filename without .onnx>"`

### Change the Ollama model
In the web UI: **Settings → Model Configurations → OllamaLLM → Edit**,
change `model_name`. No restart needed — takes effect on the next ESP32 connection.

### Enable a plugin
**Plugins → toggle** the plugin on, then **Configure** to enter any required API keys.
Plugins are passed to the agent via `result["plugins"]` in the `agent-models` response.

### Reset the database
```bash
docker exec xiaozhi-custom rm /app/data/custom_server.db
docker restart xiaozhi-custom
```

---

## What not to break

- **`routes/api.py` response format** — xiaozhi-server parses the JSON structure exactly.
  The `selected_module` keys must match the top-level provider block keys (e.g.
  `selected_module.TTS = "PiperTTS"` requires `TTS.PiperTTS = { … }` in the same response).

- **`server/data/.config.yaml`** — must be written before xiaozhi-server starts.
  If this file is missing or malformed, xiaozhi-server falls back to file-only config
  with no per-device agent selection.

- **Provider `type` values in `seed.py`** — must match Python filenames exactly.
  A wrong `type` causes a `ValueError` at provider initialisation time (not at startup).

- **`TTSProvider` / `LLMProvider` / `VLLMProvider` class names** — xiaozhi-server imports
  these by that exact name from the loaded module.
