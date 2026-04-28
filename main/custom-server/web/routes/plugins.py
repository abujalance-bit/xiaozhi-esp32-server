import json
from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required
from models import db, Plugin

plugins_bp = Blueprint("plugins", __name__)


@plugins_bp.route("/")
@login_required
def list_plugins():
    plugins = Plugin.query.order_by(Plugin.name).all()
    return render_template("plugins/list.html", plugins=plugins)


@plugins_bp.route("/<code>/toggle", methods=["POST"])
@login_required
def toggle_plugin(code):
    plugin = Plugin.query.get_or_404(code)
    plugin.enabled = not plugin.enabled
    db.session.commit()
    state = "enabled" if plugin.enabled else "disabled"
    flash(f'Plugin "{plugin.name}" {state}.', "success")
    return redirect(url_for("plugins.list_plugins"))


@plugins_bp.route("/<code>/config", methods=["GET", "POST"])
@login_required
def config_plugin(code):
    plugin = Plugin.query.get_or_404(code)
    if request.method == "POST":
        raw = request.form.get("params_json", "{}")
        try:
            plugin.params_json = json.loads(raw)
            db.session.commit()
            flash(f'Plugin "{plugin.name}" configuration saved.', "success")
        except json.JSONDecodeError as e:
            flash(f"Invalid JSON: {e}", "danger")
        return redirect(url_for("plugins.list_plugins"))
    return render_template("plugins/config.html", plugin=plugin)
