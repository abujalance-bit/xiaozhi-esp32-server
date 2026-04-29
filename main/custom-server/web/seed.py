"""Database seeding: default model configs, plugins, sys params, and default agent."""
from models import db, ModelConfig, Plugin, SysParam, Agent


DEFAULT_MODEL_CONFIGS = [
    # VAD
    ModelConfig(
        id="SileroVAD",
        type="VAD",
        name="Silero VAD (Local)",
        description="Local voice activity detection using Silero VAD model.",
        is_local=True,
        config_json={
            "type": "silero",
            "threshold": 0.5,
            "min_silence_duration_ms": 500,
            "speech_pad_ms": 100,
        },
    ),
    # ASR
    ModelConfig(
        id="FunASR",
        type="ASR",
        name="FunASR SenseVoice (Local)",
        description="Local speech recognition using FunASR SenseVoiceSmall model.",
        is_local=True,
        config_json={
            "type": "fun_local",
            # model_name: registered HuggingFace/ModelScope name (used for class lookup)
            # model_dir:  local path to the model files (skips download if it exists)
            "model_name": "iic/SenseVoiceSmall",
            "model_dir": "/data/models/SenseVoiceSmall",
            "output_dir": "tmp/",
            "device": "cuda:0",
        },
    ),
    ModelConfig(
        id="FasterWhisper",
        type="ASR",
        name="Faster Whisper (Local, GPU)",
        description="Offline Whisper via CTranslate2 — multilingual (including Spanish), CUDA-accelerated. medium ~0.5 s on Jetson.",
        is_local=True,
        config_json={
            "type": "faster_whisper_local",
            # Auto-downloads on first run, or set to a local path.
            # On Jetson ARM64 the PyPI ctranslate2 has no CUDA support;
            # the provider falls back automatically to cpu+int8.
            "model_size_or_path": "medium",
            "device": "cpu",
            "compute_type": "int8",
            "language": None,
            "output_dir": "tmp/",
        },
    ),
    ModelConfig(
        id="GroqASR",
        type="ASR",
        name="Groq Whisper (Cloud)",
        description="Groq-hosted Whisper Large v3 Turbo — very fast, free tier, multilingual including Spanish.",
        is_local=False,
        config_json={
            "type": "openai",
            "api_key": "",
            "base_url": "https://api.groq.com/openai/v1/audio/transcriptions",
            "model_name": "whisper-large-v3-turbo",
            "output_dir": "tmp/",
        },
    ),
    ModelConfig(
        id="OpenaiASR",
        type="ASR",
        name="OpenAI Whisper (Cloud)",
        description="OpenAI Whisper speech recognition via API.",
        is_local=False,
        config_json={
            "type": "openai",
            "api_key": "",
            "model_name": "whisper-1",
            "output_dir": "tmp/",
        },
    ),
    # LLM
    ModelConfig(
        id="OllamaLLM",
        type="LLM",
        name="Ollama (Local)",
        description="Local LLM via Ollama. gemma3:12b recommended for Jetson AGX Orin.",
        is_local=True,
        config_json={
            "type": "ollama",
            "model_name": "gemma3:12b",
            "base_url": "http://localhost:11434",
            "api_key": "ollama",
        },
    ),
    ModelConfig(
        id="DeepSeekLLM",
        type="LLM",
        name="DeepSeek (Cloud)",
        description="DeepSeek LLM via API.",
        is_local=False,
        config_json={
            "type": "deepseek",
            "model_name": "deepseek-chat",
            "api_key": "",
            "base_url": "https://api.deepseek.com/v1",
        },
    ),
    # VLLM
    ModelConfig(
        id="OllamaVLLM",
        type="VLLM",
        name="Ollama Vision (Local)",
        description="Local vision LLM via Ollama (e.g. minicpm-v, llava).",
        is_local=True,
        config_json={
            "type": "ollama_vllm",
            "model_name": "minicpm-v",
            "base_url": "http://localhost:11434/v1",
            "api_key": "ollama",
            "max_tokens": 500,
        },
    ),
    # TTS
    ModelConfig(
        id="PiperTTS",
        type="TTS",
        name="Piper TTS (Local, GPU)",
        description="Offline TTS using Piper with onnxruntime CUDA provider on Jetson.",
        is_local=True,
        config_json={
            "type": "piper_tts",
            "voice_model": "en_US-lessac-medium",
            # Model files (.onnx + .onnx.json) at /data/models/piper/ on the host.
            "model_dir": "/data/models/piper/",
            "output_dir": "tmp/",
            "use_cuda": True,
            "length_scale": 1.0,
            "noise_scale": 0.667,
            "noise_w": 0.8,
        },
    ),
    ModelConfig(
        id="EdgeTTS",
        type="TTS",
        name="Edge TTS (Online)",
        description="Microsoft Edge TTS — free but requires internet access.",
        is_local=False,
        config_json={
            "type": "edge",
            "voice": "en-US-JennyNeural",
            "output_dir": "tmp/",
        },
    ),
    ModelConfig(
        id="OpenAITTS",
        type="TTS",
        name="OpenAI TTS (Cloud)",
        description="OpenAI text-to-speech via API.",
        is_local=False,
        config_json={
            "type": "openai_tts",
            "api_key": "",
            "model_name": "tts-1",
            "voice": "alloy",
            "output_dir": "tmp/",
        },
    ),
    # Memory
    ModelConfig(
        id="nomem",
        type="Memory",
        name="No Memory",
        description="Stateless — no conversation memory.",
        is_local=True,
        config_json={"type": "nomem"},
    ),
    ModelConfig(
        id="mem_local_short",
        type="Memory",
        name="Local Short-Term Memory",
        description="LLM-based summarization stored locally. Uses the agent's LLM by default.",
        is_local=True,
        config_json={
            "type": "mem_local_short",
            # Leave llm blank to use the same LLM as the agent (OllamaLLM).
            # Set to another model ID to use a dedicated summarisation model.
        },
    ),
    ModelConfig(
        id="mem0ai",
        type="Memory",
        name="Mem0 AI (Cloud)",
        description="Mem0 cloud memory — 1000 free calls/month.",
        is_local=False,
        config_json={
            "type": "mem0ai",
            "api_key": "",
        },
    ),
    # Intent
    ModelConfig(
        id="function_call",
        type="Intent",
        name="Function Call",
        description="Fast intent detection via LLM function calling. Recommended.",
        is_local=True,
        config_json={"type": "function_call"},
    ),
    ModelConfig(
        id="nointent",
        type="Intent",
        name="No Intent Recognition",
        description="Disables intent recognition entirely.",
        is_local=True,
        config_json={"type": "nointent"},
    ),
    ModelConfig(
        id="intent_llm",
        type="Intent",
        name="LLM Intent (Slower)",
        description="LLM-based intent classification — more flexible but adds latency.",
        is_local=True,
        config_json={"type": "intent_llm", "llm": "OllamaLLM"},
    ),
]

DEFAULT_PLUGINS = [
    Plugin(
        code="get_weather",
        name="Weather",
        description="Fetches current weather information using QWeather API.",
        enabled=False,
        params_json={"key": "", "location": "auto"},
    ),
    Plugin(
        code="get_time",
        name="Time & Date",
        description="Reports the current time and date.",
        enabled=True,
        params_json={},
    ),
    Plugin(
        code="change_role",
        name="Role Switching",
        description="Allows the assistant to switch between predefined personas.",
        enabled=False,
        params_json={},
    ),
    Plugin(
        code="play_music",
        name="Music Player",
        description="Controls music playback from a local directory.",
        enabled=False,
        params_json={"music_dir": "/app/server/music/"},
    ),
    Plugin(
        code="get_news_from_chinanews",
        name="News (ChinaNews)",
        description="Fetches latest news from ChinaNews RSS.",
        enabled=False,
        params_json={},
    ),
    Plugin(
        code="get_news_from_newsnow",
        name="News (NewNow)",
        description="Fetches trending news from NewNow.",
        enabled=False,
        params_json={"newsnow_url": ""},
    ),
    Plugin(
        code="search_from_ragflow",
        name="RAGFlow Knowledge Base",
        description="Searches a RAGFlow knowledge base for answers.",
        enabled=False,
        params_json={
            "ragflow_url": "",
            "ragflow_api_key": "",
            "ragflow_dataset_ids": "",
        },
    ),
    Plugin(
        code="hass_get_state",
        name="Home Assistant — Get State",
        description="Retrieves the state of a Home Assistant entity.",
        enabled=False,
        params_json={"hass_url": "", "hass_token": ""},
    ),
    Plugin(
        code="hass_set_state",
        name="Home Assistant — Set State",
        description="Sets the state or service of a Home Assistant entity.",
        enabled=False,
        params_json={"hass_url": "", "hass_token": ""},
    ),
    Plugin(
        code="hass_play_music",
        name="Home Assistant — Play Music",
        description="Controls music playback via a Home Assistant media player.",
        enabled=False,
        params_json={"hass_url": "", "hass_token": "", "media_player": ""},
    ),
    Plugin(
        code="hass_get_history",
        name="Home Assistant — Get History",
        description="Queries historical state data from Home Assistant.",
        enabled=False,
        params_json={"hass_url": "", "hass_token": ""},
    ),
    Plugin(
        code="hass_search_devices",
        name="Home Assistant — Search Devices",
        description="Searches available devices in Home Assistant.",
        enabled=False,
        params_json={"hass_url": "", "hass_token": ""},
    ),
]

DEFAULT_SYS_PARAMS = [
    SysParam(
        key="device_max_output_size",
        value="0",
        value_type="number",
        description="Maximum characters per device per day (0 = unlimited).",
    ),
    SysParam(
        key="server.auth.enabled",
        value="false",
        value_type="boolean",
        description="Require ESP32 devices to authenticate with a token.",
    ),
    SysParam(
        key="server.voiceprint_similarity_threshold",
        value="0.4",
        value_type="number",
        description="Similarity threshold for voiceprint recognition.",
    ),
    SysParam(
        key="close_connection_no_voice_time",
        value="120",
        value_type="number",
        description="Seconds of silence before the connection is closed.",
    ),
    SysParam(
        key="tts_timeout",
        value="10",
        value_type="number",
        description="TTS request timeout in seconds.",
    ),
    SysParam(
        key="tool_call_timeout",
        value="30",
        value_type="number",
        description="Tool/function call timeout in seconds.",
    ),
    SysParam(
        key="enable_greeting",
        value="true",
        value_type="boolean",
        description="Play a greeting message when the device wakes up.",
    ),
    SysParam(
        key="wakeup_words",
        value="Hey Xiaozhi;Hello Xiaozhi;Hey Assistant",
        value_type="array",
        description="Wake-up phrases (semicolon-separated).",
    ),
]

DEFAULT_AGENT_PROMPT = (
    "You are a helpful, friendly voice assistant running locally on a Jetson AGX Orin. "
    "Keep your responses concise and conversational — you are speaking, not writing. "
    "Avoid long lists or markdown formatting."
)


def seed_database():
    """Seed all default records if they don't already exist."""
    for mc in DEFAULT_MODEL_CONFIGS:
        if not ModelConfig.query.get(mc.id):
            db.session.add(mc)

    for plugin in DEFAULT_PLUGINS:
        if not Plugin.query.get(plugin.code):
            db.session.add(plugin)

    for param in DEFAULT_SYS_PARAMS:
        if not SysParam.query.get(param.key):
            db.session.add(param)

    # Create the default agent if none exists
    if Agent.query.count() == 0:
        default_agent = Agent(
            name="Default Assistant",
            system_prompt=DEFAULT_AGENT_PROMPT,
            vad_model_id="SileroVAD",
            asr_model_id="FunASR",
            llm_model_id="OllamaLLM",
            vllm_model_id="OllamaVLLM",
            tts_model_id="PiperTTS",
            mem_model_id="mem_local_short",
            intent_model_id="function_call",
            tts_language="English",
            is_default=True,
        )
        db.session.add(default_agent)

    db.session.commit()
