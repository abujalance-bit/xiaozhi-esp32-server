from flask import Blueprint, render_template
from flask_login import login_required
from models import Agent, Device, Plugin, ChatHistory
from datetime import datetime, timedelta

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/dashboard")
@login_required
def index():
    agent_count = Agent.query.count()
    device_count = Device.query.count()
    online_count = Device.query.filter_by(status="online").count()
    plugin_count = Plugin.query.filter_by(enabled=True).count()

    # Recent chat history (last 20 entries)
    recent_chats = (
        ChatHistory.query.order_by(ChatHistory.created_at.desc()).limit(20).all()
    )

    # Devices with recent activity (last 5 minutes)
    cutoff = datetime.utcnow() - timedelta(minutes=5)
    active_devices = Device.query.filter(Device.last_seen >= cutoff).all()

    return render_template(
        "dashboard.html",
        agent_count=agent_count,
        device_count=device_count,
        online_count=online_count,
        plugin_count=plugin_count,
        recent_chats=recent_chats,
        active_devices=active_devices,
    )
