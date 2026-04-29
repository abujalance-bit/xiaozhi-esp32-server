"""Internal REST API consumed by xiaozhi-server.

All endpoints require Bearer token authentication using the shared API secret
stored in DATA_DIR/.api_secret.
"""
import os
from datetime import datetime
from functools import wraps

from flask import Blueprint, request, jsonify, current_app
from models import db, Agent, Device, ModelConfig, Plugin, SysParam, ChatHistory

api_bp = Blueprint("api", __name__)

DATA_DIR = os.environ.get("DATA_DIR", "/app/data")

# Keys that xiaozhi-server reads from the top-level config but are not stored in
# sys_params. These are injected into every /config/server-base response so the
# server works identically whether launched standalone or via manager-api.
_STATIC_SERVER_DEFAULTS = {
    "delete_audio": True,
    "enable_wakeup_words_response_cache": True,
    "enable_stop_tts_notify": False,
    "stop_tts_notify_voice": "config/assets/tts_notify.mp3",
    "enable_websocket_ping": False,
    "tts_audio_send_delay": 0,
    "prompt_template": "agent-base-prompt.txt",
    # Hard-accessed (no default) — must be present or the server crashes on connect
    "exit_commands": ["退出", "关闭", "exit", "quit", "bye"],
    "xiaozhi": {
        "type": "hello",
        "version": 1,
        "transport": "websocket",
        "audio_params": {
            "format": "opus",
            "sample_rate": 24000,
            "channels": 1,
            "frame_duration": 60,
        },
    },
}


def _get_api_secret():
    secret_file = os.path.join(DATA_DIR, ".api_secret")
    if os.path.exists(secret_file):
        with open(secret_file) as f:
            return f.read().strip()
    return None


def require_api_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        secret = _get_api_secret()
        if not secret or auth != f"Bearer {secret}":
            return jsonify({"code": 401, "msg": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated


def ok(data):
    return jsonify({"code": 0, "data": data, "msg": "success"})


def _build_sys_params_dict():
    """Convert flat sys_params table into the nested dict xiaozhi-server expects."""
    params = SysParam.query.all()
    result = {}
    for p in params:
        keys = p.key.split(".")
        current = result
        for k in keys[:-1]:
            current = current.setdefault(k, {})
        last = keys[-1]
        vt = p.value_type.lower()
        if vt == "number":
            try:
                v = float(p.value)
                current[last] = int(v) if v == int(v) else v
            except (ValueError, TypeError):
                current[last] = p.value
        elif vt == "boolean":
            current[last] = p.value.lower() in ("true", "1", "yes")
        elif vt == "array":
            current[last] = [x.strip() for x in p.value.split(";") if x.strip()]
        elif vt == "json":
            import json
            try:
                current[last] = json.loads(p.value)
            except Exception:
                current[last] = p.value
        else:
            current[last] = p.value
    return result


def _build_module_block(model_id):
    """Return {model_id: config_json} for a given ModelConfig id, or empty dict."""
    if not model_id:
        return {}
    mc = ModelConfig.query.get(model_id)
    if not mc:
        return {}
    return {mc.id: dict(mc.config_json)}


def _build_agent_config(agent):
    """Build the full agent config dict for a given Agent record."""
    result = {}

    # Module blocks
    module_types = ["VAD", "ASR", "LLM", "VLLM", "TTS", "Memory", "Intent"]
    model_ids = [
        agent.vad_model_id,
        agent.asr_model_id,
        agent.llm_model_id,
        agent.vllm_model_id,
        agent.tts_model_id,
        agent.mem_model_id,
        agent.intent_model_id,
    ]
    selected_module = {}

    for mtype, mid in zip(module_types, model_ids):
        if not mid:
            continue
        mc = ModelConfig.query.get(mid)
        if not mc:
            continue
        cfg = dict(mc.config_json)

        # Inject TTS voice overrides
        if mtype == "TTS":
            if agent.tts_voice:
                cfg["private_voice"] = agent.tts_voice
            if agent.tts_language:
                cfg["language"] = agent.tts_language
            if agent.tts_volume is not None:
                cfg["ttsVolume"] = agent.tts_volume
            if agent.tts_rate is not None:
                cfg["ttsRate"] = agent.tts_rate
            if agent.tts_pitch is not None:
                cfg["ttsPitch"] = agent.tts_pitch

        result[mtype] = {mc.id: cfg}
        selected_module[mtype] = mc.id

    result["selected_module"] = selected_module
    result["prompt"] = agent.system_prompt or ""
    result["summaryMemory"] = agent.summary_memory or ""
    result["chat_history_conf"] = agent.chat_history_conf or 0

    # Plugins: only include enabled plugins.
    # xiaozhi-server does json.loads() on each value, so params must be a JSON string.
    enabled_plugins = Plugin.query.filter_by(enabled=True).all()
    if enabled_plugins:
        import json as _json
        plugins_dict = {}
        for p in enabled_plugins:
            plugins_dict[p.code] = _json.dumps(dict(p.params_json) if p.params_json else {})
        result["plugins"] = plugins_dict

    # Device output limit
    max_output_param = SysParam.query.get("device_max_output_size")
    result["device_max_output_size"] = max_output_param.value if max_output_param else "0"

    return result


# ---------------------------------------------------------------------------
# POST /config/server-base
# Called once on xiaozhi-server startup to get global config.
# ---------------------------------------------------------------------------
@api_bp.route("/config/server-base", methods=["POST"])
@require_api_auth
def server_base():
    result = _build_sys_params_dict()

    # Default agent's VAD + ASR for server-level defaults
    default_agent = Agent.query.filter_by(is_default=True).first() or Agent.query.first()
    if default_agent:
        vad_block = _build_module_block(default_agent.vad_model_id)
        asr_block = _build_module_block(default_agent.asr_model_id)
        if vad_block:
            result["VAD"] = vad_block
            result.setdefault("selected_module", {})["VAD"] = default_agent.vad_model_id
        if asr_block:
            result["ASR"] = asr_block
            result.setdefault("selected_module", {})["ASR"] = default_agent.asr_model_id

    # Ensure server.auth exists
    result.setdefault("server", {}).setdefault("auth", {"enabled": False})

    # logger.py requires a "log" key — not present in sys_params, so inject defaults
    result.setdefault("log", {
        "log_level": "INFO",
        "log_dir": "tmp",
        "log_file": "server.log",
        "data_dir": "data",
    })

    # Inject static defaults for keys the server hard-accesses or needs at startup.
    # setdefault means sys_params values (already in result) always win.
    for key, val in _STATIC_SERVER_DEFAULTS.items():
        result.setdefault(key, val)

    return ok(result)


# ---------------------------------------------------------------------------
# POST /config/agent-models
# Body: {"macAddress": "...", "clientId": "...", "selectedModule": {...}}
# ---------------------------------------------------------------------------
@api_bp.route("/config/agent-models", methods=["POST"])
@require_api_auth
def agent_models():
    body = request.get_json(silent=True) or {}
    mac = body.get("macAddress", "").upper().strip()

    if not mac:
        return ok(_build_agent_config(
            Agent.query.filter_by(is_default=True).first() or Agent.query.first()
        ))

    device = Device.query.filter_by(mac_address=mac).first()
    if not device:
        # Auto-register and assign to the default agent — no binding prompt needed
        default_agent = Agent.query.filter_by(is_default=True).first() or Agent.query.first()
        new_device = Device(
            mac_address=mac,
            name=f"Device {mac[-5:]}",
            agent_id=default_agent.id if default_agent else None,
        )
        db.session.add(new_device)
        db.session.commit()
        device = new_device

    agent = Agent.query.get(device.agent_id) if device.agent_id else None
    if not agent:
        agent = Agent.query.filter_by(is_default=True).first() or Agent.query.first()
    if not agent:
        return jsonify({"code": 500, "msg": "No agents configured"}), 200

    # Update device last_seen
    device.last_seen = datetime.utcnow()
    device.status = "online"
    db.session.commit()

    return ok(_build_agent_config(agent))


# ---------------------------------------------------------------------------
# POST /config/correct-words
# Body: {"macAddress": "..."}
# ---------------------------------------------------------------------------
@api_bp.route("/config/correct-words", methods=["POST"])
@require_api_auth
def correct_words():
    # Correct-word management not yet implemented — return empty list
    return ok([])


# ---------------------------------------------------------------------------
# POST /agent/chat-history/report
# ---------------------------------------------------------------------------
@api_bp.route("/agent/chat-history/report", methods=["POST"])
@require_api_auth
def chat_history_report():
    body = request.get_json(silent=True) or {}
    entry = ChatHistory(
        session_id=body.get("sessionId"),
        mac_address=body.get("macAddress"),
        chat_type=body.get("chatType"),
        content=body.get("content"),
        report_time=body.get("reportTime"),
    )
    db.session.add(entry)
    db.session.commit()
    return ok(None)


# ---------------------------------------------------------------------------
# POST /agent/chat-summary/<session_id>/save
# POST /agent/chat-title/<session_id>/generate
# ---------------------------------------------------------------------------
@api_bp.route("/agent/chat-summary/<session_id>/save", methods=["POST"])
@require_api_auth
def chat_summary_save(session_id):
    return ok(None)


@api_bp.route("/agent/chat-title/<session_id>/generate", methods=["POST"])
@require_api_auth
def chat_title_generate(session_id):
    return ok(None)


# ---------------------------------------------------------------------------
# POST /device/register  (convenience: lets ESP32 firmware self-register)
# ---------------------------------------------------------------------------
@api_bp.route("/device/register", methods=["POST"])
@require_api_auth
def device_register():
    body = request.get_json(silent=True) or {}
    mac = body.get("macAddress", "").upper().strip()
    if not mac:
        return jsonify({"code": 400, "msg": "macAddress is required"}), 400
    device = Device.query.filter_by(mac_address=mac).first()
    if not device:
        device = Device(mac_address=mac, name=body.get("name", f"Device {mac[-5:]}"))
        db.session.add(device)
        db.session.commit()
    return ok({"id": device.id, "macAddress": device.mac_address})
