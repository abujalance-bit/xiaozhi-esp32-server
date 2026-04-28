import json
from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required
from models import db, SysParam, ModelConfig

settings_bp = Blueprint("settings", __name__)


@settings_bp.route("/")
@login_required
def index():
    params = {p.key: p for p in SysParam.query.all()}
    models = ModelConfig.query.order_by(ModelConfig.type, ModelConfig.name).all()
    return render_template("settings/index.html", params=params, models=models)


@settings_bp.route("/params", methods=["POST"])
@login_required
def save_params():
    for key in request.form:
        if key.startswith("param_"):
            param_key = key[len("param_"):]
            param = SysParam.query.get(param_key)
            if param:
                param.value = request.form[key]
    db.session.commit()
    flash("Settings saved.", "success")
    return redirect(url_for("settings.index"))


@settings_bp.route("/models/new", methods=["GET", "POST"])
@login_required
def new_model():
    if request.method == "POST":
        config_raw = request.form.get("config_json", "{}")
        try:
            config_json = json.loads(config_raw)
        except json.JSONDecodeError as e:
            flash(f"Invalid JSON config: {e}", "danger")
            return redirect(url_for("settings.new_model"))

        model_id = request.form.get("id", "").strip()
        if not model_id:
            flash("Model ID is required.", "danger")
            return redirect(url_for("settings.new_model"))
        if ModelConfig.query.get(model_id):
            flash("A model with that ID already exists.", "danger")
            return redirect(url_for("settings.new_model"))

        mc = ModelConfig(
            id=model_id,
            type=request.form.get("type", "LLM"),
            name=request.form.get("name", model_id),
            description=request.form.get("description", ""),
            is_local=request.form.get("is_local") == "on",
            config_json=config_json,
        )
        db.session.add(mc)
        db.session.commit()
        flash(f'Model "{mc.name}" added.', "success")
        return redirect(url_for("settings.index"))

    model_types = ["VAD", "ASR", "LLM", "VLLM", "TTS", "Memory", "Intent"]
    return render_template("settings/model_form.html", model=None, model_types=model_types)


@settings_bp.route("/models/<model_id>", methods=["GET", "POST"])
@login_required
def edit_model(model_id):
    mc = ModelConfig.query.get_or_404(model_id)
    model_types = ["VAD", "ASR", "LLM", "VLLM", "TTS", "Memory", "Intent"]

    if request.method == "POST":
        config_raw = request.form.get("config_json", "{}")
        try:
            mc.config_json = json.loads(config_raw)
        except json.JSONDecodeError as e:
            flash(f"Invalid JSON config: {e}", "danger")
            return redirect(url_for("settings.edit_model", model_id=model_id))

        mc.name = request.form.get("name", mc.name)
        mc.description = request.form.get("description", "")
        mc.is_local = request.form.get("is_local") == "on"
        db.session.commit()
        flash(f'Model "{mc.name}" updated.', "success")
        return redirect(url_for("settings.index"))

    return render_template("settings/model_form.html", model=mc, model_types=model_types)


@settings_bp.route("/models/<model_id>/delete", methods=["POST"])
@login_required
def delete_model(model_id):
    mc = ModelConfig.query.get_or_404(model_id)
    db.session.delete(mc)
    db.session.commit()
    flash(f'Model "{mc.name}" deleted.', "success")
    return redirect(url_for("settings.index"))
