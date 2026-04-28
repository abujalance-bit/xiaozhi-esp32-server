from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required
from models import db, Agent, ModelConfig

agents_bp = Blueprint("agents", __name__)


def _get_models_by_type():
    types = ["VAD", "ASR", "LLM", "VLLM", "TTS", "Memory", "Intent"]
    return {t: ModelConfig.query.filter_by(type=t).all() for t in types}


@agents_bp.route("/")
@login_required
def list_agents():
    agents = Agent.query.order_by(Agent.created_at.desc()).all()
    return render_template("agents/list.html", agents=agents)


@agents_bp.route("/new", methods=["GET", "POST"])
@login_required
def new_agent():
    models_by_type = _get_models_by_type()
    if request.method == "POST":
        agent = _agent_from_form(Agent())
        db.session.add(agent)
        db.session.commit()
        flash(f'Agent "{agent.name}" created.', "success")
        return redirect(url_for("agents.list_agents"))
    return render_template("agents/form.html", agent=None, models_by_type=models_by_type)


@agents_bp.route("/<agent_id>", methods=["GET", "POST"])
@login_required
def edit_agent(agent_id):
    agent = Agent.query.get_or_404(agent_id)
    models_by_type = _get_models_by_type()
    if request.method == "POST":
        _agent_from_form(agent)
        db.session.commit()
        flash(f'Agent "{agent.name}" updated.', "success")
        return redirect(url_for("agents.list_agents"))
    return render_template("agents/form.html", agent=agent, models_by_type=models_by_type)


@agents_bp.route("/<agent_id>/delete", methods=["POST"])
@login_required
def delete_agent(agent_id):
    agent = Agent.query.get_or_404(agent_id)
    if agent.is_default:
        flash("Cannot delete the default agent.", "danger")
        return redirect(url_for("agents.list_agents"))
    # Unlink devices
    for d in agent.devices:
        d.agent_id = None
    db.session.delete(agent)
    db.session.commit()
    flash("Agent deleted.", "success")
    return redirect(url_for("agents.list_agents"))


@agents_bp.route("/<agent_id>/set-default", methods=["POST"])
@login_required
def set_default(agent_id):
    Agent.query.update({"is_default": False})
    agent = Agent.query.get_or_404(agent_id)
    agent.is_default = True
    db.session.commit()
    flash(f'"{agent.name}" is now the default agent.', "success")
    return redirect(url_for("agents.list_agents"))


def _agent_from_form(agent):
    f = request.form
    agent.name = f.get("name", "").strip() or "Unnamed Agent"
    agent.system_prompt = f.get("system_prompt", "")
    agent.summary_memory = f.get("summary_memory", "")
    agent.chat_history_conf = int(f.get("chat_history_conf", 0))
    agent.vad_model_id = f.get("vad_model_id") or "SileroVAD"
    agent.asr_model_id = f.get("asr_model_id") or "FunASR"
    agent.llm_model_id = f.get("llm_model_id") or "OllamaLLM"
    agent.vllm_model_id = f.get("vllm_model_id") or "OllamaVLLM"
    agent.tts_model_id = f.get("tts_model_id") or "PiperTTS"
    agent.mem_model_id = f.get("mem_model_id") or "nomem"
    agent.intent_model_id = f.get("intent_model_id") or "function_call"
    agent.tts_voice = f.get("tts_voice", "")
    agent.tts_language = f.get("tts_language", "English")
    agent.tts_volume = _safe_int(f.get("tts_volume"), 100)
    agent.tts_rate = _safe_int(f.get("tts_rate"), 100)
    agent.tts_pitch = _safe_int(f.get("tts_pitch"), 100)
    return agent


def _safe_int(val, default):
    try:
        return int(val)
    except (TypeError, ValueError):
        return default
