from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required
from models import db, Device, Agent

devices_bp = Blueprint("devices", __name__)


@devices_bp.route("/")
@login_required
def list_devices():
    devices = Device.query.order_by(Device.created_at.desc()).all()
    return render_template("devices/list.html", devices=devices)


@devices_bp.route("/new", methods=["GET", "POST"])
@login_required
def new_device():
    agents = Agent.query.order_by(Agent.name).all()
    if request.method == "POST":
        mac = request.form.get("mac_address", "").upper().strip()
        if not mac:
            flash("MAC address is required.", "danger")
            return render_template("devices/form.html", device=None, agents=agents)
        if Device.query.filter_by(mac_address=mac).first():
            flash("A device with that MAC address already exists.", "danger")
            return render_template("devices/form.html", device=None, agents=agents)
        device = Device(
            mac_address=mac,
            name=request.form.get("name", "").strip(),
            agent_id=request.form.get("agent_id") or None,
        )
        db.session.add(device)
        db.session.commit()
        flash("Device registered.", "success")
        return redirect(url_for("devices.list_devices"))
    return render_template("devices/form.html", device=None, agents=agents)


@devices_bp.route("/<device_id>", methods=["GET", "POST"])
@login_required
def edit_device(device_id):
    device = Device.query.get_or_404(device_id)
    agents = Agent.query.order_by(Agent.name).all()
    if request.method == "POST":
        device.name = request.form.get("name", "").strip()
        device.agent_id = request.form.get("agent_id") or None
        db.session.commit()
        flash("Device updated.", "success")
        return redirect(url_for("devices.list_devices"))
    return render_template("devices/form.html", device=device, agents=agents)


@devices_bp.route("/<device_id>/delete", methods=["POST"])
@login_required
def delete_device(device_id):
    device = Device.query.get_or_404(device_id)
    db.session.delete(device)
    db.session.commit()
    flash("Device removed.", "success")
    return redirect(url_for("devices.list_devices"))
