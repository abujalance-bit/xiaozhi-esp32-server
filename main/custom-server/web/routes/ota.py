"""Flask OTA endpoint for ESP32 devices.

xiaozhi-server's own HTTP server (port 8003) skips OTA registration when
read_config_from_api=True (API mode). In the custom-server stack this flag is
always True, so OTA *must* be served here on the Flask port.

Routes (no auth — called directly by ESP32 hardware):
  GET  /xiaozhi/ota/                     — health check, plain text
  POST /xiaozhi/ota/                     — OTA response: server_time, websocket, firmware
  GET  /xiaozhi/ota/download/<filename>  — firmware binary download
"""
import glob
import os
import re
import socket
import time

from flask import Blueprint, abort, jsonify, request, send_from_directory

ota_bp = Blueprint("ota", __name__)

_ROUTES_DIR = os.path.dirname(os.path.abspath(__file__))
_SERVER_DATA_DIR = os.environ.get("SERVER_DATA_DIR") or os.path.normpath(
    os.path.join(_ROUTES_DIR, "../../../xiaozhi-server/data")
)


def _get_lan_ip() -> str:
    host = os.environ.get("SERVER_HOST")
    if host and host not in ("localhost", "127.0.0.1"):
        return host
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def _parse_version(ver: str):
    parts = re.findall(r"\d+", ver)
    return tuple(int(p) for p in parts) if parts else (0,)


def _is_higher_version(a: str, b: str) -> bool:
    ta, tb = _parse_version(a), _parse_version(b)
    maxlen = max(len(ta), len(tb))
    for i in range(maxlen):
        if (ta[i] if i < len(ta) else 0) > (tb[i] if i < len(tb) else 0):
            return True
        if (ta[i] if i < len(ta) else 0) < (tb[i] if i < len(tb) else 0):
            return False
    return False


def _find_newer_firmware(model: str, current_version: str):
    """Return (version, filename) of a newer firmware, or (None, None)."""
    bin_dir = os.path.join(_SERVER_DATA_DIR, "bin")
    if not os.path.isdir(bin_dir):
        return None, None
    candidates = []
    for path in glob.glob(os.path.join(bin_dir, "*.bin")):
        fname = os.path.basename(path)
        m = re.match(r"^(.+?)_([0-9][A-Za-z0-9.\-_]*)\.bin$", fname)
        if m and m.group(1) == model:
            candidates.append((m.group(2), fname))
    candidates.sort(key=lambda x: _parse_version(x[0]), reverse=True)
    for ver, fname in candidates:
        if _is_higher_version(ver, current_version):
            return ver, fname
    return None, None


@ota_bp.get("/xiaozhi/ota/")
def ota_get():
    ws_host = _get_lan_ip()
    ws_port = int(os.environ.get("WS_PORT", 8000))
    return (
        f"OTA service running. WebSocket URL: ws://{ws_host}:{ws_port}/xiaozhi/v1/",
        200,
        {"Content-Type": "text/plain; charset=utf-8"},
    )


@ota_bp.post("/xiaozhi/ota/")
def ota_post():
    device_id = request.headers.get("device-id", "").strip()
    client_id = request.headers.get("client-id", "").strip()
    if not device_id or not client_id:
        return jsonify({"success": False, "message": "device-id and client-id headers required"}), 400

    try:
        data_json = request.get_json(silent=True) or {}
    except Exception:
        data_json = {}

    # Device model
    device_model = ""
    for h in ("device-model", "device_model", "model"):
        v = request.headers.get(h, "").strip()
        if v:
            device_model = v
            break
    if not device_model:
        try:
            board = data_json.get("board", {})
            device_model = (board.get("type") if isinstance(board, dict) else None) or data_json.get("model", "")
        except Exception:
            pass
    if not device_model:
        device_model = "default"

    # Device firmware version
    device_version = ""
    for h in ("device-version", "device_version", "firmware-version", "app-version", "application-version"):
        v = request.headers.get(h, "").strip()
        if v:
            device_version = v
            break
    if not device_version:
        try:
            device_version = data_json.get("application", {}).get("version", "")
        except Exception:
            pass
    if not device_version:
        device_version = "0.0.0"

    ws_host = _get_lan_ip()
    ws_port = int(os.environ.get("WS_PORT", 8000))
    flask_port = int(os.environ.get("FLASK_PORT", 5001))

    # Timezone offset in minutes (positive = east of UTC)
    if time.daylight and time.localtime().tm_isdst:
        tz_offset_min = -time.altzone // 60
    else:
        tz_offset_min = -time.timezone // 60

    body = {
        "server_time": {
            "timestamp": int(round(time.time() * 1000)),
            "timezone_offset": tz_offset_min,
        },
        "firmware": {
            "version": device_version,
            "url": "",
        },
        "websocket": {
            "url": f"ws://{ws_host}:{ws_port}/xiaozhi/v1/",
            "token": "",
        },
    }

    try:
        new_ver, fname = _find_newer_firmware(device_model, device_version)
        if new_ver and fname:
            body["firmware"]["version"] = new_ver
            body["firmware"]["url"] = f"http://{ws_host}:{flask_port}/xiaozhi/ota/download/{fname}"
    except Exception:
        pass

    return jsonify(body)


@ota_bp.get("/xiaozhi/ota/download/<filename>")
def ota_download(filename):
    safe = os.path.basename(filename)
    if not re.match(r"^[A-Za-z0-9.\-_]+\.bin$", safe):
        abort(400)

    bin_dir = os.path.realpath(os.path.join(_SERVER_DATA_DIR, "bin"))
    target = os.path.realpath(os.path.join(bin_dir, safe))

    if not target.startswith(bin_dir + os.sep):
        abort(403)
    if not os.path.isfile(target):
        abort(404)

    return send_from_directory(bin_dir, safe, as_attachment=True)
